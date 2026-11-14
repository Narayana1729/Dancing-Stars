#!/usr/bin/env python3
"""Execute multi-sensor comparison between NISAR candidate changes and optical reference observations."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import tracemalloc
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np
import rasterio
import rasterio.features
from scipy.ndimage import zoom
from shapely.geometry import shape

# Ensure backend package is in python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domains.forests.processing.optical_analysis.pipeline import (
    downsample_to_80m,
    write_geotiff,
)
from app.domains.forests.processing.optical_analysis.sentinel2_loader import (
    SIMILIPAL_X_MAX,
    SIMILIPAL_X_MIN,
    SIMILIPAL_Y_MAX,
    SIMILIPAL_Y_MIN,
)
from app.domains.forests.processing.validation.candidate_extractor import (
    extract_validation_candidates,
    save_validation_candidates,
)
from app.domains.forests.processing.validation.comparator import (
    CATEGORY_NAMES,
    ValidationAgreementMap,
    synthesize_validation_agreement,
)

SAR_DIR = ROOT / "data/processed/temporal"
OPT_DIR = ROOT / "data/processed/optical_reference"
REF_DIR = ROOT / "data/reference"
BOUNDARIES_DIR = ROOT / "data/reference/boundaries/processed"
OUT_DIR = ROOT / "data/processed/validation"


def generate_agreement_map_figure(
    agreement_map: np.ndarray,
    sar_dhv: np.ndarray,
    opt_dndvi: np.ndarray,
    opt_dnbr: np.ndarray,
    sar_vc: np.ndarray,
    cat_summary: dict,
    out_png: Path,
) -> None:
    """Generate 6-panel overview of multi-sensor validation agreement."""
    print("Generating Figure 1: SAR-Optical Validation Agreement Map...")
    fig, axes = plt.subplots(2, 3, figsize=(18, 12), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    stride = 4
    extent = [
        SIMILIPAL_X_MIN / 1000.0,
        SIMILIPAL_X_MAX / 1000.0,
        SIMILIPAL_Y_MIN / 1000.0,
        SIMILIPAL_Y_MAX / 1000.0,
    ]

    # Panel 1: NISAR ΔHV
    ax1 = axes[0, 0]
    ax1.set_facecolor("#111827")
    im1 = ax1.imshow(sar_dhv[::stride, ::stride], extent=extent, cmap="PuOr", vmin=-5, vmax=5, origin="upper")
    ax1.set_title("1. NISAR Δγ⁰_HV Temporal Change (10 m)", color="white", fontsize=11, fontweight="bold")
    ax1.tick_params(colors="#9ca3af", labelsize=8)
    fig.colorbar(im1, ax=ax1, shrink=0.75, pad=0.03).set_label("Δ dB", color="white", fontsize=9)

    # Panel 2: Sentinel-2 ΔNDVI
    ax2 = axes[0, 1]
    ax2.set_facecolor("#111827")
    im2 = ax2.imshow(opt_dndvi[::stride, ::stride], extent=extent, cmap="RdYlGn", vmin=-0.4, vmax=0.2, origin="upper")
    ax2.set_title("2. Sentinel-2 ΔNDVI Greenness Change (10 m)", color="white", fontsize=11, fontweight="bold")
    ax2.tick_params(colors="#9ca3af", labelsize=8)
    fig.colorbar(im2, ax=ax2, shrink=0.75, pad=0.03).set_label("Δ NDVI", color="white", fontsize=9)

    # Panel 3: Sentinel-2 dNBR
    ax3 = axes[0, 2]
    ax3.set_facecolor("#111827")
    im3 = ax3.imshow(opt_dnbr[::stride, ::stride], extent=extent, cmap="magma", vmin=-0.1, vmax=0.6, origin="upper")
    ax3.set_title("3. Sentinel-2 USGS dNBR Burn Severity (10 m)", color="white", fontsize=11, fontweight="bold")
    ax3.tick_params(colors="#9ca3af", labelsize=8)
    fig.colorbar(im3, ax=ax3, shrink=0.75, pad=0.03).set_label("dNBR", color="white", fontsize=9)

    # Panel 4: Synthesized 6-Category Agreement Map
    ax4 = axes[1, 0]
    ax4.set_facecolor("#111827")
    # Colormap:
    # 1: Green (Agree)
    # 2: Amber (SAR-only)
    # 3: Red (Opt-only)
    # 4: Orange (Seasonal)
    # 5: Purple (Uncertain)
    # 6: Gray (Insufficient observations)
    cat_cmap = ListedColormap(["#10b981", "#f59e0b", "#ef4444", "#f97316", "#8b5cf6", "#374151"])
    im4 = ax4.imshow(agreement_map[::stride, ::stride], extent=extent, cmap=cat_cmap, vmin=0.5, vmax=6.5, origin="upper")
    ax4.set_title("4. Multi-Sensor Evidence Categorization", color="white", fontsize=11, fontweight="bold")
    ax4.tick_params(colors="#9ca3af", labelsize=8)

    patches = [
        mpatches.Patch(color="#10b981", label="1: SAR & Optical agree"),
        mpatches.Patch(color="#f59e0b", label="2: SAR-only candidate"),
        mpatches.Patch(color="#ef4444", label="3: Optical-only candidate"),
        mpatches.Patch(color="#f97316", label="4: Likely seasonal variation"),
        mpatches.Patch(color="#8b5cf6", label="5: Uncertain"),
        mpatches.Patch(color="#374151", label="6: Insufficient observations"),
    ]
    ax4.legend(handles=patches, loc="lower right", fontsize=7.5, facecolor="#111827", edgecolor="#374151", labelcolor="white")

    # Panel 5: Observational Sufficiency / Coverage Mask
    ax5 = axes[1, 1]
    ax5.set_facecolor("#111827")
    obs_suff = np.where(sar_vc[::stride, ::stride] == 2, 1, 0)
    im5 = ax5.imshow(obs_suff, extent=extent, cmap=ListedColormap(["#1f2937", "#3b82f6"]), vmin=0, vmax=1, origin="upper")
    ax5.set_title("5. NISAR Frame 012 Ground Swath Coverage", color="white", fontsize=11, fontweight="bold")
    ax5.tick_params(colors="#9ca3af", labelsize=8)
    suff_patches = [
        mpatches.Patch(color="#3b82f6", label="Covered by Frame 012 (30.65%)"),
        mpatches.Patch(color="#1f2937", label="Beyond Frame 012 (Requires Frame 013)"),
    ]
    ax5.legend(handles=suff_patches, loc="lower right", fontsize=7.5, facecolor="#111827", edgecolor="#374151", labelcolor="white")

    # Panel 6: Category Area Breakdown Bar Chart
    ax6 = axes[1, 2]
    ax6.set_facecolor("#111827")
    cat_labels_short = ["1. Agree", "2. SAR-only", "3. Opt-only", "4. Seasonal", "5. Uncertain", "6. Insuff."]
    cat_areas = [cat_summary[k]["area_km2"] for k in cat_summary.keys()]
    colors = ["#10b981", "#f59e0b", "#ef4444", "#f97316", "#8b5cf6", "#374151"]

    bars = ax6.bar(cat_labels_short, cat_areas, color=colors, edgecolor="#4b5563")
    ax6.set_yscale("log")
    ax6.set_title("6. Study Area Breakdown (km² log-scale)", color="white", fontsize=11, fontweight="bold")
    ax6.set_ylabel("Area (km²)", color="#9ca3af", fontsize=9)
    ax6.tick_params(colors="#9ca3af", labelsize=8)
    for bar in bars:
        h = bar.get_height()
        ax6.annotate(f"{h:.1f}", xy=(bar.get_x() + bar.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points", ha="center", va="bottom",
                     color="white", fontsize=7.5)
    for spine in ax6.spines.values():
        spine.set_color("#374151")

    fig.suptitle(
        "Project NISAR | Multi-Temporal SAR vs Sentinel-2 Optical Validation\n"
        "Similipal Tiger Reserve, India | Independent Cross-Sensor Synthesis (10 m Grid)",
        color="white",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    fig.savefig(out_png, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Saved: {out_png}")


def generate_case_studies_figure(
    candidates: list,
    sar_dhv: np.ndarray,
    opt_dndvi: np.ndarray,
    opt_dnbr: np.ndarray,
    agreement_map: np.ndarray,
    transform: Any,
    out_png: Path,
) -> None:
    """Generate in-depth 4-case-study diagnostic figure illustrating representative candidates."""
    print("Generating Figure 2: Representative Candidate Case Studies...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 14), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    # Select representative candidate IDs for the 4 core phenomena:
    # Case 1: SAR & Optical Agree (Cat 1)
    # Case 2: SAR-Only Candidate (Cat 2)
    # Case 3: Likely Seasonal Variation (Cat 4)
    # Case 4: Insufficient Observations (Cat 6)
    selected_cases = []
    for cat_target in [1, 2, 4, 6]:
        matching = [c for c in candidates if c["properties"]["category_id"] == cat_target]
        if matching:
            selected_cases.append(matching[0])

    cat_cmap = ListedColormap(["#10b981", "#f59e0b", "#ef4444", "#f97316", "#8b5cf6", "#374151"])

    case_axes = [axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]]

    for i, (ax, cand) in enumerate(zip(case_axes, selected_cases)):
        ax.set_facecolor("#111827")
        props = cand["properties"]
        geom = cand["geometry"]
        c_x = props["centroid_utm45n"]["easting"]
        c_y = props["centroid_utm45n"]["northing"]

        # 3 km x 3 km window around candidate centroid
        half_w = 1500.0  # meters
        col_c = int((c_x - transform.c) / transform.a)
        row_c = int((c_y - transform.f) / transform.e)
        d_px = int(half_w / 10.0)

        r0 = max(0, row_c - d_px)
        r1 = min(agreement_map.shape[0], row_c + d_px)
        c0 = max(0, col_c - d_px)
        c1 = min(agreement_map.shape[1], col_c + d_px)

        sub_extent = [
            (transform.c + c0 * 10.0) / 1000.0,
            (transform.c + c1 * 10.0) / 1000.0,
            (transform.f + r1 * -10.0) / 1000.0,
            (transform.f + r0 * -10.0) / 1000.0,
        ]

        sub_agr = agreement_map[r0:r1, c0:c1]
        im = ax.imshow(sub_agr, extent=sub_extent, cmap=cat_cmap, vmin=0.5, vmax=6.5, origin="upper")

        # Mark candidate centroid
        ax.plot(c_x / 1000.0, c_y / 1000.0, marker="x", markersize=10, color="red", markeredgewidth=2)

        title_text = (
            f"Case Study {i+1}: {props['candidate_id']} | {props['validation_category']}\n"
            f"Area: {props['area_ha']} ha | Zone: {props['location_zone'].split('(')[0].strip()}"
        )
        ax.set_title(title_text, color="white", fontsize=10, fontweight="bold", pad=6)
        ax.set_xlabel("UTM Easting (km)", color="#9ca3af", fontsize=8)
        ax.set_ylabel("UTM Northing (km)", color="#9ca3af", fontsize=8)
        ax.tick_params(colors="#9ca3af", labelsize=8)

        # Scientific detail overlay text
        sar_f = props["sar_features"]
        opt_f = props["optical_features"]
        detail_str = (
            f"Δγ⁰_HV: {sar_f['mean_delta_hv_db']} dB | ΔR: {sar_f['mean_delta_ratio_db']} dB\n"
            f"ΔNDVI: {opt_f['mean_delta_ndvi']} | dNBR: {opt_f['mean_dnbr']}\n"
            f"Severity: {props['independent_evidence']['wildfire_burn_severity']}"
        )
        ax.text(
            0.03, 0.05, detail_str,
            transform=ax.transAxes,
            fontsize=7.5,
            color="white",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#111827", edgecolor="#4b5563", alpha=0.85),
        )
        for spine in ax.spines.values():
            spine.set_color("#374151")

    fig.suptitle(
        "Multi-Sensor Validation Case Studies | Project NISAR & Sentinel-2\n"
        "Representative Candidate Physical Examinations Across Similipal Tiger Reserve",
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
    print("PROJECT NISAR — PHASE 4, TASK 6: MULTI-SENSOR VALIDATION COMPARISON")
    print("=" * 75)

    tracemalloc.start()
    t_start = time.perf_counter()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load SAR 10 m and 80 m rasters
    print("\n[STEP 1/5] Loading multi-temporal NISAR rasters...")
    with rasterio.open(SAR_DIR / "freq_a_physical_change_regimes.tif") as src:
        sar_regimes_10m = src.read(1)
        transform_10m = src.transform
        crs_str = str(src.crs)

    with rasterio.open(SAR_DIR / "freq_a_valid_count.tif") as src:
        sar_vc_10m = src.read(1)

    with rasterio.open(SAR_DIR / "freq_a_delta_hv.tif") as src:
        sar_dhv_10m = src.read(1)

    with rasterio.open(SAR_DIR / "freq_a_delta_hh.tif") as src:
        sar_dhh_10m = src.read(1)

    with rasterio.open(SAR_DIR / "freq_a_delta_ratio.tif") as src:
        sar_dr_10m = src.read(1)

    with rasterio.open(SAR_DIR / "freq_a_temporal_variability.tif") as src:
        sar_tstd_10m = src.read(1)

    # 2. Load Optical 10 m rasters
    print("[STEP 2/5] Loading Sentinel-2 optical reference rasters...")
    with rasterio.open(OPT_DIR / "s2_optical_reference_labels_10m.tif") as src:
        opt_labels_10m = src.read(1)

    with rasterio.open(OPT_DIR / "s2_detailed_subtypes_10m.tif") as src:
        opt_subtypes_10m = src.read(1)

    with rasterio.open(OPT_DIR / "s2_valid_observation_count_10m.tif") as src:
        opt_vc_10m = src.read(1)

    with rasterio.open(OPT_DIR / "s2_delta_ndvi_10m.tif") as src:
        opt_dndvi_10m = src.read(1)

    with rasterio.open(OPT_DIR / "s2_dnbr_10m.tif") as src:
        opt_dnbr_10m = src.read(1)

    with rasterio.open(OPT_DIR / "s2_delta_ndmi_10m.tif") as src:
        opt_dndmi_10m = src.read(1)

    with rasterio.open(OPT_DIR / "s2_ndvi_pre_10m.tif") as src:
        opt_ndvi_pre_10m = src.read(1)

    with rasterio.open(OPT_DIR / "s2_ndvi_post_10m.tif") as src:
        opt_ndvi_post_10m = src.read(1)

    # 3. Load authoritative boundaries and reference forest cover
    print("[STEP 3/5] Loading reserve boundaries and reference forest cover...")
    with rasterio.open(REF_DIR / "similipal_reference_forest_cover.tif") as src:
        fc_80m = src.read(1)
        forest_mask_80m = fc_80m >= 30

    # Upsample forest mask to 10 m
    forest_mask_10m = zoom(forest_mask_80m.astype(np.uint8), (8, 8), order=0).astype(bool)
    forest_mask_10m = forest_mask_10m[:sar_regimes_10m.shape[0], :sar_regimes_10m.shape[1]]

    sanctuary_geojson = BOUNDARIES_DIR / "similipal_sanctuary_epsg32645.geojson"
    core_geojson = BOUNDARIES_DIR / "similipal_core_epsg32645.geojson"

    sanctuary_mask_10m = np.zeros(sar_regimes_10m.shape, dtype=bool)
    core_mask_10m = np.zeros(sar_regimes_10m.shape, dtype=bool)

    if sanctuary_geojson.exists():
        with open(sanctuary_geojson) as f:
            s_data = json.load(f)
        geoms_s = [shape(feat["geometry"]) for feat in s_data["features"]]
        sanctuary_raster = rasterio.features.rasterize(
            [(g, 1) for g in geoms_s],
            out_shape=sar_regimes_10m.shape,
            transform=transform_10m,
            fill=0,
            dtype=np.uint8,
        )
        sanctuary_mask_10m = sanctuary_raster == 1

    if core_geojson.exists():
        with open(core_geojson) as f:
            c_data = json.load(f)
        geoms_c = [shape(feat["geometry"]) for feat in c_data["features"]]
        core_raster = rasterio.features.rasterize(
            [(g, 1) for g in geoms_c],
            out_shape=sar_regimes_10m.shape,
            transform=transform_10m,
            fill=0,
            dtype=np.uint8,
        )
        core_mask_10m = core_raster == 1

    # 4. Synthesize multi-sensor validation agreement
    print("[STEP 4/5] Synthesizing multi-sensor evidence agreement...")
    val_agreement: ValidationAgreementMap = synthesize_validation_agreement(
        sar_regimes=sar_regimes_10m,
        sar_valid_count=sar_vc_10m,
        opt_labels=opt_labels_10m,
        opt_subtypes=opt_subtypes_10m,
        opt_valid_count=opt_vc_10m,
        sanctuary_mask=sanctuary_mask_10m,
        core_mask=core_mask_10m,
    )

    # Export agreement GeoTIFFs
    write_geotiff(
        OUT_DIR / "sar_optical_validation_agreement_10m.tif",
        val_agreement.agreement_map,
        transform_10m,
        crs_str,
        nodata=0,
        dtype="uint8",
    )

    agreement_80m = downsample_to_80m(val_agreement.agreement_map, is_categorical=True)
    t_80m = rasterio.transform.from_origin(SIMILIPAL_X_MIN, SIMILIPAL_Y_MAX, 80.0, 80.0)
    write_geotiff(
        OUT_DIR / "sar_optical_validation_agreement_80m.tif",
        agreement_80m,
        t_80m,
        crs_str,
        nodata=0,
        dtype="uint8",
    )

    # 5. Extract discrete candidate polygon validation dataset
    print("[STEP 5/5] Extracting discrete validation candidates...")
    candidates = extract_validation_candidates(
        agreement_map=val_agreement.agreement_map,
        sar_dhv=sar_dhv_10m,
        sar_dhh=sar_dhh_10m,
        sar_dr=sar_dr_10m,
        sar_tstd=sar_tstd_10m,
        sar_regimes=sar_regimes_10m,
        sar_vc=sar_vc_10m,
        opt_ndvi_pre=opt_ndvi_pre_10m,
        opt_ndvi_post=opt_ndvi_post_10m,
        opt_dndvi=opt_dndvi_10m,
        opt_dnbr=opt_dnbr_10m,
        opt_dndmi=opt_dndmi_10m,
        opt_labels=opt_labels_10m,
        opt_subtypes=opt_subtypes_10m,
        forest_cover_mask=forest_mask_10m,
        sanctuary_mask=sanctuary_mask_10m,
        core_mask=core_mask_10m,
        transform=transform_10m,
        max_candidates_per_cat=10,
        min_cluster_pixels=15,
    )

    save_validation_candidates(
        candidates=candidates,
        geojson_out=OUT_DIR / "validation_candidates.geojson",
        csv_out=OUT_DIR / "validation_candidates.csv",
    )

    # Generate diagnostic figures
    generate_agreement_map_figure(
        agreement_map=val_agreement.agreement_map,
        sar_dhv=sar_dhv_10m,
        opt_dndvi=opt_dndvi_10m,
        opt_dnbr=opt_dnbr_10m,
        sar_vc=sar_vc_10m,
        cat_summary=val_agreement.category_summary,
        out_png=OUT_DIR / "sar_optical_validation_agreement_map.png",
    )

    generate_case_studies_figure(
        candidates=candidates,
        sar_dhv=sar_dhv_10m,
        opt_dndvi=opt_dndvi_10m,
        opt_dnbr=opt_dnbr_10m,
        agreement_map=val_agreement.agreement_map,
        transform=transform_10m,
        out_png=OUT_DIR / "candidate_case_studies.png",
    )

    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    duration = time.perf_counter() - t_start

    # Serialize comprehensive audit metrics JSON
    metrics_path = OUT_DIR / "validation_metrics.json"
    consolidated_metrics = {
        "validation_metadata": {
            "title": "Project NISAR Multi-Sensor Validation Synthesis",
            "study_region": "Similipal Tiger Reserve, Mayurbhanj, Odisha, India",
            "crs": "EPSG:32645",
            "spatial_extent": {
                "x_min": SIMILIPAL_X_MIN,
                "x_max": SIMILIPAL_X_MAX,
                "y_min": SIMILIPAL_Y_MIN,
                "y_max": SIMILIPAL_Y_MAX,
                "total_area_km2": 4123.09,
            },
            "sensor_pairs": {
                "radar_sensor": "NISAR L-band L2 GCOV (Track 098, Frame 012)",
                "radar_epochs": ["2026-03-04", "2026-04-21"],
                "optical_sensor": "Sentinel-2 Multi-Spectral Instrument L2A (Relative Orbit R076)",
                "optical_epochs": ["2026-03-02", "2026-04-16"],
            },
        },
        "performance": {
            "duration_seconds": round(duration, 2),
            "peak_memory_mb": round(peak_mem / (1024**2), 2),
            "peak_memory_gb": round(peak_mem / (1024**3), 3),
        },
        "category_summary": val_agreement.category_summary,
        "contingency_matrix": val_agreement.contingency_matrix,
        "zonal_summary": val_agreement.zonal_summary,
        "candidate_dataset_summary": {
            "total_candidates_extracted": len(candidates),
            "geojson_file": str(OUT_DIR / "validation_candidates.geojson"),
            "csv_file": str(OUT_DIR / "validation_candidates.csv"),
        },
    }

    with open(metrics_path, "w") as f:
        json.dump(consolidated_metrics, f, indent=2)
    print(f"\nSaved consolidated validation metrics JSON: {metrics_path}")

    print("\n" + "=" * 75)
    print("VALIDATION SYNTHESIS SUMMARY:")
    for cat_name, stats in val_agreement.category_summary.items():
        print(f"  {stats['category_id']}: {stats['category_name']:42s} | {stats['area_km2']:8.2f} km2 ({stats['percentage_total']:5.2f}%)")
    print(f"  Total validation candidates extracted: {len(candidates)}")
    print("=" * 75)


if __name__ == "__main__":
    main()

