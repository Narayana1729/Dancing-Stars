"""Unit tests for statistical forest disturbance anomaly detector subsystem."""
import numpy as np
import pytest

from app.domains.forests.detection.detector import (
    CANDIDATE_CATEGORIES,
    DetectionParameters,
    StatisticalDisturbanceDetector,
)
from app.domains.forests.detection.evaluator import (
    evaluate_single_threshold,
    run_threshold_sensitivity_suite,
)
from app.domains.forests.detection.features import (
    compute_robust_forest_statistics,
    compute_robust_z_scores,
    compute_temporal_sar_features,
)
from app.domains.forests.detection.reference_audit import (
    audit_reference_label_sufficiency,
)
from app.domains.forests.detection.spatial_context import (
    filter_by_minimum_mapping_unit,
    get_default_mmu_config,
)


def test_reference_label_audit_stops_calibration():
    """Verify that insufficient positive labels trigger the calibration stop mandate."""
    # Empirical Similipal count: 43 positive pixels out of 12.5M
    audit = audit_reference_label_sufficiency(
        override_counts={
            "positive_disturbance_pixels": 43,
            "negative_stable_pixels": 7574034,
            "uncertain_pixels": 5009469,
        },
        min_required_positive_samples=500,
    )

    assert audit.calibration_stop_mandate is True
    assert audit.is_sufficient_for_calibration is False
    assert audit.is_sufficient_for_supervised_ml is False
    assert "STOP DETECTOR CALIBRATION" in audit.stop_reason
    assert audit.class_imbalance_ratio > 100000.0

    # Test with sufficient hypothetical labels
    audit_ok = audit_reference_label_sufficiency(
        override_counts={
            "positive_disturbance_pixels": 1200,
            "negative_stable_pixels": 500000,
            "uncertain_pixels": 10000,
        },
        min_required_positive_samples=500,
    )
    assert audit_ok.calibration_stop_mandate is False
    assert audit_ok.is_sufficient_for_calibration is True


def test_robust_forest_statistics_outlier_resilience():
    """Verify that Median and MAD resist extreme outliers compared to Mean and Std."""
    # Background forest drying: normally distributed around -1.0 dB with scale 0.5 dB
    rng = np.random.default_rng(42)
    delta_hv = rng.normal(loc=-1.0, scale=0.5, size=(100, 100))
    # Inject 50 catastrophic outlier pixels (-20 dB, e.g. radar shadows or water bodies)
    delta_hv[0, :50] = -20.0

    forest_mask = np.ones((100, 100), dtype=bool)
    valid_mask = np.ones((100, 100), dtype=bool)

    stats = compute_robust_forest_statistics(delta_hv, forest_mask, valid_mask)

    # Median and MAD should remain near -1.0 and 0.5
    assert -1.2 <= stats.median_delta_hv_db <= -0.8
    assert 0.3 <= stats.mad_scale_sigma_db <= 0.7
    # Classic mean should be pulled down by the extreme outliers
    assert stats.mean_delta_hv_db < stats.median_delta_hv_db


def test_robust_z_scores_standardization():
    """Verify that Z_MAD scales anomalies by (val - median) / (1.4826 * MAD)."""
    delta_hv = np.array([[-1.0, -2.0], [-3.0, 0.0]])
    valid_mask = np.ones((2, 2), dtype=bool)

    # median = -1.5, scale = 1.0
    z = compute_robust_z_scores(delta_hv, median_val=-1.5, mad_scale=1.0, valid_mask=valid_mask)
    assert np.isclose(z[0, 0], 0.5)   # (-1.0 - (-1.5)) / 1.0 = +0.5
    assert np.isclose(z[0, 1], -0.5)  # (-2.0 - (-1.5)) / 1.0 = -0.5
    assert np.isclose(z[1, 0], -1.5)  # (-3.0 - (-1.5)) / 1.0 = -1.5
    assert np.isclose(z[1, 1], 1.5)   # (0.0 - (-1.5)) / 1.0 = +1.5


