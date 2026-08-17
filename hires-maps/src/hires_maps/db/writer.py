"""Database writer — BUILT, but OFF until Phase 3.

Design (see "The database writer" in docs/hi-res-map-pipeline.md): the writer targets the SAME
tables the current pipeline uses (`pf_grid_coordinates` for cells, `pf_dataset_statistics`
for values), fed by the builder's `on_feature` hook so the GeoJSON stage and the DB stage
share one pass over the data.

Phase 1 does NOT persist anything. This class only *shapes and counts* the rows that would be
written, so we can exercise and test the write path without committing to the schema decisions
the 4×-bigger data forces (new grid, ~345M rows, partitioning, which stats to keep). Turning it
on — the actual COPY/insert — is the Phase 3 task, and is intentionally left as a single marked
gap below.
"""

from __future__ import annotations

from ..config import WARMING_LEVELS
from ..indicators import Indicator


class StatWriter:
    """Collects the rows a DB load would produce. Persists nothing in Phase 1."""

    def __init__(self, ind: Indicator):
        self.ind = ind
        self.coordinates = 0
        self.stat_rows = 0

    def on_feature(self, lon: float, lat: float, props: dict) -> None:
        """Called by the builder for each cell. One coordinate + one stat row per warming level
        (matching `pf_dataset_statistics` granularity)."""
        self.coordinates += 1
        self.stat_rows += len(WARMING_LEVELS)
        # PHASE 3: buffer a pf_grid_coordinates row (point + generated cell polygon) and one
        # pf_dataset_statistics row per warming level (low/mid/high), then bulk COPY on flush.

    def flush(self) -> None:
        """PHASE 3: perform the bulk load here. No-op in Phase 1."""

    def report(self) -> str:
        return (
            f"[db writer OFF] would load ~{self.coordinates:,} coordinates and "
            f"{self.stat_rows:,} statistic rows for dataset {self.ind.live_id} "
            f"— persistence deferred to Phase 3."
        )
