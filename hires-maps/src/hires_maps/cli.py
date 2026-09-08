"""The build pipeline CLI: turn warming-level Zarr into map GeoJSON.

`build` / `pyramid` / `build-all` write the new data itself; `diff` / `diff-pyramid` / `diff-all`
write comparison maps against the currently-live exports. The `era5-*` commands cover the
observations: `era5-map*` publishes ERA5 as a map in its own right, and `era5-diff*` compares the
live v3 data against it. Run `hires-maps --help` for the full command list — each one carries its
own help text and options.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import era5, geojson, livemaps, stores
from .config import ERA5_STEP_DEG
from .db import StatWriter
from .indicators import INDICATORS, Indicator, get

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

# The same three zoom bands for ERA5, whose native grid is 0.25° rather than 0.1°:
#   factor 1 -> 0.25° (z2-5), 2 -> 0.5° (unused for now), 4 -> 1.0° (z0-1)
# The native rung stretches down to z2 because there is no finer rung above it to cover z4-5.
ERA5_PYRAMID_FACTORS = (1, 2, 4)


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


def _change_indicators() -> list[Indicator]:
    """The indicators published as a change, in dataset-id order. The absolute republishes exist
    only for these; everything else is already absolute."""
    return sorted((i for i in INDICATORS.values() if i.is_change), key=lambda i: i.live_id)


@app.command("absolute")
def absolute(
    slug: str = typer.Argument(..., help="a change indicator, e.g. total-annual-precipitation"),
    factor: int = typer.Option(1, help="rung: 1=0.1° 2=0.2° 8=0.8°"),
    out: Path | None = typer.Option(None, help="output .geojsonld path"),
    limit: int | None = typer.Option(None, help="only emit the first N features (smoke test)"),
) -> None:
    """Build one v4 change map as an ABSOLUTE map (`{id}-abs`), for comparison against ERA5."""
    ind = _resolve(slug)
    path, n = geojson.build(ind.slug, out, factor=factor, limit=limit, absolute=True)
    typer.echo(f"{ind.slug} abs (0.{factor}°): wrote {n:,} features -> {path.name}")


@app.command("absolute-pyramid")
def absolute_pyramid(
    slug: str = typer.Argument(..., help="a change indicator, e.g. total-annual-precipitation"),
) -> None:
    """Build the absolute v4 map at every rung we publish (native + p02 + p08)."""
    ind = _resolve(slug)
    for f in PYRAMID_FACTORS:
        path, n = geojson.build(ind.slug, None, factor=f, absolute=True)
        typer.echo(f"{ind.slug} abs (0.{f}°): wrote {n:,} features -> {path.name}")


@app.command("v3-absolute")
def v3_absolute(
    slug: str = typer.Argument(..., help="a change indicator, e.g. total-annual-precipitation"),
    out: Path | None = typer.Option(None, help="output .geojsonld path"),
    limit: int | None = typer.Option(None, help="only emit the first N features (smoke test)"),
) -> None:
    """Rebuild one currently-live change map as an ABSOLUTE map (`{id}-v3abs`), on the 0.2° grid.

    Reads the live export and adds its absolute baseline back to every level. One rung, no pyramid.
    """
    ind = _resolve(slug)
    try:
        path, n, _ = geojson.build_v3_absolute(ind.slug, out, limit=limit)
    except FileNotFoundError as exc:
        typer.echo(f"skip '{ind.slug}' — {exc}")
        return
    typer.echo(f"{ind.slug} v3abs (0.2°): wrote {n:,} features -> {path.name}")


@app.command("absolute-coverage")
def absolute_coverage() -> None:
    """Every change indicator, and what each needs for an absolute republish."""
    live_ids = set(livemaps.available())
    on_disk = set(stores.list_on_disk())
    typer.echo("")
    typer.echo(f"  {'indicator':28s} {'id':6s} {'v3 export':10s} {'v4 store':9s}")
    for ind in _change_indicators():
        mark = {True: "yes", False: "—"}
        typer.echo(
            f"  {ind.slug:28s} {ind.live_id:6s} "
            f"{mark[ind.live_id in live_ids]:10s} {mark[ind.slug in on_disk]:9s}"
        )
    typer.echo("")
    typer.echo("  v3 export -> `v3-absolute` can run;  v4 store -> `absolute` can run.")
    typer.echo("")


def _era5_one(ind: Indicator, out: Path | None, factor: int, limit: int | None) -> None:
    """One standalone ERA5 build. Skipped if the ERA5 file it needs is not on disk."""
    try:
        path, n, _ = geojson.build_era5_map(ind.slug, out, factor=factor, limit=limit)
    except FileNotFoundError as exc:
        typer.echo(f"skip '{ind.slug}' — {exc}")
        return
    typer.echo(f"{ind.slug} era5 ({ERA5_STEP_DEG * factor}°): wrote {n:,} features -> {path.name}")


@app.command("era5-map")
def era5_map(
    slug: str = typer.Argument(..., help="indicator slug, e.g. days-above-35c"),
    factor: int = typer.Option(1, help="rung: 1=0.25° 2=0.5° 4=1.0°"),
    out: Path | None = typer.Option(None, help="output .geojsonld path"),
    limit: int | None = typer.Option(None, help="only emit the first N features (smoke test)"),
) -> None:
    """Build one indicator's standalone ERA5 map at a single resolution rung."""
    _era5_one(_resolve(slug), out, factor, limit)


