from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class BoundingBox:
    """WGS84 bounding box in degrees."""
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if not (-180 <= self.west <= 180 and -180 <= self.east <= 180):
            raise ValueError("longitude must be within [-180, 180]")
        if not (-90 <= self.south <= 90 and -90 <= self.north <= 90):
            raise ValueError("latitude must be within [-90, 90]")
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("bounding box must have west < east and south < north")

    @property
    def center_lon(self) -> float:
        """Central longitude in degrees."""
        return (self.west + self.east) / 2.0

    @property
    def center_lat(self) -> float:
        """Central latitude in degrees."""
        return (self.south + self.north) / 2.0

    @property
    def utm_zone(self) -> int:
        """Calculates UTM zone number (1 to 60) from central longitude."""
        return int(math.floor((self.center_lon + 180.0) / 6.0)) + 1

    @property
    def utm_crs(self) -> str:
        """Returns appropriate UTM CRS string (e.g., 'EPSG:32645')."""
        zone = self.utm_zone
        if self.center_lat >= 0:
            return f"EPSG:{32600 + zone}"
        return f"EPSG:{32700 + zone}"

    def contains_point(self, lon: float, lat: float) -> bool:
        """Check if coordinates fall inside or on boundary of this bounding box."""
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    def intersects(self, other: BoundingBox) -> bool:
        """Check if another BoundingBox intersects this one."""
        return not (
            self.east < other.west
            or self.west > other.east
            or self.north < other.south
            or self.south > other.north
        )

    def intersection(self, other: BoundingBox) -> Optional[BoundingBox]:
        """Compute the intersection of this bounding box with another, if any."""
        if not self.intersects(other):
            return None
        inter_west = max(self.west, other.west)
        inter_south = max(self.south, other.south)
        inter_east = min(self.east, other.east)
        inter_north = min(self.north, other.north)
        if inter_west >= inter_east or inter_south >= inter_north:
            return None
        return BoundingBox(west=inter_west, south=inter_south, east=inter_east, north=inter_north)

    def is_within_india(self) -> bool:
        """Check whether the bounding box intersects the geographic territory of India."""
        # Geographic bounds of India: 68.0E to 97.5E, 6.5N to 37.5N
        india_bbox = BoundingBox(west=68.0, south=6.5, east=97.5, north=37.5)
        return self.intersects(india_bbox)

    def to_dict(self) -> dict[str, float]:
        """Dictionary representation."""
        return {
            "west": self.west,
            "south": self.south,
            "east": self.east,
            "north": self.north,
        }

    def to_geojson(self) -> dict[str, Any]:
        """Returns GeoJSON Polygon geometry representing the bounding box."""
        coords = [
            [
                [self.west, self.south],
                [self.east, self.south],
                [self.east, self.north],
                [self.west, self.north],
                [self.west, self.south],
            ]
        ]
        return {
            "type": "Polygon",
            "coordinates": coords,
        }

    def to_polygon(self) -> Any:
        """Returns a Shapely Polygon."""
        from shapely.geometry import box
        return box(self.west, self.south, self.east, self.north)
