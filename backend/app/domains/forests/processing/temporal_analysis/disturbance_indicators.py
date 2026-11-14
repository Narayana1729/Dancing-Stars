"""Physical disturbance classification and polarimetric change regime taxonomy.

Implements the scientifically honest multi-temporal disturbance classification taxonomy:
- Tier 1: Instantaneous disturbance candidate (N_valid >= 2)
- Tier 2: Temporally sustained backscatter anomaly (N_valid >= 3)
- Tier 3: Long-term persistent disturbance candidate (N_valid >= 4, Delta t >= 180d)
- Canopy Recovery: Sustained volume backscatter rebound (N_valid >= 4)
- 7-Class Deterministic Classification Framework (Phase 4.2.5 validated taxonomy)

Explicitly maintains separation between SAR radiometric evidence and independently
validated ecological forest loss conclusions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class MultiTemporalCapabilityState:
    """Explicit capability states and data dependencies across temporal tiers."""
    num_observations: int
    elapsed_days: float
    has_seasonal_coverage: bool
    post_event_epochs: int
    tier1_status: str
    tier2_status: str
    tier3_status: str
    recovery_status: str
    tier1_reason: str
    tier2_reason: str
    tier3_reason: str
    recovery_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_multi_temporal_state(
    num_observations: int,
    elapsed_days: float = 48.0,
    has_seasonal_coverage: bool = False,
    post_event_epochs: int = 0,
) -> MultiTemporalCapabilityState:
    """Compute explicit capability states according to available observation count and duration.

    Rules:
      N = 2:
        Tier 1: AVAILABLE
        Tier 2: UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS
        Tier 3: UNVERIFIABLE_INSUFFICIENT_TEMPORAL_COVERAGE
        Recovery: UNVERIFIABLE_NO_POST_EVENT_OBSERVATIONS
      N >= 3:
        Tier 2: ACTIVE (evaluated on consecutive observations)
      N >= 4:
        Tier 3: ACTIVE only when elapsed_days >= 180d AND seasonal coverage is adequate
        Recovery: ACTIVE only when post_event_epochs >= 3
    """
    tier1_status = "AVAILABLE"
    tier1_reason = "Instantaneous dual-date change candidate available (t0: March 4, t1: April 21, 2026)."

    # Tier 2
    if num_observations < 3:
        tier2_status = "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"
        tier2_reason = f"Requires ≥ 3 consecutive repeat passes; only {num_observations} dates exist in catalog."
    else:
        tier2_status = "ACTIVE"
        tier2_reason = f"Evaluated across {num_observations} consecutive repeat passes."

    # Tier 3
    if num_observations < 4:
        tier3_status = "UNVERIFIABLE_INSUFFICIENT_TEMPORAL_COVERAGE"
        tier3_reason = f"Requires ≥ 4 epochs spanning ≥ 180 days across wet and dry seasons; only {num_observations} epochs exist."
    elif elapsed_days < 180.0:
        tier3_status = "UNVERIFIABLE_INSUFFICIENT_TEMPORAL_COVERAGE"
        tier3_reason = f"Observation baseline ({elapsed_days:.1f} days) is less than required 180 days across seasonal transitions."
    elif not has_seasonal_coverage:
        tier3_status = "UNVERIFIABLE_MISSING_SEASONAL_COVERAGE"
        tier3_reason = "Missing wet-season/monsoon observations to distinguish structural felling from dry-season desiccation."
    else:
        tier3_status = "ACTIVE"
        tier3_reason = f"Evaluated across {num_observations} epochs spanning {elapsed_days:.1f} days."

    # Recovery
    if post_event_epochs < 3 or num_observations < 4:
        tier_reason = (
            "No post-event observations exist after April 21, 2026."
            if post_event_epochs == 0
            else f"Only {post_event_epochs} post-disturbance epochs observed; requires ≥ 3 cycles."
        )
        recovery_status = "UNVERIFIABLE_NO_POST_EVENT_OBSERVATIONS"
        recovery_reason = tier_reason
    else:
        recovery_status = "ACTIVE"
        recovery_reason = f"Evaluated across {post_event_epochs} post-disturbance monitoring cycles."

    return MultiTemporalCapabilityState(
        num_observations=num_observations,
        elapsed_days=elapsed_days,
        has_seasonal_coverage=has_seasonal_coverage,
        post_event_epochs=post_event_epochs,
        tier1_status=tier1_status,
        tier2_status=tier2_status,
        tier3_status=tier3_status,
        recovery_status=recovery_status,
        tier1_reason=tier1_reason,
        tier2_reason=tier2_reason,
        tier3_reason=tier3_reason,
        recovery_reason=recovery_reason,
    )


@dataclass
class DisturbanceClassificationResult:
    """Consolidated disturbance classification metrics across all temporal tiers."""
    # Tier 1: Instantaneous disturbance candidate (evaluated at t1 relative to t0)
    tier1_instantaneous_candidate: np.ndarray        # bool: True where criteria met
    tier1_instantaneous_intensity: np.ndarray        # float32: drop magnitude index

    # Tier 2: Temporally sustained backscatter anomaly (evaluated across t0 -> t1 -> t2)
    tier2_sustained_anomaly: Optional[np.ndarray]    # bool or None (None if N_valid < 3)
    tier2_status: str                                # "ACTIVE" or "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"

    # Tier 3: Long-term persistent disturbance candidate (evaluated across N_valid >= 4)
    tier3_persistent_candidate: Optional[np.ndarray] # bool or None (None if N_valid < 4)
    tier3_status: str                                # "ACTIVE" or "UNVERIFIABLE_INSUFFICIENT_TEMPORAL_COVERAGE"

    # Physical change regime taxonomy (0 to 5)
    physical_change_regimes: np.ndarray              # uint8: 0 to 5 categorical regime codes

    # Individual channel diagnostics
    channel_diagnostics: Dict[str, Any]

    # Canopy recovery
    canopy_recovery: Optional[np.ndarray] = None
    canopy_recovery_status: str = "UNVERIFIABLE_NO_POST_EVENT_OBSERVATIONS"

    # 7-Class Deterministic outputs (Phase 4.2.5)
    seven_class_map: Optional[np.ndarray] = None
    uncertainty_index: Optional[np.ndarray] = None
    state_machine_summary: Optional[Dict[str, Any]] = None


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
    delta_hv_t2_db: Optional[np.ndarray],
    delta_ratio_t1_db: np.ndarray,
    valid_t0_t1_t2: Optional[np.ndarray],
    t1_drop_thresh: float = -2.5,
    t2_sustain_thresh: float = -2.0,
    ratio_drop_thresh: float = -1.5,
    legacy_status: bool = False,
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
    if delta_hv_t2_db is None or valid_t0_t1_t2 is None or not np.any(valid_t0_t1_t2):
        status = "UNVERIFIABLE_TWO_DATES" if legacy_status else "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"
        return None, status

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
    has_seasonal_coverage: bool = True,
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
    if len(delta_hv_stack) < (min_epochs - 1):
        return None, "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"

    if elapsed_days < min_elapsed_days:
        return None, "UNVERIFIABLE_INSUFFICIENT_TEMPORAL_COVERAGE"

    if not has_seasonal_coverage:
        return None, "UNVERIFIABLE_MISSING_SEASONAL_COVERAGE"

    all_valid = np.all(valid_stack, axis=0)
    persistent = all_valid.copy()
    for dhv in delta_hv_stack:
        persistent &= np.isfinite(dhv) & (dhv <= drop_threshold_db)

    return persistent, "ACTIVE"


def evaluate_canopy_recovery(
    post_event_delta_hv_stack: Optional[List[np.ndarray]],
    valid_stack: Optional[np.ndarray],
    prior_disturbance_mask: Optional[np.ndarray] = None,
    min_post_event_epochs: int = 3,
    rebound_threshold_db: float = 1.5,
) -> Tuple[Optional[np.ndarray], str]:
    """Evaluate canopy recovery and volume scattering rebound across post-disturbance cycles.

    Scientific Boundary:
      Recovery tracking requires post-disturbance repeat passes. Missing observations
      must NEVER be interpreted as evidence of recovery.

    Returns:
        Tuple of (recovery_mask, status_string).
    """
    if (
        post_event_delta_hv_stack is None
        or len(post_event_delta_hv_stack) < min_post_event_epochs
        or valid_stack is None
        or not np.any(valid_stack)
    ):
        return None, "UNVERIFIABLE_NO_POST_EVENT_OBSERVATIONS"

    all_valid = np.all(valid_stack, axis=0)
    recovered = all_valid.copy()
    if prior_disturbance_mask is not None:
        recovered &= prior_disturbance_mask

    # Must sustain backscatter increase across post-event stack
    for dhv in post_event_delta_hv_stack:
        recovered &= np.isfinite(dhv) & (dhv >= rebound_threshold_db)

    return recovered, "ACTIVE"


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


def classify_seven_classes(
    delta_hh_db: np.ndarray,
    delta_hv_db: np.ndarray,
    delta_ratio_db: np.ndarray,
    valid_intersection: np.ndarray,
    rnd_hv: Optional[np.ndarray] = None,
    forest_mask: Optional[np.ndarray] = None,
    num_observations: int = 2,
    elapsed_days: float = 48.0,
    has_seasonal_coverage: bool = False,
    tier2_sustained_mask: Optional[np.ndarray] = None,
    tier3_persistent_mask: Optional[np.ndarray] = None,
    pixel_size_m: float = 80.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    """Execute the Phase 4.2.5 validated 7-class deterministic classification framework.

    Taxonomy:
      Class 1: No Significant Detected Change (Stable / Seasonal Desiccation / Roughness)
      Class 2: Potential Canopy Disturbance (Moderate joint drop)
      Class 3: Strong Instantaneous Disturbance Candidate (Severe polarimetric collapse)
      Class 4: Temporally Sustained Anomaly (Requires N >= 3; dormant on 2 dates)
      Class 5: Long-Term Persistent Candidate (Requires N >= 4, Delta t >= 180d; dormant on 2 dates)
      Class 6: Uncertain or Insufficient Evidence (Conflicting polarimetric regimes)
      Class 7: Invalid or Unobserved Region (Outside swath, masked, or nodata)

    Returns:
        Tuple of (classification_map, disturbance_intensity, uncertainty_index, class_summary).
    """
    shape = delta_hh_db.shape
    classification = np.full(shape, 7, dtype=np.uint8)  # Default: Class 7 (Invalid / Nodata)
    intensity = np.full(shape, np.nan, dtype=np.float32)
    uncertainty = np.full(shape, np.nan, dtype=np.float32)

    # Valid observation mask
    valid = valid_intersection & np.isfinite(delta_hh_db) & np.isfinite(delta_hv_db) & np.isfinite(delta_ratio_db)
    if forest_mask is not None:
        valid = valid & (forest_mask > 0)

    if not np.any(valid):
        return classification, intensity, uncertainty, {"total_valid_pixels": 0}

    # Compute RND_HV if not explicitly provided
    if rnd_hv is None:
        # Linear ratio proxy from dB difference
        linear_ratio = np.power(10.0, np.clip(delta_hv_db, -30.0, 30.0) / 10.0)
        rnd_calc = (linear_ratio - 1.0) / (linear_ratio + 1.0)
    else:
        rnd_calc = rnd_hv

    # --- Step 1: Long-Term Persistent Candidate (Class 5) ---
    c5 = np.zeros(shape, dtype=bool)
    if num_observations >= 4 and elapsed_days >= 180.0 and has_seasonal_coverage and tier3_persistent_mask is not None:
        c5 = valid & tier3_persistent_mask

    # --- Step 2: Temporally Sustained Anomaly (Class 4) ---
    c4 = np.zeros(shape, dtype=bool)
    if num_observations >= 3 and tier2_sustained_mask is not None:
        c4 = valid & ~c5 & tier2_sustained_mask

    # --- Step 3: Strong Instantaneous Candidate (Class 3) ---
    c3 = (
        valid
        & ~c5
        & ~c4
        & (delta_hv_db <= -2.5)
        & (delta_ratio_db <= -1.5)
        & (rnd_calc <= -0.25)
    )

    # --- Step 4: Potential Canopy Disturbance (Class 2) ---
    # Condition 2A: Moderate joint drop
    cond_2a = (delta_hv_db <= -1.5) & (delta_ratio_db <= -0.8) & (rnd_calc <= -0.15)
    # Condition 2B: Severe HV drop with marginal ratio drop
    cond_2b = (delta_hv_db <= -3.0) & (delta_ratio_db > -1.5) & (delta_ratio_db <= -0.5)
    c2 = valid & ~c5 & ~c4 & ~c3 & (cond_2a | cond_2b)

    # --- Step 5: No Significant Detected Change (Class 1) ---
    # Condition 1A: Stable intact canopy
    cond_1a = (np.abs(delta_hv_db) <= 1.5) & (np.abs(delta_ratio_db) <= 1.0)
    # Condition 1B: Natural seasonal soil/wood desiccation (HH and HV drop equally)
    cond_1b = (delta_hh_db < -1.5) & (delta_hv_db < -1.5) & (np.abs(delta_ratio_db) <= 1.0)
    # Condition 1C: Surface infiltration / roughness / regrowth
    cond_1c = (delta_hh_db > 1.5) & (delta_hv_db >= 0.0)
    c1 = valid & ~c5 & ~c4 & ~c3 & ~c2 & (cond_1a | cond_1b | cond_1c)

    # --- Step 6: Uncertain or Insufficient Evidence (Class 6) ---
    c6 = valid & ~c1 & ~c2 & ~c3 & ~c4 & ~c5

    # Populate categorical raster
    classification[c1] = 1
    classification[c2] = 2
    classification[c3] = 3
    classification[c4] = 4
    classification[c5] = 5
    classification[c6] = 6
    # Pixels where ~valid remain Class 7

    # Populate Disturbance Intensity ($I$)
    intensity[c1] = 0.0
    if np.any(c2):
        intensity[c2] = np.sqrt(
            np.maximum(-delta_hv_db[c2], 0.0)
            * np.maximum(-delta_ratio_db[c2], 0.5)
        ).astype(np.float32)

    if np.any(c3):
        intensity[c3] = np.sqrt(
            np.maximum(-delta_hv_db[c3], 0.0)
            * np.maximum(-delta_ratio_db[c3], 0.0)
        ).astype(np.float32)

    if np.any(c4):
        intensity[c4] = np.sqrt(
            np.maximum(-delta_hv_db[c4], 0.0)
            * np.maximum(-delta_ratio_db[c4], 0.0)
        ).astype(np.float32)

    if np.any(c5):
        intensity[c5] = np.sqrt(
            np.maximum(-delta_hv_db[c5], 0.0)
            * np.maximum(-delta_ratio_db[c5], 0.0)
        ).astype(np.float32)

    # Populate Uncertainty Index ($U$)
    uncertainty[c1] = 0.05
    uncertainty[c6] = 0.95
    if np.any(c4 | c5):
        uncertainty[c4 | c5] = 0.15

    # Composite uncertainty for Classes 2 and 3
    cand_mask = c2 | c3
    if np.any(cand_mask):
        sigma_speckle = 0.54  # 80m ENL ~ 64
        dhv_sub = np.maximum(-delta_hv_db[cand_mask], 0.0)
        u_speckle = np.exp(-(dhv_sub**2) / (2.0 * (sigma_speckle**2)))

        dr_sub = delta_ratio_db[cand_mask]
        u_ratio = np.where(
            dr_sub <= -1.5,
            0.0,
            np.where(dr_sub <= 0.5, (dr_sub + 1.5) / 2.0, 1.0)
        )

        u_temporal = 0.80 if num_observations <= 2 else (0.35 if num_observations == 3 else 0.10)

        u_comp = np.clip(
            np.sqrt(0.40 * (u_speckle**2) + 0.40 * (u_ratio**2) + 0.20 * (u_temporal**2)),
            0.0,
            1.0,
        )
        uncertainty[cand_mask] = u_comp.astype(np.float32)

    # Pixel area in hectares
    px_ha = (pixel_size_m * pixel_size_m) / 10000.0

    class_counts = {
        "class_1_no_significant_change": int(np.sum(c1)),
        "class_2_potential_canopy_disturbance": int(np.sum(c2)),
        "class_3_strong_instantaneous_candidate": int(np.sum(c3)),
        "class_4_temporally_sustained_anomaly": int(np.sum(c4)),
        "class_5_long_term_persistent_candidate": int(np.sum(c5)),
        "class_6_uncertain_evidence": int(np.sum(c6)),
        "class_7_invalid_or_unobserved": int(np.sum(~valid)),
    }

    class_areas_ha = {
        k.replace("class_", "area_ha_"): round(v * px_ha, 2)
        for k, v in class_counts.items()
    }

    summary = {
        "num_observations": num_observations,
        "elapsed_days": elapsed_days,
        "has_seasonal_coverage": has_seasonal_coverage,
        "total_valid_pixels": int(np.sum(valid)),
        "total_unobserved_pixels": int(np.sum(~valid)),
        "class_counts": class_counts,
        "class_areas_ha": class_areas_ha,
    }

    return classification, intensity, uncertainty, summary
