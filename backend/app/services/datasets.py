from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from uuid import uuid4

from app.core.errors import (
    ConflictError,
    FileTooLargeError,
    GoneError,
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
    source_id: str | None = None


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


def _to_record(
    filename: str, metadata: LasMetadata, source_id: str | None = None
) -> dict[str, object]:
    record: dict[str, object] = {
        "filename": filename,
        "point_count": metadata.point_count,
        "bounds": asdict(metadata.bounds),
        "crs": metadata.crs,
    }
    if source_id is not None:
        record["source_id"] = source_id
    return record


def _from_record(record: Mapping[str, Any]) -> tuple[str, LasMetadata, str | None]:
    source_id = record.get("source_id")
    return (
        str(record["filename"]),
        LasMetadata(
            point_count=int(record["point_count"]),
            bounds=LasBounds(**record["bounds"]),
            crs=record["crs"],
        ),
        None if source_id is None else str(source_id),
    )


class DatasetService:
    def __init__(
        self, storage: LocalDatasetStorage, job_store: JobStore | None = None
    ) -> None:
        self._storage = storage
        self._job_store = job_store

    def get(self, dataset_id: str) -> StoredDataset:
        """Return the dataset, or raise NotFoundError (never existed) or GoneError.

        GoneError means the record is still there but the data behind it is not.
        """
        record = self._storage.read_record(dataset_id)
        if record is None:
            raise NotFoundError("Point cloud not found")
        filename, metadata, source_id = _from_record(record)
        if self._is_lost(dataset_id, source_id):
            raise GoneError("This point cloud is no longer available")
        return StoredDataset(
            id=dataset_id,
            filename=filename,
            status=self._status(dataset_id),
            metadata=metadata,
            source_id=source_id,
        )

    def download_file(self, dataset_id: str) -> tuple[StoredDataset, Path]:
        dataset = self.get(dataset_id)
        if dataset.status != "ready":
            raise ConflictError("Point cloud is not ready for download")

        source = self._storage.find(dataset_id)
        if source is None:
            raise GoneError("The LAS/LAZ file is no longer available")
        return dataset, source

    def _is_lost(self, dataset_id: str, source_id: str | None) -> bool:
        if self._storage.has_converted(dataset_id):
            return False
        # A result has no upload to convert again, so it is lost without its files.
        # An upload only counts as lost when the file itself is gone.
        return source_id is not None or self._storage.find(dataset_id) is None

    def create_result(
        self,
        source_id: str,
        filename: str,
        metadata: LasMetadata,
        converted: Path,
        source_file: Path | None = None,
    ) -> StoredDataset:
        """Register a dataset derived from `source_id` (for example a crop).

        `converted` is the viewer-ready output and `source_file` the point cloud file
        itself (LAS/LAZ); both are moved into storage, so the result can be viewed,
        downloaded and processed like an upload. The result gets its own ID, with
        `source_id` recording where it came from. If anything fails, nothing is kept.
        """
        self.get(source_id)

        dataset_id = f"pc_{uuid4().hex}"
        safe_filename = sanitize_filename(filename)
        self._storage.publish_converted(dataset_id, converted)
        try:
            if source_file is not None:
                self._storage.store_file(dataset_id, source_file)
            self._storage.write_record(
                dataset_id, _to_record(safe_filename, metadata, source_id)
            )
        except BaseException:
            self._storage.discard_converted(dataset_id)
            self._storage.discard_upload(dataset_id)
            raise
        return StoredDataset(
            id=dataset_id,
            filename=safe_filename,
            status="ready",
            metadata=metadata,
            source_id=source_id,
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
