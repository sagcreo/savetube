# SaveTube Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Slack bot that downloads YouTube and TikTok videos via yt-dlp with PO Token support, deployed as a single Docker container.

**Architecture:** Python Slack Bolt app in Socket Mode listens for URLs in messages, fetches video metadata via yt-dlp, presents quality options as Block Kit buttons, downloads selected quality, uploads file to Slack thread. Async task queue manages concurrency. bgutil-ytdlp-pot-provider runs as a sidecar Docker container for YouTube PO Token generation.

**Tech Stack:** Python 3.12, slack-bolt, yt-dlp, bgutil-ytdlp-pot-provider (Docker), asyncio, aiohttp (file server fallback), pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-04-13-savetube-design.md`

---

## File Structure

```
savetube/
├── src/
│   ├── __init__.py            — empty
│   ├── config.py              — Settings dataclass from env vars
│   ├── url_parser.py          — URL regex detection, platform enum
│   ├── downloader.py          — yt-dlp wrapper: metadata + download
│   ├── cache.py               — In-memory file cache with TTL cleanup
│   ├── queue.py               — Async download queue with semaphore
│   ├── slack_blocks.py        — Block Kit message builders
│   ├── slack_handlers.py      — Slack message/action event handlers
│   ├── file_server.py         — aiohttp static file server (fallback)
│   └── main.py                — Entry point: wires everything together
├── tests/
│   ├── __init__.py            — empty
│   ├── test_url_parser.py     — URL parsing tests
│   ├── test_config.py         — Config loading tests
│   ├── test_downloader.py     — Downloader tests (mocked yt-dlp)
│   ├── test_cache.py          — Cache TTL and eviction tests
│   ├── test_queue.py          — Queue concurrency tests
│   └── test_slack_blocks.py   — Block Kit output tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── .gitignore
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
slack-bolt>=1.18.0
yt-dlp>=2025.1.0
aiohttp>=3.9.0
```

- [ ] **Step 2: Create requirements-dev.txt**

```
-r requirements.txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 3: Create .env.example**

```bash
# Slack tokens (required)
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Download settings
DOWNLOAD_DIR=/tmp/downloads
MAX_CONCURRENT_DOWNLOADS=3
MAX_VIDEO_DURATION=3600
MAX_QUEUE_SIZE=10
DEFAULT_QUALITY=1080
FILE_TTL_MINUTES=60
DOWNLOAD_DELAY_SECONDS=7

# Fallback file server
FILE_SERVER_PORT=6060
FILE_SERVER_BASE_URL=http://your-server-ip:6060

# PO Token provider
POT_PROVIDER_URL=http://bgutil-provider:4416
```

- [ ] **Step 4: Create .gitignore**

```
__pycache__/
*.pyc
.env
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
downloads/
```

- [ ] **Step 5: Create empty __init__.py files**

Create empty `src/__init__.py` and `tests/__init__.py`.

- [ ] **Step 6: Verify project structure**

Run: `ls -R src/ tests/`

Expected: both directories exist with `__init__.py` files.

- [ ] **Step 7: Install dependencies**

Run: `pip install -r requirements-dev.txt`

Expected: all packages install successfully.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt requirements-dev.txt .env.example .gitignore src/__init__.py tests/__init__.py
git commit -m "chore: scaffold project with dependencies and config"
```

---

### Task 2: Config module

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import os
import pytest
from src.config import Settings


def test_settings_defaults():
    """Settings should have sensible defaults when env vars are missing."""
    settings = Settings()
    assert settings.download_dir == "/tmp/downloads"
    assert settings.max_concurrent_downloads == 3
    assert settings.max_video_duration == 3600
    assert settings.max_queue_size == 10
    assert settings.default_quality == 1080
    assert settings.file_ttl_minutes == 60
    assert settings.download_delay_seconds == 7
    assert settings.file_server_port == 6060
    assert settings.pot_provider_url == "http://bgutil-provider:4416"


def test_settings_from_env(monkeypatch):
    """Settings should read from environment variables."""
    monkeypatch.setenv("DOWNLOAD_DIR", "/data/videos")
    monkeypatch.setenv("MAX_CONCURRENT_DOWNLOADS", "5")
    monkeypatch.setenv("MAX_VIDEO_DURATION", "7200")
    monkeypatch.setenv("DEFAULT_QUALITY", "720")
    settings = Settings()
    assert settings.download_dir == "/data/videos"
    assert settings.max_concurrent_downloads == 5
    assert settings.max_video_duration == 7200
    assert settings.default_quality == 720


def test_settings_requires_slack_tokens_for_validate():
    """validate() should raise if Slack tokens are missing."""
    settings = Settings()
    with pytest.raises(ValueError, match="SLACK_BOT_TOKEN"):
        settings.validate()


def test_settings_validate_ok(monkeypatch):
    """validate() should pass with both tokens set."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    settings = Settings()
    settings.validate()  # should not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Write implementation**

```python
# src/config.py
import os
from dataclasses import dataclass


