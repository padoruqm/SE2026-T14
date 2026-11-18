#!/usr/bin/env python3
"""Generate a tiny Potree 2.0 octree (one leaf node) for the browser E2E tests.

PotreeConverter is a Linux-only binary, so the E2E suite cannot depend on it. This writes
the same three files it would (metadata.json, hierarchy.bin, octree.bin) for a 40 x 40
grid on a sloped plane, so the test knows the exact world coordinates it should read back.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "frontend" / "e2e" / "fixtures" / "potree"

GRID = 40
SPACING = 2.5  # metres between neighbouring points
ORIGIN = (500_000.0, 2_000_000.0, 100.0)  # same UTM zone 48N origin as generate-sample-las.py
SLOPE = 0.1  # metres of height per metre in x
SCALE = 0.001
POINT_SIZE = 12 + 8  # int32 x 3 position, uint16 x 4 rgba


def build() -> tuple[dict[str, object], bytes, bytes]:
    points = [
        (ORIGIN[0] + i * SPACING, ORIGIN[1] + j * SPACING, ORIGIN[2] + i * SPACING * SLOPE)
        for j in range(GRID)
        for i in range(GRID)
    ]
    mins = tuple(min(p[axis] for p in points) for axis in range(3))
    maxs = tuple(max(p[axis] for p in points) for axis in range(3))

    octree = bytearray()
    for x, y, z in points:
        octree += struct.pack(
            "<3i", *(round((value - low) / SCALE) for value, low in zip((x, y, z), mins))
        )
        shade = round(65535 * (z - mins[2]) / (maxs[2] - mins[2]))
        octree += struct.pack("<4H", shade, 65535 - shade, 32768, 65535)

    hierarchy = struct.pack("<BBIqq", 1, 0, len(points), 0, len(octree))  # one leaf node
    metadata = {
        "version": "2.0",
        "name": "e2e-grid",
        "description": "",
        "points": len(points),
        "projection": "",
        "hierarchy": {"firstChunkSize": len(hierarchy), "stepSize": 4, "depth": 0},
        "offset": list(mins),
        "scale": [SCALE] * 3,
        "spacing": SPACING,
        "boundingBox": {"min": list(mins), "max": list(maxs)},
        "encoding": "DEFAULT",
        "attributes": [
            {
                "name": "position",
                "description": "",
                "size": 12,
                "numElements": 3,
                "elementSize": 4,
                "type": "int32",
                "min": list(mins),
                "max": list(maxs),
            },
            {
                "name": "rgb",
                "description": "",
                "size": 8,
                "numElements": 4,
                "elementSize": 2,
                "type": "uint16",
                "min": [0, 0, 0, 65535],
                "max": [65535, 65535, 65535, 65535],
            },
        ],
    }
    return metadata, hierarchy, bytes(octree)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    metadata, hierarchy, octree = build()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (args.output / "hierarchy.bin").write_bytes(hierarchy)
    (args.output / "octree.bin").write_bytes(octree)
    print(f"Wrote {metadata['points']} points to {args.output}")


if __name__ == "__main__":
    main()
