from datetime import date

import pytest

from app.config import get_settings
from app.core.exceptions import NotYetImplemented
from app.main import app
from app.shared.geospatial.bbox import BoundingBox
from app.shared.satellite.base import (
    DEFAULT_FOREST_PRODUCTS,
    NON_DEFAULT_FOREST_PRODUCTS,
    Mission,
    SarProduct,
    SceneQuery,
)


def test_app_starts():
    assert app.title


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_cors_allows_dev_origin(client):
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_blocks_unknown_origin(client):
    r = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_config_defaults(monkeypatch):
    for k in ("APP_ENV", "CORS_ORIGINS", "DATA_DIR"):
        monkeypatch.delenv(k, raising=False)
    s = get_settings()
    assert s.environment == "development"
    assert "http://localhost:5173" in s.cors_origins


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    s = get_settings()
    assert s.environment == "test"
    assert s.cors_origins == ("http://a.test", "http://b.test")


def test_wildfires_domain_reports_not_implemented(client):
    body = client.get("/api/v1/wildfires/status").json()
    assert body["implemented"] is False
    assert set(body["capabilities"].values()) == {"not_implemented"}


def test_wildfires_analyze_returns_501(client):
    assert client.post("/api/v1/wildfires/analyze").status_code == 501


def test_forests_domain_reports_operational_status(client):
    body = client.get("/api/v1/forests/status").json()
    assert body["implemented"] is True
    assert body["domain"] == "forests"
    assert "Similipal" in body["study_region"]
    assert body["capabilities"]["forest_disturbance_detection"] == "operational"


def test_forests_analyze_endpoint_returns_verified_metrics(client):
    resp = client.post("/api/v1/forests/analyze", json={"threshold_db": -2.5, "min_cluster_pixels": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["study_region"]["name"] == "Similipal Tiger Reserve, Odisha, India"
    assert data["observations"]["temporal_separation_days"] == 48
    assert "primary_detection" in data
    assert data["primary_detection"]["detected_pixels"] > 0
    assert data["primary_detection"]["total_forest_pixels"] > 0
    assert data["primary_detection"]["threshold_db"] == -2.5
    assert "validation" in data
    assert "sensitivity_analysis" in data
    assert len(data["sensitivity_analysis"]) == 5


def test_product_policy(client):
    body = client.get("/api/v1/data-products").json()
    assert body["default"] == ["GCOV", "GSLC"]
    assert body["not_default"] == ["GOFF", "GUNW"]
    assert set(DEFAULT_FOREST_PRODUCTS).isdisjoint(NON_DEFAULT_FOREST_PRODUCTS)


def test_bbox_validation():
    BoundingBox(west=-1, south=-1, east=1, north=1)
    with pytest.raises(ValueError):
        BoundingBox(west=1, south=0, east=0, north=1)
    with pytest.raises(ValueError):
        BoundingBox(west=0, south=0, east=1, north=91)


def test_scene_query_rejects_reversed_dates():
    bbox = BoundingBox(0, 0, 1, 1)
    with pytest.raises(ValueError):
        SceneQuery(bbox, date(2026, 2, 1), date(2026, 1, 1))
    q = SceneQuery(bbox, date(2026, 1, 1), date(2026, 2, 1))
    assert q.mission is Mission.NISAR and q.product is SarProduct.GCOV


def test_not_yet_implemented_is_not_implemented_error():
    assert issubclass(NotYetImplemented, NotImplementedError)



def test_asf_query_params_nisar_and_s1():
    from app.shared.satellite.asf import _query_params
    q = SceneQuery(BoundingBox(-63, -10, -62, -9), date(2026, 1, 1), date(2026, 2, 1))
    p = _query_params(q, 5)
    assert p["dataset"] == "NISAR" and p["processingLevel"] == "GCOV" and p["maxResults"] == "5"
    s1 = SceneQuery(q.bbox, q.start, q.end, Mission.SENTINEL_1, SarProduct.GRD_HD)
    assert _query_params(s1, 5)["platform"] == "S1"


def test_download_without_credentials_is_refused(monkeypatch, tmp_path):
    from pathlib import Path
    from app.shared.satellite.asf import AsfProvider, AsfScene, AuthenticationRequired
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    s = AsfScene("x", Mission.NISAR, SarProduct.GCOV, date(2026, 1, 1), download_url="https://example.invalid/x.h5")
    with pytest.raises(AuthenticationRequired):
        AsfProvider().download(s, str(tmp_path))


def test_nisar_gcov_loader():
    from pathlib import Path
    from app.shared.raster.nisar_gcov import NisarGcovLoader
    from app.shared.satellite.base import Mission, SarProduct

    fpath = Path(__file__).resolve().parents[2] / "data/raw/NISAR_L2_PR_GCOV_002_109_D_063_4005_DHDH_A_20251012T182508_20251012T182531_X05010_N_P_J_001.h5"
    if not fpath.exists():
        pytest.skip("Full GCOV measurement file not present locally")

    loader = NisarGcovLoader()
    meta = loader.extract(str(fpath))
    assert meta.mission == Mission.NISAR
    assert meta.product == SarProduct.GCOV
    assert meta.crs == "EPSG:32633"
    assert "HHHH" in meta.polarizations
    assert meta.extra["grid_shape"] == (36720, 37080)

    raster = loader.load(str(fpath), polarization="HHHH", frequency="frequencyB", stride=10)
    assert raster.array.ndim == 2
    assert raster.crs == "EPSG:32633"
    assert raster.pixel_spacing == (800.0, -800.0)


def test_statistical_forest_disturbance_detector():
    import numpy as np
    from app.domains.forests.algorithms.change_detector import StatisticalForestDisturbanceDetector

    detector = StatisticalForestDisturbanceDetector(default_threshold_db=-2.0, min_cluster_pixels=2)
    # Synthetic clean synthetic canopy patch (10x10)
    hh0 = np.full((10, 10), 0.05)
    hv0 = np.full((10, 10), 0.01)  # -20 dB
    hh1 = np.full((10, 10), 0.05)
    hv1 = np.full((10, 10), 0.01)  # baseline no change

    # Introduce canopy drop in a 2x2 cluster: drop from 0.01 to 0.003 (~-5.2 dB drop)
    hv1[3:5, 3:5] = 0.003
    # Single isolated pixel noise: drop at (8, 8)
    hv1[8, 8] = 0.003

    forest_mask = np.ones((10, 10), dtype=bool)

    # Without filter: both the 4-pixel cluster and 1-pixel noise detected = 5 pixels
    res_no_filt = detector.detect(
        baseline={"hh": hh0, "hv": hv0},
        target={"hh": hh1, "hv": hv1},
        forest_mask=forest_mask,
        apply_filter=False,
    )
    assert res_no_filt.detected_pixels == 5

    # With spatial filter (min_cluster=2): isolated pixel eliminated -> 4 pixels remaining
    res_filt = detector.detect(
        baseline={"hh": hh0, "hv": hv0},
        target={"hh": hh1, "hv": hv1},
        forest_mask=forest_mask,
        apply_filter=True,
    )
    assert res_filt.detected_pixels == 4
    assert res_filt.cluster_count == 1

