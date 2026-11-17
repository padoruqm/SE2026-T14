from __future__ import annotations

import tempfile
import unittest
from collections.abc import AsyncIterator
from pathlib import Path

from unittest.mock import patch

from app.core.errors import InvalidPointCloudError, NotFoundError
from app.jobs.store import JobError, JobState, JobStore
from app.services.datasets import DatasetService
from app.storage.local import LocalDatasetStorage
from las_fixtures import Vlr, build_las, geotiff_key_directory


async def _chunked(data: bytes, size: int) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


class DatasetServiceStreamingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.upload_root = root / "uploads"
        self.service = DatasetService(LocalDatasetStorage(root, max_upload_bytes=1 << 20))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_reads_metadata_when_the_header_arrives_in_tiny_chunks(self) -> None:
        keys = geotiff_key_directory((3072, 32648))
        las = build_las(
            point_count=7,
            vlrs=(Vlr("LASF_Projection", 34735, keys),),
            payload=b"p" * 300,
        )

        stored = await self.service.store_upload("tiny.las", _chunked(las, 5))

        self.assertEqual(7, stored.metadata.point_count)
        self.assertEqual("EPSG:32648", stored.metadata.crs)
        saved = next(self.upload_root.glob("*.las"))
        self.assertEqual(las, saved.read_bytes())

    async def test_header_split_across_the_signature_is_still_validated(self) -> None:
        with self.assertRaises(InvalidPointCloudError):
            await self.service.store_upload("fake.las", _chunked(b"NOTLAS" * 100, 2))

        self.assertEqual([], list(self.upload_root.iterdir()))

    async def test_stream_ending_inside_the_header_is_rejected(self) -> None:
        las = build_las()

        with self.assertRaises(InvalidPointCloudError):
            await self.service.store_upload("cut.las", _chunked(las[:120], 16))

        self.assertEqual([], list(self.upload_root.iterdir()))


class DatasetServiceLookupTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.storage = LocalDatasetStorage(self.root, max_upload_bytes=1 << 20)
        self.jobs = JobStore()
        self.service = DatasetService(self.storage, self.jobs)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def _store(self, filename: str = "survey.laz", **las: object):
        return await self.service.store_upload(filename, _chunked(build_las(**las), 64))

    async def test_get_returns_what_was_stored_at_upload(self) -> None:
        keys = geotiff_key_directory((3072, 32648))
        stored = await self._store(
            point_count=9,
            min_xyz=(1.0, 2.0, 3.0),
            max_xyz=(4.0, 5.0, 6.0),
            vlrs=(Vlr("LASF_Projection", 34735, keys),),
        )

        found = self.service.get(stored.id)

        self.assertEqual(stored.id, found.id)
        self.assertEqual("survey.laz", found.filename)
        self.assertEqual(9, found.metadata.point_count)
        self.assertEqual((1.0, 2.0, 3.0), (
            found.metadata.bounds.minX,
            found.metadata.bounds.minY,
            found.metadata.bounds.minZ,
        ))
        self.assertEqual((4.0, 5.0, 6.0), (
            found.metadata.bounds.maxX,
            found.metadata.bounds.maxY,
            found.metadata.bounds.maxZ,
        ))
        self.assertEqual("EPSG:32648", found.metadata.crs)

    async def test_get_survives_a_new_service_instance(self) -> None:
        stored = await self._store()

        fresh = DatasetService(LocalDatasetStorage(self.root, 1 << 20), JobStore())

        self.assertEqual("survey.laz", fresh.get(stored.id).filename)

    async def test_get_of_an_unknown_id_is_not_found(self) -> None:
        for dataset_id in ("pc_missing", "../x", ""):
            with self.subTest(dataset_id=dataset_id):
                with self.assertRaises(NotFoundError):
                    self.service.get(dataset_id)

    async def test_an_upload_without_a_record_is_not_found(self) -> None:
        stored = await self._store()
        (self.root / "metadata" / f"{stored.id}.json").unlink()

        with self.assertRaises(NotFoundError):
            self.service.get(stored.id)

    async def test_a_failed_record_write_removes_the_upload(self) -> None:
        with patch.object(self.storage, "write_record", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await self._store()

        self.assertEqual([], list((self.root / "uploads").iterdir()))

    async def test_a_new_upload_is_uploaded(self) -> None:
        stored = await self._store()

        self.assertEqual("uploaded", self.service.get(stored.id).status)

    async def test_status_is_converting_while_a_job_is_active(self) -> None:
        stored = await self._store()
        job = self.jobs.create("convert", stored.id)
        self.assertEqual("converting", self.service.get(stored.id).status)

        job.transition_to(JobState.RUNNING)
        self.assertEqual("converting", self.service.get(stored.id).status)

    async def test_status_is_ready_once_a_result_is_published(self) -> None:
        stored = await self._store()
        staging = self.storage.new_staging_dir(stored.id)
        (staging / "result").mkdir()
        self.storage.publish_converted(stored.id, staging / "result")

        self.assertEqual("ready", self.service.get(stored.id).status)

    async def test_status_is_failed_after_a_failed_job_without_a_result(self) -> None:
        stored = await self._store()
        job = self.jobs.create("convert", stored.id)
        job.transition_to(JobState.RUNNING)
        job.transition_to(JobState.FAILED, error=JobError("INTERNAL_ERROR", "boom"))

        self.assertEqual("failed", self.service.get(stored.id).status)

    async def test_a_failed_reconversion_keeps_the_old_result_ready(self) -> None:
        stored = await self._store()
        staging = self.storage.new_staging_dir(stored.id)
        (staging / "result").mkdir()
        self.storage.publish_converted(stored.id, staging / "result")
        job = self.jobs.create("convert", stored.id)
        job.transition_to(JobState.RUNNING)
        job.transition_to(JobState.FAILED, error=JobError("INTERNAL_ERROR", "boom"))

        self.assertEqual("ready", self.service.get(stored.id).status)

    async def test_a_later_job_replaces_an_earlier_failure(self) -> None:
        stored = await self._store()
        first = self.jobs.create("convert", stored.id)
        first.transition_to(JobState.RUNNING)
        first.transition_to(JobState.FAILED, error=JobError("INTERNAL_ERROR", "boom"))
        self.jobs.create("convert", stored.id)

        self.assertEqual("converting", self.service.get(stored.id).status)

    async def test_other_datasets_jobs_do_not_change_the_status(self) -> None:
        stored = await self._store()
        other = await self._store("other.las")
        self.jobs.create("convert", other.id)

        self.assertEqual("uploaded", self.service.get(stored.id).status)

    async def test_without_a_job_store_status_comes_from_the_files_alone(self) -> None:
        stored = await self._store()
        service = DatasetService(self.storage)

        self.assertEqual("uploaded", service.get(stored.id).status)


if __name__ == "__main__":
    unittest.main()
