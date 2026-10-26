from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    storage_root: Path
    max_upload_bytes: int
    potree_converter_path: str | None = None
    conversion_timeout_seconds: float = 600.0
    job_workers: int = 1

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            storage_root=Path(os.getenv("APP_STORAGE_ROOT", "./data/runtime")),
            max_upload_bytes=int(os.getenv("APP_MAX_UPLOAD_BYTES", 100 * 1024 * 1024)),
            potree_converter_path=os.getenv("APP_POTREE_CONVERTER_PATH") or None,
            conversion_timeout_seconds=float(
                os.getenv("APP_JOB_TIMEOUT_SECONDS") or 600
            ),
            job_workers=int(os.getenv("APP_JOB_WORKERS") or 1),
        )