@dataclass
class Settings:
    slack_bot_token: str = ""
    slack_app_token: str = ""
    download_dir: str = "/tmp/downloads"
    max_concurrent_downloads: int = 3
    max_video_duration: int = 3600
    max_queue_size: int = 10
    default_quality: int = 1080
    file_ttl_minutes: int = 60
    download_delay_seconds: int = 7
    file_server_port: int = 6060
    file_server_base_url: str = ""
    pot_provider_url: str = "http://bgutil-provider:4416"

    def __post_init__(self):
        self.slack_bot_token = os.getenv("SLACK_BOT_TOKEN", self.slack_bot_token)
        self.slack_app_token = os.getenv("SLACK_APP_TOKEN", self.slack_app_token)
        self.download_dir = os.getenv("DOWNLOAD_DIR", self.download_dir)
        self.max_concurrent_downloads = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", self.max_concurrent_downloads))
        self.max_video_duration = int(os.getenv("MAX_VIDEO_DURATION", self.max_video_duration))
        self.max_queue_size = int(os.getenv("MAX_QUEUE_SIZE", self.max_queue_size))
        self.default_quality = int(os.getenv("DEFAULT_QUALITY", self.default_quality))
        self.file_ttl_minutes = int(os.getenv("FILE_TTL_MINUTES", self.file_ttl_minutes))
        self.download_delay_seconds = int(os.getenv("DOWNLOAD_DELAY_SECONDS", self.download_delay_seconds))
        self.file_server_port = int(os.getenv("FILE_SERVER_PORT", self.file_server_port))
        self.file_server_base_url = os.getenv("FILE_SERVER_BASE_URL", self.file_server_base_url)
        self.pot_provider_url = os.getenv("POT_PROVIDER_URL", self.pot_provider_url)

    def validate(self):
        if not self.slack_bot_token:
            raise ValueError("SLACK_BOT_TOKEN is required")
        if not self.slack_app_token:
            raise ValueError("SLACK_APP_TOKEN is required")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add config module with env-based settings"
```

---

### Task 3: URL parser

**Files:**
- Create: `src/url_parser.py`
- Create: `tests/test_url_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_url_parser.py
import pytest
from src.url_parser import extract_urls, Platform


def test_youtube_watch_url():
    urls = extract_urls("check this https://www.youtube.com/watch?v=dQw4w9WgXcQ cool video")
    assert len(urls) == 1
    assert urls[0].platform == Platform.YOUTUBE
    assert urls[0].url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_youtube_short_url():
    urls = extract_urls("https://youtu.be/dQw4w9WgXcQ")
    assert len(urls) == 1
    assert urls[0].platform == Platform.YOUTUBE


def test_youtube_shorts_url():
    urls = extract_urls("https://youtube.com/shorts/abc123")
    assert len(urls) == 1
    assert urls[0].platform == Platform.YOUTUBE


def test_tiktok_url():
    urls = extract_urls("https://www.tiktok.com/@user/video/1234567890")
    assert len(urls) == 1
    assert urls[0].platform == Platform.TIKTOK


def test_tiktok_short_url():
    urls = extract_urls("https://vm.tiktok.com/ZMhAbCdEf/")
    assert len(urls) == 1
    assert urls[0].platform == Platform.TIKTOK


def test_multiple_urls():
    text = "here https://youtu.be/abc and https://www.tiktok.com/@u/video/123"
    urls = extract_urls(text)
    assert len(urls) == 2
    assert urls[0].platform == Platform.YOUTUBE
    assert urls[1].platform == Platform.TIKTOK


def test_no_urls():
    urls = extract_urls("just a normal message with no links")
    assert len(urls) == 0


def test_unknown_url_ignored():
    urls = extract_urls("https://www.google.com and https://youtu.be/abc")
    assert len(urls) == 1
    assert urls[0].platform == Platform.YOUTUBE


def test_slack_angle_bracket_urls():
    """Slack wraps URLs in angle brackets."""
    urls = extract_urls("<https://www.youtube.com/watch?v=dQw4w9WgXcQ>")
    assert len(urls) == 1
    assert urls[0].platform == Platform.YOUTUBE
    assert ">" not in urls[0].url
    assert "<" not in urls[0].url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_url_parser.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'src.url_parser'`

- [ ] **Step 3: Write implementation**

```python
# src/url_parser.py
import re
from enum import Enum
from dataclasses import dataclass


class Platform(Enum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"


@dataclass
class ParsedURL:
    url: str
    platform: Platform


# Patterns match URLs that Slack may wrap in < >
_YOUTUBE_RE = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[\w\-]+'
)
_TIKTOK_RE = re.compile(
    r'https?://(?:www\.|vm\.)?tiktok\.com/\S+'
)


