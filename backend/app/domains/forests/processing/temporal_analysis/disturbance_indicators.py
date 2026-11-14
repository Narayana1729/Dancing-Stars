"""Physical disturbance classification and polarimetric change regime taxonomy.

Implements the scientifically honest three-tier disturbance classification taxonomy:
- Tier 1: Instantaneous disturbance candidate (N_valid >= 2)
- Tier 2: Temporally sustained backscatter anomaly (N_valid >= 3)
- Tier 3: Long-term persistent disturbance candidate (N_valid >= 4)

Explicitly maintains separation between SAR radiometric evidence and independently
validated ecological forest loss conclusions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class DisturbanceClassificationResult:
    """Consolidated disturbance classification metrics across all temporal tiers."""
    # Tier 1: Instantaneous disturbance candidate (evaluated at t1 relative to t0)
    tier1_instantaneous_candidate: np.ndarray        # bool: True where criteria met
    tier1_instantaneous_intensity: np.ndarray        # float32: drop magnitude index

    # Tier 2: Temporally sustained backscatter anomaly (evaluated across t0 -> t1 -> t2)
    tier2_sustained_anomaly: Optional[np.ndarray]    # bool or None (None if N_valid < 3)
    tier2_status: str                                # "ACTIVE" or "UNVERIFIABLE_TWO_DATES"

    # Tier 3: Long-term persistent disturbance candidate (evaluated across N_valid >= 4)
    tier3_persistent_candidate: Optional[np.ndarray] # bool or None (None if N_valid < 4)
    tier3_status: str                                # "ACTIVE" or "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"

    # Physical change regime taxonomy (0 to 5)
    physical_change_regimes: np.ndarray              # uint8: 0 to 5 categorical regime codes

    # Individual channel diagnostics
    channel_diagnostics: Dict[str, Any]


def evaluate_tier1_instantaneous_candidate(
    delta_hv_db: np.ndarray,
    delta_ratio_db: np.ndarray,
    valid_intersection: np.ndarray,
    hv_drop_thresh: float = -2.5,
    ratio_drop_thresh: float = -1.5,
) -> Tuple[np.ndarray, np.ndarray]:
    """Evaluate Tier 1: Instantaneous disturbance candidate.

    Criteria:
      Delta gamma0_HV <= -2.5 dB AND Delta R_HV/HH <= -1.5 dB over valid intersection.

    Scientific Scope:
      Identifies candidate pixels exhibiting significant polarimetric drop at epoch t_k.
      Does NOT prove whether the drop is caused by mechanical logging, temporary deciduous
      leaf senescence, or soil desiccation.

    Returns:
        Tuple of (candidate_mask, drop_intensity).
    """
    shape = delta_hv_db.shape
    is_candidate = (
        valid_intersection
        & np.isfinite(delta_hv_db)
        & np.isfinite(delta_ratio_db)
        & (delta_hv_db <= hv_drop_thresh)
        & (delta_ratio_db <= ratio_drop_thresh)
    )

    drop_intensity = np.zeros(shape, dtype=np.float32)
    if np.any(is_candidate):
        drop_intensity[is_candidate] = np.sqrt(
            np.maximum(-delta_hv_db[is_candidate], 0.0)
            * np.maximum(-delta_ratio_db[is_candidate], 0.0)
        ).astype(np.float32)

    return is_candidate, drop_intensity


def evaluate_tier2_sustained_anomaly(
    delta_hv_t1_db: np.ndarray,
    delta_hv_t2_db: np.ndarray,
    delta_ratio_t1_db: np.ndarray,
    valid_t0_t1_t2: np.ndarray,
    t1_drop_thresh: float = -2.5,
    t2_sustain_thresh: float = -2.0,
    ratio_drop_thresh: float = -1.5,
) -> Tuple[Optional[np.ndarray], str]:
    """Evaluate Tier 2: Temporally sustained backscatter anomaly across 3 epochs (t0 -> t1 -> t2).

    Criteria:
      Delta HV(t1, t0) <= -2.5 dB AND Delta HV(t2, t0) <= -2.0 dB AND Delta R(t1, t0) <= -1.5 dB.

    Explicit Scientific Boundary:
      Proves that backscatter suppression is not an isolated single-day artifact (such as
      ephemeral rain or single-epoch speckle).
      It does NOT rule out multi-week soil drought, extended deciduous leaf senescence,
      or seasonal dry-period effects.

    Returns:
        Tuple of (sustained_mask, status_string).
    """
    if delta_hv_t2_db is None or not np.any(valid_t0_t1_t2):
        return None, "UNVERIFIABLE_TWO_DATES"

    is_sustained = (
        valid_t0_t1_t2
        & np.isfinite(delta_hv_t1_db)
        & np.isfinite(delta_hv_t2_db)
        & np.isfinite(delta_ratio_t1_db)
        & (delta_hv_t1_db <= t1_drop_thresh)
        & (delta_hv_t2_db <= t2_sustain_thresh)
        & (delta_ratio_t1_db <= ratio_drop_thresh)
    )

    return is_sustained, "ACTIVE"


def evaluate_tier3_persistent_candidate(
    delta_hv_stack: List[np.ndarray],
    valid_stack: np.ndarray,
    elapsed_days: float,
    min_epochs: int = 4,
    min_elapsed_days: float = 180.0,
    drop_threshold_db: float = -2.0,
) -> Tuple[Optional[np.ndarray], str]:
    """Evaluate Tier 3: Long-term persistent disturbance candidate across N >= 4 epochs.

    Explicit Scientific Boundary:
      SAR observations alone do NOT establish confirmed permanent forest loss.
      Confirming permanent land-use conversion requires independent optical time series,
      Forest Survey of India (FSI) records, or ground compartment inspection.

    Requirements:
      - Minimum N_valid >= 4 epochs.
      - Minimum elapsed time >= 180 days spanning seasonal transitions.
      - Consecutive observations must all maintain backscatter suppression below threshold.

    Returns:
        Tuple of (persistent_mask, status_string).
    """
    if len(delta_hv_stack) < (min_epochs - 1) or elapsed_days < min_elapsed_days:
        return None, "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"

    # Strict consecutive observation check
    all_valid = np.all(valid_stack, axis=0)
    persistent = all_valid.copy()
    for dhv in delta_hv_stack:
        persistent &= np.isfinite(dhv) & (dhv <= drop_threshold_db)

    return persistent, "ACTIVE"


def classify_physical_change_regimes(
    delta_hh_db: np.ndarray,
    delta_hv_db: np.ndarray,
    delta_ratio_db: np.ndarray,
    is_tier1_candidate: np.ndarray,
    intersection_mask: np.ndarray,
) -> np.ndarray:
    """Classify multi-channel backscatter changes into physical scattering regime taxonomy.

    0: Unobserved / Masked
    1: Stable Forest Canopy (|Delta HV| <= 1.5 dB and |Delta R| <= 1.0 dB)
    2: Seasonal Moisture Desiccation (Delta HH < -1.5 dB, Delta HV < -1.5 dB, |Delta R| <= 1.0 dB)
    3: Surface Roughness / Moisture Infiltration (Delta HH > +1.5 dB, Delta HV >= 0 dB)
    4: Candidate Canopy Disturbance (Tier 1 criteria)
    5: Ambiguous Polarimetric Shift (other significant shifts)

    Returns:
        Uint8 categorical raster of regime codes (0 to 5).
    """
    shape = delta_hh_db.shape
    change_regimes = np.zeros(shape, dtype=np.uint8)

    valid = intersection_mask & np.isfinite(delta_hh_db) & np.isfinite(delta_hv_db) & np.isfinite(delta_ratio_db)

    stable_mask = valid & (np.abs(delta_hv_db) <= 1.5) & (np.abs(delta_ratio_db) <= 1.0)
    desiccation_mask = valid & (delta_hh_db < -1.5) & (delta_hv_db < -1.5) & (np.abs(delta_ratio_db) <= 1.0)
    roughness_mask = valid & (delta_hh_db > 1.5) & (delta_hv_db >= 0.0)
    disturbance_mask = is_tier1_candidate & valid
    ambiguous_mask = valid & ~(stable_mask | desiccation_mask | roughness_mask | disturbance_mask)

    change_regimes[stable_mask] = 1
    change_regimes[desiccation_mask] = 2
    change_regimes[roughness_mask] = 3
    change_regimes[disturbance_mask] = 4
    change_regimes[ambiguous_mask] = 5

    return change_regimes

