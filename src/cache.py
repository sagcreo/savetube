import os
import threading
import time
from dataclasses import dataclass


@dataclass
class _CacheEntry:
    filepath: str
    created_at: float


class FileCache:
    def __init__(self, ttl_minutes: int, download_dir: str):
        self._ttl_seconds = ttl_minutes * 60
        self._download_dir = download_dir
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(url: str, quality: int) -> str:
        return f"{url}::{quality}"

    def get(self, url: str, quality: int) -> str | None:
        key = self._key(url, quality)
        with self._lock:
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
        key = self._key(url, quality)
        with self._lock:
            self._entries[key] = _CacheEntry(filepath=filepath, created_at=time.time())

    def cleanup(self) -> None:
        now = time.time()
        to_delete: list[_CacheEntry] = []
        with self._lock:
            expired_keys = [
                key for key, entry in self._entries.items()
                if now - entry.created_at > self._ttl_seconds
            ]
            for key in expired_keys:
                to_delete.append(self._entries.pop(key))
        for entry in to_delete:
            if os.path.exists(entry.filepath):
                os.remove(entry.filepath)