def test_spatial_mmu_filtering_freq_a_and_b():
    """Verify that MMU correctly distinguishes single-look speckle (Freq A) from multi-looked (Freq B)."""
    # Create a 20x20 binary mask with:
    # 1. An isolated 1-pixel noise spike at (2, 2)
    # 2. A 3-pixel cluster at (5, 5:8)
    # 3. A 6-pixel cluster at (10:12, 10:12)
    mask = np.zeros((20, 20), dtype=bool)
    mask[2, 2] = True
    mask[5, 5:8] = True  # 3 pixels
    mask[10:12, 10:13] = True  # 6 pixels

    # Frequency A: MMU = 5 pixels (0.05 ha)
    config_a = get_default_mmu_config("frequencyA")
    assert config_a.min_cluster_pixels == 5
    filtered_a, clusters_a, stats_a = filter_by_minimum_mapping_unit(mask, config_a)
    assert not filtered_a[2, 2]  # 1-pixel noise filtered
    assert not np.any(filtered_a[5, 5:8])  # 3-pixel cluster filtered
    assert np.all(filtered_a[10:12, 10:13])  # 6-pixel cluster retained
    assert clusters_a == 1
    assert stats_a["filtered_sub_mmu_pixels"] == 4

    # Frequency B: MMU = 1 pixel (0.64 ha, multi-looked)
    config_b = get_default_mmu_config("frequencyB")
    assert config_b.min_cluster_pixels == 1
    filtered_b, clusters_b, stats_b = filter_by_minimum_mapping_unit(mask, config_b)
    assert bool(filtered_b[2, 2])  # Preserved because 1 px at 80m is already 0.64 ha
    assert clusters_b == 3


def test_detector_candidate_radiometric_labelling():
    """Verify that detector classifies categories into candidate radiometric changes."""
    # Synthetic 10x10 forest patch
    # Linear backscatter values
    hh0 = np.full((10, 10), 0.05)   # ~ -13 dB
    hv0 = np.full((10, 10), 0.01)   # ~ -20 dB
    hh1 = np.full((10, 10), 0.05)
    hv1 = np.full((10, 10), 0.01)

    # 1. Volume scattering loss: drop in HV from 0.01 to 0.001 (-10 dB drop) in a 6-pixel cluster
    hv1[2:4, 2:5] = 0.001  # 6 pixels

    # 2. Surface shift: equal drop in HH and HV from 0.05->0.01 and 0.01->0.002
    hh1[7:9, 7:10] = 0.01
    hv1[7:9, 7:10] = 0.002

    forest_mask = np.ones((10, 10), dtype=bool)
    valid_mask = np.ones((10, 10), dtype=bool)

    detector = StatisticalDisturbanceDetector(
        frequency="frequencyA",
        params=DetectionParameters(z_mad_threshold=1.5, delta_ratio_threshold_db=1.0, min_baseline_hv_db=-25.0),
    )

    cat_map, z_scores, summary = detector.detect_candidate_changes(
        hh0, hv0, hh1, hv1, forest_mask, valid_mask
    )

    assert summary.total_forest_pixels == 100
    # Detections must be present in category 1 (Candidate Volume Scattering Loss)
    assert summary.detected_candidate_pixels >= 6
    assert cat_map[2, 2] == 1  # Candidate Volume Scattering Loss
    assert CANDIDATE_CATEGORIES[1] == "Candidate Volume Scattering Loss"
    assert CANDIDATE_CATEGORIES[3] == "Stable Radiometric Baseline"


def test_evaluator_metrics_calculation():
    """Verify precision, recall, F1, and false alarm rate formulas."""
    pred_mask = np.array([[True, True], [False, False]])
    ref_labels = np.array([[1, 2], [1, 2]])  # 1=Disturbed, 2=Stable
    eval_mask = np.ones((2, 2), dtype=bool)

    metric = evaluate_single_threshold(
        prediction_mask=pred_mask,
        reference_labels=ref_labels,
        eval_mask=eval_mask,
        threshold_name="Test Threshold",
        threshold_type="test",
        threshold_value=-2.0,
        pixel_area_ha=0.01,
    )

    # (0, 0): Pred True, Ref 1 (Disturbed) -> TP = 1
    # (0, 1): Pred True, Ref 2 (Stable) -> FP = 1
    # (1, 0): Pred False, Ref 1 (Disturbed) -> FN = 1
    # (1, 1): Pred False, Ref 2 (Stable) -> TN = 1
    assert metric.true_positive_pixels == 1
    assert metric.false_positive_pixels == 1
    assert metric.false_negative_pixels == 1
    assert metric.true_negative_pixels == 1
    assert metric.precision == 0.5
    assert metric.recall == 0.5
    assert metric.f1_score == 0.5
    assert metric.false_positive_rate == 0.5
    assert metric.false_discovery_rate == 0.5
    assert metric.specificity == 0.5
    assert metric.false_alarm_percentage == 50.0
