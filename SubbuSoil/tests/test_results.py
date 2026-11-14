import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import results as R
from app.services.analysis import analyse_run
from app.services.change import ChangeParams
from tests.test_analysis import make_stack

client = TestClient(app)
RUN = "abc123def456"


@pytest.fixture
def run_root(tmp_path, monkeypatch):
    settings = type("S", (), {"data_dir": tmp_path})()
    monkeypatch.setattr("app.services.analysis.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.results.get_settings", lambda: settings)
    run = tmp_path / "processed" / RUN
    run.mkdir(parents=True)
    make_stack().to_netcdf(run / "stack.nc", engine="h5netcdf")
    manifest = {
        "request": {"wkt": "POLYGON((0 0,1 0,1 1,0 0))"},
        "result": {
            "track_key": "A_156_011", "n_observations": 2,
            "aoi": {"wkt": "", "bounds": [0, 0, 1, 1], "area_km2": 1.0},
            "n_common_valid_pixels": 3597,
            "observations": [{"start_time": "2026-08-12T00:09:48+00:00"},
                             {"start_time": "2026-10-11T00:09:48+00:00"}],
        },
    }
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    analyse_run(RUN, ChangeParams())  # writes change/<pair>/ exactly as the pipeline does
    return tmp_path


def _pair(run_root):
    return R.list_runs()[0]["pairs"][0]


def test_list_and_detail(run_root):
    runs = R.list_runs()
    assert [r["run_id"] for r in runs] == [RUN]
    assert runs[0]["dates"] == ["2026-08-12", "2026-10-11"] and len(runs[0]["pairs"]) == 1
    d = R.run_detail(RUN)
    assert d["result"]["pairs"] == runs[0]["pairs"]
    assert d["request"]["wkt"].startswith("POLYGON")


def test_history_per_date(run_root):
    s = R.history(RUN)["series"]
    assert len(s) == 2
    assert s[0]["n_valid"] == 3600 and s[1]["n_valid"] == 3597  # 3 pixels invalid on date 2
    assert s[0]["mean_sm"] == pytest.approx(0.30, abs=1e-4)
    assert s[0]["valid_fraction"] == 1.0


def test_pair_detail_hides_local_paths(run_root):
    p = R.pair_detail(RUN, _pair(run_root))
    assert p["stats"]["n_compared"] == 3597
    assert "regions" not in p
    assert all(not Path(v).is_absolute() for v in p["files"].values())
    assert "delta.tif" in p["available_layers"]


def test_regions_and_overlay(run_root):
    fc = R.regions(RUN, _pair(run_root))
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 2
    ov = R.delta_bounds(RUN, _pair(run_root))
    (south, west), (north, east) = ov["bounds"]
    assert south < north and west < east
    assert 70 < west < 90 and 0 < south < 30  # lon/lat, not EASE metres
    assert ov["value_range"] == [-0.2, 0.2]


def test_png_is_valid(run_root):
    png = R.delta_png(RUN, _pair(run_root))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 200


def test_panels_png(run_root):
    png = R.panels_png(RUN, _pair(run_root))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000


def test_bad_or_unknown_ids_are_rejected(run_root):
    with pytest.raises(R.ResultNotFound):
        R.run_detail("../etc")
    with pytest.raises(R.ResultNotFound):
        R.run_detail("nope")
    with pytest.raises(R.ResultNotFound):
        R.pair_detail(RUN, "..")


def test_api_endpoints(run_root):
    pair = _pair(run_root)
    base = f"/api/v1/results/runs/{RUN}"
    assert client.get("/api/v1/results/runs").json()["runs"][0]["run_id"] == RUN
    for url in (base, f"{base}/history", f"{base}/pairs/{pair}", f"{base}/pairs/{pair}/regions",
                f"{base}/pairs/{pair}/overlay"):
        assert client.get(url).status_code == 200, url
    r = client.get(f"{base}/pairs/{pair}/delta.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/api/v1/results/runs/missing").status_code == 404
    assert client.get(f"{base}/pairs/missing").status_code == 404


def test_frontend_served(run_root):
    r = client.get("/app")
    assert r.status_code == 200 and "NISAR soil moisture change" in r.text
    assert "cdnjs.cloudflare.com" in r.text
    assert "insertAdjacentHTML" not in r.text and ".innerHTML" not in r.text  # DOM-only rendering
    redirect = client.get("/", follow_redirects=False)
    assert redirect.status_code in (302, 307) and redirect.headers["location"] == "/app"