def extract_urls(text: str) -> list[ParsedURL]:
    """Extract YouTube and TikTok URLs from a message text.

    Strips Slack angle-bracket wrapping (<url>) if present.
    Returns only recognized platform URLs; unknown links are ignored.
    """
    # Strip Slack's angle-bracket URL wrapping: <https://...> -> https://...
    cleaned = re.sub(r'<(https?://[^>|]+)(?:\|[^>]*)?>', r'\1', text)

    results: list[ParsedURL] = []
    seen: set[str] = set()

    for pattern, platform in [(_YOUTUBE_RE, Platform.YOUTUBE), (_TIKTOK_RE, Platform.TIKTOK)]:
        for match in pattern.finditer(cleaned):
            url = match.group(0).rstrip("/")
            if url not in seen:
                seen.add(url)
                results.append(ParsedURL(url=url, platform=platform))

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_url_parser.py -v`

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/url_parser.py tests/test_url_parser.py
git commit -m "feat: add URL parser for YouTube and TikTok links"
```

---

### Task 4: Downloader module

**Files:**
- Create: `src/downloader.py`
- Create: `tests/test_downloader.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_downloader.py
import pytest
from unittest.mock import patch, MagicMock
from src.downloader import Downloader, VideoMetadata, VideoFormat
from src.config import Settings


@pytest.fixture
def downloader():
    settings = Settings()
    settings.download_dir = "/tmp/test_downloads"
    settings.pot_provider_url = "http://localhost:4416"
    return Downloader(settings)


def _make_formats():
    """Fake yt-dlp format list."""
    return [
        {
            "format_id": "18",
            "ext": "mp4",
            "height": 360,
            "filesize": 5_000_000,
            "vcodec": "avc1",
            "acodec": "mp4a",
        },
        {
            "format_id": "22",
            "ext": "mp4",
            "height": 720,
            "filesize": 18_000_000,
            "vcodec": "avc1",
            "acodec": "mp4a",
        },
        {
            "format_id": "137+140",
            "ext": "mp4",
            "height": 1080,
            "filesize": 45_000_000,
            "vcodec": "avc1",
            "acodec": "none",
        },
        {
            "format_id": "140",
            "ext": "m4a",
            "height": None,
            "filesize": 3_000_000,
            "vcodec": "none",
            "acodec": "mp4a",
        },
    ]


def _make_info(formats=None):
    return {
        "title": "Test Video",
        "duration": 212,
        "thumbnail": "https://i.ytimg.com/vi/abc/hqdefault.jpg",
        "formats": formats or _make_formats(),
        "id": "abc123",
        "ext": "mp4",
    }


@patch("src.downloader.YoutubeDL")
def test_fetch_metadata(mock_ydl_class, downloader):
    mock_ydl = MagicMock()
    mock_ydl_class.return_value.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = _make_info()

    meta = downloader.fetch_metadata("https://youtube.com/watch?v=abc123")

    assert meta.title == "Test Video"
    assert meta.duration == 212
    # Should only include formats with video (height > 0)
    assert len(meta.formats) >= 1
    assert all(f.height > 0 for f in meta.formats)


@patch("src.downloader.YoutubeDL")
def test_fetch_metadata_filters_audio_only(mock_ydl_class, downloader):
    mock_ydl = MagicMock()
    mock_ydl_class.return_value.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = _make_info()

    meta = downloader.fetch_metadata("https://youtube.com/watch?v=abc123")

    # audio-only format (height=None, vcodec=none) must be excluded
    format_heights = [f.height for f in meta.formats]
    assert None not in format_heights
    assert 0 not in format_heights


@patch("src.downloader.YoutubeDL")
def test_fetch_metadata_duration_exceeds_limit(mock_ydl_class, downloader):
    downloader.settings.max_video_duration = 60
    mock_ydl = MagicMock()
    mock_ydl_class.return_value.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)
    info = _make_info()
    info["duration"] = 3700
    mock_ydl.extract_info.return_value = info

    with pytest.raises(ValueError, match="too long"):
        downloader.fetch_metadata("https://youtube.com/watch?v=long")


@patch("src.downloader.YoutubeDL")
def test_download_video(mock_ydl_class, downloader):
    mock_ydl = MagicMock()
    mock_ydl_class.return_value.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)

    info = _make_info()
    info["requested_downloads"] = [{"filepath": "/tmp/test_downloads/video.mp4"}]
    mock_ydl.extract_info.return_value = info

    path = downloader.download("https://youtube.com/watch?v=abc123", max_height=1080)

    assert path == "/tmp/test_downloads/video.mp4"
    mock_ydl.extract_info.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_downloader.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'src.downloader'`

- [ ] **Step 3: Write implementation**

