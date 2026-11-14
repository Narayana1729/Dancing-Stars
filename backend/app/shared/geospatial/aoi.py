from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.validation import explain_validity

from app.shared.geospatial.bbox import BoundingBox
from app.shared.geospatial.transform import PyprojGeoTransformer


INDIA_BOUNDS = BoundingBox(west=68.0, south=6.5, east=97.5, north=37.5)
MAX_AOI_AREA_KM2 = 500_000.0  # Limit to 500,000 km² to prevent unbounded memory allocation
MIN_AOI_AREA_HA = 0.01        # Minimum 100 m² (0.01 ha)


@dataclass
class GridSpecification:
    """Target rasterization and processing grid specification in projected CRS."""
    crs: str
    bounds_projected: Tuple[float, float, float, float]  # min_x, min_y, max_x, max_y
    pixel_spacing: Tuple[float, float]                   # (dx, dy) in meters
    width_pixels: int
    height_pixels: int
    origin: Tuple[float, float]                          # (origin_x, origin_y) top-left


@dataclass
class AreaOfInterest:
    """Configurable Area of Interest (AOI) anywhere in India for satellite monitoring."""
    geometry_geojson: Dict[str, Any]
    name: str = "Custom AOI"
    description: str = ""
    aoi_id: str = "custom_aoi"
    
    # Internal computed attributes
    _shapely_geom: Any = field(init=False, repr=False)
    _bbox: BoundingBox = field(init=False, repr=False)
    _area_km2: float = field(init=False, repr=False)
    _transformer: PyprojGeoTransformer = field(default_factory=PyprojGeoTransformer, init=False, repr=False)

    def __post_init__(self) -> None:
        # 1. Parse geometry
        try:
            self._shapely_geom = shape(self.geometry_geojson)
        except Exception as e:
            raise ValueError(f"Invalid GeoJSON geometry: {e}") from e

        if not isinstance(self._shapely_geom, (Polygon, MultiPolygon)):
            raise ValueError(f"AOI geometry must be Polygon or MultiPolygon, got {self._shapely_geom.geom_type}")

        if not self._shapely_geom.is_valid:
            reason = explain_validity(self._shapely_geom)
            # Try buffer(0) fix if minor topology error
            fixed_geom = self._shapely_geom.buffer(0)
            if fixed_geom.is_valid and isinstance(fixed_geom, (Polygon, MultiPolygon)):
                self._shapely_geom = fixed_geom
            else:
                raise ValueError(f"Geometry is topologically invalid: {reason}")

        min_lon, min_lat, max_lon, max_lat = self._shapely_geom.bounds
        self._bbox = BoundingBox(west=float(min_lon), south=float(min_lat), east=float(max_lon), north=float(max_lat))

        # 2. Check bounds within India extent
        if not self._bbox.intersects(INDIA_BOUNDS):
            raise ValueError(
                f"AOI bounding box ({self._bbox.west:.2f}E to {self._bbox.east:.2f}E, "
                f"{self._bbox.south:.2f}N to {self._bbox.north:.2f}N) lies outside India territory "
                f"(68.0E to 97.5E, 6.5N to 37.5N)."
            )

        # 3. Compute metric area in local UTM
        self._area_km2 = self._transformer.compute_projected_area_km2(self._shapely_geom, crs="EPSG:4326")
        
        area_ha = self._area_km2 * 100.0
        if area_ha < MIN_AOI_AREA_HA:
            raise ValueError(f"AOI area is too small ({area_ha:.4f} ha). Minimum allowed is {MIN_AOI_AREA_HA} ha.")
        if self._area_km2 > MAX_AOI_AREA_KM2:
            raise ValueError(f"AOI area ({self._area_km2:.1f} km²) exceeds max allowed limit ({MAX_AOI_AREA_KM2} km²).")

    @classmethod
    def from_bbox(
        cls,
        bbox: Union[BoundingBox, Tuple[float, float, float, float]],
        name: str = "Custom BBox AOI",
        aoi_id: str = "custom_bbox_aoi",
        description: str = "",
    ) -> AreaOfInterest:
        """Create an AOI directly from a BoundingBox or (west, south, east, north) tuple."""
        if isinstance(bbox, tuple):
            w, s, e, n = bbox
            bbox_obj = BoundingBox(west=w, south=s, east=e, north=n)
        else:
            bbox_obj = bbox
        return cls(
            geometry_geojson=bbox_obj.to_geojson(),
            name=name,
            aoi_id=aoi_id,
            description=description,
        )

    @classmethod
    def from_coordinates(
        cls,
        coordinates: List[List[Tuple[float, float]]],
        name: str = "Custom Polygon AOI",
        aoi_id: str = "custom_poly_aoi",
        description: str = "",
    ) -> AreaOfInterest:
        """Create an AOI from a list of coordinate rings [[(lon, lat), ...]]."""
        geojson = {
            "type": "Polygon",
            "coordinates": coordinates,
        }
        return cls(geometry_geojson=geojson, name=name, aoi_id=aoi_id, description=description)

    @property
    def bbox(self) -> BoundingBox:
        """WGS84 BoundingBox."""
        return self._bbox

    @property
    def area_km2(self) -> float:
        """Metric area in square kilometers."""
        return round(self._area_km2, 4)

    @property
    def area_ha(self) -> float:
        """Metric area in hectares."""
        return round(self._area_km2 * 100.0, 2)

    @property
    def centroid(self) -> Tuple[float, float]:
        """Centroid coordinates in WGS84 (longitude, latitude)."""
        c = self._shapely_geom.centroid
        return (round(float(c.x), 6), round(float(c.y), 6))

    @property
    def utm_zone(self) -> int:
        """Local UTM zone number based on centroid longitude."""
        lon = self.centroid[0]
        return int(math.floor((lon + 180.0) / 6.0)) + 1

    @property
    def utm_crs(self) -> str:
        """Local UTM EPSG code (e.g. 'EPSG:32645')."""
        zone = self.utm_zone
        lat = self.centroid[1]
        return f"EPSG:{32600 + zone}" if lat >= 0 else f"EPSG:{32700 + zone}"

    @property
    def shapely_geometry(self) -> Any:
        """Underlying Shapely geometry."""
        return self._shapely_geom

    def to_grid_spec(self, pixel_spacing_m: float = 80.0) -> GridSpecification:
        """Generate grid dimensions and projected coordinates for rasterization."""
        utm_crs = self.utm_crs
        min_x, min_y, max_x, max_y = self._transformer.reproject_bbox(self._bbox, utm_crs)

        # Snap bounds to pixel spacing multiples
        snap_min_x = math.floor(min_x / pixel_spacing_m) * pixel_spacing_m
        snap_max_x = math.ceil(max_x / pixel_spacing_m) * pixel_spacing_m
        snap_min_y = math.floor(min_y / pixel_spacing_m) * pixel_spacing_m
        snap_max_y = math.ceil(max_y / pixel_spacing_m) * pixel_spacing_m

        width = int(round((snap_max_x - snap_min_x) / pixel_spacing_m))
        height = int(round((snap_max_y - snap_min_y) / pixel_spacing_m))

        return GridSpecification(
            crs=utm_crs,
            bounds_projected=(snap_min_x, snap_min_y, snap_max_x, snap_max_y),
            pixel_spacing=(pixel_spacing_m, pixel_spacing_m),
            width_pixels=max(1, width),
            height_pixels=max(1, height),
            origin=(snap_min_x, snap_max_y),  # Origin is top-left in UTM (min_x, max_y)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializable dictionary representation."""
        return {
            "aoi_id": self.aoi_id,
            "name": self.name,
            "description": self.description,
            "area_km2": self.area_km2,
            "area_ha": self.area_ha,
            "centroid": {"longitude": self.centroid[0], "latitude": self.centroid[1]},
            "bbox": self._bbox.to_dict(),
            "utm_zone": self.utm_zone,
            "utm_crs": self.utm_crs,
            "geometry": self.geometry_geojson,
        }
