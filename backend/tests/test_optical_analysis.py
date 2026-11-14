"""Unit and property tests for independent Sentinel-2 optical reference generation."""
from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin

from app.domains.forests.processing.optical_analysis.optical_features import (
    OpticalPairFeatures,
    _calc_normalized_diff,
    compute_distribution_stats,
    compute_optical_pair_features,
)
from app.domains.forests.processing.optical_analysis.pipeline import (
    downsample_to_80m,
)
from app.domains.forests.processing.optical_analysis.reference_labeler import (
    OpticalReferenceDataset,
    generate_optical_reference_labels,
)
from app.domains.forests.processing.optical_analysis.sentinel2_loader import (
    Sentinel2Mosaic,
)


def create_synthetic_mosaic(
    shape: tuple[int, int] = (20, 20),
    b04_val: float = 0.05,
    b08_val: float = 0.35,
    b8a_val: float = 0.35,
    b11_val: float = 0.15,
    b12_val: float = 0.08,
    scl_val: int = 4,  # 4: Vegetation
    date_str: str = "2026-03-02",
) -> Sentinel2Mosaic:
    """Create a synthetic Sentinel2Mosaic for deterministic unit tests."""
    b04 = np.full(shape, b04_val, dtype=np.float32)
    b08 = np.full(shape, b08_val, dtype=np.float32)
    b8a = np.full(shape, b8a_val, dtype=np.float32)
    b11 = np.full(shape, b11_val, dtype=np.float32)
    b12 = np.full(shape, b12_val, dtype=np.float32)
    scl = np.full(shape, scl_val, dtype=np.uint8)

    valid = np.isin(scl, [2, 4, 5, 6]) & np.isfinite(b04) & (b04 > 0.0)

    return Sentinel2Mosaic(
        acquisition_date=date_str,
        relative_orbit="R076",
        crs="EPSG:32645",
        transform=from_origin(400000.0, 2400000.0, 10.0, 10.0),
        shape_10m=shape,
        b04=b04,
        b08=b08,
        b8a=b8a,
        b11=b11,
        b12=b12,
        scl=scl,
        valid_mask=valid,
    )


def test_normalized_diff_math():
    """Verify analytical correctness of normalized difference calculations."""
    a = np.array([0.4, 0.5, 0.0], dtype=np.float32)
    b = np.array([0.1, 0.5, 0.0], dtype=np.float32)

    res = _calc_normalized_diff(a, b)
    # (0.4 - 0.1) / (0.4 + 0.1) = 0.3 / 0.5 = 0.6
    assert np.isclose(res[0], 0.6, atol=1e-4)
    # (0.5 - 0.5) / 1.0 = 0.0
    assert np.isclose(res[1], 0.0, atol=1e-4)
    # 0.0 / 0.0 -> NaN
    assert np.isnan(res[2])


def test_usgs_dnbr_sign_convention():
    """Verify that dNBR follows the USGS Key & Benson convention: NBR_pre - NBR_post.

    Higher positive values indicate severe fire burn.
    """
    # Pre-event: high NIR (0.40), low SWIR (0.10) -> NBR = (0.4 - 0.1) / (0.4 + 0.1) = 0.3 / 0.5 = +0.60
    pre = create_synthetic_mosaic(b8a_val=0.40, b12_val=0.10, date_str="2026-03-02")
    # Post-event: destroyed canopy with high SWIR char: NIR (0.10), SWIR (0.40) -> NBR = -0.60
    post = create_synthetic_mosaic(b8a_val=0.10, b12_val=0.40, date_str="2026-04-16")

    features = compute_optical_pair_features(pre, post)
    expected_dnbr = 0.60 - (-0.60)  # +1.20
    assert np.allclose(features.dnbr[features.valid_pair_mask], expected_dnbr, atol=1e-4)
    # Must exceed USGS High-Severity Burn threshold (>= 0.66)
    assert np.all(features.dnbr[features.valid_pair_mask] >= 0.66)


def test_reference_category_classification():
    """Verify deterministic assignment of the 4 independent reference categories:

    1: Confirmed Disturbance
    2: No Observed Disturbance
    3: Uncertain
    4: Not Observable
    """
    shape = (10, 10)
    pre = create_synthetic_mosaic(shape=shape, b04_val=0.04, b08_val=0.36)  # NDVI = 0.32/0.40 = 0.80
    post = create_synthetic_mosaic(shape=shape, b04_val=0.04, b08_val=0.36)
    forest_mask = np.ones(shape, dtype=bool)

    # Pixel (0, 0): Confirmed Wildfire Disturbance (severe NDVI drop + dNBR >= 0.27)
    # Pre: NDVI=0.80, NBR=0.60
    # Post: NIR=0.08, Red=0.12 (NDVI = -0.04/0.20 = -0.20), B12=0.35 (NBR = -0.63)
    post.b04[0, 0] = 0.12
    post.b08[0, 0] = 0.08
    post.b8a[0, 0] = 0.08
    post.b12[0, 0] = 0.35

    # Pixel (1, 1): Stable Forest Canopy (maintains NDVI=0.75, unburned)
    post.b04[1, 1] = 0.05
    post.b08[1, 1] = 0.35

    # Pixel (2, 2): Uncertain / Seasonal Moisture Desiccation (moderate drop without burn)
    # Pre NDVI = 0.80, Post NDVI = 0.62 (delta = -0.18), dNBR = 0.04
    post.b04[2, 2] = 0.07
    post.b08[2, 2] = 0.30

    # Pixel (3, 3): Not Observable (Cloud in post-event scene: SCL=9)
    post.scl[3, 3] = 9
    post.valid_mask[3, 3] = False

    features = compute_optical_pair_features(pre, post)
    ref_dataset = generate_optical_reference_labels(features, pre, post, forest_mask)
    labels = ref_dataset.reference_labels

    assert labels[0, 0] == 1  # Confirmed disturbance
    assert labels[1, 1] == 2  # No observed disturbance
    assert labels[2, 2] == 3  # Uncertain (seasonal phenological desiccation)
    assert labels[3, 3] == 4  # Not observable (cloud contamination)


def test_optical_downsampling_to_80m():
    """Verify 8:1 block downsampling logic from 10 m to 80 m."""
    shape_10m = (6616, 6232)
    # Continuous float array test
    test_arr = np.full(shape_10m, 0.5, dtype=np.float32)
    res_80m = downsample_to_80m(test_arr, is_categorical=False)
    assert res_80m.shape == (827, 779)
    assert np.allclose(res_80m, 0.5, atol=1e-4)

    # Categorical label test: test that confirmed disturbance pixels trigger sensitive assignment
    cat_arr = np.full(shape_10m, 2, dtype=np.uint8)  # Default: Stable (2)
    # Put 10 confirmed disturbance pixels (1) in block (0, 0)
    cat_arr[:4, :3] = 1
    res_cat_80m = downsample_to_80m(cat_arr, is_categorical=True)
    assert res_cat_80m[0, 0] == 1  # Sensitive detection triggered
    assert res_cat_80m[1, 1] == 2  # Other blocks remain stable

