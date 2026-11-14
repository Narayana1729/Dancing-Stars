import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.main import app
from app.services.aoi import InvalidAOI, area_km2, coverage_fraction, parse_aoi
from app.services.discovery import _as_list, _latest_crid_only, _pick_h5

client = TestClient(app)


# ---------- AOI ----------
def test_parse_aoi_bbox_wkt_geojson_equivalent():
    b = parse_aoi(bbox=[78, 18, 79, 19])
    w = parse_aoi(wkt="POLYGON((78 18, 79 18, 79 19, 78 19, 78 18))")
    g = parse_aoi(geometry={"type": "Polygon", "coordinates": [[[78, 18], [79, 18], [79, 19], [78, 19], [78, 18]]]})
    assert b.equals(w) and w.equals(g)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bbox": [79, 18, 78, 19]},  # west > east
        {"wkt": "POINT(78 18)"},  # not a polygon
        {"wkt": "not wkt"},
        {"bbox": [7512718, 2170941, 7837008, 2540271]},  # projected metres, not degrees
    ],
)
def test_parse_aoi_rejects(kwargs):
    with pytest.raises(InvalidAOI):
        parse_aoi(**kwargs)


def test_area_and_coverage():
    aoi = box(78, 18, 79, 19)
    assert 11_000 < area_km2(aoi) < 12_500  # ~1°x1° near 18.5°N
    assert coverage_fraction(aoi, box(77, 17, 80, 20)) == 1.0
    assert coverage_fraction(aoi, box(78.5, 17, 80, 20)) == pytest.approx(0.5, abs=0.01)
    assert coverage_fraction(aoi, box(10, 10, 11, 11)) == 0.0


# ---------- URL / CRID helpers ----------
def test_pick_h5_skips_qa_stats():
    urls = ["https://x/a_QA_STATS.h5", "https://x/a.png", "https://x/a.h5"]
    assert _pick_h5(urls) == "https://x/a.h5"
    assert _as_list("['a', 'b']") == ["a", "b"]


class _P:
    def __init__(self, name):
        self.properties = {"sceneName": name}


def test_latest_crid_kept():
    base = "NISAR_L3_PR_SME2_031_156_A_011_4005_DHDH_A_20260929T000947_20260929T001022"
    old, new = _P(f"{base}_P05022_N_F_J_001"), _P(f"{base}_P05023_N_F_J_001")
    other = _P("NISAR_L3_PR_SME2_032_156_A_011_4005_DHDH_A_20261011T000948_20261011T001022_P05023_N_F_J_001")
    kept = _latest_crid_only([old, new, other])
    assert new in kept and other in kept and old not in kept


# ---------- API validation ----------
def test_api_requires_exactly_one_aoi():
    r = client.post("/api/v1/discovery/search", json={})
    assert r.status_code == 422
    r = client.post("/api/v1/discovery/search", json={"bbox": [78, 18, 79, 19], "wkt": "POLYGON((78 18, 79 18, 79 19, 78 18))"})
    assert r.status_code == 422


# ---------- Live (network + Earthdata) ----------
@pytest.mark.live
def test_live_search_known_region():
    r = client.post(
        "/api/v1/discovery/search",
        json={"bbox": [78.86, 18.27, 79.36, 18.77], "start_date": "2026-09-01", "end_date": "2026-10-31"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_observations"] > 0
    o = body["observations"][0]
    assert o["https_url"].endswith(".h5") and "QA_STATS" not in o["https_url"]
    assert body["tracks"][0]["n_observations"] >= 1
