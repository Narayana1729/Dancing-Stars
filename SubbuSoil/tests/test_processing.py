from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.main import app
from app.services.align import align
from app.services.aoi import parse_aoi, to_equal_area
from app.services.extraction import extract_sme2
from app.services.preprocess import BIT_OF, QCParams, UnitError, preprocess, verify_units
from app.services.subset import SubsetError, subset_to_aoi

client = TestClient(app)
DX = 200.17900467012078
DATA = Path(__file__).resolve().parents[2] / "data"
H5_A = next(DATA.glob("*SME2_031_156_A*.h5"), None)
H5_D = next(DATA.glob("*SME2_033_077_D*.h5"), None)
POLY = parse_aoi(wkt="POLYGON((78.90 18.30, 79.30 18.28, 79.35 18.60, 78.88 18.62, 78.90 18.30))")


def synth(nx=20, ny=20, x0=7_600_000.0 + DX / 2, y0=2_350_000.0 - DX / 2, sm=0.3, start="2026-08-12T00:09:48",
          gid="G1", dx=DX):
    x = x0 + np.arange(nx) * dx
    y = y0 - np.arange(ny) * dx
    shp = (ny, nx)
    ds = xr.Dataset(
        {
            "soil_moisture": (("y", "x"), np.full(shp, sm, "float32"), {"units": "meter^3/meter^3"}),
            "soil_moisture_uncertainty": (("y", "x"), np.full(shp, 0.03, "float32"), {"units": "meter^3/meter^3"}),
            "retrieval_quality_flag": (("y", "x"), np.full(shp, 14, "int16"), {"flag_fill_value": -9999}),
            "surface_quality_flag": (("y", "x"), np.zeros(shp, "int16"), {"flag_fill_value": -9999}),
            "land_cover": (("y", "x"), np.full(shp, 4, "int8"), {"flag_fill_value": -127}),
            "waterbody_fraction": (("y", "x"), np.zeros(shp, "float32")),
        },
        coords={"x": x, "y": y},
        attrs={"grid_spacing_x": dx, "grid_spacing_y": -dx, "start_time": start, "granule_id": gid},
    )
    return ds.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(6933)


def aoi_from_ea(minx, miny, maxx, maxy):
    """AOI in EPSG:4326 built from EASE-grid metres."""
    from pyproj import Transformer
    t = Transformer.from_crs(6933, 4326, always_xy=True)
    (w, e), (s, n) = t.transform([minx, maxx], [miny, maxy])
    return box(w, s, e, n)


# ---------------- step 5 ----------------
def test_subset_masks_outside_and_crops():
    ds = synth()
    # polygon covering cols 5..9, rows 5..9 (pixel centres)
    x0, y0 = float(ds.x[5]) - DX / 2 + 1, float(ds.y[9]) - DX / 2 + 1
    aoi = aoi_from_ea(x0, y0, x0 + 5 * DX - 2, y0 + 5 * DX - 2)
    out = subset_to_aoi(ds, aoi)
    assert out.sizes["x"] == 5 and out.sizes["y"] == 5
    assert int(out.aoi_mask.sum()) == 25 and out.attrs["n_aoi_pixels"] == 25
    assert out.rio.crs.to_epsg() == 6933


def test_subset_triangle_sets_outside_to_nan_and_fill():
    ds = synth()
    from pyproj import Transformer
    t = Transformer.from_crs(6933, 4326, always_xy=True)
    xa, xb = float(ds.x[2]), float(ds.x[17])
    ya, yb = float(ds.y[17]), float(ds.y[2])
    from shapely.geometry import Polygon
    tri = Polygon([t.transform(xa, ya), t.transform(xb, ya), t.transform(xa, yb)])
    out = subset_to_aoi(ds, tri)
    inside = out.aoi_mask.values.astype(bool)
    assert 0 < inside.sum() < inside.size  # genuinely non-rectangular
    assert np.isnan(out.soil_moisture.values[~inside]).all()
    assert (out.retrieval_quality_flag.values[~inside] == -9999).all()
    assert (out.land_cover.values[~inside] == -127).all()
    assert out.retrieval_quality_flag.dtype == np.int16


def test_subset_outside_raises():
    with pytest.raises(SubsetError):
        subset_to_aoi(synth(), box(10, 10, 10.5, 10.5))


# ---------------- step 6 ----------------
def _prepared(changes):
    ds = synth()
    ds["aoi_mask"] = (("y", "x"), np.ones((20, 20), "uint8"))
    for (name, r, c), v in changes.items():
        ds[name].values[r, c] = v
    return ds


def test_qc_rules_each_set_their_bit():
    ds = _prepared({
        ("soil_moisture", 0, 0): np.nan,          # no retrieval
        ("soil_moisture", 0, 1): 0.75,            # out of range
        ("retrieval_quality_flag", 0, 2): 15,     # bit0 -> not recommended
        ("land_cover", 0, 3): 5,                  # built-up
        ("waterbody_fraction", 0, 4): 0.5,        # water
        ("soil_moisture_uncertainty", 0, 5): 0.2, # uncertain
        ("aoi_mask", 0, 6): 0,                    # outside AOI
    })
    out, rep = preprocess(ds, QCParams())
    mr = out.mask_reason.values
    expect = ["no_retrieval", "out_of_valid_range", "not_recommended", "excluded_land_cover",
              "high_water_fraction", "high_uncertainty", "outside_aoi"]
    for col, rule in enumerate(expect):
        assert mr[0, col] & (1 << BIT_OF[rule]), rule
        assert np.isnan(out.soil_moisture.values[0, col])
    assert mr[1, 1] == 0 and out.valid.values[1, 1] == 1
    assert rep["n_aoi_pixels"] == 399 and rep["n_valid"] == 399 - 6
    assert rep["removed_by_rule"]["not_recommended"] == 1
    assert rep["removed_land_cover_classes"] == {"Built-up": 1}
    # raw kept for transparency
    assert out.soil_moisture_raw.values[0, 2] == pytest.approx(0.3)


