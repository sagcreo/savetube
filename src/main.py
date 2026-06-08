import asyncio
import json
import logging
import os

import aiohttp
from aiohttp import web

from src.config import Settings
from src.downloader import Downloader
from src.url_parser import extract_urls
from src.cache import FileCache
from src.job_store import JobStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("savetube")

_ERROR_MAP = [
    ("not made this video available in your country", "Видео недоступно в стране сервера."),
    ("Private video", "Видео приватное."),
    ("Video unavailable", "Видео недоступно или удалено."),
    ("Sign in to confirm your age", "Видео доступно только для авторизованных (18+)."),
    ("is not a valid URL", "Некорректная ссылка."),
    ("copyright", "Видео заблокировано по авторским правам."),
]


def _friendly_error(raw: str) -> str:
    raw_lower = raw.lower()
    for pattern, message in _ERROR_MAP:
        if pattern.lower() in raw_lower:
            return message
    return "Не удалось обработать видео. Попробуйте позже."


def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def _fire_callback(url: str, payload: dict) -> None:
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10))
    except Exception:
        logger.warning("Callback to %s failed", url)


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def create_app() -> web.Application:
    settings = Settings()
    settings.validate()
    os.makedirs(settings.download_dir, exist_ok=True)

    downloader = Downloader(settings)
    cache = FileCache(ttl_minutes=settings.file_ttl_minutes, download_dir=settings.download_dir)
    semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
    job_store = JobStore()

    async def handle_index(_request: web.Request) -> web.Response:
        return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))

    async def handle_info(request: web.Request) -> web.Response:
        data = await request.json()
        url = data.get("url", "").strip()

        parsed = extract_urls(url)
        if not parsed:
            return _json_error("Неподдерживаемая ссылка. Поддерживаются YouTube и TikTok.")

        try:
            meta = await asyncio.wait_for(
                asyncio.to_thread(downloader.fetch_metadata, parsed[0].url),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            return _json_error("Не удалось получить информацию о видео: превышено время ожидания.", status=504)
        except ValueError as e:
            return _json_error(str(e))
        except Exception as e:
            logger.exception("Metadata fetch failed for %s", url)
            return _json_error(_friendly_error(str(e)), status=500)

        return web.json_response({
            "title": meta.title,
            "duration": meta.duration,
            "thumbnail": meta.thumbnail,
            "video_id": meta.video_id,
            "formats": [
                {"height": f.height, "ext": f.ext, "filesize": f.filesize}
                for f in meta.formats
            ],
        })

    async def handle_download(request: web.Request) -> web.Response:
        data = await request.json()
        url = data.get("url", "").strip()
        quality = int(data.get("quality", settings.default_quality))

        parsed = extract_urls(url)
        if not parsed:
            return _json_error("Неподдерживаемая ссылка.")

        video_url = parsed[0].url

        cached_path = cache.get(video_url, quality)
        if cached_path and os.path.exists(cached_path):
            filename = os.path.basename(cached_path)
            filesize = os.path.getsize(cached_path)
            return web.json_response({
                "status": "done",
                "file_url": f"/files/{filename}",
                "filename": filename,
                "filesize": filesize,
            })

        if semaphore.locked() and semaphore._value == 0:
            return _json_error("Очередь загрузок переполнена. Попробуйте позже.", status=429)

        response = web.StreamResponse()
        response.content_type = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"
        await response.prepare(request)

        async def send_event(payload: dict) -> None:
            line = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            await response.write(line.encode())

        await semaphore.acquire()
        try:
            progress_queue: asyncio.Queue[str] = asyncio.Queue()
            loop = asyncio.get_event_loop()
            download_done = asyncio.Event()
            result: dict = {}

            def on_progress(text: str) -> None:
                loop.call_soon_threadsafe(progress_queue.put_nowait, text)

            async def do_download() -> None:
                try:
                    filepath = await asyncio.to_thread(
                        downloader.download, video_url, quality, on_progress,
                    )
                    cache.put(video_url, quality, filepath)
                    filename = os.path.basename(filepath)
                    filesize = os.path.getsize(filepath)
                    result["file_url"] = f"/files/{filename}"
                    result["filename"] = filename
                    result["filesize"] = filesize
                except Exception as e:
                    logger.exception("Download failed for %s", video_url)
                    result["error"] = _friendly_error(str(e))
                finally:
                    download_done.set()

            asyncio.create_task(do_download())

            while not download_done.is_set():
                try:
                    text = await asyncio.wait_for(progress_queue.get(), timeout=2.0)
                    await send_event({"status": "progress", "text": text})
                except asyncio.TimeoutError:
                    continue

            while not progress_queue.empty():
                text = progress_queue.get_nowait()
                await send_event({"status": "progress", "text": text})

            if "error" in result:
                await send_event({"status": "error", "message": result["error"]})
            else:
                await send_event({"status": "done", **result})

        finally:
            semaphore.release()

        return response

    async def handle_create_job(request: web.Request) -> web.Response:
        data = await request.json()
        url = data.get("url", "").strip()
        quality = int(data.get("quality", settings.default_quality))
        callback_url = data.get("callback_url")

        parsed = extract_urls(url)
        if not parsed:
            return _json_error("Неподдерживаемая ссылка. Поддерживаются YouTube и TikTok.")

        video_url = parsed[0].url

        cached_path = cache.get(video_url, quality)
        if cached_path and os.path.exists(cached_path):
            job = await job_store.create()
            filename = os.path.basename(cached_path)
            filesize = os.path.getsize(cached_path)
            await job_store.update(
                job.id, status="done", progress=100,
                file_url=f"/files/{filename}", filename=filename, filesize=filesize,
            )
            return web.json_response(job_store.to_dict(await job_store.get(job.id)), status=201)

        if semaphore.locked() and semaphore._value == 0:
            return _json_error("Очередь загрузок переполнена. Попробуйте позже.", status=429)

        job = await job_store.create()

        async def run_job() -> None:
            await job_store.update(job.id, status="processing", progress=10)
            await semaphore.acquire()
            try:
                filepath = await asyncio.to_thread(downloader.download, video_url, quality)
                cache.put(video_url, quality, filepath)
                filename = os.path.basename(filepath)
                filesize = os.path.getsize(filepath)
                await job_store.update(
                    job.id, status="done", progress=100,
                    file_url=f"/files/{filename}", filename=filename, filesize=filesize,
                )
                if callback_url:
                    await _fire_callback(callback_url, {
                        "id": job.id, "status": "done", "file_url": f"/files/{filename}",
                    })
            except Exception as e:
                logger.exception("Job %s failed", job.id)
                error_msg = _friendly_error(str(e))
                await job_store.update(job.id, status="failed", error=error_msg)
                if callback_url:
                    await _fire_callback(callback_url, {
                        "id": job.id, "status": "failed", "error": error_msg,
                    })
            finally:
                semaphore.release()

        asyncio.create_task(run_job())
        return web.json_response(job_store.to_dict(job), status=201)

    async def handle_get_job(request: web.Request) -> web.Response:
        job_id = request.match_info["job_id"]
        job = await job_store.get(job_id)
        if job is None:
            return _json_error("Job not found", status=404)
        return web.json_response(job_store.to_dict(job))

    async def handle_download_job(request: web.Request) -> web.Response:
        job_id = request.match_info["job_id"]
        job = await job_store.get(job_id)
        if job is None:
            return _json_error("Job not found", status=404)
        if job.status != "done":
            return _json_error("Job not completed yet", status=400)
        raise web.HTTPFound(location=job.file_url)

    async def cleanup_loop(app: web.Application) -> None:
        while True:
            await asyncio.sleep(600)
            cache.cleanup()
            await job_store.cleanup_old()
            logger.info("Cache and job cleanup completed")

    async def on_startup(app: web.Application) -> None:
        app["cleanup_task"] = asyncio.create_task(cleanup_loop(app))

    async def on_shutdown(app: web.Application) -> None:
        app["cleanup_task"].cancel()

    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    app.router.add_get("/", handle_index)
    app.router.add_post("/api/info", handle_info)
    app.router.add_post("/api/download", handle_download)
    app.router.add_post("/api/jobs", handle_create_job)
    app.router.add_get("/api/jobs/{job_id}", handle_get_job)
    app.router.add_get("/api/jobs/{job_id}/download", handle_download_job)
    app.router.add_static("/files", settings.download_dir, show_index=False)

    return app


def main() -> None:
    settings = Settings()
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=settings.api_port)


if __name__ == "__main__":
    main()
