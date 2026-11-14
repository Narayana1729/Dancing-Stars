"""Unit tests for Phase 4.1 Grid Alignment, Resampling, & Confusion Metrics."""
import numpy as np
import pytest
from rasterio.transform import from_origin

from app.domains.forests.processing.alignment import (
    aggregate_categorical_10m_to_80m,
    aggregate_continuous_10m_to_80m,
    check_grid_nesting,
)


def test_grid_nesting_detection_shifted_vs_nested():
    """Verify check_grid_nesting detects coordinate offsets and true nesting."""
    # 1. True nested grids:
    # 80 m grid starting at (401600.0, 2438400.0)
    t_80_nested = from_origin(401600.0, 2438400.0, 80.0, 80.0)
    shape_80 = (827, 779)
    # 10 m grid starting at exact same corner (401600.0, 2438400.0)
    t_10_nested = from_origin(401600.0, 2438400.0, 10.0, 10.0)
    shape_10 = (6616, 6232)

    res_nested = check_grid_nesting(t_10_nested, shape_10, t_80_nested, shape_80)
    assert res_nested.is_spatially_nested is True
    assert res_nested.origin_offset_x_m == 0.0
    assert res_nested.origin_offset_y_m == 0.0

    # 2. Shifted grids (the actual Phase 4 legacy status: 40 m offset):
    t_10_legacy = from_origin(401640.0, 2438360.0, 10.0, 10.0)
    res_shifted = check_grid_nesting(t_10_legacy, shape_10, t_80_nested, shape_80)
    assert res_shifted.is_spatially_nested is False
    assert res_shifted.origin_offset_x_m == -40.0
    assert res_shifted.origin_offset_y_m == 40.0
    assert "GRID SHIFT DETECTED" in res_shifted.alignment_diagnosis


def test_continuous_aggregation_mean():
    """Verify 8x8 block averaging for continuous arrays."""
    # 16x16 array with 4 8x8 blocks of constant values
    arr = np.zeros((16, 16), dtype=np.float32)
    arr[:8, :8] = 2.0
    arr[:8, 8:] = 4.0
    arr[8:, :8] = 6.0
    arr[8:, 8:] = 8.0

    out = aggregate_continuous_10m_to_80m(arr, method="mean")
    assert out.shape == (2, 2)
    assert np.isclose(out[0, 0], 2.0)
    assert np.isclose(out[0, 1], 4.0)
    assert np.isclose(out[1, 0], 6.0)
    assert np.isclose(out[1, 1], 8.0)


def test_categorical_aggregation_mode():
    """Verify 8x8 modal majority voting for discrete categorical labels."""
    arr = np.zeros((16, 16), dtype=np.uint8)
    # Block 0,0: 50 pixels of class 1, 14 pixels of class 2 -> mode should be 1
    arr[:8, :8] = 2
    arr[:5, :8] = 1  # 40 px of class 1
    arr[5:7, :5] = 1  # +10 px = 50 px of class 1

    # Block 0,1: all class 3
    arr[:8, 8:] = 3

    out = aggregate_categorical_10m_to_80m(arr)
    assert out.shape == (2, 2)
    assert out[0, 0] == 1
    assert out[0, 1] == 3


def test_confusion_metrics_mathematical_definitions():
    """Verify exact definitions of Precision, Recall, FPR, FDR, Specificity, and F1."""
    tp = 10
    fp = 523703
    fn = 33
    tn = 1779220

    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    fpr = fp / (fp + tn)
    fdr = fp / (tp + fp)
    specificity = tn / (tn + fp)
    f1 = 2 * precision * recall / (precision + recall)

    assert np.isclose(precision, 10 / 523713)
    assert np.isclose(recall, 10 / 43)
    assert np.isclose(fpr, 523703 / 2302923)
    assert np.isclose(fdr, 523703 / 523713)
    assert np.isclose(specificity, 1779220 / 2302923)
    assert np.isclose(specificity + fpr, 1.0)
    assert np.isclose(precision + fdr, 1.0)

    # Verify that FPR is ~22.74% while FDR is ~99.998%
    assert 0.22 <= fpr <= 0.23
    assert 0.9999 <= fdr <= 1.0

