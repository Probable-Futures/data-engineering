"""Tests for locating `data/mapbox/mts`, the folder every default output path hangs off.

`Path(__file__).parents[3]` used to do this, which is only right for an editable install — from a
wheel that walk lands inside site-packages. The replacement searches upward for the tracked
`vector-tiles/` directory, from the installed file first and then from the working directory, so
these tests build fake trees and point `config.__file__` at them rather than asserting on the real
repo (where the search would always succeed on the first try and hide the rest).
"""

import importlib
import os

import pytest

from hires_maps import config


@pytest.fixture(autouse=True)
def restore_config():
    """Put the real module-level constants back, whatever a test did to the environment."""
    yield
    os.environ.pop(config.MTS_DIR_ENV, None)
    importlib.reload(config)


def _repo(tmp_path, name: str):
    """A tree that looks like a checkout: a root holding the tracked `vector-tiles/` marker."""
    root = tmp_path / name
    (root / "vector-tiles").mkdir(parents=True)
    return root


def _installed_at(monkeypatch, directory):
    """Pretend `config.py` lives in `directory` — an editable checkout, or site-packages."""
    directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "__file__", str(directory / "config.py"))


def test_env_override_wins_without_any_search(monkeypatch, tmp_path):
    monkeypatch.setenv(config.MTS_DIR_ENV, str(tmp_path / "somewhere" / "mts"))
    assert config._find_mts_dir() == tmp_path / "somewhere" / "mts"


def test_the_override_is_read_at_import_time(monkeypatch, tmp_path):
    monkeypatch.setenv(config.MTS_DIR_ENV, str(tmp_path / "mts"))
    reloaded = importlib.reload(config)
    assert reloaded.MTS_DIR == tmp_path / "mts"
    # The two derived folders follow it, so a redirected root redirects the whole package.
    assert reloaded.LIVE_MAPS_DIR == tmp_path / "mts" / "old-geojson"
    assert reloaded.DIFF_MAPS_DIR == tmp_path / "mts" / "diff-geojson"


def test_upward_search_finds_the_root_from_an_editable_install(monkeypatch, tmp_path):
    root = _repo(tmp_path, "data-engineering")
    _installed_at(monkeypatch, root / "hires-maps" / "src" / "hires_maps")
    monkeypatch.delenv(config.MTS_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    assert config._find_mts_dir() == root / "data" / "mapbox" / "mts"


def test_a_wheel_install_falls_back_to_the_working_directory(monkeypatch, tmp_path):
    # The case `parents[3]` got wrong: nothing above site-packages holds `vector-tiles/`, so the
    # search has to carry on from where the command was actually run.
    root = _repo(tmp_path, "checkout")
    _installed_at(monkeypatch, tmp_path / "venv" / "lib" / "python3.13" / "site-packages")
    monkeypatch.delenv(config.MTS_DIR_ENV, raising=False)
    monkeypatch.chdir(root / "vector-tiles")  # run from a subdirectory, not the root

    assert config._find_mts_dir() == root / "data" / "mapbox" / "mts"


def test_the_marker_is_vector_tiles_not_the_gitignored_output_folder(monkeypatch, tmp_path):
    # `data/mapbox` is gitignored, so it does not exist in a fresh clone and cannot be the marker.
    root = _repo(tmp_path, "fresh-clone")
    _installed_at(monkeypatch, root / "hires-maps" / "src" / "hires_maps")
    monkeypatch.delenv(config.MTS_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    found = config._find_mts_dir()
    assert found == root / "data" / "mapbox" / "mts"
    assert not found.exists()  # named, not required to be there yet


def test_import_never_raises_when_no_marker_is_found(monkeypatch, tmp_path):
    # `hires-maps --help` and every unit test import this module without touching disk, so a
    # failed search has to fall back rather than explode. The first *write* is what fails.
    _installed_at(monkeypatch, tmp_path / "nowhere")
    monkeypatch.delenv(config.MTS_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    found = config._find_mts_dir()
    assert found.is_absolute()
    assert found.parts[-3:] == ("data", "mapbox", "mts")


def test_reload_from_a_directory_with_no_marker_still_imports(monkeypatch, tmp_path):
    monkeypatch.delenv(config.MTS_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    reloaded = importlib.reload(config)  # must not raise
    assert reloaded.MTS_DIR.name == "mts"
