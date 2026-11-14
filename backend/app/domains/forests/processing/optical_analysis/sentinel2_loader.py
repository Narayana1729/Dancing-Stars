"""Loader and mosaic engine for acquired Sentinel-2 L2A observations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import zipfile
import numpy as np
import rasterio
from rasterio.transform import Affine, from_origin
from rasterio.windows import from_bounds
from scipy.ndimage import zoom

# Default Similipal ROI bounds in EPSG:32645
SIMILIPAL_X_MIN = 401640.0
SIMILIPAL_X_MAX = 463960.0
SIMILIPAL_Y_MIN = 2372200.0
SIMILIPAL_Y_MAX = 2438360.0

# Boundary split latitude between T45QVE (north) and T45QVD (south) in EPSG:32645
TILE_SPLIT_Y = 2390220.0

# Sentinel-2 Baseline 04.00+ quantification parameters
BOA_QUANTIFICATION_VALUE = 10000.0
BOA_ADD_OFFSET = -1000.0


@dataclass
class Sentinel2Mosaic:
    """Seamless mosaic of Sentinel-2 L2A surface reflectance across Similipal ROI."""
    acquisition_date: str
    relative_orbit: str
    crs: str
    transform: Affine
    shape_10m: Tuple[int, int]
    # Calibrated BOA surface reflectance (float32 in [0.0, 1.0]) at 10 m resolution
    b04: np.ndarray  # Red (665 nm)
    b08: np.ndarray  # NIR Broad (842 nm)
    b8a: np.ndarray  # NIR Narrow (865 nm, upsampled from 20 m)
    b11: np.ndarray  # SWIR-1 (1610 nm, upsampled from 20 m)
    b12: np.ndarray  # SWIR-2 (2190 nm, upsampled from 20 m)
    # Scene Classification Layer (uint8, upsampled from 20 m)
    scl: np.ndarray
    # Quality validity mask (bool): clear-sky observation without cloud, shadow, or cirrus
    valid_mask: np.ndarray


def find_band_in_zip(zip_path: Path, band_suffix: str) -> str:
    """Find the internal SAFE archive file path ending with the specified band suffix."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        matching = [n for n in zf.namelist() if n.endswith(band_suffix)]
        if not matching:
            raise FileNotFoundError(f"Band with suffix '{band_suffix}' not found in {zip_path.name}")
        return matching[0]


