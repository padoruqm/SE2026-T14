from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from app.core.errors import ConflictError, InvalidRequestError
from app.jobs.store import Job, JobError, JobState, JobStore
from app.processing import ProcessingContext, Processor
from app.processing.errors import (
    ProcessingInputError,
    ProcessorExecutionError,
    ProcessorTimeoutError,
    ProcessorUnavailableError,
)
from app.services.crop_bounds import CropBoundsError, validate_crop_bounds
from app.services.datasets import DatasetService
from app.services.las_metadata import LasBounds, LasMetadata
from app.storage.local import LocalDatasetStorage

logger = logging.getLogger(__name__)

_PROCESSOR_FAILURES = (
    ProcessorExecutionError,
    ProcessorTimeoutError,
    ProcessorUnavailableError,
)
# Share of the job's progress spent on the crop itself; the rest is the conversion
# for the viewer. 100 is only reported once the result is registered.
_CROP_SHARE = 40


class _JobFailed(Exception):
    def __init__(
        self, code: str, message: str, *, log_level: int = logging.ERROR
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.log_level = log_level


class CropJobRunner:
    """Crop a point cloud to a box in the background and register the result.

    A job runs PDAL to crop the stored file, rejects an empty result, converts the
    cropped file for the viewer and registers it as a new point cloud whose
    `sourceId` is the original. The original is never changed, and a failed job
    leaves nothing behind.
    """

    def __init__(
        self,
        storage: LocalDatasetStorage,
        crop_processor: Processor,
        convert_processor: Processor,
        store: JobStore,
        workers: int = 1,
    ) -> None:
        if workers < 1:
            raise ValueError("workers must be at least one")
        self._storage = storage
        self._crop = crop_processor
        self._convert = convert_processor
        self._store = store
        self._datasets = DatasetService(storage, store)
        self._slots = asyncio.Semaphore(workers)
        self._tasks: set[asyncio.Task[None]] = set()

    def start(
        self, point_cloud_id: str, bounds: Mapping[str, float], output_format: str
    ) -> Job:
        dataset = self._datasets.get(point_cloud_id)
        if self._storage.find(point_cloud_id) is None:
            raise ConflictError("This point cloud has no file to crop")
        try:
            validate_crop_bounds(bounds, dataset.metadata.bounds)
        except CropBoundsError as exc:
            raise InvalidRequestError(["body", "bounds"], str(exc)) from exc

        job = self._store.create("crop", point_cloud_id)
        logger.info("Crop job queued", extra=self._log_context(job))
        stem = PurePosixPath(dataset.filename).stem or "point-cloud"
        task = asyncio.create_task(
            self._run(job, dict(bounds), output_format, f"{stem}-crop.{output_format}")
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run(
        self, job: Job, bounds: dict[str, float], output_format: str, filename: str
    ) -> None:
        async with self._slots:
            staging: Path | None = None
            try:
                job.transition_to(JobState.RUNNING)
                staging = self._storage.new_staging_dir(job.point_cloud_id)
                result_id = await self._crop_and_register(
                    job, staging, bounds, output_format, filename
                )
            except _JobFailed as failure:
                self._fail(job, failure.code, failure.message, failure.log_level)
            except Exception:
                logger.exception(
                    "Crop job failed unexpectedly", extra=self._log_context(job)
                )
                self._fail(job, "INTERNAL_ERROR", "The crop failed unexpectedly")
            else:
                job.transition_to(JobState.SUCCEEDED, progress=100, result_id=result_id)
                logger.info("Crop job succeeded", extra=self._log_context(job))
            finally:
                if staging is not None:
                    self._storage.discard_staging_dir(staging)

    async def _crop_and_register(
        self,
        job: Job,
        staging: Path,
        bounds: dict[str, float],
        output_format: str,
        filename: str,
    ) -> str:
        source = self._storage.find(job.point_cloud_id)
        if source is None:
            raise _JobFailed(
                "NOT_FOUND", "Point cloud not found", log_level=logging.WARNING
            )
        loop = asyncio.get_running_loop()

        cropped = await self._execute(
            job,
            self._crop,
            ProcessingContext(input_path=source, output_directory=staging / "crop"),
            {"bounds": bounds, "output_format": output_format},
            "crop",
        )
        metadata = _read_crop_summary(cropped.metadata_path)
        if metadata.point_count == 0:
            raise _JobFailed(
                "EMPTY_RESULT",
                "The selected region contains no points",
                log_level=logging.INFO,
            )
        cropped_file = _point_cloud_file(cropped.output_directory, output_format)
        self._report_progress(job, _CROP_SHARE)

        def report_conversion(progress: int) -> None:
            share = _CROP_SHARE + progress * (99 - _CROP_SHARE) // 100
            loop.call_soon_threadsafe(self._report_progress, job, share)

        viewer = await self._execute(
            job,
            self._convert,
            ProcessingContext(
                input_path=cropped_file,
                output_directory=staging / "viewer",
                progress_callback=report_conversion,
            ),
            {},
            "conversion",
        )
        result = self._datasets.create_result(
            job.point_cloud_id,
            filename,
            metadata,
            viewer.output_directory,
            source_file=cropped_file,
        )
        return result.id

    async def _execute(self, job, processor, context, parameters, step: str):
        try:
            return await asyncio.get_running_loop().run_in_executor(
                None, processor.execute, context, parameters
            )
        except ProcessingInputError as exc:
            logger.warning(
                "Crop %s rejected its input: %s",
                step,
                exc,
                extra=self._log_context(job),
            )
            raise _JobFailed(
                "INVALID_POINT_CLOUD", "The point cloud could not be cropped"
            ) from exc
        except _PROCESSOR_FAILURES as exc:
            logger.error(
                "Crop %s failed: %s (exit code %s)\n%s",
                step,
                exc,
                getattr(exc, "return_code", None),
                getattr(exc, "stderr", None) or "",
                extra=self._log_context(job),
            )
            raise _JobFailed("INTERNAL_ERROR", "The crop failed") from exc

    def _fail(
        self, job: Job, code: str, message: str, log_level: int = logging.ERROR
    ) -> None:
        job.transition_to(JobState.FAILED, error=JobError(code=code, message=message))
        logger.log(
            log_level,
            "Crop job failed with code %s",
            code,
            extra=self._log_context(job),
        )

    @staticmethod
    def _report_progress(job: Job, progress: int) -> None:
        if job.state is JobState.RUNNING:
            job.report_progress(progress)

    @staticmethod
    def _log_context(job: Job) -> dict[str, str]:
        return {
            "component": "jobs",
            "job_id": job.id,
            "point_cloud_id": job.point_cloud_id,
        }


def _read_crop_summary(path: Path) -> LasMetadata:
    """The header summary the crop processor writes next to its output."""
    summary = json.loads(path.read_text(encoding="utf-8"))
    return LasMetadata(
        point_count=int(summary["point_count"]),
        bounds=LasBounds(**summary["bounds"]),
        crs=summary["crs"],
    )


def _point_cloud_file(directory: Path, output_format: str) -> Path:
    files = [
        p
        for p in directory.glob(f"*.{output_format}")
        if p.is_file() and not p.is_symlink()
    ]
    if len(files) != 1:
        raise _JobFailed("INTERNAL_ERROR", "The crop failed")
    return files[0]
