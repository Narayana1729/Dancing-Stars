"""Pipeline orchestrator for independent optical reference dataset generation."""
from __future__ import annotations

import json
from pathlib import Path
import time
import tracemalloc
from typing import Any, Dict, Optional, Tuple
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import rasterio.features
from scipy.ndimage import zoom
from shapely.geometry import shape

from app.domains.forests.processing.optical_analysis.optical_features import (
    OpticalPairFeatures,
    compute_optical_pair_features,
)
from app.domains.forests.processing.optical_analysis.reference_labeler import (
    OpticalReferenceDataset,
    generate_optical_reference_labels,
)
from app.domains.forests.processing.optical_analysis.sentinel2_loader import (
    SIMILIPAL_X_MAX,
    SIMILIPAL_X_MIN,
    SIMILIPAL_Y_MAX,
    SIMILIPAL_Y_MIN,
    Sentinel2Mosaic,
    load_sentinel2_mosaic_date,
)


def write_geotiff(
    out_path: Path,
    array: np.ndarray,
    transform: Any,
    crs: str,
    nodata: Optional[float] = np.nan,
    dtype: str = "float32",
) -> None:
    """Write an array to a compressed, tiled GeoTIFF raster."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
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


def downsample_to_80m(
    arr_10m: np.ndarray,
    is_categorical: bool = False,
) -> np.ndarray:
    """Downsample a (6616, 6232) 10 m raster to (827, 779) 80 m raster.

    Uses 8x8 block averaging for continuous data, and sensitive majority voting for labels.
    """
    h_80, w_80 = 827, 779
    blocks = arr_10m.reshape(h_80, 8, w_80, 8)

    if not is_categorical:
        # Use nanmean over the 8x8 block
        return np.nanmean(blocks, axis=(1, 3)).astype(np.float32)
    else:
        # Categorical labels (1: Confirmed, 2: Stable, 3: Uncertain, 4: Not observable)
        # Reshape to (h_80, w_80, 64)
        flat_blocks = blocks.transpose(0, 2, 1, 3).reshape(h_80, w_80, 64)
        out = np.full((h_80, w_80), 4, dtype=np.uint8)

        # Count occurrences in each block
        c1 = np.sum(flat_blocks == 1, axis=-1)
        c2 = np.sum(flat_blocks == 2, axis=-1)
        c3 = np.sum(flat_blocks == 3, axis=-1)
        c4 = np.sum(flat_blocks == 4, axis=-1)

        # Sensitive disturbance assignment: if >= 10% of block is confirmed disturbance, label as 1
        has_c1 = c1 >= 6
        out[has_c1] = 1

        # Otherwise assign dominant category among observable
        has_c2 = (c2 >= c3) & (c2 >= c4) & ~has_c1
        has_c3 = (c3 > c2) & (c3 >= c4) & ~has_c1
        has_c4 = (c4 > c1) & (c4 > c2) & (c4 > c3) & ~has_c1

        out[has_c2] = 2
        out[has_c3] = 3
        out[has_c4] = 4
        return out


class OpticalReferencePipeline:
    """Orchestrator for processing Sentinel-2 optical reference datasets."""

    def __init__(
        self,
        raw_dir: Path,
        output_dir: Path,
        reference_dir: Path,
        boundaries_dir: Path,
    ) -> None:
        self.raw_dir = raw_dir
        self.output_dir = output_dir
        self.reference_dir = reference_dir
        self.boundaries_dir = boundaries_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> Dict[str, Any]:
        """Execute the end-to-end optical reference generation pipeline."""
        tracemalloc.start()
        t_start = time.perf_counter()

        print("\n=======================================================")
        print("OPTICAL REFERENCE GENERATION (SENTINEL-2 L2A)")
        print("=======================================================")

        # 1. Load Pre-Event Mosaic (2026-03-02) and Post-Event Mosaic (2026-04-16)
        print("Loading Pre-Event Mosaic (2026-03-02)...")
        pre_mosaic = load_sentinel2_mosaic_date(self.raw_dir, "2026-03-02")
        print("Loading Post-Event Mosaic (2026-04-16)...")
        post_mosaic = load_sentinel2_mosaic_date(self.raw_dir, "2026-04-16")

        # 2. Compute Optical Features and Differentials
        print("Computing multi-spectral indices (NDVI, NDMI, NBR, dNBR)...")
        features = compute_optical_pair_features(pre_mosaic, post_mosaic)

        # 3. Load and Upsample Reference Forest Canopy Cover Mask
        forest_cover_path = self.reference_dir / "similipal_reference_forest_cover.tif"
        print(f"Loading reference forest cover mask from {forest_cover_path.name}...")
        with rasterio.open(forest_cover_path) as src_fc:
            fc_80m = src_fc.read(1)
            forest_mask_80m = fc_80m >= 30  # FSI / FAO 30% forest canopy threshold

        # Upsample 80 m forest mask to 10 m (factor of 8)
        forest_mask_10m = zoom(forest_mask_80m.astype(np.uint8), (8, 8), order=0).astype(bool)
        # Ensure exact shape matching (6616, 6232)
        forest_mask_10m = forest_mask_10m[:features.ndvi_pre.shape[0], :features.ndvi_pre.shape[1]]

        # 4. Load and Rasterize Management Boundaries to 10 m
        sanctuary_geojson = self.boundaries_dir / "similipal_sanctuary_epsg32645.geojson"
        core_geojson = self.boundaries_dir / "similipal_core_epsg32645.geojson"

        sanctuary_mask_10m = np.zeros(features.ndvi_pre.shape, dtype=bool)
        core_mask_10m = np.zeros(features.ndvi_pre.shape, dtype=bool)

        if sanctuary_geojson.exists():
            with open(sanctuary_geojson) as f:
                s_data = json.load(f)
            geoms_s = [shape(feat["geometry"]) for feat in s_data["features"]]
            sanctuary_raster = rasterio.features.rasterize(
                [(g, 1) for g in geoms_s],
                out_shape=features.ndvi_pre.shape,
                transform=pre_mosaic.transform,
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
                out_shape=features.ndvi_pre.shape,
                transform=pre_mosaic.transform,
                fill=0,
                dtype=np.uint8,
            )
            core_mask_10m = core_raster == 1

        # 5. Generate Independent Reference Labels
        print("Generating independent optical reference labels...")
        ref_dataset = generate_optical_reference_labels(
            features=features,
            pre_mosaic=pre_mosaic,
            post_mosaic=post_mosaic,
            forest_cover_mask=forest_mask_10m,
            sanctuary_mask=sanctuary_mask_10m,
            core_mask=core_mask_10m,
        )

        # 6. Export 10 m GeoTIFF Rasters
        print("Exporting 10 m georeferenced GeoTIFF rasters...")
        t_10m = pre_mosaic.transform
        crs = pre_mosaic.crs

        rasters_10m = {
            "s2_ndvi_pre_10m.tif": (features.ndvi_pre, np.nan, "float32"),
            "s2_ndvi_post_10m.tif": (features.ndvi_post, np.nan, "float32"),
            "s2_delta_ndvi_10m.tif": (features.delta_ndvi, np.nan, "float32"),
            "s2_ndmi_pre_10m.tif": (features.ndmi_pre, np.nan, "float32"),
            "s2_ndmi_post_10m.tif": (features.ndmi_post, np.nan, "float32"),
            "s2_delta_ndmi_10m.tif": (features.delta_ndmi, np.nan, "float32"),
            "s2_nbr_pre_10m.tif": (features.nbr_pre, np.nan, "float32"),
            "s2_nbr_post_10m.tif": (features.nbr_post, np.nan, "float32"),
            "s2_dnbr_10m.tif": (features.dnbr, np.nan, "float32"),
            "s2_valid_observation_count_10m.tif": (features.valid_count_map, 0, "uint8"),
            "s2_optical_reference_labels_10m.tif": (ref_dataset.reference_labels, 0, "uint8"),
            "s2_detailed_subtypes_10m.tif": (ref_dataset.detailed_subtypes, 0, "uint8"),
        }

        for filename, (arr, nodata, dtype) in rasters_10m.items():
            write_geotiff(self.output_dir / filename, arr, t_10m, crs, nodata=nodata, dtype=dtype)

        # 7. Generate and Export 80 m Downsampled Products (for Frequency B compatibility)
        print("Generating 80 m downsampled products for NISAR Frequency B alignment...")
        t_80m = rasterio.transform.from_origin(SIMILIPAL_X_MIN, SIMILIPAL_Y_MAX, 80.0, 80.0)

        labels_80m = downsample_to_80m(ref_dataset.reference_labels, is_categorical=True)
        delta_ndvi_80m = downsample_to_80m(features.delta_ndvi, is_categorical=False)
        dnbr_80m = downsample_to_80m(features.dnbr, is_categorical=False)
        valid_count_80m = downsample_to_80m(features.valid_count_map.astype(np.float32), is_categorical=False)

        write_geotiff(self.output_dir / "s2_optical_reference_labels_80m.tif", labels_80m, t_80m, crs, nodata=0, dtype="uint8")
        write_geotiff(self.output_dir / "s2_delta_ndvi_80m.tif", delta_ndvi_80m, t_80m, crs, nodata=np.nan, dtype="float32")
        write_geotiff(self.output_dir / "s2_dnbr_80m.tif", dnbr_80m, t_80m, crs, nodata=np.nan, dtype="float32")
        write_geotiff(self.output_dir / "s2_valid_observation_count_80m.tif", valid_count_80m, t_80m, crs, nodata=np.nan, dtype="float32")

        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        duration = time.perf_counter() - t_start

        perf = {
            "duration_seconds": round(duration, 2),
            "peak_memory_mb": round(peak_mem / (1024**2), 2),
            "peak_memory_gb": round(peak_mem / (1024**3), 3),
        }

        print(f"Optical Reference Generation complete in {perf['duration_seconds']}s | Peak RAM: {perf['peak_memory_mb']} MB")

        return {
            "pre_mosaic": pre_mosaic,
            "post_mosaic": post_mosaic,
            "features": features,
            "reference_dataset": ref_dataset,
            "performance": perf,
            "masks": {
                "sanctuary_pixels_10m": int(np.sum(sanctuary_mask_10m)),
                "core_pixels_10m": int(np.sum(core_mask_10m)),
                "forest_cover_pixels_10m": int(np.sum(forest_mask_10m)),
            },
        }

