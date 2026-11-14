from __future__ import annotations

from abc import ABC, abstractmethod

from app.shared.geospatial.bbox import BoundingBox


class GeoTransformer(ABC):
    """Geospatial transformations (Phase 2+)."""

    @abstractmethod
    def reproject_bbox(self, bbox: BoundingBox, target_crs: str) -> tuple[float, float, float, float]: ...

    @abstractmethod
    def pixel_area_km2(self, crs: str, pixel_size: tuple[float, float], lat: float) -> float: ...

