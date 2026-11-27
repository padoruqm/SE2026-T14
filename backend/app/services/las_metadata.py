from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from typing import NamedTuple

from app.core.errors import InvalidPointCloudError

LAS_SIGNATURE = b"LASF"

MIN_HEADER_SIZE = 227
MAX_HEADER_SIZE = 1024
HEADER_PROBE_BYTES = 100
MAX_VLR_PROBE_BYTES = 1024 * 1024

_VLR_HEADER_SIZE = 54
_PROJECTION_USER_ID = "LASF_Projection"
_WKT_RECORD_ID = 2112
_GEOTIFF_KEY_DIRECTORY_RECORD_ID = 34735
_GEOGRAPHIC_TYPE_KEY = 2048
_PROJECTED_CS_TYPE_KEY = 3072
_USER_DEFINED = 32767
_HORIZONTAL_CRS = frozenset(
    {
        "PROJCS",
        "GEOGCS",
        "GEOCCS",
        "PROJCRS",
        "PROJECTEDCRS",
        "GEOGCRS",
        "GEOGRAPHICCRS",
        "GEODCRS",
        "GEODETICCRS",
    }
)
_COMPOUND_CRS = frozenset({"COMPD_CS", "COMPOUNDCRS"})
_IDENTIFIERS = frozenset({"AUTHORITY", "ID"})
_WKT_KEYWORD = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*([\[(])")
_WKT_VALUE = re.compile(r"\s*([^,\[\]()\s\"]+)")
_WKT_CLOSE = {"[": "]", "(": ")"}


@dataclass(frozen=True, slots=True)
class LasBounds:
    minX: float
    minY: float
    minZ: float
    maxX: float
    maxY: float
    maxZ: float


@dataclass(frozen=True, slots=True)
class LasMetadata:
    point_count: int
    bounds: LasBounds
    crs: str | None


def required_head_length(head: bytes) -> int:
    """Return how many leading bytes are needed to read the metadata.

    ``head`` must hold at least HEADER_PROBE_BYTES bytes.
    """
    header_size = struct.unpack_from("<H", head, 94)[0]
    point_data_offset = struct.unpack_from("<I", head, 96)[0]
    if not MIN_HEADER_SIZE <= header_size <= MAX_HEADER_SIZE:
        raise InvalidPointCloudError()
    if point_data_offset < header_size:
        raise InvalidPointCloudError()
    return max(header_size, min(point_data_offset, MAX_VLR_PROBE_BYTES))


def parse_las_metadata(head: bytes) -> LasMetadata:
    """Read point count, bounds and CRS from the start of a LAS/LAZ file."""
    if len(head) < HEADER_PROBE_BYTES or not head.startswith(LAS_SIGNATURE):
        raise InvalidPointCloudError()

    header_size = struct.unpack_from("<H", head, 94)[0]
    if len(head) < header_size or header_size < MIN_HEADER_SIZE:
        raise InvalidPointCloudError()

    major, minor = head[24], head[25]
    if major != 1:
        raise InvalidPointCloudError()

    if minor >= 4 and header_size >= 375:
        point_count = struct.unpack_from("<Q", head, 247)[0]
    else:
        point_count = struct.unpack_from("<I", head, 107)[0]

    max_x, min_x, max_y, min_y, max_z, min_z = struct.unpack_from("<6d", head, 179)
    values = (min_x, min_y, min_z, max_x, max_y, max_z)
    if not all(math.isfinite(value) for value in values):
        raise InvalidPointCloudError()
    if min_x > max_x or min_y > max_y or min_z > max_z:
        raise InvalidPointCloudError()

    vlr_count = struct.unpack_from("<I", head, 100)[0]
    return LasMetadata(
        point_count=point_count,
        bounds=LasBounds(min_x, min_y, min_z, max_x, max_y, max_z),
        crs=_read_crs(head, header_size, vlr_count),
    )


def _read_crs(head: bytes, header_size: int, vlr_count: int) -> str | None:
    geotiff_crs: str | None = None
    wkt_crs: str | None = None

    position = header_size
    for _ in range(vlr_count):
        if position + _VLR_HEADER_SIZE > len(head):
            break
        user_id = head[position + 2 : position + 18].split(b"\0", 1)[0]
        record_id, length = struct.unpack_from("<HH", head, position + 18)
        data_start = position + _VLR_HEADER_SIZE
        data = head[data_start : data_start + length]
        if len(data) < length:
            break
        position = data_start + length

        if user_id.decode("ascii", "ignore") != _PROJECTION_USER_ID:
            continue
        if record_id == _GEOTIFF_KEY_DIRECTORY_RECORD_ID:
            geotiff_crs = geotiff_crs or _epsg_from_geotiff_keys(data)
        elif record_id == _WKT_RECORD_ID:
            wkt_crs = wkt_crs or _epsg_from_wkt(data)

    return geotiff_crs or wkt_crs


def _epsg_from_geotiff_keys(data: bytes) -> str | None:
    if len(data) < 8:
        return None
    key_count = struct.unpack_from("<H", data, 6)[0]
    key_count = min(key_count, (len(data) - 8) // 8)

    codes: dict[int, int] = {}
    for index in range(key_count):
        key_id, location, _count, value = struct.unpack_from(
            "<4H", data, 8 + index * 8
        )
        if location == 0:
            codes[key_id] = value

    for key_id in (_PROJECTED_CS_TYPE_KEY, _GEOGRAPHIC_TYPE_KEY):
        code = codes.get(key_id)
        if code and code != _USER_DEFINED:
            return f"EPSG:{code}"
    return None


def _epsg_from_wkt(data: bytes) -> str | None:
    """The EPSG code of the horizontal CRS described by WKT 1 or 2, or None.

    Only a code attached to the CRS node itself counts. The last AUTHORITY in
    the text can belong to a unit (EPSG:9002 is the foot) or to the vertical
    part of a compound CRS, so it is not used. For a compound CRS the
    horizontal part is reported.
    """
    crs = _parse_wkt(data.decode("utf-8", "ignore").rstrip("\0 \r\n\t"))
    if crs is None:
        return None
    if crs.keyword in _COMPOUND_CRS:
        for part in crs.args:
            if isinstance(part, _WktNode) and part.keyword in _HORIZONTAL_CRS:
                return _own_epsg(part)
        return None
    return _own_epsg(crs) if crs.keyword in _HORIZONTAL_CRS else None


class _WktNode(NamedTuple):
    keyword: str
    args: list[str | _WktNode]


def _own_epsg(crs: _WktNode) -> str | None:
    for arg in crs.args:
        if isinstance(arg, _WktNode) and arg.keyword in _IDENTIFIERS:
            authority, code = (arg.args + ["", ""])[:2]
            if authority == "EPSG" and isinstance(code, str) and code.isdigit():
                return f"EPSG:{code}"
    return None


def _parse_wkt(text: str) -> _WktNode | None:
    try:
        node, end = _parse_wkt_node(text, 0, depth=0)
    except ValueError:
        return None
    return node if not text[end:].strip() else None


def _parse_wkt_node(text: str, pos: int, depth: int) -> tuple[_WktNode, int]:
    """Parse `KEYWORD[arg, ...]` at `pos`; arguments are strings, values or nodes."""
    if depth > 32:
        raise ValueError("WKT nested too deeply")
    match = _WKT_KEYWORD.match(text, pos)
    if not match:
        raise ValueError("expected a WKT keyword")
    close = _WKT_CLOSE[match.group(2)]
    args: list[str | _WktNode] = []
    pos = match.end()
    while True:
        pos = _skip_space(text, pos)
        if pos >= len(text):
            raise ValueError("unterminated WKT node")
        if text[pos] == close and not args:
            return _WktNode(match.group(1).upper(), args), pos + 1
        value: str | _WktNode
        if text[pos] == '"':
            value, pos = _parse_wkt_string(text, pos)
        elif _WKT_KEYWORD.match(text, pos):
            value, pos = _parse_wkt_node(text, pos, depth + 1)
        else:
            bare = _WKT_VALUE.match(text, pos)
            if not bare:
                raise ValueError("expected a WKT value")
            value, pos = bare.group(1), bare.end()
        args.append(value)
        pos = _skip_space(text, pos)
        if pos < len(text) and text[pos] == ",":
            pos += 1
        elif pos < len(text) and text[pos] == close:
            return _WktNode(match.group(1).upper(), args), pos + 1
        else:
            raise ValueError("expected ',' or a closing bracket")


def _parse_wkt_string(text: str, pos: int) -> tuple[str, int]:
    """A quoted string starting at `pos`; WKT escapes a quote by doubling it."""
    chars: list[str] = []
    pos += 1
    while pos < len(text):
        if text[pos] == '"':
            if text.startswith('""', pos):
                chars.append('"')
                pos += 2
                continue
            return "".join(chars), pos + 1
        chars.append(text[pos])
        pos += 1
    raise ValueError("unterminated WKT string")


def _skip_space(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos
