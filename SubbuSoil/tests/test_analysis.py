import json

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient
from pyproj import Transformer
from shapely.geometry import box, shape

from app.main import app
from app.services.aoi import to_equal_area
from app.services.change import ChangeParams, detect_change, pair_indices
from app.services.preprocess import BIT_OF
from app.services.spatial import find_regions, regions_geojson

client = TestClient(app)
DX = 200.17900467012078
N = 60
X0, Y0 = 7_600_000.0 + DX / 2, 2_350_000.0 - DX / 2
PX_KM2 = DX * DX / 1e6


def _aoi_wkt():
    t = Transformer.from_crs(6933, 4326, always_xy=True)
    (w, e), (s, n) = t.transform([X0 - DX / 2, X0 + (N - 0.5) * DX], [Y0 - (N - 0.5) * DX, Y0 + DX / 2])
    return box(w, s, e, n).wkt


def make_stack():
    """t1 = 0.30 everywhere. t2 has:
       - 10x10 strong drying (-0.15) in the NORTH-WEST (rows 5-14, cols 5-14)
       - 6x6 wetting (+0.07) in the SOUTH-EAST (rows 45-50, cols 45-50)
       - 2-pixel drying speckle (-0.08) at row 30, cols 30-31
       - 1 pixel +0.07 but uncertainty 0.1 -> not significant (row 20, col 40)
       - 3 pixels invalid on t2 (row 0, cols 0-2)
       - +0.03 noise-level change elsewhere -> no significant change
    """
    x = X0 + np.arange(N) * DX
    y = Y0 - np.arange(N) * DX
    sm1 = np.full((N, N), 0.30, "float32")
    sm2 = np.full((N, N), 0.33, "float32")
    sm2[5:15, 5:15] = 0.15
    sm2[45:51, 45:51] = 0.37
    sm2[30, 30:32] = 0.22
    sm2[20, 40] = 0.37
    unc1 = np.full((N, N), 0.02, "float32")
    unc2 = unc1.copy()
    unc2[20, 40] = 0.10
    valid2 = np.ones((N, N), "uint8")
    valid2[0, 0:3] = 0
    reason2 = np.zeros((N, N), "uint8")
    reason2[0, 0:3] = 1 << BIT_OF["not_recommended"]
    sm2 = np.where(valid2 == 1, sm2, np.nan).astype("float32")
    lc = np.full((N, N), 4, "int8")
    lc[5:15, 5:15] = 1  # tree cover under the drying block

    def layer(a1, a2):
        return (("time", "y", "x"), np.stack([a1, a2]))

    ds = xr.Dataset(
        {
            "soil_moisture": layer(sm1, sm2),
            "soil_moisture_uncertainty": layer(unc1, unc2),
            "valid": layer(np.ones((N, N), "uint8"), valid2),
            "aoi_mask": layer(np.ones((N, N), "uint8"), np.ones((N, N), "uint8")),
            "mask_reason": layer(np.zeros((N, N), "uint8"), reason2),
            "land_cover": layer(lc, lc),
        },
        coords={
            "time": np.array(["2026-08-12T00:09:48", "2026-10-11T00:09:48"], "datetime64[ns]"),
            "granule_id": ("time", ["G1", "G2"]),
            "x": x, "y": y,
        },
        attrs={"grid_spacing_x": DX, "grid_spacing_y": -DX, "aoi_wkt": _aoi_wkt()},
    )
    return ds.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(6933)


def test_pair_indices():
    assert pair_indices(3, "first_last") == [(0, 2)]
    assert pair_indices(3, "consecutive") == [(0, 1), (1, 2)]
    assert pair_indices(3, "all") == [(0, 1), (0, 2), (1, 2)]


def test_change_classes_and_significance():
    change, s = detect_change(make_stack(), 0, 1, ChangeParams())
    cls = change.change_class.values
    assert (cls[5:15, 5:15] == 1).all()                  # strong drying
    assert (cls[45:51, 45:51] == 4).all()                # wetting (0.07 < strong 0.10)
    assert (cls[30, 30:32] == 2).all()                   # drying
    assert cls[20, 40] == 3                              # big but within uncertainty
    assert (cls[0, 0:3] == 0).all()                      # not compared
    assert cls[40, 10] == 3                              # noise-level +0.03
    assert change.delta.values[7, 7] == pytest.approx(-0.15, abs=1e-6)
    assert s["n_compared"] == N * N - 3
    assert s["not_compared_reasons"]["not_recommended"] == 3
    by = {c["name"]: c for c in s["classes"]}
    assert by["strong_drying"]["n_pixels"] == 100
    assert by["strong_drying"]["area_km2"] == pytest.approx(100 * PX_KM2, rel=1e-3)
    assert by["wetting"]["n_pixels"] == 36
    assert s["days"] == 60.0
    lc = {r["land_cover"]: r for r in s["land_cover_breakdown"]}
    assert lc["Tree cover"]["pct_drying"] == 100.0


def test_regions_polygons_areas_and_location():
    stack = make_stack()
    change, _ = detect_change(stack, 0, 1, ChangeParams())
    gdf, summ, ids = find_regions(change, stack.attrs["aoi_wkt"], ChangeParams(min_region_pixels=10))

    assert summ["n_regions"] == 2
    assert summ["speckle_pixels_dropped"] == {"drying": 2, "wetting": 0}
    dry = gdf[gdf.direction == "drying"].iloc[0]
    wet = gdf[gdf.direction == "wetting"].iloc[0]
    assert dry["rank"] == 1 and dry.n_pixels == 100 and wet.n_pixels == 36
    # polygon area (equal-area CRS) == pixel count x pixel area
    assert dry.geometry.area / 1e6 == pytest.approx(100 * PX_KM2, rel=1e-9)
    assert dry.area_km2 == pytest.approx(100 * PX_KM2, abs=1e-3)  # reported value is rounded
    assert dry.mean_delta == pytest.approx(-0.15, abs=1e-4)
    assert dry.pct_strong == 100.0
    assert dry.dominant_land_cover == "Tree cover"
    assert dry.location_in_aoi == "north-west"
    assert wet.location_in_aoi == "south-east"
    assert summ["by_direction"]["drying"]["area_by_location_km2"] == {"north-west": pytest.approx(100 * PX_KM2, rel=1e-3)}
    # region raster agrees with polygons
    assert int((ids == dry.region_id).sum()) == 100

    fc = regions_geojson(gdf)
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 2
    g = shape(fc["features"][0]["geometry"])
    assert 70 < g.centroid.x < 90 and 0 < g.centroid.y < 30  # lon/lat, not metres
    assert to_equal_area(g).area / 1e6 == pytest.approx(dry.area_km2, rel=1e-3)


def test_min_region_pixels_one_keeps_speckle():
    stack = make_stack()
    change, _ = detect_change(stack, 0, 1, ChangeParams())
    _, summ, _ = find_regions(change, stack.attrs["aoi_wkt"], ChangeParams(min_region_pixels=1))
    assert summ["n_regions"] == 3 and summ["speckle_pixels_dropped"]["drying"] == 0


def test_diagonal_pixels_give_valid_polygon():
    """8-connected pixels touching only at a corner must still yield a valid geometry."""
    stack = make_stack()
    sm2 = stack.soil_moisture.values[1]
    sm2[:] = 0.30
    for k in range(12):  # a diagonal staircase of single pixels
        sm2[20 + k, 20 + k] = 0.10
    change, _ = detect_change(stack, 0, 1, ChangeParams())
    gdf, summ, _ = find_regions(change, stack.attrs["aoi_wkt"], ChangeParams(connectivity=8))
    assert summ["n_regions"] == 1 and gdf.n_pixels.iloc[0] == 12
    assert gdf.is_valid.all() and gdf.to_crs(4326).is_valid.all()
    assert gdf.geometry.iloc[0].area / 1e6 == pytest.approx(12 * PX_KM2, rel=1e-9)
    _, summ4, _ = find_regions(change, stack.attrs["aoi_wkt"], ChangeParams(connectivity=4))
    assert summ4["n_regions"] == 0  # single pixels < min_region_pixels


def test_no_change_gives_no_regions():
    stack = make_stack()
    stack["soil_moisture"][1] = stack["soil_moisture"][0]
    change, s = detect_change(stack, 0, 1, ChangeParams())
    gdf, summ, _ = find_regions(change, stack.attrs["aoi_wkt"], ChangeParams())
    assert summ["n_regions"] == 0 and len(regions_geojson(gdf)["features"]) == 0


def test_params_validation():
    with pytest.raises(ValueError):
        ChangeParams(min_change=0.1, strong_change=0.05)


def test_api_run_endpoint(tmp_path, monkeypatch):
    run = tmp_path / "processed" / "testrun"
    run.mkdir(parents=True)
    make_stack().to_netcdf(run / "stack.nc", engine="h5netcdf")
    monkeypatch.setattr("app.services.analysis.get_settings", lambda: type("S", (), {"data_dir": tmp_path})())
    r = client.post("/api/v1/analysis/runs/testrun/change", json={"min_region_pixels": 10})
    assert r.status_code == 200, r.text
    pair = r.json()["pairs"][0]
    assert pair["regions_summary"]["n_regions"] == 2
    for f in pair["files"].values():
        assert (tmp_path / f).exists() or __import__("pathlib").Path(f).exists()
    assert client.post("/api/v1/analysis/runs/nope/change").status_code == 404


@pytest.mark.live
def test_live_full_change():
    r = client.post("/api/v1/analysis/change", json={
        "wkt": "POLYGON((78.90 18.30, 79.30 18.28, 79.35 18.60, 78.88 18.62, 78.90 18.30))",
        "start_date": "2026-08-01", "end_date": "2026-11-11",
    })
    assert r.status_code == 200, r.text
    p = r.json()["pairs"][0]
    assert p["stats"]["n_compared"] > 0
    json.dumps(p["regions"])  # serialisable GeoJSON
