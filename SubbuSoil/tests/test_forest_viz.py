import json

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient

from app.main import app
from app.services import forest_analysis as F
from tests.test_forest_change import _pair

client = TestClient(app)
SUMMARY = {
    "forest_area_ha": 52118.8, "disturbed_ha": 226.3, "disturbed_share_of_forest": 0.0043,
    "n_regions": 172, "median_HV_change_db": -0.36, "median_HH_change_db": -0.51,
    "params": {"change_db": 3.0},
}
VALID = {
    "ndvi_dates": ["2026-09-27", "2026-10-27"], "ndvi_scene_cloud_pct": [1.65, 0.62],
    "min_region_ha": 1.0, "ndvi_drop_threshold": 0.1, "n_candidates": 7, "n_checked": 6,
    "n_confirmed_by_optics": 2, "unflagged_forest_drop_rate": 0.02, "candidate_drop_rate": 0.36,
    "regions": [],
}


def test_explanation_cites_the_measured_numbers():
    e = F.forest_explanation(SUMMARY, VALID)
    text = e["text"]
    assert "226 ha" in text and "172 patches" in text
    assert "2 of them show a vegetation drop" in text or "2 of them" in text
    assert "1.5%" not in text  # no invented figures
    assert "The other 4 checked patch(es)" in text
    assert "Caveats" in text


def test_explanation_without_validation_says_so():
    e = F.forest_explanation(SUMMARY, None)
    assert "could be checked" not in e["text"] and len(e["lines"]) >= 3


def test_explanation_when_nothing_checkable():
    v = dict(VALID, n_checked=0, n_confirmed_by_optics=0)
    assert "No candidate patch could be checked" in F.forest_explanation(SUMMARY, v)["text"]


def test_layer_png_and_overlay_from_a_stack(tmp_path, monkeypatch):
    d1, d2 = _pair()
    for ds in (d1, d2):
        ds["HH_db"] = (("y", "x"), 10 * np.log10(ds.HHHH.values), {"units": "dB"})
        ds["HV_db"] = (("y", "x"), 10 * np.log10(ds.HVHV.values), {"units": "dB"})
    stack = xr.concat([
        d1.assign_coords(time=np.datetime64("2026-08-21")).expand_dims("time"),
        d2.assign_coords(time=np.datetime64("2026-10-20")).expand_dims("time"),
    ], dim="time")
    stack.attrs.update({"epsg": 32643, "grid_spacing_x": 10.0, "grid_spacing_y": -10.0})
    run = tmp_path / "forest" / "runs" / "vizrun01"
    run.mkdir(parents=True)
    stack.to_netcdf(run / "stack.nc", engine="h5netcdf")
    (run / "report.json").write_text(json.dumps({"track_key": "A_113_009", "n_dates": 2,
                                                  "aoi_wkt": "POLYGON((0 0,1 0,1 1,0 0))"}), encoding="utf-8")
    monkeypatch.setattr("app.services.forest_analysis.get_settings",
                        lambda: type("S", (), {"data_dir": tmp_path})())
    monkeypatch.setattr("app.api.routes.forest.get_settings",
                        lambda: type("S", (), {"data_dir": tmp_path})())

    png = F.forest_layer_png("vizrun01", "hv_t1")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    ov = F.forest_overlay_bounds("vizrun01", "hv_t1")
    (s, w), (n, e) = ov["bounds"]
    assert s < n and w < e and ov["value_range"] == [-25.0, -5.0]

    r = client.get("/api/v1/forest/runs/vizrun01/layers/hh_t1.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/api/v1/forest/runs/vizrun01/layers/nonsense.png").status_code == 404
    assert client.get("/api/v1/forest/runs/..%2Fetc").status_code == 404


def test_api_listing_and_unknown_run(tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.routes.forest.get_settings",
                        lambda: type("S", (), {"data_dir": tmp_path})())
    assert client.get("/api/v1/forest/runs").json() == {"runs": []}
    assert client.get("/api/v1/forest/runs/doesnotexist").status_code == 404


def test_forest_page_served():
    r = client.get("/forest")
    assert r.status_code == 200 and "NISAR forest disturbance" in r.text
    assert ".innerHTML" not in r.text
