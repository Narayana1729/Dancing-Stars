from __future__ import annotations

from dataclasses import dataclass


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

