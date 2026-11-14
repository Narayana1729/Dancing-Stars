"""Windowed loader for NISAR L2 GCOV Frequency A (10 m geocoded grid).

This module performs windowed reading of high-resolution Frequency A datasets
(40 MHz chirp bandwidth, 10 m pixel spacing) over the Similipal study area
without loading full multi-gigabyte HDF5 scene rasters into memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import h5py
import numpy as np
from rasterio.transform import Affine, from_origin

# Default Similipal ROI coordinate bounds in EPSG:32645 (UTM Zone 45N)
# Derived to align with the Frequency B bounding box at an 8:1 integer ratio
SIMILIPAL_X_MIN = 401640.0
SIMILIPAL_X_MAX = 463960.0
SIMILIPAL_Y_MIN = 2372200.0
SIMILIPAL_Y_MAX = 2438360.0

GRID_PATH_FREQ_A = "science/LSAR/GCOV/grids/frequencyA"


@dataclass(frozen=True)
class FrequencyAMetadata:
    crs: str
    pixel_spacing_x: float
    pixel_spacing_y: float
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    transform: Affine
    window_shape: Tuple[int, int]
    t0_scene_id: str
    t1_scene_id: str
    t0_acquisition_time: str
    t1_acquisition_time: str
    track: int
    frame: int
    orbit_pass: str
    processing_crid_t0: str
    processing_crid_t1: str
    center_frequency_hz: float
    range_bandwidth_hz: float
    rtc_factor_stats: Dict[str, float]


@dataclass
class FrequencyAWindow:
    metadata: FrequencyAMetadata
    # Calibrated terrain-flattened gamma-naught RTC linear power arrays
    gamma0_rtc_hh_t0: np.ndarray
    gamma0_rtc_hv_t0: np.ndarray
    gamma0_rtc_hh_t1: np.ndarray
    gamma0_rtc_hv_t1: np.ndarray
    # Quality and anomaly masks
    mask_t0: np.ndarray
    mask_t1: np.ndarray
    exception_mask_t0: np.ndarray
    exception_mask_t1: np.ndarray
    # RTC area normalization factor
    rtc_factor_t0: np.ndarray
    rtc_factor_t1: np.ndarray
    # Combined valid observation mask
    valid_mask: np.ndarray


def find_frequency_a_slice(
    h5_file: h5py.File,
    x_min: float = SIMILIPAL_X_MIN,
    x_max: float = SIMILIPAL_X_MAX,
    y_min: float = SIMILIPAL_Y_MIN,
    y_max: float = SIMILIPAL_Y_MAX,
) -> Tuple[slice, slice, np.ndarray, np.ndarray, Affine]:
    """Calculate exact array slices for the requested UTM bounding box."""
    grid = h5_file[GRID_PATH_FREQ_A]
    x_coords = grid["xCoordinates"][:]
    y_coords = grid["yCoordinates"][:]
    dx = float(grid["xCoordinateSpacing"][()])
    dy = float(grid["yCoordinateSpacing"][()])

    ix0 = int(np.searchsorted(x_coords, x_min))
    ix1 = int(np.searchsorted(x_coords, x_max))

    # yCoordinates is descending (dy is negative, -10.0 m)
    iy0 = int(np.searchsorted(-y_coords, -y_max))
    iy1 = int(np.searchsorted(-y_coords, -y_min))

    x_slice = slice(ix0, ix1)
    y_slice = slice(iy0, iy1)

    sub_x = x_coords[x_slice]
    sub_y = y_coords[y_slice]

    # Cell-edge origin for geospatial raster affine transform
    x_origin = sub_x[0] - dx / 2.0
    y_origin = sub_y[0] - dy / 2.0
    transform = from_origin(x_origin, y_origin, dx, -dy)

    return y_slice, x_slice, sub_x, sub_y, transform


def load_frequency_a_window(
    t0_path: Path,
    t1_path: Path,
    x_min: float = SIMILIPAL_X_MIN,
    x_max: float = SIMILIPAL_X_MAX,
    y_min: float = SIMILIPAL_Y_MIN,
    y_max: float = SIMILIPAL_Y_MAX,
) -> FrequencyAWindow:
    """Perform windowed read of Frequency A from two NISAR L2 GCOV products."""
    if not t0_path.exists():
        raise FileNotFoundError(f"t0 GCOV file not found: {t0_path}")
    if not t1_path.exists():
        raise FileNotFoundError(f"t1 GCOV file not found: {t1_path}")

    with h5py.File(t0_path, "r") as h0, h5py.File(t1_path, "r") as h1:
        g0 = h0[GRID_PATH_FREQ_A]
        g1 = h1[GRID_PATH_FREQ_A]

        # Verify CRS and spatial reference compatibility
        epsg0 = int(g0["projection"][()])
        epsg1 = int(g1["projection"][()])
        if epsg0 != epsg1:
            raise ValueError(f"Incompatible CRS: t0 is EPSG:{epsg0}, t1 is EPSG:{epsg1}")
        crs_str = f"EPSG:{epsg0}"

        dx0 = float(g0["xCoordinateSpacing"][()])
        dx1 = float(g1["xCoordinateSpacing"][()])
        dy0 = float(g0["yCoordinateSpacing"][()])
        dy1 = float(g1["yCoordinateSpacing"][()])
        if dx0 != dx1 or dy0 != dy1:
            raise ValueError(f"Incompatible pixel spacing: t0=({dx0},{dy0}), t1=({dx1},{dy1})")

        y_slice_0, x_slice_0, sub_x0, sub_y0, transform0 = find_frequency_a_slice(
            h0, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
        )
        y_slice_1, x_slice_1, sub_x1, sub_y1, transform1 = find_frequency_a_slice(
            h1, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
        )

        if not np.array_equal(sub_x0, sub_x1) or not np.array_equal(sub_y0, sub_y1):
            raise ValueError("Frequency A coordinate arrays do not match between t0 and t1")

        # Windowed extraction of polarimetric covariance diagonal terms (float32)
        hh0 = g0["HHHH"][y_slice_0, x_slice_0].astype(np.float32)
        hv0 = g0["HVHV"][y_slice_0, x_slice_0].astype(np.float32)
        hh1 = g1["HHHH"][y_slice_1, x_slice_1].astype(np.float32)
        hv1 = g1["HVHV"][y_slice_1, x_slice_1].astype(np.float32)

        # Quality and exception masks
        mask0 = g0["mask"][y_slice_0, x_slice_0]
        mask1 = g1["mask"][y_slice_1, x_slice_1]
        ex0 = g0["inputDataExceptionMask"][y_slice_0, x_slice_0]
        ex1 = g1["inputDataExceptionMask"][y_slice_1, x_slice_1]

        # RTC normalization factor
        rtc0 = g0["rtcGammaToSigmaFactor"][y_slice_0, x_slice_0].astype(np.float32)
        rtc1 = g1["rtcGammaToSigmaFactor"][y_slice_1, x_slice_1].astype(np.float32)

        # Metadata extraction
        def _get_str(obj: Any) -> str:
            val = obj[()]
            return val.decode("utf-8") if isinstance(val, bytes) else str(val)

        t0_scene = _get_str(h0["science/LSAR/identification/granuleId"]) if "granuleId" in h0["science/LSAR/identification"] else t0_path.stem
        t1_scene = _get_str(h1["science/LSAR/identification/granuleId"]) if "granuleId" in h1["science/LSAR/identification"] else t1_path.stem
        t0_time = _get_str(h0["science/LSAR/identification/zeroDopplerStartTime"])
        t1_time = _get_str(h1["science/LSAR/identification/zeroDopplerStartTime"])
        track = int(h0["science/LSAR/identification/trackNumber"][()])
        frame = int(h0["science/LSAR/identification/frameNumber"][()])
        orbit_pass = _get_str(h0["science/LSAR/identification/orbitPassDirection"])
        crid_t0 = _get_str(h0["science/LSAR/identification/compositeReleaseId"])
        crid_t1 = _get_str(h1["science/LSAR/identification/compositeReleaseId"])

        swath_meta = h0["science/LSAR/GCOV/metadata/sourceData/swaths/frequencyA"]
        center_freq = float(swath_meta["centerFrequency"][()])
        range_bw = float(swath_meta["acquiredRangeBandwidth"][()])

    # Combined valid observation mask:
    # 1. Native mask must indicate valid subswath sample (mask == 1, not fill 255 and not partial 0)
    # 2. Native exception mask must be 0 (no instrument sample slip)
    # 3. Measurement power must be finite, non-NaN, and strictly greater than noise floor threshold 1e-7
    eps = 1e-7
    valid_t0 = (mask0 == 1) & (ex0 == 0) & np.isfinite(hh0) & np.isfinite(hv0) & (hh0 > eps) & (hv0 > eps)
    valid_t1 = (mask1 == 1) & (ex1 == 0) & np.isfinite(hh1) & np.isfinite(hv1) & (hh1 > eps) & (hv1 > eps)
    combined_valid = valid_t0 & valid_t1

    # RTC factor statistics over valid pixels
    rtc_valid_t0 = rtc0[combined_valid]
    rtc_valid_t1 = rtc1[combined_valid]
    if len(rtc_valid_t0) > 0 and len(rtc_valid_t1) > 0:
        rtc_diff = rtc_valid_t1 - rtc_valid_t0
        rtc_stats = {
            "rtc_t0_min": float(np.min(rtc_valid_t0)),
            "rtc_t0_max": float(np.max(rtc_valid_t0)),
            "rtc_t0_mean": float(np.mean(rtc_valid_t0)),
            "rtc_t0_std": float(np.std(rtc_valid_t0)),
            "rtc_t1_min": float(np.min(rtc_valid_t1)),
            "rtc_t1_max": float(np.max(rtc_valid_t1)),
            "rtc_t1_mean": float(np.mean(rtc_valid_t1)),
            "rtc_t1_std": float(np.std(rtc_valid_t1)),
            "rtc_diff_min": float(np.min(rtc_diff)),
            "rtc_diff_max": float(np.max(rtc_diff)),
            "rtc_diff_mean": float(np.mean(rtc_diff)),
            "rtc_diff_std": float(np.std(rtc_diff)),
            "max_abs_diff": float(np.max(np.abs(rtc_diff))),
        }
    else:
        rtc_stats = {
            "rtc_t0_min": float(np.nan),
            "rtc_t0_max": float(np.nan),
            "rtc_t0_mean": float(np.nan),
            "rtc_t0_std": float(np.nan),
            "rtc_t1_min": float(np.nan),
            "rtc_t1_max": float(np.nan),
            "rtc_t1_mean": float(np.nan),
            "rtc_t1_std": float(np.nan),
            "rtc_diff_min": float(np.nan),
            "rtc_diff_max": float(np.nan),
            "rtc_diff_mean": float(np.nan),
            "rtc_diff_std": float(np.nan),
            "max_abs_diff": float(np.nan),
        }

    meta = FrequencyAMetadata(
        crs=crs_str,
        pixel_spacing_x=dx0,
        pixel_spacing_y=dy0,
        x_min=float(sub_x0[0]),
        x_max=float(sub_x0[-1]),
        y_min=float(sub_y0[-1]),
        y_max=float(sub_y0[0]),
        transform=transform0,
        window_shape=(len(sub_y0), len(sub_x0)),
        t0_scene_id=t0_scene,
        t1_scene_id=t1_scene,
        t0_acquisition_time=t0_time,
        t1_acquisition_time=t1_time,
        track=track,
        frame=frame,
        orbit_pass=orbit_pass,
        processing_crid_t0=crid_t0,
        processing_crid_t1=crid_t1,
        center_frequency_hz=center_freq,
        range_bandwidth_hz=range_bw,
        rtc_factor_stats=rtc_stats,
    )

    return FrequencyAWindow(
        metadata=meta,
        gamma0_rtc_hh_t0=hh0,
        gamma0_rtc_hv_t0=hv0,
        gamma0_rtc_hh_t1=hh1,
        gamma0_rtc_hv_t1=hv1,
        mask_t0=mask0,
        mask_t1=mask1,
        exception_mask_t0=ex0,
        exception_mask_t1=ex1,
        rtc_factor_t0=rtc0,
        rtc_factor_t1=rtc1,
        valid_mask=combined_valid,
    )
