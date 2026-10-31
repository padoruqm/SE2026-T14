#!/usr/bin/env python3
"""Generate a tiny deterministic LAS 1.2 point cloud for local demos and tests."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "sample" / "demo.las"
HEADER_SIZE = 227
POINT_RECORD_SIZE = 20
SCALE = (0.01, 0.01, 0.01)
OFFSET = (500_000.0, 2_000_000.0, 100.0)
RAW_POINTS = (
    (0, 0, 0, 2),
    (1_000, 0, 0, 2),
    (0, 1_000, 0, 5),
    (1_000, 1_000, 500, 5),
    (500, 500, 250, 6),
)


def build_las() -> bytes:
    geo_keys = struct.pack(
        "<20H",
        1,
        1,
        0,
        4,
        1024,
        0,
        1,
        1,
        1025,
        0,
        1,
        1,
        2048,
        0,
        1,
        4326,
        3072,
        0,
        1,
        32648,
    )
    vlr_header = struct.pack(
        "<H16sHH32s",
        0,
        b"LASF_Projection",
        34735,
        len(geo_keys),
        b"GeoTIFF coordinate system",
    )
    point_data_offset = HEADER_SIZE + len(vlr_header) + len(geo_keys)

    header = bytearray(HEADER_SIZE)
    header[:4] = b"LASF"
    header[24:26] = bytes((1, 2))
    header[26:58] = b"SE2026-T14 sample".ljust(32, b"\0")
    header[58:90] = b"Sample LAS generator".ljust(32, b"\0")
    struct.pack_into("<H", header, 94, HEADER_SIZE)
    struct.pack_into("<I", header, 96, point_data_offset)
    struct.pack_into("<I", header, 100, 1)
    header[104] = 0
    struct.pack_into("<H", header, 105, POINT_RECORD_SIZE)
    struct.pack_into("<I", header, 107, len(RAW_POINTS))
    struct.pack_into("<I", header, 111, len(RAW_POINTS))
    struct.pack_into("<3d", header, 131, *SCALE)
    struct.pack_into("<3d", header, 155, *OFFSET)

    coordinates = [
        tuple(raw[index] * SCALE[index] + OFFSET[index] for index in range(3))
        for raw in RAW_POINTS
    ]
    xs, ys, zs = zip(*coordinates)
    struct.pack_into(
        "<6d",
        header,
        179,
        max(xs),
        min(xs),
        max(ys),
        min(ys),
        max(zs),
        min(zs),
    )

    point_records = bytearray()
    for x, y, z, classification in RAW_POINTS:
        record = bytearray(POINT_RECORD_SIZE)
        struct.pack_into("<3iH", record, 0, x, y, z, 100)
        record[14] = 9
        record[15] = classification
        point_records.extend(record)

    return bytes(header) + vlr_header + geo_keys + bytes(point_records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output LAS path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    las = build_las()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(las)
    print(
        f"Created {args.output} "
        f"({len(las)} bytes, {len(RAW_POINTS)} points, EPSG:32648)"
    )


if __name__ == "__main__":
    main()
