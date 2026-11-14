"""Sentinel-2 L2A NDVI on the SME2 grid (Earth Search STAC, public COGs on AWS).

For each NISAR date we pick the Sentinel-2 acquisition day within +/- window
that covers the AOI with the least cloud (ties -> closest in time), read red,
nir and the scene classification (SCL) of every tile from that day directly
onto the 200 m EASE grid (GDAL warps from the COG overviews, so only a few MB
are read), mask cloud/shadow/snow/water via SCL, and compute NDVI.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import numpy as np
import rasterio
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
SCL_VALID = (4, 5, 7)  # vegetation, bare soil, unclassified
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MAX_RETRY": "3", "GDAL_HTTP_RETRY_DELAY": "1"}


class VegetationError(RuntimeError):
    pass


def _scale_offset(item, band: str) -> tuple[float, float]:
    """Reflectance = DN * scale + offset.

    Sentinel-2 processing baseline >= 04.00 adds a +1000 DN offset (BOA_ADD_OFFSET).
    Earth Search advertises offset -0.1 in raster:bands, but when
    `earthsearch:boa_offset_applied` is true the pixel values have ALREADY been
    corrected, so applying the offset again would make red reflectance negative
    and push NDVI to ~1.
    """
    rb = (item.assets[band].extra_fields.get("raster:bands") or [{}])[0]
    scale = float(rb.get("scale", 1e-4))
    offset = float(rb.get("offset", 0.0))
    if item.properties.get("earthsearch:boa_offset_applied"):
        offset = 0.0
    return scale, offset


def choose_scene(
    aoi: BaseGeometry, t: datetime, window_days: int, max_cloud: float
) -> tuple[str, list, float, float]:
    start, end = (t - timedelta(days=window_days)).date(), (t + timedelta(days=window_days)).date()
    items = list(Client.open(STAC_URL).search(
        collections=[COLLECTION], intersects=aoi.__geo_interface__,
        datetime=f"{start}/{end}", query={"eo:cloud_cover": {"lt": max_cloud}}, max_items=200,
    ).items())
    if not items:
        raise VegetationError(f"No Sentinel-2 scene with cloud < {max_cloud}% within +/-{window_days} days of {t.date()}")
    by_day = defaultdict(list)
    for it in items:
        by_day[it.datetime.date()].append(it)
    best = None
    for day, its in by_day.items():
        cover = aoi.intersection(shape(its[0].geometry))
        for it in its[1:]:
            cover = cover.union(aoi.intersection(shape(it.geometry)))
        coverage = cover.area / aoi.area
        cloud = float(np.mean([it.properties.get("eo:cloud_cover", 100) for it in its]))
        key = (coverage < 0.9, cloud, abs((day - t.date()).days))
        if best is None or key < best[0]:
            best = (key, day, its, coverage, cloud)
    _, day, its, coverage, cloud = best
    return day.isoformat(), its, round(coverage, 3), round(cloud, 2)


def _read(href: str, transform, width: int, height: int, resampling: Resampling) -> np.ndarray:
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src, WarpedVRT(
        src, crs="EPSG:6933", transform=transform, width=width, height=height,
        resampling=resampling, nodata=0,
    ) as vrt:
        return vrt.read(1)


def ndvi_on_grid(aoi: BaseGeometry, t: datetime, transform, width: int, height: int,
                 window_days: int = 15, max_cloud: float = 60) -> tuple[np.ndarray, dict]:
    day, items, coverage, cloud = choose_scene(aoi, t, window_days, max_cloud)
    jobs = []
    for it in items:
        for band, rs in (("red", Resampling.average), ("nir", Resampling.average), ("scl", Resampling.mode)):
            jobs.append((it, band, rs))
    with ThreadPoolExecutor(max_workers=6) as pool:
        arrays = list(pool.map(lambda j: _read(j[0].assets[j[1]].href, transform, width, height, j[2]), jobs))

    ndvi = np.full((height, width), np.nan, "float32")
    n_cloudy = 0
    for k, it in enumerate(items):
        red_dn, nir_dn, scl = arrays[3 * k], arrays[3 * k + 1], arrays[3 * k + 2]
        rs, ro = _scale_offset(it, "red")
        ns, no = _scale_offset(it, "nir")
        red = red_dn.astype("float32") * rs + ro
        nir = nir_dn.astype("float32") * ns + no
        has = (red_dn > 0) & (nir_dn > 0)
        ok = has & np.isin(scl, SCL_VALID)
        n_cloudy += int((has & ~ok).sum())
        with np.errstate(divide="ignore", invalid="ignore"):
            v = (nir - red) / (nir + red)
        fill = ok & np.isnan(ndvi) & np.isfinite(v)
        ndvi[fill] = np.clip(v[fill], -1, 1)

    meta = {
        "date": day,
        "days_from_nisar": (datetime.fromisoformat(day).date() - t.date()).days,
        "tiles": [it.id for it in items],
        "scene_cloud_cover_pct": cloud,
        "aoi_coverage": coverage,
        "masked_pixels": n_cloudy,
    }
    return ndvi, meta
