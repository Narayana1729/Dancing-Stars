"""Unit and integration tests for multi-sensor SAR vs optical validation."""
from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin

from app.domains.forests.processing.validation.candidate_extractor import (
    extract_validation_candidates,
)
from app.domains.forests.processing.validation.comparator import (
    CATEGORY_NAMES,
    ValidationAgreementMap,
    synthesize_validation_agreement,
)


def create_synthetic_inputs(shape: tuple[int, int] = (15, 15)):
    """Create synthetic multi-sensor rasters for deterministic validation logic tests."""
    sar_regimes = np.full(shape, 1, dtype=np.uint8)  # Default: Stable (1)
    sar_vc = np.full(shape, 2, dtype=np.uint8)        # Default: Valid (2)
    opt_labels = np.full(shape, 2, dtype=np.uint8)    # Default: No disturbance (2)
    opt_subtypes = np.full(shape, 21, dtype=np.uint8) # Default: Stable forest (21)
    opt_vc = np.full(shape, 2, dtype=np.uint8)        # Default: Valid (2)

    sanctuary_mask = np.ones(shape, dtype=bool)
    core_mask = np.zeros(shape, dtype=bool)
    core_mask[5:10, 5:10] = True

    # 1. Pixel (0, 0): Disturbance Agreement (SAR 4 & Opt 1) -> Cat 1
    sar_regimes[0, 0] = 4
    opt_labels[0, 0] = 1
    opt_subtypes[0, 0] = 11

    # 2. Pixel (1, 1): Stable Agreement (SAR 1 & Opt 21) -> Cat 1
    sar_regimes[1, 1] = 1
    opt_labels[1, 1] = 2
    opt_subtypes[1, 1] = 21

    # 3. Pixel (2, 2): SAR-Only Candidate (SAR 4 & Opt 2) -> Cat 2
    sar_regimes[2, 2] = 4
    opt_labels[2, 2] = 2
    opt_subtypes[2, 2] = 21

    # 4. Pixel (3, 3): Optical-Only Candidate (Opt 1 & SAR 1) -> Cat 3
    sar_regimes[3, 3] = 1
    opt_labels[3, 3] = 1
    opt_subtypes[3, 3] = 12

    # 5. Pixel (4, 4): Likely Seasonal Variation (SAR drop & Opt 32 surface scorch) -> Cat 4
    sar_regimes[4, 4] = 4
    opt_labels[4, 4] = 3
    opt_subtypes[4, 4] = 32

    # 6. Pixel (5, 5): Uncertain (SAR 5 Ambiguous & Opt 33) -> Cat 5
    sar_regimes[5, 5] = 5
    opt_labels[5, 5] = 3
    opt_subtypes[5, 5] = 33

    # 7. Pixel (6, 6): Insufficient observations (SAR outside swath: vc=0) -> Cat 6
    sar_vc[6, 6] = 0

    return (
        sar_regimes,
        sar_vc,
        opt_labels,
        opt_subtypes,
        opt_vc,
        sanctuary_mask,
        core_mask,
    )


def test_evidence_category_synthesis():
    """Verify deterministic pixel-level assignment of the 6 evidence categories."""
    (
        sar_regimes,
        sar_vc,
        opt_labels,
        opt_subtypes,
        opt_vc,
        sanctuary_mask,
        core_mask,
    ) = create_synthetic_inputs()

    val_map = synthesize_validation_agreement(
        sar_regimes=sar_regimes,
        sar_valid_count=sar_vc,
        opt_labels=opt_labels,
        opt_subtypes=opt_subtypes,
        opt_valid_count=opt_vc,
        sanctuary_mask=sanctuary_mask,
        core_mask=core_mask,
    )
    agr = val_map.agreement_map

    assert agr[0, 0] == 1  # SAR and optical agree (disturbance)
    assert agr[1, 1] == 1  # SAR and optical agree (stable)
    assert agr[2, 2] == 2  # SAR-only candidate
    assert agr[3, 3] == 3  # Optical-only candidate
    assert agr[4, 4] == 4  # Likely seasonal or temporary variation
    assert agr[5, 5] == 5  # Uncertain
    assert agr[6, 6] == 6  # Insufficient observations


def test_candidate_extraction_properties():
    """Verify that extracted candidate features contain valid geometries and structured schemas."""
    (
        sar_regimes,
        sar_vc,
        opt_labels,
        opt_subtypes,
        opt_vc,
        sanctuary_mask,
        core_mask,
    ) = create_synthetic_inputs(shape=(20, 20))

    # Plant a 4x4 cluster of SAR-only candidates (Cat 2)
    sar_regimes[2:6, 2:6] = 4
    opt_labels[2:6, 2:6] = 2

    val_map = synthesize_validation_agreement(
        sar_regimes=sar_regimes,
        sar_valid_count=sar_vc,
        opt_labels=opt_labels,
        opt_subtypes=opt_subtypes,
        opt_valid_count=opt_vc,
        sanctuary_mask=sanctuary_mask,
        core_mask=core_mask,
    )

    shape = (20, 20)
    transform = from_origin(400000.0, 2400000.0, 10.0, 10.0)

    # Synthetic scalar rasters
    sar_dhv = np.full(shape, -3.5, dtype=np.float32)
    sar_dhh = np.full(shape, -1.0, dtype=np.float32)
    sar_dr = np.full(shape, -2.5, dtype=np.float32)
    sar_tstd = np.full(shape, 2.5, dtype=np.float32)
    opt_ndvi_pre = np.full(shape, 0.75, dtype=np.float32)
    opt_ndvi_post = np.full(shape, 0.70, dtype=np.float32)
    opt_dndvi = np.full(shape, -0.05, dtype=np.float32)
    opt_dnbr = np.full(shape, 0.02, dtype=np.float32)
    opt_dndmi = np.full(shape, -0.05, dtype=np.float32)
    forest_mask = np.ones(shape, dtype=bool)

    candidates = extract_validation_candidates(
        agreement_map=val_map.agreement_map,
        sar_dhv=sar_dhv,
        sar_dhh=sar_dhh,
        sar_dr=sar_dr,
        sar_tstd=sar_tstd,
        sar_regimes=sar_regimes,
        sar_vc=sar_vc,
        opt_ndvi_pre=opt_ndvi_pre,
        opt_ndvi_post=opt_ndvi_post,
        opt_dndvi=opt_dndvi,
        opt_dnbr=opt_dnbr,
        opt_dndmi=opt_dndmi,
        opt_labels=opt_labels,
        opt_subtypes=opt_subtypes,
        forest_cover_mask=forest_mask,
        sanctuary_mask=sanctuary_mask,
        core_mask=core_mask,
        transform=transform,
        max_candidates_per_cat=5,
        min_cluster_pixels=10,
    )

    assert len(candidates) > 0
    c1 = candidates[0]
    p = c1["properties"]

    assert "candidate_id" in p
    assert "validation_category" in p
    assert "area_ha" in p
    assert p["area_ha"] > 0
    assert "centroid_utm45n" in p
    assert "sar_features" in p
    assert "optical_features" in p
    assert "reason_for_classification" in p
    assert len(p["reason_for_classification"]) > 20
    assert c1["geometry"]["type"] in ["Polygon", "MultiPolygon"]