```python
# src/downloader.py
import os
from dataclasses import dataclass
from yt_dlp import YoutubeDL
from src.config import Settings


@dataclass
class VideoFormat:
    format_id: str
    height: int
    ext: str
    filesize: int | None  # bytes, may be None if unknown


@dataclass
class VideoMetadata:
    title: str
    duration: int  # seconds
    thumbnail: str
    formats: list[VideoFormat]
    video_id: str


class Downloader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _base_opts(self) -> dict:
        return {
            "quiet": True,
            "no_warnings": True,
            "extractor_args": {
                "youtubepot-bgutilhttp": {
                    "base_url": [self.settings.pot_provider_url],
                },
            },
        }

    def fetch_metadata(self, url: str) -> VideoMetadata:
        """Fetch video metadata without downloading."""
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
                format_id=f["format_id"],
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

    def download(self, url: str, max_height: int = 1080) -> str:
        """Download video and return file path."""
        os.makedirs(self.settings.download_dir, exist_ok=True)

        opts = self._base_opts()
        opts.update({
            "format": f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best",
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(self.settings.download_dir, "%(id)s_%(height)sp.%(ext)s"),
        })

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        downloads = info.get("requested_downloads", [])
        if downloads:
            return downloads[0]["filepath"]

        # Fallback: construct path from template
        video_id = info.get("id", "video")
        ext = info.get("ext", "mp4")
        return os.path.join(self.settings.download_dir, f"{video_id}_{max_height}p.{ext}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_downloader.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/downloader.py tests/test_downloader.py
git commit -m "feat: add yt-dlp downloader with metadata and PO Token support"
```

---

### Task 5: File cache

**Files:**
- Create: `src/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cache.py
import time
import pytest
from unittest.mock import patch
from src.cache import FileCache


def test_cache_put_and_get(tmp_path):
    cache = FileCache(ttl_minutes=60, download_dir=str(tmp_path))
    # Create a fake file
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"fake video content")

    cache.put("https://youtube.com/watch?v=abc", 1080, str(fake_file))
    result = cache.get("https://youtube.com/watch?v=abc", 1080)
    assert result == str(fake_file)


def test_cache_miss(tmp_path):
    cache = FileCache(ttl_minutes=60, download_dir=str(tmp_path))
    result = cache.get("https://youtube.com/watch?v=missing", 720)
    assert result is None


def test_cache_expired(tmp_path):
    cache = FileCache(ttl_minutes=0, download_dir=str(tmp_path))
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"fake video content")

    cache.put("https://youtube.com/watch?v=abc", 1080, str(fake_file))
    # TTL is 0 minutes, so it should be expired immediately
    time.sleep(0.1)
    result = cache.get("https://youtube.com/watch?v=abc", 1080)
    assert result is None


def test_cache_cleanup_removes_expired_files(tmp_path):
    cache = FileCache(ttl_minutes=0, download_dir=str(tmp_path))
    fake_file = tmp_path / "old_video.mp4"
    fake_file.write_bytes(b"old content")

    cache.put("https://youtube.com/watch?v=old", 720, str(fake_file))
    time.sleep(0.1)
    cache.cleanup()

    assert not fake_file.exists()
    assert cache.get("https://youtube.com/watch?v=old", 720) is None


def test_cache_different_qualities(tmp_path):
    cache = FileCache(ttl_minutes=60, download_dir=str(tmp_path))
    file_720 = tmp_path / "video_720.mp4"
    file_1080 = tmp_path / "video_1080.mp4"
    file_720.write_bytes(b"720 content")
    file_1080.write_bytes(b"1080 content")

    cache.put("https://youtube.com/watch?v=abc", 720, str(file_720))
    cache.put("https://youtube.com/watch?v=abc", 1080, str(file_1080))

    assert cache.get("https://youtube.com/watch?v=abc", 720) == str(file_720)
    assert cache.get("https://youtube.com/watch?v=abc", 1080) == str(file_1080)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cache.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'src.cache'`

- [ ] **Step 3: Write implementation**

```python
# src/cache.py
import os
import time
from dataclasses import dataclass, field


@dataclass
class _CacheEntry:
    filepath: str
    created_at: float


class FileCache:
    def __init__(self, ttl_minutes: int, download_dir: str):
        self._ttl_seconds = ttl_minutes * 60
        self._download_dir = download_dir
        self._entries: dict[str, _CacheEntry] = {}

    @staticmethod
    def _key(url: str, quality: int) -> str:
        return f"{url}::{quality}"

    def get(self, url: str, quality: int) -> str | None:
        """Return cached file path if exists and not expired, else None."""
        key = self._key(url, quality)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.time() - entry.created_at > self._ttl_seconds:
            del self._entries[key]
            return None
        if not os.path.exists(entry.filepath):
            del self._entries[key]
            return None
        return entry.filepath

    def put(self, url: str, quality: int, filepath: str) -> None:
        """Store a file path in cache."""
        key = self._key(url, quality)
        self._entries[key] = _CacheEntry(filepath=filepath, created_at=time.time())

    def cleanup(self) -> None:
        """Remove expired entries and delete their files from disk."""
        now = time.time()
        expired_keys = [
            key for key, entry in self._entries.items()
            if now - entry.created_at > self._ttl_seconds
        ]
        for key in expired_keys:
            entry = self._entries.pop(key)
            if os.path.exists(entry.filepath):
                os.remove(entry.filepath)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cache.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/cache.py tests/test_cache.py
git commit -m "feat: add file cache with TTL and cleanup"
```

