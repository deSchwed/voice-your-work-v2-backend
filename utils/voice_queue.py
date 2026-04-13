import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    VOICE_CLONE = "voice_clone"
    VOICE_DESIGN = "voice_design"


@dataclass
class VoiceJob:
    user_id: int
    job_type: JobType
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    result: Any = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


Handler = Callable[[dict[str, Any]], Coroutine[Any, Any, Any]]


class VoiceQueue:
    def __init__(self, max_workers: int = 1) -> None:
        self._queue: asyncio.Queue[VoiceJob] = asyncio.Queue()
        self._jobs: dict[str, VoiceJob] = {}
        self._handlers: dict[JobType, Handler] = {}
        self._max_workers = max_workers
        self._workers: list[asyncio.Task] = []

    def register_handler(self, job_type: JobType, handler: Handler) -> None:
        self._handlers[job_type] = handler

    def get_user_jobs(self, user_id: int) -> list[VoiceJob]:
        return [job for job in self._jobs.values() if job.user_id == user_id]

    async def _process(self, job: VoiceJob) -> None:
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)

        handler = self._handlers.get(job.job_type)
        if handler is None:
            job.status = JobStatus.FAILED
            job.error = f"No handler registered for job type: {job.job_type}"
            job.completed_at = datetime.now(timezone.utc)
            return

        try:
            job.result = await handler(job.payload)
            job.status = JobStatus.COMPLETED
        except Exception as err:
            job.status = JobStatus.FAILED
            job.error = str(err)
        finally:
            job.completed_at = datetime.now(timezone.utc)

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._process(job)
            finally:
                self._queue.task_done()

    async def start(self) -> None:
        for _ in range(self._max_workers):
            self._workers.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()


voice_queue = VoiceQueue()
