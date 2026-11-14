#!/usr/bin/env python3
"""Execute independent Sentinel-2 optical reference generation for Similipal Tiger Reserve."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np

# Ensure backend package is in python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domains.forests.processing.optical_analysis.pipeline import (
    OpticalReferencePipeline,
)
from app.domains.forests.processing.optical_analysis.sentinel2_loader import (
    SIMILIPAL_X_MAX,
    SIMILIPAL_X_MIN,
    SIMILIPAL_Y_MAX,
    SIMILIPAL_Y_MIN,
)

RAW_DIR = ROOT / "data/reference/sentinel2_raw"
OUT_DIR = ROOT / "data/processed/optical_reference"
REF_DIR = ROOT / "data/reference"
BOUNDARIES_DIR = ROOT / "data/reference/boundaries/processed"


def generate_overview_figure(
    features: Any,
    ref_dataset: Any,
    out_png: Path,
) -> None:
    """Generate 6-panel overview of optical reference observations and categories."""
    print("Generating Figure 1: Optical Reference Overview...")
    fig, axes = plt.subplots(2, 3, figsize=(18, 12), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    # Stride for preview plotting efficiency (stride 4 matches 40 m resolution)
    stride = 4
    extent = [
        SIMILIPAL_X_MIN / 1000.0,
        SIMILIPAL_X_MAX / 1000.0,
        SIMILIPAL_Y_MIN / 1000.0,
        SIMILIPAL_Y_MAX / 1000.0,
    ]

    p1 = features.ndvi_pre[::stride, ::stride]
    p2 = features.ndvi_post[::stride, ::stride]
    p3 = features.delta_ndvi[::stride, ::stride]
    p4 = features.dnbr[::stride, ::stride]
    p5 = features.valid_count_map[::stride, ::stride].astype(float)
    p6 = ref_dataset.reference_labels[::stride, ::stride]

    # Category Colormap: 1: Red (Confirmed), 2: Green (Stable), 3: Amber (Uncertain), 4: Dark Gray (Not observable)
    cat_cmap = ListedColormap(["#1f2937", "#ef4444", "#10b981", "#f59e0b", "#4b5563"])

    panels = [
        (axes[0, 0], p1, "1. Pre-Event NDVI (2026-03-02)", "YlGn", (0.1, 0.85), "NDVI"),
        (axes[0, 1], p2, "2. Post-Event NDVI (2026-04-16)", "YlGn", (0.1, 0.85), "NDVI"),
        (axes[0, 2], p3, "3. ΔNDVI Temporal Change (t_post − t_pre)", "RdYlGn", (-0.4, 0.2), "Δ NDVI"),
        (axes[1, 0], p4, "4. USGS dNBR Burn Severity Index", "magma", (-0.1, 0.6), "dNBR"),
        (axes[1, 1], p5, "5. Valid Observation Count Map (SCL Clear-Sky)", "Blues", (0, 2), "Epochs"),
        (axes[1, 2], p6, "6. Independent Optical Reference Categories", cat_cmap, (0.5, 4.5), "Category"),
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

        if title.startswith("6."):
            # Custom legend for categories
            patches = [
                mpatches.Patch(color="#ef4444", label="1: Confirmed disturbance"),
                mpatches.Patch(color="#10b981", label="2: No observed disturbance"),
                mpatches.Patch(color="#f59e0b", label="3: Uncertain"),
                mpatches.Patch(color="#4b5563", label="4: Not observable"),
            ]
            ax.legend(handles=patches, loc="lower right", fontsize=8, facecolor="#111827", edgecolor="#374151", labelcolor="white")
        else:
            cbar = fig.colorbar(im, ax=ax, shrink=0.75, pad=0.03)
            cbar.set_label(unit, color="white", fontsize=9)
            cbar.ax.tick_params(colors="#9ca3af", labelsize=8)

    fig.suptitle(
        "Sentinel-2 L2A Independent Optical Reference Observations | Similipal Tiger Reserve\n"
        "Relative Orbit R076 Quad (Tiles T45QVE + T45QVD) | Δt = 45 Days (2026-03-02 to 2026-04-16) | 10 m Grid",
        color="white",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    fig.savefig(out_png, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Saved: {out_png}")


def generate_fire_vs_seasonal_figure(
    features: Any,
    ref_dataset: Any,
    out_png: Path,
) -> None:
    """Generate 4-panel diagnostic separating wildfire burn severity from seasonal desiccation."""
    print("Generating Figure 2: Fire vs Seasonal Desiccation Analysis...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 13), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    stride = 4
    extent = [
        SIMILIPAL_X_MIN / 1000.0,
        SIMILIPAL_X_MAX / 1000.0,
        SIMILIPAL_Y_MIN / 1000.0,
        SIMILIPAL_Y_MAX / 1000.0,
    ]

    # Panel 1: ΔNDMI Canopy Moisture Decline
    ax1 = axes[0, 0]
    ax1.set_facecolor("#111827")
    im1 = ax1.imshow(
        features.delta_ndmi[::stride, ::stride],
        extent=extent,
        cmap="PuOr",
        vmin=-0.35,
        vmax=0.15,
        origin="upper",
    )
    ax1.set_title("1. ΔNDMI Canopy Moisture Decline (t_post − t_pre)", color="white", fontsize=11, fontweight="bold")
    ax1.set_xlabel("UTM Easting (km)", color="#9ca3af", fontsize=8)
    ax1.set_ylabel("UTM Northing (km)", color="#9ca3af", fontsize=8)
    ax1.tick_params(colors="#9ca3af", labelsize=8)
    cbar1 = fig.colorbar(im1, ax=ax1, shrink=0.75, pad=0.03)
    cbar1.set_label("Δ NDMI", color="white", fontsize=9)
    cbar1.ax.tick_params(colors="#9ca3af", labelsize=8)

    # Panel 2: USGS Burn Severity Categorization
    ax2 = axes[0, 1]
    ax2.set_facecolor("#111827")
    dnbr_s = features.dnbr[::stride, ::stride]
    # Create categorical burn severity map:
    # 0: Unburned (< 0.10)
    # 1: Low-severity (0.10 to 0.27)
    # 2: Moderate-Low severity (0.27 to 0.44)
    # 3: Moderate-High / High severity (>= 0.44)
    burn_cat = np.zeros(dnbr_s.shape, dtype=np.uint8)
    burn_cat[(dnbr_s >= 0.10) & (dnbr_s < 0.27)] = 1
    burn_cat[(dnbr_s >= 0.27) & (dnbr_s < 0.44)] = 2
    burn_cat[dnbr_s >= 0.44] = 3

    burn_cmap = ListedColormap(["#10b981", "#fbbf24", "#f97316", "#dc2626"])
    im2 = ax2.imshow(burn_cat, extent=extent, cmap=burn_cmap, vmin=0, vmax=3, origin="upper")
    ax2.set_title("2. USGS dNBR Burn Severity Classification", color="white", fontsize=11, fontweight="bold")
    ax2.set_xlabel("UTM Easting (km)", color="#9ca3af", fontsize=8)
    ax2.set_ylabel("UTM Northing (km)", color="#9ca3af", fontsize=8)
    ax2.tick_params(colors="#9ca3af", labelsize=8)

    burn_patches = [
        mpatches.Patch(color="#10b981", label="Unburned (dNBR < 0.10)"),
        mpatches.Patch(color="#fbbf24", label="Low Severity (0.10 to 0.27)"),
        mpatches.Patch(color="#f97316", label="Moderate-Low Severity (0.27 to 0.44)"),
        mpatches.Patch(color="#dc2626", label="High Severity (dNBR >= 0.44)"),
    ]
    ax2.legend(handles=burn_patches, loc="lower right", fontsize=8, facecolor="#111827", edgecolor="#374151", labelcolor="white")

    # Panel 3: Detailed Optical Subtypes Map
    ax3 = axes[1, 0]
    ax3.set_facecolor("#111827")
    subtypes_s = ref_dataset.detailed_subtypes[::stride, ::stride]
    # Map subtypes to clean color scheme:
    # 11: Crown Fire Burn (#ef4444)
    # 12: Canopy Clearing / Bare Ground (#b91c1c)
    # 21: Stable Forest (#10b981)
    # 22: Stable Non-Forest (#3b82f6)
    # 31: Seasonal Phenological Desiccation (#f59e0b)
    # 32: Surface Litter Scorch (#f97316)
    # 33: Other Uncertain (#8b5cf6)
    # 40: Not Observable (#4b5563)
    sub_code_map = np.zeros(subtypes_s.shape, dtype=np.uint8)
    sub_code_map[subtypes_s == 11] = 1
    sub_code_map[subtypes_s == 12] = 2
    sub_code_map[subtypes_s == 21] = 3
    sub_code_map[subtypes_s == 22] = 4
    sub_code_map[subtypes_s == 31] = 5
    sub_code_map[subtypes_s == 32] = 6
    sub_code_map[subtypes_s == 33] = 7
    sub_code_map[subtypes_s == 40] = 0

    sub_cmap = ListedColormap(["#1f2937", "#ef4444", "#991b1b", "#10b981", "#3b82f6", "#f59e0b", "#f97316", "#8b5cf6"])
    im3 = ax3.imshow(sub_code_map, extent=extent, cmap=sub_cmap, vmin=0, vmax=7, origin="upper")
    ax3.set_title("3. Detailed Biophysical Subtypes", color="white", fontsize=11, fontweight="bold")
    ax3.set_xlabel("UTM Easting (km)", color="#9ca3af", fontsize=8)
    ax3.set_ylabel("UTM Northing (km)", color="#9ca3af", fontsize=8)
    ax3.tick_params(colors="#9ca3af", labelsize=8)

    sub_patches = [
        mpatches.Patch(color="#ef4444", label="11: Confirmed Crown Fire Burn"),
        mpatches.Patch(color="#991b1b", label="12: Confirmed Canopy Clearing"),
        mpatches.Patch(color="#10b981", label="21: Stable Forest Canopy"),
        mpatches.Patch(color="#3b82f6", label="22: Stable Non-Forest"),
        mpatches.Patch(color="#f59e0b", label="31: Seasonal Phenological Drying"),
        mpatches.Patch(color="#f97316", label="32: Surface Litter Scorch"),
        mpatches.Patch(color="#8b5cf6", label="33: Other Uncertain Shifts"),
        mpatches.Patch(color="#1f2937", label="40: Not Observable"),
    ]
    ax3.legend(handles=sub_patches, loc="lower right", fontsize=7.5, facecolor="#111827", edgecolor="#374151", labelcolor="white")

    # Panel 4: Stratified Histograms of ΔNDVI and dNBR
    ax4 = axes[1, 1]
    ax4.set_facecolor("#111827")
    valid_p = features.valid_pair_mask
    d_ndvi_vals = features.delta_ndvi[valid_p & np.isfinite(features.delta_ndvi)]
    dnbr_vals = features.dnbr[valid_p & np.isfinite(features.dnbr)]

    bins = np.linspace(-0.5, 0.5, 80)
    ax4.hist(d_ndvi_vals, bins=bins, color="#10b981", alpha=0.6, density=True, label="ΔNDVI (Greenness Change)")
    ax4.hist(dnbr_vals, bins=bins, color="#f97316", alpha=0.6, density=True, label="dNBR (Burn Severity)")
    ax4.axvline(0.0, color="#9ca3af", linestyle="--", linewidth=1.2)
    ax4.axvline(-0.20, color="#ef4444", linestyle=":", linewidth=1.5, label="ΔNDVI Loss Gate (-0.20)")
    ax4.axvline(0.27, color="#dc2626", linestyle=":", linewidth=1.5, label="dNBR Mod-High Gate (+0.27)")

    ax4.set_title("4. Empirical Spectral Differentials Distribution", color="white", fontsize=11, fontweight="bold")
    ax4.set_xlabel("Index Differential Value", color="#9ca3af", fontsize=8)
    ax4.set_ylabel("Probability Density", color="#9ca3af", fontsize=8)
    ax4.tick_params(colors="#9ca3af", labelsize=8)
    ax4.legend(loc="upper right", fontsize=7.5, facecolor="#111827", edgecolor="#374151", labelcolor="white")
    for spine in ax4.spines.values():
        spine.set_color("#374151")

    fig.suptitle(
        "Optical Biophysical Analysis | Wildfire Assessment vs Seasonal Canopy Phenology\n"
        "Separating transient leaf shedding from permanent structural canopy destruction | Similipal Tiger Reserve",
        color="white",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    fig.savefig(out_png, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Saved: {out_png}")


def generate_focal_inspection_figure(
    features: Any,
    pre_mosaic: Any,
    post_mosaic: Any,
    ref_dataset: Any,
    out_png: Path,
) -> None:
    """Generate high-resolution focal inspection of confirmed disturbance vs drying."""
    print("Generating Figure 3: Focal Disturbance Inspection...")
    # Select focal window in northern Similipal with verified candidate changes
    # Row 1600 to 2600 (height 1000 pixels = 10 km)
    # Col 2800 to 3800 (width 1000 pixels = 10 km)
    r0, r1 = 1800, 2800
    c0, c1 = 2800, 3800

    focal_extent = [
        (SIMILIPAL_X_MIN + c0 * 10.0) / 1000.0,
        (SIMILIPAL_X_MIN + c1 * 10.0) / 1000.0,
        (SIMILIPAL_Y_MAX - r1 * 10.0) / 1000.0,
        (SIMILIPAL_Y_MAX - r0 * 10.0) / 1000.0,
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18, 11), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    # False color composite: R=B08 (NIR), G=B04 (Red), B=B04 (approx false color infrared)
    nir_pre = np.clip(pre_mosaic.b08[r0:r1, c0:c1] * 2.5, 0, 1)
    red_pre = np.clip(pre_mosaic.b04[r0:r1, c0:c1] * 3.5, 0, 1)
    rgb_pre = np.dstack([nir_pre, red_pre, red_pre])

    nir_post = np.clip(post_mosaic.b08[r0:r1, c0:c1] * 2.5, 0, 1)
    red_post = np.clip(post_mosaic.b04[r0:r1, c0:c1] * 3.5, 0, 1)
    rgb_post = np.dstack([nir_post, red_post, red_post])

    cat_cmap = ListedColormap(["#1f2937", "#ef4444", "#10b981", "#f59e0b", "#4b5563"])

    # 1. Pre False Color
    ax1 = axes[0, 0]
    ax1.set_facecolor("#111827")
    ax1.imshow(rgb_pre, extent=focal_extent, origin="upper")
    ax1.set_title("1. Pre-Event False Color NIR (2026-03-02)", color="white", fontsize=11, fontweight="bold")
    ax1.tick_params(colors="#9ca3af", labelsize=8)

    # 2. Post False Color
    ax2 = axes[0, 1]
    ax2.set_facecolor("#111827")
    ax2.imshow(rgb_post, extent=focal_extent, origin="upper")
    ax2.set_title("2. Post-Event False Color NIR (2026-04-16)", color="white", fontsize=11, fontweight="bold")
    ax2.tick_params(colors="#9ca3af", labelsize=8)

    # 3. ΔNDVI
    ax3 = axes[0, 2]
    ax3.set_facecolor("#111827")
    im3 = ax3.imshow(features.delta_ndvi[r0:r1, c0:c1], extent=focal_extent, cmap="RdYlGn", vmin=-0.4, vmax=0.2, origin="upper")
    ax3.set_title("3. ΔNDVI Greenness Change", color="white", fontsize=11, fontweight="bold")
    ax3.tick_params(colors="#9ca3af", labelsize=8)
    fig.colorbar(im3, ax=ax3, shrink=0.75, pad=0.03).set_label("Δ NDVI", color="white", fontsize=9)

    # 4. dNBR
    ax4 = axes[1, 0]
    ax4.set_facecolor("#111827")
    im4 = ax4.imshow(features.dnbr[r0:r1, c0:c1], extent=focal_extent, cmap="magma", vmin=-0.1, vmax=0.6, origin="upper")
    ax4.set_title("4. USGS dNBR Burn Severity", color="white", fontsize=11, fontweight="bold")
    ax4.tick_params(colors="#9ca3af", labelsize=8)
    fig.colorbar(im4, ax=ax4, shrink=0.75, pad=0.03).set_label("dNBR", color="white", fontsize=9)

    # 5. Reference Category
    ax5 = axes[1, 1]
    ax5.set_facecolor("#111827")
    im5 = ax5.imshow(ref_dataset.reference_labels[r0:r1, c0:c1], extent=focal_extent, cmap=cat_cmap, vmin=0.5, vmax=4.5, origin="upper")
    ax5.set_title("5. Optical Reference Categories", color="white", fontsize=11, fontweight="bold")
    ax5.tick_params(colors="#9ca3af", labelsize=8)
    patches = [
        mpatches.Patch(color="#ef4444", label="Confirmed Disturbance"),
        mpatches.Patch(color="#10b981", label="No Disturbance"),
        mpatches.Patch(color="#f59e0b", label="Uncertain"),
        mpatches.Patch(color="#4b5563", label="Not Observable"),
    ]
    ax5.legend(handles=patches, loc="lower right", fontsize=7.5, facecolor="#111827", edgecolor="#374151", labelcolor="white")

    # 6. Transect Profile
    ax6 = axes[1, 2]
    ax6.set_facecolor("#111827")
    transect_row = (r0 + r1) // 2
    tr_ndvi_pre = features.ndvi_pre[transect_row, c0:c1]
    tr_ndvi_post = features.ndvi_post[transect_row, c0:c1]
    tr_dnbr = features.dnbr[transect_row, c0:c1]
    x_km = np.linspace(focal_extent[0], focal_extent[1], len(tr_ndvi_pre))

    ax6.plot(x_km, tr_ndvi_pre, color="#10b981", label="NDVI Pre (Mar 02)", linewidth=1.5)
    ax6.plot(x_km, tr_ndvi_post, color="#f59e0b", label="NDVI Post (Apr 16)", linewidth=1.5)
    ax6.plot(x_km, tr_dnbr, color="#ef4444", linestyle="--", label="dNBR (Burn)", linewidth=1.5)
    ax6.axhline(0.27, color="#dc2626", linestyle=":", linewidth=1, label="dNBR Burn Gate (+0.27)")

    ax6.set_title("6. Cross-Track Spectral Transect Profile", color="white", fontsize=11, fontweight="bold")
    ax6.set_xlabel("UTM Easting (km)", color="#9ca3af", fontsize=8)
    ax6.set_ylabel("Spectral Index Value", color="#9ca3af", fontsize=8)
    ax6.tick_params(colors="#9ca3af", labelsize=8)
    ax6.legend(loc="lower left", fontsize=7.5, facecolor="#111827", edgecolor="#374151", labelcolor="white")
    for spine in ax6.spines.values():
        spine.set_color("#374151")

    fig.suptitle(
        "Focal Area Optical Inspection | Similipal Tiger Reserve\n"
        "10 km × 10 km High-Resolution Window | Validation of Confirmed Disturbance vs Seasonal Dynamics",
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
    print("PROJECT NISAR — PHASE 4, TASK 5: OPTICAL REFERENCE GENERATION")
    print("=" * 75)

    pipeline = OpticalReferencePipeline(
        raw_dir=RAW_DIR,
        output_dir=OUT_DIR,
        reference_dir=REF_DIR,
        boundaries_dir=BOUNDARIES_DIR,
    )

    results = pipeline.run()

    # Generate publication figures
    generate_overview_figure(results["features"], results["reference_dataset"], OUT_DIR / "optical_reference_overview.png")
    generate_fire_vs_seasonal_figure(results["features"], results["reference_dataset"], OUT_DIR / "optical_fire_vs_seasonal_drying.png")
    generate_focal_inspection_figure(
        results["features"],
        results["pre_mosaic"],
        results["post_mosaic"],
        results["reference_dataset"],
        OUT_DIR / "optical_reference_focal_inspection.png",
    )

    # Serialize consolidated metrics JSON
    metrics_path = OUT_DIR / "optical_reference_metrics.json"
    consolidated_metrics = {
        "dataset_metadata": {
            "title": "Independent Sentinel-2 L2A Optical Reference Dataset",
            "study_region": "Similipal Tiger Reserve, Mayurbhanj, Odisha, India",
            "crs": "EPSG:32645",
            "spatial_extent": {
                "x_min": SIMILIPAL_X_MIN,
                "x_max": SIMILIPAL_X_MAX,
                "y_min": SIMILIPAL_Y_MIN,
                "y_max": SIMILIPAL_Y_MAX,
                "width_pixels_10m": 6232,
                "height_pixels_10m": 6616,
                "total_pixels_10m": 41230912,
            },
            "sensor": "Sentinel-2 Multi-Spectral Instrument (MSI)",
            "processing_baseline": "L2A BOA Surface Reflectance (N0512)",
            "relative_orbit": "R076",
            "temporal_pair": {
                "pre_event_date": "2026-03-02",
                "post_event_date": "2026-04-16",
                "interval_days": 45,
                "temporal_proximity_to_nisar": "NISAR T0 (2026-03-04, -2d); NISAR T1 (2026-04-21, -5d)",
            },
        },
        "performance": results["performance"],
        "category_summary": results["reference_dataset"].category_summary,
        "zonal_summary": results["reference_dataset"].zonal_summary,
        "spectral_statistics": results["features"].statistics,
    }

    with open(metrics_path, "w") as f:
        json.dump(consolidated_metrics, f, indent=2)
    print(f"\nSaved consolidated optical reference metrics JSON: {metrics_path}")

    print("\n" + "=" * 75)
    print("OPTICAL REFERENCE GENERATION SUMMARY:")
    for cat_name, stats in results["reference_dataset"].category_summary.items():
        print(f"  {stats['category_id']}: {stats['category_name']:28s} | {stats['area_km2']:8.2f} km2 ({stats['percentage_total']:5.2f}%)")
    print("=" * 75)


if __name__ == "__main__":
    main()