---

### Task 6: Async download queue

**Files:**
- Create: `src/queue.py`
- Create: `tests/test_queue.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_queue.py
import asyncio
import pytest
import pytest_asyncio
from src.queue import DownloadQueue, DownloadJob


@pytest.fixture
def queue():
    return DownloadQueue(max_concurrent=2, max_queue_size=3, delay_seconds=0)


@pytest.mark.asyncio
async def test_queue_submit_and_process(queue):
    results = []

    async def fake_worker(job: DownloadJob):
        results.append(job.url)

    queue.set_worker(fake_worker)
    await queue.start()

    job = DownloadJob(url="https://youtube.com/watch?v=abc", quality=1080, channel_id="C123", thread_ts="123.456")
    await queue.submit(job)

    # Give the worker time to process
    await asyncio.sleep(0.1)
    await queue.stop()

    assert "https://youtube.com/watch?v=abc" in results


@pytest.mark.asyncio
async def test_queue_respects_max_size(queue):
    async def slow_worker(job: DownloadJob):
        await asyncio.sleep(10)

    queue.set_worker(slow_worker)
    await queue.start()

    # Fill queue: 2 active + 3 waiting = 5 max
    for i in range(5):
        job = DownloadJob(url=f"https://youtube.com/watch?v={i}", quality=1080, channel_id="C123", thread_ts=f"{i}.0")
        await queue.submit(job)

    # 6th should be rejected
    overflow_job = DownloadJob(url="https://youtube.com/watch?v=overflow", quality=1080, channel_id="C123", thread_ts="6.0")
    with pytest.raises(asyncio.QueueFull):
        await queue.submit(overflow_job)

    await queue.stop()


@pytest.mark.asyncio
async def test_queue_concurrency_limit(queue):
    """Should not run more than max_concurrent jobs at once."""
    peak_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    async def counting_worker(job: DownloadJob):
        nonlocal peak_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            peak_concurrent = max(peak_concurrent, current_concurrent)
        await asyncio.sleep(0.05)
        async with lock:
            current_concurrent -= 1

    queue.set_worker(counting_worker)
    await queue.start()

    for i in range(5):
        job = DownloadJob(url=f"https://youtube.com/watch?v={i}", quality=1080, channel_id="C123", thread_ts=f"{i}.0")
        await queue.submit(job)

    await asyncio.sleep(0.5)
    await queue.stop()

    assert peak_concurrent <= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_queue.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'src.queue'`

- [ ] **Step 3: Write implementation**

```python
# src/queue.py
import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable


@dataclass
class DownloadJob:
    url: str
    quality: int
    channel_id: str
    thread_ts: str


class DownloadQueue:
    def __init__(self, max_concurrent: int, max_queue_size: int, delay_seconds: float):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue: asyncio.Queue[DownloadJob] = asyncio.Queue(maxsize=max_queue_size)
        self._delay = delay_seconds
        self._worker: Callable[[DownloadJob], Awaitable[None]] | None = None
        self._tasks: list[asyncio.Task] = []
        self._running = False

    def set_worker(self, worker: Callable[[DownloadJob], Awaitable[None]]) -> None:
        self._worker = worker

    async def start(self) -> None:
        self._running = True
        self._tasks.append(asyncio.create_task(self._consumer()))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    async def submit(self, job: DownloadJob) -> None:
        """Add a job to the queue. Raises asyncio.QueueFull if queue is at capacity."""
        self._queue.put_nowait(job)

    async def _consumer(self) -> None:
        while self._running:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            asyncio.create_task(self._process(job))

    async def _process(self, job: DownloadJob) -> None:
        async with self._semaphore:
            if self._worker:
                try:
                    await self._worker(job)
                except Exception:
                    pass  # Error handling is the worker's responsibility
            if self._delay > 0:
                await asyncio.sleep(self._delay)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_queue.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/queue.py tests/test_queue.py
git commit -m "feat: add async download queue with concurrency limit"
```

---

### Task 7: Slack Block Kit message builders

