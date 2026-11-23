from __future__ import annotations

from collections.abc import Mapping

from app.services.las_metadata import LasBounds

AXES = ("X", "Y", "Z")


class CropBoundsError(ValueError):
    """The requested crop region cannot be used; the message is safe to show."""


def validate_crop_bounds(bounds: Mapping[str, float], dataset: LasBounds) -> None:
    """Check a crop region against the point cloud it is cut from.

    The same rules as the viewer (frontend `cropBounds.ts`): min may not exceed
    max, a region needs an area in X and Y (a zero height is allowed, so a flat
    dataset can be cropped), and it must overlap the point cloud. Touching only
    an edge is not an overlap. Partial overlap is fine: the crop keeps what is
    inside.
    """
    for axis in AXES:
        if bounds[f"min{axis}"] > bounds[f"max{axis}"]:
            raise CropBoundsError(f"min{axis} must not be greater than max{axis}")
    if bounds["maxX"] <= bounds["minX"] or bounds["maxY"] <= bounds["minY"]:
        raise CropBoundsError("The region has no area")

    overlap = {
        axis: (
            max(bounds[f"min{axis}"], getattr(dataset, f"min{axis}")),
            min(bounds[f"max{axis}"], getattr(dataset, f"max{axis}")),
        )
        for axis in AXES
    }
    no_area = any(high <= low for axis, (low, high) in overlap.items() if axis != "Z")
    if no_area or overlap["Z"][1] < overlap["Z"][0]:
        raise CropBoundsError("The region does not overlap the point cloud")
