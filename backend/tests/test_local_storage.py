from __future__ import annotations

import asyncio
import tempfile
import unittest
from collections.abc import AsyncIterator
from pathlib import Path

from app.storage.local import (
    InvalidStorageKeyError,
    LocalDatasetStorage,
    UploadTooLargeError,
)

MAX_UPLOAD_BYTES = 16


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def _failing_after(first: bytes) -> AsyncIterator[bytes]:
    yield first
    raise ConnectionResetError("client went away")


async def _hanging_after(first: bytes) -> AsyncIterator[bytes]:
    yield first
    await asyncio.sleep(60)
    yield b""


class LocalDatasetStorageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.upload_root = self.root / "uploads"
        self.storage = LocalDatasetStorage(self.root, MAX_UPLOAD_BYTES)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _files_under_root(self) -> list[Path]:
        return sorted(path for path in self.root.rglob("*") if path.is_file())

    async def test_saves_chunks_in_order_and_reports_the_size(self) -> None:
        path, size = await self.storage.save("pc_1", ".las", _chunks(b"LA", b"SF", b"!"))

        self.assertEqual(self.upload_root / "pc_1.las", path)
        self.assertEqual(b"LASF!", path.read_bytes())
        self.assertEqual(5, size)

    async def test_accepts_a_file_of_exactly_the_limit(self) -> None:
        _, size = await self.storage.save("pc_1", ".las", _chunks(b"x" * MAX_UPLOAD_BYTES))

        self.assertEqual(MAX_UPLOAD_BYTES, size)

    async def test_rejects_a_file_over_the_limit_and_removes_the_partial_file(self) -> None:
        with self.assertRaises(UploadTooLargeError):
            await self.storage.save(
                "pc_1", ".las", _chunks(b"x" * MAX_UPLOAD_BYTES, b"y")
            )

        self.assertEqual([], self._files_under_root())

    async def test_removes_the_partial_file_when_the_stream_fails(self) -> None:
        with self.assertRaises(ConnectionResetError):
            await self.storage.save("pc_1", ".las", _failing_after(b"LASF"))

        self.assertEqual([], self._files_under_root())

    async def test_removes_the_partial_file_when_the_upload_is_cancelled(self) -> None:
        task = asyncio.create_task(
            self.storage.save("pc_1", ".las", _hanging_after(b"LASF"))
        )
        await asyncio.sleep(0.05)
        self.assertEqual(1, len(self._files_under_root()))

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertEqual([], self._files_under_root())

    async def test_a_failed_upload_keeps_the_previous_file_with_that_id(self) -> None:
        await self.storage.save("pc_1", ".las", _chunks(b"original"))

        with self.assertRaises(UploadTooLargeError):
            await self.storage.save("pc_1", ".las", _chunks(b"x" * 100))

        self.assertEqual(b"original", (self.upload_root / "pc_1.las").read_bytes())
        self.assertEqual([self.upload_root / "pc_1.las"], self._files_under_root())

    async def test_creates_the_upload_directory_on_first_use(self) -> None:
        self.assertFalse(self.upload_root.exists())

        await self.storage.save("pc_1", ".laz", _chunks(b"LASF"))

        self.assertTrue(self.upload_root.is_dir())

    async def test_error_messages_do_not_contain_filesystem_paths(self) -> None:
        with self.assertRaises(UploadTooLargeError) as raised:
            await self.storage.save("pc_1", ".las", _chunks(b"x" * 100))

        self.assertNotIn(str(self.root), str(raised.exception))


    async def test_rejects_dataset_ids_that_could_leave_the_upload_directory(self) -> None:
        for dataset_id in (
            "../escape",
            "..\\escape",
            "/etc/passwd",
            "sub/dir",
            "pc_1/../../escape",
            "..",
            "",
            "pc_1\x00",
        ):
            with self.subTest(dataset_id=dataset_id):
                with self.assertRaises(InvalidStorageKeyError):
                    await self.storage.save(dataset_id, ".las", _chunks(b"LASF"))

        self.assertEqual([], self._files_under_root())

    async def test_rejects_suffixes_that_are_not_a_plain_extension(self) -> None:
        for suffix in ("/../escape", ".las/../..", "las", "", ".las\x00", ".a.b", ".part"):
            with self.subTest(suffix=suffix):
                with self.assertRaises(InvalidStorageKeyError):
                    await self.storage.save("pc_1", suffix, _chunks(b"LASF"))

        self.assertEqual([], self._files_under_root())

    async def test_never_writes_outside_the_upload_directory(self) -> None:
        sibling = self.root / "escape.las"

        with self.assertRaises(InvalidStorageKeyError):
            await self.storage.save("../escape", ".las", _chunks(b"LASF"))

        self.assertFalse(sibling.exists())

    async def test_rejects_a_symlinked_destination(self) -> None:
        target = self.root / "victim.las"
        target.write_bytes(b"keep me")
        self.upload_root.mkdir()
        (self.upload_root / "pc_1.las").symlink_to(target)

        with self.assertRaises(InvalidStorageKeyError):
            await self.storage.save("pc_1", ".las", _chunks(b"overwritten"))

        self.assertEqual(b"keep me", target.read_bytes())

    async def test_does_not_write_through_a_symlinked_partial_file(self) -> None:
        target = self.root / "victim.txt"
        target.write_bytes(b"keep me")
        self.upload_root.mkdir()
        (self.upload_root / "pc_1.las.part").symlink_to(target)

        with self.assertRaises(InvalidStorageKeyError):
            await self.storage.save("pc_1", ".las", _chunks(b"overwritten"))

        self.assertEqual(b"keep me", target.read_bytes())


class DatasetRecordTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.storage = LocalDatasetStorage(self.root, MAX_UPLOAD_BYTES)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_reads_back_what_was_written(self) -> None:
        record = {"filename": "survey.laz", "point_count": 12, "crs": None}

        self.storage.write_record("pc_1", record)

        self.assertEqual(record, self.storage.read_record("pc_1"))

    def test_unknown_record_is_none(self) -> None:
        self.assertIsNone(self.storage.read_record("pc_missing"))

    def test_writing_again_replaces_the_record(self) -> None:
        self.storage.write_record("pc_1", {"filename": "a.las"})
        self.storage.write_record("pc_1", {"filename": "b.las"})

        self.assertEqual({"filename": "b.las"}, self.storage.read_record("pc_1"))

    def test_leaves_no_temporary_file_behind(self) -> None:
        self.storage.write_record("pc_1", {"filename": "a.las"})

        names = [path.name for path in (self.root / "metadata").iterdir()]
        self.assertEqual(["pc_1.json"], names)

    def test_records_do_not_appear_next_to_uploads(self) -> None:
        self.storage.write_record("pc_1", {"filename": "a.las"})

        self.assertFalse((self.root / "uploads").exists())

    def test_a_lookup_with_an_unsafe_id_finds_nothing(self) -> None:
        (self.root / "secret.json").write_text('{"filename": "x"}', encoding="utf-8")

        for dataset_id in ("../secret", "..", "", "a/b", "pc_1\x00", "bad.id"):
            with self.subTest(dataset_id=dataset_id):
                self.assertIsNone(self.storage.read_record(dataset_id))

    def test_writing_a_record_with_an_unsafe_id_is_refused(self) -> None:
        for dataset_id in ("../escape", "..", "", "a/b", "bad.id"):
            with self.subTest(dataset_id=dataset_id):
                with self.assertRaises(InvalidStorageKeyError):
                    self.storage.write_record(dataset_id, {"filename": "a.las"})

        self.assertEqual([], sorted(self.root.rglob("*.json")))

    def test_a_symlinked_record_is_not_followed(self) -> None:
        target = self.root / "outside.json"
        target.write_text('{"filename": "outside"}', encoding="utf-8")
        (self.root / "metadata").mkdir()
        (self.root / "metadata" / "pc_1.json").symlink_to(target)

        self.assertIsNone(self.storage.read_record("pc_1"))

    def test_a_corrupt_record_is_an_error_not_a_missing_dataset(self) -> None:
        (self.root / "metadata").mkdir()
        (self.root / "metadata" / "pc_1.json").write_text("{not json", encoding="utf-8")

        with self.assertRaises(ValueError):
            self.storage.read_record("pc_1")

    async def test_discard_upload_removes_the_stored_file_only(self) -> None:
        await self.storage.save("pc_1", ".las", _chunks(b"LASF"))
        await self.storage.save("pc_2", ".las", _chunks(b"LASF"))

        self.storage.discard_upload("pc_1")

        self.assertIsNone(self.storage.find("pc_1"))
        self.assertIsNotNone(self.storage.find("pc_2"))

    def test_discard_upload_of_an_unknown_dataset_is_a_no_op(self) -> None:
        self.storage.discard_upload("pc_missing")
        self.storage.discard_upload("../etc")


if __name__ == "__main__":
    unittest.main()
