"""Tests for Forest Disturbance Visualization endpoints and services."""
import pytest


def test_forest_layers_catalog_endpoint(client):
    r = client.get("/api/v1/forests/layers")
    assert r.status_code == 200
    data = r.json()
    assert "layers" in data
    assert len(data["layers"]) == 9
    layer_ids = [l["id"] for l in data["layers"]]
    expected_layers = [
        "boundary",
        "delta_hh",
        "delta_hv",
        "delta_ratio",
        "rnd_hv",
        "tier1_candidates",
        "physical_regimes",
        "valid_coverage",
        "uncertainty_mask",
    ]
    for expected in expected_layers:
        assert expected in layer_ids
    assert "bounds" in data
    assert "wgs84" in data["bounds"]
    assert "utm" in data["bounds"]


def test_forest_layers_png_rendering(client):
    layers_to_test = [
        "delta_hh",
        "delta_hv",
        "delta_ratio",
        "rnd_hv",
        "tier1_candidates",
        "physical_regimes",
        "valid_coverage",
        "uncertainty_mask",
    ]
    for layer_id in layers_to_test:
        r = client.get(f"/api/v1/forests/layers/{layer_id}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert len(r.content) > 1000  # valid PNG binary


def test_forest_layers_aoi_clipping(client):
    r = client.get("/api/v1/forests/layers/delta_hv?aoi_clip=sanctuary")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 1000


def test_forest_layers_invalid_layer_returns_404(client):
    r = client.get("/api/v1/forests/layers/invalid_unknown_layer")
    assert r.status_code == 404


def test_forest_boundaries_endpoint(client):
    r = client.get("/api/v1/forests/boundaries")
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) >= 2
    feature_ids = [f["id"] for f in data["features"]]
    assert "similipal_sanctuary" in feature_ids
    assert "similipal_core" in feature_ids


def test_forest_temporal_metrics_endpoint(client):
    r = client.get("/api/v1/forests/temporal-metrics")
    assert r.status_code == 200
    data = r.json()
    assert "observations" in data
    assert data["observations"]["temporal_separation_days"] == 48
    assert "quantitative_changes" in data
    assert "delta_hh_db" in data["quantitative_changes"]
    assert "delta_hv_db" in data["quantitative_changes"]
    assert "delta_ratio_db" in data["quantitative_changes"]
    assert "disturbance_classification" in data
    assert data["disturbance_classification"]["tier1_instantaneous"]["status"] == "ACTIVE_CANDIDATE"
    assert data["disturbance_classification"]["tier2_temporally_sustained"]["status"] == "UNAVAILABLE_UNVERIFIABLE"
    assert data["disturbance_classification"]["tier3_long_term_persistent"]["status"] == "UNAVAILABLE_UNVERIFIABLE"
    assert data["disturbance_classification"]["canopy_recovery"]["status"] == "UNVERIFIABLE"
    assert "scientific_uncertainty" in data


def test_forest_pixel_inspect_endpoint(client):
    # Test valid pixel inside swath: lon=86.234, lat=21.543
    r = client.get("/api/v1/forests/pixel-inspect?lon=86.234&lat=21.543")
    assert r.status_code == 200
    data = r.json()
    assert data["inside_bbox"] is True
    assert "coordinates" in data
    assert "values" in data
    assert "regime" in data
    assert "disturbance_candidate" in data

    # Test outside bounding box
    r_out = client.get("/api/v1/forests/pixel-inspect?lon=81.0&lat=20.0")
    assert r_out.status_code == 200
    data_out = r_out.json()
    assert data_out["inside_bbox"] is False

