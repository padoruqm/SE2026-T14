"""Measure real local TCP latency for 60 concurrent draft operations."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import statistics
import time
from pathlib import Path

import httpx


def summary(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "requests": len(samples), "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 3),
        "max_ms": round(max(samples), 3),
    }


async def run(base: str) -> dict:
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=60, max_keepalive_connections=60), timeout=10) as client:
        async def revision(dataset):
            response = await client.get(f"{base}/api/pointcloud/{dataset}/draft")
            response.raise_for_status()
            return response.json()["revision"]

        async def batch(commands):
            start = asyncio.Event()

            async def send(dataset, command):
                await start.wait()
                before = time.perf_counter()
                response = await client.put(f"{base}/api/pointcloud/{dataset}/draft", json=command)
                elapsed = (time.perf_counter() - before) * 1000
                return response.status_code, response.json(), elapsed

            tasks = [asyncio.create_task(send(dataset, command)) for dataset, command in commands]
            start.set()
            return await asyncio.gather(*tasks)

        latencies = []
        for round_id in range(3):
            datasets = [f"pc_load_{i:02d}" for i in range(60)]
            revisions = await asyncio.gather(*(revision(d) for d in datasets))
            commands = [(dataset, {
                "expectedRevision": rev, "operationId": f"load-{i}-{rev}",
                "state": {"pointSize": 1 + ((i + round_id) % 9) * 0.5, "colorMode": "rgb"},
            }) for i, (dataset, rev) in enumerate(zip(datasets, revisions))]
            responses = await batch(commands)
            for (_, command), (code, body, elapsed) in zip(commands, responses):
                assert code == 200, (code, body)
                assert body == {"revision": command["expectedRevision"] + 1, "state": command["state"]}
                latencies.append(elapsed)

        base_revision = await revision("pc_race")
        competing = [("pc_race", {
            "expectedRevision": base_revision, "operationId": f"race-{base_revision}-{i}",
            "state": {"pointSize": 1 + (i % 9) * 0.5, "colorMode": "rgb"},
        }) for i in range(60)]
        race = await batch(competing)
        assert sorted(code for code, _, _ in race) == [200] + [409] * 59
        assert await revision("pc_race") == base_revision + 1

        base_revision = await revision("pc_replay")
        command = {"expectedRevision": base_revision, "operationId": f"replay-{base_revision}",
                   "state": {"pointSize": 2.5, "colorMode": "intensity"}}
        replay = await batch([("pc_replay", command)] * 60)
        assert all(code == 200 and body == {"revision": base_revision + 1, "state": command["state"]}
                   for code, body, _ in replay)
        assert await revision("pc_replay") == base_revision + 1

        result = {"concurrency": 60, "independent_writes": summary(latencies),
                  "same_base_race": {**summary([r[2] for r in race]), "success": 1, "conflicts": 59},
                  "same_operation_retries": {**summary([r[2] for r in replay]), "acknowledgements": 60, "revision_advances": 1},
                  "target_p95_ms": 2000, "python": platform.python_version(),
                  "platform": platform.platform(),
                  "scope": "single uvicorn process, real loopback TCP and local SQLite/WAL; small viewer-settings JSON; excludes WAN, upload/conversion and 3D rendering"}
        result["target_met_in_this_run"] = all(result[k]["p95_ms"] <= 2000 for k in (
            "independent_writes", "same_base_race", "same_operation_retries"))
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args.base_url))
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + "\n")
    raise SystemExit(not result["target_met_in_this_run"])
