"""Robust linear-power and decibel-domain multi-temporal statistics engines.

Implements mathematically rigorous domain separation:
- Linear Power Domain: Mean, Standard Deviation, and Relative Normalized Difference (RND).
- Decibel Domain (dB): Median, Median Absolute Deviation (MAD), Z-score, and Tiled Theil-Sen Slope.
"""
from __future__ import annotations

import resource
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

# Configurable numerical stability threshold (not a verified sensor thermal noise floor)
EPSILON_NUMERICAL_STABILITY = 2e-7


def compute_linear_temporal_statistics(
    stack_linear: np.ndarray,
    valid_mask_stack: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute per-pixel temporal mean and sample standard deviation in the linear power domain.

    Args:
        stack_linear: Linear backscatter power array of shape (T, H, W).
        valid_mask_stack: Boolean validity mask array of shape (T, H, W).

    Returns:
        Tuple of (mean_linear, std_linear), both shape (H, W).
        - mean_linear is NaN where N_valid == 0.
        - std_linear is NaN where N_valid < 2 (per ddof=1 sample variance requirements).
    """
    T, H, W = stack_linear.shape
    valid_counts = np.sum(valid_mask_stack, axis=0, dtype=np.int16)

    # Replace invalid pixels with 0 for summation
    clean_linear = np.where(valid_mask_stack & np.isfinite(stack_linear), stack_linear, 0.0)

    # 1. Temporal Mean (linear power)
    sum_linear = np.sum(clean_linear, axis=0, dtype=np.float64)
    mean_linear = np.full((H, W), np.nan, dtype=np.float32)
    valid_mean_mask = valid_counts >= 1
    mean_linear[valid_mean_mask] = (
        sum_linear[valid_mean_mask] / valid_counts[valid_mean_mask]
    ).astype(np.float32)

    # 2. Temporal Sample Standard Deviation (linear power, ddof=1)
    std_linear = np.full((H, W), np.nan, dtype=np.float32)
    valid_std_mask = valid_counts >= 2
    if np.any(valid_std_mask):
        # Broadcast mean along epoch axis for deviation calculation
        mean_expanded = np.expand_dims(mean_linear, axis=0)  # (1, H, W)
        diff_sq = np.where(valid_mask_stack, (stack_linear - mean_expanded) ** 2, 0.0)
        sum_diff_sq = np.sum(diff_sq, axis=0, dtype=np.float64)
        sample_variance = sum_diff_sq[valid_std_mask] / (valid_counts[valid_std_mask] - 1)
        std_linear[valid_std_mask] = np.sqrt(np.maximum(sample_variance, 0.0)).astype(np.float32)

    return mean_linear, std_linear


def compute_db_temporal_statistics(
    stack_db: np.ndarray,
    valid_mask_stack: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute per-pixel temporal median and robust MAD in the decibel (dB) domain.

    Behavior by valid observation count (N_valid):
    - N_valid == 0: median = NaN, MAD = NaN
    - N_valid == 1: median = value, MAD = NaN (dispersion around a single point is undefined)
    - N_valid >= 2: median = median(values), MAD = 1.4826 * median(|values - median|)

    Returns:
        Tuple of (median_db, mad_db), both shape (H, W).
    """
    T, H, W = stack_db.shape
    valid_counts = np.sum(valid_mask_stack, axis=0, dtype=np.int16)

    median_db = np.full((H, W), np.nan, dtype=np.float32)
    mad_db = np.full((H, W), np.nan, dtype=np.float32)

    if T == 0:
        return median_db, mad_db

    # For small T (e.g. T <= 10), masked per-pixel sorting is efficient
    # Mask invalid with NaN
    nan_db = np.where(valid_mask_stack & np.isfinite(stack_db), stack_db, np.nan)

    # Compute median along time axis ignoring NaNs
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning, message="All-NaN slice")
        computed_median = np.nanmedian(nan_db, axis=0)
    median_db[valid_counts >= 1] = computed_median[valid_counts >= 1].astype(np.float32)

    # Compute MAD where N_valid >= 2
    valid_mad_mask = valid_counts >= 2
    if np.any(valid_mad_mask):
        median_expanded = np.expand_dims(median_db, axis=0)  # (1, H, W)
        abs_deviations = np.abs(nan_db - median_expanded)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning, message="All-NaN slice")
            median_abs_dev = np.nanmedian(abs_deviations, axis=0)
        # Scale factor 1.4826 provides asymptotic consistency with standard deviation for normal distribution
        mad_db[valid_mad_mask] = (1.4826 * median_abs_dev[valid_mad_mask]).astype(np.float32)

    return median_db, mad_db


def compute_temporal_zscore(
    stack_db: np.ndarray,
    median_db: np.ndarray,
    mad_db: np.ndarray,
    valid_mask_stack: np.ndarray,
    sigma_floor: float = 0.5,
) -> np.ndarray:
    """Compute robust standardized anomaly Z-score for each epoch in decibels.

    Z_k = (gamma0_dB,k - median_dB) / max(MAD_dB, sigma_floor)
    Returns:
        Array of shape (T, H, W). NaN where invalid or MAD is NaN.
    """
    T, H, W = stack_db.shape
    z_stack = np.full((T, H, W), np.nan, dtype=np.float32)

    scale = np.maximum(mad_db, sigma_floor)
    valid_scale = np.isfinite(mad_db) & (scale > 0.0)

    for k in range(T):
        epoch_valid = valid_mask_stack[k] & valid_scale & np.isfinite(stack_db[k])
        z_stack[k, epoch_valid] = (
            (stack_db[k, epoch_valid] - median_db[epoch_valid]) / scale[epoch_valid]
        ).astype(np.float32)

    return z_stack


