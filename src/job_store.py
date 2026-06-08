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
