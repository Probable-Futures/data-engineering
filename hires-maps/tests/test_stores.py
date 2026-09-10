"""Tests for the two lookup layers that answer "what is on disk, and what is it called".

`stores` covers the new warming-level Zarr; `livemaps` covers the currently-live exports. Both
feed `diff-all`'s decision about which comparison maps it can build, so a silent empty list here
shows up as a build that quietly does nothing.
"""

from hires_maps import livemaps, stores
from hires_maps.config import STORE_SUFFIX


def test_var_name_derivation():
    assert stores.value_var("days-above-35c") == "days_above_35c"
    assert stores.value_var("average-water-balance") == "average_water_balance"


def test_store_path_is_the_slug_folder_holding_the_suffixed_zarr(monkeypatch, tmp_path):
    monkeypatch.setattr(stores, "WL_ROOT", tmp_path)
    path = stores.store_path("days-above-35c")
    assert path.parent == tmp_path / "days-above-35c"
    assert path.name == f"days-above-35c_{STORE_SUFFIX}"


def test_list_on_disk_returns_sorted_indicator_folders(monkeypatch, tmp_path):
    for name in ("wettest-day", "days-above-35c", "average-temperature"):
        (tmp_path / name).mkdir()
    (tmp_path / "notes.txt").touch()  # a file, not an indicator
    (tmp_path / ".DS_Store").mkdir()  # a dotted folder, not an indicator
    monkeypatch.setattr(stores, "WL_ROOT", tmp_path)

    assert stores.list_on_disk() == ["average-temperature", "days-above-35c", "wettest-day"]


def test_list_on_disk_is_empty_rather_than_an_error_when_the_data_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(stores, "WL_ROOT", tmp_path / "never-downloaded")
    assert stores.list_on_disk() == []


def test_live_path_names_the_export_after_its_dataset_id(monkeypatch, tmp_path):
    monkeypatch.setattr(livemaps, "LIVE_MAPS_DIR", tmp_path)
    assert livemaps.live_path("40105") == tmp_path / "40105.geojsonld"


def test_available_lists_the_ids_of_the_exports_on_disk(monkeypatch, tmp_path):
    for name in ("40601.geojsonld", "40105.geojsonld", "README.md"):
        (tmp_path / name).touch()
    monkeypatch.setattr(livemaps, "LIVE_MAPS_DIR", tmp_path)

    assert livemaps.available() == ["40105", "40601"]


def test_available_is_empty_rather_than_an_error_when_the_folder_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(livemaps, "LIVE_MAPS_DIR", tmp_path / "no-such-folder")
    assert livemaps.available() == []
