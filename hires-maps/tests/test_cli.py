"""Tests for the command layer: which builds each command fans out to, and what it says when a
slug cannot be built.

The builders themselves are replaced with recorders — this is about argument plumbing and the
three "skip" paths, not about map values, which every other test module covers. `cli` holds module
references (`from . import geojson, livemaps, stores`), so patching the attribute on the module
patches what `cli` calls.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from hires_maps import cli, era5, geojson, livemaps, stores

runner = CliRunner()

# 40105 / 40101; the second has no live export in most tests below.
KNOWN = ["days-above-35c", "average-temperature"]


@pytest.fixture
def recorded(monkeypatch):
    """Swap the builders for recorders and return one call log per build family."""
    calls: dict[str, list[dict]] = {"build": [], "diff": [], "era5v3": []}

    def fake_build(slug, out=None, *, factor=1, limit=None, on_feature=None, **kw):
        calls["build"].append(
            {
                "slug": slug,
                "out": out,
                "factor": factor,
                "limit": limit,
                "db": on_feature is not None,
            }
        )
        return Path(f"{slug}-hires.geojsonld"), 7

    def fake_build_diff(slug, out=None, *, factor=1, limit=None, progress_every=250_000, **kw):
        calls["diff"].append({"slug": slug, "out": out, "factor": factor, "limit": limit})
        return Path(f"{slug}-diff.geojsonld"), 5, None

    def fake_build_era5_v3_diff(slug, out=None, *, limit=None, progress_every=250_000, **kw):
        calls["era5v3"].append({"slug": slug, "out": out, "limit": limit})
        return Path(f"{slug}-era5v3.geojsonld"), 3, None

    monkeypatch.setattr(geojson, "build", fake_build)
    monkeypatch.setattr(geojson, "build_diff", fake_build_diff)
    monkeypatch.setattr(geojson, "build_era5_v3_diff", fake_build_era5_v3_diff)
    monkeypatch.setattr(stores, "list_on_disk", lambda: list(KNOWN))
    monkeypatch.setattr(livemaps, "available", lambda: ["40105"])
    monkeypatch.setattr(era5, "available", lambda: list(KNOWN))
    return calls


def test_unknown_slug_is_a_usage_error_not_a_crash(recorded):
    for command in ("build", "pyramid", "diff", "diff-pyramid"):
        result = runner.invoke(cli.app, [command, "not-a-map"])
        assert result.exit_code == 2, command
        assert "unknown indicator 'not-a-map'" in result.output, command
    assert recorded["build"] == []
    assert recorded["diff"] == []


def test_build_passes_its_options_through(recorded):
    result = runner.invoke(cli.app, ["build", "days-above-35c", "--factor", "2", "--limit", "9"])
    assert result.exit_code == 0
    assert recorded["build"] == [
        {"slug": "days-above-35c", "out": None, "factor": 2, "limit": 9, "db": False}
    ]


def test_pyramid_builds_one_rung_per_pyramid_factor(recorded):
    result = runner.invoke(cli.app, ["pyramid", "days-above-35c"])
    assert result.exit_code == 0
    assert [c["factor"] for c in recorded["build"]] == list(cli.PYRAMID_FACTORS)
    assert {c["slug"] for c in recorded["build"]} == {"days-above-35c"}


def test_diff_pyramid_builds_one_rung_per_pyramid_factor(recorded):
    result = runner.invoke(cli.app, ["diff-pyramid", "days-above-35c"])
    assert result.exit_code == 0
    assert [c["factor"] for c in recorded["diff"]] == list(cli.PYRAMID_FACTORS)


def test_build_all_fans_out_over_indicators_and_rungs(recorded):
    result = runner.invoke(cli.app, ["build-all", "--pyramid"])
    assert result.exit_code == 0
    assert len(recorded["build"]) == len(KNOWN) * len(cli.PYRAMID_FACTORS)
    for slug in KNOWN:
        assert [c["factor"] for c in recorded["build"] if c["slug"] == slug] == list(
            cli.PYRAMID_FACTORS
        )


def test_build_all_without_pyramid_builds_only_the_native_rung(recorded):
    result = runner.invoke(cli.app, ["build-all"])
    assert result.exit_code == 0
    assert [c["factor"] for c in recorded["build"]] == [1] * len(KNOWN)


def test_build_all_reports_a_slug_that_is_not_in_the_registry(recorded, monkeypatch):
    monkeypatch.setattr(stores, "list_on_disk", lambda: [*KNOWN, "mystery-dataset"])
    result = runner.invoke(cli.app, ["build-all"])
    assert result.exit_code == 0
    assert "not in the indicator registry: mystery-dataset" in result.output
    assert "mystery-dataset" not in {c["slug"] for c in recorded["build"]}


def test_write_db_runs_the_writer_only_on_the_native_rung(recorded):
    result = runner.invoke(cli.app, ["pyramid", "days-above-35c", "--write-db"])
    assert result.exit_code == 0
    assert [c["db"] for c in recorded["build"]] == [True, False, False]
    assert result.output.count("[db writer OFF]") == 1


def test_write_db_is_off_by_default(recorded):
    runner.invoke(cli.app, ["build", "days-above-35c"])
    assert recorded["build"][0]["db"] is False


def test_diff_all_builds_only_indicators_with_a_live_export(recorded):
    result = runner.invoke(cli.app, ["diff-all"])
    assert result.exit_code == 0
    assert [c["slug"] for c in recorded["diff"]] == ["days-above-35c"]
    assert "no live export for: average-temperature" in result.output


def test_diff_all_calls_an_unregistered_slug_unregistered_not_missing_a_live_export(
    recorded, monkeypatch
):
    # The old single expression reported both cases as "no live export", which is a lie about a
    # slug the registry has never heard of — and sends the reader looking for the wrong file.
    monkeypatch.setattr(stores, "list_on_disk", lambda: [*KNOWN, "mystery-dataset"])
    result = runner.invoke(cli.app, ["diff-all"])
    assert result.exit_code == 0

    assert "not in the indicator registry: mystery-dataset" in result.output
    no_live_line = next(ln for ln in result.output.splitlines() if "no live export for" in ln)
    assert "mystery-dataset" not in no_live_line
    assert "average-temperature" in no_live_line


def test_diff_all_skips_an_indicator_whose_live_export_vanished(recorded, monkeypatch):
    def missing(slug, out=None, **kw):
        raise FileNotFoundError(f"no live export for dataset {slug}")

    monkeypatch.setattr(geojson, "build_diff", missing)
    result = runner.invoke(cli.app, ["diff-all"])
    assert result.exit_code == 0
    assert "skip 'days-above-35c'" in result.output


def test_live_maps_lists_the_exports_and_their_indicators(recorded):
    result = runner.invoke(cli.app, ["live-maps"])
    assert result.exit_code == 0
    assert "40105" in result.output
    assert "days-above-35c" in result.output


def test_live_maps_exits_non_zero_when_the_folder_is_empty(recorded, monkeypatch):
    monkeypatch.setattr(livemaps, "available", list)
    result = runner.invoke(cli.app, ["live-maps"])
    assert result.exit_code == 1
    assert "No live exports found" in result.output


def test_era5_diff_passes_its_options_through(recorded, tmp_path):
    out = tmp_path / "x.geojsonld"
    result = runner.invoke(
        cli.app, ["era5-diff", "days-above-35c", "--out", str(out), "--limit", "9"]
    )
    assert result.exit_code == 0
    assert recorded["era5v3"] == [{"slug": "days-above-35c", "out": out, "limit": 9}]


def test_era5_diff_all_builds_only_indicators_with_a_live_export(recorded):
    # 40202 in production, `average-temperature` here: an ERA5 file with no v3 export to compare
    # against. It must be named as a blocker rather than silently dropped.
    result = runner.invoke(cli.app, ["era5-diff-all"])
    assert result.exit_code == 0
    assert [c["slug"] for c in recorded["era5v3"]] == ["days-above-35c"]
    assert "no live export (blocked): 40101" in result.output


def test_era5_diff_all_names_a_slug_the_registry_does_not_know(recorded, monkeypatch):
    monkeypatch.setattr(era5, "available", lambda: [*KNOWN, "some-new-era5-file"])
    result = runner.invoke(cli.app, ["era5-diff-all"])
    assert result.exit_code == 0
    assert "not in the indicator registry: some-new-era5-file" in result.output


def test_era5_diff_unknown_slug_is_a_usage_error(recorded):
    result = runner.invoke(cli.app, ["era5-diff", "not-a-map"])
    assert result.exit_code == 2
    assert "unknown indicator 'not-a-map'" in result.output
    assert recorded["era5v3"] == []


@pytest.fixture
def recorded_v4(recorded, monkeypatch):
    """`recorded` plus a recorder for the v4 comparison builder."""
    recorded["era5v4"] = []

    def fake(slug, out=None, *, factor=1, limit=None, progress_every=250_000, **kw):
        recorded["era5v4"].append({"slug": slug, "out": out, "factor": factor, "limit": limit})
        return Path(f"{slug}-era5v4.geojsonld"), 4, None

    monkeypatch.setattr(geojson, "build_era5_v4_diff", fake)
    return recorded


def test_era5_diff_reference_v4_reaches_the_v4_builder(recorded_v4):
    result = runner.invoke(
        cli.app, ["era5-diff", "days-above-35c", "--reference", "v4", "--factor", "8"]
    )
    assert result.exit_code == 0
    assert recorded_v4["era5v4"] == [
        {"slug": "days-above-35c", "out": None, "factor": 8, "limit": None}
    ]
    assert recorded_v4["era5v3"] == []  # and did NOT run the v3 path


def test_era5_diff_v4_pyramid_builds_one_rung_per_factor(recorded_v4):
    result = runner.invoke(
        cli.app, ["era5-diff", "days-above-35c", "--reference", "v4", "--pyramid"]
    )
    assert result.exit_code == 0
    assert [c["factor"] for c in recorded_v4["era5v4"]] == list(cli.ERA5_V4_PYRAMID_FACTORS)


def test_rung_options_are_a_usage_error_under_reference_v3(recorded_v4):
    # v3 is a single rung, so silently ignoring --factor/--pyramid would build one file where
    # three were asked for -- only noticed at upload time.
    for extra in (["--factor", "8"], ["--pyramid"]):
        result = runner.invoke(cli.app, ["era5-diff", "days-above-35c", *extra])
        assert result.exit_code == 2, extra
        assert "single rung" in result.output, extra
    assert recorded_v4["era5v3"] == []
    assert recorded_v4["era5v4"] == []


def test_reference_rejects_an_unknown_value(recorded_v4):
    result = runner.invoke(cli.app, ["era5-diff", "days-above-35c", "--reference", "v5"])
    assert result.exit_code == 2
    assert recorded_v4["era5v3"] == []
    assert recorded_v4["era5v4"] == []


def test_era5_diff_all_v4_gates_on_the_store_not_the_live_export(recorded_v4, monkeypatch):
    # The v3 set and the v4 set are genuinely different. `average-temperature` has no live export
    # here (the 40202 analogue) but does have a store, so the v4 run MUST include it -- gating on
    # live exports would skip exactly the ids this family exists to unlock.
    monkeypatch.setattr(stores, "list_on_disk", lambda: list(KNOWN))
    monkeypatch.setattr(era5, "available", lambda: [*KNOWN, "no-store-here"])
    result = runner.invoke(cli.app, ["era5-diff-all", "--reference", "v4"])
    assert result.exit_code == 0
    assert sorted(c["slug"] for c in recorded_v4["era5v4"]) == sorted(KNOWN)
    assert "not in the indicator registry: no-store-here" in result.output
    assert "no live export" not in result.output  # that is the v3 wording


def test_era5_diff_all_v4_names_a_slug_with_no_store(recorded_v4, monkeypatch):
    # `dry-hot-days` in production: an ERA5 file and a live export, but no downscaled store.
    monkeypatch.setattr(stores, "list_on_disk", lambda: ["days-above-35c"])
    result = runner.invoke(cli.app, ["era5-diff-all", "--reference", "v4"])
    assert result.exit_code == 0
    assert [c["slug"] for c in recorded_v4["era5v4"]] == ["days-above-35c"]
    assert "no v4 store (blocked): 40101" in result.output
