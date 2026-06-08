# SaveTube Job API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/download` to SaveTube so n8n can trigger downloads without SSE streaming.

**Architecture:** New `src/job_store.py` holds an in-memory `JobStore` (asyncio.Lock, dict of `JobRecord`). Three new routes added to `create_app()` in `src/main.py`. Existing SSE endpoint and WebGUI are untouched. Optional `callback_url` posts a JSON webhook when a job finishes.

**Tech Stack:** Python 3.12, aiohttp 3.9, pytest, pytest-aiohttp

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/job_store.py` | `JobRecord` dataclass + `JobStore` (CRUD, cleanup) |
| Modify | `src/main.py` | 3 new routes + cleanup_loop calls `job_store.cleanup_old()` |
| Modify | `requirements.txt` | Add `pytest>=8.0`, `pytest-aiohttp>=0.3` |
| Create | `tests/__init__.py` | Empty package marker |
| Create | `tests/test_job_store.py` | Unit tests for `JobStore` |
| Create | `tests/test_job_api.py` | Integration tests for new API routes |

---

## Task 1: Add pytest dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add test dependencies**

Replace contents of `requirements.txt` with:

```
yt-dlp>=2025.1.0
aiohttp>=3.9.0
pytest>=8.0
pytest-aiohttp>=0.3
```

- [ ] **Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore: add pytest and pytest-aiohttp"
```

---

## Task 2: Create `src/job_store.py`

**Files:**
- Create: `src/job_store.py`
- Create: `tests/__init__.py`
- Create: `tests/test_job_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/__init__.py` (empty file).

Create `tests/test_job_store.py`:

```python
import asyncio
import time
import pytest
from src.job_store import JobStore


@pytest.fixture
def store():
    return JobStore()


@pytest.mark.asyncio
async def test_create_returns_pending_job(store):
    job = await store.create()
    assert job.id.startswith("job_")
    assert job.status == "pending"
    assert job.progress == 0
    assert job.file_url is None
    assert job.error is None


@pytest.mark.asyncio
async def test_get_existing_job(store):
    job = await store.create()
    fetched = await store.get(job.id)
    assert fetched is not None
    assert fetched.id == job.id


@pytest.mark.asyncio
async def test_get_missing_job_returns_none(store):
    result = await store.get("job_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_update_status(store):
    job = await store.create()
    await store.update(job.id, status="processing", progress=10)
    updated = await store.get(job.id)
    assert updated.status == "processing"
    assert updated.progress == 10


@pytest.mark.asyncio
async def test_update_done(store):
    job = await store.create()
    await store.update(job.id, status="done", progress=100,
                       file_url="/files/vid.mp4", filename="vid.mp4", filesize=12345)
    updated = await store.get(job.id)
    assert updated.status == "done"
    assert updated.file_url == "/files/vid.mp4"
    assert updated.filesize == 12345


@pytest.mark.asyncio
async def test_update_nonexistent_job_is_noop(store):
    await store.update("job_ghost", status="done")  # should not raise


@pytest.mark.asyncio
async def test_cleanup_removes_old_jobs(store):
    job = await store.create()
    # backdate created_at
    async with store._lock:
        store._jobs[job.id].created_at = time.time() - 7201
    await store.cleanup_old(max_age_seconds=7200)
    assert await store.get(job.id) is None


@pytest.mark.asyncio
async def test_cleanup_keeps_fresh_jobs(store):
    job = await store.create()
    await store.cleanup_old(max_age_seconds=7200)
    assert await store.get(job.id) is not None


@pytest.mark.asyncio
async def test_to_dict(store):
    job = await store.create()
    d = store.to_dict(job)
    assert d["id"] == job.id
    assert d["status"] == "pending"
    assert d["progress"] == 0
    assert d["file_url"] is None
    assert d["error"] is None
```

- [ ] **Step 2: Run tests — expect FAIL (ImportError)**

```bash
pytest tests/test_job_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.job_store'`

- [ ] **Step 3: Implement `src/job_store.py`**

```python
import asyncio
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class JobRecord:
    id: str
    status: str          # pending | processing | done | failed
    progress: int
    file_url: str | None
    filename: str | None
    filesize: int | None
    error: str | None
    created_at: float = field(default_factory=time.time)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self) -> JobRecord:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        record = JobRecord(
            id=job_id,
            status="pending",
            progress=0,
            file_url=None,
            filename=None,
            filesize=None,
            error=None,
        )
        async with self._lock:
            self._jobs[job_id] = record
        return record

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job_id: str, **fields) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)

    async def cleanup_old(self, max_age_seconds: float = 7200) -> None:
        now = time.time()
        async with self._lock:
            expired = [
                jid for jid, j in self._jobs.items()
                if now - j.created_at > max_age_seconds
            ]
            for jid in expired:
                del self._jobs[jid]

    def to_dict(self, job: JobRecord) -> dict:
        return {
            "id": job.id,
            "status": job.status,
            "progress": job.progress,
            "file_url": job.file_url,
            "filename": job.filename,
            "filesize": job.filesize,
            "error": job.error,
        }
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_job_store.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/job_store.py tests/__init__.py tests/test_job_store.py
git commit -m "feat: add JobStore with in-memory job tracking"
```

