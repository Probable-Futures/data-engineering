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

from hires_maps import cli, geojson, livemaps, stores

runner = CliRunner()

# 40105 / 40101; the second has no live export in most tests below.
KNOWN = ["days-above-35c", "average-temperature"]


@pytest.fixture
def recorded(monkeypatch):
    """Swap both builders for recorders and return the two call logs."""
    calls: dict[str, list[dict]] = {"build": [], "diff": []}

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

    monkeypatch.setattr(geojson, "build", fake_build)
    monkeypatch.setattr(geojson, "build_diff", fake_build_diff)
    monkeypatch.setattr(stores, "list_on_disk", lambda: list(KNOWN))
    monkeypatch.setattr(livemaps, "available", lambda: ["40105"])
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
