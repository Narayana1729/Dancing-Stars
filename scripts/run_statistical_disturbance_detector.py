#!/usr/bin/env python3
"""Project NISAR — Statistical Forest Disturbance Anomaly Detector Runner.

Executes:
1. Independent Reference Label Audit (verifying calibration stop mandate).
2. Frequency A (10 m) candidate anomaly detection with MMU = 0.05 ha (5 px).
3. Frequency B (80 m) candidate anomaly detection with MMU = 0.64 ha (1 px).
4. Threshold sensitivity sweep (Historical unvalidated vs Robust Z_MAD).
5. GeoTIFF raster exports to data/processed/detection/.
6. Diagnostic figure generation and detection_metrics.json export.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from scipy.ndimage import zoom

# Ensure backend package is in python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domains.forests.detection import (
    CANDIDATE_CATEGORIES,
    DetectionParameters,
    StatisticalDisturbanceDetector,
    audit_reference_label_sufficiency,
    run_threshold_sensitivity_suite,
)

TEMPORAL_DIR = ROOT / "data/processed/temporal"
OPTICAL_DIR = ROOT / "data/processed/optical_reference"
VALIDATION_DIR = ROOT / "data/processed/validation"
REFERENCE_DIR = ROOT / "data/reference"
OUT_DIR = ROOT / "data/processed/detection"


def write_geotiff(
    out_path: Path,
    array: np.ndarray,
    transform: rasterio.Affine,
    crs: str,
    nodata: float = 0,
    dtype: str = "uint8",
) -> None:
    """Write 2D NumPy array to georeferenced GeoTIFF."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    height, width = array.shape
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
        compress="lzw",
    ) as dst:
        dst.write(array.astype(dtype), 1)
    print(f"  Saved GeoTIFF: {out_path} ({height}x{width}, dtype={dtype})")


