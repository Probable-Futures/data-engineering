"""The build pipeline CLI: turn warming-level Zarr into map GeoJSON.

`build` / `pyramid` / `build-all` write the new data itself; `diff` / `diff-pyramid` / `diff-all`
write comparison maps against the currently-live exports. Run `hires-maps --help` for the full
command list — each one carries its own help text and options.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import geojson, livemaps, stores
from .db import StatWriter
from .indicators import Indicator, get

app = typer.Typer(
    add_completion=False,
    help="Build Probable Futures map data (GeoJSON) from the warming-level Zarr data.",
)

# The resolution pyramid we publish (see "The resolution pyramid" in
# docs/hi-res-map-pipeline.md): native 0.1° + coarser rungs for low zoom.
#   factor 1 -> 0.1° (z4-5), 2 -> 0.2° (z2-3), 8 -> 0.8° (z0-1)
# There is deliberately NO 0.4° rung: a tileset pinned to minzoom 1 / maxzoom 1 fails Mapbox's
# post-publish metadata check ("center zoom value must be greater than or equal to minzoom 1"),
# so the coarsest rung starts at zoom 0 and covers z0-1 instead. At z1 a 0.8° cell is ~2px, so
# nothing visible is lost. `--factor 4` still works if you ever want to build 0.4° by hand.
PYRAMID_FACTORS = (1, 2, 8)


def _resolve(slug: str) -> Indicator:
    """The registry entry for a slug typed on the command line, or a usage error naming it."""
    ind = get(slug)
    if ind is None:
        raise typer.BadParameter(f"unknown indicator '{slug}'")
    return ind


def _on_disk(live_ids: set[str] | None = None) -> tuple[list[Indicator], list[str], list[str]]:
    """One pass over the slugs on disk, split into what can be built and why the rest cannot.

    Returns (buildable, no_live, unregistered). Given `live_ids`, an indicator whose live export
    is missing goes to `no_live`; without it every registry entry is buildable. The two reasons
    are kept apart because they are not the same problem: a slug the registry has never heard of
    is not waiting on an export that was never going to exist.
    """
    buildable: list[Indicator] = []
    no_live: list[str] = []
    unregistered: list[str] = []
    for slug in stores.list_on_disk():
        ind = get(slug)
        if ind is None:
            unregistered.append(slug)
        elif live_ids is not None and ind.live_id not in live_ids:
            no_live.append(slug)
        else:
            buildable.append(ind)
    return buildable, no_live, unregistered


def _build_one(
    ind: Indicator, out: Path | None, factor: int, limit: int | None, write_db: bool
) -> None:
    # The DB is fed only from the native rung; coarse rungs are tile-only.
    writer = StatWriter(ind) if (write_db and factor == 1) else None
    hook = writer.on_feature if writer else None
    path, n = geojson.build(ind.slug, out, factor=factor, limit=limit, on_feature=hook)
    typer.echo(f"{ind.slug} (0.{factor}°): wrote {n:,} features -> {path.name}")
    if writer:
        writer.flush()
        typer.echo("  " + writer.report())


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
    _build_one(_resolve(slug), out, factor, limit, write_db)


@app.command()
def pyramid(
    slug: str = typer.Argument(..., help="indicator slug, e.g. days-above-35c"),
    write_db: bool = typer.Option(False, "--write-db/--no-write-db"),
) -> None:
    """Build the resolution pyramid we publish for one indicator (native + p02 + p08)."""
    ind = _resolve(slug)
    for f in PYRAMID_FACTORS:
        _build_one(ind, None, f, None, write_db)


@app.command("build-all")
def build_all(
    with_pyramid: bool = typer.Option(False, "--pyramid", help="build all rungs, not just native"),
    limit: int | None = typer.Option(None, help="per-indicator feature cap (smoke test)"),
    write_db: bool = typer.Option(False, "--write-db/--no-write-db"),
) -> None:
    """Build every indicator found on disk (native only, or the full pyramid with --pyramid)."""
    buildable, _, unregistered = _on_disk()
    factors = PYRAMID_FACTORS if with_pyramid else (1,)
    typer.echo(f"building {len(buildable)} indicators × {len(factors)} rung(s)…")
    if unregistered:
        typer.echo(f"  not in the indicator registry: {', '.join(unregistered)}")
    for ind in buildable:
        for f in factors:
            _build_one(ind, None, f, limit, write_db)


def _diff_one(ind: Indicator, out: Path | None, factor: int, limit: int | None) -> None:
    """One comparison build. Skipped if the live export it needs is not on disk."""
    try:
        path, n, _ = geojson.build_diff(ind.slug, out, factor=factor, limit=limit)
    except FileNotFoundError as exc:
        typer.echo(f"skip '{ind.slug}' — {exc}")
        return
    typer.echo(f"{ind.slug} diff (0.{factor}°): wrote {n:,} features -> {path.name}")


@app.command()
def diff(
    slug: str = typer.Argument(..., help="indicator slug, e.g. days-above-35c"),
    factor: int = typer.Option(1, help="rung: 1=0.1° 2=0.2° 8=0.8°"),
    out: Path | None = typer.Option(None, help="output .geojsonld path"),
    limit: int | None = typer.Option(None, help="only emit the first N features (smoke test)"),
) -> None:
    """Build one indicator's comparison map: the new data minus the currently-live map."""
    _diff_one(_resolve(slug), out, factor, limit)


@app.command("diff-pyramid")
def diff_pyramid(
    slug: str = typer.Argument(..., help="indicator slug, e.g. days-above-35c"),
) -> None:
    """Build the comparison map at every rung we publish (native + p02 + p08)."""
    ind = _resolve(slug)
    for f in PYRAMID_FACTORS:
        _diff_one(ind, None, f, None)


@app.command("diff-all")
def diff_all(
    with_pyramid: bool = typer.Option(False, "--pyramid", help="build all rungs, not just native"),
    limit: int | None = typer.Option(None, help="per-indicator feature cap (smoke test)"),
) -> None:
    """Build comparison maps for every indicator that has both new data and a live export."""
    factors = PYRAMID_FACTORS if with_pyramid else (1,)
    buildable, no_live, unregistered = _on_disk(set(livemaps.available()))
    typer.echo(f"building {len(buildable)} comparison maps × {len(factors)} rung(s)…")
    if no_live:
        typer.echo(f"  no live export for: {', '.join(no_live)}")
    if unregistered:
        typer.echo(f"  not in the indicator registry: {', '.join(unregistered)}")
    for ind in buildable:
        for f in factors:
            _diff_one(ind, None, f, limit)


@app.command("live-maps")
def list_live_maps() -> None:
    """List the live map exports on disk, and which indicators they pair with."""
    ids = livemaps.available()
    if not ids:
        typer.echo(f"No live exports found under {livemaps.LIVE_MAPS_DIR}")
        raise typer.Exit(1)
    by_live_id = {ind.live_id: slug for slug in stores.list_on_disk() if (ind := get(slug))}
    typer.echo(f"{len(ids)} live exports under {livemaps.LIVE_MAPS_DIR}:\n")
    for live_id in ids:
        slug = by_live_id.get(live_id)
        typer.echo(f"  {live_id:8s} {slug or '— no new data on disk'}")
    typer.echo("")


if __name__ == "__main__":
    app()