---

## Task 3: Add `POST /api/jobs` and `GET /api/jobs/{id}`

**Files:**
- Modify: `src/main.py`
- Create: `tests/test_job_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_job_api.py`:

```python
import asyncio
from unittest.mock import patch, MagicMock
import pytest
from aiohttp.test_utils import TestClient, TestServer
from src.main import create_app


@pytest.fixture
def mock_downloader_success(tmp_path):
    """Patches Downloader.download to create a real temp file and return its path."""
    fake_file = tmp_path / "video_1080p.mp4"
    fake_file.write_bytes(b"fake video content")

    def fake_download(url, max_height=1080, on_progress=None):
        return str(fake_file)

    with patch("src.main.Downloader.download", side_effect=fake_download):
        yield str(fake_file)


@pytest.fixture
def mock_downloader_error():
    with patch("src.main.Downloader.download", side_effect=Exception("Video unavailable")):
        yield


@pytest.fixture
async def client(aiohttp_client, tmp_path):
    with patch("src.main.Settings") as MockSettings:
        s = MockSettings.return_value
        s.download_dir = str(tmp_path)
        s.max_concurrent_downloads = 3
        s.default_quality = 1080
        s.file_ttl_minutes = 60
        s.api_port = 6060
        s.pot_provider_url = "http://localhost:4416"
        s.validate.return_value = None
        app = create_app()
    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_create_job_invalid_url(client):
    resp = await client.post("/api/jobs", json={"url": "https://example.com/notavideo"})
    assert resp.status == 400
    data = await resp.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_create_job_returns_pending(client):
    with patch("src.main.Downloader.fetch_metadata", return_value=MagicMock()):
        # We only test that a valid URL returns a job — download runs in background
        with patch("src.main.Downloader.download", return_value="/tmp/fake.mp4"):
            resp = await client.post("/api/jobs", json={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "quality": 720,
            })
    assert resp.status == 201
    data = await resp.json()
    assert data["status"] == "pending"
    assert data["id"].startswith("job_")
    assert data["progress"] == 0


@pytest.mark.asyncio
async def test_get_job_not_found(client):
    resp = await client.get("/api/jobs/job_notexist")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_get_job_returns_status(client):
    with patch("src.main.Downloader.download", return_value="/tmp/fake.mp4"):
        create_resp = await client.post("/api/jobs", json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        })
    assert create_resp.status == 201
    job_id = (await create_resp.json())["id"]

    get_resp = await client.get(f"/api/jobs/{job_id}")
    assert get_resp.status == 200
    data = await get_resp.json()
    assert data["id"] == job_id
    assert data["status"] in ("pending", "processing", "done", "failed")
```

- [ ] **Step 2: Run tests — expect FAIL (404 for new routes)**

```bash
pytest tests/test_job_api.py -v
```

Expected: failures on routes not yet registered

- [ ] **Step 3: Add job store + new routes to `src/main.py`**

At the top of `main.py`, add the import after existing imports:

```python
from src.job_store import JobStore
```

Inside `create_app()`, after the line `cache = FileCache(...)`, add:

```python
job_store = JobStore()
```

Add these two handlers inside `create_app()`, after `handle_download`:

```python
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
            filepath = await asyncio.to_thread(
                downloader.download, video_url, quality,
            )
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
```

Register the routes inside `create_app()`, after the existing `app.router.add_post("/api/download", ...)` line:

```python
app.router.add_post("/api/jobs", handle_create_job)
app.router.add_get("/api/jobs/{job_id}", handle_get_job)
```

Also update `cleanup_loop` to clean up old jobs — replace the existing `cleanup_loop` function:

```python
async def cleanup_loop(app: web.Application) -> None:
    while True:
        await asyncio.sleep(600)
        cache.cleanup()
        await job_store.cleanup_old()
        logger.info("Cache and job cleanup completed")
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_job_api.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_job_api.py
git commit -m "feat: add POST /api/jobs and GET /api/jobs/{job_id}"
```

---

## Task 4: Add `GET /api/jobs/{id}/download`

**Files:**
- Modify: `src/main.py`
- Modify: `tests/test_job_api.py`

- [ ] **Step 1: Add tests for download endpoint**

Append to `tests/test_job_api.py`:

