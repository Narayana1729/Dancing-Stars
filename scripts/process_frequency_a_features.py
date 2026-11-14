#!/usr/bin/env python3
"""Execute Frequency A windowed loading, polarimetric feature extraction, and export.

Saves georeferenced rasters, metadata, and diagnostic figures to data/processed/frequency_a/.
"""
from __future__ import annotations

import json
import os
import sys
import time
import tracemalloc
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import rasterio

# Ensure backend package is in python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domains.forests.processing.frequency_a_loader import (
    SIMILIPAL_X_MAX,
    SIMILIPAL_X_MIN,
    SIMILIPAL_Y_MAX,
    SIMILIPAL_Y_MIN,
    load_frequency_a_window,
)
from app.domains.forests.processing.polarimetric_features import (
    extract_polarimetric_features,
)

T0_PATH = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
T1_PATH = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"
OUT_DIR = ROOT / "data/processed/frequency_a"


def write_geotiff(
    out_path: Path,
    array: np.ndarray,
    transform: Any,
    crs: str,
    nodata: Optional[float] = np.nan,
    dtype: str = "float32",
) -> None:
    profile = {
        "driver": "GTiff",
        "height": array.shape[0],
        "width": array.shape[1],
        "count": 1,
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
        "compress": "deflate",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    if nodata is not None:
        profile["nodata"] = nodata

    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(array.astype(dtype), 1)


def generate_diagnostic_plot(
    features: Any,
    meta: Any,
    out_png: Path,
) -> None:
    print("Rendering diagnostic plots...")
    fig, axes = plt.subplots(2, 3, figsize=(18, 12), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    # Downsample for preview plotting (stride 8 matches Frequency B resolution for fast rendering)
    stride = 4
    extent = [
        meta.x_min / 1000.0,
        meta.x_max / 1000.0,
        meta.y_min / 1000.0,
        meta.y_max / 1000.0,
    ]

    panels = [
        (
            axes[0, 0],
            features.delta_gamma0_hh_db[::stride, ::stride],
            "1. Δγ⁰_HH Temporal Change (t₁ − t₀)",
            "RdBu_r",
            (-6, 6),
            "Δ dB",
        ),
        (
            axes[0, 1],
            features.delta_gamma0_hv_db[::stride, ::stride],
            "2. Δγ⁰_HV Volume Scattering Change (t₁ − t₀)",
            "PuOr",
            (-5, 5),
            "Δ dB",
        ),
        (
            axes[0, 2],
            features.delta_ratio_hv_hh_db[::stride, ::stride],
            "3. ΔR_HV/HH Temporal Ratio Change (t₁ − t₀)",
            "coolwarm",
            (-4, 4),
            "Δ dB",
        ),
        (
            axes[1, 0],
            features.ratio_hv_hh_t0_db[::stride, ::stride],
            "4. R_HV/HH Cross-Ratio at t₀ (2026-03-04)",
            "viridis",
            (-12, -2),
            "dB",
        ),
        (
            axes[1, 1],
            features.ratio_hv_hh_t1_db[::stride, ::stride],
            "5. R_HV/HH Cross-Ratio at t₁ (2026-04-21)",
            "viridis",
            (-12, -2),
            "dB",
        ),
        (
            axes[1, 2],
            features.valid_mask[::stride, ::stride].astype(float),
            "6. Frequency A Valid Observation Mask (10 m)",
            "Blues_r",
            (0, 1),
            "Binary Mask",
        ),
    ]

    for ax, data, title, cmap, (vmin, vmax), unit in panels:
        ax.set_facecolor("#111827")
        im = ax.imshow(
            data, extent=extent, cmap=cmap, vmin=vmin, vmax=vmax, origin="upper"
        )
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
        "NISAR L2 GCOV Frequency A Polarimetric Feature Extraction (10 m Native Grid)\n"
        f"Similipal Tiger Reserve, India | Track {meta.track}, Frame {meta.frame} ({meta.orbit_pass}) | Δt = 48 Days | 40 MHz Bandwidth",
        color="white",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    fig.savefig(out_png, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Saved diagnostic figure to: {out_png}")


def main():
    print("=" * 70)
    print("NISAR FREQUENCY A (10 m) WINDOWED PROCESSING & FEATURE EXTRACTION")
    print("=" * 70)

    tracemalloc.start()
    t_start = time.perf_counter()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading Frequency A window over Similipal:")
    print(f"  X: [{SIMILIPAL_X_MIN}, {SIMILIPAL_X_MAX}]")
    print(f"  Y: [{SIMILIPAL_Y_MIN}, {SIMILIPAL_Y_MAX}]")

    window = load_frequency_a_window(
        t0_path=T0_PATH,
        t1_path=T1_PATH,
        x_min=SIMILIPAL_X_MIN,
        x_max=SIMILIPAL_X_MAX,
        y_min=SIMILIPAL_Y_MIN,
        y_max=SIMILIPAL_Y_MAX,
    )
    meta = window.metadata

    print(f"  Extracted window shape: {meta.window_shape}")
    print(f"  Pixel spacing: {meta.pixel_spacing_x} m x {meta.pixel_spacing_y} m")
    print(f"  CRS: {meta.crs}")
    print(f"  Total window pixels: {window.valid_mask.size:,}")

    valid_count = int(np.sum(window.valid_mask))
    invalid_count = int(window.valid_mask.size - valid_count)
    valid_pct = (valid_count / window.valid_mask.size) * 100.0
    print(f"  Valid pixels: {valid_count:,} ({valid_pct:.2f}%)")
    print(f"  Invalid pixels: {invalid_count:,} ({100 - valid_pct:.2f}%)")

    print("\nExtracting physical polarimetric features...")
    features = extract_polarimetric_features(window)

    # Write GeoTIFF rasters
    print("\nWriting georeferenced GeoTIFF rasters to", OUT_DIR)
    write_geotiff(
        OUT_DIR / "delta_gamma0_hh_db.tif",
        features.delta_gamma0_hh_db,
        meta.transform,
        meta.crs,
        nodata=np.nan,
    )
    write_geotiff(
        OUT_DIR / "delta_gamma0_hv_db.tif",
        features.delta_gamma0_hv_db,
        meta.transform,
        meta.crs,
        nodata=np.nan,
    )
    write_geotiff(
        OUT_DIR / "ratio_hv_hh_t0_db.tif",
        features.ratio_hv_hh_t0_db,
        meta.transform,
        meta.crs,
        nodata=np.nan,
    )
    write_geotiff(
        OUT_DIR / "ratio_hv_hh_t1_db.tif",
        features.ratio_hv_hh_t1_db,
        meta.transform,
        meta.crs,
        nodata=np.nan,
    )
    write_geotiff(
        OUT_DIR / "delta_ratio_hv_hh_db.tif",
        features.delta_ratio_hv_hh_db,
        meta.transform,
        meta.crs,
        nodata=np.nan,
    )
    write_geotiff(
        OUT_DIR / "valid_mask.tif",
        features.valid_mask.astype(np.uint8),
        meta.transform,
        meta.crs,
        nodata=0,
        dtype="uint8",
    )

    out_png = OUT_DIR / "frequency_a_polarimetric_features.png"
    generate_diagnostic_plot(features, meta, out_png)

    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    duration = time.perf_counter() - t_start

    print(f"\nProcessing Performance:")
    print(f"  Duration: {duration:.2f} seconds")
    print(f"  Peak RAM: {peak_mem / (1024**2):.2f} MB ({peak_mem / (1024**3):.3f} GB)")

    # Comprehensive metadata record
    metadata_record = {
        "dataset_info": {
            "mission": "NISAR",
            "product_level": "L2 GCOV (Geocoded Polarimetric Covariance)",
            "frequency_band": "Frequency A (L-band Primary Science Channel)",
            "center_frequency_hz": meta.center_frequency_hz,
            "acquired_range_bandwidth_hz": meta.range_bandwidth_hz,
            "native_slant_range_resolution_m": 3.75,
            "native_azimuth_resolution_m": 5.36,
            "geocoded_pixel_spacing_m": meta.pixel_spacing_x,
            "crs": meta.crs,
            "track": meta.track,
            "frame": meta.frame,
            "orbit_pass": meta.orbit_pass,
            "t0_scene_id": meta.t0_scene_id,
            "t1_scene_id": meta.t1_scene_id,
            "t0_acquisition_time": meta.t0_acquisition_time,
            "t1_acquisition_time": meta.t1_acquisition_time,
            "temporal_baseline_days": 48,
            "software_crid_t0": meta.processing_crid_t0,
            "software_crid_t1": meta.processing_crid_t1,
        },
        "spatial_extent": {
            "x_min": meta.x_min,
            "x_max": meta.x_max,
            "y_min": meta.y_min,
            "y_max": meta.y_max,
            "height_pixels": meta.window_shape[0],
            "width_pixels": meta.window_shape[1],
            "total_pixels": int(window.valid_mask.size),
            "valid_pixels": valid_count,
            "invalid_pixels": invalid_count,
            "valid_percent": round(valid_pct, 2),
            "observed_ground_area_km2": round(valid_count * (meta.pixel_spacing_x**2) / 1e6, 2),
        },
        "performance": {
            "runtime_seconds": round(duration, 2),
            "peak_memory_mb": round(peak_mem / (1024**2), 2),
            "peak_memory_gb": round(peak_mem / (1024**3), 3),
        },
        "rtc_normalization_stats": meta.rtc_factor_stats,
        "feature_statistics": features.statistics,
        "scientific_disclaimer": (
            "These extracted polarimetric layers represent calibrated physical radar backscatter "
            "differences and ratios in terrain-flattened gamma-naught RTC space. They DO NOT "
            "constitute a validated forest disturbance or wildfire classification. Classification "
            "requires independent optical cross-validation (Sentinel-2 dNBR/NDVI) and multi-feature "
            "statistical modeling."
        ),
    }

    meta_json = OUT_DIR / "frequency_a_features_metadata.json"
    meta_json.write_text(json.dumps(metadata_record, indent=2))
    print(f"Saved metadata JSON to: {meta_json}")
    print("\nFeature Extraction Complete.")


if __name__ == "__main__":
    main()

