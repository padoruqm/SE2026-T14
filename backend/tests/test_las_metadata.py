from __future__ import annotations

import unittest

from app.core.errors import InvalidPointCloudError
from app.services.las_metadata import (
    HEADER_PROBE_BYTES,
    MAX_VLR_PROBE_BYTES,
    parse_las_metadata,
    required_head_length,
)
from las_fixtures import Vlr, build_las, geotiff_key_directory
from wkt_fixtures import AUTZEN_CLASSIFIED_WKT, AUTZEN_TRIM_WKT

PROJECTION = "LASF_Projection"


class ParseLasMetadataTest(unittest.TestCase):
    def test_reads_point_count_and_bounds_from_a_1_2_header(self) -> None:
        las = build_las(
            point_count=1250000,
            min_xyz=(100.0, 200.0, -1.5),
            max_xyz=(180.5, 260.25, 42.7),
        )

        metadata = parse_las_metadata(las)

        self.assertEqual(1250000, metadata.point_count)
        self.assertEqual(
            (100.0, 200.0, -1.5, 180.5, 260.25, 42.7),
            (
                metadata.bounds.minX,
                metadata.bounds.minY,
                metadata.bounds.minZ,
                metadata.bounds.maxX,
                metadata.bounds.maxY,
                metadata.bounds.maxZ,
            ),
        )
        self.assertIsNone(metadata.crs)

    def test_reads_the_64_bit_point_count_of_a_1_4_header(self) -> None:
        las = build_las(minor_version=4, point_count=5_000_000_000)

        self.assertEqual(5_000_000_000, parse_las_metadata(las).point_count)

    def test_reads_epsg_from_the_geotiff_key_directory(self) -> None:
        keys = geotiff_key_directory((1024, 1), (3072, 32648))
        las = build_las(vlrs=(Vlr(PROJECTION, 34735, keys),))

        self.assertEqual("EPSG:32648", parse_las_metadata(las).crs)

    def test_falls_back_to_a_geographic_epsg_code(self) -> None:
        keys = geotiff_key_directory((2048, 4326))
        las = build_las(vlrs=(Vlr(PROJECTION, 34735, keys),))

        self.assertEqual("EPSG:4326", parse_las_metadata(las).crs)

    def test_ignores_user_defined_crs_codes(self) -> None:
        keys = geotiff_key_directory((3072, 32767))
        las = build_las(vlrs=(Vlr(PROJECTION, 34735, keys),))

        self.assertIsNone(parse_las_metadata(las).crs)

    def test_reads_epsg_from_a_wkt_record(self) -> None:
        wkt = b'PROJCS["WGS 84 / UTM 48N",GEOGCS["WGS 84",AUTHORITY["EPSG","4326"]],AUTHORITY["EPSG","32648"]]\0'
        las = build_las(vlrs=(Vlr(PROJECTION, 2112, wkt),))

        self.assertEqual("EPSG:32648", parse_las_metadata(las).crs)

    def test_ignores_vlrs_from_other_users(self) -> None:
        keys = geotiff_key_directory((3072, 32648))
        las = build_las(vlrs=(Vlr("other", 34735, keys),))

        self.assertIsNone(parse_las_metadata(las).crs)

    def test_rejects_a_truncated_header(self) -> None:
        las = build_las()

        with self.assertRaises(InvalidPointCloudError):
            parse_las_metadata(las[:150])

    def test_rejects_a_wrong_signature(self) -> None:
        las = b"XXXX" + build_las()[4:]

        with self.assertRaises(InvalidPointCloudError):
            parse_las_metadata(las)

    def test_rejects_inverted_bounds(self) -> None:
        las = build_las(min_xyz=(5.0, 0.0, 0.0), max_xyz=(1.0, 1.0, 1.0))

        with self.assertRaises(InvalidPointCloudError):
            parse_las_metadata(las)

    def test_rejects_non_finite_bounds(self) -> None:
        las = build_las(max_xyz=(float("nan"), 1.0, 1.0))

        with self.assertRaises(InvalidPointCloudError):
            parse_las_metadata(las)


def _crs_of(wkt: str) -> str | None:
    las = build_las(vlrs=(Vlr(PROJECTION, 2112, wkt.encode() + b"\0"),))
    return parse_las_metadata(las).crs