def plot_detector_comparison(
    cat_map_a: np.ndarray,
    z_scores_a: np.ndarray,
    cat_map_b: np.ndarray,
    z_scores_b: np.ndarray,
    summary_a: dict,
    summary_b: dict,
    out_path: Path,
) -> None:
    """Generate 4-panel comparison figure between Frequency A and Frequency B."""
    print("Generating Figure 1: Frequency A vs Frequency B Detector Comparison...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 14), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    # Extent in km
    extent = [401.64, 463.96, 2372.20, 2438.36]

    # Panel 1: Frequency A Categorical Detections (10 m)
    ax1 = axes[0, 0]
    ax1.set_facecolor("#111827")
    cmap_cat = plt.matplotlib.colors.ListedColormap([
        "#1f2937",  # 0: Masked
        "#ef4444",  # 1: Volume Loss (Red)
        "#f59e0b",  # 2: Surface/Dielectric (Amber)
        "#10b981",  # 3: Stable (Emerald)
        "#6366f1",  # 4: Uncertain (Indigo)
    ])
    stride_a = 4
    im1 = ax1.imshow(
        cat_map_a[::stride_a, ::stride_a],
        extent=extent,
        cmap=cmap_cat,
        vmin=0,
        vmax=4,
        origin="upper",
    )
    ax1.set_title(
        f"1. Frequency A (10 m) Candidate Radiometric Changes\nDetected: {summary_a['detected_candidate_area_ha']:.1f} ha ({summary_a['candidate_fraction_percent']:.2f}% of Forest)",
        color="white",
        fontsize=11,
        fontweight="bold",
    )
    ax1.tick_params(colors="#9ca3af", labelsize=8)

    # Panel 2: Frequency A Robust Z-Scores
    ax2 = axes[0, 1]
    ax2.set_facecolor("#111827")
    im2 = ax2.imshow(
        z_scores_a[::stride_a, ::stride_a],
        extent=extent,
        cmap="coolwarm_r",
        vmin=-4,
        vmax=4,
        origin="upper",
    )
    ax2.set_title(
        f"2. Frequency A (10 m) Standardized Robust Z_MAD\nForest Median: {summary_a['robust_stats']['median_delta_hv_db']:.2f} dB, Scale: {summary_a['robust_stats']['mad_scale_sigma_db']:.2f} dB",
        color="white",
        fontsize=11,
        fontweight="bold",
    )
    ax2.tick_params(colors="#9ca3af", labelsize=8)
    fig.colorbar(im2, ax=ax2, shrink=0.75, pad=0.03).set_label("Z_MAD (Standardized)", color="white", fontsize=9)

    # Panel 3: Frequency B Categorical Detections (80 m)
    ax3 = axes[1, 0]
    ax3.set_facecolor("#111827")
    im3 = ax3.imshow(
        cat_map_b,
        extent=extent,
        cmap=cmap_cat,
        vmin=0,
        vmax=4,
        origin="upper",
    )
    ax3.set_title(
        f"3. Frequency B (80 m) Candidate Radiometric Changes\nDetected: {summary_b['detected_candidate_area_ha']:.1f} ha ({summary_b['candidate_fraction_percent']:.2f}% of Forest)",
        color="white",
        fontsize=11,
        fontweight="bold",
    )
    ax3.tick_params(colors="#9ca3af", labelsize=8)

    # Panel 4: Frequency B Robust Z-Scores
    ax4 = axes[1, 1]
    ax4.set_facecolor("#111827")
    im4 = ax4.imshow(
        z_scores_b,
        extent=extent,
        cmap="coolwarm_r",
        vmin=-4,
        vmax=4,
        origin="upper",
    )
    ax4.set_title(
        f"4. Frequency B (80 m) Standardized Robust Z_MAD\nForest Median: {summary_b['robust_stats']['median_delta_hv_db']:.2f} dB, Scale: {summary_b['robust_stats']['mad_scale_sigma_db']:.2f} dB",
        color="white",
        fontsize=11,
        fontweight="bold",
    )
    ax4.tick_params(colors="#9ca3af", labelsize=8)
    fig.colorbar(im4, ax=ax4, shrink=0.75, pad=0.03).set_label("Z_MAD (Standardized)", color="white", fontsize=9)

    plt.savefig(out_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved: {out_path}")


def plot_sensitivity_curves(
    sensitivity_metrics: list[dict],
    out_path: Path,
) -> None:
    """Generate sensitivity and false alarm comparison chart."""
    print("Generating Figure 2: Sensitivity and False Alarm Curves...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    # Filter into historical vs robust
    hist = [m for m in sensitivity_metrics if m["threshold_type"] == "historical_db" and m["ratio_threshold_db"] is None]
    zmad = [m for m in sensitivity_metrics if m["threshold_type"] == "robust_z_mad" and m["ratio_threshold_db"] is None]

    # Panel 1: False Alarm Percentage (%) vs Cutoff
    ax1.set_facecolor("#111827")
    x_hist = [m["threshold_value"] for m in hist]
    fa_hist = [m["false_alarm_percentage"] for m in hist]
    area_hist = [m["detected_area_ha"] for m in hist]

    ax1.plot(x_hist, fa_hist, marker="o", color="#ef4444", linewidth=2.5, label="Historical ΔHV (dB)")
    ax1.set_title("Historical Threshold False-Alarm Rate (%)\n(False Positives / Total Detections)", color="white", fontsize=11, fontweight="bold")
    ax1.set_xlabel("ΔHV Threshold (dB)", color="#9ca3af", fontsize=9)
    ax1.set_ylabel("False Alarm %", color="#9ca3af", fontsize=9)
    ax1.set_ylim(80, 100.5)
    ax1.grid(True, linestyle="--", alpha=0.3, color="#374151")
    ax1.tick_params(colors="#9ca3af", labelsize=8)
    ax1.legend(facecolor="#1f2937", edgecolor="#374151", labelcolor="white")

    # Panel 2: Detected Area (ha) vs False Positives
    ax2.set_facecolor("#111827")
    x_z = [m["threshold_value"] for m in zmad]
    area_z = [m["detected_area_ha"] for m in zmad]
    rec_z = [m["recall"] * 100.0 for m in zmad]

    ax2.plot(x_z, area_z, marker="s", color="#3b82f6", linewidth=2.5, label="Robust Z_MAD Area (ha)")
    ax2.set_title("Robust Z_MAD Candidate Anomaly Area (ha)\nvs Z-Score Cutoff", color="white", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Z_MAD Cutoff", color="#9ca3af", fontsize=9)
    ax2.set_ylabel("Flagged Area (ha)", color="#9ca3af", fontsize=9)
    ax2.grid(True, linestyle="--", alpha=0.3, color="#374151")
    ax2.tick_params(colors="#9ca3af", labelsize=8)
    ax2.legend(facecolor="#1f2937", edgecolor="#374151", labelcolor="white")

    plt.savefig(out_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved: {out_path}")


def main() -> None:
    t_start = time.time()
    print("=" * 75)
    print("PROJECT NISAR — PHASE 4: STATISTICAL FOREST DISTURBANCE ANOMALY DETECTOR")
    print("=" * 75)

    # 1. Independent Reference Label Sufficiency Audit
    print("\n[STEP 1/5] Auditing independent reference label sufficiency...")
    val_json_path = VALIDATION_DIR / "validation_metrics.json"
    audit_res = audit_reference_label_sufficiency(validation_metrics_path=val_json_path)

    print(f"  Positive disturbance samples : {audit_res.positive_disturbance_pixels} pixels ({audit_res.positive_area_ha} ha)")
    print(f"  Negative stable samples      : {audit_res.negative_stable_pixels:,} pixels")
    print(f"  Class imbalance ratio        : 1 : {audit_res.class_imbalance_ratio:,.0f}")
    print(f"  Sufficient for calibration   : {audit_res.is_sufficient_for_calibration}")
    print(f"  Calibration stop mandate     : {audit_res.calibration_stop_mandate}")
    print(f"  Audit conclusion             : {audit_res.stop_reason}")

    # 2. Load Multi-Temporal NISAR Observations
    print("\n[STEP 2/5] Loading multi-temporal NISAR observations...")
    # Frequency A (10 m)
    with rasterio.open(TEMPORAL_DIR / "freq_a_hh_t0.tif") as src:
        hh0_a = src.read(1)
        transform_a = src.transform
        crs_str = src.crs.to_string()
    with rasterio.open(TEMPORAL_DIR / "freq_a_hv_t0.tif") as src:
        hv0_a = src.read(1)
    with rasterio.open(TEMPORAL_DIR / "freq_a_hh_t1.tif") as src:
        hh1_a = src.read(1)
    with rasterio.open(TEMPORAL_DIR / "freq_a_hv_t1.tif") as src:
        hv1_a = src.read(1)
    with rasterio.open(TEMPORAL_DIR / "freq_a_valid_count.tif") as src:
        vc_a = src.read(1) == 2

    # Frequency B (80 m)
    with rasterio.open(TEMPORAL_DIR / "freq_b_hh_t0.tif") as src:
        hh0_b = src.read(1)
        transform_b = src.transform
    with rasterio.open(TEMPORAL_DIR / "freq_b_hv_t0.tif") as src:
        hv0_b = src.read(1)
    with rasterio.open(TEMPORAL_DIR / "freq_b_hh_t1.tif") as src:
        hh1_b = src.read(1)
    with rasterio.open(TEMPORAL_DIR / "freq_b_hv_t1.tif") as src:
        hv1_b = src.read(1)
    with rasterio.open(TEMPORAL_DIR / "freq_b_valid_count.tif") as src:
        vc_b = src.read(1) == 2

    # Load reference forest cover
    with rasterio.open(REFERENCE_DIR / "similipal_reference_forest_cover.tif") as src:
        fc_80m = src.read(1)
        forest_mask_80m = fc_80m >= 30

    # Upsample forest mask to 10 m
    forest_mask_10m = zoom(forest_mask_80m.astype(np.uint8), (8, 8), order=0).astype(bool)
    forest_mask_10m = forest_mask_10m[:hh0_a.shape[0], :hh0_a.shape[1]]

    # Load independent optical reference labels for sensitivity evaluation
    with rasterio.open(OPTICAL_DIR / "s2_optical_reference_labels_10m.tif") as src:
        opt_labels_10m = src.read(1)

    # 3. Execute Detector on Frequency A (10 m)
    print("\n[STEP 3/5] Executing detector on Frequency A (10 m native grid)...")
    detector_a = StatisticalDisturbanceDetector(
        frequency="frequencyA",
        params=DetectionParameters(
            z_mad_threshold=2.0,
            delta_ratio_threshold_db=1.0,
            min_baseline_hv_db=-22.0,
            apply_mmu=True,
        ),
    )
    cat_map_a, z_scores_a, summary_a = detector_a.detect_candidate_changes(
        hh0=hh0_a,
        hv0=hv0_a,
        hh1=hh1_a,
        hv1=hv1_a,
        forest_mask=forest_mask_10m,
        valid_mask=vc_a,
        input_in_db=True,
    )
    print(f"  Frequency A Forest Pixels    : {summary_a.total_forest_pixels:,} ({summary_a.total_forest_area_km2:.2f} km2)")
    print(f"  Background Forest Median     : {summary_a.robust_stats.median_delta_hv_db:.2f} dB")
    print(f"  Background MAD Scale         : {summary_a.robust_stats.mad_scale_sigma_db:.2f} dB")
    print(f"  Detected Candidate Volume Loss: {summary_a.detected_candidate_pixels:,} px ({summary_a.detected_candidate_area_ha:.2f} ha, {summary_a.candidate_fraction_percent:.3f}%)")
    print(f"  MMU Filtered Sub-MMU Pixels  : {summary_a.mmu_stats['filtered_sub_mmu_pixels']:,} px in {summary_a.mmu_stats['filtered_sub_mmu_clusters']:,} clusters")

    # 4. Execute Detector on Frequency B (80 m)
    print("\n[STEP 4/5] Executing detector on Frequency B (80 m regional grid)...")
    detector_b = StatisticalDisturbanceDetector(
        frequency="frequencyB",
        params=DetectionParameters(
            z_mad_threshold=2.0,
            delta_ratio_threshold_db=1.0,
            min_baseline_hv_db=-22.0,
            apply_mmu=True,
        ),
    )
    cat_map_b, z_scores_b, summary_b = detector_b.detect_candidate_changes(
        hh0=hh0_b,
        hv0=hv0_b,
        hh1=hh1_b,
        hv1=hv1_b,
        forest_mask=forest_mask_80m[:hh0_b.shape[0], :hh0_b.shape[1]],
        valid_mask=vc_b,
        input_in_db=True,
    )
    print(f"  Frequency B Forest Pixels    : {summary_b.total_forest_pixels:,} ({summary_b.total_forest_area_km2:.2f} km2)")
    print(f"  Background Forest Median     : {summary_b.robust_stats.median_delta_hv_db:.2f} dB")
    print(f"  Background MAD Scale         : {summary_b.robust_stats.mad_scale_sigma_db:.2f} dB")
    print(f"  Detected Candidate Volume Loss: {summary_b.detected_candidate_pixels:,} px ({summary_b.detected_candidate_area_ha:.2f} ha, {summary_b.candidate_fraction_percent:.3f}%)")

    # 5. Run Threshold Sensitivity Suite on Frequency A
    print("\n[STEP 5/5] Running threshold sensitivity & false-alarm evaluation...")
    with rasterio.open(TEMPORAL_DIR / "freq_a_delta_hv.tif") as src:
        dhv_10m = src.read(1)
    with rasterio.open(TEMPORAL_DIR / "freq_a_delta_ratio.tif") as src:
        dr_10m = src.read(1)

    sensitivity_results = run_threshold_sensitivity_suite(
        delta_hv=dhv_10m,
        delta_ratio=dr_10m,
        z_scores=z_scores_a,
        reference_labels=opt_labels_10m,
        forest_mask=forest_mask_10m,
        valid_mask=vc_a,
        pixel_area_ha=0.01,
    )

    print("\n" + "=" * 95)
    print(f"{'THRESHOLD CANDIDATE':<45} | {'AREA (ha)':<10} | {'TP (px)':<7} | {'FP (px)':<8} | {'PRECISION':<9} | {'FALSE ALARM %':<12}")
    print("-" * 95)
    for res in sensitivity_results:
        print(f"{res.threshold_name:<45} | {res.detected_area_ha:<10.1f} | {res.true_positive_pixels:<7} | {res.false_positive_pixels:<8} | {res.precision:<9.6f} | {res.false_alarm_percentage:<12.2f}%")
    print("=" * 95)

    # 6. Export GeoTIFFs
    print("\nExporting output GeoTIFFs...")
    write_geotiff(
        OUT_DIR / "freq_a_candidate_radiometric_changes_10m.tif",
        cat_map_a,
        transform_a,
        crs_str,
        nodata=0,
        dtype="uint8",
    )
    write_geotiff(
        OUT_DIR / "freq_a_robust_zscore_10m.tif",
        z_scores_a,
        transform_a,
        crs_str,
        nodata=-9999.0,
        dtype="float32",
    )
    write_geotiff(
        OUT_DIR / "freq_b_candidate_radiometric_changes_80m.tif",
        cat_map_b,
        transform_b,
        crs_str,
        nodata=0,
        dtype="uint8",
    )
    write_geotiff(
        OUT_DIR / "freq_b_robust_zscore_80m.tif",
        z_scores_b,
        transform_b,
        crs_str,
        nodata=-9999.0,
        dtype="float32",
    )

    # 7. Generate Diagnostic Figures
    plot_detector_comparison(
        cat_map_a=cat_map_a,
        z_scores_a=z_scores_a,
        cat_map_b=cat_map_b,
        z_scores_b=z_scores_b,
        summary_a=summary_a.to_dict(),
        summary_b=summary_b.to_dict(),
        out_path=OUT_DIR / "detector_comparison_freq_a_vs_b.png",
    )

    plot_sensitivity_curves(
        sensitivity_metrics=[r.to_dict() for r in sensitivity_results],
        out_path=OUT_DIR / "sensitivity_and_false_alarm_curves.png",
    )

    # 8. Save Machine-Readable Detection Metrics JSON
    consolidated_metrics = {
        "metadata": {
            "title": "Project NISAR Statistical Forest Disturbance Anomaly Detection",
            "study_region": "Similipal Tiger Reserve, Mayurbhanj, Odisha, India",
            "crs": crs_str,
            "temporal_baseline": {
                "t0": "2026-03-04T00:23:42 UTC",
                "t1": "2026-04-21T00:23:42 UTC",
                "delta_days": 48,
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "reference_label_audit": audit_res.to_dict(),
        "frequency_a_10m": summary_a.to_dict(),
        "frequency_b_80m": summary_b.to_dict(),
        "sensitivity_evaluation": [r.to_dict() for r in sensitivity_results],
        "deliverables": {
            "freq_a_candidate_changes_tif": str(OUT_DIR / "freq_a_candidate_radiometric_changes_10m.tif"),
            "freq_a_zscore_tif": str(OUT_DIR / "freq_a_robust_zscore_10m.tif"),
            "freq_b_candidate_changes_tif": str(OUT_DIR / "freq_b_candidate_radiometric_changes_80m.tif"),
            "freq_b_zscore_tif": str(OUT_DIR / "freq_b_robust_zscore_80m.tif"),
            "comparison_figure": str(OUT_DIR / "detector_comparison_freq_a_vs_b.png"),
            "sensitivity_figure": str(OUT_DIR / "sensitivity_and_false_alarm_curves.png"),
        },
        "performance": {
            "duration_seconds": round(time.time() - t_start, 2),
        },
    }

    metrics_json_path = OUT_DIR / "detection_metrics.json"
    with open(metrics_json_path, "w", encoding="utf-8") as f:
        json.dump(consolidated_metrics, f, indent=2)
    print(f"Saved consolidated metrics JSON: {metrics_json_path}")
    print(f"\nDetection Pipeline Complete in {time.time() - t_start:.2f} s")


if __name__ == "__main__":
    main()
