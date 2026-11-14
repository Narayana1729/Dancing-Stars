from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.domains.forests.services.forest_service import ForestAnalysisService
from app.domains.forests.services.visualization_service import ForestVisualizationService

router = APIRouter(prefix="/forests", tags=["forests"])
_vis_service = ForestVisualizationService()

CAPABILITIES = {
    "forest_disturbance_detection": "operational",
    "deforestation_assessment": "operational",
    "change_detection": "operational",
    "spatial_consistency_filtering": "operational",
    "independent_reference_validation": "operational",
    "multi_temporal_layer_visualization": "operational",
}


class ForestAnalysisRequest(BaseModel):
    threshold_db: float = Field(
        default=-2.5,
        ge=-10.0,
        le=0.0,
        description="HV backscatter drop threshold in dB for canopy disturbance detection.",
    )
    min_cluster_pixels: int = Field(
        default=3,
        ge=1,
        le=50,
        description="Minimum cluster size in pixels (minimum mapping unit, MMU) to eliminate isolated speckle.",
    )
    apply_spatial_filter: bool = Field(
        default=True,
        description="Whether to apply connected component spatial consistency filtering.",
    )


@router.get("/status")
def status() -> dict:
    return {
        "domain": "forests",
        "implemented": True,
        "study_region": "Similipal Tiger Reserve, Odisha, India",
        "capabilities": CAPABILITIES,
        "methodology": "Statistical Multi-Temporal SAR Radiometric Change Detection (NISAR L2 GCOV)",
    }


@router.post("/analyze")
def analyze(req: Optional[ForestAnalysisRequest] = None) -> dict:
    service = ForestAnalysisService()
    if req is None:
        req = ForestAnalysisRequest()
    return service.run_analysis(
        threshold_db=req.threshold_db,
        min_cluster_pixels=req.min_cluster_pixels,
        apply_spatial_filter=req.apply_spatial_filter,
    )


@router.get("/layers")
def get_layers() -> dict:
    """Returns the catalog of all 9 multi-temporal visualization layers."""
    return _vis_service.get_layers_catalog()


@router.get("/layers/{layer_id}")
def get_layer_image(
    layer_id: str,
    aoi_clip: str = Query(
        default="none",
        description="AOI mask clipping mode ('none', 'sanctuary', 'core', 'forest')",
    ),
) -> Response:
    """Renders and streams a colormapped RGBA PNG raster with nodata transparency."""
    try:
        png_bytes = _vis_service.render_layer_png(layer_id=layer_id, aoi_clip=aoi_clip)
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Disposition": f"inline; filename={layer_id}.png",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boundaries")
def get_boundaries() -> dict:
    """Returns the Similipal Sanctuary and Core Reserve boundary GeoJSON in EPSG:4326."""
    try:
        return _vis_service.get_boundaries_geojson()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/temporal-metrics")
def get_temporal_metrics() -> dict:
    """Returns the verified Phase 4.2.2 multi-temporal metrics and scientific classification status."""
    return _vis_service.get_temporal_metrics()


@router.get("/pixel-inspect")
def inspect_pixel(
    lon: float = Query(..., ge=80.0, le=90.0, description="Longitude in decimal degrees (EPSG:4326)"),
    lat: float = Query(..., ge=15.0, le=30.0, description="Latitude in decimal degrees (EPSG:4326)"),
) -> dict:
    """Samples physical values across all layers at the specified geographic coordinate."""
    return _vis_service.inspect_pixel(lon=lon, lat=lat)

