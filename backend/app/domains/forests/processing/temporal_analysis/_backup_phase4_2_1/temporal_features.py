"""Extraction of physical multi-temporal polarimetric features from NISAR L2 GCOV series."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np
from scipy.ndimage import uniform_filter

from app.domains.forests.processing.temporal_analysis.metadata import (
    FeatureDistributionStats,
    ZonalStats,
)
from app.domains.forests.processing.temporal_analysis.temporal_loader import (
    LoadedTemporalSeries,
    NOISE_FLOOR_EPS,
)


@dataclass
class MultiTemporalFeatures:
    """Multi-temporal polarimetric features extracted from a NISAR L2 GCOV series."""
    # Backscatter power in decibels (dB) for each epoch [k]
    hh_db: List[np.ndarray]
    hv_db: List[np.ndarray]
    # Cross-polarization ratio R = 10*log10(HV / HH) in dB for each epoch [k]
    ratio_hv_hh_db: List[np.ndarray]

    # Differential features relative to epoch 0 (t1 - t0, t2 - t0, etc.)
    delta_hh_db: List[np.ndarray]
    delta_hv_db: List[np.ndarray]
    delta_ratio_db: List[np.ndarray]

    # Local temporal variability (standard deviation across time in dB)
    temporal_std_hv_db: np.ndarray
    # Spatial neighborhood variability of temporal change (3x3 local std of delta_hv)
    spatial_local_std_delta_hv_db: np.ndarray

    # Persistence and recovery indicators
    persistence_indicator: np.ndarray  # float32: dual-channel corroborated disturbance indicator
    recovery_trajectory_db: np.ndarray  # float32: backscatter trajectory (t_last - t_previous)
    is_corroborated_disturbance_candidate: np.ndarray  # bool: candidate disturbance mask

    # Physical change regime taxonomy (0 to 5)
    physical_change_regimes: np.ndarray  # uint8: categorical physical scattering regimes

    # Quality validity masks
    valid_count_map: np.ndarray
    intersection_mask: np.ndarray

    # Quantitative statistical metrics
    overall_statistics: Dict[str, FeatureDistributionStats]


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
    # Replace NaNs with zeros for the filter, using normalized weight
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
    """Compute physical multi-temporal polarimetric features from loaded NISAR series.

    Equations:
      γ⁰_HH_dB(t_k) = 10 * log10(HH(t_k))
      γ⁰_HV_dB(t_k) = 10 * log10(HV(t_k))
      R_HV_HH(t_k)  = 10 * log10(HV(t_k) / HH(t_k)) = γ⁰_HV_dB(t_k) - γ⁰_HH_dB(t_k)
      Δγ⁰_HH(t_k)   = γ⁰_HH_dB(t_k) - γ⁰_HH_dB(t_0)
      Δγ⁰_HV(t_k)   = γ⁰_HV_dB(t_k) - γ⁰_HV_dB(t_0)
      ΔR_HV_HH(t_k) = R_HV_HH(t_k) - R_HV_HH(t_0)

    Physical Regime Classification:
      0: Unobserved / Masked
      1: Stable Forest Canopy (|ΔHV| <= 1.5 dB and |ΔR| <= 1.0 dB)
      2: Seasonal Moisture Desiccation (ΔHH < -1.5 dB, ΔHV < -1.5 dB, |ΔR| <= 1.0 dB)
      3: Surface Roughness / Moisture Infiltration (ΔHH > +1.5 dB, ΔHV >= 0 dB)
      4: Candidate Canopy Disturbance (ΔHV < -2.5 dB and ΔR < -1.5 dB)
      5: Ambiguous Polarimetric Shift (other significant shifts)
    """
    n_epochs = series.metadata.num_epochs
    shape = series.metadata.window_shape
    intersection = series.intersection_mask

    hh_db_list: List[np.ndarray] = []
    hv_db_list: List[np.ndarray] = []
    ratio_db_list: List[np.ndarray] = []

    # 1. Compute single-epoch backscatter (dB) and cross-polarization ratio
    for k in range(n_epochs):
        valid_k = series.valid_masks[k]
        hh_lin = series.hh_linear[k]
        hv_lin = series.hv_linear[k]

        hh_db = np.full(shape, np.nan, dtype=np.float32)
        hv_db = np.full(shape, np.nan, dtype=np.float32)
        ratio_db = np.full(shape, np.nan, dtype=np.float32)

        valid_vals = valid_k & np.isfinite(hh_lin) & np.isfinite(hv_lin) & (hh_lin > noise_floor_eps) & (hv_lin > noise_floor_eps)

        hh_db[valid_vals] = (10.0 * np.log10(hh_lin[valid_vals])).astype(np.float32)
        hv_db[valid_vals] = (10.0 * np.log10(hv_lin[valid_vals])).astype(np.float32)
        ratio_db[valid_vals] = (hv_db[valid_vals] - hh_db[valid_vals]).astype(np.float32)

        hh_db_list.append(hh_db)
        hv_db_list.append(hv_db)
        ratio_db_list.append(ratio_db)

    # 2. Pairwise temporal changes relative to epoch 0
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

    # 3. Local temporal variability (standard deviation across epochs in dB)
    # Stack valid dB arrays across time
    hv_stack = np.stack(hv_db_list, axis=0)  # shape: (n_epochs, H, W)
    # Compute std along epoch axis where intersection is valid
    if n_epochs == 2:
        # Exact two-point temporal standard deviation: |y1 - y0| / sqrt(2)
        temporal_std_hv = np.full(shape, np.nan, dtype=np.float32)
        temporal_std_hv[intersection] = (
            np.abs(delta_hv_list[0][intersection]) / np.sqrt(2.0)
        ).astype(np.float32)
    else:
        # General N-epoch sample standard deviation (ddof=1)
        temporal_std_hv = np.full(shape, np.nan, dtype=np.float32)
        temporal_std_hv[intersection] = np.std(hv_stack[:, intersection], axis=0, ddof=1).astype(np.float32)

    # Spatial neighborhood variability of the primary temporal change (3x3 kernel)
    spatial_std_delta_hv = compute_local_spatial_std(delta_hv_list[0], intersection, size=3)

    # 4. Persistence and recovery indicators
    # Dual-polarization corroborated candidate disturbance:
    # Requires significant drop in both cross-pol volume backscatter (ΔHV < -2.5 dB)
    # AND drop in depolarizing ratio (ΔR < -1.5 dB)
    primary_dhv = delta_hv_list[0]
    primary_dhh = delta_hh_list[0]
    primary_dratio = delta_ratio_list[0]

    is_corroborated_disturbance = (
        intersection
        & (primary_dhv < -2.5)
        & (primary_dratio < -1.5)
    )

    # Corroborated disturbance intensity indicator (higher values = more severe structural drop)
    persistence_indicator = np.zeros(shape, dtype=np.float32)
    cand_pixels = is_corroborated_disturbance
    persistence_indicator[cand_pixels] = (
        np.sqrt(np.maximum(-primary_dhv[cand_pixels], 0.0) * np.maximum(-primary_dratio[cand_pixels], 0.0))
    ).astype(np.float32)

    # Recovery / trajectory indicator:
    # For N=2, trajectory from t0 to t1. For N>=3, trajectory from (t_last - t_previous)
    if n_epochs == 2:
        recovery_trajectory = primary_dhv.copy()
    else:
        last_valid = series.valid_masks[-1] & series.valid_masks[-2]
        recovery_trajectory = np.full(shape, np.nan, dtype=np.float32)
        recovery_trajectory[last_valid] = (hv_db_list[-1][last_valid] - hv_db_list[-2][last_valid]).astype(np.float32)

    # 5. Physical Change Regime Taxonomy
    # 0: Unobserved / Masked
    # 1: Stable Forest Canopy (|ΔHV| <= 1.5 dB and |ΔR| <= 1.0 dB)
    # 2: Seasonal Moisture Desiccation (ΔHH < -1.5 dB, ΔHV < -1.5 dB, |ΔR| <= 1.0 dB)
    # 3: Surface Roughness / Moisture Infiltration (ΔHH > +1.5 dB, ΔHV >= 0 dB)
    # 4: Candidate Canopy Disturbance (ΔHV < -2.5 dB and ΔR < -1.5 dB)
    # 5: Ambiguous Polarimetric Shift
    change_regimes = np.zeros(shape, dtype=np.uint8)

    # Condition masks over valid intersection
    stable_mask = intersection & (np.abs(primary_dhv) <= 1.5) & (np.abs(primary_dratio) <= 1.0)
    desiccation_mask = intersection & (primary_dhh < -1.5) & (primary_dhv < -1.5) & (np.abs(primary_dratio) <= 1.0)
    roughness_mask = intersection & (primary_dhh > 1.5) & (primary_dhv >= 0.0)
    disturbance_mask = is_corroborated_disturbance
    ambiguous_mask = intersection & ~(stable_mask | desiccation_mask | roughness_mask | disturbance_mask)

    change_regimes[stable_mask] = 1
    change_regimes[desiccation_mask] = 2
    change_regimes[roughness_mask] = 3
    change_regimes[disturbance_mask] = 4
    change_regimes[ambiguous_mask] = 5

    # 6. Overall statistics
    stats: Dict[str, FeatureDistributionStats] = {
        "hh_db_t0": compute_distribution_stats(hh_db_list[0], series.valid_masks[0]),
        "hv_db_t0": compute_distribution_stats(hv_db_list[0], series.valid_masks[0]),
        "ratio_hv_hh_db_t0": compute_distribution_stats(ratio_db_list[0], series.valid_masks[0]),
        "hh_db_t1": compute_distribution_stats(hh_db_list[1], series.valid_masks[1]),
        "hv_db_t1": compute_distribution_stats(hv_db_list[1], series.valid_masks[1]),
        "ratio_hv_hh_db_t1": compute_distribution_stats(ratio_db_list[1], series.valid_masks[1]),
        "delta_hh_db": compute_distribution_stats(primary_dhh, intersection),
        "delta_hv_db": compute_distribution_stats(primary_dhv, intersection),
        "delta_ratio_hv_hh_db": compute_distribution_stats(primary_dratio, intersection),
        "temporal_std_hv_db": compute_distribution_stats(temporal_std_hv, intersection),
        "spatial_local_std_delta_hv_db": compute_distribution_stats(spatial_std_delta_hv, intersection),
    }

    return MultiTemporalFeatures(
        hh_db=hh_db_list,
        hv_db=hv_db_list,
        ratio_hv_hh_db=ratio_db_list,
        delta_hh_db=delta_hh_list,
        delta_hv_db=delta_hv_list,
        delta_ratio_db=delta_ratio_list,
        temporal_std_hv_db=temporal_std_hv,
        spatial_local_std_delta_hv_db=spatial_std_delta_hv,
        persistence_indicator=persistence_indicator,
        recovery_trajectory_db=recovery_trajectory,
        is_corroborated_disturbance_candidate=is_corroborated_disturbance,
        physical_change_regimes=change_regimes,
        valid_count_map=series.valid_count_map,
        intersection_mask=intersection,
        overall_statistics=stats,
    )

