from __future__ import annotations

import unittest

from app.services.crop_bounds import CropBoundsError, validate_crop_bounds
from app.services.las_metadata import LasBounds

DATASET = LasBounds(minX=0.0, minY=0.0, minZ=10.0, maxX=100.0, maxY=50.0, maxZ=20.0)


def region(**overrides: float) -> dict[str, float]:
    bounds = {"minX": 10.0, "minY": 10.0, "minZ": 12.0, "maxX": 20.0, "maxY": 30.0, "maxZ": 18.0}
    bounds.update(overrides)
    return bounds


class ValidateCropBoundsTest(unittest.TestCase):
    def test_accepts_a_region_inside_the_point_cloud(self) -> None:
        validate_crop_bounds(region(), DATASET)

    def test_accepts_a_region_that_only_partly_overlaps(self) -> None:
        validate_crop_bounds(region(minX=-50.0, maxX=10.0, maxZ=500.0), DATASET)

    def test_accepts_a_region_larger_than_the_point_cloud(self) -> None:
        validate_crop_bounds(
            region(minX=-1e6, minY=-1e6, minZ=-1e6, maxX=1e6, maxY=1e6, maxZ=1e6), DATASET
        )

    def test_accepts_a_zero_height_region(self) -> None:
        validate_crop_bounds(region(minZ=15.0, maxZ=15.0), DATASET)

    def test_rejects_min_greater_than_max_on_any_axis(self) -> None:
        for axis in ("X", "Y", "Z"):
            with self.subTest(axis=axis):
                bounds = region()
                bounds[f"min{axis}"], bounds[f"max{axis}"] = (
                    bounds[f"max{axis}"],
                    bounds[f"min{axis}"],
                )
                with self.assertRaisesRegex(CropBoundsError, f"min{axis}"):
                    validate_crop_bounds(bounds, DATASET)

    def test_rejects_a_region_without_area(self) -> None:
        for overrides in ({"maxX": 10.0}, {"maxY": 10.0}, {"maxX": 10.0, "maxY": 10.0}):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(CropBoundsError, "no area"):
                    validate_crop_bounds(region(**overrides), DATASET)

    def test_rejects_a_region_outside_the_point_cloud(self) -> None:
        for overrides in (
            {"minX": 200.0, "maxX": 300.0},
            {"minY": -40.0, "maxY": -30.0},
            {"minZ": 30.0, "maxZ": 40.0},
            {"minZ": 0.0, "maxZ": 5.0},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(CropBoundsError, "does not overlap"):
                    validate_crop_bounds(region(**overrides), DATASET)

    def test_touching_only_an_edge_is_not_an_overlap(self) -> None:
        with self.assertRaisesRegex(CropBoundsError, "does not overlap"):
            validate_crop_bounds(region(minX=100.0, maxX=150.0), DATASET)

    def test_touching_the_top_of_the_z_range_still_overlaps(self) -> None:
        validate_crop_bounds(region(minZ=20.0, maxZ=25.0), DATASET)


if __name__ == "__main__":
    unittest.main()
