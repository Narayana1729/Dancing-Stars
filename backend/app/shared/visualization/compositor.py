from __future__ import annotations

import io
from enum import Enum
from typing import Optional, Tuple
import numpy as np
from PIL import Image


class SarCompositeType(str, Enum):
    DUAL_POL_RGB = "DUAL_POL_RGB"                      # R: HH, G: HV, B: HH-HV
    MULTI_TEMPORAL_CHANGE_RGB = "MULTI_TEMPORAL_CHANGE"  # R: t0 HV, G: t1 HV, B: Delta(HV/HH)


class OpticalCompositeType(str, Enum):
    COLOR_INFRARED_CIR = "COLOR_INFRARED_CIR"          # R: NIR(B08), G: Red(B04), B: Green(B03)
    SWIR_BURN_SEVERITY = "SWIR_BURN_SEVERITY"          # R: SWIR2(B12), G: NIR(B8A), B: Red(B04)
    TRUE_COLOR_RGB = "TRUE_COLOR_RGB"                  # R: Red(B04), G: Green(B03), B: Blue(B02)


def robust_percentile_stretch(
    band: np.ndarray,
    valid_mask: np.ndarray,
    p_min: float = 2.0,
    p_max: float = 98.0,
) -> np.ndarray:
    """Linearly stretch valid pixels between p_min and p_max percentiles into [0, 255] uint8."""
    out = np.zeros(band.shape, dtype=np.uint8)
    valid_vals = band[valid_mask]
    if len(valid_vals) == 0:
        return out

    val_low = float(np.nanpercentile(valid_vals, p_min))
    val_high = float(np.nanpercentile(valid_vals, p_max))

    if val_high <= val_low:
        val_high = val_low + 1.0

    stretched = np.clip((band - val_low) / (val_high - val_low), 0.0, 1.0)
    out[valid_mask] = (stretched[valid_mask] * 255.0).astype(np.uint8)
    return out


class SARFalseColorCompositor:
    """Generates false-color RGB imagery from dual-pol and multi-temporal SAR backscatter."""

    @staticmethod
    def create_dual_pol_rgb(
        hh_db: np.ndarray,
        hv_db: np.ndarray,
        valid_mask: Optional[np.ndarray] = None,
        p_min: float = 2.0,
        p_max: float = 98.0,
    ) -> bytes:
        """Create Dual-Pol RGB composite: R=HH, G=HV, B=HH-HV.
        
        Interpretation:
        - Dense Forest: Rich Green (strong volume scattering in HV).
        - Urban / Double-Bounce: Yellow/White (strong in both HH and HV).
        - Bare Soil / Smooth Surface: Deep Blue/Violet (stronger HH, weak HV).
        - Calm Water: Dark/Black (specular reflection, low backscatter in both).
        """
        if valid_mask is None:
            valid_mask = (~np.isnan(hh_db)) & (~np.isnan(hv_db))

        diff_db = hh_db - hv_db  # Co-to-cross polarization difference

        r = robust_percentile_stretch(hh_db, valid_mask, p_min, p_max)
        g = robust_percentile_stretch(hv_db, valid_mask, p_min, p_max)
        b = robust_percentile_stretch(diff_db, valid_mask, p_min, p_max)
        alpha = np.where(valid_mask, 255, 0).astype(np.uint8)

        rgba = np.stack([r, g, b, alpha], axis=-1)
        img = Image.fromarray(rgba, mode="RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    @staticmethod
    def create_multitemporal_change_rgb(
        hv_t0_db: np.ndarray,
        hv_t1_db: np.ndarray,
        delta_ratio_db: np.ndarray,
        valid_mask: Optional[np.ndarray] = None,
        p_min: float = 2.0,
        p_max: float = 98.0,
    ) -> bytes:
        """Create Multi-temporal Change RGB composite: R=t0 HV, G=t1 HV, B=Delta Ratio.
        
        Interpretation:
        - Stable Forest: Neutral / Olive-Green (t0 HV ~= t1 HV).
        - Canopy Loss / Deforestation: Bright Red / Orange (high t0 HV, low t1 HV).
        - Regrowth / Flush: Bright Green / Cyan (low t0 HV, high t1 HV).
        - Moisture / Soil Drift: Blue / Magenta (driven by polarization ratio changes).
        """
        if valid_mask is None:
            valid_mask = (~np.isnan(hv_t0_db)) & (~np.isnan(hv_t1_db)) & (~np.isnan(delta_ratio_db))

        r = robust_percentile_stretch(hv_t0_db, valid_mask, p_min, p_max)
        g = robust_percentile_stretch(hv_t1_db, valid_mask, p_min, p_max)
        b = robust_percentile_stretch(delta_ratio_db, valid_mask, p_min, p_max)
        alpha = np.where(valid_mask, 255, 0).astype(np.uint8)

        rgba = np.stack([r, g, b, alpha], axis=-1)
        img = Image.fromarray(rgba, mode="RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


class OpticalFalseColorCompositor:
    """Generates false-color RGB imagery from Sentinel-2 / Landsat optical surface reflectance."""

    @staticmethod
    def create_color_infrared_cir(
        nir_band: np.ndarray,
        red_band: np.ndarray,
        green_band: np.ndarray,
        valid_mask: Optional[np.ndarray] = None,
        p_min: float = 2.0,
        p_max: float = 98.0,
    ) -> bytes:
        """Create Standard Color Infrared (CIR) composite: R=NIR, G=Red, B=Green.
        
        Interpretation:
        - Healthy Dense Canopy: Vibrant Crimson / Deep Red (high NIR reflectance).
        - Cleared Land / Built-up: Cyan / White / Light Brown.
        - Water Bodies: Jet Black / Dark Navy.
        """
        if valid_mask is None:
            valid_mask = (~np.isnan(nir_band)) & (~np.isnan(red_band)) & (~np.isnan(green_band))

        r = robust_percentile_stretch(nir_band, valid_mask, p_min, p_max)
        g = robust_percentile_stretch(red_band, valid_mask, p_min, p_max)
        b = robust_percentile_stretch(green_band, valid_mask, p_min, p_max)
        alpha = np.where(valid_mask, 255, 0).astype(np.uint8)

        rgba = np.stack([r, g, b, alpha], axis=-1)
        img = Image.fromarray(rgba, mode="RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    @staticmethod
    def create_swir_burn_severity(
        swir2_band: np.ndarray,
        nir_band: np.ndarray,
        red_band: np.ndarray,
        valid_mask: Optional[np.ndarray] = None,
        p_min: float = 2.0,
        p_max: float = 98.0,
    ) -> bytes:
        """Create SWIR Burn Severity composite: R=SWIR2, G=NIR, B=Red.
        
        Interpretation:
        - Active Fire / Recent Scar: Vivid Bright Orange / Brick Red (high SWIR2 from char & dry soil).
        - Intact Healthy Forest: Brilliant Emerald Green (high NIR, low SWIR2).
        - Dry Sparse Scrub: Tan / Ochre.
        """
        if valid_mask is None:
            valid_mask = (~np.isnan(swir2_band)) & (~np.isnan(nir_band)) & (~np.isnan(red_band))

        r = robust_percentile_stretch(swir2_band, valid_mask, p_min, p_max)
        g = robust_percentile_stretch(nir_band, valid_mask, p_min, p_max)
        b = robust_percentile_stretch(red_band, valid_mask, p_min, p_max)
        alpha = np.where(valid_mask, 255, 0).astype(np.uint8)

        rgba = np.stack([r, g, b, alpha], axis=-1)
        img = Image.fromarray(rgba, mode="RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
