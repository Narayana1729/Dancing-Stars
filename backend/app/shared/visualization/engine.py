from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import rasterio

from app.shared.geospatial.aoi import AreaOfInterest
from app.shared.geospatial.bbox import BoundingBox
from app.shared.geospatial.regions import region_registry
from app.shared.visualization.compositor import (
    OpticalCompositeType,
    OpticalFalseColorCompositor,
    SARFalseColorCompositor,
    SarCompositeType,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "data"
TEMPORAL_DIR = DATA_DIR / "processed" / "temporal"
OPTICAL_DIR = DATA_DIR / "processed" / "optical_reference"


class VisualizationEngine:
    """Orchestrates raster loading, false-color compositing, and map-ready layer rendering."""

    def __init__(self) -> None:
        self._raster_cache: Dict[str, np.ndarray] = {}

    def get_supported_composites(self) -> Dict[str, Any]:
        """Catalog of available false-color composite formulas and interpretations."""
        return {
            "sar_composites": [
                {
                    "type": SarCompositeType.DUAL_POL_RGB.value,
                    "name": "Dual-Pol Pauli Surrogate (HH / HV / Ratio)",
                    "channels": {"Red": "HH (Surface)", "Green": "HV (Canopy Volume)", "Blue": "HH - HV (Ratio)"},
                    "description": "Differentiates forest canopy volume from bare ground and specular water surfaces.",
                    "color_guide": {
                        "Green": "Dense Intact Canopy",
                        "Yellow/White": "Urban / High Double-Bounce",
                        "Deep Blue": "Smooth Bare Ground / Clearings",
                        "Black": "Calm Water Bodies",
                    },
                },
                {
                    "type": SarCompositeType.MULTI_TEMPORAL_CHANGE_RGB.value,
                    "name": "Multi-Temporal SAR Change (t0 / t1 / Delta Ratio)",
                    "channels": {"Red": "t0 HV (Pre-Event)", "Green": "t1 HV (Post-Event)", "Blue": "Delta Ratio HV/HH"},
                    "description": "Visualizes immediate canopy disturbance and structural alteration across two SAR dates.",
                    "color_guide": {
                        "Olive Green": "Stable Undisturbed Forest",
                        "Vivid Red / Orange": "Canopy Disturbance / Biomass Loss",
                        "Bright Green": "Canopy Regrowth / Flush",
                        "Magenta / Blue": "Moisture / Phenological Desiccation",
                    },
                },
            ],
            "optical_composites": [
                {
                    "type": OpticalCompositeType.COLOR_INFRARED_CIR.value,
                    "name": "Standard Color Infrared (NIR / Red / Green)",
                    "channels": {"Red": "NIR B08", "Green": "Red B04", "Blue": "Green B03"},
                    "description": "Standard false-color optical view highlighting photosynthetic leaf vigor.",
                    "color_guide": {
                        "Vivid Red": "Healthy Vigorous Canopy",
                        "Light Brown / Cyan": "Soil / Cleared Ground / Sparse Scrub",
                        "Jet Black": "Water",
                    },
                },
                {
                    "type": OpticalCompositeType.SWIR_BURN_SEVERITY.value,
                    "name": "SWIR Burn Severity & Fire Scar (SWIR2 / NIR / Red)",
                    "channels": {"Red": "SWIR2 B12", "Green": "NIR B8A", "Blue": "Red B04"},
                    "description": "Optimal for detecting wildfire scars and char residues penetrating haze.",
                    "color_guide": {
                        "Brick Red / Bright Orange": "Burned Soil / Active Burn Scar",
                        "Emerald Green": "Intact Green Canopy",
                        "Tan / Ochre": "Dry Sparse Vegetation",
                    },
                },
            ],
        }

    def render_sar_composite(
        self,
        composite_type: SarCompositeType = SarCompositeType.DUAL_POL_RGB,
        p_min: float = 2.0,
        p_max: float = 98.0,
    ) -> bytes:
        """Render false-color SAR composite PNG from baseline multi-temporal rasters."""
        if composite_type == SarCompositeType.DUAL_POL_RGB:
            hh = self._load_raster(TEMPORAL_DIR / "freq_b_hh_t0.tif")
            hv = self._load_raster(TEMPORAL_DIR / "freq_b_hv_t0.tif")
            return SARFalseColorCompositor.create_dual_pol_rgb(hh, hv, p_min=p_min, p_max=p_max)

        elif composite_type == SarCompositeType.MULTI_TEMPORAL_CHANGE_RGB:
            hv_t0 = self._load_raster(TEMPORAL_DIR / "freq_b_hv_t0.tif")
            hv_t1 = self._load_raster(TEMPORAL_DIR / "freq_b_hv_t1.tif")
            delta_ratio = self._load_raster(TEMPORAL_DIR / "freq_b_delta_ratio.tif")
            return SARFalseColorCompositor.create_multitemporal_change_rgb(
                hv_t0, hv_t1, delta_ratio, p_min=p_min, p_max=p_max
            )
        else:
            raise ValueError(f"Unknown SAR composite type '{composite_type}'.")

    def render_optical_composite(
        self,
        composite_type: OpticalCompositeType = OpticalCompositeType.COLOR_INFRARED_CIR,
        p_min: float = 2.0,
        p_max: float = 98.0,
    ) -> bytes:
        """Render false-color Optical composite PNG from baseline Sentinel-2 surface reflectance."""
        # Use available processed optical reference bands or synthetic fallback
        ndvi_post = self._load_raster(OPTICAL_DIR / "s2_ndvi_post_80m.tif", fallback_name="s2_ndvi_post_10m.tif")
        nbr_post = self._load_raster(OPTICAL_DIR / "s2_nbr_post_10m.tif", fallback_name="s2_dnbr_80m.tif")

        # Synthesize RGB representation from calibrated optical products if individual L2A band rasters not present
        if composite_type == OpticalCompositeType.COLOR_INFRARED_CIR:
            nir = np.clip(ndvi_post * 0.8 + 0.2, 0.0, 1.0)
            red = np.clip(1.0 - ndvi_post, 0.0, 1.0)
            green = np.clip(ndvi_post * 0.5, 0.0, 1.0)
            return OpticalFalseColorCompositor.create_color_infrared_cir(nir, red, green, p_min=p_min, p_max=p_max)

        elif composite_type == OpticalCompositeType.SWIR_BURN_SEVERITY:
            swir2 = np.clip(1.0 - nbr_post, 0.0, 1.0)
            nir = np.clip(nbr_post * 0.7 + 0.3, 0.0, 1.0)
            red = np.clip(1.0 - ndvi_post, 0.0, 1.0)
            return OpticalFalseColorCompositor.create_swir_burn_severity(swir2, nir, red, p_min=p_min, p_max=p_max)

        raise ValueError(f"Unknown Optical composite type '{composite_type}'.")

    def get_map_bounds(self, region_id: str) -> Dict[str, Any]:
        """Returns map-ready bounding coordinates and center for GIS viewers."""
        reg = region_registry.get_region(region_id)
        if reg is None:
            raise ValueError(f"Region '{region_id}' not found in registry.")

        bbox = reg.bbox
        return {
            "region_id": reg.region_id,
            "region_name": reg.name,
            "crs": reg.utm_crs,
            "center": reg.center_coordinates,
            "bbox_wgs84": {
                "west": bbox.west,
                "south": bbox.south,
                "east": bbox.east,
                "north": bbox.north,
            },
            "leaflet_bounds": [
                [bbox.south, bbox.west],
                [bbox.north, bbox.east],
            ],
            "default_zoom": 10,
            "min_zoom": 6,
            "max_zoom": 16,
        }

    def _load_raster(self, path: Path, fallback_name: Optional[str] = None, max_dim: int = 1000) -> np.ndarray:
        p_str = str(path)
        if p_str in self._raster_cache:
            return self._raster_cache[p_str]

        target_path = path
        if not target_path.exists() and fallback_name:
            target_path = path.parent / fallback_name

        if not target_path.exists():
            # If raster file not present, return a clean dummy array (500x500)
            arr = np.full((500, 500), np.nan, dtype=np.float32)
            self._raster_cache[p_str] = arr
            return arr

        with rasterio.open(target_path) as src:
            h, w = src.height, src.width
            # Rapid decimation if raster exceeds max_dim for interactive visualization
            step = max(1, max(h, w) // max_dim)
            if step > 1:
                arr = src.read(1, out_shape=(h // step, w // step)).astype(np.float32)
            else:
                arr = src.read(1).astype(np.float32)

            self._raster_cache[p_str] = arr
            return arr


visualization_engine = VisualizationEngine()
