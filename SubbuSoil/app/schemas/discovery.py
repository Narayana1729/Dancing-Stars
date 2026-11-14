from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class FlightDirection(str, Enum):
    ASCENDING = "ASCENDING"
    DESCENDING = "DESCENDING"


class DiscoveryRequest(BaseModel):
    """Area of interest + time window. Give exactly one of `bbox`, `geometry`, `wkt`."""

    bbox: list[float] | None = Field(
        None,
        min_length=4,
        max_length=4,
        description="[west, south, east, north] in EPSG:4326 degrees",
    )
    geometry: dict[str, Any] | None = Field(
        None, description="GeoJSON Polygon/MultiPolygon in EPSG:4326"
    )
    wkt: str | None = Field(None, description="WKT POLYGON in EPSG:4326 (lon lat)")

    start_date: date = Field(
        default_factory=lambda: (datetime.now(timezone.utc) - timedelta(days=90)).date()
    )
    end_date: date = Field(default_factory=lambda: datetime.now(timezone.utc).date())
    flight_direction: FlightDirection | None = None
    min_coverage: float = Field(
        0.0, ge=0.0, le=1.0, description="Min fraction of the AOI a granule must cover"
    )
    max_results: int = Field(250, ge=1, le=2000)

    @model_validator(mode="after")
    def _check(self):
        given = [x for x in (self.bbox, self.geometry, self.wkt) if x is not None]
        if len(given) != 1:
            raise ValueError("Provide exactly one of: bbox, geometry, wkt")
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


# Shown as a dropdown in /docs ("Try it out"). Coordinates are lon, lat (EPSG:4326).
_DATES = {"start_date": "2026-08-01", "end_date": "2026-11-11"}
AOI_EXAMPLES = {
    "geojson_polygon": {
        "summary": "Polygon (GeoJSON)",
        "description": "Any polygon; first and last point must be the same.",
        "value": {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [78.90, 18.30], [79.30, 18.28], [79.35, 18.60],
                    [78.88, 18.62], [78.90, 18.30],
                ]],
            },
            **_DATES,
        },
    },
    "wkt_polygon": {
        "summary": "Polygon (WKT)",
        "value": {
            "wkt": "POLYGON((78.90 18.30, 79.30 18.28, 79.35 18.60, 78.88 18.62, 78.90 18.30))",
            **_DATES,
        },
    },
    "bbox": {
        "summary": "Bounding box",
        "value": {"bbox": [78.86, 18.27, 79.36, 18.77], **_DATES},
    },
}


class Observation(BaseModel):
    granule_id: str
    start_time: datetime
    stop_time: datetime
    flight_direction: str
    track: int
    frame: int
    cycle: int
    orbit: int | None
    track_key: str = Field(description="Repeat-pass group: <direction>_<track>_<frame>")
    crid: str
    https_url: str
    s3_url: str | None
    size_bytes: int | None
    aoi_coverage: float = Field(description="Fraction of the AOI inside the footprint (0-1)")
    footprint: dict[str, Any] = Field(description="GeoJSON footprint, EPSG:4326")


class TrackGroup(BaseModel):
    track_key: str
    flight_direction: str
    track: int
    frame: int
    n_observations: int
    mean_aoi_coverage: float
    granule_ids: list[str] = Field(description="Sorted oldest -> newest")


class AOIInfo(BaseModel):
    wkt: str
    bounds: list[float]
    area_km2: float


class DiscoveryResponse(BaseModel):
    aoi: AOIInfo
    start_date: date
    end_date: date
    n_observations: int
    observations: list[Observation]
    tracks: list[TrackGroup] = Field(
        description="Observations grouped by repeat-pass geometry, best coverage first. "
        "Pairs for change detection should come from the same track."
    )
