"""Satellite acquisition interfaces. No provider is implemented in Phase 1."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import Enum

from app.shared.geospatial.bbox import BoundingBox


class Mission(str, Enum):
    NISAR = "NISAR"
    SENTINEL_1 = "SENTINEL-1"


class SarProduct(str, Enum):
    GCOV = "GCOV"  # geocoded polarimetric covariance, radiometrically terrain corrected
    GSLC = "GSLC"  # geocoded single-look complex
    GOFF = "GOFF"  # geocoded pixel offsets
    GUNW = "GUNW"  # geocoded unwrapped interferogram
    GRD_HD = "GRD_HD"  # Sentinel-1 ground-range detected, high-res (supplementary source)


# GCOV: backscatter analysis and disturbance detection.
# GSLC: backscatter amplitude analysis and comparison.
# GOFF / GUNW are deformation/offset products, not default for forest monitoring.
DEFAULT_FOREST_PRODUCTS: tuple[SarProduct, ...] = (SarProduct.GCOV, SarProduct.GSLC)
NON_DEFAULT_FOREST_PRODUCTS: tuple[SarProduct, ...] = (SarProduct.GOFF, SarProduct.GUNW)


@dataclass(frozen=True)
class SceneQuery:
    bbox: BoundingBox
    start: date
    end: date
    mission: Mission = Mission.NISAR
    product: SarProduct = SarProduct.GCOV

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("start date must not be after end date")


@dataclass(frozen=True)
class SceneRecord:
    """Catalogue entry describing a granule. Never contains pixel data."""
    scene_id: str
    mission: Mission
    product: SarProduct
    acquired: date
    download_url: str | None = None


class SatelliteProvider(ABC):
    """Contract for NISAR / Sentinel-1 acquisition (Phase 2+)."""

    @abstractmethod
    def search(self, query: SceneQuery) -> list[SceneRecord]: ...

    @abstractmethod
    def download(self, scene: SceneRecord, dest_dir: str) -> str:
        """Download a granule and return the local path."""

