from typing import Any

from pydantic import BaseModel, Field

from app.schemas.processing import PrepareRequest, PrepareResponse
from app.services.change import ChangeParams
from app.services.context.integrate import ContextParams


class ChangeRequest(PrepareRequest):
    """Full pipeline: prepare (steps 3-7) + change (8) + regions (9)."""

    change: ChangeParams = Field(default_factory=ChangeParams)


class ExplainRequest(ChangeRequest):
    """Full pipeline: steps 3-11."""

    context: ContextParams = Field(default_factory=ContextParams)
    n_top_regions: int = Field(5, ge=1, le=50)


class DeltaStats(BaseModel):
    mean: float
    std: float
    min: float
    max: float
    p5: float
    p25: float
    median: float
    p75: float
    p95: float


class ClassRow(BaseModel):
    class_id: int
    name: str
    n_pixels: int
    area_km2: float
    pct_of_compared: float


class LandCoverRow(BaseModel):
    land_cover: str
    n_pixels: int
    area_km2: float
    mean_delta: float
    pct_drying: float
    pct_wetting: float


class PairStats(BaseModel):
    t1: str
    t2: str
    granule_t1: str
    granule_t2: str
    days: float
    n_aoi_pixels: int
    n_compared: int = Field(description="Pixels valid on both dates")
    compared_area_km2: float
    compared_fraction: float
    mean_sm_t1: float | None
    mean_sm_t2: float | None
    delta: DeltaStats | None
    median_combined_uncertainty: float | None
    classes: list[ClassRow]
    land_cover_breakdown: list[LandCoverRow]
    not_compared_reasons: dict[str, int] = Field(description="AOI pixels not compared, by QC rule (either date)")
    pixel_area_km2: float


class DirectionSummary(BaseModel):
    n_regions: int
    area_km2: float
    pct_of_compared_area: float
    largest_region_km2: float
    area_by_location_km2: dict[str, float] = Field(description="Region area by position in the AOI (compass)")


class RegionsSummary(BaseModel):
    n_regions: int
    speckle_pixels_dropped: dict[str, int]
    by_direction: dict[str, DirectionSummary]


class Factor(BaseModel):
    id: str
    name: str
    verdict: str = Field(description="supports | contradicts | inconclusive | unavailable")
    strength: str | None = Field(description="weak | moderate | strong")
    evidence: dict[str, Any]
    rule: str
    statement: str


class RegionExplanation(BaseModel):
    region_id: int
    rank: int
    direction: str
    area_km2: float
    statement: str
    context: dict[str, Any] | None


class Explanation(BaseModel):
    headline: str
    overall_direction: str
    what: dict[str, Any]
    where: dict[str, Any]
    when: dict[str, Any]
    how_much: dict[str, Any]
    factors: list[Factor]
    likely_drivers: list[dict[str, Any]]
    regions: list[RegionExplanation]
    data_quality: dict[str, Any]
    narrative: str = Field(description="Markdown narrative")
    method: str


class PairResult(BaseModel):
    stats: PairStats
    regions_summary: RegionsSummary
    regions: dict[str, Any] = Field(description="GeoJSON FeatureCollection (EPSG:4326), largest first")
    files: dict[str, str]
    context: dict[str, Any] | None = Field(None, description="Step 10 supporting data")
    explanation: Explanation | None = Field(None, description="Step 11 explanation")


class ChangeResponse(BaseModel):
    run_id: str
    params: ChangeParams
    context_params: ContextParams | None = None
    aoi_wkt: str
    pairs: list[PairResult]


class RunAnalysisRequest(BaseModel):
    """Steps 8-11 on an existing run."""

    change: ChangeParams = Field(default_factory=ChangeParams)
    context: ContextParams = Field(default_factory=ContextParams)
    n_top_regions: int = Field(5, ge=1, le=50)


class FullChangeResponse(ChangeResponse):
    preparation: PrepareResponse
