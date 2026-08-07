"""The build pipeline CLI: turn warming-level Zarr into map GeoJSON.

    hires-maps build days-above-35c                      # native 0.1°
    hires-maps build days-above-35c --factor 2           # a single coarse rung (0.2°)
    hires-maps pyramid days-above-35c                    # native + p02 + p08
    hires-maps build days-above-35c --limit 5000         # quick smoke test
    hires-maps build days-above-35c --write-db           # also exercise the (OFF) DB writer
    hires-maps build-all [--pyramid]                     # all 26 indicators
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import stores
from .db import StatWriter
from .geojson import build as build_geojson
from .indicators import get

app = typer.Typer(
    add_completion=False,
    help="Build Probable Futures map data (GeoJSON) from the warming-level Zarr data.",
)

# The resolution pyramid we publish (docs §8): native 0.1° + coarser rungs for low zoom.
#   factor 1 -> 0.1° (z4-5), 2 -> 0.2° (z2-3), 8 -> 0.8° (z0-1)
# There is deliberately NO 0.4° rung: a tileset pinned to minzoom 1 / maxzoom 1 fails Mapbox's
# post-publish metadata check ("center zoom value must be greater than or equal to minzoom 1"),
# so the coarsest rung starts at zoom 0 and covers z0-1 instead. At z1 a 0.8° cell is ~2px, so
# nothing visible is lost. `--factor 4` still works if you ever want to build 0.4° by hand.
PYRAMID_FACTORS = (1, 2, 8)


def _run(slug: str, out: Path | None, factor: int, limit: int | None, write_db: bool) -> None:
    ind = get(slug)
    if ind is None:
        typer.echo(f"skip '{slug}' — not in the indicator registry")
        return
    # The DB is fed only from the native rung; coarse rungs are tile-only.
    writer = StatWriter(ind) if (write_db and factor == 1) else None
    hook = writer.on_feature if writer else None
    path, n = build_geojson(slug, out, factor=factor, limit=limit, on_feature=hook)
    typer.echo(f"{slug} (0.{factor}°): wrote {n:,} features -> {path.name}")
    if writer:
        writer.flush()
        typer.echo("  " + writer.report())


# example usage:
# $ hires-maps build days-above-35c --factor 2
@app.command()
def build(
    slug: str = typer.Argument(..., help="indicator slug, e.g. days-above-35c"),
    factor: int = typer.Option(1, help="rung: 1=0.1° 2=0.2° 8=0.8° (4=0.4° unused)"),
    out: Path | None = typer.Option(None, help="output .geojsonld path"),
    limit: int | None = typer.Option(None, help="only emit the first N features (smoke test)"),
    write_db: bool = typer.Option(
        False, "--write-db/--no-write-db", help="also run the DB writer (OFF: counts only)"
    ),
) -> None:
    """Build one indicator's GeoJSON at a single resolution rung."""
    if get(slug) is None:
        raise typer.BadParameter(f"unknown indicator '{slug}'")
    _run(slug, out, factor, limit, write_db)


# example usage:
# $ hires-maps pyramid days-above-35c
@app.command()
def pyramid(
    slug: str = typer.Argument(..., help="indicator slug, e.g. days-above-35c"),
    write_db: bool = typer.Option(False, "--write-db/--no-write-db"),
) -> None:
    """Build the resolution pyramid we publish for one indicator (native + p02 + p08)."""
    if get(slug) is None:
        raise typer.BadParameter(f"unknown indicator '{slug}'")
    for f in PYRAMID_FACTORS:
        _run(slug, None, f, None, write_db)


# example usage:
# $ hires-maps build-all --pyramid
@app.command("build-all")
def build_all(
    with_pyramid: bool = typer.Option(False, "--pyramid", help="build all rungs, not just native"),
    limit: int | None = typer.Option(None, help="per-indicator feature cap (smoke test)"),
    write_db: bool = typer.Option(False, "--write-db/--no-write-db"),
) -> None:
    """Build every indicator found on disk (native only, or the full pyramid with --pyramid)."""
    slugs = stores.list_on_disk()
    factors = PYRAMID_FACTORS if with_pyramid else (1,)
    typer.echo(f"building {len(slugs)} indicators × {len(factors)} rung(s)…")
    for slug in slugs:
        for f in factors:
            _run(slug, None, f, limit, write_db)


if __name__ == "__main__":
    app()
