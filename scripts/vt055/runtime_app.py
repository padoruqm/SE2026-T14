"""Local E2E fixture: real app/API/storage + built UI, without Potree binaries."""
from __future__ import annotations

import os
import runpy
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ["VT055_DATA_ROOT"])
sample = runpy.run_path(str(ROOT / "scripts/generate-sample-las.py"))["build_las"]()
uploads = DATA / "uploads"
uploads.mkdir(parents=True, exist_ok=True)
for dataset in ["pc_e2e", "pc_race", "pc_replay", *[f"pc_load_{i:02d}" for i in range(60)]]:
    (uploads / f"{dataset}.las").write_bytes(sample)

app = create_app(Settings(storage_root=DATA, max_upload_bytes=1 << 20))


@app.get("/viewer/{dataset_id}", include_in_schema=False)
def viewer_page(dataset_id: str):
    return FileResponse(ROOT / "frontend/dist/index.html")


app.mount("/assets", StaticFiles(directory=ROOT / "frontend/dist/assets"), name="assets")
