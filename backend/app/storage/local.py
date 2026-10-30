from __future__ import annotations

import re
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

_DATASET_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SUFFIX = re.compile(r"\.[A-Za-z0-9]{1,8}")
_RESERVED_SUFFIXES = frozenset({".part"})


class UploadTooLargeError(ValueError):
    pass


class InvalidStorageKeyError(ValueError):
    pass


class LocalDatasetStorage:
    def __init__(self, root: Path, max_upload_bytes: int) -> None:
        self._upload_root = root / "uploads"
        self._converted_root = root / "converted"
        self._max_upload_bytes = max_upload_bytes

    async def save(
        self,
        dataset_id: str,
        suffix: str,
        chunks: AsyncIterator[bytes],
    ) -> tuple[Path, int]:
        if not _DATASET_ID.fullmatch(dataset_id):
            raise InvalidStorageKeyError("Invalid dataset id")
        if not _SUFFIX.fullmatch(suffix) or suffix.lower() in _RESERVED_SUFFIXES:
            raise InvalidStorageKeyError("Invalid file suffix")

        self._upload_root.mkdir(parents=True, exist_ok=True)
        destination = self._upload_root / f"{dataset_id}{suffix}"
        partial = destination.with_suffix(f"{suffix}.part")
        if destination.is_symlink() or partial.is_symlink():
            raise InvalidStorageKeyError("Refusing to write through a symbolic link")
        size = 0

        try:
            with partial.open("wb") as output:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > self._max_upload_bytes:
                        raise UploadTooLargeError
                    output.write(chunk)
            partial.replace(destination)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

        return destination, size

    def find(self, dataset_id: str) -> Path | None:
        """Return the stored upload for `dataset_id`, or None if there is none."""
        if not _DATASET_ID.fullmatch(dataset_id) or not self._upload_root.is_dir():
            return None
        for candidate in sorted(self._upload_root.glob(f"{dataset_id}.*")):
            if (
                candidate.suffix.lower() not in _RESERVED_SUFFIXES
                and candidate.is_file()
                and not candidate.is_symlink()
            ):
                return candidate
        return None

    def has_converted(self, dataset_id: str) -> bool:
        return (self._converted_root / dataset_id).is_dir()

    def new_staging_dir(self, dataset_id: str) -> Path:
        """Create an empty directory next to the results for a conversion to work in."""
        self._converted_root.mkdir(parents=True, exist_ok=True)
        return Path(
            tempfile.mkdtemp(prefix=f".{dataset_id}-", dir=self._converted_root)
        )

    def publish_converted(self, dataset_id: str, result: Path) -> None:
        """Make `result` the converted output for `dataset_id`, replacing any old one.

        The old result is moved aside first, so a reader sees either the old or the
        new result and never a missing one.
        """
        destination = self._converted_root / dataset_id
        previous: Path | None = None
        if destination.exists():
            previous = Path(
                tempfile.mkdtemp(prefix=f".{dataset_id}-old-", dir=self._converted_root)
            )
            destination.rename(previous / "result")
        try:
            result.rename(destination)
        except BaseException:
            if previous is not None:
                (previous / "result").rename(destination)
            raise
        finally:
            if previous is not None:
                shutil.rmtree(previous, ignore_errors=True)

    def discard_staging_dir(self, staging: Path) -> None:
        shutil.rmtree(staging, ignore_errors=True)
