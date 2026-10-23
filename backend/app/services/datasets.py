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
from app.services.las_metadata import (
    HEADER_PROBE_BYTES,
    LAS_SIGNATURE,
    LasMetadata,
    parse_las_metadata,
    required_head_length,
)
from app.storage.local import LocalDatasetStorage, UploadTooLargeError

ALLOWED_SUFFIXES = frozenset({".las", ".laz"})


@dataclass(frozen=True, slots=True)
class StoredDataset:
    id: str
    filename: str
    status: str
    metadata: LasMetadata


def sanitize_filename(filename: str) -> str:
    return PurePosixPath(PureWindowsPath(filename).name).name


class _HeaderInspector:
    """Pass chunks through while validating the LAS header and reading its metadata."""

    def __init__(self) -> None:
        self.metadata: LasMetadata | None = None

    async def stream(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        head = bytearray()
        needed: int | None = None
        async for chunk in chunks:
            if self.metadata is not None:
                yield chunk
                continue

            head += chunk
            if len(head) >= len(LAS_SIGNATURE) and not head.startswith(LAS_SIGNATURE):
                raise InvalidPointCloudError()
            if needed is None and len(head) >= HEADER_PROBE_BYTES:
                needed = required_head_length(bytes(head))
            if needed is not None and len(head) >= needed:
                self.metadata = parse_las_metadata(bytes(head[:needed]))
                yield bytes(head)

        if self.metadata is None:
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
        inspector = _HeaderInspector()
        try:
            await self._storage.save(dataset_id, suffix, inspector.stream(chunks))
        except UploadTooLargeError as exc:
            raise FileTooLargeError() from exc

        if inspector.metadata is None:
            raise InvalidPointCloudError()
        return StoredDataset(
            id=dataset_id,
            filename=safe_filename,
            status="uploaded",
            metadata=inspector.metadata,
        )