**Files:**
- Create: `src/slack_blocks.py`
- Create: `tests/test_slack_blocks.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_slack_blocks.py
import pytest
from src.slack_blocks import build_quality_buttons, build_downloading_message, build_done_message, build_error_message
from src.downloader import VideoMetadata, VideoFormat


def _make_metadata():
    return VideoMetadata(
        title="Test Video",
        duration=212,
        thumbnail="https://example.com/thumb.jpg",
        video_id="abc123",
        formats=[
            VideoFormat(format_id="18", height=360, ext="mp4", filesize=5_000_000),
            VideoFormat(format_id="22", height=720, ext="mp4", filesize=18_000_000),
            VideoFormat(format_id="137", height=1080, ext="mp4", filesize=45_000_000),
        ],
    )


def test_quality_buttons_structure():
    meta = _make_metadata()
    blocks = build_quality_buttons(meta)
    # Should have a section with title + actions with buttons
    assert any(b["type"] == "section" for b in blocks)
    actions = [b for b in blocks if b["type"] == "actions"]
    assert len(actions) == 1
    buttons = actions[0]["elements"]
    assert len(buttons) == 3


def test_quality_buttons_labels():
    meta = _make_metadata()
    blocks = build_quality_buttons(meta)
    actions = [b for b in blocks if b["type"] == "actions"][0]
    labels = [btn["text"]["text"] for btn in actions["elements"]]
    assert "360p" in labels[0]
    assert "720p" in labels[1]
    assert "1080p" in labels[2]


def test_quality_buttons_action_ids():
    meta = _make_metadata()
    blocks = build_quality_buttons(meta)
    actions = [b for b in blocks if b["type"] == "actions"][0]
    for btn in actions["elements"]:
        assert btn["action_id"].startswith("download_")


def test_quality_buttons_filesize_display():
    meta = _make_metadata()
    blocks = build_quality_buttons(meta)
    actions = [b for b in blocks if b["type"] == "actions"][0]
    # 5MB should show as ~5 MB
    assert "5" in actions["elements"][0]["text"]["text"]


def test_quality_buttons_unknown_filesize():
    meta = VideoMetadata(
        title="Test", duration=60, thumbnail="", video_id="x",
        formats=[VideoFormat(format_id="1", height=720, ext="mp4", filesize=None)],
    )
    blocks = build_quality_buttons(meta)
    actions = [b for b in blocks if b["type"] == "actions"][0]
    # Should still render without crashing
    assert "720p" in actions["elements"][0]["text"]["text"]


def test_downloading_message():
    blocks = build_downloading_message(1080)
    text = blocks[0]["text"]["text"]
    assert "1080p" in text


def test_done_message():
    blocks = build_done_message("video.mp4", 45_200_000)
    text = blocks[0]["text"]["text"]
    assert "video.mp4" in text


def test_error_message():
    blocks = build_error_message("Video unavailable")
    text = blocks[0]["text"]["text"]
    assert "Video unavailable" in text


def test_duration_formatting():
    meta = _make_metadata()
    blocks = build_quality_buttons(meta)
    section = [b for b in blocks if b["type"] == "section"][0]
    # 212 seconds = 3:32
    assert "3:32" in section["text"]["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_slack_blocks.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'src.slack_blocks'`

- [ ] **Step 3: Write implementation**

```python
# src/slack_blocks.py
from src.downloader import VideoMetadata


def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_filesize(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "? MB"
    mb = size_bytes / (1024 * 1024)
    if mb >= 1024:
        return f"~{mb / 1024:.1f} GB"
    return f"~{mb:.0f} MB"


def build_quality_buttons(meta: VideoMetadata) -> list[dict]:
    """Build Block Kit blocks with video info and quality selection buttons."""
    duration_str = _format_duration(meta.duration)

    buttons = []
    for fmt in meta.formats:
        size_str = _format_filesize(fmt.filesize)
        buttons.append({
            "type": "button",
            "text": {"type": "plain_text", "text": f"{fmt.height}p {size_str}"},
            "action_id": f"download_{fmt.height}",
            "value": f"{meta.video_id}::{fmt.height}",
        })

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{meta.title}* \u00b7 {duration_str}",
            },
        },
        {
            "type": "actions",
            "elements": buttons,
        },
    ]


def build_downloading_message(quality: int) -> list[dict]:
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"\u23f3 Downloading {quality}p..."},
        },
    ]


def build_done_message(filename: str, filesize: int) -> list[dict]:
    size_str = _format_filesize(filesize)
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"\u2705 Done \u00b7 {filename} \u00b7 {size_str}"},
        },
    ]


def build_error_message(error: str) -> list[dict]:
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"\u274c {error}"},
        },
    ]


def build_fallback_link_message(url: str, filename: str, filesize: int) -> list[dict]:
    size_str = _format_filesize(filesize)
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"\u2705 Done \u00b7 {filename} \u00b7 {size_str}\n<{url}|Download link> (expires in 1 hour)",
            },
        },
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_slack_blocks.py -v`

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/slack_blocks.py tests/test_slack_blocks.py
git commit -m "feat: add Slack Block Kit message builders"
```

---

### Task 8: Slack event handlers

**Files:**
- Create: `src/slack_handlers.py`

This module wires everything together: message listener, button action handler, download worker.

- [ ] **Step 1: Write implementation**

```python
# src/slack_handlers.py
import asyncio
import logging
import os
from slack_bolt import App
from src.config import Settings
from src.url_parser import extract_urls
from src.downloader import Downloader
from src.cache import FileCache
from src.queue import DownloadQueue, DownloadJob
from src.slack_blocks import (
    build_quality_buttons,
    build_downloading_message,
    build_done_message,
    build_error_message,
    build_fallback_link_message,
)

