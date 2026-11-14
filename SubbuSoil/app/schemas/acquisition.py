from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.schemas.discovery import AOIInfo, DiscoveryRequest


class SelectionStrategy(str, Enum):
    FIRST_LAST = "first_last"  # oldest + newest on the track (max time separation)
    LATEST = "latest"          # the N most recent
    ALL = "all"                # every observation on the track (up to max_observations)


class AccessMode(str, Enum):
    STREAM = "stream"      # read remotely over HTTPS on demand (Cookbook default)
    DOWNLOAD = "download"  # cache the whole .h5 under DATA_DIR/raw, then read locally


class AcquisitionRequest(DiscoveryRequest):
    """Discovery parameters + how to pick observations for change detection."""

    track_key: str | None = Field(
        None, description="e.g. 'A_156_011'. Default: best-covering track with >=2 observations"
    )
    granule_ids: list[str] | None = Field(
        None, description="Explicit granules to use (overrides track_key/strategy)"
    )
    strategy: SelectionStrategy = SelectionStrategy.FIRST_LAST
    max_observations: int = Field(2, ge=2, le=50)
    mode: AccessMode = AccessMode.STREAM
    min_coverage: float = Field(0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_ids(self):
        if self.granule_ids is not None and len(set(self.granule_ids)) < 2:
            raise ValueError("granule_ids must contain at least 2 distinct granules")
        return self


class AcquiredObservation(BaseModel):
    granule_id: str
    start_time: datetime
    track_key: str
    aoi_coverage: float
    https_url: str
    mode: AccessMode
    local_path: str | None = None
    size_bytes: int | None = None
    # filled by remote verification
    verified: bool = False
    grid_shape: list[int] | None = None
    epsg: int | None = None
    variables: list[str] = []
    error: str | None = None


class AcquisitionResponse(BaseModel):
    aoi: AOIInfo
    track_key: str
    n_observations: int
    days_spanned: float
    observations: list[AcquiredObservation] = Field(description="Sorted oldest -> newest")
