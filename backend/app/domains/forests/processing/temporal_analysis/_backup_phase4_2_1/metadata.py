"""Metadata schemas and data models for multi-temporal NISAR processing."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
from rasterio.transform import Affine


@dataclass(frozen=True)
class AcquisitionMetadata:
    """Metadata describing a single NISAR L2 GCOV acquisition."""
    granule_id: str
    acquisition_time: str
    track: int
    frame: int
    orbit_pass: str
    look_direction: str
    crid: str
    frequency_band: str  # "frequencyA" or "frequencyB"
    center_frequency_hz: float
    range_bandwidth_hz: float
    near_range_incidence_deg: float
    far_range_incidence_deg: float
    range_resolution_m: float
    azimuth_resolution_m: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TemporalSeriesMetadata:
    """Metadata describing a multi-temporal NISAR processing series."""
    frequency_id: str  # "frequencyA" or "frequencyB"
    nominal_resolution_m: float
    crs: str
    transform: Affine
    window_shape: tuple[int, int]
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    acquisitions: List[AcquisitionMetadata]
    num_epochs: int
    baseline_days: List[int]  # Days relative to epoch 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["transform"] = list(self.transform)
        return d


@dataclass(frozen=True)
class FeatureDistributionStats:
    """Summary descriptive statistics for a scalar raster band."""
    count: int
    min: float
    max: float
    mean: float
    std: float
    median: float
    p05: float
    p25: float
    p75: float
    p95: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ZonalStats:
    """Zonal statistics for a metric stratified across Similipal management zones."""
    overall: FeatureDistributionStats
    sanctuary: Optional[FeatureDistributionStats] = None
    core: Optional[FeatureDistributionStats] = None
    outside_reserve: Optional[FeatureDistributionStats] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": self.overall.to_dict(),
            "sanctuary": self.sanctuary.to_dict() if self.sanctuary else None,
            "core": self.core.to_dict() if self.core else None,
            "outside_reserve": self.outside_reserve.to_dict() if self.outside_reserve else None,
        }


@dataclass(frozen=True)
class PipelinePerformance:
    """Runtime and memory benchmarks for processing a frequency pipeline."""
    frequency_id: str
    duration_seconds: float
    peak_ram_mb: float
    peak_ram_gb: float
    total_pixels: int
    valid_pixels: int
    valid_percentage: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

