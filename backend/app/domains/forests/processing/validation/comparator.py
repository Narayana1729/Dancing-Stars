"""Synthesized multi-sensor comparison between multi-temporal NISAR and optical reference."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple
import numpy as np


@dataclass
class ValidationAgreementMap:
    """Pixel-level multi-sensor evidence categorization map across Similipal study area."""
    # Categorical Agreement Raster (uint8):
    #   1: SAR and optical evidence agree
    #   2: SAR-only candidate
    #   3: Optical-only candidate
    #   4: Likely seasonal or temporary variation
    #   5: Uncertain
    #   6: Insufficient observations
    agreement_map: np.ndarray
    # Category summary (pixel counts, percentages, area in ha and km2)
    category_summary: Dict[str, Dict[str, Any]]
    # Cross-tabulation confusion matrix between SAR Regime and Optical Category
    contingency_matrix: Dict[str, Dict[str, int]]
    # Zonal summary stratified across Core, Sanctuary, and Outside Reserve
    zonal_summary: Dict[str, Dict[str, Any]]


CATEGORY_NAMES = {
    1: "SAR and optical evidence agree",
    2: "SAR-only candidate",
    3: "Optical-only candidate",
    4: "Likely seasonal or temporary variation",
    5: "Uncertain",
    6: "Insufficient observations",
}


def synthesize_validation_agreement(
    sar_regimes: np.ndarray,      # uint8: 0 to 5 from Frequency A (10 m)
    sar_valid_count: np.ndarray,  # uint8: 0, 1, 2
    opt_labels: np.ndarray,       # uint8: 1 to 4 from Sentinel-2 (10 m)
    opt_subtypes: np.ndarray,     # uint8: 11, 12, 21, 22, 31, 32, 33, 40
    opt_valid_count: np.ndarray,  # uint8: 0, 1, 2
    sanctuary_mask: np.ndarray,   # bool: Similipal Sanctuary
    core_mask: np.ndarray,        # bool: Similipal Core CTH
) -> ValidationAgreementMap:
    """Synthesize pixel-level multi-sensor validation agreement map.

    Evidence Categories:
      1: SAR and optical evidence agree
         - Severe disturbance agreement: SAR Regime 4 & Optical Category 1
         - Stable forest canopy agreement: SAR Regime 1 & Optical Subtype 21
      2: SAR-only candidate: SAR Regime 4 & Optical Category 2 (No observed disturbance)
      3: Optical-only candidate: Optical Category 1 & SAR Regime 1 (Stable SAR)
      4: Likely seasonal or temporary variation: SAR backscatter decline (Regimes 2, 4, 5)
         corroborated by Optical seasonal desiccation (Subtype 31) or surface litter scorch (Subtype 32)
      5: Uncertain: Conflicting, ambiguous, or agricultural/riparian shifts
      6: Insufficient observations: Missing SAR coverage (N_sar < 2) OR optical cloud/shadow (N_opt < 2)
    """
    shape = sar_regimes.shape
    agreement = np.full(shape, 6, dtype=np.uint8)  # Default: 6 (Insufficient observations)

    both_valid = (sar_valid_count == 2) & (opt_valid_count == 2)

    # 1. SAR and optical evidence agree
    # A. Disturbance agreement: Both flag severe disturbance
    dist_agree = both_valid & (sar_regimes == 4) & (opt_labels == 1)
    # B. Stable agreement: Both flag stable closed canopy forest
    stable_agree = both_valid & (sar_regimes == 1) & (opt_subtypes == 21)
    agreement[dist_agree | stable_agree] = 1

    # 2. SAR-only candidate: SAR flags candidate disturbance, Optical shows clear-sky stability
    sar_only = both_valid & (sar_regimes == 4) & (opt_labels == 2)
    agreement[sar_only] = 2

    # 3. Optical-only candidate: Optical confirms disturbance, SAR shows stability
    opt_only = both_valid & (opt_labels == 1) & (sar_regimes == 1)
    agreement[opt_only] = 3

    # 4. Likely seasonal or temporary variation: SAR backscatter decline matched with
    # Optical seasonal desiccation (Subtype 31) or low-severity surface litter scorch (Subtype 32)
    seasonal = both_valid & np.isin(sar_regimes, [2, 4, 5]) & np.isin(opt_subtypes, [31, 32])
    agreement[seasonal] = 4

    # 5. Uncertain: Remaining both-valid pixels with ambiguous or complex shifts
    uncertain = both_valid & (agreement == 6)
    agreement[uncertain] = 5

    # 6. Summary metrics calculation (10 m resolution: 1 px = 0.01 ha = 0.0001 km2)
    total_pixels = int(agreement.size)
    summary: Dict[str, Dict[str, Any]] = {}
    for cat_id, cat_name in CATEGORY_NAMES.items():
        cnt = int(np.sum(agreement == cat_id))
        pct = (cnt / total_pixels) * 100.0
        ha = cnt * 0.01
        km2 = cnt * 0.0001
        summary[f"category_{cat_id}_{cat_name.lower().replace(' ', '_').replace('-', '_')}"] = {
            "category_id": cat_id,
            "category_name": cat_name,
            "pixel_count": cnt,
            "percentage_total": round(pct, 2),
            "area_ha": round(ha, 2),
            "area_km2": round(km2, 2),
        }

    # Cross-tabulation contingency matrix over both_valid pixels
    contingency: Dict[str, Dict[str, int]] = {}
    for r in range(1, 6):
        r_dict: Dict[str, int] = {}
        r_mask = both_valid & (sar_regimes == r)
        for o in range(1, 5):
            o_cnt = int(np.sum(r_mask & (opt_labels == o)))
            r_dict[f"opt_category_{o}"] = o_cnt
        contingency[f"sar_regime_{r}"] = r_dict

    # Zonal summary across management zones
    zonal: Dict[str, Dict[str, Any]] = {}
    zones = {
        "sanctuary": sanctuary_mask,
        "core": core_mask,
        "outside_reserve": ~sanctuary_mask,
    }

    for zone_name, z_mask in zones.items():
        z_total = int(np.sum(z_mask))
        z_dict: Dict[str, Any] = {"total_zone_pixels": z_total}
        for cat_id, cat_name in CATEGORY_NAMES.items():
            cnt = int(np.sum((agreement == cat_id) & z_mask))
            pct = (cnt / z_total * 100.0) if z_total > 0 else 0.0
            ha = cnt * 0.01
            km2 = cnt * 0.0001
            z_dict[f"category_{cat_id}"] = {
                "name": cat_name,
                "pixel_count": cnt,
                "percentage_zone": round(pct, 2),
                "area_ha": round(ha, 2),
                "area_km2": round(km2, 2),
            }
        zonal[zone_name] = z_dict

    return ValidationAgreementMap(
        agreement_map=agreement,
        category_summary=summary,
        contingency_matrix=contingency,
        zonal_summary=zonal,
    )

