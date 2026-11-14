"""End-to-end reproducible multi-temporal processing pipeline for NISAR observations."""
from __future__ import annotations

import json
from pathlib import Path
import time
import tracemalloc
from typing import Any, Dict, List, Optional, Tuple
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import rasterio.features
from shapely.geometry import shape

from app.domains.forests.processing.temporal_analysis.metadata import (
    PipelinePerformance,
    ZonalStats,
)
from app.domains.forests.processing.temporal_analysis.temporal_features import (
    MultiTemporalFeatures,
    compute_distribution_stats,
    extract_multitemporal_features,
)
from app.domains.forests.processing.temporal_analysis.temporal_loader import (
    LoadedTemporalSeries,
    SIMILIPAL_X_MAX,
    SIMILIPAL_X_MIN,
    SIMILIPAL_Y_MAX,
    SIMILIPAL_Y_MIN,
    load_multitemporal_series,
)


def write_geotiff(
    out_path: Path,
    array: np.ndarray,
    transform: Any,
    crs: str,
    nodata: Optional[float] = np.nan,
    dtype: str = "float32",
) -> None:
    """Write an array to a compressed, tiled Cloud-Optimized GeoTIFF raster."""
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


def load_boundary_masks(
    sanctuary_geojson_path: Path,
    core_geojson_path: Path,
    out_shape: Tuple[int, int],
    transform: Any,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rasterize authoritative Similipal Tiger Reserve boundaries to the raster grid."""
    sanctuary_mask = np.zeros(out_shape, dtype=bool)
    core_mask = np.zeros(out_shape, dtype=bool)

    if sanctuary_geojson_path.exists():
        with open(sanctuary_geojson_path) as f:
            data = json.load(f)
        geoms = [shape(feat["geometry"]) for feat in data["features"]]
        sanctuary_raster = rasterio.features.rasterize(
            [(g, 1) for g in geoms],
            out_shape=out_shape,
            transform=transform,
            fill=0,
            dtype=np.uint8,
        )
        sanctuary_mask = sanctuary_raster == 1

    if core_geojson_path.exists():
        with open(core_geojson_path) as f:
            data = json.load(f)
        geoms = [shape(feat["geometry"]) for feat in data["features"]]
        core_raster = rasterio.features.rasterize(
            [(g, 1) for g in geoms],
            out_shape=out_shape,
            transform=transform,
            fill=0,
            dtype=np.uint8,
        )
        core_mask = core_raster == 1

    outside_reserve_mask = ~sanctuary_mask
    return sanctuary_mask, core_mask, outside_reserve_mask


class MultiTemporalNISARPipeline:
    """Orchestrator for multi-temporal NISAR L2 GCOV feature extraction and zonal audit."""

    def __init__(
        self,
        output_dir: Path,
        boundaries_dir: Optional[Path] = None,
    ) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if boundaries_dir is not None:
            self.sanctuary_path = boundaries_dir / "similipal_sanctuary_epsg32645.geojson"
            self.core_path = boundaries_dir / "similipal_core_epsg32645.geojson"
        else:
            self.sanctuary_path = Path("data/reference/boundaries/processed/similipal_sanctuary_epsg32645.geojson")
            self.core_path = Path("data/reference/boundaries/processed/similipal_core_epsg32645.geojson")

    def run_frequency_pipeline(
        self,
        file_paths: List[Path],
        frequency_key: str = "frequencyB",
        x_min: float = SIMILIPAL_X_MIN,
        x_max: float = SIMILIPAL_X_MAX,
        y_min: float = SIMILIPAL_Y_MIN,
        y_max: float = SIMILIPAL_Y_MAX,
        export_rasters: bool = True,
    ) -> Dict[str, Any]:
        """Execute full multi-temporal analysis for a specific radar frequency.

        Measures runtime, peak RAM, writes georeferenced rasters, and calculates zonal statistics.
        """
        tracemalloc.start()
        t_start = time.perf_counter()

        freq_prefix = "freq_a" if frequency_key == "frequencyA" else "freq_b"
        print(f"\n--- Running Multi-Temporal Pipeline for {frequency_key} ({freq_prefix}) ---")
        print(f"Number of input acquisitions: {len(file_paths)}")
        for i, p in enumerate(file_paths):
            print(f"  Epoch {i}: {p.name}")

        # 1. Load multi-temporal series with spatial alignment verification
        series: LoadedTemporalSeries = load_multitemporal_series(
            file_paths=file_paths,
            frequency_key=frequency_key,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
        )

        # 2. Extract multi-temporal features
        features: MultiTemporalFeatures = extract_multitemporal_features(series)

        # 3. Load and rasterize authoritative management boundaries
        shape = series.metadata.window_shape
        sanctuary_mask, core_mask, outside_mask = load_boundary_masks(
            self.sanctuary_path,
            self.core_path,
            shape,
            series.metadata.transform,
        )

        # 4. Compute stratified zonal statistics
        zonal_stats: Dict[str, ZonalStats] = {}
        primary_dhv = features.delta_hv_db[0]
        primary_dhh = features.delta_hh_db[0]
        primary_dratio = features.delta_ratio_db[0]
        temporal_std = features.temporal_std_hv_db
        intersection = features.intersection_mask

        metrics_to_stratify = {
            "delta_hv_db": primary_dhv,
            "delta_hh_db": primary_dhh,
            "delta_ratio_hv_hh_db": primary_dratio,
            "temporal_std_hv_db": temporal_std,
            "persistence_indicator": features.persistence_indicator,
        }

        for metric_name, arr in metrics_to_stratify.items():
            zonal_stats[metric_name] = ZonalStats(
                overall=compute_distribution_stats(arr, intersection),
                sanctuary=compute_distribution_stats(arr, intersection & sanctuary_mask),
                core=compute_distribution_stats(arr, intersection & core_mask),
                outside_reserve=compute_distribution_stats(arr, intersection & outside_mask),
            )

        # 5. Calculate physical regime surface areas (hectares and km2)
        pixel_area_m2 = series.metadata.nominal_resolution_m**2
        regime_counts = {}
        for r_code in range(6):
            cnt = int(np.sum(features.physical_change_regimes == r_code))
            area_ha = (cnt * pixel_area_m2) / 10000.0
            area_km2 = (cnt * pixel_area_m2) / 1e6
            regime_counts[f"regime_{r_code}"] = {
                "pixel_count": cnt,
                "area_ha": round(area_ha, 2),
                "area_km2": round(area_km2, 2),
            }

        # 6. Export GeoTIFF rasters
        raster_paths: Dict[str, str] = {}
        if export_rasters:
            t = series.metadata.transform
            crs = series.metadata.crs

            # Temporal backscatter time series
            for k in range(series.metadata.num_epochs):
                p_hh = self.output_dir / f"{freq_prefix}_hh_t{k}.tif"
                write_geotiff(p_hh, features.hh_db[k], t, crs, nodata=np.nan)
                raster_paths[f"hh_t{k}"] = str(p_hh)

                p_hv = self.output_dir / f"{freq_prefix}_hv_t{k}.tif"
                write_geotiff(p_hv, features.hv_db[k], t, crs, nodata=np.nan)
                raster_paths[f"hv_t{k}"] = str(p_hv)

                p_r = self.output_dir / f"{freq_prefix}_ratio_t{k}.tif"
                write_geotiff(p_r, features.ratio_hv_hh_db[k], t, crs, nodata=np.nan)
                raster_paths[f"ratio_t{k}"] = str(p_r)

            # Pairwise temporal changes
            p_dhh = self.output_dir / f"{freq_prefix}_delta_hh.tif"
            write_geotiff(p_dhh, primary_dhh, t, crs, nodata=np.nan)
            raster_paths["delta_hh"] = str(p_dhh)

            p_dhv = self.output_dir / f"{freq_prefix}_delta_hv.tif"
            write_geotiff(p_dhv, primary_dhv, t, crs, nodata=np.nan)
            raster_paths["delta_hv"] = str(p_dhv)

            p_dratio = self.output_dir / f"{freq_prefix}_delta_ratio.tif"
            write_geotiff(p_dratio, primary_dratio, t, crs, nodata=np.nan)
            raster_paths["delta_ratio"] = str(p_dratio)

            # Variability, valid counts, and regimes
            p_tstd = self.output_dir / f"{freq_prefix}_temporal_variability.tif"
            write_geotiff(p_tstd, temporal_std, t, crs, nodata=np.nan)
            raster_paths["temporal_variability"] = str(p_tstd)

            p_vcount = self.output_dir / f"{freq_prefix}_valid_count.tif"
            write_geotiff(p_vcount, features.valid_count_map.astype(np.uint8), t, crs, nodata=0, dtype="uint8")
            raster_paths["valid_count"] = str(p_vcount)

            p_regimes = self.output_dir / f"{freq_prefix}_physical_change_regimes.tif"
            write_geotiff(p_regimes, features.physical_change_regimes, t, crs, nodata=0, dtype="uint8")
            raster_paths["physical_change_regimes"] = str(p_regimes)

        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        duration = time.perf_counter() - t_start

        total_pixels = int(features.intersection_mask.size)
        valid_pixels = int(np.sum(features.intersection_mask))
        valid_pct = (valid_pixels / total_pixels) * 100.0

        perf = PipelinePerformance(
            frequency_id=frequency_key,
            duration_seconds=round(duration, 2),
            peak_ram_mb=round(peak_mem / (1024**2), 2),
            peak_ram_gb=round(peak_mem / (1024**3), 3),
            total_pixels=total_pixels,
            valid_pixels=valid_pixels,
            valid_percentage=round(valid_pct, 2),
        )

        print(f"Completed {frequency_key} in {perf.duration_seconds:.2f}s | Peak RAM: {perf.peak_ram_mb:.1f} MB")

        return {
            "series": series,
            "features": features,
            "performance": perf,
            "zonal_statistics": {k: v.to_dict() for k, v in zonal_stats.items()},
            "regime_areas": regime_counts,
            "raster_paths": raster_paths,
            "boundary_masks": {
                "sanctuary_pixels": int(np.sum(sanctuary_mask)),
                "core_pixels": int(np.sum(core_mask)),
                "outside_pixels": int(np.sum(outside_mask)),
            },
        }

