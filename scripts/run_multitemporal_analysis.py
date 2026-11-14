#!/usr/bin/env python3
"""Run multi-temporal NISAR processing pipeline for Similipal Tiger Reserve.

Processes Frequency B (80 m) and Frequency A (10 m) independently,
measures runtime and peak RAM, exports georeferenced GeoTIFFs,
generates publication diagnostic visualizations, and writes metrics JSON.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

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

T0_PATH = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
T1_PATH = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"
OUT_DIR = ROOT / "data/processed/temporal"
BOUNDARIES_DIR = ROOT / "data/reference/boundaries/processed"


def generate_backscatter_and_changes_plot(
    res_b: dict,
    out_png: Path,
) -> None:
    """Generate 6-panel overview of multi-temporal backscatter and polarimetric changes."""
    print("Generating Figure 1: Multi-temporal Backscatter and Polarimetric Changes...")
    features = res_b["features"]
    meta = res_b["series"].metadata

    fig, axes = plt.subplots(2, 3, figsize=(18, 12), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    extent = [meta.x_min / 1000.0, meta.x_max / 1000.0, meta.y_min / 1000.0, meta.y_max / 1000.0]

    panels = [
        (axes[0, 0], features.hv_db[0], "1. γ⁰_HV Backscatter at t₀ (2026-03-04)", "magma", (-26, -10), "dB"),
        (axes[0, 1], features.hv_db[1], "2. γ⁰_HV Backscatter at t₁ (2026-04-21)", "magma", (-26, -10), "dB"),
        (axes[0, 2], features.delta_hv_db[0], "3. Δγ⁰_HV Temporal Change (t₁ − t₀)", "PuOr", (-5, 5), "Δ dB"),
        (axes[1, 0], features.delta_hh_db[0], "4. Δγ⁰_HH Temporal Change (t₁ − t₀)", "RdBu_r", (-6, 6), "Δ dB"),
        (axes[1, 1], features.delta_ratio_db[0], "5. ΔR_HV/HH Cross-Ratio Change (t₁ − t₀)", "coolwarm", (-4, 4), "Δ dB"),
        (axes[1, 2], features.valid_count_map.astype(float), "6. Valid Observation Count Map", "Blues", (0, 2), "Epochs"),
    ]

    for ax, data, title, cmap, (vmin, vmax), unit in panels:
        ax.set_facecolor("#111827")
        im = ax.imshow(data, extent=extent, cmap=cmap, vmin=vmin, vmax=vmax, origin="upper")
        ax.set_title(title, color="white", fontsize=11, fontweight="bold", pad=8)
        ax.set_xlabel("UTM Zone 45N Easting (km)", color="#9ca3af", fontsize=8)
        ax.set_ylabel("UTM Zone 45N Northing (km)", color="#9ca3af", fontsize=8)
        ax.tick_params(colors="#9ca3af", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#374151")

        cbar = fig.colorbar(im, ax=ax, shrink=0.75, pad=0.03)
        cbar.set_label(unit, color="white", fontsize=9)
        cbar.ax.tick_params(colors="#9ca3af", labelsize=8)

    fig.suptitle(
        "NISAR Multi-Temporal Polarimetric Analysis | Similipal Tiger Reserve, India\n"
        f"Frequency B (80 m Grid) | Track {meta.acquisitions[0].track}, Frame {meta.acquisitions[0].frame} ({meta.acquisitions[0].orbit_pass}) | Δt = 48 Days",
        color="white",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    fig.savefig(out_png, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Saved: {out_png}")


def generate_variability_and_regimes_plot(
    res_b: dict,
    out_png: Path,
) -> None:
    """Generate 4-panel diagnostic of temporal variability and physical change regimes."""
    print("Generating Figure 2: Temporal Variability and Physical Change Regimes...")
    features = res_b["features"]
    meta = res_b["series"].metadata
    extent = [meta.x_min / 1000.0, meta.x_max / 1000.0, meta.y_min / 1000.0, meta.y_max / 1000.0]

    fig, axes = plt.subplots(2, 2, figsize=(16, 13), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    # Panel 1: Local Temporal Variability
    ax1 = axes[0, 0]
    ax1.set_facecolor("#111827")
    im1 = ax1.imshow(features.temporal_std_hv_db, extent=extent, cmap="inferno", vmin=0, vmax=3.5, origin="upper")
    ax1.set_title("1. Temporal Backscatter Variability σ_temp(HV) [dB]", color="white", fontsize=11, fontweight="bold")
    ax1.set_xlabel("UTM Easting (km)", color="#9ca3af", fontsize=8)
    ax1.set_ylabel("UTM Northing (km)", color="#9ca3af", fontsize=8)
    ax1.tick_params(colors="#9ca3af", labelsize=8)
    cbar1 = fig.colorbar(im1, ax=ax1, shrink=0.75, pad=0.03)
    cbar1.set_label("σ_temp (dB)", color="white", fontsize=9)
    cbar1.ax.tick_params(colors="#9ca3af", labelsize=8)

    # Panel 2: Spatial Neighborhood Variability of Temporal Change (3x3 kernel)
    ax2 = axes[0, 1]
    ax2.set_facecolor("#111827")
    im2 = ax2.imshow(features.spatial_local_std_delta_hv_db, extent=extent, cmap="viridis", vmin=0, vmax=2.5, origin="upper")
    ax2.set_title("2. Spatial Neighborhood Variability of ΔHV (3×3 Kernel)", color="white", fontsize=11, fontweight="bold")
    ax2.set_xlabel("UTM Easting (km)", color="#9ca3af", fontsize=8)
    ax2.set_ylabel("UTM Northing (km)", color="#9ca3af", fontsize=8)
    ax2.tick_params(colors="#9ca3af", labelsize=8)
    cbar2 = fig.colorbar(im2, ax=ax2, shrink=0.75, pad=0.03)
    cbar2.set_label("Spatial Local σ (dB)", color="white", fontsize=9)
    cbar2.ax.tick_params(colors="#9ca3af", labelsize=8)

    # Panel 3: Physical Change Regimes Map
    ax3 = axes[1, 0]
    ax3.set_facecolor("#111827")
    from matplotlib.colors import ListedColormap
    # Regimes: 0=Masked, 1=Stable, 2=Desiccation, 3=Roughness/Moisture, 4=Disturbance Candidate, 5=Ambiguous
    regime_cmap = ListedColormap(["#1f2937", "#10b981", "#f59e0b", "#3b82f6", "#ef4444", "#8b5cf6"])
    im3 = ax3.imshow(features.physical_change_regimes, extent=extent, cmap=regime_cmap, vmin=0, vmax=5, origin="upper")
    ax3.set_title("3. Physical Polarimetric Scattering Regimes", color="white", fontsize=11, fontweight="bold")
    ax3.set_xlabel("UTM Easting (km)", color="#9ca3af", fontsize=8)
    ax3.set_ylabel("UTM Northing (km)", color="#9ca3af", fontsize=8)
    ax3.tick_params(colors="#9ca3af", labelsize=8)

    regime_patches = [
        mpatches.Patch(color="#1f2937", label="0: Unobserved / Masked"),
        mpatches.Patch(color="#10b981", label="1: Stable Forest Canopy"),
        mpatches.Patch(color="#f59e0b", label="2: Seasonal Moisture Desiccation"),
        mpatches.Patch(color="#3b82f6", label="3: Surface Roughness / Moisture Infiltration"),
        mpatches.Patch(color="#ef4444", label="4: Candidate Canopy Disturbance"),
        mpatches.Patch(color="#8b5cf6", label="5: Ambiguous Polarimetric Shift"),
    ]
    ax3.legend(handles=regime_patches, loc="lower right", fontsize=8, facecolor="#111827", edgecolor="#374151", labelcolor="white")

    # Panel 4: Stratified Distribution of ΔHV
    ax4 = axes[1, 1]
    ax4.set_facecolor("#111827")
    dhv = features.delta_hv_db[0]
    inter = features.intersection_mask
    zstats = res_b["zonal_statistics"]["delta_hv_db"]

    bins = np.linspace(-6, 6, 80)
    # Stratified samples
    # Sanctuary vs outside
    s_mask = inter & (res_b["boundary_masks"]["sanctuary_pixels"] > 0)
    # We can reconstruct masks from zonal counts or plot overall
    ax4.hist(dhv[inter], bins=bins, color="#60a5fa", alpha=0.6, density=True, label="All Valid ROI Pixels")
    ax4.axvline(0.0, color="#9ca3af", linestyle="--", linewidth=1.2, label="Zero Change")
    ax4.axvline(zstats["overall"]["mean"], color="#ef4444", linestyle="-", linewidth=1.5, label=f"ROI Mean: {zstats['overall']['mean']:.2f} dB")
    ax4.axvline(zstats["sanctuary"]["mean"], color="#10b981", linestyle=":", linewidth=1.8, label=f"Sanctuary Mean: {zstats['sanctuary']['mean']:.2f} dB")

    ax4.set_title("4. Stratified Δγ⁰_HV Temporal Change Distribution", color="white", fontsize=11, fontweight="bold")
    ax4.set_xlabel("Δγ⁰_HV (dB)", color="#9ca3af", fontsize=9)
    ax4.set_ylabel("Probability Density", color="#9ca3af", fontsize=9)
    ax4.tick_params(colors="#9ca3af", labelsize=8)
    ax4.legend(loc="upper right", fontsize=8, facecolor="#111827", edgecolor="#374151", labelcolor="white")
    for spine in ax4.spines.values():
        spine.set_color("#374151")

    fig.suptitle(
        "NISAR Temporal Variability & Physical Scattering Regimes | Similipal Tiger Reserve\n"
        "Multi-temporal 48-day baseline (2026-03-04 to 2026-04-21) | Non-thresholded physical categorization",
        color="white",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    fig.savefig(out_png, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Saved: {out_png}")


def generate_candidate_disturbance_inspection_plot(
    res_b: dict,
    out_png: Path,
) -> None:
    """Generate high-resolution inspection of candidate disturbance zones vs seasonal drying."""
    print("Generating Figure 3: Candidate Disturbance Spatial Inspection...")
    features = res_b["features"]
    meta = res_b["series"].metadata

    # Select a focal patch with significant candidate changes (e.g. northern buffer / core boundary)
    # Patch centered around UTM Easting 430-445 km, Northing 2410-2425 km
    # Index in Frequency B (827 x 779):
    # Y: 2438.36 down to 2372.28 -> 2410-2425 is approximately index rows 150 to 350
    # X: 401.64 to 463.88 -> 430-445 is approximately index cols 350 to 550
    y0, y1 = 200, 380
    x0, x1 = 340, 520

    sub_extent = [
        (meta.x_min + x0 * 80.0) / 1000.0,
        (meta.x_min + x1 * 80.0) / 1000.0,
        (meta.y_max - y1 * 80.0) / 1000.0,
        (meta.y_max - y0 * 80.0) / 1000.0,
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18, 11), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    patch_panels = [
        (axes[0, 0], features.hv_db[0][y0:y1, x0:x1], "1. γ⁰_HV Backscatter at t₀ (March 04)", "magma", (-26, -10), "dB"),
        (axes[0, 1], features.hv_db[1][y0:y1, x0:x1], "2. γ⁰_HV Backscatter at t₁ (April 21)", "magma", (-26, -10), "dB"),
        (axes[0, 2], features.delta_hv_db[0][y0:y1, x0:x1], "3. Δγ⁰_HV Temporal Difference", "PuOr", (-5, 5), "Δ dB"),
        (axes[1, 0], features.delta_ratio_db[0][y0:y1, x0:x1], "4. ΔR_HV/HH Cross-Ratio Change", "coolwarm", (-4, 4), "Δ dB"),
        (axes[1, 1], features.persistence_indicator[y0:y1, x0:x1], "5. Corroborated Disturbance Metric", "Reds", (0, 4), "Score"),
    ]

    for ax, data, title, cmap, (vmin, vmax), unit in patch_panels:
        ax.set_facecolor("#111827")
        im = ax.imshow(data, extent=sub_extent, cmap=cmap, vmin=vmin, vmax=vmax, origin="upper")
        ax.set_title(title, color="white", fontsize=11, fontweight="bold", pad=8)
        ax.set_xlabel("UTM Easting (km)", color="#9ca3af", fontsize=8)
        ax.set_ylabel("UTM Northing (km)", color="#9ca3af", fontsize=8)
        ax.tick_params(colors="#9ca3af", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#374151")
        cbar = fig.colorbar(im, ax=ax, shrink=0.75, pad=0.03)
        cbar.set_label(unit, color="white", fontsize=9)
        cbar.ax.tick_params(colors="#9ca3af", labelsize=8)

    # Panel 6: Cross-track transect profile
    ax6 = axes[1, 2]
    ax6.set_facecolor("#111827")
    transect_row = (y0 + y1) // 2
    transect_hv0 = features.hv_db[0][transect_row, x0:x1]
    transect_hv1 = features.hv_db[1][transect_row, x0:x1]
    transect_dhv = features.delta_hv_db[0][transect_row, x0:x1]
    x_km = np.linspace(sub_extent[0], sub_extent[1], len(transect_hv0))

    ax6.plot(x_km, transect_hv0, color="#f59e0b", label="HV at t₀ (March 04)", linewidth=1.5)
    ax6.plot(x_km, transect_hv1, color="#60a5fa", label="HV at t₁ (April 21)", linewidth=1.5)
    ax6.plot(x_km, transect_dhv, color="#ef4444", linestyle="--", label="ΔHV (t₁ − t₀)", linewidth=1.5)
    ax6.axhline(0, color="#6b7280", linestyle=":", linewidth=1)
    ax6.axhline(-2.5, color="#f87171", linestyle=":", linewidth=1, label="Disturbance Ref (-2.5 dB)")

    ax6.set_title("6. Cross-Track Transect Backscatter Profile", color="white", fontsize=11, fontweight="bold", pad=8)
    ax6.set_xlabel("UTM Easting (km)", color="#9ca3af", fontsize=8)
    ax6.set_ylabel("Backscatter (dB)", color="#9ca3af", fontsize=8)
    ax6.tick_params(colors="#9ca3af", labelsize=8)
    ax6.legend(loc="lower left", fontsize=7.5, facecolor="#111827", edgecolor="#374151", labelcolor="white")
    for spine in ax6.spines.values():
        spine.set_color("#374151")

    fig.suptitle(
        "Candidate Disturbance Spatial Inspection | Similipal Tiger Reserve\n"
        "Physical Volume Scattering Decline vs Seasonal Phenological Variation | 14.4 km × 14.4 km Focal Window",
        color="white",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    fig.savefig(out_png, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Saved: {out_png}")


def main():
    print("=" * 75)
    print("PROJECT NISAR — PHASE 4, TASK 4: MULTI-TEMPORAL PROCESSING PIPELINE")
    print("=" * 75)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    file_paths = [T0_PATH, T1_PATH]

    pipeline = MultiTemporalNISARPipeline(
        output_dir=OUT_DIR,
        boundaries_dir=BOUNDARIES_DIR,
    )

    # 1. Execute Frequency B (80 m) multi-temporal pipeline
    print("\n[STEP 1/3] Processing Frequency B (80 m) multi-temporal baseline...")
    res_b = pipeline.run_frequency_pipeline(
        file_paths=file_paths,
        frequency_key="frequencyB",
        export_rasters=True,
    )

    # 2. Execute Frequency A (10 m) multi-temporal pipeline
    print("\n[STEP 2/3] Processing Frequency A (10 m) high-resolution pipeline...")
    res_a = pipeline.run_frequency_pipeline(
        file_paths=file_paths,
        frequency_key="frequencyA",
        export_rasters=True,
    )

    # 3. Generate diagnostic visual inspection products
    print("\n[STEP 3/3] Generating diagnostic visual figures...")
    generate_backscatter_and_changes_plot(res_b, OUT_DIR / "multitemporal_backscatter_and_changes.png")
    generate_variability_and_regimes_plot(res_b, OUT_DIR / "temporal_variability_and_regimes.png")
    generate_candidate_disturbance_inspection_plot(res_b, OUT_DIR / "candidate_disturbance_spatial_inspection.png")

    # 4. Save consolidated pipeline metrics JSON
    metrics_path = OUT_DIR / "temporal_pipeline_metrics.json"
    consolidated_metrics = {
        "pipeline_metadata": {
            "execution_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "study_region": "Similipal Tiger Reserve, Mayurbhanj, Odisha, India",
            "crs": "EPSG:32645",
            "spatial_bounding_box_utm45n": {
                "x_min": SIMILIPAL_X_MIN,
                "x_max": SIMILIPAL_X_MAX,
                "y_min": SIMILIPAL_Y_MIN,
                "y_max": SIMILIPAL_Y_MAX,
            },
            "temporal_series": {
                "number_of_epochs_available": 2,
                "note_on_time_series_depth": (
                    "Only two authentic Indian NISAR observations (2026-03-04 and 2026-04-21) "
                    "are currently archived in data/raw/India/. Temporal baseline is 48 days. "
                    "A multi-temporal series with N >= 3 epochs remains pending further ingestion."
                ),
                "epochs": [
                    {
                        "index": 0,
                        "date": "2026-03-04",
                        "granule_id": res_b["series"].metadata.acquisitions[0].granule_id,
                        "crid": res_b["series"].metadata.acquisitions[0].crid,
                        "track": res_b["series"].metadata.acquisitions[0].track,
                        "frame": res_b["series"].metadata.acquisitions[0].frame,
                        "orbit_pass": res_b["series"].metadata.acquisitions[0].orbit_pass,
                        "look_direction": res_b["series"].metadata.acquisitions[0].look_direction,
                    },
                    {
                        "index": 1,
                        "date": "2026-04-21",
                        "granule_id": res_b["series"].metadata.acquisitions[1].granule_id,
                        "crid": res_b["series"].metadata.acquisitions[1].crid,
                        "track": res_b["series"].metadata.acquisitions[1].track,
                        "frame": res_b["series"].metadata.acquisitions[1].frame,
                        "orbit_pass": res_b["series"].metadata.acquisitions[1].orbit_pass,
                        "look_direction": res_b["series"].metadata.acquisitions[1].look_direction,
                    },
                ],
            },
        },
        "frequency_b_80m": {
            "performance": res_b["performance"].to_dict(),
            "zonal_statistics": res_b["zonal_statistics"],
            "regime_areas": res_b["regime_areas"],
            "raster_paths": res_b["raster_paths"],
        },
        "frequency_a_10m": {
            "performance": res_a["performance"].to_dict(),
            "zonal_statistics": res_a["zonal_statistics"],
            "regime_areas": res_a["regime_areas"],
            "raster_paths": res_a["raster_paths"],
        },
    }

    with open(metrics_path, "w") as f:
        json.dump(consolidated_metrics, f, indent=2)
    print(f"\nSaved consolidated metrics JSON: {metrics_path}")

    print("\n" + "=" * 75)
    print("MULTI-TEMPORAL PROCESSING SUMMARY:")
    print(f"  Frequency B (80 m): Runtime = {res_b['performance'].duration_seconds}s | Peak RAM = {res_b['performance'].peak_ram_mb} MB")
    print(f"  Frequency A (10 m): Runtime = {res_a['performance'].duration_seconds}s | Peak RAM = {res_a['performance'].peak_ram_mb} MB")
    print(f"  Total GeoTIFFs generated: {len(res_b['raster_paths']) + len(res_a['raster_paths'])}")
    print("=" * 75)


if __name__ == "__main__":
    main()

