"""Unit and integration tests for Phase 6 Satellite Catalogue & Data Acquisition Engine."""
from __future__ import annotations

from datetime import date
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.geospatial.bbox import BoundingBox
from app.shared.satellite.catalogue import (
    CatalogueItem,
    CatalogueQuery,
    SatelliteCatalogueService,
    catalogue_service,
)
from app.shared.satellite.local_inventory import (
    LocalGranuleRecord,
    LocalInventoryService,
    local_inventory_service,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# -------------------------------------------------------------------------
# 1. SatelliteCatalogueService Tests
# -------------------------------------------------------------------------

def test_catalogue_search_nisar_similipal_bbox() -> None:
    service = SatelliteCatalogueService()
    # Similipal bounding box
    bbox = BoundingBox(west=86.15, south=21.45, east=86.70, north=22.15)
    query = CatalogueQuery(
        bbox=bbox,
        missions=["NISAR"],
        limit=20,
    )

    results = service.search(query)
    assert len(results) > 0
    first = results[0]
    assert first.mission == "NISAR"
    assert first.product_type == "GCOV"
    assert first.sensor_type == "SAR"
    assert first.overlap_percent > 0.0
    assert first.polarizations == ["HH", "HV"]


def test_catalogue_search_sentinel2_optical() -> None:
    service = SatelliteCatalogueService()
    bbox = BoundingBox(west=86.15, south=21.45, east=86.70, north=22.15)
    query = CatalogueQuery(
        bbox=bbox,
        missions=["SENTINEL-2"],
        max_cloud_cover_percent=10.0,
        limit=10,
    )

    results = service.search(query)
    assert len(results) > 0
    first = results[0]
    assert first.mission == "SENTINEL-2"
    assert first.product_type == "L2A"
    assert first.sensor_type == "OPTICAL"
    assert first.cloud_cover_percent is not None
    assert first.cloud_cover_percent <= 10.0


def test_catalogue_date_filtering() -> None:
    service = SatelliteCatalogueService()
    bbox = BoundingBox(west=86.15, south=21.45, east=86.70, north=22.15)
    
    # Query for March 2026 only
    query = CatalogueQuery(
        bbox=bbox,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        missions=["NISAR", "SENTINEL-2"],
    )

    results = service.search(query)
    for item in results:
        acq = date.fromisoformat(item.acquisition_date)
        assert date(2026, 3, 1) <= acq <= date(2026, 3, 31)


# -------------------------------------------------------------------------
# 2. LocalInventoryService Tests
# -------------------------------------------------------------------------

def test_local_inventory_scans_authentic_hdf5() -> None:
    service = LocalInventoryService()
    records = service.scan_inventory()
    
    # Must find our authentic NISAR GCOV files in data/raw
    assert len(records) >= 2
    for r in records:
        assert r.mission == "NISAR"
        assert r.product_type == "GCOV"
        assert r.format == "HDF5"
        assert r.file_size_gb > 0.0
        assert r.file_path.endswith(".h5")
        assert r.polarizations is not None
        assert "HHHH" in r.polarizations or "HH" in r.polarizations or len(r.polarizations) > 0


# -------------------------------------------------------------------------
# 3. FastAPI Catalogue API Endpoints
# -------------------------------------------------------------------------

def test_api_catalogue_search_by_region(client: TestClient) -> None:
    payload = {
        "region_id": "similipal",
        "missions": ["NISAR", "SENTINEL-2"],
        "max_cloud_cover_percent": 25.0,
        "limit": 15,
    }
    resp = client.post("/api/v1/catalogue/search", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_found" in data
    assert data["total_found"] > 0
    assert len(data["granules"]) <= 15

    missions_found = {g["mission"] for g in data["granules"]}
    assert "NISAR" in missions_found or "SENTINEL-2" in missions_found


def test_api_catalogue_search_by_bbox(client: TestClient) -> None:
    payload = {
        "bbox": {
            "west": 86.2,
            "south": 21.6,
            "east": 86.5,
            "north": 21.8,
        },
        "missions": ["NISAR"],
        "limit": 5,
    }
    resp = client.post("/api/v1/catalogue/search", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_found"] > 0
    for g in data["granules"]:
        assert g["mission"] == "NISAR"


def test_api_catalogue_missions(client: TestClient) -> None:
    resp = client.get("/api/v1/catalogue/missions")
    assert resp.status_code == 200
    data = resp.json()
    assert "missions" in data
    mission_names = [m["mission"] for m in data["missions"]]
    assert "NISAR" in mission_names
    assert "SENTINEL-1" in mission_names
    assert "SENTINEL-2" in mission_names
    assert "LANDSAT 8/9" in mission_names


def test_api_catalogue_local_inventory(client: TestClient) -> None:
    resp = client.get("/api/v1/catalogue/local-inventory")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_granules" in data
    assert data["total_granules"] >= 2
    assert "total_size_gb" in data
    assert data["total_size_gb"] > 0.0
    assert len(data["granules"]) == data["total_granules"]
