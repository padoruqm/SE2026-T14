from __future__ import annotations

import asyncio
import tempfile
import unittest
from collections.abc import AsyncIterator
from pathlib import Path

from app.storage.local import LocalDatasetStorage, UploadTooLargeError

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


if __name__ == "__main__":
    unittest.main()