logger = logging.getLogger("savetube")

# In-memory store: message_ts -> (url, VideoMetadata)
# Needed to look up the original URL when a button is clicked
_pending_selections: dict[str, tuple[str, object]] = {}


def register_handlers(
    app: App,
    settings: Settings,
    downloader: Downloader,
    cache: FileCache,
    queue: DownloadQueue,
):
    """Register Slack message and action handlers on the Bolt app."""

    @app.message("")
    def handle_message(message, say, client):
        text = message.get("text", "")
        parsed = extract_urls(text)
        if not parsed:
            return

        channel_id = message["channel"]
        message_ts = message["ts"]

        for parsed_url in parsed:
            try:
                meta = downloader.fetch_metadata(parsed_url.url)
            except ValueError as e:
                say(
                    text=str(e),
                    blocks=build_error_message(str(e)),
                    thread_ts=message_ts,
                )
                continue
            except Exception as e:
                logger.exception(f"Metadata fetch failed for {parsed_url.url}")
                say(
                    text="Failed to fetch video info",
                    blocks=build_error_message("Failed to fetch video info. Try again later."),
                    thread_ts=message_ts,
                )
                continue

            result = say(
                text=f"{meta.title}",
                blocks=build_quality_buttons(meta),
                thread_ts=message_ts,
            )
            # Store for button handler lookup
            bot_msg_ts = result["ts"]
            _pending_selections[bot_msg_ts] = (parsed_url.url, meta)

    # Register a handler for each possible quality button
    for quality in [144, 240, 360, 480, 720, 1080, 1440, 2160]:
        _register_download_action(
            app, f"download_{quality}", quality,
            settings, downloader, cache, queue,
        )


def _register_download_action(
    app: App,
    action_id: str,
    quality: int,
    settings: Settings,
    downloader: Downloader,
    cache: FileCache,
    queue: DownloadQueue,
):
    @app.action(action_id)
    def handle_download(ack, body, client):
        ack()

        message_ts = body["message"]["ts"]
        channel_id = body["channel"]["id"]
        action = body["actions"][0]
        value = action["value"]  # "video_id::height"

        # Parse the original URL from pending selections
        pending = _pending_selections.get(message_ts)
        if not pending:
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text="Session expired. Please send the link again.",
                blocks=build_error_message("Session expired. Please send the link again."),
            )
            return

        url, meta = pending
        del _pending_selections[message_ts]

        # Update message to "downloading"
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=f"Downloading {quality}p...",
            blocks=build_downloading_message(quality),
        )

        # Check cache first
        cached_path = cache.get(url, quality)
        if cached_path:
            _upload_file(client, channel_id, message_ts, cached_path, settings)
            return

        # Submit to download queue
        job = DownloadJob(
            url=url,
            quality=quality,
            channel_id=channel_id,
            thread_ts=message_ts,
        )
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(queue.submit(job))
        except asyncio.QueueFull:
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text="Queue full",
                blocks=build_error_message("Download queue is full. Please try again later."),
            )


async def make_download_worker(
    settings: Settings,
    downloader: Downloader,
    cache: FileCache,
    slack_client,
):
    """Return an async worker function for the download queue."""

    async def worker(job: DownloadJob):
        try:
            filepath = await asyncio.to_thread(
                downloader.download, job.url, job.quality
            )
            cache.put(job.url, job.quality, filepath)
            _upload_file(slack_client, job.channel_id, job.thread_ts, filepath, settings)
        except Exception as e:
            logger.exception(f"Download failed for {job.url}")
            slack_client.chat_update(
                channel=job.channel_id,
                ts=job.thread_ts,
                text=str(e),
                blocks=build_error_message(f"Download failed: {e}"),
            )

    return worker


def _upload_file(client, channel_id: str, thread_ts: str, filepath: str, settings: Settings):
    """Upload file to Slack, fall back to HTTP link on failure."""
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)

    try:
        client.files_upload_v2(
            channel=channel_id,
            thread_ts=thread_ts,
            file=filepath,
            filename=filename,
        )
        client.chat_update(
            channel=channel_id,
            ts=thread_ts,
            text=f"Done: {filename}",
            blocks=build_done_message(filename, filesize),
        )
    except Exception as e:
        logger.warning(f"Slack upload failed: {e}, falling back to HTTP link")
        if settings.file_server_base_url:
            file_url = f"{settings.file_server_base_url}/{filename}"
            client.chat_update(
                channel=channel_id,
                ts=thread_ts,
                text=f"Done: {file_url}",
                blocks=build_fallback_link_message(file_url, filename, filesize),
            )
        else:
            client.chat_update(
                channel=channel_id,
                ts=thread_ts,
                text=f"Done: {filename} ({filesize} bytes) — but Slack upload failed",
                blocks=build_error_message(f"File ready ({filename}) but Slack upload failed. Configure FILE_SERVER_BASE_URL for fallback."),
            )
