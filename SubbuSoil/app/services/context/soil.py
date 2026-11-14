"""Topsoil (0-5 cm) properties from ISRIC SoilGrids 2.0 (public COGs/VRTs),
warped onto the SME2 grid with average resampling (SoilGrids is 250 m).

Units after conversion: sand/clay/silt in %, soc in g/kg.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

SOILGRIDS = "/vsicurl/https://files.isric.org/soilgrids/latest/data/{p}/{p}_0-5cm_mean.vrt"
PROPERTIES = {"sand": 0.1, "clay": 0.1, "silt": 0.1, "soc": 0.1}  # g/kg -> %, dg/kg -> g/kg
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.vrt,.ovr",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MAX_RETRY": "3",
}


def _read(prop: str, transform, width: int, height: int) -> np.ndarray:
    with rasterio.Env(**GDAL_ENV), rasterio.open(SOILGRIDS.format(p=prop)) as src, WarpedVRT(
        src, crs="EPSG:6933", transform=transform, width=width, height=height, resampling=Resampling.average,
    ) as vrt:
        a = vrt.read(1).astype("float32")
        if src.nodata is not None:
            a[a == src.nodata] = np.nan
        a[a <= 0] = np.nan
    return a * PROPERTIES[prop]


def soil_on_grid(transform, width: int, height: int) -> dict[str, np.ndarray]:
    with ThreadPoolExecutor(max_workers=len(PROPERTIES)) as pool:
        arrays = list(pool.map(lambda p: _read(p, transform, width, height), PROPERTIES))
    return dict(zip(PROPERTIES, arrays))


def texture_class(sand: float, clay: float) -> str:
    """USDA texture triangle (simplified)."""
    silt = 100 - sand - clay
    if clay >= 40:
        return "clay" if silt < 40 and sand <= 45 else ("silty clay" if silt >= 40 else "sandy clay")
    if clay >= 27:
        return "clay loam" if 20 < sand <= 45 else ("silty clay loam" if sand <= 20 else "sandy clay loam")
    if clay >= 20 and sand > 45:
        return "sandy clay loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if silt >= 50:
        return "silt loam"
    if sand >= 85:
        return "sand"
    if sand >= 70:
        return "loamy sand"
    if sand >= 52 or (clay < 7 and silt < 50):
        return "sandy loam"
    return "loam"
