"""Area-of-interest parsing and geometry helpers (EPSG:4326 input)."""
from functools import lru_cache

import numpy as np
import shapely

from pyproj import Transformer
from shapely import wkt as shapely_wkt
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

# EASE-Grid 2.0 global, equal-area — also the native CRS of NISAR SME2 grids
EQUAL_AREA_EPSG = 6933


class InvalidAOI(ValueError):
    pass


@lru_cache
def _to_equal_area() -> Transformer:
    return Transformer.from_crs(4326, EQUAL_AREA_EPSG, always_xy=True)


def parse_aoi(
    bbox: list[float] | None = None,
    geometry: dict | None = None,
    wkt: str | None = None,
) -> BaseGeometry:
    try:
        if bbox is not None:
            west, south, east, north = bbox
            if not (west < east and south < north):
                raise InvalidAOI("bbox must be [west, south, east, north] with west<east, south<north")
            geom = box(west, south, east, north)
        elif geometry is not None:
            geom = shape(geometry)
        elif wkt is not None:
            geom = shapely_wkt.loads(wkt)
        else:
            raise InvalidAOI("No AOI given")
    except InvalidAOI:
        raise
    except Exception as e:  # malformed GeoJSON / WKT
        raise InvalidAOI(f"Could not parse AOI: {e}") from e

    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise InvalidAOI(f"AOI must be a Polygon or MultiPolygon, got {geom.geom_type}")
    if geom.is_empty or not geom.is_valid:
        raise InvalidAOI("AOI geometry is empty or invalid (self-intersecting?)")
    w, s, e, n = geom.bounds
    if w < -180 or e > 180 or s < -90 or n > 90:
        raise InvalidAOI("AOI must be in EPSG:4326 lon/lat degrees")
    return geom


def to_equal_area(geom: BaseGeometry) -> BaseGeometry:
    tf = _to_equal_area()
    return shapely.transform(
        geom, lambda xy: np.column_stack(tf.transform(xy[:, 0], xy[:, 1]))
    )


def area_km2(geom: BaseGeometry) -> float:
    return to_equal_area(geom).area / 1e6


def coverage_fraction(aoi: BaseGeometry, footprint: BaseGeometry) -> float:
    """Fraction of the AOI's area that lies inside the footprint (equal-area)."""
    aoi_ea = to_equal_area(aoi)
    if aoi_ea.area == 0:
        return 0.0
    inter = aoi_ea.intersection(to_equal_area(footprint.buffer(0)))
    return round(min(1.0, inter.area / aoi_ea.area), 4)
