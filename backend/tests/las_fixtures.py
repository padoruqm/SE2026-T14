from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER_SIZE_1_2 = 227
HEADER_SIZE_1_4 = 375
VLR_HEADER_SIZE = 54


@dataclass(frozen=True, slots=True)
class Vlr:
    user_id: str
    record_id: int
    data: bytes


def geotiff_key_directory(*keys: tuple[int, int]) -> bytes:
    """Build a GeoTIFF key directory (record 34735) from (key id, value) pairs."""
    words = [1, 1, 0, len(keys)]
    for key_id, value in keys:
        words.extend([key_id, 0, 1, value])
    return struct.pack(f"<{len(words)}H", *words)


def build_las(
    *,
    minor_version: int = 2,
    point_count: int = 2,
    scale: tuple[float, float, float] = (0.01, 0.01, 0.01),
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    min_xyz: tuple[float, float, float] = (1.0, 1.0, 0.0),
    max_xyz: tuple[float, float, float] = (2.0, 2.0, 1.0),
    vlrs: tuple[Vlr, ...] = (),
    payload: bytes = b"",
) -> bytes:
    """Build a LAS file with a valid public header block, VLRs and raw payload."""
    header_size = HEADER_SIZE_1_4 if minor_version >= 4 else HEADER_SIZE_1_2
    header = bytearray(header_size)
    header[0:4] = b"LASF"
    header[24] = 1
    header[25] = minor_version
    struct.pack_into("<H", header, 94, header_size)

    vlr_bytes = b""
    for vlr in vlrs:
        vlr_bytes += struct.pack(
            "<H16sHH32s",
            0,
            vlr.user_id.encode("ascii"),
            vlr.record_id,
            len(vlr.data),
            b"",
        )
        vlr_bytes += vlr.data

    struct.pack_into("<I", header, 96, header_size + len(vlr_bytes))
    struct.pack_into("<I", header, 100, len(vlrs))
    header[104] = 1
    struct.pack_into("<H", header, 105, 28)
    if minor_version >= 4:
        struct.pack_into("<Q", header, 247, point_count)
    else:
        struct.pack_into("<I", header, 107, point_count)
    struct.pack_into("<3d", header, 131, *scale)
    struct.pack_into("<3d", header, 155, *offset)
    struct.pack_into(
        "<6d",
        header,
        179,
        max_xyz[0],
        min_xyz[0],
        max_xyz[1],
        min_xyz[1],
        max_xyz[2],
        min_xyz[2],
    )
    return bytes(header) + vlr_bytes + payload
