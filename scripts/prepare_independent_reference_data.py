#!/usr/bin/env python3
"""Fetch and reproject authentic independent reference datasets for Similipal Tiger Reserve.

Datasets:
1. Hansen Global Forest Change (GFC) Tree Canopy Cover (treecover2000)
2. Hansen Global Forest Change Forest Loss Year (lossyear)
Source: University of Maryland / Google Earth Engine (Hansen et al., Science 2013)
Target CRS: EPSG:32645 (WGS 84 / UTM Zone 45N)
Grid: Perfectly aligned with NISAR GCOV Frequency B (80 m spacing)
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/reference"
OUT_DIR.mkdir(parents=True, exist_ok=True)

GFC_TC_URL = "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2023-v1.11/Hansen_GFC-2023-v1.11_treecover2000_30N_080E.tif"
GFC_LOSS_URL = "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2023-v1.11/Hansen_GFC-2023-v1.11_lossyear_30N_080E.tif"

# Exact Similipal BBox in EPSG:4326
BBOX_4326 = [86.05, 21.45, 86.65, 22.05]

# Target grid parameters derived from NISAR GCOV Frequency B
# Top-left corner: X=401640.0, Y=2438360.0
# Spacing: dx=80.0, dy=-80.0
# Shape: (827, 779)
TARGET_CRS = "EPSG:32645"
X_ORIGIN = 401640.0
Y_ORIGIN = 2438360.0
RES_M = 80.0
HEIGHT = 827
WIDTH = 779
TARGET_TRANSFORM = from_origin(X_ORIGIN, Y_ORIGIN, RES_M, RES_M)


def fetch_and_reproject(cog_url: str, out_tif: Path, resampling: Resampling) -> np.ndarray:
    print(f"Reading source window from {cog_url}...")
    with rasterio.open(cog_url) as src:
        win = from_bounds(BBOX_4326[0] - 0.05, BBOX_4326[1] - 0.05, BBOX_4326[2] + 0.05, BBOX_4326[3] + 0.05, src.transform)
        src_data = src.read(1, window=win)
        src_transform = src.window_transform(win)
        src_crs = src.crs

    print(f"  Source window shape: {src_data.shape}, dtype: {src_data.dtype}")
    print(f"  Reprojecting to {TARGET_CRS} at {RES_M}m resolution (shape: {HEIGHT}x{WIDTH})...")

    dest_data = np.zeros((HEIGHT, WIDTH), dtype=src_data.dtype)
    reproject(
        source=src_data,
        destination=dest_data,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=TARGET_TRANSFORM,
        dst_crs=TARGET_CRS,
        resampling=resampling,
    )

    out_meta = {
        "driver": "GTiff",
        "height": HEIGHT,
        "width": WIDTH,
        "count": 1,
        "dtype": dest_data.dtype,
        "crs": TARGET_CRS,
        "transform": TARGET_TRANSFORM,
        "nodata": 0 if "loss" in out_tif.name else 255,
        "compress": "deflate",
    }

    with rasterio.open(out_tif, "w", **out_meta) as dst:
        dst.write(dest_data, 1)

    print(f"  Saved to: {out_tif}")
    return dest_data


def main():
    tc_tif = OUT_DIR / "similipal_reference_forest_cover.tif"
    loss_tif = OUT_DIR / "similipal_reference_gfc_loss.tif"
    meta_json = OUT_DIR / "similipal_reference_metadata.json"

    tc_array = fetch_and_reproject(GFC_TC_URL, tc_tif, Resampling.bilinear)
    loss_array = fetch_and_reproject(GFC_LOSS_URL, loss_tif, Resampling.nearest)

    # Calculate statistics on the target grid
    total_pixels = HEIGHT * WIDTH
    forest_mask = tc_array >= 30  # Standard FSI/FAO 30% canopy cover threshold
    forest_pixels = int(np.sum(forest_mask))
    non_forest_pixels = total_pixels - forest_pixels
    forest_area_km2 = (forest_pixels * (RES_M * RES_M)) / 1e6
    total_area_km2 = (total_pixels * (RES_M * RES_M)) / 1e6

    loss_pixels = int(np.sum(loss_array > 0))
    loss_area_km2 = (loss_pixels * (RES_M * RES_M)) / 1e6

    metadata = {
        "dataset_name": "Similipal Forest Reference & Disturbance Benchmark",
        "region": "Similipal Tiger Reserve, Odisha, India",
        "geographic_bounds_wgs84": {
            "west": BBOX_4326[0],
            "south": BBOX_4326[1],
            "east": BBOX_4326[2],
            "north": BBOX_4326[3],
        },
        "projected_bounds_utm45n": {
            "crs": TARGET_CRS,
            "x_origin": X_ORIGIN,
            "y_origin": Y_ORIGIN,
            "pixel_size_m": RES_M,
            "height_pixels": HEIGHT,
            "width_pixels": WIDTH,
            "total_area_km2": round(total_area_km2, 2),
        },
        "forest_cover_benchmark": {
            "source": "Hansen Global Forest Change v1.11 (treecover2000)",
            "citation": "Hansen, M. C., et al. (2013). High-Resolution Global Maps of 21st-Century Forest Cover Change. Science, 342(6160), 850-853.",
            "forest_canopy_threshold_percent": 30,
            "forest_pixels": forest_pixels,
            "forest_percent": round(forest_pixels / total_pixels * 100, 2),
            "forest_area_km2": round(forest_area_km2, 2),
            "non_forest_pixels": non_forest_pixels,
            "non_forest_percent": round(non_forest_pixels / total_pixels * 100, 2),
        },
        "historical_disturbance_benchmark": {
            "source": "Hansen Global Forest Change v1.11 (lossyear 2001-2023)",
            "historical_loss_pixels": loss_pixels,
            "historical_loss_percent": round(loss_pixels / total_pixels * 100, 2),
            "historical_loss_area_km2": round(loss_area_km2, 2),
        },
        "national_reference_alignment": {
            "organization": "Forest Survey of India (FSI)",
            "publication": "India State of Forest Report (ISFR)",
            "mayurbhanj_district_forest_cover_fsi_percent": 38.3,
            "similipal_core_and_buffer_area_km2": 2750.0,
        },
    }

    meta_json.write_text(json.dumps(metadata, indent=2))
    print(f"\nMetadata saved to: {meta_json}")
    print("\nSummary Validation:")
    print(f"  Total AOI Area: {total_area_km2:.1f} km² ({total_pixels:,} pixels)")
    print(f"  Reference Forest Cover (>=30% canopy): {forest_area_km2:.1f} km² ({metadata['forest_cover_benchmark']['forest_percent']}%)")
    print(f"  Historical Disturbance (2001-2023): {loss_area_km2:.1f} km² ({metadata['historical_disturbance_benchmark']['historical_loss_percent']}%)")


if __name__ == "__main__":
    main()

