"""Acquisition compatibility and grid validation for multi-temporal NISAR series.

Enforces 12 strict geometric, radiometric, and spatial-grid compatibility criteria
without performing redundant full-array coordinate memory allocations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from rasterio.transform import Affine

from app.domains.forests.processing.temporal_analysis.metadata import (
    AcquisitionMetadata,
)

# Configurable numerical tolerance thresholds
COORD_TOLERANCE_M = 1e-3       # 1 mm tolerance on spatial grid origins/endpoints
RESOLUTION_TOLERANCE_M = 1e-4  # 0.1 mm tolerance on pixel spacing dx, dy
INCIDENCE_TOLERANCE_DEG = 0.5   # 0.5 degree tolerance on radar incidence angles


class CompatibilityError(ValueError):
    """Raised when an acquisition violates multi-temporal stacking compatibility rules."""
    pass


@dataclass(frozen=True)
class GridVerificationContext:
    """Lightweight metadata context for spatial grid alignment without copying full arrays."""
    crs: str
    transform: Affine
    shape: Tuple[int, int]
    x_first: float
    x_last: float
    y_first: float
    y_last: float
    dx: float
    dy: float


def validate_acquisition_compatibility(
    reference_meta: AcquisitionMetadata,
    candidate_meta: AcquisitionMetadata,
    reference_grid: GridVerificationContext,
    candidate_grid: GridVerificationContext,
    coord_tol_m: float = COORD_TOLERANCE_M,
    res_tol_m: float = RESOLUTION_TOLERANCE_M,
    inc_tol_deg: float = INCIDENCE_TOLERANCE_DEG,
) -> None:
    """Validate 12 essential compatibility criteria before admitting an acquisition into a stack.

    Raises CompatibilityError with an explicit scientific explanation if any check fails.
    """
    # 1. Track Number
    if reference_meta.track != candidate_meta.track:
        raise CompatibilityError(
            f"Track mismatch: reference is Track {reference_meta.track}, "
            f"candidate ({candidate_meta.granule_id}) is Track {candidate_meta.track}. "
            "Cross-track temporal differencing violates orbital repeat geometry."
        )

    # 2. Frame Identifier
    if reference_meta.frame != candidate_meta.frame:
        raise CompatibilityError(
            f"Frame mismatch: reference is Frame {reference_meta.frame}, "
            f"candidate ({candidate_meta.granule_id}) is Frame {candidate_meta.frame}. "
            "Frame 012 and Frame 013 cover disjoint geographic swaths and must not be combined without mosaicking."
        )

    # 3. Orbit Pass Direction (Ascending vs Descending)
    ref_pass = reference_meta.orbit_pass.strip().upper()
    cand_pass = candidate_meta.orbit_pass.strip().upper()
    if ref_pass != cand_pass:
        raise CompatibilityError(
            f"Orbit pass direction mismatch: reference is {ref_pass}, "
            f"candidate ({candidate_meta.granule_id}) is {cand_pass}. "
            "Ascending and Descending passes view topography from opposite look angles; mixing them induces false anomalies."
        )

    # 4. Radar Frequency Channel
    if reference_meta.frequency_band != candidate_meta.frequency_band:
        raise CompatibilityError(
            f"Radar frequency mismatch: reference is {reference_meta.frequency_band}, "
            f"candidate ({candidate_meta.granule_id}) is {candidate_meta.frequency_band}. "
            "Frequency A (10m) and Frequency B (80m) are non-interchangeable products."
        )

    # 5. Look Direction
    ref_look = reference_meta.look_direction.strip().upper()
    cand_look = candidate_meta.look_direction.strip().upper()
    if ref_look != cand_look:
        raise CompatibilityError(
            f"Radar look direction mismatch: reference is {ref_look}, candidate is {cand_look}."
        )

    # 6. Incidence Angle Geometry
    near_diff = abs(reference_meta.near_range_incidence_deg - candidate_meta.near_range_incidence_deg)
    far_diff = abs(reference_meta.far_range_incidence_deg - candidate_meta.far_range_incidence_deg)
    if near_diff > inc_tol_deg or far_diff > inc_tol_deg:
        raise CompatibilityError(
            f"Incidence angle deviation exceeds tolerance ({inc_tol_deg}°): "
            f"near-range diff = {near_diff:.2f}°, far-range diff = {far_diff:.2f}°."
        )

    # 7. Coordinate Reference System (CRS)
    if reference_grid.crs != candidate_grid.crs:
        raise CompatibilityError(
            f"CRS mismatch: reference is {reference_grid.crs}, candidate is {candidate_grid.crs}."
        )

    # 8. Raster Grid Dimensions
    if reference_grid.shape != candidate_grid.shape:
        raise CompatibilityError(
            f"Raster dimension mismatch: reference shape is {reference_grid.shape}, "
            f"candidate shape is {candidate_grid.shape}."
        )

    # 9. Pixel Resolution (dx, dy)
    dx_diff = abs(reference_grid.dx - candidate_grid.dx)
    dy_diff = abs(reference_grid.dy - candidate_grid.dy)
    if dx_diff > res_tol_m or dy_diff > res_tol_m:
        raise CompatibilityError(
            f"Pixel spacing mismatch: dx diff = {dx_diff:.6f}m, dy diff = {dy_diff:.6f}m "
            f"(tolerance = {res_tol_m}m)."
        )

    # 10. Affine Geotransform Origin
    ref_t = reference_grid.transform
    cand_t = candidate_grid.transform
    x0_diff = abs(ref_t.c - cand_t.c)
    y0_diff = abs(ref_t.f - cand_t.f)
    if x0_diff > coord_tol_m or y0_diff > coord_tol_m:
        raise CompatibilityError(
            f"Affine transform origin offset exceeds {coord_tol_m}m tolerance: "
            f"dX0 = {x0_diff:.6f}m, dY0 = {y0_diff:.6f}m. Sub-pixel misalignment detected."
        )

    # 11. Coordinate Endpoints (X-first, X-last)
    x_first_diff = abs(reference_grid.x_first - candidate_grid.x_first)
    x_last_diff = abs(reference_grid.x_last - candidate_grid.x_last)
    if x_first_diff > coord_tol_m or x_last_diff > coord_tol_m:
        raise CompatibilityError(
            f"X-coordinate endpoint mismatch: first diff = {x_first_diff:.6f}m, last diff = {x_last_diff:.6f}m."
        )

    # 12. Coordinate Endpoints (Y-first, Y-last)
    y_first_diff = abs(reference_grid.y_first - candidate_grid.y_first)
    y_last_diff = abs(reference_grid.y_last - candidate_grid.y_last)
    if y_first_diff > coord_tol_m or y_last_diff > coord_tol_m:
        raise CompatibilityError(
            f"Y-coordinate endpoint mismatch: first diff = {y_first_diff:.6f}m, last diff = {y_last_diff:.6f}m."
        )


def compare_raster_baselines(
    arr_baseline: np.ndarray,
    arr_new: np.ndarray,
    tolerance: float = 1e-5,
    is_mask: bool = False,
) -> Dict[str, Any]:
    """Compare two raster arrays for exact numerical backward compatibility.

    Returns comparison report with exact pixel differences, max absolute error,
    and nodata location agreement.
    """
    if arr_baseline.shape != arr_new.shape:
        return {
            "is_compatible": False,
            "reason": f"Shape mismatch: {arr_baseline.shape} vs {arr_new.shape}",
        }

    # 1. Check nodata / NaN location identity
    nan_baseline = np.isnan(arr_baseline) if not is_mask else (arr_baseline == 0)
    nan_new = np.isnan(arr_new) if not is_mask else (arr_new == 0)
    nan_mismatch = int(np.sum(nan_baseline != nan_new))

    # 2. Check valid data numerical agreement
    valid = (~nan_baseline) & (~nan_new)
    if is_mask:
        diff_pixels = int(np.sum(arr_baseline != arr_new))
        max_diff = float(np.max(np.abs(arr_baseline.astype(int) - arr_new.astype(int)))) if len(arr_baseline) > 0 else 0.0
        passed = (diff_pixels == 0)
    else:
        if np.sum(valid) == 0:
            max_diff = 0.0
            diff_pixels = 0
            passed = (nan_mismatch == 0)
        else:
            diffs = np.abs(arr_baseline[valid] - arr_new[valid])
            max_diff = float(np.max(diffs))
            diff_pixels = int(np.sum(diffs > tolerance))
            passed = (diff_pixels == 0) and (nan_mismatch == 0)

    return {
        "is_compatible": passed,
        "max_absolute_difference": max_diff,
        "pixels_exceeding_tolerance": diff_pixels,
        "nodata_location_mismatches": nan_mismatch,
        "total_pixels": arr_baseline.size,
        "valid_comparison_pixels": int(np.sum(valid)),
    }

