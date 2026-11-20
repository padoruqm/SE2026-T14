"""VT-057 load check: 80 concurrent tasks, target p95 <= 2.5 s.

Starts the real backend with uvicorn on 127.0.0.1, then runs 80 tasks at the
same time. Each task uploads one LAS file and reads GET /api/config. While the
tasks run, one admin PUT changes the limit. Only existing dependencies are used
(uvicorn + httpx from the dev extra).

Usage (from the repository root):
    PYTHONPATH=backend:backend/tests python3 qa/vt057/load_test.py [rounds]
"""
from __future__ import annotations

import asyncio
import os
import statistics
import subprocess
import sys
import tempfile
import time

import httpx

from las_fixtures import build_las

CONCURRENCY = 80
P95_TARGET_SECONDS = 2.5
PORT = 8765
BASE_URL = f"http://127.0.0.1:{PORT}"
ADMIN_TOKEN = "vt057-load-token"
START_LIMIT = 1024 * 1024  # 1 MiB
NEW_LIMIT = 2 * 1024 * 1024  # 2 MiB, so every upload stays valid
LAS_FILE = build_las(point_count=1000, payload=b"\0" * 20 * 1000)  # ~20 KB


def p95(values: list[float]) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[94]


async def one_task(client: httpx.AsyncClient, index: int) -> tuple[float, bool]:
    started = time.perf_counter()
    upload = await client.post(
        "/api/upload", files={"file": (f"load_{index}.las", LAS_FILE)}
    )
    config = await client.get("/api/config")
    elapsed = time.perf_counter() - started
    # Business outcome, not only status: the file is stored and the limit is sane.
    ok = (
        upload.status_code == 201
        and upload.json()["metadata"]["pointCount"] == 1000
        and config.json()["maxUploadBytes"] in (START_LIMIT, NEW_LIMIT)
    )
    return elapsed, ok


async def one_round() -> tuple[list[float], int, int]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        admin = client.put(
            "/api/admin/config",
            json={"maxUploadBytes": NEW_LIMIT},
            headers={"X-Admin-Token": ADMIN_TOKEN},
        )
        results = await asyncio.gather(
            *(one_task(client, i) for i in range(CONCURRENCY)), admin
        )
        admin_response = results.pop()
        assert admin_response.status_code == 200, admin_response.text
        final_limit = (await client.get("/api/config")).json()["maxUploadBytes"]
        assert final_limit == NEW_LIMIT, final_limit
        # Reset for the next round.
        await client.put(
            "/api/admin/config",
            json={"maxUploadBytes": START_LIMIT},
            headers={"X-Admin-Token": ADMIN_TOKEN},
        )
    latencies = [elapsed for elapsed, _ in results]
    failed = sum(1 for _, ok in results if not ok)
    return latencies, failed, len(results)


def wait_until_ready() -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{BASE_URL}/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError("backend did not start")


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    storage = tempfile.TemporaryDirectory()
    environment = dict(
        os.environ,
        APP_STORAGE_ROOT=storage.name,
        APP_MAX_UPLOAD_BYTES=str(START_LIMIT),
        APP_ADMIN_TOKEN=ADMIN_TOKEN,
    )
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT),
         "--log-level", "warning"],
        env=environment,
    )
    exit_code = 0
    try:
        wait_until_ready()
        print(f"concurrency={CONCURRENCY} file_bytes={len(LAS_FILE)} target_p95={P95_TARGET_SECONDS}s")
        for number in range(1, rounds + 1):
            latencies, failed, total = asyncio.run(one_round())
            value = p95(latencies)
            verdict = "PASS" if value <= P95_TARGET_SECONDS and failed == 0 else "FAIL"
            if verdict == "FAIL":
                exit_code = 1
            print(
                f"round={number} tasks={total} failed={failed} "
                f"p50={statistics.median(latencies):.3f}s p95={value:.3f}s "
                f"max={max(latencies):.3f}s -> {verdict}"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
        storage.cleanup()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
