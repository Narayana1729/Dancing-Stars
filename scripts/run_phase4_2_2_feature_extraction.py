#!/usr/bin/env python3
"""Execute Phase 4.2.2 generalized multi-temporal feature extraction in an isolated directory.

Runs Frequency B (80 m) and Frequency A (10 m) pipelines, writes outputs strictly to
data/processed/validation/temporal_regression/, and performs automated numerical
comparison against Phase 4.1.1 baseline rasters in data/processed/temporal/.
"""
from __future__ import annotations

import json
import os
import resource
import sys
import time
from pathlib import Path
import numpy as np
import rasterio

# Ensure backend package is accessible
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domains.forests.processing.temporal_analysis.pipeline import (
    MultiTemporalNISARPipeline,
)
from app.domains.forests.processing.temporal_analysis.temporal_loader import (
    SIMILIPAL_X_MAX,
    SIMILIPAL_X_MIN,
    SIMILIPAL_Y_MAX,
    SIMILIPAL_Y_MIN,
)
from app.domains.forests.processing.temporal_analysis.temporal_validation import (
    compare_raster_baselines,
)

T0_PATH = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
T1_PATH = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"

BASELINE_DIR = ROOT / "data/processed/temporal"
REGRESSION_DIR = ROOT / "data/processed/validation/temporal_regression"
BOUNDARIES_DIR = ROOT / "data/reference/boundaries/processed"


def read_geotiff(path: Path) -> np.ndarray:
    """Read full GeoTIFF raster into NumPy array."""
    with rasterio.open(path) as src:
        return src.read(1)


def run_phase4_2_2_pipeline() -> Dict[str, Any]:
    """Execute isolated regression pipeline and compare with Phase 4.1.1 baseline."""
    print("=" * 80)
    print("PROJECT NISAR — PHASE 4.2.2 MULTI-TEMPORAL FEATURE EXTRACTION & REGRESSION")
    print("=" * 80)
    print(f"Baseline Directory (Read-Only): {BASELINE_DIR.relative_to(ROOT)}")
    print(f"Regression Directory (Isolated): {REGRESSION_DIR.relative_to(ROOT)}")

    REGRESSION_DIR.mkdir(parents=True, exist_ok=True)
    file_paths = [T0_PATH, T1_PATH]

    pipeline = MultiTemporalNISARPipeline(
        output_dir=REGRESSION_DIR,
        boundaries_dir=BOUNDARIES_DIR,
    )

    # 1. Execute Frequency B (80 m)
    print("\n[Step 1/3] Processing Frequency B (80 m) in regression directory...")
    t0_b = time.perf_counter()
    res_b = pipeline.run_frequency_pipeline(
        file_paths=file_paths,
        frequency_key="frequencyB",
        export_rasters=True,
    )
    dur_b = time.perf_counter() - t0_b

    # 2. Execute Frequency A (10 m)
    print("\n[Step 2/3] Processing Frequency A (10 m) in regression directory...")
    t0_a = time.perf_counter()
    res_a = pipeline.run_frequency_pipeline(
        file_paths=file_paths,
        frequency_key="frequencyA",
        export_rasters=True,
    )
    dur_a = time.perf_counter() - t0_a

    # 3. Perform Numerical Backward-Compatibility Comparison
    print("\n[Step 3/3] Performing numerical comparison against Phase 4.1.1 baseline...")
    comparison_targets = [
        # (filename, is_mask, tolerance)
        ("freq_b_hh_t0.tif", False, 1e-5),
        ("freq_b_hv_t0.tif", False, 1e-5),
        ("freq_b_ratio_t0.tif", False, 1e-5),
        ("freq_b_hh_t1.tif", False, 1e-5),
        ("freq_b_hv_t1.tif", False, 1e-5),
        ("freq_b_ratio_t1.tif", False, 1e-5),
        ("freq_b_delta_hh.tif", False, 1e-5),
        ("freq_b_delta_hv.tif", False, 1e-5),
        ("freq_b_delta_ratio.tif", False, 1e-5),
        ("freq_b_temporal_variability.tif", False, 1e-5),
        ("freq_b_valid_count.tif", True, 0.0),
        ("freq_b_physical_change_regimes.tif", True, 0.0),
    ]

    comparisons: Dict[str, Any] = {}
    all_passed = True

    for fname, is_mask, tol in comparison_targets:
        base_file = BASELINE_DIR / fname
        reg_file = REGRESSION_DIR / fname

        if not base_file.exists():
            print(f"  ⚠ Baseline file missing: {fname} (Skipping comparison)")
            continue
        if not reg_file.exists():
            print(f"  ❌ Regression file missing: {fname}")
            all_passed = False
            continue

        arr_base = read_geotiff(base_file)
        arr_reg = read_geotiff(reg_file)

        comp = compare_raster_baselines(arr_base, arr_reg, tolerance=tol, is_mask=is_mask)
        comparisons[fname] = comp

        status_str = "✓ PASS" if comp["is_compatible"] else "❌ FAIL"
        max_err = comp.get("max_absolute_difference", 0.0)
        exceeding = comp.get("pixels_exceeding_tolerance", 0)
        nan_mismatch = comp.get("nodata_location_mismatches", 0)

        print(f"  {status_str} | {fname:<35} | MaxDiff: {max_err:.2e} | Mismatch: {exceeding} px | NaNDiff: {nan_mismatch} px")
        if not comp["is_compatible"]:
            all_passed = False

    # Process RSS measurement
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    max_rss_mb = (max_rss / (1024 * 1024)) if sys.platform == "darwin" else (max_rss / 1024)

    summary_report = {
        "execution_metadata": {
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "platform": sys.platform,
            "overall_backward_compatibility_verdict": "PASSED" if all_passed else "FAILED",
            "process_peak_rss_mb": round(max_rss_mb, 2),
            "performance": {
                "frequency_b_seconds": round(dur_b, 2),
                "frequency_a_seconds": round(dur_a, 2),
            },
        },
        "regression_comparisons": comparisons,
        "theil_sen_performance_b": res_b["features"].theil_sen_performance,
        "theil_sen_performance_a": res_a["features"].theil_sen_performance,
        "disturbance_status_b": {
            "tier1_active": True,
            "tier2_status": res_b["features"].tier2_status,
            "tier3_status": res_b["features"].tier3_status,
        },
    }

    report_path = REGRESSION_DIR / "phase4_2_2_regression_comparison.json"
    with open(report_path, "w") as f:
        json.dump(summary_report, f, indent=2)

    print(f"\nSaved regression comparison report: {report_path.relative_to(ROOT)}")
    print("=" * 80)
    return summary_report


if __name__ == "__main__":
    run_phase4_2_2_pipeline()

