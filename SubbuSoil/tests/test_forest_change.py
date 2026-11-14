import json

import numpy as np
import pytest
import xarray as xr
from rasterio.transform import from_origin

from app.services import forest_analysis as F

EPSG = 32643
N = 60


def _scene(hh_lin, hv_lin, valid=None):
    shape = (N, N)
    valid = np.ones(shape, bool) if valid is None else valid
    return xr.Dataset(
        {
            "HHHH": (("y", "x"), np.where(valid, hh_lin, np.nan).astype("float32")),
            "HVHV": (("y", "x"), np.where(valid, hv_lin, np.nan).astype("float32")),
            "valid": (("y", "x"), valid.astype("uint8")),
        },
        coords={"x": 300000 + np.arange(N) * 10.0, "y": 1800000 - np.arange(N) * 10.0},
    )


def _pair(drop_hv_db=-6.0, drop_hh_db=-3.0, block=(20, 40)):
    """Forest at about -6 dB HH and -13 dB HV on date 1. On date 2 a block loses
    drop_hh_db of HH and drop_hv_db of HV. Everything else is unchanged."""
    hh1 = np.full((N, N), 10 ** (-0.6), "float32")
    hv1 = np.full((N, N), 10 ** (-1.3), "float32")
    hh2, hv2 = hh1.copy(), hv1.copy()
    a, b = block
    hh2[a:b, a:b] *= 10 ** (drop_hh_db / 10)
    hv2[a:b, a:b] *= 10 ** (drop_hv_db / 10)
    return _scene(hh1, hv1), _scene(hh2, hv2)


def test_change_flags_the_block_per_polarisation():
    d1, d2 = _pair()
    ch = F.change_arrays(d1, d2, F.ForestParams())
    assert ch["class_HV"][30, 30] == -1 and ch["class_HH"][30, 30] == -1
    assert ch["class_HV"][5, 5] == 0 and ch["class_HH"][5, 5] == 0          # unchanged area
    assert ch["delta_HV_db"][30, 30] == pytest.approx(-6.0, abs=0.05)
    assert ch["delta_HH_db"][30, 30] == pytest.approx(-3.0, abs=0.05)


def test_small_hh_change_is_not_flagged_but_hv_is():
    d1, d2 = _pair(drop_hv_db=-6.0, drop_hh_db=-1.0)  # HH only 1 dB: below the 3 dB threshold
    ch = F.change_arrays(d1, d2, F.ForestParams())
    assert ch["class_HV"][30, 30] == -1 and ch["class_HH"][30, 30] == 0


def test_invalid_pixels_are_not_compared():
    d1, d2 = _pair()
    valid2 = np.ones((N, N), bool)
    valid2[30, :] = False
    d2 = _scene(d2.HHHH.values, d2.HVHV.values, valid2)
    ch = F.change_arrays(d1, d2, F.ForestParams())
    assert not ch["compared"][30, 30] and ch["class_HV"][30, 30] == 0


def test_disturbance_region_and_forest_mask():
    d1, d2 = _pair()
    p = F.ForestParams(min_region_pixels=20)
    ch = F.change_arrays(d1, d2, p)
    tf = from_origin(300000, 1800000, 10, 10)
    forest = np.ones((N, N), bool)
    gdf, summ = F.disturbances(ch, forest, tf, EPSG, p)
    assert summ["n_regions"] == 1 and summ["disturbed_ha"] > 0
    assert gdf.iloc[0]["fraction_HH_also_dropped"] > 0.5  # HH dropped too in this block
    # the same change outside forest is not counted
    gdf0, summ0 = F.disturbances(ch, np.zeros((N, N), bool), tf, EPSG, p)
    assert summ0["n_regions"] == 0 and summ0["disturbed_ha"] == 0
    # a patch smaller than the minimum is dropped
    gdf_big, _ = F.disturbances(ch, forest, tf, EPSG, F.ForestParams(min_region_pixels=100000))
    assert len(gdf_big) == 0


def test_analyse_forest_writes_outputs(tmp_path, monkeypatch):
    d1, d2 = _pair()
    stack = xr.concat([
        d1.assign_coords(time=np.datetime64("2026-08-21")).expand_dims("time"),
        d2.assign_coords(time=np.datetime64("2026-10-20")).expand_dims("time"),
    ], dim="time")
    stack.attrs.update({"epsg": EPSG, "grid_spacing_x": 10.0, "grid_spacing_y": -10.0})
    run = tmp_path / "forest" / "runs" / "testforest"
    run.mkdir(parents=True)
    stack.to_netcdf(run / "stack.nc", engine="h5netcdf")
    (run / "report.json").write_text(json.dumps({"aoi_wkt": "POLYGON((0 0,1 0,1 1,0 0))"}), encoding="utf-8")
    monkeypatch.setattr("app.services.forest_analysis.get_settings",
                        lambda: type("S", (), {"data_dir": tmp_path})())
    forest_all = np.ones((N, N), bool)
    monkeypatch.setattr("app.services.forest_analysis.tree_cover_mask",
                        lambda *a, **k: (forest_all, ["N12E075"], []))

    s = F.analyse_forest("testforest")
    assert s["n_regions"] == 1 and s["dates"] == ["2026-08-21", "2026-10-20"]
    assert s["tree_tiles_used"] == ["N12E075"]
    out = run / "forest_change"
    assert (out / "delta_HH_db.tif").exists() and (out / "delta_HV_db.tif").exists()
    fc = json.loads((out / "disturbances.geojson").read_text(encoding="utf-8"))
    assert len(fc["features"]) == 1
    assert json.loads((out / "summary.json").read_text(encoding="utf-8"))["disturbed_ha"] > 0
