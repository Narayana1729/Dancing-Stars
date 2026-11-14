"""Spatial Context, Connected Components, & Minimum Mapping Unit (MMU) Analysis.

Investigates and enforces Minimum Mapping Units based on actual spatial resolution:
- Frequency A (10 m spacing, ~100 m² native resolution cell):
  MMU = 5 pixels (0.05 ha) to filter single-look speckle while preserving fine canopy gaps.
- Frequency B (80 m spacing, ~6,400 m² multi-looked resolution cell):
  MMU = 1 pixel (0.64 ha) or 2 pixels (1.28 ha) because pixels are already multi-looked.

Preserves fine linear and small canopy features; avoids unjustified spatial smoothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy import ndimage


@dataclass
class MMUConfiguration:
    """Configuration parameters for spatial context and Minimum Mapping Unit filtering."""
    frequency_name: str
    pixel_size_m: float
    pixel_area_ha: float
    min_cluster_pixels: int
    mmu_area_ha: float
    connectivity: int = 8  # 8-connectivity (diagonal adjacency allowed)


def get_default_mmu_config(frequency: str) -> MMUConfiguration:
    """Return physically justified MMU configuration for Frequency A or B.

    Parameters
    ----------
    frequency : str
        'frequencyA' or 'frequencyB' (case-insensitive).

    Returns
    -------
    MMUConfiguration
    """
    freq = frequency.lower()
    if "a" in freq:
        # Frequency A: 10 m pixel spacing, single-look speckle requires ~0.05 ha (5 pixels)
        return MMUConfiguration(
            frequency_name="Frequency A",
            pixel_size_m=10.0,
            pixel_area_ha=0.01,
            min_cluster_pixels=5,
            mmu_area_ha=0.05,
            connectivity=8,
        )
    elif "b" in freq:
        # Frequency B: 80 m pixel spacing, multi-looked (16x looks), 1 pixel is already 0.64 ha
        return MMUConfiguration(
            frequency_name="Frequency B",
            pixel_size_m=80.0,
            pixel_area_ha=0.64,
            min_cluster_pixels=1,
            mmu_area_ha=0.64,
            connectivity=8,
        )
    else:
        raise ValueError(f"Unknown frequency identifier: '{frequency}'. Expected 'frequencyA' or 'frequencyB'.")


def filter_by_minimum_mapping_unit(
    binary_mask: np.ndarray,
    mmu_config: MMUConfiguration,
) -> Tuple[np.ndarray, int, Dict[str, Any]]:
    """Filter binary anomaly mask by connected-component Minimum Mapping Unit.

    Uses 8-connectivity without morphological smoothing to preserve narrow linear
    features and small natural disturbance patches.

    Parameters
    ----------
    binary_mask : np.ndarray
        Boolean 2D mask of raw candidate anomaly pixels.
    mmu_config : MMUConfiguration
        Configuration specifying pixel area and minimum cluster size.

    Returns
    -------
    filtered_mask : np.ndarray
        Boolean 2D mask of anomalies meeting the MMU.
    cluster_count : int
        Number of distinct spatial clusters retained.
    cluster_stats : Dict[str, Any]
        Cluster size metrics (mean ha, max ha, total ha).
    """
    if not np.any(binary_mask):
        return binary_mask.copy(), 0, {
            "total_retained_clusters": 0,
            "total_retained_pixels": 0,
            "total_retained_area_ha": 0.0,
            "filtered_sub_mmu_pixels": 0,
            "filtered_sub_mmu_clusters": 0,
        }

    # 8-connectivity structuring element
    structure = ndimage.generate_binary_structure(2, 2)
    labeled, num_features = ndimage.label(binary_mask, structure=structure)

    if num_features == 0:
        return binary_mask.copy(), 0, {
            "total_retained_clusters": 0,
            "total_retained_pixels": 0,
            "total_retained_area_ha": 0.0,
            "filtered_sub_mmu_pixels": 0,
            "filtered_sub_mmu_clusters": 0,
        }

    # Calculate cluster sizes
    cluster_sizes = ndimage.sum(binary_mask, labeled, range(num_features + 1))
    
    # Filter out clusters smaller than min_cluster_pixels
    min_pixels = mmu_config.min_cluster_pixels
    keep_indices = np.where(cluster_sizes >= min_pixels)[0]
    # Index 0 is the background
    keep_indices = keep_indices[keep_indices != 0]

    filtered_mask = np.isin(labeled, keep_indices)
    retained_labeled, retained_count = ndimage.label(filtered_mask, structure=structure)

    retained_pixels = int(np.sum(filtered_mask))
    retained_area_ha = round(retained_pixels * mmu_config.pixel_area_ha, 3)

    raw_pixels = int(np.sum(binary_mask))
    filtered_pixels = raw_pixels - retained_pixels
    filtered_clusters = int(num_features - retained_count)

    stats = {
        "total_retained_clusters": int(retained_count),
        "total_retained_pixels": retained_pixels,
        "total_retained_area_ha": retained_area_ha,
        "filtered_sub_mmu_pixels": filtered_pixels,
        "filtered_sub_mmu_clusters": filtered_clusters,
        "mmu_threshold_pixels": min_pixels,
        "mmu_threshold_ha": mmu_config.mmu_area_ha,
    }

    return filtered_mask, int(retained_count), stats

