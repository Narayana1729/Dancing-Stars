from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.shared.geospatial.bbox import BoundingBox
from app.shared.geospatial.regions import region_registry
from app.shared.satellite.catalogue import (
    CatalogueItem,
    CatalogueQuery,
    catalogue_service,
)
from app.shared.satellite.local_inventory import local_inventory_service


router = APIRouter(prefix="/catalogue", tags=["catalogue"])


class BBoxSearchModel(BaseModel):
    west: float = Field(..., ge=-180.0, le=180.0)
    south: float = Field(..., ge=-90.0, le=90.0)
    east: float = Field(..., ge=-180.0, le=180.0)
    north: float = Field(..., ge=-90.0, le=90.0)


class CatalogueSearchRequest(BaseModel):
    region_id: Optional[str] = Field(None, description="Registered region ID (e.g. 'similipal')")
    geometry: Optional[Dict[str, Any]] = Field(None, description="GeoJSON Polygon or MultiPolygon")
    bbox: Optional[BBoxSearchModel] = Field(None, description="WGS84 bounding box")
    start_date: Optional[date] = Field(None, description="Earliest acquisition date (YYYY-MM-DD)")
    end_date: Optional[date] = Field(None, description="Latest acquisition date (YYYY-MM-DD)")
    missions: List[str] = Field(default_factory=lambda: ["NISAR", "SENTINEL-2"], description="List of satellite missions")
    max_cloud_cover_percent: Optional[float] = Field(30.0, ge=0.0, le=100.0, description="Max cloud cover for optical")
    polarizations: Optional[List[str]] = Field(None, description="Required polarizations (e.g. ['HH', 'HV'])")
    limit: int = Field(50, ge=1, le=200, description="Max granules to return")


@router.post("/search")
def search_catalogue(req: CatalogueSearchRequest) -> Dict[str, Any]:
    """Search multi-mission satellite imagery by polygon, bounding box, date range, and cloud cover."""
    try:
        bbox_obj: Optional[BoundingBox] = None
        geom_dict: Optional[Dict[str, Any]] = req.geometry

        if req.region_id:
            reg = region_registry.get_region(req.region_id)
            if reg is None:
                raise HTTPException(status_code=404, detail=f"Region '{req.region_id}' not found.")
            geom_dict = reg.geometry
        elif req.bbox:
            bbox_obj = BoundingBox(
                west=req.bbox.west,
                south=req.bbox.south,
                east=req.bbox.east,
                north=req.bbox.north,
            )

        query = CatalogueQuery(
            bbox=bbox_obj,
            geometry=geom_dict,
            start_date=req.start_date,
            end_date=req.end_date,
            missions=req.missions,
            max_cloud_cover_percent=req.max_cloud_cover_percent,
            polarizations=req.polarizations,
            limit=req.limit,
        )

        results = catalogue_service.search(query)

        return {
            "total_found": len(results),
            "granules": [item.to_dict() for item in results],
            "query_applied": {
                "region_id": req.region_id,
                "missions": req.missions,
                "start_date": req.start_date.isoformat() if req.start_date else None,
                "end_date": req.end_date.isoformat() if req.end_date else None,
                "max_cloud_cover_percent": req.max_cloud_cover_percent,
                "limit": req.limit,
            },
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/missions")
def list_supported_missions() -> Dict[str, Any]:
    """List operational characteristics of satellite missions supported by the system."""
    return {
        "missions": [
            {
                "mission": "NISAR",
                "agency": "NASA-ISRO",
                "sensor": "L-band SAR (1.25 GHz / 24 cm wavelength) + S-band SAR",
                "orbit": "Sun-synchronous, 747 km altitude, 12-day repeat cycle",
                "swath_width_km": 242.0,
                "spatial_resolution": "Frequency A: 10m (40 MHz); Frequency B: 80m (5 MHz sideband)",
                "polarizations": ["HH", "HV", "VH", "VV", "Compact Pol"],
                "primary_application": "Forest canopy structure, biomass penetration, sub-canopy flood/ground disturbance",
                "default_products": ["GCOV", "GSLC"],
            },
            {
                "mission": "SENTINEL-1",
                "agency": "ESA",
                "sensor": "C-band SAR (5.4 GHz / 5.6 cm wavelength)",
                "orbit": "Sun-synchronous, 6-12 day repeat cycle",
                "swath_width_km": 250.0,
                "spatial_resolution": "10m (IW GRD_HD)",
                "polarizations": ["VV", "VH", "HH", "HV"],
                "primary_application": "Upper canopy roughness, leaf moisture, surface roughness",
                "default_products": ["GRD_HD", "SLC"],
            },
            {
                "mission": "SENTINEL-2",
                "agency": "ESA",
                "sensor": "MultiSpectral Instrument (MSI)",
                "orbit": "Sun-synchronous, 5-day constellation revisit",
                "swath_width_km": 290.0,
                "spatial_resolution": "10m (VIS/NIR: B02, B03, B04, B08), 20m (Red-edge & SWIR)",
                "spectral_indices": ["NDVI", "NBR", "NDMI", "dNBR"],
                "primary_application": "Optical canopy greenness, foliar chlorophyll, fire scar severity",
                "default_products": ["L2A Surface Reflectance"],
            },
            {
                "mission": "LANDSAT 8/9",
                "agency": "USGS-NASA",
                "sensor": "Operational Land Imager (OLI-2) + TIRS-2",
                "orbit": "Sun-synchronous, 8-day combined repeat",
                "swath_width_km": 185.0,
                "spatial_resolution": "30m multispectral, 15m panchromatic, 100m thermal",
                "primary_application": "Multi-decadal historical forest baseline (1984-present)",
                "default_products": ["Level-2 Surface Reflectance"],
            },
        ]
    }


@router.get("/local-inventory")
def get_local_inventory() -> Dict[str, Any]:
    """List and inspect verified authentic satellite granules physically resident in the local workspace."""
    records = local_inventory_service.scan_inventory()
    total_size_gb = round(sum(r.file_size_gb for r in records), 2)
    return {
        "total_granules": len(records),
        "total_size_gb": total_size_gb,
        "granules": [r.to_dict() for r in records],
    }
