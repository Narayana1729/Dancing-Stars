from datetime import date, datetime, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.main import app
from app.services.change import ChangeParams, detect_change
from app.services.context import integrate
from app.services.context.integrate import ContextParams, pair_context
from app.services.context.soil import texture_class
from app.services.context.vegetation import _scale_offset
from app.services.context.weather import point_metrics, sample_points
from app.services.explain import explain_pair
from app.services.spatial import find_regions
from tests.test_analysis import make_stack

client = TestClient(app)
T1, T2 = datetime(2026, 8, 12, 0, 9), datetime(2026, 10, 11, 0, 9)


# ---------------------------------------------------------------- weather
def _openmeteo(rain_fn, sm_t1=0.30, sm_t2=0.20, lat=18.5, lon=79.1):
    start = date(2026, 7, 8)
    days = [(start + timedelta(days=i)).isoformat() for i in range((T2.date() - start).days + 1)]
    hours = [f"{d}T{h:02d}:00" for d in days for h in range(24)]
    sm = [0.25] * len(hours)
    sm[hours.index("2026-08-12T00:00")] = sm_t1
    sm[hours.index("2026-10-11T00:00")] = sm_t2
    return {
        "latitude": lat, "longitude": lon,
        "daily": {"time": days, "precipitation_sum": [rain_fn(date.fromisoformat(d)) for d in days],
                  "temperature_2m_mean": [27.0] * len(days), "temperature_2m_max": [31.0] * len(days),
                  "et0_fao_evapotranspiration": [4.0] * len(days)},
        "hourly": {"time": hours, "soil_moisture_0_to_7cm": sm},
    }


def test_point_metrics_windows():
    # 10 mm/day only during Aug 5-11 (the 7 days before t1)
    p = _openmeteo(lambda d: 10.0 if date(2026, 8, 5) <= d <= date(2026, 8, 11) else 0.0)
    m = point_metrics(p, T1, T2, antecedent_days=7)
    assert m["rain_7d_before_t1_mm"] == 70.0
    assert m["rain_7d_before_t2_mm"] == 0.0
    assert m["rain_between_mm"] == 0.0           # Aug 12 .. Oct 10
    assert m["days_since_rain_ge5mm_t1"] == 1
    assert m["et0_7d_before_t2_mm"] == 28.0
    assert m["era5_sm_delta"] == pytest.approx(-0.10)
    assert m["water_balance_between_mm"] == pytest.approx(-4.0 * 60)


def test_sample_points_inside_aoi():
    aoi = box(78.9, 18.3, 79.3, 18.7)
    pts = sample_points(aoi, 0.1)
    assert 10 <= len(pts) <= 30
    assert all(78.85 <= lo <= 79.35 and 18.25 <= la <= 18.75 for la, lo in pts)
    assert len(sample_points(box(79, 18, 79.01, 18.01), 0.1)) == 1  # tiny AOI -> centroid


# ---------------------------------------------------------------- vegetation / soil
class _Asset:
    def __init__(self, offset):
        self.extra_fields = {"raster:bands": [{"scale": 0.0001, "offset": offset}]}


class _Item:
    def __init__(self, applied):
        self.assets = {"red": _Asset(-0.1)}
        self.properties = {"earthsearch:boa_offset_applied": applied}


def test_boa_offset_not_applied_twice():
    assert _scale_offset(_Item(True), "red") == (0.0001, 0.0)
    assert _scale_offset(_Item(False), "red") == (0.0001, -0.1)
    # realistic vegetation pixel: DN red 533, nir 3419 -> NDVI ~0.73 (not ~1)
    s, o = _scale_offset(_Item(True), "red")
    red, nir = 533 * s + o, 3419 * s + o
    assert (nir - red) / (nir + red) == pytest.approx(0.73, abs=0.01)


@pytest.mark.parametrize("sand,clay,expected", [
    (29, 38, "clay loam"), (90, 5, "sand"), (40, 20, "loam"), (10, 50, "silty clay"), (65, 10, "sandy loam"),
])
def test_texture_class(sand, clay, expected):
    assert texture_class(sand, clay) == expected


# ---------------------------------------------------------------- integration (sources mocked)
@pytest.fixture
def pair(tmp_path):
    stack = make_stack()
    change, stats = detect_change(stack, 0, 1, ChangeParams())
    gdf, summ, ids = find_regions(change, stack.attrs["aoi_wkt"], ChangeParams())
    return tmp_path, stack, change, stats, gdf, summ, ids


