"""Generation of independent optical reference labels from Sentinel-2 observations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
import numpy as np

from app.domains.forests.processing.optical_analysis.optical_features import (
    OpticalPairFeatures,
    compute_distribution_stats,
)
from app.domains.forests.processing.optical_analysis.sentinel2_loader import (
    Sentinel2Mosaic,
)


@dataclass
class OpticalReferenceDataset:
    """Independent optical reference dataset for forest disturbance validation."""
    # Primary Reference Categories:
    #   1: Confirmed Disturbance
    #   2: No Observed Disturbance
    #   3: Uncertain
    #   4: Not Observable
    reference_labels: np.ndarray  # uint8: 1 to 4
    # Granular physical sub-types (uint8: 11, 12, 21, 22, 31, 32, 33, 40)
    detailed_subtypes: np.ndarray
    # Pixel counts and ground surface areas (ha and km2)
    category_summary: Dict[str, Dict[str, Any]]
    # Zonal summary across Similipal management zones
    zonal_summary: Dict[str, Dict[str, Any]]


def generate_optical_reference_labels(
    features: OpticalPairFeatures,
    pre_mosaic: Sentinel2Mosaic,
    post_mosaic: Sentinel2Mosaic,
    forest_cover_mask: np.ndarray,  # bool (10 m): True where reference forest canopy >= 30%
    sanctuary_mask: Optional[np.ndarray] = None,
    core_mask: Optional[np.ndarray] = None,
) -> OpticalReferenceDataset:
    """Generate independent optical reference labels using strictly optical criteria.

    Rules:
      - Category 4 (Not Observable): Cloud, cloud shadow, cirrus, or missing data in either epoch.
      - Category 2 (No Observed Disturbance): Clear-sky observation maintaining stable forest canopy.
      - Category 1 (Confirmed Disturbance): Multiple independent optical lines of evidence prove
        physical canopy destruction (severe greenness drop to non-forest level corroborated by
        moderate-high severity burn dNBR >= 0.27 or bare ground exposure).
      - Category 3 (Uncertain): Significant spectral shift (e.g. seasonal deciduous moisture loss or
        surface understory scorch) where independent evidence is insufficient to prove permanent
        canopy tree loss.
    """
    shape = features.ndvi_pre.shape
    labels = np.full(shape, 4, dtype=np.uint8)  # Default: 4 (Not Observable)
    subtypes = np.full(shape, 40, dtype=np.uint8)

    valid_pair = features.valid_pair_mask
    ndvi_pre = features.ndvi_pre
    ndvi_post = features.ndvi_post
    delta_ndvi = features.delta_ndvi
    delta_ndmi = features.delta_ndmi
    dnbr = features.dnbr
    scl_pre = pre_mosaic.scl
    scl_post = post_mosaic.scl

    # Condition: Pre-event confirmed forest
    is_pre_forest = valid_pair & (ndvi_pre >= 0.50) & forest_cover_mask

    # 1. CATEGORY 1: CONFIRMED DISTURBANCE (Strict independent evidence)
    # A. Wildfire crown burn: pre-forest, severe greenness drop to non-forest, dNBR >= 0.27 (USGS moderate-high)
    burn_confirmed = (
        is_pre_forest
        & (delta_ndvi <= -0.20)
        & (ndvi_post < 0.40)
        & (dnbr >= 0.27)
    )

    # B. Mechanical clearing / bare ground exposure: pre-forest, severe greenness drop,
    # SCL transition from Vegetation (4) to Not-Vegetated (5), and severe moisture collapse
    clearing_confirmed = (
        is_pre_forest
        & (delta_ndvi <= -0.25)
        & (ndvi_post < 0.35)
        & (scl_pre == 4)
        & (scl_post == 5)
        & (delta_ndmi <= -0.20)
    )

    confirmed_mask = burn_confirmed | clearing_confirmed
    labels[confirmed_mask] = 1
    subtypes[burn_confirmed] = 11      # Confirmed Crown Fire Burn
    subtypes[clearing_confirmed] = 12  # Confirmed Canopy Clearing / Bare Ground

    # 2. CATEGORY 2: NO OBSERVED DISTURBANCE
    # A. Stable Forest Canopy: pre-forest, greenness maintained, unburned (dNBR < 0.10)
    stable_forest = (
        is_pre_forest
        & (ndvi_post >= 0.45)
        & (np.abs(delta_ndvi) <= 0.15)
        & (dnbr < 0.10)
        & ~confirmed_mask
    )

    # B. Stable Non-Forest: pre-nonforest, stable across dates
    stable_nonforest = (
        valid_pair
        & ~is_pre_forest
        & (np.abs(delta_ndvi) <= 0.12)
        & ~confirmed_mask
    )

    stable_mask = stable_forest | stable_nonforest
    labels[stable_mask] = 2
    subtypes[stable_forest] = 21     # Stable Forest Canopy
    subtypes[stable_nonforest] = 22  # Stable Non-Forest / Water / Rock

    # 3. CATEGORY 3: UNCERTAIN
    # Valid clear-sky pixels not meeting confirmed criteria or stable criteria:
    uncertain_mask = valid_pair & ~confirmed_mask & ~stable_mask
    labels[uncertain_mask] = 3

    # Detailed Subtypes within Uncertain:
    # Subtype 31: Seasonal Phenological Drying / Leaf Drop (greenness drop, but NDVI_post remains >= 0.40, unburned dNBR < 0.10)
    desiccation_uncertain = (
        uncertain_mask
        & is_pre_forest
        & (delta_ndvi < -0.15)
        & (ndvi_post >= 0.40)
        & (dnbr < 0.10)
    )
    # Subtype 32: Surface Understory Litter Scorch / Low Severity Burn (dNBR in [0.10, 0.27), tree canopy partially green)
    surface_scorch_uncertain = (
        uncertain_mask
        & (dnbr >= 0.10)
        & (dnbr < 0.27)
    )
    # Subtype 33: Other Uncertain / Agricultural / Riparian Shifts
    other_uncertain = uncertain_mask & ~desiccation_uncertain & ~surface_scorch_uncertain

    subtypes[desiccation_uncertain] = 31
    subtypes[surface_scorch_uncertain] = 32
    subtypes[other_uncertain] = 33

    # 4. CATEGORY 4: NOT OBSERVABLE (default)
    # labels already 4, subtypes 40

    # Summary Statistics Calculation (10 m resolution: 1 pixel = 0.01 ha = 0.0001 km2)
    pixel_area_ha = 0.01
    pixel_area_km2 = 0.0001
    total_pixels = int(labels.size)

    category_names = {
        1: "Confirmed disturbance",
        2: "No observed disturbance",
        3: "Uncertain",
        4: "Not observable",
    }

    summary: Dict[str, Dict[str, Any]] = {}
    for cat_id, cat_name in category_names.items():
        cnt = int(np.sum(labels == cat_id))
        pct = (cnt / total_pixels) * 100.0
        ha = cnt * pixel_area_ha
        km2 = cnt * pixel_area_km2
        summary[f"category_{cat_id}_{cat_name.lower().replace(' ', '_')}"] = {
            "category_id": cat_id,
            "category_name": cat_name,
            "pixel_count": cnt,
            "percentage_total": round(pct, 2),
            "area_ha": round(ha, 2),
            "area_km2": round(km2, 2),
        }

    # Zonal Stratification across Similipal Reserve Zones
    zonal: Dict[str, Dict[str, Any]] = {}
    zones = {}
    if sanctuary_mask is not None:
        zones["sanctuary"] = sanctuary_mask
    if core_mask is not None:
        zones["core"] = core_mask
    if sanctuary_mask is not None:
        zones["outside_reserve"] = ~sanctuary_mask

    for zone_name, z_mask in zones.items():
        z_total = int(np.sum(z_mask))
        z_dict: Dict[str, Any] = {"total_zone_pixels": z_total}
        for cat_id, cat_name in category_names.items():
            cnt = int(np.sum((labels == cat_id) & z_mask))
            pct = (cnt / z_total * 100.0) if z_total > 0 else 0.0
            ha = cnt * pixel_area_ha
            km2 = cnt * pixel_area_km2
            z_dict[f"category_{cat_id}"] = {
                "name": cat_name,
                "pixel_count": cnt,
                "percentage_zone": round(pct, 2),
                "area_ha": round(ha, 2),
                "area_km2": round(km2, 2),
            }
        zonal[zone_name] = z_dict

    return OpticalReferenceDataset(
        reference_labels=labels,
        detailed_subtypes=subtypes,
        category_summary=summary,
        zonal_summary=zonal,
    )

