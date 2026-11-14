"""Forest disturbance analysis service executing multi-temporal NISAR analytics."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import h5py
import numpy as np
import rasterio

from app.domains.forests.algorithms.change_detector import (
    DisturbanceDetectionResult,
    StatisticalForestDisturbanceDetector,
)

ROOT = Path(__file__).resolve().parents[5]
RAW_INDIA = ROOT / "data/raw/India"
REF_DIR = ROOT / "data/reference"

T0_FILE = (
    RAW_INDIA
    / "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
)
T1_FILE = (
    RAW_INDIA
    / "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"
)
FOREST_COVER_TIF = REF_DIR / "similipal_reference_forest_cover.tif"
GFC_LOSS_TIF = REF_DIR / "similipal_reference_gfc_loss.tif"

# Frequency B indices corresponding to Similipal Reserve BBox
Y_SLICE = slice(363, 1190)
X_SLICE = slice(502, 1281)


class ForestAnalysisService:
    def __init__(self) -> None:
        self.detector = StatisticalForestDisturbanceDetector(
            default_threshold_db=-2.5,
            min_cluster_pixels=3,
            pixel_size_m=80.0,
        )

    def load_data(self) -> Dict[str, Any]:
        if not T0_FILE.exists() or not T1_FILE.exists():
            raise FileNotFoundError("Authentic NISAR L2 GCOV multi-temporal files not found in data/raw/India/")
        if not FOREST_COVER_TIF.exists():
            raise FileNotFoundError("Reference forest cover dataset not found in data/reference/")

        with h5py.File(T0_FILE, "r") as h0, h5py.File(T1_FILE, "r") as h1:
            g0 = h0["/science/LSAR/GCOV/grids/frequencyB"]
            g1 = h1["/science/LSAR/GCOV/grids/frequencyB"]

            hh0 = g0["HHHH"][Y_SLICE, X_SLICE]
            hv0 = g0["HVHV"][Y_SLICE, X_SLICE]
            hh1 = g1["HHHH"][Y_SLICE, X_SLICE]
            hv1 = g1["HVHV"][Y_SLICE, X_SLICE]

        with rasterio.open(FOREST_COVER_TIF) as src_tc:
            forest_canopy = src_tc.read(1)
            forest_mask = forest_canopy >= 30  # Standard FSI/FAO 30% threshold

        ref_loss = None
        if GFC_LOSS_TIF.exists():
            with rasterio.open(GFC_LOSS_TIF) as src_loss:
                ref_loss = src_loss.read(1)

        return {
            "baseline": {"hh": hh0, "hv": hv0},
            "target": {"hh": hh1, "hv": hv1},
            "forest_mask": forest_mask,
            "reference_loss": ref_loss,
        }

    def run_analysis(
        self,
        threshold_db: float = -2.5,
        min_cluster_pixels: int = 3,
        apply_spatial_filter: bool = True,
    ) -> Dict[str, Any]:
        data = self.load_data()

        primary_result = self.detector.detect(
            baseline=data["baseline"],
            target=data["target"],
            forest_mask=data["forest_mask"],
            threshold_db=threshold_db,
            apply_filter=apply_spatial_filter,
            min_cluster_pixels=min_cluster_pixels,
            reference_disturbance=data["reference_loss"],
        )

        # Sensitivity sweep across candidate thresholds
        sensitivity_sweep = self.detector.evaluate_sensitivity(
            baseline=data["baseline"],
            target=data["target"],
            forest_mask=data["forest_mask"],
            thresholds=[-1.5, -2.0, -2.5, -3.0, -3.5],
            min_cluster=min_cluster_pixels,
            reference_disturbance=data["reference_loss"],
        )

        return {
            "study_region": {
                "name": "Similipal Tiger Reserve, Odisha, India",
                "center_coordinates": {"latitude": 21.75, "longitude": 86.35},
                "projected_crs": "EPSG:32645 (UTM Zone 45N)",
                "pixel_spacing_m": 80.0,
                "domain": "forest_disturbance_detection",
                "methodology": "Statistical Multi-Temporal SAR Radiometric Change Detection",
            },
            "observations": {
                "baseline_t0": {
                    "scene_id": "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001",
                    "timestamp": "2026-03-04T23:37:20Z",
                    "orbit_track": 98,
                    "frame": 12,
                    "pass": "Ascending",
                },
                "target_t1": {
                    "scene_id": "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001",
                    "timestamp": "2026-04-21T23:37:20Z",
                    "orbit_track": 98,
                    "frame": 12,
                    "pass": "Ascending",
                },
                "temporal_separation_days": 48,
                "orbital_cycles": 4,
            },
            "primary_detection": {
                "threshold_db": primary_result.threshold_db,
                "detected_pixels": primary_result.detected_pixels,
                "detected_area_ha": primary_result.detected_area_ha,
                "detected_area_km2": primary_result.detected_area_km2,
                "total_forest_pixels": primary_result.total_forest_pixels,
                "total_forest_area_km2": primary_result.total_forest_area_km2,
                "disturbance_fraction_percent": primary_result.disturbance_fraction_percent,
                "mean_forest_delta_hv_db": primary_result.mean_forest_delta_hv_db,
                "std_forest_delta_hv_db": primary_result.std_forest_delta_hv_db,
                "median_forest_delta_hv_db": primary_result.median_forest_delta_hv_db,
                "spatial_filter_applied": primary_result.spatial_filter_applied,
                "min_cluster_pixels": primary_result.min_cluster_pixels,
                "cluster_count": primary_result.cluster_count,
                "seven_class_distribution": primary_result.seven_class_distribution,
                "tier_statuses": primary_result.tier_statuses,
            },
            "capabilities_audit": {
                "available": [
                    "tier1_instantaneous_candidate_detection",
                    "seven_class_deterministic_screening",
                    "physical_scattering_regimes",
                    "polarimetric_differencing",
                ],
                "blocked": {
                    "supervised_ml": "Requires ≥ 50 verified field compartments (43 samples exist; 53,556:1 imbalance).",
                    "seasonal_baseline": "Requires 8-12 acquisitions across 3 seasons (only 2 spring dates exist).",
                    "tier2_sustained": "Requires ≥ 3 consecutive epochs (N = 2 available).",
                    "tier3_persistent": "Requires ≥ 180 days across seasonal transitions (48 days available).",
                    "canopy_recovery": "Requires post-disturbance repeat monitoring cycles.",
                },
            },
            "validation": primary_result.validation_metrics,
            "sensitivity_analysis": [
                {
                    "threshold_db": r.threshold_db,
                    "detected_pixels": r.detected_pixels,
                    "detected_area_ha": r.detected_area_ha,
                    "disturbance_fraction_percent": r.disturbance_fraction_percent,
                    "cluster_count": r.cluster_count,
                    "false_positive_rate": r.validation_metrics["false_positive_rate"]
                    if r.validation_metrics
                    else None,
                }
                for r in sensitivity_sweep
            ],
            "reference_sources": {
                "forest_mask": "Hansen Global Forest Change v1.11 (treecover2000 >= 30% canopy)",
                "historical_benchmark": "Hansen Global Forest Change v1.11 (lossyear 2001-2023)",
                "national_benchmark": "Forest Survey of India (ISFR Mayurbhanj District Assessment)",
            },
        }
