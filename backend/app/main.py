from __future__ import annotations

from fastapi import FastAPI

from app.api.datasets import router as datasets_router
from app.api.jobs import router as jobs_router
from app.core.config import Settings
from app.core.errors import register_error_handlers
from app.jobs.runner import ConvertJobRunner
from app.jobs.store import JobStore
from app.processing.converter import Converter, PotreeConverter
from app.storage.local import LocalDatasetStorage


def create_app(
    settings: Settings | None = None, converter: Converter | None = None
) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    app = FastAPI(title="Point Cloud Explorer API", version="0.1.0")
    app.state.storage = LocalDatasetStorage(
        root=resolved_settings.storage_root,
        max_upload_bytes=resolved_settings.max_upload_bytes,
    )
    app.state.job_store = JobStore()
    app.state.jobs = ConvertJobRunner(
        storage=app.state.storage,
        converter=converter
        or PotreeConverter(
            resolved_settings.potree_converter_path,
            resolved_settings.conversion_timeout_seconds,
        ),
        store=app.state.job_store,
        workers=resolved_settings.job_workers,
    )
    register_error_handlers(app)
    app.include_router(datasets_router)
    app.include_router(jobs_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
