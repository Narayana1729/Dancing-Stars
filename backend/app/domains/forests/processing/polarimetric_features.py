"""Polarimetric feature extraction for NISAR Frequency A observations.

This module computes physical radiometric backscatter changes and cross-polarization
ratios without applying unverified disturbance classification thresholds.
All calculations operate in terrain-flattened gamma-naught RTC space.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple
import numpy as np

from app.domains.forests.processing.frequency_a_loader import FrequencyAWindow


@dataclass
class PolarimetricFeatures:
    # Temporal backscatter differences (dB)
    delta_gamma0_hh_db: np.ndarray
    delta_gamma0_hv_db: np.ndarray
    # Polarimetric cross-ratios (dB)
    ratio_hv_hh_t0_db: np.ndarray
    ratio_hv_hh_t1_db: np.ndarray
    # Temporal ratio change (dB)
    delta_ratio_hv_hh_db: np.ndarray
    # Valid observation mask
    valid_mask: np.ndarray
    # Descriptive statistics over valid pixels
    statistics: Dict[str, Dict[str, float]]


def extract_polarimetric_features(
    window: FrequencyAWindow,
    noise_floor_eps: float = 1e-7,
) -> PolarimetricFeatures:
    """Compute physical polarimetric features from calibrated Frequency A window.

    Equations:
      Δγ⁰_HH_dB = 10 * log10(HH_t1 / HH_t0)
      Δγ⁰_HV_dB = 10 * log10(HV_t1 / HV_t0)
      R_HV_HH_t0 = 10 * log10(HV_t0 / HH_t0)
      R_HV_HH_t1 = 10 * log10(HV_t1 / HH_t1)
      ΔR_HV_HH = R_HV_HH_t1 - R_HV_HH_t0

    Calculations are strictly masked to valid, fully-focused, anomaly-free observations.
    Invalid or unobserved pixels are set to np.nan.
    """
    valid = window.valid_mask

    hh0 = window.gamma0_rtc_hh_t0
    hv0 = window.gamma0_rtc_hv_t0
    hh1 = window.gamma0_rtc_hh_t1
    hv1 = window.gamma0_rtc_hv_t1

    # Allocate output float32 arrays initialized to NaN
    shape = hh0.shape
    delta_hh_db = np.full(shape, np.nan, dtype=np.float32)
    delta_hv_db = np.full(shape, np.nan, dtype=np.float32)
    ratio_t0_db = np.full(shape, np.nan, dtype=np.float32)
    ratio_t1_db = np.full(shape, np.nan, dtype=np.float32)
    delta_ratio_db = np.full(shape, np.nan, dtype=np.float32)

    # Valid pixel subsets (avoids allocating full-size temporary copies)
    hh0_v = np.clip(hh0[valid], noise_floor_eps, None)
    hv0_v = np.clip(hv0[valid], noise_floor_eps, None)
    hh1_v = np.clip(hh1[valid], noise_floor_eps, None)
    hv1_v = np.clip(hv1[valid], noise_floor_eps, None)

    # A. Temporal HH change: 10 * log10(HH_t1 / HH_t0)
    # Equivalent to 10*log10(HH_t1) - 10*log10(HH_t0)
    d_hh = (10.0 * np.log10(hh1_v / hh0_v)).astype(np.float32)
    delta_hh_db[valid] = d_hh

    # B. Temporal HV change: 10 * log10(HV_t1 / HV_t0)
    d_hv = (10.0 * np.log10(hv1_v / hv0_v)).astype(np.float32)
    delta_hv_db[valid] = d_hv

    # C. Cross-polarization ratio at t0: 10 * log10(HV_t0 / HH_t0)
    r0 = (10.0 * np.log10(hv0_v / hh0_v)).astype(np.float32)
    ratio_t0_db[valid] = r0

    # D. Cross-polarization ratio at t1: 10 * log10(HV_t1 / HH_t1)
    r1 = (10.0 * np.log10(hv1_v / hh1_v)).astype(np.float32)
    ratio_t1_db[valid] = r1

    # E. Temporal ratio change: R_t1 - R_t0
    d_ratio = (r1 - r0).astype(np.float32)
    delta_ratio_db[valid] = d_ratio

    def _calc_stats(arr: np.ndarray) -> Dict[str, float]:
        return {
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "median": float(np.median(arr)),
            "p05": float(np.percentile(arr, 5)),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "p95": float(np.percentile(arr, 95)),
        }

    stats = {
        "delta_gamma0_hh_db": _calc_stats(d_hh),
        "delta_gamma0_hv_db": _calc_stats(d_hv),
        "ratio_hv_hh_t0_db": _calc_stats(r0),
        "ratio_hv_hh_t1_db": _calc_stats(r1),
        "delta_ratio_hv_hh_db": _calc_stats(d_ratio),
    }

    return PolarimetricFeatures(
        delta_gamma0_hh_db=delta_hh_db,
        delta_gamma0_hv_db=delta_hv_db,
        ratio_hv_hh_t0_db=ratio_t0_db,
        ratio_hv_hh_t1_db=ratio_t1_db,
        delta_ratio_hv_hh_db=delta_ratio_db,
        valid_mask=valid,
        statistics=stats,
    )

