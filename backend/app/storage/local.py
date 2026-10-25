from __future__ import annotations

import re
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
