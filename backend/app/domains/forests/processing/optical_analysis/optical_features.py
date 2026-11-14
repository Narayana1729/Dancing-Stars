"""Calculation of multi-spectral optical indices and temporal differentials."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
import numpy as np

from app.domains.forests.processing.optical_analysis.sentinel2_loader import (
    Sentinel2Mosaic,
)


@dataclass
class OpticalPairFeatures:
    """Biophysical spectral indices and temporal changes across pre/post Sentinel-2 pair."""
    # Vegetation Indices (10 m native)
    ndvi_pre: np.ndarray
    ndvi_post: np.ndarray
    delta_ndvi: np.ndarray

    # Canopy Moisture Indices (NDMI / NDWI, 10 m upsampled)
    ndmi_pre: np.ndarray
    ndmi_post: np.ndarray
    delta_ndmi: np.ndarray

    # Burn Severity Indices (NBR and USGS dNBR, 10 m upsampled)
    nbr_pre: np.ndarray
    nbr_post: np.ndarray
    dnbr: np.ndarray  # Key & Benson (2006): NBR_pre - NBR_post (higher = severe burn)

    # Observation Counts & Masks
    valid_count_map: np.ndarray  # uint8: 0, 1, or 2 clear-sky observations
    valid_pair_mask: np.ndarray  # bool: True where both dates are clear-sky valid

    # Summary Statistics
    statistics: Dict[str, Dict[str, float]]


def _calc_normalized_diff(band_a: np.ndarray, band_b: np.ndarray) -> np.ndarray:
    """Safely calculate normalized difference ratio (A - B) / (A + B)."""
    denom = band_a + band_b
    valid = np.isfinite(band_a) & np.isfinite(band_b) & (denom > 1e-6)

    ratio = np.full(band_a.shape, np.nan, dtype=np.float32)
    ratio[valid] = (band_a[valid] - band_b[valid]) / denom[valid]
    ratio[valid] = np.clip(ratio[valid], -1.0, 1.0)
    return ratio


def compute_distribution_stats(arr: np.ndarray, mask: np.ndarray) -> Dict[str, float]:
    """Calculate summary statistics over a valid masked region."""
    data = arr[mask & np.isfinite(arr)]
    if len(data) == 0:
        return {
            "count": 0,
            "min": float("nan"),
            "max": float("nan"),
            "mean": float("nan"),
            "std": float("nan"),
            "median": float("nan"),
            "p05": float("nan"),
            "p25": float("nan"),
            "p75": float("nan"),
            "p95": float("nan"),
        }
    return {
        "count": int(len(data)),
        "min": float(np.min(data)),
        "max": float(np.max(data)),
        "mean": float(np.mean(data)),
        "std": float(np.std(data)),
        "median": float(np.median(data)),
        "p05": float(np.percentile(data, 5)),
        "p25": float(np.percentile(data, 25)),
        "p75": float(np.percentile(data, 75)),
        "p95": float(np.percentile(data, 95)),
    }


def compute_optical_pair_features(
    pre_mosaic: Sentinel2Mosaic,
    post_mosaic: Sentinel2Mosaic,
) -> OpticalPairFeatures:
    """Compute biophysical indices and temporal differentials from pre/post Sentinel-2 mosaics.

    Equations:
      NDVI = (B08 - B04) / (B08 + B04)
      NDMI = (B08 - B11) / (B08 + B11)
      NBR  = (B8A - B12) / (B8A + B12)
      ΔNDVI = NDVI_post - NDVI_pre
      ΔNDMI = NDMI_post - NDMI_pre
      dNBR  = NBR_pre - NBR_post  (USGS standard sign convention)
    """
    valid_pre = pre_mosaic.valid_mask
    valid_post = post_mosaic.valid_mask

    # 1. Normalized Difference Vegetation Index (NDVI)
    ndvi_pre = _calc_normalized_diff(pre_mosaic.b08, pre_mosaic.b04)
    ndvi_post = _calc_normalized_diff(post_mosaic.b08, post_mosaic.b04)

    # 2. Normalized Difference Moisture Index (NDMI)
    ndmi_pre = _calc_normalized_diff(pre_mosaic.b08, pre_mosaic.b11)
    ndmi_post = _calc_normalized_diff(post_mosaic.b08, post_mosaic.b11)

    # 3. Normalized Burn Ratio (NBR)
    nbr_pre = _calc_normalized_diff(pre_mosaic.b8a, pre_mosaic.b12)
    nbr_post = _calc_normalized_diff(post_mosaic.b8a, post_mosaic.b12)

    # 4. Valid observation counts (0, 1, 2)
    valid_count_map = (valid_pre.astype(np.uint8) + valid_post.astype(np.uint8))
    valid_pair_mask = (valid_count_map == 2)

    # 5. Differentials (strictly masked to valid pairs)
    delta_ndvi = np.full(ndvi_pre.shape, np.nan, dtype=np.float32)
    delta_ndmi = np.full(ndmi_pre.shape, np.nan, dtype=np.float32)
    dnbr = np.full(nbr_pre.shape, np.nan, dtype=np.float32)

    delta_ndvi[valid_pair_mask] = (ndvi_post[valid_pair_mask] - ndvi_pre[valid_pair_mask]).astype(np.float32)
    delta_ndmi[valid_pair_mask] = (ndmi_post[valid_pair_mask] - ndmi_pre[valid_pair_mask]).astype(np.float32)
    # USGS dNBR: NBR_pre - NBR_post (positive = severe burn)
    dnbr[valid_pair_mask] = (nbr_pre[valid_pair_mask] - nbr_post[valid_pair_mask]).astype(np.float32)

    stats = {
        "ndvi_pre": compute_distribution_stats(ndvi_pre, valid_pre),
        "ndvi_post": compute_distribution_stats(ndvi_post, valid_post),
        "delta_ndvi": compute_distribution_stats(delta_ndvi, valid_pair_mask),
        "ndmi_pre": compute_distribution_stats(ndmi_pre, valid_pre),
        "ndmi_post": compute_distribution_stats(ndmi_post, valid_post),
        "delta_ndmi": compute_distribution_stats(delta_ndmi, valid_pair_mask),
        "nbr_pre": compute_distribution_stats(nbr_pre, valid_pre),
        "nbr_post": compute_distribution_stats(nbr_post, valid_post),
        "dnbr": compute_distribution_stats(dnbr, valid_pair_mask),
    }

    return OpticalPairFeatures(
        ndvi_pre=ndvi_pre,
        ndvi_post=ndvi_post,
        delta_ndvi=delta_ndvi,
        ndmi_pre=ndmi_pre,
        ndmi_post=ndmi_post,
        delta_ndmi=delta_ndmi,
        nbr_pre=nbr_pre,
        nbr_post=nbr_post,
        dnbr=dnbr,
        valid_count_map=valid_count_map,
        valid_pair_mask=valid_pair_mask,
        statistics=stats,
    )

