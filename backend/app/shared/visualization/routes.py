from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.shared.visualization.compositor import OpticalCompositeType, SarCompositeType
from app.shared.visualization.engine import visualization_engine


router = APIRouter(prefix="/visualization", tags=["visualization"])


@router.get("/composites/types")
def get_composite_types() -> Dict[str, Any]:
    """List available SAR and Optical false-color composite formulas, band mappings, and color guides."""
    return visualization_engine.get_supported_composites()


@router.get("/composites/sar/{composite_type}")
def get_sar_composite_image(
    composite_type: SarCompositeType,
    p_min: float = Query(2.0, ge=0.0, le=20.0, description="Lower percentile stretch"),
    p_max: float = Query(98.0, ge=80.0, le=100.0, description="Upper percentile stretch"),
) -> Response:
    """Render and stream false-color SAR composite PNG (Dual-Pol RGB or Multi-Temporal Change RGB)."""
    try:
        png_bytes = visualization_engine.render_sar_composite(
            composite_type=composite_type,
            p_min=p_min,
            p_max=p_max,
        )
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Disposition": f"inline; filename={composite_type.value}.png",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rendering failed: {str(e)}")


@router.get("/composites/optical/{composite_type}")
def get_optical_composite_image(
    composite_type: OpticalCompositeType,
    p_min: float = Query(2.0, ge=0.0, le=20.0, description="Lower percentile stretch"),
    p_max: float = Query(98.0, ge=80.0, le=100.0, description="Upper percentile stretch"),
) -> Response:
    """Render and stream false-color Optical composite PNG (Color Infrared or SWIR Burn Severity)."""
    try:
        png_bytes = visualization_engine.render_optical_composite(
            composite_type=composite_type,
            p_min=p_min,
            p_max=p_max,
        )
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Disposition": f"inline; filename={composite_type.value}.png",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rendering failed: {str(e)}")


@router.get("/map-bounds/{region_id}")
def get_map_bounds(region_id: str) -> Dict[str, Any]:
    """Retrieve map-ready bounding boxes, center coordinates, and recommended zoom levels for GIS viewers."""
    try:
        return visualization_engine.get_map_bounds(region_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
