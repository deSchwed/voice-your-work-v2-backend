import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    GENERATE = "generate"
    PREVIEW = "preview"


JOB_TYPE_GENERATE = "generate"
JOB_TYPE_PREVIEW = "preview"


@dataclass
class GenerateJob:
    queue_job_id: int
    generation_id: int
    text: str
    language: str
    ref_audio: str
    ref_text: str
    status: JobStatus = JobStatus.PENDING
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PreviewJob:
    queue_job_id: int
    voice_id: int
    ref_text: str
    ref_audio: str
    name: str
    status: JobStatus = JobStatus.PENDING
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class VoiceQueue:
    def __init__(self, max_workers: int = 1) -> None:
        self._queue: asyncio.Queue[GenerateJob | PreviewJob] = asyncio.Queue()
        self._generate_jobs: dict[int, GenerateJob] = {}  # keyed by generation_id
        self._preview_jobs: dict[int, PreviewJob] = {}  # keyed by voice_id
        self._max_workers = max_workers
        self._workers: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Public enqueue methods — create a QueueJob DB row then add to queue
    # ------------------------------------------------------------------

    async def enqueue_generate(
        self,
        generation_id: int,
        text: str,
        language: str,
        ref_audio: str,
        ref_text: str,
    ) -> GenerateJob:
        queue_job_id = await self._create_db_job(
            JobType.GENERATE, voice_generation_id=generation_id
        )
        return await self._add_generate_to_queue(
            queue_job_id, generation_id, text, language, ref_audio, ref_text
        )

    async def enqueue_preview(
        self,
        voice_id: int,
        ref_text: str,
        ref_audio: str,
        name: str,
    ) -> PreviewJob:
        queue_job_id = await self._create_db_job(
            JobType.PREVIEW, voice_clone_id=voice_id
        )
        return await self._add_preview_to_queue(
            queue_job_id, voice_id, ref_text, ref_audio, name
        )

    def get_generate_job(self, generation_id: int) -> GenerateJob | None:
        return self._generate_jobs.get(generation_id)

    def get_preview_job(self, voice_id: int) -> PreviewJob | None:
        return self._preview_jobs.get(voice_id)

    # ------------------------------------------------------------------
    # Startup restore — re-enqueue from existing QueueJob rows
    # ------------------------------------------------------------------

    async def restore_from_db(self) -> None:
        """Re-enqueue pending or interrupted jobs from the previous run.

        Resets any 'processing' rows to 'pending' (backend crashed mid-job),
        then re-enqueues all pending rows in original submission order.
        """
        from sqlalchemy import select, update
        from sqlalchemy.orm import selectinload

        import models
        from database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(models.QueueJob)
                .where(models.QueueJob.status == JobStatus.PROCESSING)
                .values(status=JobStatus.PENDING)
            )
            await session.commit()

            result = await session.execute(
                select(models.QueueJob)
                .where(models.QueueJob.status == JobStatus.PENDING)
                .options(
                    selectinload(models.QueueJob.voice_generation).selectinload(
                        models.VoiceGenerate.voice
                    ),
                    selectinload(models.QueueJob.voice_clone),
                )
                .order_by(models.QueueJob.created_at)
            )

            for queue_job in result.scalars().all():
                if queue_job.job_type == JobType.GENERATE:
                    gen = queue_job.voice_generation
                    if gen and gen.voice:
                        await self._add_generate_to_queue(
                            queue_job_id=queue_job.id,
                            generation_id=gen.id,
                            text=gen.prompt_text,
                            language=gen.language,
                            ref_audio=gen.voice.ref_audio_path,
                            ref_text=gen.voice.ref_text,
                        )
                elif queue_job.job_type == JobType.PREVIEW:
                    voice = queue_job.voice_clone
                    if voice:
                        await self._add_preview_to_queue(
                            queue_job_id=queue_job.id,
                            voice_id=voice.id,
                            ref_text=voice.ref_text,
                            ref_audio=voice.ref_audio_path,
                            name=voice.name,
                        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _create_db_job(
        self,
        job_type: str,
        voice_generation_id: int | None = None,
        voice_clone_id: int | None = None,
    ) -> int:
        import models
        from database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            queue_job = models.QueueJob(
                job_type=job_type,
                voice_generation_id=voice_generation_id,
                voice_clone_id=voice_clone_id,
            )
            session.add(queue_job)
            await session.commit()
            await session.refresh(queue_job)
            return queue_job.id

    async def _add_generate_to_queue(
        self,
        queue_job_id: int,
        generation_id: int,
        text: str,
        language: str,
        ref_audio: str,
        ref_text: str,
    ) -> GenerateJob:
        job = GenerateJob(
            queue_job_id=queue_job_id,
            generation_id=generation_id,
            text=text,
            language=language,
            ref_audio=ref_audio,
            ref_text=ref_text,
        )
        self._generate_jobs[generation_id] = job
        await self._queue.put(job)
        return job

    async def _add_preview_to_queue(
        self,
        queue_job_id: int,
        voice_id: int,
        ref_text: str,
        ref_audio: str,
        name: str,
    ) -> PreviewJob:
        job = PreviewJob(
            queue_job_id=queue_job_id,
            voice_id=voice_id,
            ref_text=ref_text,
            ref_audio=ref_audio,
            name=name,
        )
        self._preview_jobs[voice_id] = job
        await self._queue.put(job)
        return job

    async def _update_generate_status(
        self,
        queue_job_id: int,
        generation_id: int,
        status: JobStatus,
        audio_file: str | None = None,
        error_message: str | None = None,
    ) -> None:
        from sqlalchemy import select

        import models
        from database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            queue_job_result = await session.execute(
                select(models.QueueJob).where(models.QueueJob.id == queue_job_id)
            )
            queue_job = queue_job_result.scalars().first()
            if queue_job:
                queue_job.status = status
                if error_message is not None:
                    queue_job.error_message = error_message

            if audio_file is not None:
                gen_result = await session.execute(
                    select(models.VoiceGenerate).where(
                        models.VoiceGenerate.id == generation_id
                    )
                )
                generation = gen_result.scalars().first()
                if generation:
                    generation.audio_file = audio_file
                    generation.is_generated = True
                    # Increment times used
                    voice_result = await session.execute(
                        select(models.VoiceClone).where(
                            models.VoiceClone.id == generation.voice_id
                        )
                    )
                    voice = voice_result.scalars().first()
                    if voice:
                        voice.times_used += 1

            await session.commit()

    async def _update_preview_status(
        self,
        queue_job_id: int,
        voice_id: int,
        status: JobStatus,
        preview_file: str | None = None,
        error_message: str | None = None,
    ) -> None:
        from sqlalchemy import select

        import models
        from database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            queue_job_result = await session.execute(
                select(models.QueueJob).where(models.QueueJob.id == queue_job_id)
            )
            queue_job = queue_job_result.scalars().first()
            if queue_job:
                queue_job.status = status
                if error_message is not None:
                    queue_job.error_message = error_message

            if preview_file is not None:
                voice_result = await session.execute(
                    select(models.VoiceClone).where(models.VoiceClone.id == voice_id)
                )
                voice = voice_result.scalars().first()
                if voice:
                    voice.preview_audio_file = preview_file
                    voice.is_ready = True

            await session.commit()

    # ------------------------------------------------------------------
    # Job processors
    # ------------------------------------------------------------------

    async def _process_generate(self, job: GenerateJob) -> None:
        from voice_engine.engine import tts_engine

        job.status = JobStatus.PROCESSING
        await self._update_generate_status(
            job.queue_job_id, job.generation_id, JobStatus.PROCESSING
        )

        try:
            filename = await asyncio.to_thread(
                tts_engine.generate,
                text=job.text,
                language=job.language,
                ref_audio=job.ref_audio,
                ref_text=job.ref_text,
            )
            job.status = JobStatus.COMPLETED
            await self._update_generate_status(
                job.queue_job_id,
                job.generation_id,
                JobStatus.COMPLETED,
                audio_file=filename,
            )
        except Exception as err:
            job.status = JobStatus.FAILED
            job.error = str(err)
            await self._update_generate_status(
                job.queue_job_id,
                job.generation_id,
                JobStatus.FAILED,
                error_message=str(err),
            )

    async def _process_preview(self, job: PreviewJob) -> None:
        from voice_engine.engine import tts_engine

        job.status = JobStatus.PROCESSING
        await self._update_preview_status(
            job.queue_job_id, job.voice_id, JobStatus.PROCESSING
        )

        try:
            filename = await asyncio.to_thread(
                tts_engine.generate_preview, job.ref_text, job.ref_audio, job.name
            )
            job.status = JobStatus.COMPLETED
            await self._update_preview_status(
                job.queue_job_id,
                job.voice_id,
                JobStatus.COMPLETED,
                preview_file=filename,
            )
        except Exception as err:
            job.status = JobStatus.FAILED
            job.error = str(err)
            await self._update_preview_status(
                job.queue_job_id,
                job.voice_id,
                JobStatus.FAILED,
                error_message=str(err),
            )

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if isinstance(job, PreviewJob):
                    await self._process_preview(job)
                else:
                    await self._process_generate(job)
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
