"""Unit and integration tests for Phase 5 Configurable Geospatial Backend."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.geospatial.aoi import AreaOfInterest, GridSpecification
from app.shared.geospatial.bbox import BoundingBox
from app.shared.geospatial.coverage import (
    CoverageAssessment,
    CoverageStatus,
    ObservationCoverageChecker,
    coverage_checker,
)
from app.shared.geospatial.regions import RegionMetadata, RegionRegistry, region_registry
from app.shared.geospatial.transform import PyprojGeoTransformer


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# -------------------------------------------------------------------------
# 1. BoundingBox Tests
# -------------------------------------------------------------------------

def test_bounding_box_valid_properties() -> None:
    bbox = BoundingBox(west=86.15, south=21.45, east=86.70, north=22.15)
    assert bbox.center_lon == pytest.approx(86.425, rel=1e-4)
    assert bbox.center_lat == pytest.approx(21.80, rel=1e-4)
    assert bbox.utm_zone == 45
    assert bbox.utm_crs == "EPSG:32645"
    assert bbox.is_within_india() is True
    assert bbox.contains_point(86.35, 21.75) is True
    assert bbox.contains_point(70.0, 20.0) is False


def test_bounding_box_invalid_raises() -> None:
    # West >= East
    with pytest.raises(ValueError, match="west < east"):
        BoundingBox(west=86.70, south=21.45, east=86.15, north=22.15)

    # South >= North
    with pytest.raises(ValueError, match="south < north"):
        BoundingBox(west=86.15, south=22.15, east=86.70, north=21.45)

    # Out of range latitude
    with pytest.raises(ValueError, match="latitude"):
        BoundingBox(west=86.15, south=-95.0, east=86.70, north=21.45)


def test_bounding_box_intersection() -> None:
    b1 = BoundingBox(west=86.0, south=21.0, east=87.0, north=22.0)
    b2 = BoundingBox(west=86.5, south=21.5, east=87.5, north=22.5)
    b3 = BoundingBox(west=90.0, south=25.0, east=91.0, north=26.0)

    assert b1.intersects(b2) is True
    assert b1.intersects(b3) is False

    inter = b1.intersection(b2)
    assert inter is not None
    assert inter.west == 86.5
    assert inter.south == 21.5
    assert inter.east == 87.0
    assert inter.north == 22.0

    assert b1.intersection(b3) is None


# -------------------------------------------------------------------------
# 2. PyprojGeoTransformer Tests
# -------------------------------------------------------------------------

def test_pyproj_geo_transformer_reprojection() -> None:
    transformer = PyprojGeoTransformer()
    bbox = BoundingBox(west=86.0, south=21.0, east=87.0, north=22.0)

    min_x, min_y, max_x, max_y = transformer.reproject_bbox(bbox, "EPSG:32645")
    assert min_x < max_x
    assert min_y < max_y
    # In UTM 45N, X is around 350-550 km, Y is around 2300-2450 km
    assert 300_000 < min_x < 500_000
    assert 2_200_000 < min_y < 2_500_000


def test_pyproj_pixel_area() -> None:
    transformer = PyprojGeoTransformer()
    # 80m x 80m in projected CRS = 6400 m² = 0.0064 km² = 0.64 ha
    area_km2 = transformer.pixel_area_km2("EPSG:32645", (80.0, 80.0))
    assert area_km2 == pytest.approx(0.0064, rel=1e-4)

    area_ha = transformer.pixel_area_ha("EPSG:32645", (80.0, 80.0))
    assert area_ha == pytest.approx(0.64, rel=1e-4)


# -------------------------------------------------------------------------
# 3. AreaOfInterest Tests
# -------------------------------------------------------------------------

def test_aoi_valid_polygon_in_india() -> None:
    # A small polygon inside Odisha, India
    poly_coords = [
        [
            [86.2, 21.6],
            [86.5, 21.6],
            [86.5, 21.9],
            [86.2, 21.9],
            [86.2, 21.6],
        ]
    ]
    geojson = {"type": "Polygon", "coordinates": poly_coords}
    aoi = AreaOfInterest(geometry_geojson=geojson, name="Test Odisha Forest")

    assert aoi.area_km2 > 500.0  # Approx 30km x 33km ~= 1000 km²
    assert aoi.area_ha > 50_000.0
    assert aoi.utm_zone == 45
    assert aoi.utm_crs == "EPSG:32645"
    assert 86.2 <= aoi.centroid[0] <= 86.5
    assert 21.6 <= aoi.centroid[1] <= 21.9

    # Grid spec generation
    grid = aoi.to_grid_spec(pixel_spacing_m=80.0)
    assert grid.crs == "EPSG:32645"
    assert grid.width_pixels > 0
    assert grid.height_pixels > 0


def test_aoi_outside_india_rejected() -> None:
    # Polygon in Europe (e.g. France)
    poly_coords = [
        [
            [2.2, 48.8],
            [2.5, 48.8],
            [2.5, 49.0],
            [2.2, 49.0],
            [2.2, 48.8],
        ]
    ]
    geojson = {"type": "Polygon", "coordinates": poly_coords}
    with pytest.raises(ValueError, match="outside India territory"):
        AreaOfInterest(geometry_geojson=geojson)


def test_aoi_from_bbox() -> None:
    bbox = BoundingBox(west=76.2, south=11.7, east=76.4, north=11.9)
    aoi = AreaOfInterest.from_bbox(bbox, name="Wayanad Test")
    assert aoi.utm_zone == 43
    assert aoi.utm_crs == "EPSG:32643"
    assert aoi.area_km2 > 0


# -------------------------------------------------------------------------
# 4. RegionRegistry Tests
# -------------------------------------------------------------------------

def test_predefined_regions_loaded() -> None:
    registry = RegionRegistry()
    regions = registry.list_regions()
    assert len(regions) >= 6

    # Verify primary case study: Similipal
    similipal = registry.get_region("similipal")
    assert similipal is not None
    assert similipal.is_validated_case_study is True
    assert similipal.utm_crs == "EPSG:32645"
    assert similipal.state == "Odisha"

    # Verify Sundarbans
    sundarbans = registry.get_region("sundarbans")
    assert sundarbans is not None
    assert "Mangrove" in sundarbans.biome


def test_custom_region_registration_and_deletion() -> None:
    registry = RegionRegistry()
    bbox = BoundingBox(west=85.0, south=20.0, east=85.2, north=20.2)
    aoi = AreaOfInterest.from_bbox(bbox, name="Mahanadi Valley", aoi_id="mahanadi_01")

    meta = registry.register_custom_aoi(aoi=aoi, region_id="mahanadi_01", state="Odisha")
    assert meta.region_id == "mahanadi_01"
    assert meta.is_predefined is False

    # Retrieve
    retrieved = registry.get_region("mahanadi_01")
    assert retrieved is not None
    assert retrieved.name == "Mahanadi Valley"

    # Deletion
    assert registry.remove_custom_region("mahanadi_01") is True
    assert registry.get_region("mahanadi_01") is None

    # Cannot delete predefined
    with pytest.raises(ValueError, match="Cannot delete predefined"):
        registry.remove_custom_region("similipal")


# -------------------------------------------------------------------------
# 5. ObservationCoverageChecker Tests
# -------------------------------------------------------------------------

def test_coverage_evaluation_similipal_overlap() -> None:
    checker = ObservationCoverageChecker()
    # Northern Similipal lies inside Track 098 Frame 012
    # UTM 45N bounds: 410000 - 450000, 2380000 - 2400690 -> Lon ~86.2 to 86.4, Lat ~21.65 to 21.72
    bbox = BoundingBox(west=86.25, south=21.65, east=86.35, north=21.70)
    aoi = AreaOfInterest.from_bbox(bbox, name="North Similipal Swath Test")

    assessment = checker.evaluate_aoi_coverage(aoi=aoi, swath_id="NISAR_T098_F012")
    assert assessment.coverage_status in (CoverageStatus.FULL_COVERAGE, CoverageStatus.PARTIAL_COVERAGE)
    assert assessment.overlap_percentage > 0.0
    assert assessment.available_observations == 2


def test_coverage_evaluation_south_india_no_overlap() -> None:
    checker = ObservationCoverageChecker()
    # Wayanad (Kerala) is in Zone 43N, far away from Track 098 Frame 012 (Odisha)
    bbox = BoundingBox(west=76.2, south=11.7, east=76.4, north=11.9)
    aoi = AreaOfInterest.from_bbox(bbox, name="Wayanad Zero Coverage Test")

    assessment = checker.evaluate_aoi_coverage(aoi=aoi, swath_id="NISAR_T098_F012")
    assert assessment.coverage_status == CoverageStatus.NO_COVERAGE
    assert assessment.overlap_percentage == 0.0
    assert assessment.available_observations == 0
    assert "outside" in assessment.scientific_notice.lower()


# -------------------------------------------------------------------------
# 6. FastAPI Geospatial API Endpoints
# -------------------------------------------------------------------------

def test_api_aoi_validate_valid_geojson(client: TestClient) -> None:
    payload = {
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [86.2, 21.6],
                    [86.4, 21.6],
                    [86.4, 21.8],
                    [86.2, 21.8],
                    [86.2, 21.6],
                ]
            ],
        },
        "name": "Validation Test AOI",
    }
    resp = client.post("/api/v1/geospatial/aoi/validate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["aoi"]["utm_crs"] == "EPSG:32645"
    assert data["aoi"]["area_km2"] > 0
    assert data["grid_spec_80m"]["crs"] == "EPSG:32645"


def test_api_aoi_validate_outside_india(client: TestClient) -> None:
    payload = {
        "bbox": {
            "west": 10.0,
            "south": 50.0,
            "east": 11.0,
            "north": 51.0,
        }
    }
    resp = client.post("/api/v1/geospatial/aoi/validate", json=payload)
    assert resp.status_code == 422
    assert "outside India territory" in resp.json()["detail"]


def test_api_list_and_get_regions(client: TestClient) -> None:
    resp = client.get("/api/v1/geospatial/regions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_regions"] >= 6
    region_ids = [r["region_id"] for r in data["regions"]]
    assert "similipal" in region_ids
    assert "sundarbans" in region_ids
    assert "corbett" in region_ids

    # Detail endpoint
    detail_resp = client.get("/api/v1/geospatial/regions/similipal")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["name"] == "Similipal Tiger Reserve & Wildlife Sanctuary"
    assert detail["is_validated_case_study"] is True
    assert "geometry" in detail

    # 404 for unknown region
    not_found = client.get("/api/v1/geospatial/regions/unknown_reserve_xyz")
    assert not_found.status_code == 404


def test_api_custom_region_lifecycle(client: TestClient) -> None:
    custom_payload = {
        "region_id": "kanha_custom_sub_aoi",
        "name": "Kanha Sub-basin",
        "state": "Madhya Pradesh",
        "biome": "Central Deciduous",
        "bbox": {
            "west": 80.5,
            "south": 22.1,
            "east": 80.7,
            "north": 22.3,
        },
    }
    # Register
    reg_resp = client.post("/api/v1/geospatial/regions/custom", json=custom_payload)
    assert reg_resp.status_code == 200
    assert reg_resp.json()["status"] == "REGISTERED"

    # Verify in list
    list_resp = client.get("/api/v1/geospatial/regions")
    assert "kanha_custom_sub_aoi" in [r["region_id"] for r in list_resp.json()["regions"]]

    # Delete
    del_resp = client.delete("/api/v1/geospatial/regions/custom/kanha_custom_sub_aoi")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "DELETED"

    # Attempt to delete predefined region raises 403
    del_predefined = client.delete("/api/v1/geospatial/regions/custom/similipal")
    assert del_predefined.status_code == 403


def test_api_coverage_check(client: TestClient) -> None:
    # Check coverage by region_id
    resp = client.post("/api/v1/geospatial/coverage", json={"region_id": "similipal"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["aoi_id"] == "similipal"
    assert data["mission"] == "NISAR"
    assert "coverage_status" in data
    assert "overlap_percentage" in data


def test_api_utm_zone_lookup(client: TestClient) -> None:
    # Bhubaneswar / Similipal longitude (~86E)
    resp = client.get("/api/v1/geospatial/utm-zone?lon=86.35&lat=21.75")
    assert resp.status_code == 200
    data = resp.json()
    assert data["utm_zone"] == 45
    assert data["crs"] == "EPSG:32645"
    assert data["within_india_extent"] is True

    # Bengaluru longitude (~77.5E)
    resp2 = client.get("/api/v1/geospatial/utm-zone?lon=77.59&lat=12.97")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["utm_zone"] == 43
    assert data2["crs"] == "EPSG:32643"
