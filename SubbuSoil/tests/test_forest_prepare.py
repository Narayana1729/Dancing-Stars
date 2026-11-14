import numpy as np
import pytest
import xarray as xr
from pyproj import Transformer
from shapely.geometry import box

from app.services import forest_analysis as F
from tests.test_forest_steps import DX, EPSG, _synthetic_gcov


def _extract(tmp_path, monkeypatch, name, x0, y0, aoi):
    monkeypatch.setattr("app.services.forest_analysis.get_settings",
                        lambda: type("S", (), {"data_dir": tmp_path})(), raising=False)
    monkeypatch.setattr("app.core.config.get_settings", lambda: type("S", (), {"data_dir": tmp_path})())
    path = tmp_path / f"{name}.h5"
    _synthetic_gcov(path, x0=x0, y0=y0, granule=name)
    ds, _ = F.extract_gcov(str(path), aoi, pad_pixels=1, use_cache=False)
    return ds


@pytest.fixture
def aoi_and_origin():
    to_utm = Transformer.from_crs(4326, EPSG, always_xy=True)
    cx, cy = to_utm.transform(75.2, 14.2)
    to_ll = Transformer.from_crs(EPSG, 4326, always_xy=True)
    lo, hi = to_ll.transform(cx - 300, cy - 300), to_ll.transform(cx + 300, cy + 300)
    return box(lo[0], lo[1], hi[0], hi[1]), cx - 600, cy + 600


def test_quality_masks_remove_each_bad_kind(tmp_path, monkeypatch, aoi_and_origin):
    aoi, x0, y0 = aoi_and_origin
    ds = _extract(tmp_path, monkeypatch, "q", x0, y0, aoi)
    out, rep = F.apply_gcov_quality(ds)
    assert rep["removed_by_rule"]["non_finite"] >= 1       # the NaN pixel
    assert rep["removed_by_rule"]["invalid_subswath"] >= 1  # the masked rows
    assert rep["n_valid"] < rep["n_pixels"]
    assert np.isnan(out.HHHH.values[out.valid.values == 0]).all()
    assert {"HH_db", "HV_db", "valid"} <= set(out.data_vars) and "mask" not in out.data_vars
    db = out.HH_db.values[out.valid.values == 1]
    assert -8 < np.median(db) < -4 and out.HH_db.attrs["units"] == "dB"


def test_geotiffs_pass_crs_spacing_and_units_checks(tmp_path, monkeypatch, aoi_and_origin):
    aoi, x0, y0 = aoi_and_origin
    ds1 = _extract(tmp_path, monkeypatch, "g1", x0, y0, aoi)
    ds2 = _extract(tmp_path, monkeypatch, "g2", x0, y0, aoi)
    ds1.attrs["start_time"], ds2.attrs["start_time"] = "2026-08-21T00:33:39", "2026-10-20T00:33:39"
    d1, _ = F.apply_gcov_quality(ds1)
    d2, _ = F.apply_gcov_quality(ds2)
    stack, _ = F.align_gcov([d1, d2])
    tifs = F.write_gcov_geotiffs(stack, tmp_path / "tifs")
    assert len(tifs) == 6 and all(t["crs_ok"] and t["spacing_ok"] for t in tifs)
    assert {t["units"] for t in tifs} == {"dB", "1"}


def test_same_grid_aligns_exactly_and_offset_grid_resamples(tmp_path, monkeypatch, aoi_and_origin):
    aoi, x0, y0 = aoi_and_origin
    a = _extract(tmp_path, monkeypatch, "a", x0, y0, aoi)
    b = _extract(tmp_path, monkeypatch, "b", x0, y0, aoi)
    a.attrs["start_time"], b.attrs["start_time"] = "2026-08-21T00:00:00", "2026-10-20T00:00:00"
    _, rep = F.align_gcov([F.apply_gcov_quality(a)[0], F.apply_gcov_quality(b)[0]])
    assert [r["method"] for r in rep] == ["exact_reindex", "exact_reindex"]
    c = _extract(tmp_path, monkeypatch, "c", x0 + 4.0, y0, aoi)  # 0.4 px east: off the lattice
    c.attrs["start_time"] = "2026-10-20T00:00:00"
    _, rep2 = F.align_gcov([F.apply_gcov_quality(a)[0], F.apply_gcov_quality(c)[0]])
    assert rep2[1]["method"] == "reproject_nearest"
