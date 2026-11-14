"""Unit and integration tests for Phase 7 SAR and Optical Visualization Engine."""
from __future__ import annotations

import io
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.visualization.compositor import (
    OpticalCompositeType,
    OpticalFalseColorCompositor,
    SARFalseColorCompositor,
    SarCompositeType,
    robust_percentile_stretch,
)
from app.shared.visualization.engine import VisualizationEngine, visualization_engine


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# -------------------------------------------------------------------------
# 1. Compositor Unit Tests
# -------------------------------------------------------------------------

def test_robust_percentile_stretch() -> None:
    arr = np.linspace(-15.0, 5.0, 100).reshape((10, 10))
    valid_mask = np.ones((10, 10), dtype=bool)
    valid_mask[0, 0] = False  # one nodata pixel

    stretched = robust_percentile_stretch(arr, valid_mask, p_min=5.0, p_max=95.0)
    assert stretched.shape == (10, 10)
    assert stretched.dtype == np.uint8
    assert stretched[0, 0] == 0
    assert stretched.max() <= 255
    assert stretched.min() >= 0


def test_sar_dual_pol_rgb_png_generation() -> None:
    h, w = 40, 40
    hh = np.full((h, w), -8.0, dtype=np.float32)
    hv = np.full((h, w), -14.0, dtype=np.float32)
    valid = np.ones((h, w), dtype=bool)
    valid[0, :5] = False

    png_bytes = SARFalseColorCompositor.create_dual_pol_rgb(hh, hv, valid_mask=valid)
    assert isinstance(png_bytes, bytes)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # Verify PNG image dimensions and RGBA mode
    img = Image.open(io.BytesIO(png_bytes))
    assert img.size == (w, h)
    assert img.mode == "RGBA"


def test_sar_multitemporal_change_rgb_png_generation() -> None:
    h, w = 30, 30
    hv_t0 = np.full((h, w), -13.0, dtype=np.float32)
    hv_t1 = np.full((h, w), -16.5, dtype=np.float32)  # canopy loss
    delta_ratio = np.full((h, w), -2.0, dtype=np.float32)

    png_bytes = SARFalseColorCompositor.create_multitemporal_change_rgb(hv_t0, hv_t1, delta_ratio)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    img = Image.open(io.BytesIO(png_bytes))
    assert img.size == (w, h)
    assert img.mode == "RGBA"


def test_optical_compositor_png_generation() -> None:
    h, w = 25, 25
    nir = np.full((h, w), 0.7, dtype=np.float32)
    red = np.full((h, w), 0.2, dtype=np.float32)
    green = np.full((h, w), 0.3, dtype=np.float32)

    cir_bytes = OpticalFalseColorCompositor.create_color_infrared_cir(nir, red, green)
    assert cir_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    swir2 = np.full((h, w), 0.15, dtype=np.float32)
    swir_bytes = OpticalFalseColorCompositor.create_swir_burn_severity(swir2, nir, red)
    assert swir_bytes.startswith(b"\x89PNG\r\n\x1a\n")


# -------------------------------------------------------------------------
# 2. VisualizationEngine Tests
# -------------------------------------------------------------------------

def test_engine_supported_composites_catalog() -> None:
    engine = VisualizationEngine()
    cats = engine.get_supported_composites()
    assert "sar_composites" in cats
    assert "optical_composites" in cats

    sar_types = [c["type"] for c in cats["sar_composites"]]
    assert SarCompositeType.DUAL_POL_RGB.value in sar_types
    assert SarCompositeType.MULTI_TEMPORAL_CHANGE_RGB.value in sar_types

    opt_types = [c["type"] for c in cats["optical_composites"]]
    assert OpticalCompositeType.COLOR_INFRARED_CIR.value in opt_types
    assert OpticalCompositeType.SWIR_BURN_SEVERITY.value in opt_types


def test_engine_get_map_bounds_similipal() -> None:
    engine = VisualizationEngine()
    bounds = engine.get_map_bounds("similipal")
    assert bounds["region_id"] == "similipal"
    assert bounds["crs"] == "EPSG:32645"
    assert "leaflet_bounds" in bounds
    assert len(bounds["leaflet_bounds"]) == 2
    assert bounds["default_zoom"] == 10

    # Non-existent region raises ValueError
    with pytest.raises(ValueError, match="not found"):
        engine.get_map_bounds("non_existent_park")


# -------------------------------------------------------------------------
# 3. FastAPI Visualization API Endpoints
# -------------------------------------------------------------------------

def test_api_visualization_composite_types(client: TestClient) -> None:
    resp = client.get("/api/v1/visualization/composites/types")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sar_composites"]) >= 2
    assert len(data["optical_composites"]) >= 2


def test_api_render_sar_composite(client: TestClient) -> None:
    resp = client.get("/api/v1/visualization/composites/sar/DUAL_POL_RGB")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG\r\n\x1a\n")

    # Change RGB
    resp2 = client.get("/api/v1/visualization/composites/sar/MULTI_TEMPORAL_CHANGE")
    assert resp2.status_code == 200
    assert resp2.headers["content-type"] == "image/png"


def test_api_render_optical_composite(client: TestClient) -> None:
    resp = client.get("/api/v1/visualization/composites/optical/COLOR_INFRARED_CIR")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG\r\n\x1a\n")

    resp2 = client.get("/api/v1/visualization/composites/optical/SWIR_BURN_SEVERITY")
    assert resp2.status_code == 200
    assert resp2.headers["content-type"] == "image/png"


def test_api_visualization_map_bounds(client: TestClient) -> None:
    resp = client.get("/api/v1/visualization/map-bounds/similipal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["region_id"] == "similipal"
    assert data["crs"] == "EPSG:32645"
    assert "center" in data

    # 404 for unknown
    resp_404 = client.get("/api/v1/visualization/map-bounds/invalid_id")
    assert resp_404.status_code == 404