def test_pair_context_with_mocked_sources(pair, monkeypatch):
    tmp, stack, change, stats, gdf, summ, ids = pair
    shape = change.delta.shape
    # NDVI rises exactly where soil moisture rises -> strong positive correlation
    ndvi1 = np.full(shape, 0.5, "float32")
    ndvi2 = (0.5 + change.delta.fillna(0).values * 2).astype("float32")
    monkeypatch.setattr(integrate, "ndvi_on_grid", lambda aoi, t, *a, **k: (
        ndvi1 if t.month == 8 else ndvi2, {"date": t.date().isoformat(), "days_from_nisar": 0, "tiles": [],
                                          "scene_cloud_cover_pct": 0, "aoi_coverage": 1, "masked_pixels": 0}))
    sand = np.full(shape, 30.0, "float32")
    sand[:, :30] = 60.0  # sandier west
    monkeypatch.setattr(integrate, "soil_on_grid", lambda *a: {
        "sand": sand, "clay": np.full(shape, 30.0, "float32"),
        "silt": np.full(shape, 40.0, "float32"), "soc": np.full(shape, 10.0, "float32")})
    monkeypatch.setattr(integrate, "weather_context", lambda *a, **k: {
        "aoi_mean": {"rain_7d_before_t1_mm": 5.0}, "points": [{"lat": 18.4, "lon": 79.0, "rain_7d_before_t1_mm": 5.0}],
        "n_points": 1})

    out_dir = tmp / "out"
    out_dir.mkdir()
    ctx = pair_context(tmp, change, ids, gdf, stack.attrs["aoi_wkt"], ContextParams(), out_dir)
    assert ctx["weather"]["available"] and ctx["vegetation"]["available"] and ctx["soil"]["available"]
    assert ctx["vegetation"]["corr_sm_delta_vs_ndvi_delta"]["rho"] > 0.5
    assert ctx["soil"]["texture_class"] is not None
    assert len(ctx["regions"]) == len(gdf)
    r1 = next(r for r in ctx["regions"] if r["region_id"] == int(gdf.iloc[0].region_id))
    assert r1["ndvi_delta"] == pytest.approx(-0.30, abs=0.01)  # strong drying block: 2 x -0.15
    assert r1["soil_sand"] == pytest.approx(60.0)              # it sits in the sandy west
    assert (out_dir / "context.nc").exists() and (out_dir / "ndvi_delta.tif").exists()
    # cached second call does not hit the sources
    monkeypatch.setattr(integrate, "ndvi_on_grid", lambda *a, **k: (_ for _ in ()).throw(AssertionError("not cached")))
    monkeypatch.setattr(integrate, "soil_on_grid", lambda *a: (_ for _ in ()).throw(AssertionError("not cached")))
    pair_context(tmp, change, ids, gdf, stack.attrs["aoi_wkt"], ContextParams(), None)


