import h5py
import numpy as np
import pytest
from pyproj import Transformer
from shapely.geometry import box

from app.services import forest_analysis as F

EPSG = 32643  # UTM 43N, as in the real Western Ghats granules
DX = 10.0


def _synthetic_gcov(path, n=120, x0=None, y0=None, granule="NISAR_L2_PR_GCOV_TEST"):
    """Small GCOV-shaped file: same group, layers, projection and coordinate layout."""
    rng = np.random.default_rng(0)
    hh = (10 ** (rng.normal(-0.6, 0.2, (n, n)))).astype("float32")  # about -6 dB
    hv = (hh * 0.25).astype("float32")                               # about -12 dB
    hh[60, 60] = np.nan  # invalid pixel inside the central AOI window
    mask = np.zeros((n, n), "uint8")
    mask[58:60, :] = 255  # invalid subswath rows through the centre
    xs = x0 + np.arange(n) * DX
    ys = y0 - np.arange(n) * DX
    with h5py.File(path, "w") as f:
        f["science/LSAR/identification/granuleId"] = granule
        g = f.create_group("science/LSAR/GCOV/grids/frequencyA")
        g["HHHH"] = hh
        g["HVHV"] = hv
        g["mask"] = mask
        g["numberOfLooks"] = np.full((n, n), 4.0, "float32")
        g["projection"] = np.uint32(EPSG)
        g["projection"].attrs["epsg_code"] = str(EPSG)
        g["xCoordinates"] = xs
        g["yCoordinates"] = ys
        g["xCoordinateSpacing"] = DX
        g["yCoordinateSpacing"] = -DX
        g["HHHH"].attrs["units"] = b"1"
    return hh, hv, mask


@pytest.fixture
def grid(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.forest_analysis.get_settings",
                        lambda: type("S", (), {"data_dir": tmp_path})(), raising=False)
    monkeypatch.setattr("app.core.config.get_settings", lambda: type("S", (), {"data_dir": tmp_path})())
    # place the synthetic grid around lon 75.2, lat 14.2 (UTM 43N)
    to_utm = Transformer.from_crs(4326, EPSG, always_xy=True)
    cx, cy = to_utm.transform(75.2, 14.2)
    x0, y0 = cx - 600, cy + 600  # 120 px at 10 m: roughly 1.2 km square
    path = tmp_path / "gcov.h5"
    hh, hv, mask = _synthetic_gcov(path, x0=x0, y0=y0)
    to_ll = Transformer.from_crs(EPSG, 4326, always_xy=True)
    lo = [to_ll.transform(cx - 300 + dx, cy - 300 + dy) for dx, dy in [(0, 0), (600, 0), (600, 600), (0, 600)]]
    aoi = box(lo[0][0], lo[0][1], lo[2][0], lo[2][1])  # central ~600 m square, in lon/lat
    return path, hh, hv, mask, aoi


def test_product_definition_matches_notes():
    p = F.GCOVProduct()
    assert p.group == "/science/LSAR/GCOV/grids/frequencyA"
    assert p.polarisations == ("HHHH", "HVHV")


def test_verify_accepts_gcov_and_rejects_other_files(grid):
    path, *_ = grid
    info = F.verify_gcov(str(path), "NISAR_L2_PR_GCOV_TEST")
    assert info["layers"] == ["HHHH", "HVHV"] and info["shape"] == [120, 120]
    with pytest.raises(Exception, match="mismatch"):
        F.verify_gcov(str(path), "SOMETHING_ELSE_ENTIRELY")


def test_inspect_reports_layers_grid_and_projection(grid):
    path, *_ = grid
    info = F.inspect_gcov(str(path))
    assert info["layers"]["HHHH"]["units"] == "1"
    assert info["grid"]["xCoordinateSpacing"] == DX
    assert info["projection"]["epsg_code"] == str(EPSG)


def test_extract_window_covers_aoi_and_keeps_values(grid):
    path, hh, hv, mask, aoi = grid
    ds, cache = F.extract_gcov(str(path), aoi, pad_pixels=1, use_cache=False)
    assert cache.exists()
    r0, r1 = map(int, ds.attrs["window_rows"].split(":"))
    c0, c1 = map(int, ds.attrs["window_cols"].split(":"))
    assert ds.HHHH.shape == (r1 - r0, c1 - c0) and ds.HHHH.shape[0] < 120  # a window, not the whole grid
    np.testing.assert_array_equal(ds.HHHH.values, hh[r0:r1, c0:c1])
    np.testing.assert_array_equal(ds.HVHV.values, hv[r0:r1, c0:c1])
    assert ds.rio.crs.to_epsg() == EPSG


def test_summary_excludes_invalid_and_converts_to_db(grid):
    path, hh, hv, mask, aoi = grid
    ds, _ = F.extract_gcov(str(path), aoi, pad_pixels=1, use_cache=False)
    s = F.summarize_gcov(ds)
    assert 0 < s["valid_fraction"] < 1          # NaN pixel and masked rows are excluded
    assert -8 < s["HH_dB"]["median"] < -4       # about -6 dB by construction
    assert s["HV_dB"]["median"] < s["HH_dB"]["median"]  # HV was made weaker than HH


def test_extract_uses_cache_second_time(grid):
    path, *_, aoi = grid
    _, first = F.extract_gcov(str(path), aoi, pad_pixels=1)
    _, second = F.extract_gcov(str(path), aoi, pad_pixels=1)
    assert first == second


def test_aoi_outside_granule_is_rejected(grid):
    path, *_ = grid
    from app.services.extraction import ExtractionError
    with pytest.raises(ExtractionError):
        F.extract_gcov(str(path), box(10, 10, 10.1, 10.1), use_cache=False)
