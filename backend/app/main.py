from __future__ import annotations

from fastapi import FastAPI

from app.api.datasets import router as datasets_router
from app.core.config import Settings
from app.storage.local import LocalDatasetStorage


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    app = FastAPI(title="Point Cloud Explorer API", version="0.1.0")
    app.state.storage = LocalDatasetStorage(
        root=resolved_settings.storage_root,
        max_upload_bytes=resolved_settings.max_upload_bytes,
    )
    app.include_router(datasets_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
