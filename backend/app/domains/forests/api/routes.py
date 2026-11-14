from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.domains.forests.detection.reference_audit import assert_ml_training_permitted
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

CAPABILITIES_AUDIT = {
    "available_capabilities": {
        "tier1_instantaneous_candidate_detection": {
            "status": "AVAILABLE",
            "observation_count": 2,
            "temporal_coverage_days": 48.0,
            "description": "Dual-date L-band SAR backscatter differencing (ΔHV <= -2.5 dB, ΔR <= -1.5 dB, MMU >= 1.92 ha).",
            "confidence": "Provisional statistical candidate; unvalidated change hypothesis, NOT confirmed deforestation.",
        },
        "seven_class_deterministic_screening": {
            "status": "AVAILABLE",
            "observation_count": 2,
            "description": "Rule-based 7-tier classification integrating polarimetric scattering regimes, RND, and MAD dispersion.",
        },
        "physical_scattering_regimes": {
            "status": "AVAILABLE",
            "observation_count": 2,
            "description": "5-regime polarimetric decomposition separating volume loss, soil moisture drying, and surface roughness.",
        },
        "polarimetric_differencing": {
            "status": "AVAILABLE",
            "observation_count": 2,
            "description": "Decibel difference rasters for ΔHH, ΔHV, ΔRatio, and linear RND.",
        },
    },
    "blocked_capabilities": {
        "supervised_machine_learning_classifier": {
            "status": "BLOCKED_BY_DATA",
            "available_positive_samples": 43,
            "class_imbalance": "53,556:1",
            "missing_data_requirements": "Requires ≥ 50 verified, geographically distributed field compartments across all 4 forest strata. Supervised ML is strictly prohibited.",
        },
        "multi_temporal_seasonal_reference_baseline": {
            "status": "BLOCKED_BY_DATA",
            "available_observations": 2,
            "temporal_coverage": "48 days (single pre-monsoon dry season)",
            "missing_data_requirements": "Requires 8-12 repeat acquisitions spanning all astronomical/meteorological seasons (Monsoon, Post-Monsoon, Dry).",
        },
        "tier2_temporally_sustained_anomaly_classifier": {
            "status": "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS",
            "available_observations": 2,
            "missing_data_requirements": "Requires ≥ 3 consecutive post-disturbance repeat passes showing sustained backscatter suppression.",
        },
        "tier3_long_term_persistent_deforestation_classifier": {
            "status": "UNVERIFIABLE_INSUFFICIENT_TEMPORAL_COVERAGE",
            "available_observations": 2,
            "temporal_coverage_days": 48.0,
            "missing_data_requirements": "Requires ≥ 4 repeat passes spanning ≥ 180 days across seasonal leaf-flush cycles plus in-situ field validation.",
        },
        "canopy_recovery_and_rebound_tracking": {
            "status": "UNVERIFIABLE_NO_POST_EVENT_OBSERVATIONS",
            "available_observations": 2,
            "missing_data_requirements": "Requires ≥ 3 post-disturbance repeat monitoring cycles spanning 6-12 months.",
        },
        "similipal_core_full_swath_coverage": {
            "status": "PARTIALLY_BLOCKED",
            "available_swath_overlap": "18.29% of Similipal Core covered by Track 098 Frame 012",
            "missing_data_requirements": "Requires NISAR Track 098 Frame 013 to cover the southern 81.71% of the Core Reserve.",
        },
    },
    "sensor_provenance": {
        "mission": "NISAR (NASA-ISRO SAR Mission)",
        "instrument": "L-band Synthetic Aperture Radar (1217.5 / 1257.5 MHz)",
        "product_type": "Level-2 GCOV (Geocoded Covariance)",
        "track": 98,
        "frame": 12,
        "pass": "Ascending",
        "epochs": [
            {"date": "2026-03-04T23:37:20Z", "cycle": 14},
            {"date": "2026-04-21T23:37:20Z", "cycle": 18},
        ],
        "observation_count": 2,
        "temporal_baseline_days": 48.0,
    },
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
        "capabilities_audit": CAPABILITIES_AUDIT,
        "observation_count": 2,
        "temporal_baseline_days": 48.0,
        "methodology": "Statistical Multi-Temporal SAR Radiometric Change Detection (NISAR L2 GCOV)",
        "provenance": CAPABILITIES_AUDIT["sensor_provenance"],
    }


@router.get("/capabilities")
def get_capabilities() -> dict:
    """Returns granular audit of operational vs blocked capabilities and data requirements."""
    return CAPABILITIES_AUDIT


@router.post("/ml/train")
def train_supervised_model() -> dict:
    """Supervised ML training endpoint guarded by scientific sample sufficiency invariants."""
    assert_ml_training_permitted()
    return {"status": "trained"}


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