@app.command("era5-map-pyramid")
def era5_map_pyramid(
    slug: str = typer.Argument(..., help="indicator slug, e.g. days-above-35c"),
) -> None:
    """Build the standalone ERA5 map at every rung we publish (0.25° + 0.5° + 1.0°)."""
    ind = _resolve(slug)
    for f in ERA5_PYRAMID_FACTORS:
        _era5_one(ind, None, f, None)


@app.command("era5-map-all")
def era5_map_all(
    with_pyramid: bool = typer.Option(False, "--pyramid", help="build all rungs, not just native"),
    limit: int | None = typer.Option(None, help="per-indicator feature cap (smoke test)"),
) -> None:
    """Build a standalone ERA5 map for every indicator with an ERA5 file on disk."""
    factors = ERA5_PYRAMID_FACTORS if with_pyramid else (1,)
    slugs = era5.available()
    known = [s for s in slugs if get(s) is not None]
    unregistered = [s for s in slugs if get(s) is None]
    typer.echo(f"building {len(known)} ERA5 maps × {len(factors)} rung(s)…")
    if unregistered:
        typer.echo(f"  not in the indicator registry: {', '.join(unregistered)}")
    for slug in known:
        for f in factors:
            _era5_one(get(slug), None, f, limit)


def _era5_diff_one(ind: Indicator, out: Path | None, limit: int | None) -> None:
    """One ERA5-vs-v3 build. Skipped if either half — the ERA5 file or the live export — is
    missing, naming which one, so `era5-diff-all` reports its blockers instead of failing."""
    try:
        path, n, _ = geojson.build_era5_v3_diff(ind.slug, out, limit=limit)
    except FileNotFoundError as exc:
        typer.echo(f"skip '{ind.slug}' — {exc}")
        return
    typer.echo(f"{ind.slug} era5v3 (0.2°): wrote {n:,} features -> {path.name}")


@app.command("era5-diff")
def era5_diff(
    slug: str = typer.Argument(..., help="indicator slug, e.g. days-above-35c"),
    out: Path | None = typer.Option(None, help="output .geojsonld path"),
    limit: int | None = typer.Option(None, help="only emit the first N features (smoke test)"),
) -> None:
    """Build one indicator's ERA5 comparison map: the LIVE v3 data minus the observations.

    Positive (red) means what we publish today reads higher than ERA5. One rung on the v3 0.2°
    grid, so there is no `--factor`. ERA5 covers everything v3 publishes (both stop short of
    Antarctica), so expect only a few hundred v3-only cells along coastlines.
    """
    _era5_diff_one(_resolve(slug), out, limit)


@app.command("era5-diff-all")
def era5_diff_all(
    limit: int | None = typer.Option(None, help="per-indicator feature cap (smoke test)"),
) -> None:
    """Build ERA5 comparison maps for every indicator with both an ERA5 file and a live export."""
    live_ids = set(livemaps.available())
    slugs = [s for s in era5.available() if get(s) is not None]
    buildable = [ind for s in slugs if (ind := get(s)).live_id in live_ids]
    blocked = [ind.live_id for s in slugs if (ind := get(s)).live_id not in live_ids]
    unregistered = [s for s in era5.available() if get(s) is None]
    typer.echo(f"building {len(buildable)} ERA5-vs-v3 comparison maps…")
    if blocked:
        typer.echo(f"  no live export (blocked): {', '.join(sorted(blocked))}")
    if unregistered:
        typer.echo(f"  not in the indicator registry: {', '.join(unregistered)}")
    for ind in buildable:
        _era5_diff_one(ind, None, limit)


@app.command("era5-coverage")
def era5_coverage() -> None:
    """What the ERA5 files cover, and what blocks the rest.

    Three columns, because the three answers are different questions: an ERA5 map needs only the
    ERA5 file; an ERA5-vs-v3 comparison also needs a live export; an ERA5-vs-v4 comparison also
    needs a downscaled store.
    """
    slugs = era5.available()
    if not slugs:
        typer.echo(f"No ERA5 files found under {era5.ERA5_DIR}")
        raise typer.Exit(1)

    live_ids = set(livemaps.available())
    on_disk = set(stores.list_on_disk())
    counts = {"era5": 0, "v3": 0, "v4": 0}

    typer.echo(f"{len(slugs)} ERA5 files under {era5.ERA5_DIR}:\n")
    typer.echo(f"  {'indicator':32s} {'id':6s} {'era5':6s} {'vs v3':6s} {'vs v4':6s}")
    for slug in slugs:
        ind = get(slug)
        if ind is None:
            typer.echo(f"  {slug:32s} {'?':6s} not in the indicator registry")
            continue
        has_live = ind.live_id in live_ids
        has_store = slug in on_disk
        counts["era5"] += 1
        counts["v3"] += has_live
        counts["v4"] += has_store
        mark = {True: "yes", False: "—"}
        typer.echo(
            f"  {slug:32s} {ind.live_id:6s} {'yes':6s} {mark[has_live]:6s} {mark[has_store]:6s}"
        )

    typer.echo("")
    typer.echo(f"buildable: {counts['era5']} ERA5 maps, {counts['v3']} vs v3, {counts['v4']} vs v4")
    missing_live = [get(s).live_id for s in slugs if get(s) and get(s).live_id not in live_ids]
    missing_store = [s for s in slugs if get(s) and s not in on_disk]
    if missing_live:
        typer.echo(f"  no live export (blocks vs v3): {', '.join(sorted(missing_live))}")
    if missing_store:
        typer.echo(f"  no downscaled store (blocks vs v4): {', '.join(sorted(missing_store))}")
    typer.echo("")


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
