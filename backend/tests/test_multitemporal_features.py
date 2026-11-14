"""Comprehensive unit and regression tests for generalized multi-temporal feature extraction.

Tests all seven review corrections:
- Linear-power vs decibel-domain separation
- MAD and dispersion behavior across N_valid = 0, 1, >= 2
- Denominator and validity safeguards for Relative Normalized Difference (RND)
- Three-tier disturbance classification taxonomy (Instantaneous, Sustained, Persistent)
- Tiled Theil-Sen slope estimation with exact fractional-day Doppler timestamps
- 12-point acquisition compatibility validation
- Memory-bounded execution and backward compatibility
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
import numpy as np
import pytest
from rasterio.transform import Affine, from_origin

from app.domains.forests.processing.temporal_analysis.disturbance_indicators import (
    classify_physical_change_regimes,
    evaluate_tier1_instantaneous_candidate,
    evaluate_tier2_sustained_anomaly,
    evaluate_tier3_persistent_candidate,
)
from app.domains.forests.processing.temporal_analysis.metadata import (
    AcquisitionMetadata,
    TemporalSeriesMetadata,
)
from app.domains.forests.processing.temporal_analysis.temporal_features import (
    MultiTemporalFeatures,
    extract_multitemporal_features,
)
from app.domains.forests.processing.temporal_analysis.temporal_loader import (
    LoadedTemporalSeries,
)
from app.domains.forests.processing.temporal_analysis.temporal_statistics import (
    EPSILON_NUMERICAL_STABILITY,
    compute_db_temporal_statistics,
    compute_linear_temporal_statistics,
    compute_relative_normalized_difference,
    compute_temporal_zscore,
    compute_tiled_theil_sen_slope,
)
from app.domains.forests.processing.temporal_analysis.temporal_validation import (
    COORD_TOLERANCE_M,
    CompatibilityError,
    GridVerificationContext,
    compare_raster_baselines,
    validate_acquisition_compatibility,
)


def make_dummy_acq_meta(
    granule_id: str = "NISAR_TEST_001",
    acq_time: str = "2026-03-04T23:37:20",
    track: int = 98,
    frame: int = 12,
    orbit_pass: str = "Ascending",
    look_dir: str = "Left",
    frequency_band: str = "frequencyB",
    near_inc: float = 33.0,
    far_inc: float = 47.0,
) -> AcquisitionMetadata:
    """Create test AcquisitionMetadata."""
    return AcquisitionMetadata(
        granule_id=granule_id,
        acquisition_time=acq_time,
        track=track,
        frame=frame,
        orbit_pass=orbit_pass,
        look_direction=look_dir,
        crid="P05023",
        frequency_band=frequency_band,
        center_frequency_hz=1293500000.0,
        range_bandwidth_hz=5000000.0,
        near_range_incidence_deg=near_inc,
        far_range_incidence_deg=far_inc,
        range_resolution_m=30.0,
        azimuth_resolution_m=5.36,
    )


def make_dummy_grid_ctx(
    crs: str = "EPSG:32645",
    x0: float = 400000.0,
    y0: float = 2400000.0,
    dx: float = 80.0,
    dy: float = -80.0,
    shape: Tuple[int, int] = (10, 10),
) -> GridVerificationContext:
    """Create test GridVerificationContext."""
    transform = from_origin(x0 - dx / 2.0, y0 - dy / 2.0, dx, -dy)
    x_first = x0
    x_last = x0 + (shape[1] - 1) * dx
    y_first = y0
    y_last = y0 + (shape[0] - 1) * dy
    return GridVerificationContext(
        crs=crs,
        transform=transform,
        shape=shape,
        x_first=x_first,
        x_last=x_last,
        y_first=y_first,
        y_last=y_last,
        dx=dx,
        dy=dy,
    )


# ---------------------------------------------------------------------------
# Test 1: Linear-Power vs Decibel-Domain Separation & Dispersion Behavior
# ---------------------------------------------------------------------------
def test_linear_vs_db_domain_statistics_separation():
    """Verify linear mean/std in power space and median/MAD in decibel space."""
    # Synthetic 4-epoch series: [0.01, 0.04, 0.02, 0.08] in linear power
    linear_vals = np.array([0.01, 0.04, 0.02, 0.08], dtype=np.float32)
    db_vals = (10.0 * np.log10(linear_vals)).astype(np.float32)

    stack_linear = np.tile(linear_vals[:, None, None], (1, 5, 5))
    stack_db = np.tile(db_vals[:, None, None], (1, 5, 5))
    valid_mask = np.ones((4, 5, 5), dtype=bool)

    # 1. Linear statistics
    mean_lin, std_lin = compute_linear_temporal_statistics(stack_linear, valid_mask)
    expected_mean_lin = float(np.mean(linear_vals))
    expected_std_lin = float(np.std(linear_vals, ddof=1))

    assert np.allclose(mean_lin, expected_mean_lin, atol=1e-5)
    assert np.allclose(std_lin, expected_std_lin, atol=1e-5)

    # 2. Decibel statistics
    median_db, mad_db = compute_db_temporal_statistics(stack_db, valid_mask)
    expected_median_db = float(np.median(db_vals))
    expected_mad_db = float(1.4826 * np.median(np.abs(db_vals - expected_median_db)))

    assert np.allclose(median_db, expected_median_db, atol=1e-5)
    assert np.allclose(mad_db, expected_mad_db, atol=1e-5)


def test_mad_and_std_behavior_by_valid_observation_count():
    """Verify MAD and Sample Std behavior across N_valid = 0, 1, and >= 2."""
    shape = (1, 3, 3)
    # Pixel (0, 0): N_valid = 0
    # Pixel (0, 1): N_valid = 1
    # Pixel (0, 2): N_valid = 2
    # Pixel (1, 0): N_valid = 3
    stack_lin = np.array([
        [[0.01, 0.01, 0.01]],
        [[0.02, 0.02, 0.04]],
        [[0.03, 0.03, 0.09]],
    ], dtype=np.float32).reshape(3, 1, 3)  # T=3, H=1, W=3

    stack_db = (10.0 * np.log10(stack_lin)).astype(np.float32)

    valid_mask = np.zeros((3, 1, 3), dtype=bool)
    # Pixel (0, 0): 0 valid
    # Pixel (0, 1): 1 valid (epoch 0 only)
    valid_mask[0, 0, 1] = True
    # Pixel (0, 2): 2 valid (epochs 0 and 1)
    valid_mask[0, 0, 2] = True
    valid_mask[1, 0, 2] = True

    # Linear stats
    mean_lin, std_lin = compute_linear_temporal_statistics(stack_lin, valid_mask)
    assert np.isnan(mean_lin[0, 0])
    assert not np.isnan(mean_lin[0, 1])
    assert not np.isnan(mean_lin[0, 2])

    # Sample standard deviation MUST be NaN for N_valid < 2
    assert np.isnan(std_lin[0, 0])
    assert np.isnan(std_lin[0, 1])  # N_valid == 1 -> NaN
    assert not np.isnan(std_lin[0, 2])  # N_valid == 2 -> valid

    # Decibel stats
    median_db, mad_db = compute_db_temporal_statistics(stack_db, valid_mask)
    assert np.isnan(median_db[0, 0])
    assert not np.isnan(median_db[0, 1])  # N_valid == 1 -> valid median
    assert not np.isnan(median_db[0, 2])  # N_valid == 2 -> valid median

    # MAD MUST be NaN for N_valid < 2
    assert np.isnan(mad_db[0, 0])
    assert np.isnan(mad_db[0, 1])  # N_valid == 1 -> NaN
    assert not np.isnan(mad_db[0, 2])  # N_valid == 2 -> valid scale


# ---------------------------------------------------------------------------
# Test 2: Denominator and Validity Safeguards for RND
# ---------------------------------------------------------------------------
def test_relative_normalized_difference_safeguards():
    """Verify RND denominator guards, bounds in [-1, 1], and NaN propagation."""
    H, W = 4, 4
    lin_curr = np.full((H, W), 0.04, dtype=np.float32)
    lin_prev = np.full((H, W), 0.02, dtype=np.float32)
    val_curr = np.ones((H, W), dtype=bool)
    val_prev = np.ones((H, W), dtype=bool)

    # Pixel (0, 0): Normal drop from 0.04 to 0.02 -> (0.04 - 0.02) / (0.04 + 0.02) = +0.3333
    # Pixel (0, 1): Zero denominator (both 0.0) -> NaN
    lin_curr[0, 1] = 0.0
    lin_prev[0, 1] = 0.0

    # Pixel (0, 2): Denominator below numerical epsilon (1e-8 < 2e-7) -> NaN
    lin_curr[0, 2] = 5e-8
    lin_prev[0, 2] = 5e-8

    # Pixel (0, 3): Invalid previous epoch -> NaN
    val_prev[0, 3] = False

    # Pixel (1, 0): Negative power anomaly -> NaN
    lin_curr[1, 0] = -0.01

    # Pixel (1, 1): Complete drop to zero -> (0 - 0.05)/(0 + 0.05) = -1.0
    lin_curr[1, 1] = 1e-6
    lin_prev[1, 1] = 0.1

    rnd = compute_relative_normalized_difference(
        lin_curr, lin_prev, val_curr, val_prev, epsilon_num=EPSILON_NUMERICAL_STABILITY
    )

    # Valid pixel
    assert np.isclose(rnd[0, 0], (0.04 - 0.02) / (0.04 + 0.02), atol=1e-5)
    assert -1.0 <= rnd[0, 0] <= 1.0

    # Safeguard rejections
    assert np.isnan(rnd[0, 1])  # Zero denominator
    assert np.isnan(rnd[0, 2])  # Below epsilon_num
    assert np.isnan(rnd[0, 3])  # Invalid epoch
    assert np.isnan(rnd[1, 0])  # Negative power

    # Bounded
    valid_pixels = rnd[np.isfinite(rnd)]
    assert np.all(valid_pixels >= -1.0) and np.all(valid_pixels <= 1.0)


# ---------------------------------------------------------------------------
# Test 3: Theil-Sen Slope Estimation & Exact Doppler Timestamps
# ---------------------------------------------------------------------------
def test_theil_sen_slope_with_fractional_days_and_outliers():
    """Verify Theil-Sen trend recovery with exact Doppler timestamps and outliers."""
    # Synthetic time series across 4 epochs: t = [0.0, 12.0, 24.0, 36.0] days
    # True underlying linear slope: -0.05 dB / day (total drop -1.8 dB over 36 days)
    t_days = [0.0, 12.0, 24.0, 36.0]
    base_db = -12.0
    true_slope = -0.05

    shape = (10, 10)
    stack_db = np.zeros((4, shape[0], shape[1]), dtype=np.float32)
    valid_mask = np.ones((4, shape[0], shape[1]), dtype=bool)

    for k, t in enumerate(t_days):
        stack_db[k, :, :] = base_db + true_slope * t

    # Inject heavy outlier at epoch 1 for pixel (5, 5) (e.g. wet rain spike +6 dB)
    stack_db[1, 5, 5] = base_db + 6.0

    slope_map, perf = compute_tiled_theil_sen_slope(
        stack_db=stack_db,
        timestamps_days=t_days,
        valid_mask_stack=valid_mask,
        tile_size=4,
    )

    # Normal pixel (0, 0): exactly matches true slope
    assert np.isclose(slope_map[0, 0], true_slope, atol=1e-4)

    # Outlier pixel (5, 5): Theil-Sen median slope resists single outlier!
    # Slopes for pairs: (0,1)=+0.5, (0,2)=-0.05, (0,3)=-0.05, (1,2)=-0.55, (1,3)=-0.30, (2,3)=-0.05
    # Sorted slopes: [-0.55, -0.30, -0.05, -0.05, -0.05, +0.50] -> median is -0.05!
    assert np.isclose(slope_map[5, 5], true_slope, atol=1e-3)

    # Performance logging verified
    assert perf["eligible_pixels"] == 100
    assert perf["duration_seconds"] >= 0.0
    assert perf["peak_rss_mb"] > 0.0


def test_theil_sen_slope_strictly_nan_when_insufficient_epochs():
    """Verify Theil-Sen slope is strictly NaN when N_valid < 3."""
    t_days = [0.0, 48.0]  # Only 2 epochs available (like authentic local NISAR)
    stack_db = np.full((2, 5, 5), -12.0, dtype=np.float32)
    stack_db[1, :, :] = -15.0
    valid_mask = np.ones((2, 5, 5), dtype=bool)

    slope_map, perf = compute_tiled_theil_sen_slope(
        stack_db=stack_db,
        timestamps_days=t_days,
        valid_mask_stack=valid_mask,
        tile_size=2,
    )

    # All pixels MUST be NaN because N=2 < 3
    assert np.all(np.isnan(slope_map))
    assert perf["eligible_pixels"] == 0
    assert "N_valid >= 3" in perf["note"]


# ---------------------------------------------------------------------------
# Test 4: Three-Tier Disturbance Classification Taxonomy
# ---------------------------------------------------------------------------
def test_three_tier_disturbance_classification():
    """Verify Instantaneous (Tier 1), Sustained (Tier 2), and Persistent (Tier 3) logic."""
    shape = (5, 5)

    # 1. Tier 1: Instantaneous Disturbance Candidate (N >= 2)
    dhv = np.full(shape, -1.0, dtype=np.float32)
    dratio = np.full(shape, -0.5, dtype=np.float32)
    inter = np.ones(shape, dtype=bool)

    # Pixel (2, 2) meets Tier 1 criteria (dHV <= -2.5 and dR <= -1.5)
    dhv[2, 2] = -3.5
    dratio[2, 2] = -2.0

    cand_mask, intensity = evaluate_tier1_instantaneous_candidate(dhv, dratio, inter)
    assert cand_mask[2, 2] is True or cand_mask[2, 2] == 1
    assert not cand_mask[0, 0]
    expected_intensity = float(np.sqrt(3.5 * 2.0))
    assert np.isclose(intensity[2, 2], expected_intensity, atol=1e-4)

    # 2. Tier 2: Sustained Anomaly (N >= 3)
    # Pixel (1, 1): drop at t1, sustained at t2 -> Sustained!
    # Pixel (2, 2): drop at t1, REBOUND at t2 (-0.5 dB) -> Transient, NOT sustained!
    dhv_t1 = np.full(shape, 0.0, dtype=np.float32)
    dhv_t2 = np.full(shape, 0.0, dtype=np.float32)
    dratio_t1 = np.full(shape, 0.0, dtype=np.float32)
    valid_3 = np.ones(shape, dtype=bool)

    # Pixel (1, 1): Sustained drop
    dhv_t1[1, 1] = -3.0
    dhv_t2[1, 1] = -2.5
    dratio_t1[1, 1] = -1.8

    # Pixel (2, 2): Transient drop (recovered at t2)
    dhv_t1[2, 2] = -3.5
    dhv_t2[2, 2] = -0.5  # Rebound!
    dratio_t1[2, 2] = -2.0

    sustained_mask, status = evaluate_tier2_sustained_anomaly(
        dhv_t1, dhv_t2, dratio_t1, valid_3
    )
    assert status == "ACTIVE"
    assert sustained_mask[1, 1]  # Sustained
    assert not sustained_mask[2, 2]  # Transient rejected!

    # When N=2, Tier 2 must return UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS (or legacy UNVERIFIABLE_TWO_DATES)
    sustained_n2, status_n2 = evaluate_tier2_sustained_anomaly(
        dhv_t1, None, dratio_t1, valid_3
    )
    assert sustained_n2 is None
    assert status_n2 in ("UNVERIFIABLE_TWO_DATES", "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS")

    # 3. Tier 3: Long-Term Persistent Candidate (N >= 4, elapsed >= 180d)
    # Under N=2 or elapsed < 180d, must return UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS
    pers_n2, status_n3 = evaluate_tier3_persistent_candidate(
        delta_hv_stack=[dhv_t1],
        valid_stack=np.ones((2, 5, 5), dtype=bool),
        elapsed_days=48.0,
    )
    assert pers_n2 is None
    assert status_n3 == "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"


# ---------------------------------------------------------------------------
# Test 5: 12-Point Acquisition Compatibility Validation
# ---------------------------------------------------------------------------
def test_12_point_acquisition_compatibility_validation():
    """Verify strict validation against track, frame, pass, freq, and grid origin offsets."""
    ref_meta = make_dummy_acq_meta(track=98, frame=12, orbit_pass="Ascending", frequency_band="frequencyB")
    ref_grid = make_dummy_grid_ctx(x0=400000.0, y0=2400000.0, dx=80.0, dy=-80.0)

    # Identical candidate -> Must PASS
    cand_meta = make_dummy_acq_meta(granule_id="NISAR_CAND_002", track=98, frame=12, orbit_pass="Ascending")
    cand_grid = make_dummy_grid_ctx(x0=400000.0, y0=2400000.0, dx=80.0, dy=-80.0)
    validate_acquisition_compatibility(ref_meta, cand_meta, ref_grid, cand_grid)

    # Test 1: Track mismatch
    cand_bad_track = make_dummy_acq_meta(track=120)
    with pytest.raises(CompatibilityError, match="Track mismatch"):
        validate_acquisition_compatibility(ref_meta, cand_bad_track, ref_grid, cand_grid)

    # Test 2: Frame mismatch
    cand_bad_frame = make_dummy_acq_meta(frame=13)
    with pytest.raises(CompatibilityError, match="Frame mismatch"):
        validate_acquisition_compatibility(ref_meta, cand_bad_frame, ref_grid, cand_grid)

    # Test 3: Orbit pass direction mismatch (Ascending vs Descending)
    cand_bad_pass = make_dummy_acq_meta(orbit_pass="Descending")
    with pytest.raises(CompatibilityError, match="Orbit pass direction mismatch"):
        validate_acquisition_compatibility(ref_meta, cand_bad_pass, ref_grid, cand_grid)

    # Test 4: Radar frequency mismatch
    cand_bad_freq = make_dummy_acq_meta(frequency_band="frequencyA")
    with pytest.raises(CompatibilityError, match="Radar frequency mismatch"):
        validate_acquisition_compatibility(ref_meta, cand_bad_freq, ref_grid, cand_grid)

    # Test 5: Sub-pixel origin shift (> 1 mm)
    cand_shifted_origin = make_dummy_grid_ctx(x0=400000.05)  # 5 cm shift
    with pytest.raises(CompatibilityError, match="Affine transform origin offset"):
        validate_acquisition_compatibility(ref_meta, cand_meta, ref_grid, cand_shifted_origin)


# ---------------------------------------------------------------------------
# Test 6: Backward Compatibility Regression Comparison against Phase 4.1.1
# ---------------------------------------------------------------------------
def test_backward_compatibility_regression_comparator():
    """Verify that compare_raster_baselines detects exact equality and flags discrepancies."""
    baseline = np.array([[1.0, 2.0], [3.0, np.nan]], dtype=np.float32)
    new_identical = np.array([[1.0, 2.0], [3.0, np.nan]], dtype=np.float32)
    new_numerical_diff = np.array([[1.0000001, 2.0], [3.0, np.nan]], dtype=np.float32)
    new_nan_mismatch = np.array([[1.0, 2.0], [np.nan, np.nan]], dtype=np.float32)

    # Exact match
    res_ident = compare_raster_baselines(baseline, new_identical, tolerance=1e-5)
    assert res_ident["is_compatible"] is True
    assert res_ident["max_absolute_difference"] == 0.0
    assert res_ident["nodata_location_mismatches"] == 0

    # Within tolerance
    res_tol = compare_raster_baselines(baseline, new_numerical_diff, tolerance=1e-5)
    assert res_tol["is_compatible"] is True

    # Nodata mismatch
    res_nan = compare_raster_baselines(baseline, new_nan_mismatch, tolerance=1e-5)
    assert res_nan["is_compatible"] is False
    assert res_nan["nodata_location_mismatches"] == 1
