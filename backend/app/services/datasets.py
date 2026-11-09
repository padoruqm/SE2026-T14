from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from uuid import uuid4

from app.core.errors import (
    FileTooLargeError,
    InvalidPointCloudError,
    NotFoundError,
    UnsupportedFileTypeError,
)
from app.jobs.store import JobState, JobStore
from app.services.las_metadata import (
    HEADER_PROBE_BYTES,
    LAS_SIGNATURE,
    LasBounds,
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


def _to_record(filename: str, metadata: LasMetadata) -> dict[str, object]:
    return {
        "filename": filename,
        "point_count": metadata.point_count,
        "bounds": asdict(metadata.bounds),
        "crs": metadata.crs,
    }


def _from_record(record: Mapping[str, Any]) -> tuple[str, LasMetadata]:
    return str(record["filename"]), LasMetadata(
        point_count=int(record["point_count"]),
        bounds=LasBounds(**record["bounds"]),
        crs=record["crs"],
    )


class DatasetService:
    def __init__(
        self, storage: LocalDatasetStorage, job_store: JobStore | None = None
    ) -> None:
        self._storage = storage
        self._job_store = job_store

    def get(self, dataset_id: str) -> StoredDataset:
        record = self._storage.read_record(dataset_id)
        if record is None:
            raise NotFoundError("Point cloud not found")
        filename, metadata = _from_record(record)
        return StoredDataset(
            id=dataset_id,
            filename=filename,
            status=self._status(dataset_id),
            metadata=metadata,
        )

    def _status(self, dataset_id: str) -> str:
        jobs = self._job_store
        if jobs is not None and jobs.has_active("convert", dataset_id):
            return "converting"
        if self._storage.has_converted(dataset_id):
            return "ready"
        latest = jobs.latest("convert", dataset_id) if jobs is not None else None
        if latest is not None and latest.state is JobState.FAILED:
            return "failed"
        return "uploaded"

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
        try:
            self._storage.write_record(
                dataset_id, _to_record(safe_filename, inspector.metadata)
            )
        except BaseException:
            self._storage.discard_upload(dataset_id)
            raise
        return StoredDataset(
            id=dataset_id,
            filename=safe_filename,
            status="uploaded",
            metadata=inspector.metadata,
        )
