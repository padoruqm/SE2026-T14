from __future__ import annotations

import asyncio
import logging

from app.core.errors import ConflictError, NotFoundError
from app.jobs.store import Job, JobError, JobStore
from app.processing.converter import ConversionError, Converter
from app.storage.local import LocalDatasetStorage

logger = logging.getLogger(__name__)


class ConvertJobRunner:
    """Create convert jobs and run them in the background, a few at a time."""

    def __init__(
        self,
        storage: LocalDatasetStorage,
        converter: Converter,
        store: JobStore,
        workers: int = 1,
    ) -> None:
        self._storage = storage
        self._converter = converter
        self._store = store
        self._slots = asyncio.Semaphore(workers)
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self, point_cloud_id: str, force: bool) -> Job:
        source = self._storage.find(point_cloud_id)
        if source is None:
            raise NotFoundError("Point cloud not found")
        if self._store.has_active("convert", point_cloud_id):
            raise ConflictError("A conversion is already in progress")
        if not force and self._storage.has_converted(point_cloud_id):
            raise ConflictError("The point cloud has already been converted")

        job = self._store.create("convert", point_cloud_id)
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run(self, job: Job) -> None:
        async with self._slots:
            job.state = "running"
            staging = self._storage.new_staging_dir(job.point_cloud_id)
            try:
                source = self._storage.find(job.point_cloud_id)
                if source is None:
                    raise ConversionError("NOT_FOUND", "Point cloud not found")
                await self._converter.convert(source, staging)
                self._storage.publish_converted(job.point_cloud_id, staging)
            except ConversionError as exc:
                self._fail(job, exc.code, exc.message)
            except Exception:
                logger.exception("Conversion of %s failed", job.point_cloud_id)
                self._fail(job, "INTERNAL_ERROR", "The conversion failed unexpectedly")
            else:
                job.state = "succeeded"
                job.progress = 100
                job.result_id = job.point_cloud_id
            finally:
                self._storage.discard_staging_dir(staging)

    @staticmethod
    def _fail(job: Job, code: str, message: str) -> None:
        job.state = "failed"
        job.error = JobError(code=code, message=message)