```

- [ ] **Step 2: Verify no import errors**

Run: `python -c "from src.slack_handlers import register_handlers, make_download_worker; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/slack_handlers.py
git commit -m "feat: add Slack event and action handlers"
```

---

### Task 9: File server fallback

**Files:**
- Create: `src/file_server.py`

- [ ] **Step 1: Write implementation**

```python
# src/file_server.py
import asyncio
import logging
from aiohttp import web
from src.config import Settings

logger = logging.getLogger("savetube.fileserver")


async def start_file_server(settings: Settings) -> web.AppRunner:
    """Start a simple static file server for download fallback.

    Serves files from settings.download_dir on settings.file_server_port.
    """
    app = web.Application()
    app.router.add_static("/", settings.download_dir, show_index=False)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.file_server_port)
    await site.start()

    logger.info(f"File server started on port {settings.file_server_port}")
    return runner
```

- [ ] **Step 2: Verify no import errors**

Run: `python -c "from src.file_server import start_file_server; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/file_server.py
git commit -m "feat: add aiohttp fallback file server"
```

---

### Task 10: Main entry point

**Files:**
- Create: `src/main.py`

- [ ] **Step 1: Write implementation**

```python
# src/main.py
import asyncio
import logging
import os
import signal
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from src.config import Settings
from src.downloader import Downloader
from src.cache import FileCache
from src.queue import DownloadQueue
from src.slack_handlers import register_handlers, make_download_worker
from src.file_server import start_file_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("savetube")


def main():
    settings = Settings()
    settings.validate()

    os.makedirs(settings.download_dir, exist_ok=True)

    app = App(token=settings.slack_bot_token)
    downloader = Downloader(settings)
    cache = FileCache(ttl_minutes=settings.file_ttl_minutes, download_dir=settings.download_dir)
    queue = DownloadQueue(
        max_concurrent=settings.max_concurrent_downloads,
        max_queue_size=settings.max_queue_size,
        delay_seconds=settings.download_delay_seconds,
    )

    register_handlers(app, settings, downloader, cache, queue)

    # Run async components in background
    loop = asyncio.new_event_loop()

    async def start_async():
        worker = await make_download_worker(settings, downloader, cache, app.client)
        queue.set_worker(worker)
        await queue.start()

        if settings.file_server_base_url:
            await start_file_server(settings)

        # Periodic cache cleanup every 10 minutes
        async def cleanup_loop():
            while True:
                await asyncio.sleep(600)
                cache.cleanup()
                logger.info("Cache cleanup completed")

        asyncio.create_task(cleanup_loop())

    loop.run_until_complete(start_async())

    import threading
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    logger.info("SaveTube bot starting...")
    handler = SocketModeHandler(app, settings.slack_app_token)
    handler.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify no import errors**

Run: `python -c "from src.main import main; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add main entry point with Socket Mode"
```

---

### Task 11: Docker setup

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

# yt-dlp needs ffmpeg for merging video+audio streams
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

CMD ["python", "-m", "src.main"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
services:
  bgutil-provider:
    image: brainicism/bgutil-ytdlp-pot-provider
    container_name: bgutil-provider
    init: true
    ports:
      - "4416:4416"
    environment:
      - TOKEN_TTL=6
    restart: unless-stopped

  savetube:
    build: .
    container_name: savetube
    depends_on:
      - bgutil-provider
    env_file:
      - .env
    environment:
      - POT_PROVIDER_URL=http://bgutil-provider:4416
    volumes:
      - downloads:/tmp/downloads
    ports:
      - "${FILE_SERVER_PORT:-6060}:${FILE_SERVER_PORT:-6060}"
    restart: unless-stopped

volumes:
  downloads:
```

- [ ] **Step 3: Verify Dockerfile syntax**

Run: `docker build --check .` or `docker build -t savetube:test .`

Expected: Build completes without errors (won't start without Slack tokens, but image should build).

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: add Docker and Docker Compose configuration"
```

---

### Task 12: Integration smoke test

Manual verification that everything works end-to-end.

- [ ] **Step 1: Run all unit tests**

Run: `python -m pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 2: Create a .env file with real tokens**

Copy `.env.example` to `.env` and fill in real `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`.

- [ ] **Step 3: Start the stack**

Run: `docker compose up --build`

Expected: Both containers start. Logs show:
- `bgutil-provider` listening on port 4416
- `SaveTube bot starting...`

- [ ] **Step 4: Test in Slack**

1. Send a YouTube link in the configured channel
2. Bot should reply in thread with title + quality buttons
3. Click a quality button
4. Bot should update message to "Downloading..."
5. Bot should upload the video file to the thread

- [ ] **Step 5: Test TikTok**

1. Send a TikTok link
2. Same flow as above

- [ ] **Step 6: Test error cases**

1. Send a private/deleted YouTube video link — should get error message
2. Fill the queue (send many links quickly) — should get "Queue full" message

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "chore: verify all tests pass, ready for deployment"
```
