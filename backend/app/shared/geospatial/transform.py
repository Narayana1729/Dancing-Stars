from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, Sequence, Tuple
import pyproj
from shapely.geometry import shape, mapping
from shapely.ops import transform as shapely_transform

from app.shared.geospatial.bbox import BoundingBox


class GeoTransformer(ABC):
    """Geospatial transformations interface."""

    @abstractmethod
    def reproject_bbox(self, bbox: BoundingBox, target_crs: str) -> tuple[float, float, float, float]: ...

    @abstractmethod
    def pixel_area_km2(self, crs: str, pixel_size: tuple[float, float], lat: float = 0.0) -> float: ...


class PyprojGeoTransformer(GeoTransformer):
    """High-precision reprojection and geodesic calculations using PyProj and Shapely."""

    def __init__(self) -> None:
        self._transformers: dict[tuple[str, str], pyproj.Transformer] = {}

    def get_transformer(self, source_crs: str, target_crs: str) -> pyproj.Transformer:
        """Cache and retrieve pyproj Transformer."""
        key = (source_crs.upper(), target_crs.upper())
        if key not in self._transformers:
            self._transformers[key] = pyproj.Transformer.from_crs(
                source_crs, target_crs, always_xy=True
            )
        return self._transformers[key]

    def reproject_bbox(self, bbox: BoundingBox, target_crs: str) -> tuple[float, float, float, float]:
        """Reproject WGS84 BoundingBox into target CRS (min_x, min_y, max_x, max_y)."""
        transformer = self.get_transformer("EPSG:4326", target_crs)
        # Transform the 4 corners of the bbox
        corners_lon = [bbox.west, bbox.east, bbox.east, bbox.west]
        corners_lat = [bbox.south, bbox.south, bbox.north, bbox.north]
        xs, ys = transformer.transform(corners_lon, corners_lat)
        return (min(xs), min(ys), max(xs), max(ys))

    def reproject_point(self, lon: float, lat: float, target_crs: str, source_crs: str = "EPSG:4326") -> tuple[float, float]:
        """Reproject a single coordinate point (x, y)."""
        transformer = self.get_transformer(source_crs, target_crs)
        x, y = transformer.transform(lon, lat)
        return (float(x), float(y))

    def reproject_geometry(self, geometry: Any, source_crs: str, target_crs: str) -> Any:
        """Reproject a Shapely geometry from source_crs to target_crs."""
        if source_crs.upper() == target_crs.upper():
            return geometry
        transformer = self.get_transformer(source_crs, target_crs)
        try:
            import numpy as np
            import shapely
            if hasattr(shapely, "transform"):
                return shapely.transform(
                    geometry,
                    lambda coords: np.column_stack(transformer.transform(coords[:, 0], coords[:, 1])),
                )
        except Exception:
            pass
        return shapely_transform(transformer.transform, geometry)

    def pixel_area_km2(self, crs: str, pixel_size: tuple[float, float], lat: float = 0.0) -> float:
        """Compute surface area of a single pixel in square kilometers."""
        dx, dy = abs(pixel_size[0]), abs(pixel_size[1])
        crs_upper = crs.upper()

        if "4326" in crs_upper:
            # Degrees: compute metric width and height at given latitude
            # 1 deg lat ~= 111.132 km; 1 deg lon ~= 111.320 * cos(lat) km
            lat_rad = math.radians(lat)
            width_km = dx * 111.320 * math.cos(lat_rad)
            height_km = dy * 111.132
            return width_km * height_km
        else:
            # Projected CRS (assumed in meters, e.g. UTM)
            area_m2 = dx * dy
            return area_m2 / 1_000_000.0

    def pixel_area_ha(self, crs: str, pixel_size: tuple[float, float], lat: float = 0.0) -> float:
        """Compute surface area of a single pixel in hectares (1 km² = 100 ha)."""
        return self.pixel_area_km2(crs=crs, pixel_size=pixel_size, lat=lat) * 100.0

    def compute_projected_area_km2(self, geometry: Any, crs: str = "EPSG:4326") -> float:
        """Compute the metric area of a geometry in km² by reprojecting to its local UTM zone."""
        from shapely.geometry import shape

        geom = shape(geometry) if isinstance(geometry, dict) else geometry
        if "4326" in crs.upper():
            centroid = geom.centroid
            zone = int(math.floor((centroid.x + 180.0) / 6.0)) + 1
            utm_crs = f"EPSG:{32600 + zone}" if centroid.y >= 0 else f"EPSG:{32700 + zone}"
            projected_geom = self.reproject_geometry(geom, source_crs="EPSG:4326", target_crs=utm_crs)
            return float(projected_geom.area) / 1_000_000.0
        else:
            # Already in projected metric CRS
            return float(geom.area) / 1_000_000.0
