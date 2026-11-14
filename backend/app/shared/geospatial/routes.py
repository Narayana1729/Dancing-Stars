from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.shared.geospatial.aoi import AreaOfInterest
from app.shared.geospatial.bbox import BoundingBox
from app.shared.geospatial.coverage import coverage_checker
from app.shared.geospatial.regions import region_registry


router = APIRouter(prefix="/geospatial", tags=["geospatial"])


class BBoxModel(BaseModel):
    west: float = Field(..., ge=-180.0, le=180.0, description="Western longitude")
    south: float = Field(..., ge=-90.0, le=90.0, description="Southern latitude")
    east: float = Field(..., ge=-180.0, le=180.0, description="Eastern longitude")
    north: float = Field(..., ge=-90.0, le=90.0, description="Northern latitude")


class AOIValidateRequest(BaseModel):
    geometry: Optional[Dict[str, Any]] = Field(None, description="GeoJSON Polygon or MultiPolygon")
    bbox: Optional[BBoxModel] = Field(None, description="WGS84 Bounding Box")
    name: str = Field("Custom AOI", description="Optional display name for AOI")
    description: str = Field("", description="Optional notes or description")


class CustomRegionRegisterRequest(BaseModel):
    region_id: Optional[str] = Field(None, description="Unique slug for the region (auto-generated if omitted)")
    name: str = Field(..., description="Descriptive region name")
    state: str = Field("Custom State", description="Indian State or Union Territory")
    biome: str = Field("User Defined Biome", description="Ecological biome classification")
    geometry: Optional[Dict[str, Any]] = Field(None, description="GeoJSON Polygon")
    bbox: Optional[BBoxModel] = Field(None, description="WGS84 Bounding Box")
    description: str = Field("", description="Description of the monitored zone")


class CoverageCheckRequest(BaseModel):
    region_id: Optional[str] = Field(None, description="Existing registered region ID")
    geometry: Optional[Dict[str, Any]] = Field(None, description="Ad-hoc GeoJSON Polygon")
    bbox: Optional[BBoxModel] = Field(None, description="Ad-hoc WGS84 Bounding Box")
    swath_id: str = Field("NISAR_T098_F012", description="Satellite swath identifier to evaluate")


@router.post("/aoi/validate")
def validate_aoi(req: AOIValidateRequest) -> Dict[str, Any]:
    """Validate user-defined polygon or bounding box within India territory.
    
    Computes metric area, centroid, bounding box, local UTM CRS, and analysis grid.
    """
    try:
        if req.geometry:
            aoi = AreaOfInterest(geometry_geojson=req.geometry, name=req.name, description=req.description)
        elif req.bbox:
            bbox_obj = BoundingBox(west=req.bbox.west, south=req.bbox.south, east=req.bbox.east, north=req.bbox.north)
            aoi = AreaOfInterest.from_bbox(bbox_obj, name=req.name, description=req.description)
        else:
            raise HTTPException(status_code=400, detail="Must provide either 'geometry' or 'bbox'.")
        
        grid_80m = aoi.to_grid_spec(pixel_spacing_m=80.0)
        
        return {
            "valid": True,
            "aoi": aoi.to_dict(),
            "grid_spec_80m": {
                "crs": grid_80m.crs,
                "bounds_projected": grid_80m.bounds_projected,
                "pixel_spacing": grid_80m.pixel_spacing,
                "width_pixels": grid_80m.width_pixels,
                "height_pixels": grid_80m.height_pixels,
                "origin": grid_80m.origin,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Validation failed: {str(e)}")


@router.get("/regions")
def list_regions(
    include_predefined: bool = Query(True, description="Include predefined Indian biomes"),
    include_custom: bool = Query(True, description="Include user-registered custom regions"),
) -> Dict[str, Any]:
    """List available satellite monitoring regions across India."""
    regions = region_registry.list_regions(
        include_predefined=include_predefined,
        include_custom=include_custom,
    )
    return {
        "total_regions": len(regions),
        "regions": regions,
    }


@router.get("/regions/{region_id}")
def get_region_details(region_id: str) -> Dict[str, Any]:
    """Retrieve complete metadata and GeoJSON geometry for a specific region."""
    reg = region_registry.get_region(region_id)
    if reg is None:
        raise HTTPException(status_code=404, detail=f"Region '{region_id}' not found.")
    return reg.to_dict()


@router.post("/regions/custom")
def register_custom_region(req: CustomRegionRegisterRequest) -> Dict[str, Any]:
    """Register an arbitrary user-drawn polygon or bounding box anywhere in India."""
    try:
        if req.geometry:
            aoi = AreaOfInterest(
                geometry_geojson=req.geometry,
                name=req.name,
                description=req.description,
                aoi_id=req.region_id or "custom_aoi",
            )
        elif req.bbox:
            bbox_obj = BoundingBox(west=req.bbox.west, south=req.bbox.south, east=req.bbox.east, north=req.bbox.north)
            aoi = AreaOfInterest.from_bbox(
                bbox_obj,
                name=req.name,
                description=req.description,
                aoi_id=req.region_id or "custom_bbox",
            )
        else:
            raise HTTPException(status_code=400, detail="Must provide either 'geometry' or 'bbox'.")

        meta = region_registry.register_custom_aoi(
            aoi=aoi,
            region_id=req.region_id,
            state=req.state,
            biome=req.biome,
        )
        return {
            "status": "REGISTERED",
            "region": meta.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/regions/custom/{region_id}")
def delete_custom_region(region_id: str) -> Dict[str, Any]:
    """Delete a user-defined custom region. Predefined regions cannot be deleted."""
    try:
        deleted = region_registry.remove_custom_region(region_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Custom region '{region_id}' not found.")
        return {"status": "DELETED", "region_id": region_id}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/coverage")
def check_coverage(req: CoverageCheckRequest) -> Dict[str, Any]:
    """Evaluate satellite swath coverage and observation count for an AOI or region."""
    try:
        if req.region_id:
            reg = region_registry.get_region(req.region_id)
            if reg is None:
                raise HTTPException(status_code=404, detail=f"Region '{req.region_id}' not found.")
            aoi = AreaOfInterest(
                geometry_geojson=reg.geometry,
                name=reg.name,
                aoi_id=reg.region_id,
                description=reg.description,
            )
        elif req.geometry:
            aoi = AreaOfInterest(geometry_geojson=req.geometry)
        elif req.bbox:
            bbox_obj = BoundingBox(west=req.bbox.west, south=req.bbox.south, east=req.bbox.east, north=req.bbox.north)
            aoi = AreaOfInterest.from_bbox(bbox_obj)
        else:
            raise HTTPException(status_code=400, detail="Provide 'region_id', 'geometry', or 'bbox'.")

        assessment = coverage_checker.evaluate_aoi_coverage(aoi=aoi, swath_id=req.swath_id)
        return assessment.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/utm-zone")
def lookup_utm_zone(
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in degrees"),
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in degrees"),
) -> Dict[str, Any]:
    """Determine projected UTM EPSG code for any geographic coordinates."""
    zone = int(math.floor((lon + 180.0) / 6.0)) + 1
    epsg_code = 32600 + zone if lat >= 0 else 32700 + zone
    crs = f"EPSG:{epsg_code}"
    is_india = (68.0 <= lon <= 97.5) and (6.5 <= lat <= 37.5)
    return {
        "longitude": lon,
        "latitude": lat,
        "utm_zone": zone,
        "epsg_code": epsg_code,
        "crs": crs,
        "hemisphere": "Northern" if lat >= 0 else "Southern",
        "within_india_extent": is_india,
    }