class CrsFromWktTest(unittest.TestCase):
    """Only a code that belongs to the coordinate system itself counts."""

    def test_reads_the_projected_crs_code(self) -> None:
        wkt = (
            'PROJCS["WGS 84 / UTM zone 48N",GEOGCS["WGS 84",DATUM["WGS_1984",'
            'SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
            'AUTHORITY["EPSG","6326"]],AUTHORITY["EPSG","4326"]],'
            'UNIT["metre",1,AUTHORITY["EPSG","9001"]],AUTHORITY["EPSG","32648"]]'
        )
        self.assertEqual("EPSG:32648", _crs_of(wkt))

    def test_reads_a_geographic_crs_code(self) -> None:
        wkt = (
            'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
            'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
            'AUTHORITY["EPSG","4326"]]'
        )
        self.assertEqual("EPSG:4326", _crs_of(wkt))

    def test_a_user_defined_projection_has_no_code(self) -> None:
        # Its last AUTHORITY is the foot unit (EPSG:9002), which is not a CRS.
        self.assertIsNone(_crs_of(AUTZEN_TRIM_WKT))

    def test_a_compound_crs_reports_its_horizontal_part(self) -> None:
        # The compound has no code; the vertical part (EPSG:6360) comes last.
        self.assertEqual("EPSG:2992", _crs_of(AUTZEN_CLASSIFIED_WKT))

    def test_a_compound_crs_with_its_own_code_still_reports_the_horizontal_part(
        self,
    ) -> None:
        wkt = (
            'COMPD_CS["WGS 84 / UTM 48N + EGM96 height",'
            'PROJCS["WGS 84 / UTM zone 48N",UNIT["metre",1],AUTHORITY["EPSG","32648"]],'
            'VERT_CS["EGM96 height",UNIT["metre",1],AUTHORITY["EPSG","5773"]],'
            'AUTHORITY["EPSG","9705"]]'
        )
        self.assertEqual("EPSG:32648", _crs_of(wkt))

    def test_reads_wkt2_identifiers(self) -> None:
        wkt = (
            'PROJCRS["WGS 84 / UTM zone 48N",BASEGEOGCRS["WGS 84",'
            'DATUM["World Geodetic System 1984",ELLIPSOID["WGS 84",6378137,298.257223563]],'
            'ID["EPSG",4326]],CONVERSION["UTM zone 48N",ID["EPSG",16048]],'
            'CS[Cartesian,2],LENGTHUNIT["metre",1,ID["EPSG",9001]],ID["EPSG",32648]]'
        )
        self.assertEqual("EPSG:32648", _crs_of(wkt))

    def test_a_wkt2_compound_reports_its_horizontal_part(self) -> None:
        wkt = (
            'COMPOUNDCRS["x",PROJCRS["h",LENGTHUNIT["metre",1],ID["EPSG",32648]],'
            'VERTCRS["v",LENGTHUNIT["metre",1],ID["EPSG",5773]]]'
        )
        self.assertEqual("EPSG:32648", _crs_of(wkt))

    def test_brackets_inside_names_do_not_confuse_it(self) -> None:
        # WKT escapes a quote by doubling it.
        wkt = (
            'PROJCS["a ""quoted"" [name], AUTHORITY[""EPSG"",""1""]",'
            'AUTHORITY["EPSG","32648"]]'
        )
        self.assertEqual("EPSG:32648", _crs_of(wkt))

    def test_malformed_wkt_has_no_code(self) -> None:
        for wkt in ("", "not wkt", 'PROJCS["unterminated",AUTHORITY["EPSG","32648"]', "[]"):
            with self.subTest(wkt=wkt):
                self.assertIsNone(_crs_of(wkt))


class RequiredHeadLengthTest(unittest.TestCase):
    def test_covers_the_header_and_its_vlrs(self) -> None:
        keys = geotiff_key_directory((3072, 32648))
        las = build_las(vlrs=(Vlr(PROJECTION, 34735, keys),), payload=b"x" * 500)

        length = required_head_length(las[:HEADER_PROBE_BYTES])

        self.assertEqual(227 + 54 + len(keys), length)

    def test_caps_the_amount_of_data_buffered_for_vlrs(self) -> None:
        las = bytearray(build_las())
        las[96:100] = (50 * 1024 * 1024).to_bytes(4, "little")

        self.assertEqual(
            MAX_VLR_PROBE_BYTES, required_head_length(bytes(las[:HEADER_PROBE_BYTES]))
        )

    def test_rejects_an_implausible_header_size(self) -> None:
        las = bytearray(build_las())
        las[94:96] = (10).to_bytes(2, "little")

        with self.assertRaises(InvalidPointCloudError):
            required_head_length(bytes(las[:HEADER_PROBE_BYTES]))


if __name__ == "__main__":
    unittest.main()
