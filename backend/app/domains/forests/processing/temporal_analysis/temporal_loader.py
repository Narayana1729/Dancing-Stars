"""Reproducible multi-temporal loader for NISAR L2 GCOV products (Frequency A and B)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple
import h5py
import numpy as np
from rasterio.transform import Affine, from_origin

from app.domains.forests.processing.temporal_analysis.metadata import (
    AcquisitionMetadata,
    TemporalSeriesMetadata,
)
from app.domains.forests.processing.temporal_analysis.temporal_validation import (
    GridVerificationContext,
    validate_acquisition_compatibility,
)

# Standard Similipal Tiger Reserve study area bounds (EPSG:32645 / UTM Zone 45N)
SIMILIPAL_X_MIN = 401640.0
SIMILIPAL_X_MAX = 463960.0
SIMILIPAL_Y_MIN = 2372200.0
SIMILIPAL_Y_MAX = 2438360.0

NOISE_FLOOR_EPS = 1e-7


@dataclass
class LoadedTemporalSeries:
    """In-memory loaded multi-temporal NISAR observations for a specific frequency."""
    metadata: TemporalSeriesMetadata
    dates: List[str]
    # Linear RTC power arrays (float32) for each epoch, with invalid pixels set to NaN
    hh_linear: List[np.ndarray]
    hv_linear: List[np.ndarray]
    # Native quality masks (uint8) and boolean validity masks for each epoch
    native_masks: List[np.ndarray]
    exception_masks: List[np.ndarray]
    valid_masks: List[np.ndarray]
    # Terrain radiometric area normalization factors
    rtc_factors: List[np.ndarray]
    # Multi-epoch co-occurrence metrics
    valid_count_map: np.ndarray  # int16: number of valid epochs per pixel (0 to N)
    intersection_mask: np.ndarray  # bool: True where valid across ALL epochs


def _get_h5_str(obj: Any) -> str:
    """Decode HDF5 string or bytes dataset safely."""
    val = obj[()]
    return val.decode("utf-8") if isinstance(val, (bytes, bytearray)) else str(val)


def find_grid_slice(
    h5_file: h5py.File,
    frequency_key: str,
    x_min: float = SIMILIPAL_X_MIN,
    x_max: float = SIMILIPAL_X_MAX,
    y_min: float = SIMILIPAL_Y_MIN,
    y_max: float = SIMILIPAL_Y_MAX,
) -> Tuple[slice, slice, np.ndarray, np.ndarray, Affine]:
    """Calculate exact array slices and georeferenced transform for the UTM bounding box."""
    grid_group = f"science/LSAR/GCOV/grids/{frequency_key}"
    grid = h5_file[grid_group]
    x_coords = grid["xCoordinates"][:]
    y_coords = grid["yCoordinates"][:]
    dx = float(grid["xCoordinateSpacing"][()])
    dy = float(grid["yCoordinateSpacing"][()])

    ix0 = int(np.searchsorted(x_coords, x_min))
    ix1 = int(np.searchsorted(x_coords, x_max))

    # yCoordinates is descending (dy is negative, e.g. -10.0 or -80.0 m)
    iy0 = int(np.searchsorted(-y_coords, -y_max))
    iy1 = int(np.searchsorted(-y_coords, -y_min))

    x_slice = slice(ix0, ix1)
    y_slice = slice(iy0, iy1)

    sub_x = x_coords[x_slice]
    sub_y = y_coords[y_slice]

    if len(sub_x) == 0 or len(sub_y) == 0:
        raise ValueError(
            f"Requested bounding box [{x_min}, {x_max}, {y_min}, {y_max}] "
            f"does not intersect raster extent: X=[{x_coords[0]}, {x_coords[-1]}], "
            f"Y=[{y_coords[-1]}, {y_coords[0]}]"
        )

    # Pixel corner origin for Affine transform
    x_origin = sub_x[0] - dx / 2.0
    y_origin = sub_y[0] - dy / 2.0
    transform = from_origin(x_origin, y_origin, dx, -dy)

    return y_slice, x_slice, sub_x, sub_y, transform


def extract_acquisition_metadata(
    h5_file: h5py.File,
    frequency_key: str,
    file_path: Path,
) -> AcquisitionMetadata:
    """Extract metadata and radar geometry parameters from an open NISAR L2 GCOV file."""
    ident = h5_file["science/LSAR/identification"]
    swath_meta = h5_file[f"science/LSAR/GCOV/metadata/sourceData/swaths/{frequency_key}"]

    granule_id = _get_h5_str(ident["granuleId"]) if "granuleId" in ident else file_path.stem
    acq_time = _get_h5_str(ident["zeroDopplerStartTime"])
    track = int(ident["trackNumber"][()])
    frame = int(ident["frameNumber"][()])
    orbit_pass = _get_h5_str(ident["orbitPassDirection"])
    look_dir = _get_h5_str(ident["lookDirection"])
    crid = _get_h5_str(ident["compositeReleaseId"])

    center_freq = float(swath_meta["centerFrequency"][()])
    range_bw = float(swath_meta["acquiredRangeBandwidth"][()])
    near_inc = float(swath_meta["nearRangeIncidenceAngle"][()])
    far_inc = float(swath_meta["farRangeIncidenceAngle"][()])
    range_res = float(swath_meta["rangeResolution"][()])
    az_res = float(swath_meta["sceneCenterAlongTrackResolution"][()])

    return AcquisitionMetadata(
        granule_id=granule_id,
        acquisition_time=acq_time,
        track=track,
        frame=frame,
        orbit_pass=orbit_pass,
        look_direction=look_dir,
        crid=crid,
        frequency_band=frequency_key,
        center_frequency_hz=center_freq,
        range_bandwidth_hz=range_bw,
        near_range_incidence_deg=near_inc,
        far_range_incidence_deg=far_inc,
        range_resolution_m=range_res,
        azimuth_resolution_m=az_res,
    )


def load_multitemporal_series(
    file_paths: List[Path],
    frequency_key: str = "frequencyB",
    x_min: float = SIMILIPAL_X_MIN,
    x_max: float = SIMILIPAL_X_MAX,
    y_min: float = SIMILIPAL_Y_MIN,
    y_max: float = SIMILIPAL_Y_MAX,
    noise_floor_eps: float = NOISE_FLOOR_EPS,
) -> LoadedTemporalSeries:
    """Load a multi-temporal series of NISAR L2 GCOV products for a given frequency.

    Args:
        file_paths: Ordered list of NISAR L2 GCOV HDF5 file paths.
        frequency_key: "frequencyA" (10 m) or "frequencyB" (80 m).
        x_min, x_max, y_min, y_max: Spatial window bounding box in EPSG:32645 coordinates.
        noise_floor_eps: Lower bound for valid positive radar backscatter power.

    Returns:
        LoadedTemporalSeries with verified spatial registration, calibrated arrays,
        and pixel-level quality masks.
    """
    if not file_paths:
        raise ValueError("Must provide at least one NISAR GCOV file path.")

    for p in file_paths:
        if not p.exists():
            raise FileNotFoundError(f"NISAR file does not exist: {p}")

    # Chronological sorting by zero-Doppler start time
    def _extract_start_time(p: Path) -> str:
        with h5py.File(p, "r") as f:
            ident = f.get("science/LSAR/identification")
            return _get_h5_str(ident["zeroDopplerStartTime"]) if ident and "zeroDopplerStartTime" in ident else ""

    sorted_paths = sorted(file_paths, key=_extract_start_time)

    acquisitions: List[AcquisitionMetadata] = []
    dates: List[str] = []
    hh_linear_list: List[np.ndarray] = []
    hv_linear_list: List[np.ndarray] = []
    native_mask_list: List[np.ndarray] = []
    exception_mask_list: List[np.ndarray] = []
    valid_mask_list: List[np.ndarray] = []
    rtc_factor_list: List[np.ndarray] = []

    reference_sub_x: Optional[np.ndarray] = None
    reference_sub_y: Optional[np.ndarray] = None
    reference_transform: Optional[Affine] = None
    reference_crs: Optional[str] = None
    window_shape: Optional[Tuple[int, int]] = None
    ref_grid_ctx: Optional[GridVerificationContext] = None
    ref_meta: Optional[AcquisitionMetadata] = None

    for i, path in enumerate(sorted_paths):
        with h5py.File(path, "r") as h5:
            grid_group_name = f"science/LSAR/GCOV/grids/{frequency_key}"
            if grid_group_name not in h5:
                raise KeyError(f"Grid group {grid_group_name} not found in {path.name}")

            grid = h5[grid_group_name]

            # 1. Verify CRS
            epsg = int(grid["projection"][()])
            crs_str = f"EPSG:{epsg}"
            if reference_crs is None:
                reference_crs = crs_str

            # 2. Extract spatial slices
            y_slice, x_slice, sub_x, sub_y, transform = find_grid_slice(
                h5,
                frequency_key=frequency_key,
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
            )

            dx = float(grid["xCoordinateSpacing"][()])
            dy = float(grid["yCoordinateSpacing"][()])

            # 3. Extract metadata and acquisition geometry
            acq_meta = extract_acquisition_metadata(h5, frequency_key, path)

            # 4. Construct grid verification context
            current_grid_ctx = GridVerificationContext(
                crs=crs_str,
                transform=transform,
                shape=(len(sub_y), len(sub_x)),
                x_first=float(sub_x[0]),
                x_last=float(sub_x[-1]),
                y_first=float(sub_y[0]),
                y_last=float(sub_y[-1]),
                dx=dx,
                dy=dy,
            )

            # 5. Enforce 12-point compatibility validation against epoch 0
            if i == 0:
                ref_grid_ctx = current_grid_ctx
                ref_meta = acq_meta
                reference_sub_x = sub_x
                reference_sub_y = sub_y
                reference_transform = transform
                window_shape = (len(sub_y), len(sub_x))
            else:
                validate_acquisition_compatibility(
                    reference_meta=ref_meta,
                    candidate_meta=acq_meta,
                    reference_grid=ref_grid_ctx,
                    candidate_grid=current_grid_ctx,
                )

            acquisitions.append(acq_meta)
            dates.append(acq_meta.acquisition_time[:10])

            # 5. Extract calibrated RTC arrays (float32)
            hh = grid["HHHH"][y_slice, x_slice].astype(np.float32)
            hv = grid["HVHV"][y_slice, x_slice].astype(np.float32)

            # 6. Extract masks and RTC area factors
            mask = grid["mask"][y_slice, x_slice].astype(np.uint8)
            ex_mask = grid["inputDataExceptionMask"][y_slice, x_slice].astype(np.uint8)
            rtc_factor = grid["rtcGammaToSigmaFactor"][y_slice, x_slice].astype(np.float32)

            # 7. Formulate strict quality validity criteria:
            # - mask == 1: valid radar observation (not fill 255 and not partial edge 0)
            # - exception_mask == 0: no instrument sample slip or clock glitch
            # - finite backscatter above noise floor threshold
            valid = (
                (mask == 1)
                & (ex_mask == 0)
                & np.isfinite(hh)
                & np.isfinite(hv)
                & (hh > noise_floor_eps)
                & (hv > noise_floor_eps)
            )

            # Assign NaNs to invalid pixels in working linear arrays to prevent silent leaks
            hh_clean = np.where(valid, hh, np.nan).astype(np.float32)
            hv_clean = np.where(valid, hv, np.nan).astype(np.float32)

            hh_linear_list.append(hh_clean)
            hv_linear_list.append(hv_clean)
            native_mask_list.append(mask)
            exception_mask_list.append(ex_mask)
            valid_mask_list.append(valid)
            rtc_factor_list.append(rtc_factor)

    # Multi-epoch co-occurrence metrics
    valid_count_map = np.sum(valid_mask_list, axis=0, dtype=np.int16)
    intersection_mask = (valid_count_map == len(file_paths))

    # Calculate temporal baselines relative to epoch 0
    from datetime import datetime
    t0_dt = datetime.fromisoformat(acquisitions[0].acquisition_time[:19])
    baseline_days = [
        int((datetime.fromisoformat(acq.acquisition_time[:19]) - t0_dt).total_seconds() / 86400)
        for acq in acquisitions
    ]
    baseline_days_float = [
        round((datetime.fromisoformat(acq.acquisition_time[:19]) - t0_dt).total_seconds() / 86400.0, 4)
        for acq in acquisitions
    ]
    dates_iso = [acq.acquisition_time for acq in acquisitions]

    nom_res = 10.0 if frequency_key == "frequencyA" else 80.0

    meta = TemporalSeriesMetadata(
        frequency_id=frequency_key,
        nominal_resolution_m=nom_res,
        crs=reference_crs,
        transform=reference_transform,
        window_shape=window_shape,
        x_min=float(reference_sub_x[0]),
        x_max=float(reference_sub_x[-1]),
        y_min=float(reference_sub_y[-1]),
        y_max=float(reference_sub_y[0]),
        acquisitions=acquisitions,
        num_epochs=len(file_paths),
        baseline_days=baseline_days,
        baseline_days_float=baseline_days_float,
        dates_iso=dates_iso,
    )

    return LoadedTemporalSeries(
        metadata=meta,
        dates=dates,
        hh_linear=hh_linear_list,
        hv_linear=hv_linear_list,
        native_masks=native_mask_list,
        exception_masks=exception_mask_list,
        valid_masks=valid_mask_list,
        rtc_factors=rtc_factor_list,
        valid_count_map=valid_count_map,
        intersection_mask=intersection_mask,
    )

