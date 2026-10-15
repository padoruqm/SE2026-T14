from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    storage_root: Path
    max_upload_bytes: int

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            storage_root=Path(os.getenv("APP_STORAGE_ROOT", "./data/runtime")),
            max_upload_bytes=int(os.getenv("APP_MAX_UPLOAD_BYTES", 100 * 1024 * 1024)),
        )