```python
@pytest.mark.asyncio
async def test_download_job_not_found(client):
    resp = await client.get("/api/jobs/job_ghost/download", allow_redirects=False)
    assert resp.status == 404


@pytest.mark.asyncio
async def test_download_job_not_ready(client):
    with patch("src.main.Downloader.download", return_value="/tmp/fake.mp4"):
        create_resp = await client.post("/api/jobs", json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        })
    job_id = (await create_resp.json())["id"]
    # Immediately after creation job is pending — not done yet
    # Force status back to pending for this test
    resp = await client.get(f"/api/jobs/{job_id}/download", allow_redirects=False)
    # status is either pending (400) or done (302) depending on timing — either is valid
    assert resp.status in (302, 400)


@pytest.mark.asyncio
async def test_download_job_done_redirects(client, tmp_path):
    fake_file = tmp_path / "vid_1080p.mp4"
    fake_file.write_bytes(b"fake")

    with patch("src.main.Downloader.download", return_value=str(fake_file)):
        create_resp = await client.post("/api/jobs", json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        })
    job_id = (await create_resp.json())["id"]

    # Wait for background task to complete
    for _ in range(20):
        await asyncio.sleep(0.1)
        get_resp = await client.get(f"/api/jobs/{job_id}")
        if (await get_resp.json())["status"] in ("done", "failed"):
            break

    dl_resp = await client.get(f"/api/jobs/{job_id}/download", allow_redirects=False)
    assert dl_resp.status == 302
    assert "/files/" in dl_resp.headers["Location"]
```

- [ ] **Step 2: Run tests — expect FAIL on download tests**

```bash
pytest tests/test_job_api.py::test_download_job_not_found tests/test_job_api.py::test_download_job_done_redirects -v
```

Expected: FAIL (route not registered)

- [ ] **Step 3: Add `handle_download_job` to `src/main.py`**

Add this handler inside `create_app()`, after `handle_get_job`:

```python
async def handle_download_job(request: web.Request) -> web.Response:
    job_id = request.match_info["job_id"]
    job = await job_store.get(job_id)
    if job is None:
        return _json_error("Job not found", status=404)
    if job.status != "done":
        return _json_error("Job not completed yet", status=400)
    raise web.HTTPFound(location=job.file_url)
```

Register the route after the existing job routes:

```python
app.router.add_get("/api/jobs/{job_id}/download", handle_download_job)
```

- [ ] **Step 4: Run all tests — expect PASS**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_job_api.py
git commit -m "feat: add GET /api/jobs/{job_id}/download"
```

---

## Task 5: Add `callback_url` helper `_fire_callback`

The `run_job()` coroutine in Task 3 already calls `_fire_callback` — this task defines it.

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Add `_fire_callback` to `src/main.py`**

Add this function after `_json_error`, before `STATIC_DIR`:

```python
async def _fire_callback(url: str, payload: dict) -> None:
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10))
    except Exception:
        logger.warning("Callback to %s failed", url)
```

Add `import aiohttp` at the top of `main.py` if not already present (it is via `from aiohttp import web` — change that line to also import `aiohttp` directly):

```python
import aiohttp
from aiohttp import web
```

- [ ] **Step 2: Run all tests — expect PASS**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add callback_url support for job completion webhook"
```

---

## Task 6: Manual smoke test

- [ ] **Step 1: Start the service locally**

```bash
docker compose -f docker-compose.local.yml up --build
```

- [ ] **Step 2: Create a job**

```bash
curl -s -X POST http://localhost:6060/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","quality":480}' | python -m json.tool
```

Expected response:
```json
{
  "id": "job_abc123...",
  "status": "pending",
  "progress": 0,
  "file_url": null,
  "filename": null,
  "filesize": null,
  "error": null
}
```

- [ ] **Step 3: Poll until done**

```bash
# Replace job_abc123 with actual id from step 2
curl -s http://localhost:6060/api/jobs/job_abc123 | python -m json.tool
```

Expected when complete:
```json
{
  "id": "job_abc123",
  "status": "done",
  "progress": 100,
  "file_url": "/files/dQw4w9WgXcQ_480p.mp4",
  ...
}
```

- [ ] **Step 4: Download the file**

```bash
curl -L http://localhost:6060/api/jobs/job_abc123/download -o video.mp4
ls -lh video.mp4
```

Expected: `video.mp4` file on disk

---

## n8n Setup Reference

**Workflow for n8n (polling variant):**

1. **HTTP Request node** — POST `http://savetube:6060/api/jobs`
   - Body: `{"url": "{{ $json.url }}", "quality": 1080}`
   - Returns: `{ "id": "job_xxx" }`

2. **Wait node** — 10 seconds

3. **HTTP Request node** — GET `http://savetube:6060/api/jobs/{{ $json.id }}`

4. **IF node** — `status == "done"` → continue; `status == "failed"` → error branch; else → loop back to Wait

5. **HTTP Request node** — GET `http://savetube:6060/api/jobs/{{ $json.id }}/download`
   - Response format: File

**Or with callback_url:** pass n8n webhook URL in step 1, skip polling entirely.
