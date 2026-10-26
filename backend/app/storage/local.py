from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

class UploadTooLargeError(ValueError):
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
        self._upload_root.mkdir(parents=True, exist_ok=True)
        destination = self._upload_root / f"{dataset_id}{suffix}"
        partial = destination.with_suffix(f"{suffix}.part")
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
