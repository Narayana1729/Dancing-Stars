"""Statistical Forest Disturbance Anomaly Detector for Multi-Temporal NISAR Observations.

Scientific Basis:
1. Reference labels in the active swath are statistically insufficient to support
   supervised empirical threshold calibration or machine learning.
2. The detector implements an unsupervised, robust statistical anomaly framework
   using Median and MAD-based standardized z-scores (Z_MAD).
3. Evaluates multiple statistical approaches:
   - Robust temporal statistics (Median and MAD)
   - Multi-feature statistical rules (Z_MAD <= -k AND Delta_R <= -tau_R AND HV0 >= tau_base)
   - Change-point / standardized distance metrics
   - Spatial clustering with Minimum Mapping Unit (MMU) enforcement
4. All detections are strictly labelled as 'Candidate Radiometric Changes'.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from app.domains.forests.detection.features import (
    RobustForestStatistics,
    compute_robust_forest_statistics,
    compute_robust_z_scores,
    compute_temporal_sar_features,
)
from app.domains.forests.detection.spatial_context import (
    MMUConfiguration,
    filter_by_minimum_mapping_unit,
    get_default_mmu_config,
)

CANDIDATE_CATEGORIES = {
    0: "Non-Forest or Masked",
    1: "Candidate Volume Scattering Loss",
    2: "Candidate Surface / Dielectric Shift",
    3: "Stable Radiometric Baseline",
    4: "Uncertain / Complex Change",
}


@dataclass
class DetectionParameters:
    """Detection parameters for robust statistical anomaly detection."""
    z_mad_threshold: float = 2.0           # Standardized robust MAD z-score cutoff (|Z| >= threshold)
    delta_ratio_threshold_db: float = 1.0  # Differential ratio drop cutoff (Delta_R <= -threshold)
    min_baseline_hv_db: float = -22.0      # Minimum pre-event HV backscatter confirming tree canopy
    apply_mmu: bool = True                 # Whether to apply spatial MMU filtering
    mmu_config: Optional[MMUConfiguration] = None


@dataclass
class DetectionSummary:
    """Summary metrics of statistical candidate anomaly detection."""
    frequency_name: str
    pixel_size_m: float
    total_domain_pixels: int
    total_forest_pixels: int
    total_forest_area_km2: float
    robust_stats: RobustForestStatistics
    detected_candidate_pixels: int
    detected_candidate_area_ha: float
    detected_candidate_area_km2: float
    candidate_fraction_percent: float
    cluster_count: int
    mmu_stats: Dict[str, Any]
    category_breakdown: Dict[str, Dict[str, Any]]
    detection_parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frequency_name": self.frequency_name,
            "pixel_size_m": self.pixel_size_m,
            "total_domain_pixels": self.total_domain_pixels,
            "total_forest_pixels": self.total_forest_pixels,
            "total_forest_area_km2": self.total_forest_area_km2,
            "robust_stats": asdict(self.robust_stats),
            "detected_candidate_pixels": self.detected_candidate_pixels,
            "detected_candidate_area_ha": self.detected_candidate_area_ha,
            "detected_candidate_area_km2": self.detected_candidate_area_km2,
            "candidate_fraction_percent": self.candidate_fraction_percent,
            "cluster_count": self.cluster_count,
            "mmu_stats": self.mmu_stats,
            "category_breakdown": self.category_breakdown,
            "detection_parameters": self.detection_parameters,
        }


class StatisticalDisturbanceDetector:
    """Unsupervised robust statistical anomaly detector for multi-temporal NISAR."""

    def __init__(
        self,
        frequency: str = "frequencyA",
        params: Optional[DetectionParameters] = None,
    ) -> None:
        self.frequency = frequency
        self.params = params or DetectionParameters()
        if self.params.mmu_config is None:
            self.params.mmu_config = get_default_mmu_config(frequency)

    def detect_candidate_changes(
        self,
        hh0: np.ndarray,
        hv0: np.ndarray,
        hh1: np.ndarray,
        hv1: np.ndarray,
        forest_mask: np.ndarray,
        valid_mask: np.ndarray,
        input_in_db: bool = False,
    ) -> Tuple[np.ndarray, np.ndarray, DetectionSummary]:
        """Detect candidate radiometric changes across the documented forest mask.

        Parameters
        ----------
        hh0, hv0 : np.ndarray
            Baseline linear backscatter at t0.
        hh1, hv1 : np.ndarray
            Target linear backscatter at t1.
        forest_mask : np.ndarray
            Documented forest cover mask (boolean).
        valid_mask : np.ndarray
            Valid observation mask (boolean).

        Returns
        -------
        categorical_map : np.ndarray
            Categorical map with values 0 to 4.
        z_scores : np.ndarray
            Standardized robust Z-score array (floating point).
        summary : DetectionSummary
            Comprehensive detection metrics.
        """
        # 1. Compute calibrated features
        features = compute_temporal_sar_features(
            hh0, hv0, hh1, hv1, valid_mask, input_in_db=input_in_db
        )
        eval_valid = features["valid_mask"] & forest_mask

        total_forest_pixels = int(np.sum(eval_valid))
        if total_forest_pixels == 0:
            raise ValueError("No valid forest pixels available within the evaluation domain.")

        pixel_area_ha = self.params.mmu_config.pixel_area_ha
        total_forest_area_km2 = round((total_forest_pixels * pixel_area_ha) / 100.0, 2)

        # 2. Compute robust forest background statistics
        robust_stats = compute_robust_forest_statistics(
            delta_hv=features["delta_hv"],
            forest_mask=forest_mask,
            valid_mask=features["valid_mask"],
        )

        # 3. Standardize delta_hv into robust Z-scores
        z_scores = compute_robust_z_scores(
            delta_hv=features["delta_hv"],
            median_val=robust_stats.median_delta_hv_db,
            mad_scale=robust_stats.mad_scale_sigma_db,
            valid_mask=features["valid_mask"],
        )

        # 4. Multi-Feature Statistical Anomaly Rules
        # Rule A: Significant volume scattering anomaly (Z_MAD <= -threshold)
        raw_vol_loss = (
            eval_valid
            & (z_scores <= -self.params.z_mad_threshold)
            & (features["delta_ratio"] <= -self.params.delta_ratio_threshold_db)
            & (features["hv0_db"] >= self.params.min_baseline_hv_db)
        )

        # Rule B: Surface / Dielectric shift (Z_MAD <= -threshold, but Delta_R does not drop)
        raw_surface_shift = (
            eval_valid
            & (z_scores <= -self.params.z_mad_threshold)
            & (features["delta_ratio"] > -self.params.delta_ratio_threshold_db)
        )

        # 5. Spatial context / MMU filtering
        if self.params.apply_mmu:
            filtered_vol_loss, cluster_count, mmu_stats = filter_by_minimum_mapping_unit(
                binary_mask=raw_vol_loss,
                mmu_config=self.params.mmu_config,
            )
            filtered_surface_shift, _, _ = filter_by_minimum_mapping_unit(
                binary_mask=raw_surface_shift,
                mmu_config=self.params.mmu_config,
            )
        else:
            filtered_vol_loss = raw_vol_loss
            filtered_surface_shift = raw_surface_shift
            cluster_count = 0
            mmu_stats = {
                "total_retained_clusters": 0,
                "total_retained_pixels": int(np.sum(filtered_vol_loss)),
                "total_retained_area_ha": round(int(np.sum(filtered_vol_loss)) * pixel_area_ha, 3),
                "filtered_sub_mmu_pixels": 0,
                "filtered_sub_mmu_clusters": 0,
            }

        # 6. Assemble categorical classification map
        cat_map = np.zeros(eval_valid.shape, dtype=np.uint8)
        # Class 3: Stable radiometric baseline
        cat_map[eval_valid] = 3
        # Class 4: Uncertain / Complex shifts (|Z| >= threshold positive or noisy)
        cat_map[eval_valid & (z_scores >= self.params.z_mad_threshold)] = 4
        # Class 2: Surface / Dielectric shift
        cat_map[filtered_surface_shift] = 2
        # Class 1: Candidate Volume Scattering Loss (Primary candidate disturbance)
        cat_map[filtered_vol_loss] = 1

        # Calculate category breakdown
        total_domain = int(cat_map.size)
        cat_breakdown = {}
        for c_id, c_name in CANDIDATE_CATEGORIES.items():
            cnt = int(np.sum(cat_map == c_id))
            ha = round(cnt * pixel_area_ha, 2)
            km2 = round(ha / 100.0, 4)
            pct = round((cnt / total_forest_pixels) * 100.0, 2) if total_forest_pixels > 0 and c_id != 0 else round((cnt / total_domain) * 100.0, 2)
            cat_breakdown[f"category_{c_id}"] = {
                "id": c_id,
                "name": c_name,
                "pixel_count": cnt,
                "area_ha": ha,
                "area_km2": km2,
                "percentage": pct,
            }

        detected_pixels = int(np.sum(filtered_vol_loss))
        detected_ha = round(detected_pixels * pixel_area_ha, 2)
        detected_km2 = round(detected_ha / 100.0, 4)
        pct_forest = round((detected_pixels / total_forest_pixels) * 100.0, 3)

        summary = DetectionSummary(
            frequency_name=self.params.mmu_config.frequency_name,
            pixel_size_m=self.params.mmu_config.pixel_size_m,
            total_domain_pixels=total_domain,
            total_forest_pixels=total_forest_pixels,
            total_forest_area_km2=total_forest_area_km2,
            robust_stats=robust_stats,
            detected_candidate_pixels=detected_pixels,
            detected_candidate_area_ha=detected_ha,
            detected_candidate_area_km2=detected_km2,
            candidate_fraction_percent=pct_forest,
            cluster_count=cluster_count,
            mmu_stats=mmu_stats,
            category_breakdown=cat_breakdown,
            detection_parameters={
                "z_mad_threshold": self.params.z_mad_threshold,
                "delta_ratio_threshold_db": self.params.delta_ratio_threshold_db,
                "min_baseline_hv_db": self.params.min_baseline_hv_db,
                "min_cluster_pixels": self.params.mmu_config.min_cluster_pixels,
                "mmu_area_ha": self.params.mmu_config.mmu_area_ha,
                "apply_mmu": self.params.apply_mmu,
            },
        )

        return cat_map, z_scores, summary
