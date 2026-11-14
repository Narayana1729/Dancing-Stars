from pathlib import Path

import h5py
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.aoi import parse_aoi
from app.services.extraction import (
    GRIDS,
    ExtractionError,
    decode_retrieval_flag,
    extract_sme2,
    summarize,
)

client = TestClient(app)
LOCAL_H5 = next(Path(__file__).resolve().parents[2].joinpath("data").glob("*SME2*031_156*.h5"), None)
needs_local = pytest.mark.skipif(LOCAL_H5 is None, reason="no local SME2 file in ../data")
POLY = parse_aoi(wkt="POLYGON((78.90 18.30, 79.30 18.28, 79.35 18.60, 78.88 18.62, 78.90 18.30))")


def test_decode_retrieval_flag():
    rqf = np.array([-9999, 0, 1, 14, 15], dtype="int16")
    b = decode_retrieval_flag(rqf)
    assert b["flag_valid"].tolist() == [False, True, True, True, True]
    assert b["not_recommended"].tolist() == [False, False, True, False, True]
    assert b["dsg_applied"].tolist() == [False, False, False, True, True]
    assert b["pmi_applied"].tolist() == [False, False, False, True, True]


@needs_local
def test_extract_window_matches_raw_hdf5(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.extraction.get_settings",
                        lambda: type("S", (), {"data_dir": tmp_path})())
    ds, path = extract_sme2(str(LOCAL_H5), POLY, use_cache=False)
    assert path.exists()
    r0, r1 = map(int, ds.attrs["window_rows"].split(":"))
    c0, c1 = map(int, ds.attrs["window_cols"].split(":"))
    with h5py.File(LOCAL_H5) as h:
        g = h[GRIDS]
        raw = g["soilMoisture"][r0:r1, c0:c1]
        rq_raw = g["retrievalQualityFlag"][r0:r1, c0:c1]
        # ancillary grid must be the same grid as the main layers
        np.testing.assert_array_equal(g["xCoordinates"][:], g["ancillaryData/xCoordinates"][:])
        np.testing.assert_array_equal(g["yCoordinates"][:], g["ancillaryData/yCoordinates"][:])
    # fill -> NaN, everything else bit-identical
    np.testing.assert_array_equal(np.isnan(ds.soil_moisture.values), raw == -9999)
    np.testing.assert_array_equal(ds.soil_moisture.values[raw != -9999], raw[raw != -9999])
    np.testing.assert_array_equal(ds.retrieval_quality_flag.values, rq_raw)

    # window covers the AOI and is far smaller than the 1845x1620 grid
    assert ds.rio.crs.to_epsg() == 6933
    from app.services.aoi import to_equal_area
    minx, miny, maxx, maxy = to_equal_area(POLY).bounds
    bx0, by0, bx1, by1 = ds.rio.bounds()
    assert bx0 <= minx and by0 <= miny and bx1 >= maxx and by1 >= maxy
    assert ds.sizes["y"] < 400 and ds.sizes["x"] < 400

    # lat/lon coords agree with the window
    assert 18.2 < float(ds.latitude.min()) and float(ds.latitude.max()) < 18.9
    assert 78.8 < float(ds.longitude.min()) and float(ds.longitude.max()) < 79.4

    s = summarize(ds)
    assert s["units"] == "meter^3/meter^3"
    # product valid range is 0.02-0.60 m3/m3 (float32, so allow rounding)
    assert s["soil_moisture"]["min"] >= 0.02 - 1e-6 and s["soil_moisture"]["max"] <= 0.6 + 1e-6
    assert s["n_recommended"] + s["n_not_recommended"] == s["n_soil_moisture"]


@needs_local
def test_aoi_outside_grid_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.extraction.get_settings",
                        lambda: type("S", (), {"data_dir": tmp_path})())
    with pytest.raises(ExtractionError, match="does not intersect"):
        extract_sme2(str(LOCAL_H5), parse_aoi(bbox=[10, 10, 11, 11]), use_cache=False)


@pytest.mark.live
def test_live_extract_polygon():
    r = client.post("/api/v1/extraction/extract", json={
        "wkt": POLY.wkt, "start_date": "2026-08-01", "end_date": "2026-11-11",
    })
    assert r.status_code == 200, r.text
    obs = r.json()["observations"]
    assert len(obs) == 2 and all(o["error"] is None for o in obs), obs
    assert all(o["summary"]["n_soil_moisture"] > 0 for o in obs)