def test_qc_params_can_disable_rules():
    ds = _prepared({("retrieval_quality_flag", 0, 0): 15, ("land_cover", 0, 1): 5})
    out, rep = preprocess(ds, QCParams(require_recommended=False, exclude_land_cover=[]))
    assert rep["n_valid"] == 400


def test_units():
    ds = synth()
    ds.soil_moisture.attrs["units"] = "%"
    ds.soil_moisture_uncertainty.attrs["units"] = "%"
    ds["soil_moisture"] = ds.soil_moisture * 100
    ds.soil_moisture.attrs["units"] = "%"
    out, note = verify_units(ds)
    assert "converted" in note and float(out.soil_moisture.max()) == pytest.approx(0.3)
    bad = synth()
    bad.soil_moisture.attrs["units"] = "kg/m2"
    with pytest.raises(UnitError):
        verify_units(bad)


# ---------------- step 7 ----------------
def _pp(ds):
    ds["aoi_mask"] = (("y", "x"), np.ones((ds.sizes["y"], ds.sizes["x"]), "uint8"))
    return preprocess(ds, QCParams())[0]


def test_align_exact_on_shared_lattice_with_different_extents():
    a = _pp(synth(gid="A", start="2026-08-12T00:00:00"))
    b = _pp(synth(nx=25, ny=18, x0=float(a.x[3]), y0=float(a.y[2]), sm=0.2, gid="B", start="2026-10-11T00:00:00"))
    stack, rep = align([b, a])  # out of order on purpose
    assert [r["method"] for r in rep] == ["exact_reindex", "exact_reindex"]
    assert list(stack.granule_id.values) == ["A", "B"]  # sorted by time
    assert stack.sizes["x"] == 28 and stack.sizes["y"] == 20  # union extent
    # pixel at A[5,5] == B[3,2] lands on the same target cell, values untouched
    xa, ya = float(a.x[5]), float(a.y[5])
    v = stack.soil_moisture.sel(x=xa, y=ya)
    assert v.values.tolist() == pytest.approx([0.3, 0.2])
    # where B has no data -> NaN / mask_reason outside_aoi
    assert np.isnan(stack.soil_moisture.isel(time=1, x=0, y=0))
    assert int(stack.mask_reason.isel(time=1, x=0, y=0)) == 1


def test_align_resamples_when_off_lattice():
    a = _pp(synth(gid="A", start="2026-08-12T00:00:00"))
    b = _pp(synth(x0=float(a.x[0]) + DX * 0.4, gid="B", start="2026-10-11T00:00:00"))
    stack, rep = align([a, b])
    assert rep[1]["method"] == "reproject_nearest" and rep[1]["origin_offset_px"][0] == pytest.approx(0.4)
    assert stack.soil_moisture.isel(time=0).shape == stack.soil_moisture.isel(time=1).shape


@pytest.mark.skipif(H5_A is None or H5_D is None, reason="local SME2 files not present")
def test_real_files_two_tracks_align_exactly(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.extraction.get_settings", lambda: type("S", (), {"data_dir": tmp_path})())
    dss = []
    for p in (H5_A, H5_D):
        ds, _ = extract_sme2(str(p), POLY, use_cache=False)
        ds = subset_to_aoi(ds, POLY)
        dss.append(preprocess(ds, QCParams())[0])
    # the two tracks were read with different windows from different grids...
    assert dss[0].attrs["window_cols"] != dss[1].attrs["window_cols"]
    stack, rep = align(dss)
    # ...but both sit on EASE-Grid 2.0, so no resampling is needed
    assert all(r["method"] == "exact_reindex" for r in rep), rep
    assert all(max(r["origin_offset_px"]) < 1e-6 for r in rep)
    # the AOI covers the same pixels in both
    np.testing.assert_array_equal(stack.aoi_mask.isel(time=0), stack.aoi_mask.isel(time=1))
    minx, miny, maxx, maxy = to_equal_area(POLY).bounds
    bx0, by0, bx1, by1 = stack.rio.bounds()
    assert bx0 <= minx + DX and bx1 >= maxx - DX


@pytest.mark.skipif(H5_A is None, reason="local SME2 file not present")
def test_cached_extraction_keeps_crs(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.extraction.get_settings", lambda: type("S", (), {"data_dir": tmp_path})())
    first, path = extract_sme2(str(H5_A), POLY)
    again, path2 = extract_sme2(str(H5_A), POLY)  # served from the NetCDF cache
    assert path == path2 and again.rio.crs.to_epsg() == 6933
    assert again.rio.transform() == first.rio.transform()
    subset_to_aoi(again, POLY)  # must not raise "no CRS"


@pytest.mark.live
def test_live_prepare():
    r = client.post("/api/v1/processing/prepare", json={
        "wkt": POLY.wkt, "start_date": "2026-08-01", "end_date": "2026-11-11",
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["n_observations"] == 2 and j["n_common_valid_pixels"] > 0
    assert all(o["alignment"]["method"] == "exact_reindex" for o in j["observations"])
    assert all(Path(o["soil_moisture_cog"]).exists() for o in j["observations"])
    assert Path(j["stack_netcdf"]).exists()
