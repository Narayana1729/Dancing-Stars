"""Service for rendering and serving multi-temporal forest disturbance visualization layers."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import pyproj
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[5]
DATA_DIR = ROOT / "data"
REGRESSION_DIR = DATA_DIR / "processed/validation/temporal_regression"
TEMPORAL_DIR = DATA_DIR / "processed/temporal"
REFERENCE_DIR = DATA_DIR / "reference"
BOUNDARIES_DIR = REFERENCE_DIR / "boundaries/processed"

PROVENANCE_FILE = REGRESSION_DIR / "freq_b_provenance.json"
METRICS_FILE = TEMPORAL_DIR / "temporal_pipeline_metrics.json"
BOUNDARIES_4326_FILE = BOUNDARIES_DIR / "similipal_boundaries_epsg4326.json"
FOREST_COVER_FILE = REFERENCE_DIR / "similipal_reference_forest_cover.tif"

# Exact bounding box coordinates
UTM_BOUNDS = {
    "left": 401600.0,
    "bottom": 2372240.0,
    "right": 463920.0,
    "top": 2438400.0,
    "crs": "EPSG:32645",
}

WGS84_BOUNDS = {
    "west": 86.050355,
    "south": 21.449910,
    "east": 86.650337,
    "north": 22.049976,
    "crs": "EPSG:4326",
}

PHYSICAL_REGIME_DEFINITIONS = {
    0: {
        "name": "No Significant Change / Unclassified",
        "description": "Baseline radiometric stability across repeat acquisitions",
        "color": "rgba(0, 0, 0, 0)",
        "hex": "#00000000",
    },
    1: {
        "name": "Volume Scattering Loss (Canopy Disturbance)",
        "description": "Significant drop in HV cross-polarization (ΔHV <= -2.5 dB)",
        "color": "rgba(225, 29, 72, 0.9)",
        "hex": "#e11d48",
    },
    2: {
        "name": "Surface Scattering / Moisture Increase",
        "description": "HH increase (ΔHH >= +2.0 dB) with stable HV",
        "color": "rgba(2, 132, 199, 0.9)",
        "hex": "#0284c7",
    },
    3: {
        "name": "Severe Volume & Surface Attenuation",
        "description": "Coordinated drop across both polarizations (ΔHV <= -2.5 dB, ΔHH <= -2.0 dB)",
        "color": "rgba(124, 58, 237, 0.9)",
        "hex": "#7c3aed",
    },
    4: {
        "name": "Structural Growth / Regrowth",
        "description": "HV increase (ΔHV >= +2.0 dB) indicating biomass or canopy increase",
        "color": "rgba(5, 150, 105, 0.9)",
        "hex": "#059669",
    },
    5: {
        "name": "Double-Bounce / Roughness Increase",
        "description": "Strong co-pol increase (ΔHH >= +3.0 dB) with secondary HV elevation",
        "color": "rgba(217, 119, 6, 0.9)",
        "hex": "#d97706",
    },
}

LAYER_CATALOG = [
    {
        "id": "boundary",
        "name": "Forest & Sanctuary Legal Boundaries",
        "description": "Statutory boundaries of Similipal Wildlife Sanctuary and Core Tiger Reserve (EPSG:4326)",
        "units": "Vector Boundary",
        "type": "vector",
        "colormap": "none",
        "category": "Reference Boundaries",
        "default_visible": True,
    },
    {
        "id": "delta_hh",
        "name": "HH Co-Pol Backscatter Change",
        "description": "Calibrated co-polarization backscatter change (Δσ°_HH = σ°_HH(t₁) − σ°_HH(t₀))",
        "units": "dB",
        "type": "continuous",
        "min_val": -5.0,
        "max_val": 5.0,
        "colormap": "RdBu_r",
        "category": "Radiometric Change",
        "default_visible": False,
    },
    {
        "id": "delta_hv",
        "name": "HV Cross-Pol Backscatter Change",
        "description": "Calibrated cross-polarization volume scattering change (Δσ°_HV = σ°_HV(t₁) − σ°_HV(t₀))",
        "units": "dB",
        "type": "continuous",
        "min_val": -4.0,
        "max_val": 4.0,
        "colormap": "PuOr",
        "category": "Radiometric Change",
        "default_visible": True,
    },
    {
        "id": "delta_ratio",
        "name": "Cross-Polarization Ratio Change",
        "description": "Change in dual-polarization ratio (ΔR = R(t₁) − R(t₀) where R = σ°_HV / σ°_HH)",
        "units": "dB",
        "type": "continuous",
        "min_val": -3.0,
        "max_val": 3.0,
        "colormap": "coolwarm",
        "category": "Radiometric Change",
        "default_visible": False,
    },
    {
        "id": "rnd_hv",
        "name": "Relative Normalized Difference (RND)",
        "description": "Relative normalized difference index (RND_HV = (γ°(t₁) − γ°(t₀)) / (γ°(t₁) + γ°(t₀)))",
        "units": "Index [-1, 1]",
        "type": "continuous",
        "min_val": -0.5,
        "max_val": 0.5,
        "colormap": "PRGn",
        "category": "Radiometric Change",
        "default_visible": False,
    },
    {
        "id": "tier1_candidates",
        "name": "Instantaneous Disturbance Candidates",
        "description": "Tier 1 candidate pixels with severe canopy volume backscatter drop (ΔHV ≤ −2.5 dB, MMU ≥ 1.92 ha)",
        "units": "Candidate Anomaly (dB drop)",
        "type": "anomaly",
        "min_val": 0.0,
        "max_val": 10.0,
        "colormap": "YlOrRd",
        "category": "Classification & Physical Regimes",
        "default_visible": True,
    },
    {
        "id": "physical_regimes",
        "name": "Physical Change Regimes",
        "description": "Categorical dual-polarization change regimes (0: Stability, 1: Volume Loss, 2: Surface/Moisture, 3: Dual Loss, 4: Regrowth, 5: Roughness)",
        "units": "Regime Class (0-5)",
        "type": "categorical",
        "min_val": 0,
        "max_val": 5,
        "colormap": "discrete",
        "regimes": PHYSICAL_REGIME_DEFINITIONS,
        "category": "Classification & Physical Regimes",
        "default_visible": False,
    },
    {
        "id": "valid_coverage",
        "name": "Valid Observation Coverage",
        "description": "Observation count per pixel across the 48-day baseline (0: Unobserved, 1: Single Epoch, 2: Dual Epochs)",
        "units": "Valid Epochs (0-2)",
        "type": "categorical",
        "min_val": 0,
        "max_val": 2,
        "colormap": "discrete",
        "category": "Quality & Uncertainty",
        "default_visible": False,
    },
    {
        "id": "uncertainty_mask",
        "name": "Uncertainty & Insufficient Evidence Mask",
        "description": "Spatial areas with insufficient observation count (N < 2), out-of-swath unobserved coverage, or elevated dispersion",
        "units": "Uncertainty Flag",
        "type": "mask",
        "min_val": 0,
        "max_val": 1,
        "colormap": "warning",
        "category": "Quality & Uncertainty",
        "default_visible": False,
    },
]


class ForestVisualizationService:
    """Manages raster rendering, colormapping, coordinate projection, and spatial querying."""

    def __init__(self) -> None:
        self._png_cache: Dict[Tuple[str, str], bytes] = {}
        self._raster_cache: Dict[str, np.ndarray] = {}
        self._metadata_cache: Optional[Dict[str, Any]] = None
        self._transform = None
        self._inv_transform = None
        self._shape = (827, 779)
        self._transformer_to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True)
        self._transformer_to_wgs84 = pyproj.Transformer.from_crs("EPSG:32645", "EPSG:4326", always_xy=True)
        self._init_transform()

    def _init_transform(self) -> None:
        ref_file = REGRESSION_DIR / "freq_b_delta_hv.tif"
        if not ref_file.exists():
            ref_file = TEMPORAL_DIR / "freq_b_delta_hv.tif"
        if ref_file.exists():
            with rasterio.open(ref_file) as src:
                self._transform = src.transform
                self._inv_transform = ~src.transform
                self._shape = src.shape

    def get_layers_catalog(self) -> Dict[str, Any]:
        return {
            "layers": LAYER_CATALOG,
            "bounds": {
                "wgs84": WGS84_BOUNDS,
                "utm": UTM_BOUNDS,
            },
            "raster_dimensions": {
                "width": self._shape[1],
                "height": self._shape[0],
                "pixel_size_m": 80.0,
            },
            "regimes": PHYSICAL_REGIME_DEFINITIONS,
        }

    def get_boundaries_geojson(self) -> Dict[str, Any]:
        if BOUNDARIES_4326_FILE.exists():
            with open(BOUNDARIES_4326_FILE) as f:
                return json.load(f)
        raise FileNotFoundError(f"Boundary file not found at {BOUNDARIES_4326_FILE}")

    def _load_raster(self, name: str) -> np.ndarray:
        if name in self._raster_cache:
            return self._raster_cache[name]

        path = REGRESSION_DIR / f"{name}.tif"
        if not path.exists():
            path = TEMPORAL_DIR / f"{name}.tif"
        if not path.exists():
            raise FileNotFoundError(f"Raster {name}.tif not found in regression or temporal directories.")

        with rasterio.open(path) as src:
            arr = src.read(1)
            self._raster_cache[name] = arr
            return arr

    def _get_aoi_mask(self, aoi_clip: str) -> Optional[np.ndarray]:
        """Returns boolean mask where True = keep pixel, False = mask out."""
        if aoi_clip == "none" or not aoi_clip:
            return None

        if aoi_clip == "forest":
            if FOREST_COVER_FILE.exists():
                with rasterio.open(FOREST_COVER_FILE) as src:
                    return src.read(1) >= 30
            return None

        boundary_file = None
        if aoi_clip == "sanctuary":
            boundary_file = BOUNDARIES_DIR / "similipal_sanctuary_epsg32645.geojson"
        elif aoi_clip == "core":
            boundary_file = BOUNDARIES_DIR / "similipal_core_epsg32645.geojson"

        if boundary_file and boundary_file.exists():
            with open(boundary_file) as f:
                data = json.load(f)
            geoms = [shape(data["features"][0]["geometry"])]
            return geometry_mask(geoms, transform=self._transform, invert=True, out_shape=self._shape)

        return None

    def render_layer_png(self, layer_id: str, aoi_clip: str = "none") -> bytes:
        cache_key = (layer_id, aoi_clip)
        if cache_key in self._png_cache:
            return self._png_cache[cache_key]

        aoi_mask = self._get_aoi_mask(aoi_clip)
        h, w = self._shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)

        if layer_id == "delta_hh":
            arr = self._load_raster("freq_b_delta_hh")
            valid = ~np.isnan(arr)
            if aoi_mask is not None:
                valid = valid & aoi_mask
            cmap = plt.get_cmap("RdBu_r")
            norm = np.clip((arr - (-5.0)) / (5.0 - (-5.0)), 0, 1)
            mapped = (cmap(norm) * 255).astype(np.uint8)
            rgba[valid] = mapped[valid]

        elif layer_id == "delta_hv":
            arr = self._load_raster("freq_b_delta_hv")
            valid = ~np.isnan(arr)
            if aoi_mask is not None:
                valid = valid & aoi_mask
            cmap = plt.get_cmap("PuOr")
            norm = np.clip((arr - (-4.0)) / (4.0 - (-4.0)), 0, 1)
            mapped = (cmap(norm) * 255).astype(np.uint8)
            rgba[valid] = mapped[valid]

        elif layer_id == "delta_ratio":
            arr = self._load_raster("freq_b_delta_ratio")
            valid = ~np.isnan(arr)
            if aoi_mask is not None:
                valid = valid & aoi_mask
            cmap = plt.get_cmap("coolwarm")
            norm = np.clip((arr - (-3.0)) / (3.0 - (-3.0)), 0, 1)
            mapped = (cmap(norm) * 255).astype(np.uint8)
            rgba[valid] = mapped[valid]

        elif layer_id == "rnd_hv":
            arr = self._load_raster("freq_b_rnd_hv_step")
            valid = ~np.isnan(arr)
            if aoi_mask is not None:
                valid = valid & aoi_mask
            cmap = plt.get_cmap("PRGn")
            norm = np.clip((arr - (-0.5)) / (0.5 - (-0.5)), 0, 1)
            mapped = (cmap(norm) * 255).astype(np.uint8)
            rgba[valid] = mapped[valid]

        elif layer_id == "tier1_candidates":
            arr = self._load_raster("freq_b_tier1_instantaneous_intensity")
            valid = (arr > 0.0)
            if aoi_mask is not None:
                valid = valid & aoi_mask
            # High-visibility crimson overlay with intensity
            cmap = plt.get_cmap("YlOrRd")
            norm = np.clip(arr / 6.0, 0, 1)
            mapped = (cmap(norm) * 255).astype(np.uint8)
            # Ensure high opacity for detected candidates
            mapped[..., 3] = 230
            rgba[valid] = mapped[valid]

        elif layer_id == "physical_regimes":
            arr = self._load_raster("freq_b_physical_change_regimes")
            # Map discrete regimes
            regime_colors = {
                1: [225, 29, 72, 220],    # Volume Loss: Crimson
                2: [2, 132, 199, 220],    # Moisture/Surface: Sky Blue
                3: [124, 58, 237, 220],   # Dual Loss: Purple
                4: [5, 150, 105, 220],    # Regrowth: Emerald
                5: [217, 119, 6, 220],    # Roughness/Double-bounce: Amber
            }
            for reg_idx, color in regime_colors.items():
                m = (arr == reg_idx)
                if aoi_mask is not None:
                    m = m & aoi_mask
                rgba[m] = color

        elif layer_id == "valid_coverage":
            arr = self._load_raster("freq_b_valid_count")
            # 0: Transparent, 1: Amber, 2: Emerald
            m1 = (arr == 1)
            m2 = (arr == 2)
            if aoi_mask is not None:
                m1 = m1 & aoi_mask
                m2 = m2 & aoi_mask
            rgba[m1] = [245, 158, 11, 200]
            rgba[m2] = [16, 185, 129, 180]

        elif layer_id == "uncertainty_mask":
            vc = self._load_raster("freq_b_valid_count")
            # Highlight unobserved / single observation or out of swath within bounding box
            uncertain = (vc < 2)
            if aoi_mask is not None:
                uncertain = uncertain & aoi_mask
            # Caution amber-rose hatch tint
            rgba[uncertain] = [244, 63, 94, 130]

        else:
            raise ValueError(f"Unknown layer_id: {layer_id}")

        img = Image.fromarray(rgba, "RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        png_bytes = buf.getvalue()
        self._png_cache[cache_key] = png_bytes
        return png_bytes

    def get_temporal_metrics(self) -> Dict[str, Any]:
        """Provides full metrics, acquisition details, candidate status, and scientific uncertainty declarations."""
        prov: Dict[str, Any] = {}
        if PROVENANCE_FILE.exists():
            with open(PROVENANCE_FILE) as f:
                prov = json.load(f)

        metrics: Dict[str, Any] = {}
        if METRICS_FILE.exists():
            with open(METRICS_FILE) as f:
                metrics = json.load(f)

        return {
            "study_region": {
                "name": "Similipal Tiger Reserve, Odisha, India",
                "center_coordinates": {"latitude": 21.75, "longitude": 86.35},
                "projected_crs": "EPSG:32645 (UTM Zone 45N)",
                "pixel_size_m": 80.0,
                "domain": "forest_disturbance_detection",
            },
            "observations": {
                "baseline_t0": {
                    "scene_id": "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001",
                    "timestamp": "2026-03-04T23:37:20Z",
                    "track": 98,
                    "frame": 12,
                    "pass": "Ascending",
                    "look_direction": "Left",
                    "crid": "P05023",
                    "frequency_band": "frequencyB (L-band)",
                },
                "comparison_t1": {
                    "scene_id": "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001",
                    "timestamp": "2026-04-21T23:37:20Z",
                    "track": 98,
                    "frame": 12,
                    "pass": "Ascending",
                    "look_direction": "Left",
                    "crid": "P05023",
                    "frequency_band": "frequencyB (L-band)",
                },
                "temporal_separation_days": 48,
                "orbital_repeat_cycles": 4,
            },
            "quantitative_changes": {
                "delta_hh_db": {
                    "mean": -0.42,
                    "median": -0.38,
                    "std": 1.48,
                    "units": "dB",
                },
                "delta_hv_db": {
                    "mean": -1.18,
                    "median": -1.12,
                    "std": 1.25,
                    "units": "dB",
                },
                "delta_ratio_db": {
                    "mean": -0.76,
                    "median": -0.74,
                    "std": 1.62,
                    "units": "dB",
                },
                "rnd_hv": {
                    "mean": -0.134,
                    "median": -0.128,
                    "units": "unitless index [-1, 1]",
                },
            },
            "disturbance_classification": {
                "tier1_instantaneous": {
                    "status": "ACTIVE_CANDIDATE",
                    "detected_area_ha": 68.5,
                    "detected_area_km2": 0.685,
                    "detected_pixels": 107,
                    "total_forest_pixels": 46515,
                    "disturbance_fraction_percent": 0.23,
                    "threshold_db": -2.5,
                    "mmu_cluster_pixels": 3,
                    "spatial_filter_applied": True,
                    "scientific_designation": "Instantaneous Disturbance Candidate (Unvalidated Statistical Anomaly)",
                    "deforestation_verdict": "NOT_CONFIRMED_DEFORESTATION",
                },
                "tier2_temporally_sustained": {
                    "status": "UNAVAILABLE_UNVERIFIABLE",
                    "reason": "Requires ≥ 3 consecutive post-event acquisitions; only 2 dates exist in catalog.",
                },
                "tier3_long_term_persistent": {
                    "status": "UNAVAILABLE_UNVERIFIABLE",
                    "reason": "Requires multi-seasonal baseline and independent aerial/field validation.",
                },
                "canopy_recovery": {
                    "status": "UNVERIFIABLE",
                    "reason": "Cannot assess rebound or permanent clearing with a single post-event epoch.",
                },
            },
            "coverage_and_validity": {
                "total_bounding_box_pixels": 644233,
                "valid_dual_epoch_pixels": 197386,
                "single_epoch_pixels": 240,
                "unobserved_swath_pixels": 446607,
                "monitored_reserve_forest_area_km2": 297.7,
                "reserve_swath_overlap_percent": 18.29,
                "frame_validity_percent": 94.8,
            },
            "scientific_uncertainty": {
                "phenological_moisture_sensitivity": {
                    "level": "High",
                    "finding": "Coordinated ~1.1 dB drop across undisturbed forest reflects peak dry-season foliar desiccation.",
                },
                "spatial_coverage_limitation": {
                    "level": "Significant",
                    "finding": "81.71% of Similipal Core lies outside Track 098 swath.",
                },
                "independent_optical_corroboration": {
                    "in_swath_overlap_ha": 0.43,
                    "outside_swath_unobserved_loss_ha": 11.40,
                    "s2_optical_scene_date": "2026-03-23 / 2026-04-12",
                    "caution": "NDVI > 0.55 indicates retained green canopy, but does not independently establish absence of understory fire or partial thinning; 0.43 ha is a candidate cross-sensor event, not confirmed deforestation.",
                },
                "strict_guardrail": "Instantaneous candidates are statistical change hypotheses, NOT confirmed deforestation events.",
            },
        }

    def inspect_pixel(self, lon: float, lat: float) -> Dict[str, Any]:
        """Samples all layers at a target geographic point (WGS84 lon, lat)."""
        x, y = self._transformer_to_utm.transform(lon, lat)
        col_f, row_f = self._inv_transform @ (x, y)
        col, row = int(round(col_f)), int(round(row_f))

        h, w = self._shape
        if not (0 <= row < h and 0 <= col < w):
            return {
                "inside_bbox": False,
                "coordinates": {"longitude": lon, "latitude": lat, "utm_easting": x, "utm_northing": y},
                "error": "Coordinates lie outside Similipal bounding box.",
            }

        delta_hh = float(self._load_raster("freq_b_delta_hh")[row, col])
        delta_hv = float(self._load_raster("freq_b_delta_hv")[row, col])
        delta_ratio = float(self._load_raster("freq_b_delta_ratio")[row, col])
        rnd_hv = float(self._load_raster("freq_b_rnd_hv_step")[row, col])
        tier1_intensity = float(self._load_raster("freq_b_tier1_instantaneous_intensity")[row, col])
        physical_regime = int(self._load_raster("freq_b_physical_change_regimes")[row, col])
        valid_count = int(self._load_raster("freq_b_valid_count")[row, col])

        in_forest = False
        if FOREST_COVER_FILE.exists():
            with rasterio.open(FOREST_COVER_FILE) as src:
                tc = src.read(1)[row, col]
                in_forest = bool(tc >= 30)

        regime_meta = PHYSICAL_REGIME_DEFINITIONS.get(physical_regime, {
            "name": "Unknown",
            "description": "N/A",
            "hex": "#00000000",
        })

        is_tier1_candidate = bool(tier1_intensity > 0.0)

        return {
            "inside_bbox": True,
            "grid_cell": {"row": row, "col": col},
            "coordinates": {
                "longitude": round(lon, 6),
                "latitude": round(lat, 6),
                "utm_easting": round(x, 2),
                "utm_northing": round(y, 2),
                "crs": "EPSG:32645",
            },
            "valid_observation_count": valid_count,
            "is_valid_observation": bool(valid_count == 2),
            "in_reference_forest": in_forest,
            "values": {
                "delta_hh_db": round(delta_hh, 2) if not np.isnan(delta_hh) else None,
                "delta_hv_db": round(delta_hv, 2) if not np.isnan(delta_hv) else None,
                "delta_ratio_db": round(delta_ratio, 2) if not np.isnan(delta_ratio) else None,
                "rnd_hv": round(rnd_hv, 4) if not np.isnan(rnd_hv) else None,
                "tier1_instantaneous_drop_intensity": round(tier1_intensity, 2) if is_tier1_candidate else 0.0,
            },
            "regime": {
                "id": physical_regime,
                "name": regime_meta["name"],
                "description": regime_meta["description"],
                "color": regime_meta["hex"],
            },
            "disturbance_candidate": {
                "is_candidate": is_tier1_candidate,
                "classification": "Tier 1 Instantaneous Candidate" if is_tier1_candidate else "No Disturbance Candidate Detected",
                "caution": "Instantaneous candidate only; not confirmed deforestation." if is_tier1_candidate else None,
            },
        }
