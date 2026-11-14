from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.acquisition import AcquisitionRequest
from app.schemas.discovery import AOIInfo
from app.services.preprocess import QCParams


class PrepareRequest(AcquisitionRequest):
    qc: QCParams = Field(default_factory=QCParams)
    all_touched: bool = Field(
        False, description="Include pixels touched by the polygon edge (default: pixel centre inside)"
    )


class QCReport(BaseModel):
    units: str
    n_aoi_pixels: int
    n_with_retrieval: int
    n_valid: int
    valid_fraction: float
    removed_by_rule: dict[str, int] = Field(description="Pixels inside AOI removed per rule (rules overlap)")
    removed_land_cover_classes: dict[str, int]
    qc_params: dict


class AlignmentReport(BaseModel):
    granule_id: str | None
    method: str = Field(description="exact_reindex (no resampling) or reproject_nearest")
    crs: str
    resolution_m: list[float]
    origin_offset_px: list[float]
    source_shape: list[int]


class PreparedObservation(BaseModel):
    granule_id: str
    start_time: datetime
    qc: QCReport | None = None
    alignment: AlignmentReport | None = None
    soil_moisture_cog: str | None = None
    mask_reason_cog: str | None = None
    error: str | None = None


class GridInfo(BaseModel):
    crs: str
    shape: list[int] = Field(description="[rows, cols]")
    resolution_m: list[float]
    bounds: list[float]
    transform: list[float]
    pixel_area_km2: float


class PrepareResponse(BaseModel):
    run_id: str
    aoi: AOIInfo
    track_key: str
    grid: GridInfo
    n_observations: int
    n_common_valid_pixels: int = Field(description="Valid in every observation (usable for change detection)")
    common_valid_area_km2: float
    observations: list[PreparedObservation]
    stack_netcdf: str
    output_dir: str
