"""Unit and integration tests for multi-temporal NISAR processing pipeline."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
from rasterio.transform import from_origin

from app.domains.forests.processing.temporal_analysis.metadata import (
    AcquisitionMetadata,
    TemporalSeriesMetadata,
)
from app.domains.forests.processing.temporal_analysis.temporal_features import (
    MultiTemporalFeatures,
    compute_distribution_stats,
    compute_local_spatial_std,
    extract_multitemporal_features,
)
from app.domains.forests.processing.temporal_analysis.temporal_loader import (
    LoadedTemporalSeries,
    NOISE_FLOOR_EPS,
    find_grid_slice,
    load_multitemporal_series,
)

ROOT = Path(__file__).resolve().parents[2]
T0_PATH = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
T1_PATH = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"


def create_synthetic_series(
    shape: tuple[int, int] = (25, 25),
    hh_vals: tuple[float, float] = (0.1, 0.1),
    hv_vals: tuple[float, float] = (0.02, 0.02),
    inject_nan: bool = False,
    inject_mask_fill: bool = False,
) -> LoadedTemporalSeries:
    """Create synthetic LoadedTemporalSeries for deterministic math testing."""
    h0, h1 = hh_vals
    v0, v1 = hv_vals

    hh0 = np.full(shape, h0, dtype=np.float32)
    hv0 = np.full(shape, v0, dtype=np.float32)
    hh1 = np.full(shape, h1, dtype=np.float32)
    hv1 = np.full(shape, v1, dtype=np.float32)

    mask0 = np.ones(shape, dtype=np.uint8)
    mask1 = np.ones(shape, dtype=np.uint8)
    ex0 = np.zeros(shape, dtype=np.uint8)
    ex1 = np.zeros(shape, dtype=np.uint8)

    if inject_nan:
        hh0[0, 0] = np.nan
        hv1[1, 1] = np.nan

    if inject_mask_fill:
        mask0[2, 2] = 255  # Fill value
        ex1[3, 3] = 1     # Instrument exception

    valid0 = (mask0 == 1) & (ex0 == 0) & np.isfinite(hh0) & np.isfinite(hv0) & (hh0 > 1e-7) & (hv0 > 1e-7)
    valid1 = (mask1 == 1) & (ex1 == 0) & np.isfinite(hh1) & np.isfinite(hv1) & (hh1 > 1e-7) & (hv1 > 1e-7)

    hh0_c = np.where(valid0, hh0, np.nan)
    hv0_c = np.where(valid0, hv0, np.nan)
    hh1_c = np.where(valid1, hh1, np.nan)
    hv1_c = np.where(valid1, hv1, np.nan)

    v_count = valid0.astype(np.int16) + valid1.astype(np.int16)
    intersection = (valid0 & valid1)

    acq0 = AcquisitionMetadata(
        granule_id="NISAR_TEST_T0",
        acquisition_time="2026-03-04T23:37:20",
        track=98,
        frame=12,
        orbit_pass="Ascending",
        look_direction="Left",
        crid="P05023",
        frequency_band="frequencyB",
        center_frequency_hz=1293500000.0,
        range_bandwidth_hz=5000000.0,
        near_range_incidence_deg=33.0,
        far_range_incidence_deg=47.2,
        range_resolution_m=30.0,
        azimuth_resolution_m=5.36,
    )
    acq1 = AcquisitionMetadata(
        granule_id="NISAR_TEST_T1",
        acquisition_time="2026-04-21T23:37:20",
        track=98,
        frame=12,
        orbit_pass="Ascending",
        look_direction="Left",
        crid="P05023",
        frequency_band="frequencyB",
        center_frequency_hz=1293500000.0,
        range_bandwidth_hz=5000000.0,
        near_range_incidence_deg=33.0,
        far_range_incidence_deg=47.2,
        range_resolution_m=30.0,
        azimuth_resolution_m=5.36,
    )

    meta = TemporalSeriesMetadata(
        frequency_id="frequencyB",
        nominal_resolution_m=80.0,
        crs="EPSG:32645",
        transform=from_origin(400000.0, 2400000.0, 80.0, 80.0),
        window_shape=shape,
        x_min=400000.0,
        x_max=400000.0 + shape[1] * 80.0,
        y_min=2400000.0 - shape[0] * 80.0,
        y_max=2400000.0,
        acquisitions=[acq0, acq1],
        num_epochs=2,
        baseline_days=[0, 48],
    )

    return LoadedTemporalSeries(
        metadata=meta,
        dates=["2026-03-04", "2026-04-21"],
        hh_linear=[hh0_c, hh1_c],
        hv_linear=[hv0_c, hv1_c],
        native_masks=[mask0, mask1],
        exception_masks=[ex0, ex1],
        valid_masks=[valid0, valid1],
        rtc_factors=[np.ones(shape, dtype=np.float32), np.ones(shape, dtype=np.float32)],
        valid_count_map=v_count,
        intersection_mask=intersection,
    )


def test_synthetic_differential_backscatter_math():
    """Verify exact analytical values for delta HH, delta HV, and cross-ratios."""
    # HH drops from 0.1 to 0.05 (-3.0103 dB)
    # HV drops from 0.04 to 0.01 (-6.0206 dB)
    series = create_synthetic_series(hh_vals=(0.1, 0.05), hv_vals=(0.04, 0.01))
    features = extract_multitemporal_features(series)

    mask = series.intersection_mask
    expected_dhh = 10.0 * np.log10(0.05 / 0.1)
    expected_dhv = 10.0 * np.log10(0.01 / 0.04)
    expected_r0 = 10.0 * np.log10(0.04 / 0.1)
    expected_r1 = 10.0 * np.log10(0.01 / 0.05)
    expected_dratio = expected_r1 - expected_r0

    assert np.allclose(features.delta_hh_db[0][mask], expected_dhh, atol=1e-4)
    assert np.allclose(features.delta_hv_db[0][mask], expected_dhv, atol=1e-4)
    assert np.allclose(features.ratio_hv_hh_db[0][mask], expected_r0, atol=1e-4)
    assert np.allclose(features.ratio_hv_hh_db[1][mask], expected_r1, atol=1e-4)
    assert np.allclose(features.delta_ratio_db[0][mask], expected_dratio, atol=1e-4)


def test_two_point_temporal_variability():
    """Verify that temporal variability equals |delta_hv| / sqrt(2)."""
    series = create_synthetic_series(hv_vals=(0.04, 0.01))
    features = extract_multitemporal_features(series)

    mask = series.intersection_mask
    dhv = 10.0 * np.log10(0.01 / 0.04)
    expected_sigma = np.abs(dhv) / np.sqrt(2.0)

    actual_sigma = features.temporal_std_hv_db[mask]
    assert np.allclose(actual_sigma, expected_sigma, atol=1e-4)


def test_quality_mask_and_fill_value_rejection():
    """Verify that fill values, exceptions, and NaNs are excluded from valid intersection."""
    series = create_synthetic_series(inject_nan=True, inject_mask_fill=True)
    features = extract_multitemporal_features(series)

    inter = features.intersection_mask
    assert not inter[0, 0]  # NaN at HH0
    assert not inter[1, 1]  # NaN at HV1
    assert not inter[2, 2]  # Mask == 255 at t0
    assert not inter[3, 3]  # Exception == 1 at t1

    # In delta arrays, invalid pixels must be NaN
    assert np.isnan(features.delta_hv_db[0][0, 0])
    assert np.isnan(features.delta_hv_db[0][1, 1])
    assert np.isnan(features.delta_hv_db[0][2, 2])
    assert np.isnan(features.delta_hv_db[0][3, 3])


def test_physical_change_regimes_categorization():
    """Test classification of physical scattering regimes."""
    shape = (10, 10)
    series = create_synthetic_series(shape=shape)

    # Modify specific pixels to test different regimes
    # Pixel (0, 0): Stable (dHV = -0.5 dB, dR = -0.2 dB) -> Regime 1
    # Pixel (1, 1): Moisture desiccation (dHH = -2.5 dB, dHV = -2.5 dB, dR = 0.0 dB) -> Regime 2
    # Pixel (2, 2): Surface roughness increase (dHH = +2.0 dB, dHV = +0.5 dB) -> Regime 3
    # Pixel (3, 3): Candidate disturbance (dHV = -4.0 dB, dR = -2.5 dB) -> Regime 4

    series.hh_linear[0][0, 0] = 0.1
    series.hv_linear[0][0, 0] = 0.02
    series.hh_linear[1][0, 0] = 0.1 * 10**(-0.3 / 10)
    series.hv_linear[1][0, 0] = 0.02 * 10**(-0.5 / 10)

    series.hh_linear[0][1, 1] = 0.1
    series.hv_linear[0][1, 1] = 0.02
    series.hh_linear[1][1, 1] = 0.1 * 10**(-2.5 / 10)
    series.hv_linear[1][1, 1] = 0.02 * 10**(-2.5 / 10)

    series.hh_linear[0][2, 2] = 0.1
    series.hv_linear[0][2, 2] = 0.02
    series.hh_linear[1][2, 2] = 0.1 * 10**(2.0 / 10)
    series.hv_linear[1][2, 2] = 0.02 * 10**(0.5 / 10)

    series.hh_linear[0][3, 3] = 0.1
    series.hv_linear[0][3, 3] = 0.02
    series.hh_linear[1][3, 3] = 0.1 * 10**(-1.5 / 10)
    series.hv_linear[1][3, 3] = 0.02 * 10**(-4.0 / 10)

    features = extract_multitemporal_features(series)
    regimes = features.physical_change_regimes

    assert regimes[0, 0] == 1  # Stable
    assert regimes[1, 1] == 2  # Seasonal desiccation
    assert regimes[2, 2] == 3  # Surface roughness
    assert regimes[3, 3] == 4  # Disturbance candidate
    assert features.is_corroborated_disturbance_candidate[3, 3] is True or features.is_corroborated_disturbance_candidate[3, 3] == 1


def test_frequency_b_real_data_loading():
    """Verify authentic NISAR Frequency B loading on Similipal test window."""
    if not T0_PATH.exists() or not T1_PATH.exists():
        pytest.skip("Authentic NISAR raw data not available in data/raw/India/")

    # Window in verified swath coverage (50x50 pixels)
    series = load_multitemporal_series(
        file_paths=[T0_PATH, T1_PATH],
        frequency_key="frequencyB",
        x_min=420000.0,
        x_max=424000.0,
        y_min=2380000.0,
        y_max=2384000.0,
    )

    assert series.metadata.frequency_id == "frequencyB"
    assert series.metadata.nominal_resolution_m == 80.0
    assert series.metadata.num_epochs == 2
    assert len(series.hh_linear) == 2
    assert series.valid_count_map.shape == (50, 50)
    assert np.all(series.valid_count_map <= 2)

    features = extract_multitemporal_features(series)
    assert len(features.delta_hv_db) == 1
    assert features.delta_hv_db[0].shape == (50, 50)
    assert "delta_hv_db" in features.overall_statistics
    stats = features.overall_statistics["delta_hv_db"]
    assert stats.count > 0
    assert -20.0 < stats.mean < 20.0
