from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from uuid import uuid4

from app.core.errors import (
    FileTooLargeError,
    InvalidPointCloudError,
    UnsupportedFileTypeError,
)
from app.storage.local import LocalDatasetStorage, UploadTooLargeError

ALLOWED_SUFFIXES = frozenset({".las", ".laz"})
LAS_SIGNATURE = b"LASF"


@dataclass(frozen=True, slots=True)
class StoredDataset:
    id: str
    filename: str
    status: str


def sanitize_filename(filename: str) -> str:
    return PurePosixPath(PureWindowsPath(filename).name).name


async def _validated_chunks(chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    head = b""
    validated = False
    async for chunk in chunks:
        if not validated:
            head += chunk
            if len(head) < len(LAS_SIGNATURE):
                continue
            if not head.startswith(LAS_SIGNATURE):
                raise InvalidPointCloudError()
            validated = True
            chunk = head
        yield chunk
    if not validated:
        raise InvalidPointCloudError()


class DatasetService:
    def __init__(self, storage: LocalDatasetStorage) -> None:
        self._storage = storage

    async def store_upload(
        self, filename: str, chunks: AsyncIterator[bytes]
    ) -> StoredDataset:
        safe_filename = sanitize_filename(filename)
        suffix = PurePosixPath(safe_filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise UnsupportedFileTypeError()

        dataset_id = f"pc_{uuid4().hex}"
        try:
            await self._storage.save(dataset_id, suffix, _validated_chunks(chunks))
        except UploadTooLargeError as exc:
            raise FileTooLargeError() from exc

        return StoredDataset(id=dataset_id, filename=safe_filename, status="uploaded")
