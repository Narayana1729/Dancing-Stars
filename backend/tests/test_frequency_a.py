"""Unit and property tests for Frequency A (10 m) loader and polarimetric feature extraction."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
from rasterio.transform import from_origin

from app.domains.forests.processing.frequency_a_loader import (
    FrequencyAMetadata,
    FrequencyAWindow,
    load_frequency_a_window,
)
from app.domains.forests.processing.polarimetric_features import (
    extract_polarimetric_features,
)

ROOT = Path(__file__).resolve().parents[2]
T0_PATH = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
T1_PATH = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"


def create_synthetic_window(
    shape=(20, 20),
    hh0_val=0.1,
    hv0_val=0.01,
    hh1_val=0.1,
    hv1_val=0.01,
    inject_nan=False,
    inject_edge_mask=False,
) -> FrequencyAWindow:
    """Helper to generate a clean synthetic FrequencyAWindow for deterministic unit tests."""
    hh0 = np.full(shape, hh0_val, dtype=np.float32)
    hv0 = np.full(shape, hv0_val, dtype=np.float32)
    hh1 = np.full(shape, hh1_val, dtype=np.float32)
    hv1 = np.full(shape, hv1_val, dtype=np.float32)

    mask0 = np.ones(shape, dtype=np.uint8)
    mask1 = np.ones(shape, dtype=np.uint8)
    ex0 = np.zeros(shape, dtype=np.uint8)
    ex1 = np.zeros(shape, dtype=np.uint8)

    rtc0 = np.full(shape, 0.75, dtype=np.float32)
    rtc1 = np.full(shape, 0.75, dtype=np.float32)

    if inject_nan:
        hh0[0, 0] = np.nan
        hv1[1, 1] = np.nan

    if inject_edge_mask:
        # 255 indicates fill / outside acquisition
        mask0[2, 2] = 255
        # 0 indicates partial / edge anomaly
        mask1[3, 3] = 0

    valid = (
        (mask0 == 1)
        & (mask1 == 1)
        & (ex0 == 0)
        & (ex1 == 0)
        & np.isfinite(hh0)
        & np.isfinite(hv0)
        & np.isfinite(hh1)
        & np.isfinite(hv1)
        & (hh0 > 1e-7)
        & (hv0 > 1e-7)
        & (hh1 > 1e-7)
        & (hv1 > 1e-7)
    )

    meta = FrequencyAMetadata(
        crs="EPSG:32645",
        pixel_spacing_x=10.0,
        pixel_spacing_y=-10.0,
        x_min=400000.0,
        x_max=400200.0,
        y_min=2400000.0,
        y_max=2400200.0,
        transform=from_origin(400000.0, 2400200.0, 10.0, 10.0),
        window_shape=shape,
        t0_scene_id="TEST_T0",
        t1_scene_id="TEST_T1",
        t0_acquisition_time="2026-03-04T23:37:20",
        t1_acquisition_time="2026-04-21T23:37:20",
        track=98,
        frame=12,
        orbit_pass="Ascending",
        processing_crid_t0="P05023",
        processing_crid_t1="P05023",
        center_frequency_hz=1239000000.0,
        range_bandwidth_hz=40000000.0,
        rtc_factor_stats={"rtc_t0_mean": 0.75, "rtc_t1_mean": 0.75, "max_abs_diff": 0.0},
    )

    return FrequencyAWindow(
        metadata=meta,
        gamma0_rtc_hh_t0=hh0,
        gamma0_rtc_hv_t0=hv0,
        gamma0_rtc_hh_t1=hh1,
        gamma0_rtc_hv_t1=hv1,
        mask_t0=mask0,
        mask_t1=mask1,
        exception_mask_t0=ex0,
        exception_mask_t1=ex1,
        rtc_factor_t0=rtc0,
        rtc_factor_t1=rtc1,
        valid_mask=valid,
    )


# TEST 1: Correct Frequency A dataset loading
def test_frequency_a_dataset_loading():
    if not T0_PATH.exists() or not T1_PATH.exists():
        pytest.skip("NISAR L2 GCOV files not present locally")

    # Load a tiny 100m test window
    win = load_frequency_a_window(
        t0_path=T0_PATH,
        t1_path=T1_PATH,
        x_min=420000.0,
        x_max=421000.0,
        y_min=2400000.0,
        y_max=2401000.0,
    )
    assert win.gamma0_rtc_hh_t0.ndim == 2
    assert win.gamma0_rtc_hv_t0.ndim == 2
    assert win.gamma0_rtc_hh_t1.ndim == 2
    assert win.gamma0_rtc_hv_t1.ndim == 2
    assert win.gamma0_rtc_hh_t0.dtype == np.float32


# TEST 2: Correct spatial window extraction
def test_spatial_window_extraction():
    if not T0_PATH.exists():
        pytest.skip("NISAR L2 GCOV file not present locally")

    win = load_frequency_a_window(
        t0_path=T0_PATH,
        t1_path=T1_PATH,
        x_min=410000.0,
        x_max=411000.0,
        y_min=2390000.0,
        y_max=2391000.0,
    )
    # 1000m span with 10m spacing should yield 100 pixels in each axis
    assert win.metadata.window_shape == (100, 100)
    assert win.gamma0_rtc_hh_t0.shape == (100, 100)


# TEST 3: Matching t0/t1 coordinates
def test_matching_t0_t1_coordinates():
    if not T0_PATH.exists():
        pytest.skip("NISAR L2 GCOV file not present locally")

    win = load_frequency_a_window(
        t0_path=T0_PATH,
        t1_path=T1_PATH,
        x_min=415000.0,
        x_max=416000.0,
        y_min=2395000.0,
        y_max=2396000.0,
    )
    assert win.metadata.pixel_spacing_x == 10.0
    assert win.metadata.pixel_spacing_y == -10.0
    assert win.metadata.crs == "EPSG:32645"


# TEST 4: NaN and fill-value handling
def test_nan_and_fill_value_handling():
    syn_win = create_synthetic_window(inject_nan=True, inject_edge_mask=True)
    features = extract_polarimetric_features(syn_win)

    # Injected NaN at (0, 0) and (1, 1) must be masked out in valid_mask and features
    assert syn_win.valid_mask[0, 0] == False
    assert syn_win.valid_mask[1, 1] == False
    assert np.isnan(features.delta_gamma0_hh_db[0, 0])
    assert np.isnan(features.delta_gamma0_hv_db[1, 1])

    # Edge fill mask (255) at (2, 2) and anomaly (0) at (3, 3) must be excluded
    assert syn_win.valid_mask[2, 2] == False
    assert syn_win.valid_mask[3, 3] == False
    assert np.isnan(features.delta_ratio_hv_hh_db[2, 2])


# TEST 5: RTC factor extraction
def test_rtc_factor_extraction():
    if not T0_PATH.exists():
        pytest.skip("NISAR L2 GCOV file not present locally")

    # Use coordinates inside the valid swath (X around 463000)
    win = load_frequency_a_window(
        t0_path=T0_PATH,
        t1_path=T1_PATH,
        x_min=463000.0,
        x_max=463500.0,
        y_min=2400000.0,
        y_max=2400500.0,
    )
    assert win.rtc_factor_t0.shape == (50, 50)
    assert win.rtc_factor_t1.shape == (50, 50)
    assert "rtc_t0_mean" in win.metadata.rtc_factor_stats
    assert 0.0 < win.metadata.rtc_factor_stats["rtc_t0_mean"] <= 1.0


# TEST 6: Correct HH temporal change calculation
def test_hh_temporal_change_calculation():
    # If HH drops by factor of 2 (from 0.1 to 0.05), ΔHH_dB = 10 * log10(0.05 / 0.1) = -3.0103 dB
    syn_win = create_synthetic_window(hh0_val=0.1, hh1_val=0.05)
    features = extract_polarimetric_features(syn_win)

    expected = 10.0 * np.log10(0.05 / 0.1)
    actual = features.delta_gamma0_hh_db[syn_win.valid_mask]
    assert np.allclose(actual, expected, atol=1e-4)


# TEST 7: Correct HV temporal change calculation
def test_hv_temporal_change_calculation():
    # If HV drops by factor of 4 (from 0.04 to 0.01), ΔHV_dB = 10 * log10(0.01 / 0.04) = -6.0206 dB
    syn_win = create_synthetic_window(hv0_val=0.04, hv1_val=0.01)
    features = extract_polarimetric_features(syn_win)

    expected = 10.0 * np.log10(0.01 / 0.04)
    actual = features.delta_gamma0_hv_db[syn_win.valid_mask]
    assert np.allclose(actual, expected, atol=1e-4)


# TEST 8: Correct HV/HH ratio calculation
def test_hv_hh_ratio_calculation():
    # HV=0.01, HH=0.1 -> R = 10 * log10(0.01 / 0.1) = -10.0 dB
    syn_win = create_synthetic_window(hh0_val=0.1, hv0_val=0.01, hh1_val=0.2, hv1_val=0.04)
    features = extract_polarimetric_features(syn_win)

    expected_r0 = 10.0 * np.log10(0.01 / 0.1)  # -10.0 dB
    expected_r1 = 10.0 * np.log10(0.04 / 0.2)  # -6.9897 dB

    actual_r0 = features.ratio_hv_hh_t0_db[syn_win.valid_mask]
    actual_r1 = features.ratio_hv_hh_t1_db[syn_win.valid_mask]
    assert np.allclose(actual_r0, expected_r0, atol=1e-4)
    assert np.allclose(actual_r1, expected_r1, atol=1e-4)


# TEST 9: Correct temporal ratio difference
def test_temporal_ratio_difference():
    # R0 = -10.0 dB, R1 = -6.9897 dB -> ΔR = +3.0103 dB
    syn_win = create_synthetic_window(hh0_val=0.1, hv0_val=0.01, hh1_val=0.2, hv1_val=0.04)
    features = extract_polarimetric_features(syn_win)

    expected_dr = (10.0 * np.log10(0.04 / 0.2)) - (10.0 * np.log10(0.01 / 0.1))
    actual_dr = features.delta_ratio_hv_hh_db[syn_win.valid_mask]
    assert np.allclose(actual_dr, expected_dr, atol=1e-4)


# TEST 10: Preservation of existing Frequency B baseline
def test_frequency_b_baseline_preservation():
    from app.domains.forests.services.forest_service import ForestAnalysisService

    svc = ForestAnalysisService()
    res = svc.run_analysis(threshold_db=-2.5, min_cluster_pixels=3)

    # Frequency B baseline should remain unaffected
    assert res["study_region"]["name"] == "Similipal Tiger Reserve, Odisha, India"
    assert res["primary_detection"]["threshold_db"] == -2.5
    assert res["primary_detection"]["detected_pixels"] == 107
    assert res["primary_detection"]["detected_area_ha"] == 68.48
    assert res["primary_detection"]["total_forest_pixels"] == 46515
