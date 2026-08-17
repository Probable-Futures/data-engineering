"""GeoJSON build stage: warming-level Zarr -> newline-delimited GeoJSON (.geojsonld)."""

from .builder import build
from .diff_builder import build_diff
from .output import Variant, output_path

__all__ = ["Variant", "build", "build_diff", "output_path"]
