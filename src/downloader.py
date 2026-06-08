import os
from dataclasses import dataclass
from typing import Callable
from yt_dlp import YoutubeDL
from src.config import Settings

ProgressCallback = Callable[[str], None]  # (status_line)


@dataclass
class VideoFormat:
    height: int
    ext: str
    filesize: int | None


@dataclass
class VideoMetadata:
    title: str
    duration: int
    thumbnail: str
    formats: list[VideoFormat]
    video_id: str


class Downloader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _base_opts(self) -> dict:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 20,
            "retry_sleep_functions": {"http": lambda n: 2 ** n},
            "extractor_args": {
                "youtube": {
                    "player_client": ["web_embedded", "tv", "android_vr"],
                },
                "youtubepot-bgutilhttp": {
                    "base_url": [self.settings.pot_provider_url],
                },
            },
        }
        if self.settings.cookies_file:
            opts["cookiefile"] = self.settings.cookies_file
        if self.settings.yt_proxy:
            opts["proxy"] = self.settings.yt_proxy
        return opts

    def fetch_metadata(self, url: str) -> VideoMetadata:
        opts = self._base_opts()

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        duration = info.get("duration") or 0
        if duration > self.settings.max_video_duration:
            limit_min = self.settings.max_video_duration // 60
            raise ValueError(f"Video too long ({duration}s). Max: {limit_min} min")

        formats: list[VideoFormat] = []
        seen_heights: set[int] = set()

        for f in info.get("formats", []):
            height = f.get("height")
            vcodec = f.get("vcodec", "none")
            if not height or height <= 0 or vcodec == "none":
                continue
            if height in seen_heights:
                continue
            seen_heights.add(height)
            formats.append(VideoFormat(
                height=height,
                ext=f.get("ext", "mp4"),
                filesize=f.get("filesize") or f.get("filesize_approx"),
            ))

        formats.sort(key=lambda f: f.height)

        return VideoMetadata(
            title=info.get("title", "Unknown"),
            duration=duration,
            thumbnail=info.get("thumbnail", ""),
            formats=formats,
            video_id=info.get("id", ""),
        )

    def download(self, url: str, max_height: int = 1080, on_progress: ProgressCallback | None = None) -> str:
        os.makedirs(self.settings.download_dir, exist_ok=True)

        opts = self._base_opts()
        opts.update({
            "format": f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best",
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(self.settings.download_dir, "%(id)s_%(height)sp.%(ext)s"),
        })

        if on_progress:
            stream_index = [0]
            labels = ["видео", "аудио"]

            def _hook(d):
                status = d.get("status")
                if status == "finished":
                    stream_index[0] += 1
                    return
                if status != "downloading":
                    return
                label = labels[stream_index[0]] if stream_index[0] < len(labels) else "данные"
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                speed = d.get("_speed_str", "").strip()
                if total:
                    pct = downloaded / total * 100
                    line = f"Скачиваю {label}: {pct:.0f}%"
                else:
                    mb = downloaded / (1024 * 1024)
                    line = f"Скачиваю {label}: {mb:.1f} MB"
                if speed:
                    line += f" · {speed}"
                on_progress(line)

            opts["progress_hooks"] = [_hook]

            def _pp_hook(d):
                if d.get("status") == "started":
                    on_progress("Объединяю видео и аудио...")

            opts["postprocessor_hooks"] = [_pp_hook]

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        downloads = info.get("requested_downloads", [])
        if downloads:
            return downloads[0]["filepath"]

        video_id = info.get("id", "video")
        ext = info.get("ext", "mp4")
        return os.path.join(self.settings.download_dir, f"{video_id}_{max_height}p.{ext}")