def test_pair_context_source_failure_is_isolated(pair, monkeypatch):
    tmp, stack, change, stats, gdf, summ, ids = pair
    monkeypatch.setattr(integrate, "weather_context", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    ctx = pair_context(tmp, change, ids, gdf, stack.attrs["aoi_wkt"],
                       ContextParams(include_vegetation=False, include_soil=False))
    assert ctx["weather"] == {"available": False, "error": "RuntimeError: down"}
    assert ctx["vegetation"]["error"] == "disabled"


# ---------------------------------------------------------------- explanation engine
def _stats(crop_delta, natural_delta, mean_delta, wet=600.0, dry=50.0):
    total = 1500.0
    return {
        "t1": T1.isoformat(), "t2": T2.isoformat(), "days": 60.0,
        "compared_area_km2": total, "compared_fraction": 0.72,
        "mean_sm_t1": 0.24, "mean_sm_t2": 0.24 + mean_delta,
        "delta": {"mean": mean_delta, "median": mean_delta, "p5": -0.07, "p95": 0.18, "std": 0.05,
                  "min": -0.3, "max": 0.3, "p25": 0, "p75": 0.1},
        "median_combined_uncertainty": 0.047,
        "classes": [
            {"class_id": 1, "name": "strong_drying", "area_km2": dry / 2, "n_pixels": 1, "pct_of_compared": 0},
            {"class_id": 2, "name": "drying", "area_km2": dry / 2, "n_pixels": 1, "pct_of_compared": 0},
            {"class_id": 3, "name": "no_significant_change", "area_km2": total - wet - dry, "n_pixels": 1, "pct_of_compared": 0},
            {"class_id": 4, "name": "wetting", "area_km2": wet / 2, "n_pixels": 1, "pct_of_compared": 0},
            {"class_id": 5, "name": "strong_wetting", "area_km2": wet / 2, "n_pixels": 1, "pct_of_compared": 0},
        ],
        "land_cover_breakdown": [
            {"land_cover": "Cropland", "n_pixels": 9000, "area_km2": 1, "mean_delta": crop_delta, "pct_drying": 5, "pct_wetting": 60},
            {"land_cover": "Grassland", "n_pixels": 1000, "area_km2": 1, "mean_delta": natural_delta, "pct_drying": 30, "pct_wetting": 5},
        ],
        "not_compared_reasons": {"not_recommended": 100, "no_retrieval": 50},
    }


SUMMARY = {"n_regions": 1, "speckle_pixels_dropped": {}, "by_direction": {
    "wetting": {"n_regions": 1, "area_km2": 300, "pct_of_compared_area": 20, "largest_region_km2": 300,
                "area_by_location_km2": {"north-east": 300}},
    "drying": {"n_regions": 0, "area_km2": 0, "pct_of_compared_area": 0, "largest_region_km2": 0,
               "area_by_location_km2": {}}}}
REGIONS = [{"region_id": 1, "rank": 1, "direction": "wetting", "area_km2": 300.0, "mean_delta": 0.12,
            "mean_sm_t1": 0.22, "mean_sm_t2": 0.34, "dominant_land_cover": "Cropland",
            "dominant_land_cover_pct": 99.0, "location_in_aoi": "north-east"}]


def _weather(a1, a2, era_delta, e1=30.0, e2=30.0):
    return {"available": True, "points": [{"lat": 18.5, "lon": 79.1}], "aoi_mean": {
        "rain_7d_before_t1_mm": a1, "rain_7d_before_t2_mm": a2, "rain_between_mm": 150.0,
        "et0_7d_before_t1_mm": e1, "et0_7d_before_t2_mm": e2, "tmax_7d_before_t1_c": 31.0,
        "tmax_7d_before_t2_c": 32.0, "era5_sm_t1": 0.30, "era5_sm_t2": 0.30 + era_delta,
        "era5_sm_delta": era_delta, "water_balance_between_mm": -100.0}}


def _verdicts(e):
    return {f["id"]: (f["verdict"], f["strength"]) for f in e["factors"]}


def test_irrigation_scenario():
    """Crops wet up while it did not rain and the weather model dried -> irrigation, strong."""
    e = explain_pair(_stats(0.06, -0.03, 0.054), SUMMARY, REGIONS,
                     {"weather": _weather(22, 0, -0.16), "regions": [
                         {"region_id": 1, "weather": {"rain_7d_before_t1_mm": 21, "rain_7d_before_t2_mm": 1,
                                                      "era5_sm_delta": -0.19}}]})
    v = _verdicts(e)
    assert e["overall_direction"] == "wetting"
    assert v["rainfall"] == ("contradicts", "moderate")
    assert v["reanalysis"][0] == "contradicts"
    assert v["irrigation"] == ("supports", "strong")
    assert e["likely_drivers"][0]["factor"].startswith("Irrigation")
    assert "suggests irrigation" in e["regions"][0]["statement"]
    assert any("ERA5-Land" in c for c in e["data_quality"]["caveats"])
    assert v["vegetation"][0] == "unavailable" and v["soil"][0] == "unavailable"


def test_rain_scenario():
    """Uniform wetting after heavy recent rain, confirmed by the weather model -> rainfall."""
    e = explain_pair(_stats(0.06, 0.055, 0.06), SUMMARY, REGIONS, {"weather": _weather(2, 60, 0.08)})
    v = _verdicts(e)
    assert v["rainfall"] == ("supports", "strong")
    assert v["reanalysis"] == ("supports", "strong")
    assert v["irrigation"][0] == "inconclusive"
    assert e["likely_drivers"][0]["factor"] in ("Rainfall", "Weather-driven change (ERA5-Land reanalysis agreement)")


def test_drying_with_heat():
    e = explain_pair(_stats(-0.06, -0.06, -0.06, wet=20, dry=700), SUMMARY, REGIONS,
                     {"weather": _weather(40, 0, -0.1, e1=25, e2=40)})
    v = _verdicts(e)
    assert e["overall_direction"] == "drying"
    assert v["rainfall"] == ("supports", "strong") and v["evaporation"] == ("supports", "strong")


def test_explain_without_any_context_still_answers():
    e = explain_pair(_stats(0.06, -0.03, 0.054), SUMMARY, REGIONS, {})
    assert e["headline"] and "**Where.**" in e["narrative"]
    assert all(f["verdict"] in ("unavailable", "supports", "inconclusive") for f in e["factors"])
    assert e["when"]["t1_local_solar_time"] == "00:09"  # no longitude known -> UTC


@pytest.mark.live
def test_live_explain_run():
    from app.core.config import get_settings
    runs = sorted((get_settings().data_dir / "processed").glob("*/stack.nc"))
    if not runs:
        pytest.skip("no prepared run")
    r = client.post(f"/api/v1/analysis/runs/{runs[0].parent.name}/explain", json={})
    assert r.status_code == 200, r.text
    p = r.json()["pairs"][0]
    assert p["explanation"]["headline"]
    ndvi = p["context"]["vegetation"]
    if ndvi["available"]:
        assert 0 < ndvi["ndvi_t1_mean"] < 0.95  # guards against the BOA double-offset bug
