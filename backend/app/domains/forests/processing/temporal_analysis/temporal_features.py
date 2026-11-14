"""Extraction of physical multi-temporal polarimetric features from NISAR L2 GCOV series.

This module acts as the public feature extraction facade. It coordinates:
- Decibel backscatter and cross-polarization ratio calculations.
- Differential baseline and sequential step changes.
- Relative Normalized Difference (RND) with numerical stability safeguards.
- Robust temporal statistics (Mean/Std in linear space; Median/MAD/Z-score in dB space).
- Memory-bounded Theil-Sen slope estimation.
- Three-tier physical disturbance classification (Tiers 1 to 3).
- Scattering regime taxonomy (Regimes 0 to 5).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy.ndimage import uniform_filter

from app.domains.forests.processing.temporal_analysis.disturbance_indicators import (
    classify_physical_change_regimes,
    evaluate_tier1_instantaneous_candidate,
    evaluate_tier2_sustained_anomaly,
    evaluate_tier3_persistent_candidate,
)
from app.domains.forests.processing.temporal_analysis.metadata import (
    FeatureDistributionStats,
    ZonalStats,
)
from app.domains.forests.processing.temporal_analysis.temporal_loader import (
    LoadedTemporalSeries,
    NOISE_FLOOR_EPS,
)
from app.domains.forests.processing.temporal_analysis.temporal_statistics import (
    compute_db_temporal_statistics,
    compute_linear_temporal_statistics,
    compute_relative_normalized_difference,
    compute_temporal_zscore,
    compute_tiled_theil_sen_slope,
)


@dataclass
class MultiTemporalFeatures:
    """Multi-temporal polarimetric features extracted from a NISAR L2 GCOV series.

    Maintains 100% backward compatibility with all Phase 4.1.1 attributes while
    exposing new multi-temporal statistical products and three-tier disturbance metrics.
    """
    # --- Legacy Phase 4.1.1 Compatible Attributes ---
    # Backscatter power in decibels (dB) for each epoch [k]
    hh_db: List[np.ndarray]
    hv_db: List[np.ndarray]
    # Cross-polarization ratio R = 10*log10(HV / HH) in dB for each epoch [k]
    ratio_hv_hh_db: List[np.ndarray]

    # Differential features relative to epoch 0 (t1 - t0, t2 - t0, etc.)
    delta_hh_db: List[np.ndarray]
    delta_hv_db: List[np.ndarray]
    delta_ratio_db: List[np.ndarray]

    # Local temporal variability (two-point |y1 - y0| / sqrt(2) for N=2, or sample std in dB)
    temporal_std_hv_db: np.ndarray
    # Spatial neighborhood variability of temporal change (3x3 local std of delta_hv)
    spatial_local_std_delta_hv_db: np.ndarray

    # Persistence and recovery indicators (legacy aliases)
    persistence_indicator: np.ndarray  # float32: alias to tier1_instantaneous_intensity
    recovery_trajectory_db: np.ndarray  # float32: backscatter trajectory (t_last - t_previous)
    is_corroborated_disturbance_candidate: np.ndarray  # bool: alias to tier1_instantaneous_candidate

    # Physical change regime taxonomy (0 to 5)
    physical_change_regimes: np.ndarray  # uint8: categorical physical scattering regimes

    # Quality validity masks
    valid_count_map: np.ndarray
    intersection_mask: np.ndarray

    # Quantitative statistical metrics
    overall_statistics: Dict[str, FeatureDistributionStats]

    # --- New Phase 4.2.2 Multi-Temporal Extensions ---
    # Linear Power Domain Statistics
    mean_hh_linear: Optional[np.ndarray] = None
    mean_hv_linear: Optional[np.ndarray] = None
    std_hh_linear: Optional[np.ndarray] = None
    std_hv_linear: Optional[np.ndarray] = None

    # Decibel Domain Statistics
    median_hh_db: Optional[np.ndarray] = None
    median_hv_db: Optional[np.ndarray] = None
    mad_hh_db: Optional[np.ndarray] = None
    mad_hv_db: Optional[np.ndarray] = None

    # Theil-Sen Trend Engine (dB / day)
    theil_sen_slope_hv_db_per_day: Optional[np.ndarray] = None
    theil_sen_performance: Optional[Dict[str, Any]] = None

    # Sequential Step Differences and RND
    delta_hv_step_db: Optional[List[np.ndarray]] = None
    rnd_hv_step: Optional[List[np.ndarray]] = None

    # Three-Tier Disturbance Taxonomy
    tier1_instantaneous_candidate: Optional[np.ndarray] = None
    tier1_instantaneous_intensity: Optional[np.ndarray] = None
    tier2_sustained_anomaly: Optional[np.ndarray] = None
    tier2_status: str = "UNVERIFIABLE_TWO_DATES"
    tier3_persistent_candidate: Optional[np.ndarray] = None
    tier3_status: str = "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"


def compute_distribution_stats(arr: np.ndarray, mask: np.ndarray) -> FeatureDistributionStats:
    """Calculate robust descriptive statistics over a masked region."""
    valid_data = arr[mask & np.isfinite(arr)]
    if len(valid_data) == 0:
        return FeatureDistributionStats(
            count=0,
            min=float("nan"),
            max=float("nan"),
            mean=float("nan"),
            std=float("nan"),
            median=float("nan"),
            p05=float("nan"),
            p25=float("nan"),
            p75=float("nan"),
            p95=float("nan"),
        )

    return FeatureDistributionStats(
        count=int(len(valid_data)),
        min=float(np.min(valid_data)),
        max=float(np.max(valid_data)),
        mean=float(np.mean(valid_data)),
        std=float(np.std(valid_data)),
        median=float(np.median(valid_data)),
        p05=float(np.percentile(valid_data, 5)),
        p25=float(np.percentile(valid_data, 25)),
        p75=float(np.percentile(valid_data, 75)),
        p95=float(np.percentile(valid_data, 95)),
    )


def compute_local_spatial_std(arr: np.ndarray, mask: np.ndarray, size: int = 3) -> np.ndarray:
    """Compute local neighborhood standard deviation using fast uniform filtering.

    Var(X) = E[X^2] - (E[X])^2 over a (size x size) window.
    """
    filled = np.where(mask & np.isfinite(arr), arr, 0.0)
    w = np.where(mask & np.isfinite(arr), 1.0, 0.0)

    sum_w = uniform_filter(w, size=size, mode="reflect")
    valid_kernel = sum_w > 0.4  # At least 40% of the kernel has valid observations

    mean_x = uniform_filter(filled, size=size, mode="reflect") / np.maximum(sum_w, 1e-6)
    mean_x2 = uniform_filter(filled**2, size=size, mode="reflect") / np.maximum(sum_w, 1e-6)

    variance = np.maximum(mean_x2 - mean_x**2, 0.0)
    local_std = np.sqrt(variance)

    result = np.full(arr.shape, np.nan, dtype=np.float32)
    result[mask & valid_kernel] = local_std[mask & valid_kernel]
    return result


def extract_multitemporal_features(
    series: LoadedTemporalSeries,
    noise_floor_eps: float = NOISE_FLOOR_EPS,
) -> MultiTemporalFeatures:
    """Compute generalized multi-temporal polarimetric features from loaded NISAR series.

    Preserves 100% numerical backward compatibility with the Phase 4.1.1 baseline when N=2,
    while scaling seamlessly to arbitrary N-epoch time series stacks.
    """
    n_epochs = series.metadata.num_epochs
    shape = series.metadata.window_shape
    intersection = series.intersection_mask

    hh_db_list: List[np.ndarray] = []
    hv_db_list: List[np.ndarray] = []
    ratio_db_list: List[np.ndarray] = []

    # 1. Compute single-epoch decibel backscatter and cross-polarization ratio
    for k in range(n_epochs):
        valid_k = series.valid_masks[k]

        hh_db = np.full(shape, np.nan, dtype=np.float32)
        hv_db = np.full(shape, np.nan, dtype=np.float32)
        ratio_db = np.full(shape, np.nan, dtype=np.float32)

        hh_lin = series.hh_linear[k]
        hv_lin = series.hv_linear[k]

        hh_db[valid_k] = (10.0 * np.log10(np.maximum(hh_lin[valid_k], noise_floor_eps))).astype(np.float32)
        hv_db[valid_k] = (10.0 * np.log10(np.maximum(hv_lin[valid_k], noise_floor_eps))).astype(np.float32)
        ratio_db[valid_k] = (hv_db[valid_k] - hh_db[valid_k]).astype(np.float32)

        hh_db_list.append(hh_db)
        hv_db_list.append(hv_db)
        ratio_db_list.append(ratio_db)

    # 2. Compute differential features relative to baseline epoch 0
    delta_hh_list: List[np.ndarray] = []
    delta_hv_list: List[np.ndarray] = []
    delta_ratio_list: List[np.ndarray] = []

    for k in range(1, n_epochs):
        pair_valid = series.valid_masks[0] & series.valid_masks[k]

        d_hh = np.full(shape, np.nan, dtype=np.float32)
        d_hv = np.full(shape, np.nan, dtype=np.float32)
        d_ratio = np.full(shape, np.nan, dtype=np.float32)

        d_hh[pair_valid] = (hh_db_list[k][pair_valid] - hh_db_list[0][pair_valid]).astype(np.float32)
        d_hv[pair_valid] = (hv_db_list[k][pair_valid] - hv_db_list[0][pair_valid]).astype(np.float32)
        d_ratio[pair_valid] = (ratio_db_list[k][pair_valid] - ratio_db_list[0][pair_valid]).astype(np.float32)

        delta_hh_list.append(d_hh)
        delta_hv_list.append(d_hv)
        delta_ratio_list.append(d_ratio)

    # 3. Compute sequential step differences and Relative Normalized Difference (RND)
    delta_hv_step_list: List[np.ndarray] = []
    rnd_hv_step_list: List[np.ndarray] = []

    for k in range(1, n_epochs):
        step_valid = series.valid_masks[k - 1] & series.valid_masks[k]
        d_step = np.full(shape, np.nan, dtype=np.float32)
        d_step[step_valid] = (hv_db_list[k][step_valid] - hv_db_list[k - 1][step_valid]).astype(np.float32)
        delta_hv_step_list.append(d_step)

        rnd_step = compute_relative_normalized_difference(
            current_linear=series.hv_linear[k],
            previous_linear=series.hv_linear[k - 1],
            valid_current=series.valid_masks[k],
            valid_previous=series.valid_masks[k - 1],
        )
        rnd_hv_step_list.append(rnd_step)

    # 4. Multi-Temporal Linear and dB Statistics
    hh_linear_stack = np.stack(series.hh_linear, axis=0)
    hv_linear_stack = np.stack(series.hv_linear, axis=0)
    valid_mask_stack = np.stack(series.valid_masks, axis=0)
    hv_db_stack = np.stack(hv_db_list, axis=0)
    hh_db_stack = np.stack(hh_db_list, axis=0)

    # Linear Domain Statistics
    mean_hh_lin, std_hh_lin = compute_linear_temporal_statistics(hh_linear_stack, valid_mask_stack)
    mean_hv_lin, std_hv_lin = compute_linear_temporal_statistics(hv_linear_stack, valid_mask_stack)

    # Decibel Domain Statistics
    median_hh_db, mad_hh_db = compute_db_temporal_statistics(hh_db_stack, valid_mask_stack)
    median_hv_db, mad_hv_db = compute_db_temporal_statistics(hv_db_stack, valid_mask_stack)

    # Legacy two-point temporal variability: |y1 - y0| / sqrt(2) when N=2
    if n_epochs == 2 and len(delta_hv_list) > 0:
        temporal_std_hv = np.full(shape, np.nan, dtype=np.float32)
        temporal_std_hv[intersection] = (
            np.abs(delta_hv_list[0][intersection]) / np.sqrt(2.0)
        ).astype(np.float32)
    else:
        temporal_std_hv = np.full(shape, np.nan, dtype=np.float32)
        temporal_std_hv[intersection] = np.std(hv_db_stack[:, intersection], axis=0, ddof=1).astype(np.float32)

    # Spatial local std of primary delta_hv
    spatial_std_delta_hv = (
        compute_local_spatial_std(delta_hv_list[0], intersection, size=3)
        if delta_hv_list
        else np.full(shape, np.nan, dtype=np.float32)
    )

    # 5. Tiled Theil-Sen Slope Estimation
    timestamps_days = series.metadata.baseline_days_float or [float(d) for d in series.metadata.baseline_days]
    theil_sen_slope, theil_sen_perf = compute_tiled_theil_sen_slope(
        stack_db=hv_db_stack,
        timestamps_days=timestamps_days,
        valid_mask_stack=valid_mask_stack,
        tile_size=512,
    )

    # 6. Three-Tier Disturbance Classification
    primary_dhv = delta_hv_list[0] if delta_hv_list else np.full(shape, np.nan, dtype=np.float32)
    primary_dhh = delta_hh_list[0] if delta_hh_list else np.full(shape, np.nan, dtype=np.float32)
    primary_dratio = delta_ratio_list[0] if delta_ratio_list else np.full(shape, np.nan, dtype=np.float32)

    # Tier 1: Instantaneous Disturbance Candidate (N >= 2)
    is_tier1_candidate, tier1_intensity = evaluate_tier1_instantaneous_candidate(
        delta_hv_db=primary_dhv,
        delta_ratio_db=primary_dratio,
        valid_intersection=intersection,
    )

    # Tier 2: Temporally Sustained Backscatter Anomaly (N >= 3)
    if n_epochs >= 3 and len(delta_hv_list) >= 2:
        valid_3epochs = series.valid_masks[0] & series.valid_masks[1] & series.valid_masks[2]
        is_tier2_sustained, tier2_status = evaluate_tier2_sustained_anomaly(
            delta_hv_t1_db=delta_hv_list[0],
            delta_hv_t2_db=delta_hv_list[1],
            delta_ratio_t1_db=delta_ratio_list[0],
            valid_t0_t1_t2=valid_3epochs,
        )
    else:
        is_tier2_sustained = None
        tier2_status = "UNVERIFIABLE_TWO_DATES"

    # Tier 3: Long-Term Persistent Disturbance Candidate (N >= 4, elapsed >= 180d)
    elapsed_days = float(timestamps_days[-1] - timestamps_days[0]) if timestamps_days else 0.0
    if n_epochs >= 4:
        is_tier3_persistent, tier3_status = evaluate_tier3_persistent_candidate(
            delta_hv_stack=delta_hv_list,
            valid_stack=valid_mask_stack,
            elapsed_days=elapsed_days,
            min_epochs=4,
            min_elapsed_days=180.0,
        )
    else:
        is_tier3_persistent = None
        tier3_status = "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"

    # Physical change regime classification
    change_regimes = classify_physical_change_regimes(
        delta_hh_db=primary_dhh,
        delta_hv_db=primary_dhv,
        delta_ratio_db=primary_dratio,
        is_tier1_candidate=is_tier1_candidate,
        intersection_mask=intersection,
    )

    # Recovery trajectory (for backward compatibility: primary_dhv if N=2, t_last - t_prev if N>=3)
    if n_epochs == 2:
        recovery_trajectory = primary_dhv.copy()
    else:
        last_valid = series.valid_masks[-1] & series.valid_masks[-2]
        recovery_trajectory = np.full(shape, np.nan, dtype=np.float32)
        recovery_trajectory[last_valid] = (hv_db_list[-1][last_valid] - hv_db_list[-2][last_valid]).astype(np.float32)

    # 7. Descriptive Statistics Compilation (with 100% backward-compatible keys)
    stats: Dict[str, FeatureDistributionStats] = {}

    # Epoch backscatter distributions
    for k in range(n_epochs):
        stats[f"hh_db_t{k}"] = compute_distribution_stats(hh_db_list[k], series.valid_masks[k])
        stats[f"hv_db_t{k}"] = compute_distribution_stats(hv_db_list[k], series.valid_masks[k])
        stats[f"ratio_hv_hh_db_t{k}"] = compute_distribution_stats(ratio_db_list[k], series.valid_masks[k])

    # Differential baseline distributions
    if delta_hv_list:
        stats["delta_hh_db"] = compute_distribution_stats(primary_dhh, intersection)
        stats["delta_hv_db"] = compute_distribution_stats(primary_dhv, intersection)
        stats["delta_ratio_hv_hh_db"] = compute_distribution_stats(primary_dratio, intersection)

    stats["temporal_std_hv_db"] = compute_distribution_stats(temporal_std_hv, intersection)
    stats["spatial_local_std_delta_hv_db"] = compute_distribution_stats(spatial_std_delta_hv, intersection)

    return MultiTemporalFeatures(
        hh_db=hh_db_list,
        hv_db=hv_db_list,
        ratio_hv_hh_db=ratio_db_list,
        delta_hh_db=delta_hh_list,
        delta_hv_db=delta_hv_list,
        delta_ratio_db=delta_ratio_list,
        temporal_std_hv_db=temporal_std_hv,
        spatial_local_std_delta_hv_db=spatial_std_delta_hv,
        persistence_indicator=tier1_intensity,  # 100% backward-compatible alias
        recovery_trajectory_db=recovery_trajectory,
        is_corroborated_disturbance_candidate=is_tier1_candidate,  # 100% backward-compatible alias
        physical_change_regimes=change_regimes,
        valid_count_map=series.valid_count_map,
        intersection_mask=intersection,
        overall_statistics=stats,
        # New multi-temporal features
        mean_hh_linear=mean_hh_lin,
        mean_hv_linear=mean_hv_lin,
        std_hh_linear=std_hh_lin,
        std_hv_linear=std_hv_lin,
        median_hh_db=median_hh_db,
        median_hv_db=median_hv_db,
        mad_hh_db=mad_hh_db,
        mad_hv_db=mad_hv_db,
        theil_sen_slope_hv_db_per_day=theil_sen_slope,
        theil_sen_performance=theil_sen_perf,
        delta_hv_step_db=delta_hv_step_list,
        rnd_hv_step=rnd_hv_step_list,
        tier1_instantaneous_candidate=is_tier1_candidate,
        tier1_instantaneous_intensity=tier1_intensity,
        tier2_sustained_anomaly=is_tier2_sustained,
        tier2_status=tier2_status,
        tier3_persistent_candidate=is_tier3_persistent,
        tier3_status=tier3_status,
    )