def compute_relative_normalized_difference(
    current_linear: np.ndarray,
    previous_linear: np.ndarray,
    valid_current: np.ndarray,
    valid_previous: np.ndarray,
    epsilon_num: float = EPSILON_NUMERICAL_STABILITY,
) -> np.ndarray:
    """Compute Relative Normalized Difference (RND) in linear power space with validity safeguards.

    Equation:
      RND = (gamma0_k - gamma0_{k-1}) / (gamma0_k + gamma0_{k-1})
    Subject to:
      valid_k and valid_{k-1} and gamma0_k > 0 and gamma0_{k-1} > 0 and denominator > epsilon_num.

    Returns:
        Float32 array bounded strictly within [-1.0, +1.0], with NaN for invalid pixels.
    """
    H, W = current_linear.shape
    rnd = np.full((H, W), np.nan, dtype=np.float32)

    valid_pair = (
        valid_current
        & valid_previous
        & np.isfinite(current_linear)
        & np.isfinite(previous_linear)
        & (current_linear > 0.0)
        & (previous_linear > 0.0)
    )

    denominator = current_linear + previous_linear
    valid_calc = valid_pair & (denominator > epsilon_num)

    if np.any(valid_calc):
        ratio = (current_linear[valid_calc] - previous_linear[valid_calc]) / denominator[valid_calc]
        # Bounded mathematically within [-1.0, 1.0]
        rnd[valid_calc] = np.clip(ratio, -1.0, 1.0).astype(np.float32)

    return rnd


def compute_tiled_theil_sen_slope(
    stack_db: np.ndarray,
    timestamps_days: List[float],
    valid_mask_stack: np.ndarray,
    tile_size: int = 512,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Compute non-parametric Theil-Sen linear trend slope using memory-bounded block processing.

    Slope:
      beta = median((y_j - y_i) / (t_j - t_i)) for all i < j where both are valid.

    Strict Scientific Constraints:
    - Evaluated only where N_valid >= 3.
    - Missing observations are handled dynamically per pixel.
    - Where N_valid < 3, the slope is strictly NaN.
    - Evaluated in blocks of (tile_size x tile_size) to bound peak process memory.

    Returns:
        Tuple of (theil_sen_slope_db_per_day, performance_metrics).
    """
    t_start = time.perf_counter()
    T, H, W = stack_db.shape
    slope_map = np.full((H, W), np.nan, dtype=np.float32)

    valid_counts = np.sum(valid_mask_stack, axis=0, dtype=np.int16)
    eligible_pixels = int(np.sum(valid_counts >= 3))

    if eligible_pixels == 0 or T < 3:
        # Cannot compute Theil-Sen slope with fewer than 3 valid observations
        duration = time.perf_counter() - t_start
        max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        max_rss_mb = (max_rss / (1024 * 1024)) if sys.platform == "darwin" else (max_rss / 1024)
        return slope_map, {
            "eligible_pixels": 0,
            "total_pixels": H * W,
            "duration_seconds": round(duration, 4),
            "peak_rss_mb": round(max_rss_mb, 2),
            "tile_size": tile_size,
            "note": "Theil-Sen slope requires N_valid >= 3 epochs per pixel; all pixels set to NaN.",
        }

    time_arr = np.array(timestamps_days, dtype=np.float64)

    # Process raster in memory-bounded rectangular blocks
    for y0 in range(0, H, tile_size):
        y1 = min(y0 + tile_size, H)
        for x0 in range(0, W, tile_size):
            x1 = min(x0 + tile_size, W)

            tile_valid_counts = valid_counts[y0:y1, x0:x1]
            if not np.any(tile_valid_counts >= 3):
                continue

            tile_db = stack_db[:, y0:y1, x0:x1]          # (T, h, w)
            tile_valid = valid_mask_stack[:, y0:y1, x0:x1]  # (T, h, w)
            th, tw = y1 - y0, x1 - x0

            # Find all pairwise slope combinations
            # Number of pairs K = T * (T - 1) // 2
            slope_pairs: List[np.ndarray] = []
            for i in range(T):
                for j in range(i + 1, T):
                    dt = time_arr[j] - time_arr[i]
                    if abs(dt) < 1e-5:
                        continue
                    pair_valid = tile_valid[i] & tile_valid[j]
                    dy = tile_db[j] - tile_db[i]
                    slope_ij = np.where(pair_valid, dy / dt, np.nan)
                    slope_pairs.append(slope_ij)

            if slope_pairs:
                # Stack pairwise slopes: shape (K, th, tw)
                pairs_stack = np.stack(slope_pairs, axis=0)
                import warnings
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=RuntimeWarning, message="All-NaN slice")
                    tile_median_slope = np.nanmedian(pairs_stack, axis=0)

                # Assign only where N_valid >= 3
                eligible_tile_mask = tile_valid_counts >= 3
                slope_map[y0:y1, x0:x1][eligible_tile_mask] = tile_median_slope[eligible_tile_mask].astype(np.float32)

    duration = time.perf_counter() - t_start
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    max_rss_mb = (max_rss / (1024 * 1024)) if sys.platform == "darwin" else (max_rss / 1024)

    return slope_map, {
        "eligible_pixels": eligible_pixels,
        "total_pixels": H * W,
        "duration_seconds": round(duration, 4),
        "peak_rss_mb": round(max_rss_mb, 2),
        "tile_size": tile_size,
    }