def read_band_slice(
    zip_path: Path,
    band_suffix: str,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> Tuple[np.ndarray, Affine]:
    """Read an exact spatial window from a zipped JP2 image via GDAL /vsizip/."""
    internal_path = find_band_in_zip(zip_path, band_suffix)
    vsi_url = f"/vsizip/{zip_path}/{internal_path}"
    with rasterio.open(vsi_url) as src:
        win = from_bounds(x_min, y_min, x_max, y_max, src.transform)
        # Snap window to integer pixel coordinates to avoid partial pixel shifts
        win_int = win.round_shape()
        arr = src.read(1, window=win_int)
        win_transform = rasterio.windows.transform(win_int, src.transform)
        return arr, win_transform


def load_sentinel2_mosaic_date(
    raw_dir: Path,
    date_str: str,  # "2026-03-02" or "2026-04-16"
    x_min: float = SIMILIPAL_X_MIN,
    x_max: float = SIMILIPAL_X_MAX,
    y_min: float = SIMILIPAL_Y_MIN,
    y_max: float = SIMILIPAL_Y_MAX,
) -> Sentinel2Mosaic:
    """Construct a seamless, orthorectified Sentinel-2 mosaic over Similipal ROI.

    Stitches Tile T45QVE (north) and Tile T45QVD (south) along Y = 2390220.0 m.
    Applies Sentinel-2 Baseline 05.12 physical surface reflectance offset:
      rho = (DN - 1000) / 10000.0
    Generates Sen2Cor Scene Classification Layer (SCL) cloud/shadow mask.
    """
    compact_date = date_str.replace("-", "")
    zip_ve = None
    zip_vd = None

    for z in raw_dir.glob("*.zip"):
        name = z.name
        if compact_date in name:
            if "T45QVE" in name:
                zip_ve = z
            elif "T45QVD" in name:
                zip_vd = z

    if zip_ve is None or zip_vd is None:
        raise FileNotFoundError(
            f"Missing required Sentinel-2 pair for date {date_str}. "
            f"Found T45QVE: {zip_ve is not None}, T45QVD: {zip_vd is not None} in {raw_dir}"
        )

    # 1. Read 10 m Bands: B04 (Red) and B08 (NIR)
    # T45QVE: North slice [TILE_SPLIT_Y, y_max] -> [2390220.0, 2438360.0]
    # T45QVD: South slice [y_min, TILE_SPLIT_Y] -> [2372200.0, 2390220.0]
    b04_ve, transform_10m = read_band_slice(zip_ve, "_B04_10m.jp2", x_min, x_max, TILE_SPLIT_Y, y_max)
    b04_vd, _ = read_band_slice(zip_vd, "_B04_10m.jp2", x_min, x_max, y_min, TILE_SPLIT_Y)
    b04_raw = np.vstack([b04_ve, b04_vd])

    b08_ve, _ = read_band_slice(zip_ve, "_B08_10m.jp2", x_min, x_max, TILE_SPLIT_Y, y_max)
    b08_vd, _ = read_band_slice(zip_vd, "_B08_10m.jp2", x_min, x_max, y_min, TILE_SPLIT_Y)
    b08_raw = np.vstack([b08_ve, b08_vd])

    target_shape_10m = b04_raw.shape  # Expected: (6616, 6232)

    # 2. Read 20 m Bands: B8A (Narrow NIR), B11 (SWIR-1), B12 (SWIR-2), SCL
    b8a_ve, _ = read_band_slice(zip_ve, "_B8A_20m.jp2", x_min, x_max, TILE_SPLIT_Y, y_max)
    b8a_vd, _ = read_band_slice(zip_vd, "_B8A_20m.jp2", x_min, x_max, y_min, TILE_SPLIT_Y)
    b8a_raw_20m = np.vstack([b8a_ve, b8a_vd])

    b11_ve, _ = read_band_slice(zip_ve, "_B11_20m.jp2", x_min, x_max, TILE_SPLIT_Y, y_max)
    b11_vd, _ = read_band_slice(zip_vd, "_B11_20m.jp2", x_min, x_max, y_min, TILE_SPLIT_Y)
    b11_raw_20m = np.vstack([b11_ve, b11_vd])

    b12_ve, _ = read_band_slice(zip_ve, "_B12_20m.jp2", x_min, x_max, TILE_SPLIT_Y, y_max)
    b12_vd, _ = read_band_slice(zip_vd, "_B12_20m.jp2", x_min, x_max, y_min, TILE_SPLIT_Y)
    b12_raw_20m = np.vstack([b12_ve, b12_vd])

    scl_ve, _ = read_band_slice(zip_ve, "_SCL_20m.jp2", x_min, x_max, TILE_SPLIT_Y, y_max)
    scl_vd, _ = read_band_slice(zip_vd, "_SCL_20m.jp2", x_min, x_max, y_min, TILE_SPLIT_Y)
    scl_raw_20m = np.vstack([scl_ve, scl_vd])

    # 3. Upsample 20 m bands to exact 10 m shape
    zoom_y = target_shape_10m[0] / b8a_raw_20m.shape[0]
    zoom_x = target_shape_10m[1] / b8a_raw_20m.shape[1]

    # Bilinear interpolation for continuous reflectance bands
    b8a_raw = zoom(b8a_raw_20m, (zoom_y, zoom_x), order=1).astype(np.float32)
    b11_raw = zoom(b11_raw_20m, (zoom_y, zoom_x), order=1).astype(np.float32)
    b12_raw = zoom(b12_raw_20m, (zoom_y, zoom_x), order=1).astype(np.float32)
    # Nearest neighbor interpolation for discrete categorical SCL
    scl = zoom(scl_raw_20m, (zoom_y, zoom_x), order=0).astype(np.uint8)

    # 4. Calibrate to physical BOA surface reflectance
    # rho = (DN - 1000) / 10000.0, clipped to [0.0, 1.0]
    def _calibrate_boa(raw_dn: np.ndarray) -> np.ndarray:
        # 0 in raw DN indicates missing/no data in Sentinel-2 L2A
        nodata_mask = (raw_dn == 0)
        refl = (raw_dn.astype(np.float32) + BOA_ADD_OFFSET) / BOA_QUANTIFICATION_VALUE
        refl = np.clip(refl, 0.0, 1.0)
        refl[nodata_mask] = np.nan
        return refl

    b04 = _calibrate_boa(b04_raw)
    b08 = _calibrate_boa(b08_raw)
    b8a = _calibrate_boa(b8a_raw)
    b11 = _calibrate_boa(b11_raw)
    b12 = _calibrate_boa(b12_raw)

    # 5. Formulate SCL clear-sky quality mask
    # SCL Classes:
    #   0: No Data (mask)
    #   1: Saturated / Defective (mask)
    #   2: Dark Area Pixels (cast topographic shadows from steep ridges, retain)
    #   3: Cloud Shadows (mask)
    #   4: Vegetation (valid)
    #   5: Not-Vegetated / Bare Soil (valid)
    #   6: Water (valid)
    #   7: Unclassified (mask)
    #   8: Cloud Medium Probability (mask)
    #   9: Cloud High Probability (mask)
    #  10: Thin Cirrus (mask)
    #  11: Snow / Ice (mask)
    valid_scl = np.isin(scl, [2, 4, 5, 6])
    valid_spectral = (
        np.isfinite(b04)
        & np.isfinite(b08)
        & np.isfinite(b8a)
        & np.isfinite(b11)
        & np.isfinite(b12)
        & (b04 > 0.0)
        & (b08 > 0.0)
    )
    valid_mask = valid_scl & valid_spectral

    # Mask invalid pixels in reflectance arrays with NaN
    b04[~valid_mask] = np.nan
    b08[~valid_mask] = np.nan
    b8a[~valid_mask] = np.nan
    b11[~valid_mask] = np.nan
    b12[~valid_mask] = np.nan

    # Target raster transform derived from Similipal ROI bounds
    target_transform = from_origin(x_min, y_max, 10.0, 10.0)

    return Sentinel2Mosaic(
        acquisition_date=date_str,
        relative_orbit="R076",
        crs="EPSG:32645",
        transform=target_transform,
        shape_10m=target_shape_10m,
        b04=b04,
        b08=b08,
        b8a=b8a,
        b11=b11,
        b12=b12,
        scl=scl,
        valid_mask=valid_mask,
    )

