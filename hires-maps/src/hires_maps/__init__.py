"""hires-maps — build Probable Futures map data from the new downscaled warming-level Zarr data.

Pipeline (see docs/warming-levels-data-and-next-steps.md):
    Zarr (warming levels) -> GeoJSON (.geojsonld) -> Mapbox tileset/style

This package is the build pipeline. The `dev/` subpackage holds throwaway inspection tools.
"""

__version__ = "0.1.0"
