"""Multi-Temporal Polarimetric SAR Feature Extraction & Robust Temporal Statistics.

Extracts polarimetric features and computes robust statistical anomaly metrics:
- Differential backscatter (ΔHH, ΔHV)
- Cross-polarization ratio and differential ratio (R, ΔR)
- Robust location and scale estimators (Median, MAD, 1.4826 * MAD)
- Standardized robust Z-score (Z_MAD)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple
import numpy as np


@dataclass
class RobustForestStatistics:
    """Robust location and scale metrics for forest backscatter change."""
    median_delta_hv_db: float
    mad_delta_hv_db: float
    mad_scale_sigma_db: float
    mean_delta_hv_db: float
    std_delta_hv_db: float
    pixel_count: int


def compute_temporal_sar_features(
    hh0: np.ndarray,
    hv0: np.ndarray,
    hh1: np.ndarray,
    hv1: np.ndarray,
    valid_mask: np.ndarray,
    input_in_db: bool = False,
    eps: float = 1e-7,
) -> Dict[str, np.ndarray]:
    """Compute calibrated decibel backscatter, temporal differences, and cross-ratios.

    Parameters
    ----------
    hh0, hv0 : np.ndarray
        Baseline gamma-nought backscatter at t0 (linear power or dB).
    hh1, hv1 : np.ndarray
        Target gamma-nought backscatter at t1 (linear power or dB).
    valid_mask : np.ndarray
        Boolean mask of pixels with valid quality flags at both epochs.
    input_in_db : bool
        If True, inputs are already in decibels (dB). If False, inputs are linear power.
    eps : float
        Numerical clipping floor for linear power.

    Returns
    -------
    Dict[str, np.ndarray]
        Computed feature layers (dB backscatter, differences, ratios).
    """
    if input_in_db:
        valid = (
            valid_mask
            & ~np.isnan(hh0)
            & ~np.isnan(hv0)
            & ~np.isnan(hh1)
            & ~np.isnan(hv1)
        )
        hh0_db = np.where(valid, hh0, np.nan)
        hv0_db = np.where(valid, hv0, np.nan)
        hh1_db = np.where(valid, hh1, np.nan)
        hv1_db = np.where(valid, hv1, np.nan)
    else:
        valid = (
            valid_mask
            & ~np.isnan(hh0)
            & ~np.isnan(hv0)
            & ~np.isnan(hh1)
            & ~np.isnan(hv1)
            & (hh0 > eps)
            & (hv0 > eps)
            & (hh1 > eps)
            & (hv1 > eps)
        )
        hh0_db = np.where(valid, 10.0 * np.log10(np.clip(hh0, eps, None)), np.nan)
        hv0_db = np.where(valid, 10.0 * np.log10(np.clip(hv0, eps, None)), np.nan)
        hh1_db = np.where(valid, 10.0 * np.log10(np.clip(hh1, eps, None)), np.nan)
        hv1_db = np.where(valid, 10.0 * np.log10(np.clip(hv1, eps, None)), np.nan)

    delta_hh = np.where(valid, hh1_db - hh0_db, np.nan)
    delta_hv = np.where(valid, hv1_db - hv0_db, np.nan)

    ratio_0 = np.where(valid, hv0_db - hh0_db, np.nan)
    ratio_1 = np.where(valid, hv1_db - hh1_db, np.nan)
    delta_ratio = np.where(valid, ratio_1 - ratio_0, np.nan)

    # Local two-point temporal variability: std = |delta_hv| / sqrt(2)
    temporal_std = np.where(valid, np.abs(delta_hv) / np.sqrt(2.0), np.nan)

    return {
        "valid_mask": valid,
        "hh0_db": hh0_db,
        "hv0_db": hv0_db,
        "hh1_db": hh1_db,
        "hv1_db": hv1_db,
        "delta_hh": delta_hh,
        "delta_hv": delta_hv,
        "ratio_0": ratio_0,
        "ratio_1": ratio_1,
        "delta_ratio": delta_ratio,
        "temporal_std": temporal_std,
    }


def compute_robust_forest_statistics(
    delta_hv: np.ndarray,
    forest_mask: np.ndarray,
    valid_mask: np.ndarray,
) -> RobustForestStatistics:
    """Compute robust location (Median) and scale (MAD) across intact forest baseline.

    Parameters
    ----------
    delta_hv : np.ndarray
        Cross-polarization backscatter change (dB).
    forest_mask : np.ndarray
        Documented forest cover mask (boolean).
    valid_mask : np.ndarray
        Valid observation mask (boolean).

    Returns
    -------
    RobustForestStatistics
        Summary statistics object.
    """
    eval_mask = valid_mask & forest_mask & ~np.isnan(delta_hv)
    if not np.any(eval_mask):
        raise ValueError("No valid forest pixels available for robust statistics estimation.")

    vals = delta_hv[eval_mask]
    med = float(np.median(vals))
    abs_dev = np.abs(vals - med)
    mad = float(np.median(abs_dev))
    # Consistent scale estimator for normal distribution: sigma_hat = 1.4826 * MAD
    mad_scale = float(1.4826 * mad)
    if mad_scale < 1e-4:
        mad_scale = 1e-4

    mean_val = float(np.mean(vals))
    std_val = float(np.std(vals))

    return RobustForestStatistics(
        median_delta_hv_db=round(med, 4),
        mad_delta_hv_db=round(mad, 4),
        mad_scale_sigma_db=round(mad_scale, 4),
        mean_delta_hv_db=round(mean_val, 4),
        std_delta_hv_db=round(std_val, 4),
        pixel_count=int(vals.size),
    )


def compute_robust_z_scores(
    delta_hv: np.ndarray,
    median_val: float,
    mad_scale: float,
    valid_mask: np.ndarray,
) -> np.ndarray:
    """Standardize delta_hv using robust Median and MAD scale: Z_MAD = (delta_hv - median) / scale.

    Parameters
    ----------
    delta_hv : np.ndarray
        Cross-polarization backscatter change (dB).
    median_val : float
        Robust median of forest background (dB).
    mad_scale : float
        Consistent MAD-based scale estimator (dB).
    valid_mask : np.ndarray
        Valid observation mask.

    Returns
    -------
    np.ndarray
        Standardized robust Z-score array (floating point, with NaN for invalid pixels).
    """
    scale = max(mad_scale, 1e-4)
    z = np.where(valid_mask & ~np.isnan(delta_hv), (delta_hv - median_val) / scale, np.nan)
    return z.astype(np.float32)
