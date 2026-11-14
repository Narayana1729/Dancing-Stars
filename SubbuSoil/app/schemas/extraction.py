from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.discovery import AOIInfo


class Stats(BaseModel):
    min: float
    max: float
    mean: float
    median: float
    std: float


class ExtractionSummary(BaseModel):
    window_shape: list[int] = Field(description="[rows, cols] of the AOI window read from the grid")
    bounds_epsg6933: list[float]
    n_pixels: int
    n_soil_moisture: int = Field(description="Pixels with a soil moisture value (not fill)")
    n_recommended: int = Field(description="...of which retrievalQualityFlag bit0 == 0 (recommended)")
    n_not_recommended: int
    algorithms_applied: dict[str, int]
    soil_moisture: Stats | None
    soil_moisture_uncertainty: Stats | None
    units: str | None
    surface_flag_bits: dict[str, int] = Field(
        description="Pixel count per set bit of surfaceQualityFlag (bit meanings undocumented for R05 products)"
    )
    land_cover: dict[str, int]


class ExtractedObservation(BaseModel):
    granule_id: str
    start_time: datetime
    track_key: str
    netcdf_path: str | None = None
    summary: ExtractionSummary | None = None
    error: str | None = None


class ExtractionResponse(BaseModel):
    aoi: AOIInfo
    track_key: str
    n_observations: int
    observations: list[ExtractedObservation]
