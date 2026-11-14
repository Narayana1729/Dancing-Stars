"""Comprehensive test suite for Phase 5.0 Software & Architectural Unblocking.

Verifies:
1. Multi-temporal state machine transitions (N=2, N=3, N>=4, elapsed < 180d, missing seasons, missing post-event).
2. Never interpreting missing observations as recovery or permanent loss.
3. Phase 4.2.5 7-class deterministic classification framework (mutually exclusive, exhaustive, desiccation immunity).
4. Decoupled disturbance intensity vs uncertainty index.
5. ML safety invariants and DataSufficiencyError prevention of supervised training.
6. Missing polarization channels routing to Class 7.
7. API transparency for operational vs blocked capabilities.
"""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import DataSufficiencyError
from app.domains.forests.algorithms.change_detector import StatisticalForestDisturbanceDetector
from app.domains.forests.detection.reference_audit import (
    assert_ml_training_permitted,
    audit_reference_label_sufficiency,
)
from app.domains.forests.processing.temporal_analysis.disturbance_indicators import (
    classify_seven_classes,
    evaluate_canopy_recovery,
    evaluate_multi_temporal_state,
    evaluate_tier1_instantaneous_candidate,
    evaluate_tier2_sustained_anomaly,
    evaluate_tier3_persistent_candidate,
)
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Multi-Temporal State Machine Tests
# ---------------------------------------------------------------------------

def test_state_machine_n2_exact_statuses():
    """Verify that under N=2 observations, Tiers 2, 3, and Recovery report explicit blocked statuses."""
    state = evaluate_multi_temporal_state(num_observations=2, elapsed_days=48.0)

    assert state.tier1_status == "AVAILABLE"
    assert state.tier2_status == "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"
    assert state.tier3_status == "UNVERIFIABLE_INSUFFICIENT_TEMPORAL_COVERAGE"
    assert state.recovery_status == "UNVERIFIABLE_NO_POST_EVENT_OBSERVATIONS"

    # Explanations must be explicit and scientifically honest
    assert "2 dates" in state.tier2_reason
    assert "180 days" in state.tier3_reason
    assert "No post-event observations" in state.recovery_reason


def test_state_machine_n3_sustained_anomaly():
    """Verify that under N=3, Tier 2 activates and distinguishes sustained drops from rebound."""
    state = evaluate_multi_temporal_state(num_observations=3, elapsed_days=72.0)
    assert state.tier1_status == "AVAILABLE"
    assert state.tier2_status == "ACTIVE"
    assert state.tier3_status == "UNVERIFIABLE_INSUFFICIENT_TEMPORAL_COVERAGE"
    assert state.recovery_status == "UNVERIFIABLE_NO_POST_EVENT_OBSERVATIONS"

    # Test physical evaluation
    shape = (4, 4)
    dhv_t1 = np.zeros(shape, dtype=np.float32)
    dhv_t2 = np.zeros(shape, dtype=np.float32)
    dratio_t1 = np.zeros(shape, dtype=np.float32)
    valid_3 = np.ones(shape, dtype=bool)

    # Pixel (1, 1): drop at t1 (-3.0 dB), sustained at t2 (-2.5 dB)
    dhv_t1[1, 1] = -3.0
    dhv_t2[1, 1] = -2.5
    dratio_t1[1, 1] = -1.8

    # Pixel (2, 2): drop at t1 (-3.5 dB), but rebounds at t2 (-0.2 dB)
    dhv_t1[2, 2] = -3.5
    dhv_t2[2, 2] = -0.2
    dratio_t1[2, 2] = -2.0

    sustained_mask, status = evaluate_tier2_sustained_anomaly(
        delta_hv_t1_db=dhv_t1,
        delta_hv_t2_db=dhv_t2,
        delta_ratio_t1_db=dratio_t1,
        valid_t0_t1_t2=valid_3,
    )

    assert status == "ACTIVE"
    assert sustained_mask is not None
    assert bool(sustained_mask[1, 1]) is True   # Sustained drop detected
    assert bool(sustained_mask[2, 2]) is False  # Rebound correctly rejected


def test_state_machine_n4_temporal_coverage_and_seasons():
    """Verify Tier 3 requirements: N>=4, elapsed >= 180d, and seasonal coverage."""
    # Sub-case A: N=4 but elapsed < 180 days (e.g. 96 days)
    state_short = evaluate_multi_temporal_state(
        num_observations=4,
        elapsed_days=96.0,
        has_seasonal_coverage=True,
    )
    assert state_short.tier3_status == "UNVERIFIABLE_INSUFFICIENT_TEMPORAL_COVERAGE"
    assert "less than required 180 days" in state_short.tier3_reason

    # Sub-case B: N=4 and elapsed >= 180d, but missing seasonal observations
    state_no_season = evaluate_multi_temporal_state(
        num_observations=4,
        elapsed_days=200.0,
        has_seasonal_coverage=False,
    )
    assert state_no_season.tier3_status == "UNVERIFIABLE_MISSING_SEASONAL_COVERAGE"
    assert "Missing wet-season/monsoon" in state_no_season.tier3_reason

    # Sub-case C: Fully verified multi-seasonal baseline
    state_full = evaluate_multi_temporal_state(
        num_observations=4,
        elapsed_days=210.0,
        has_seasonal_coverage=True,
    )
    assert state_full.tier3_status == "ACTIVE"


def test_canopy_recovery_evaluation():
    """Verify recovery tracking requires post-disturbance repeat passes and never claims recovery from missing data."""
    # N=2: No post-event stack
    rec_n2, status_n2 = evaluate_canopy_recovery(
        post_event_delta_hv_stack=None,
        valid_stack=None,
    )
    assert rec_n2 is None
    assert status_n2 == "UNVERIFIABLE_NO_POST_EVENT_OBSERVATIONS"

    # Insufficient post-event observations (e.g. only 1 pass)
    shape = (3, 3)
    rec_short, status_short = evaluate_canopy_recovery(
        post_event_delta_hv_stack=[np.ones(shape)],
        valid_stack=np.ones((1, 3, 3), dtype=bool),
        min_post_event_epochs=3,
    )
    assert rec_short is None
    assert status_short == "UNVERIFIABLE_NO_POST_EVENT_OBSERVATIONS"

    # Genuine post-event monitoring (3 cycles) with sustained backscatter rebound (+2.0 dB)
    post_stack = [
        np.full(shape, 2.0, dtype=np.float32),
        np.full(shape, 1.8, dtype=np.float32),
        np.full(shape, 2.2, dtype=np.float32),
    ]
    prior_disturbance = np.zeros(shape, dtype=bool)
    prior_disturbance[1, 1] = True  # Pixel (1, 1) had prior disturbance

    rec_active, status_active = evaluate_canopy_recovery(
        post_event_delta_hv_stack=post_stack,
        valid_stack=np.ones((3, 3, 3), dtype=bool),
        prior_disturbance_mask=prior_disturbance,
        min_post_event_epochs=3,
        rebound_threshold_db=1.5,
    )
    assert status_active == "ACTIVE"
    assert rec_active is not None
    assert bool(rec_active[1, 1]) is True
    assert bool(rec_active[0, 0]) is False  # Undisturbed pixel cannot "recover"


# ---------------------------------------------------------------------------
# 2. 7-Class Deterministic Classification Framework Tests
# ---------------------------------------------------------------------------

def test_seven_class_mutual_exclusivity_and_exhaustiveness():
    """Verify that every pixel is assigned to exactly one class (1 through 7)."""
    shape = (10, 10)
    dhv = np.full(shape, -0.4, dtype=np.float32)
    dhh = np.full(shape, -0.3, dtype=np.float32)
    dratio = np.full(shape, -0.1, dtype=np.float32)
    valid = np.ones(shape, dtype=bool)

    # Class 3: Strong instantaneous candidate
    dhv[1, 1] = -3.5
    dratio[1, 1] = -2.0

    # Class 2: Potential canopy disturbance (moderate)
    dhv[2, 2] = -2.0
    dratio[2, 2] = -1.0

    # Class 1: Desiccation (equal drying in HH and HV, stable ratio)
    dhh[3, 3] = -2.5
    dhv[3, 3] = -2.5
    dratio[3, 3] = 0.0

    # Class 1: Roughness / moisture infiltration
    dhh[4, 4] = 2.0
    dhv[4, 4] = 0.5

    # Class 6: Ambiguous shift (severe HH drop, HV increase)
    dhh[5, 5] = -3.0
    dhv[5, 5] = 1.0
    dratio[5, 5] = 4.0

    # Class 7: Masked / invalid pixel
    valid[0, 0] = False
    valid[9, 9] = False

    cmap, intensity, uncertainty, summary = classify_seven_classes(
        delta_hh_db=dhh,
        delta_hv_db=dhv,
        delta_ratio_db=dratio,
        valid_intersection=valid,
        num_observations=2,
        elapsed_days=48.0,
    )

    # Exhaustive check: values must be in [1, 7]
    assert np.all(np.isin(cmap, [1, 2, 3, 4, 5, 6, 7]))
    assert summary["total_valid_pixels"] == 98
    assert summary["total_unobserved_pixels"] == 2

    # Verify specific assignments
    assert cmap[1, 1] == 3   # Strong Candidate
    assert cmap[2, 2] == 2   # Potential Disturbance
    assert cmap[3, 3] == 1   # Natural Desiccation (Immunity to false alarm!)
    assert cmap[4, 4] == 1   # Roughness Infiltration
    assert cmap[5, 5] == 6   # Ambiguous Shift
    assert cmap[0, 0] == 7   # Invalid / Masked
    assert cmap[9, 9] == 7   # Invalid / Masked

    # Under N=2, Classes 4 and 5 must have exactly 0 pixels
    assert summary["class_counts"]["class_4_temporally_sustained_anomaly"] == 0
    assert summary["class_counts"]["class_5_long_term_persistent_candidate"] == 0


def test_desiccation_false_positive_immunity():
    """Verify that equal HH and HV drying with stable ratio is classified as Class 1, NOT deforestation."""
    shape = (4, 4)
    # Severe 3.0 dB drop in both polarizations (intense regional heatwave dry-down)
    dhh = np.full(shape, -3.0, dtype=np.float32)
    dhv = np.full(shape, -3.0, dtype=np.float32)
    dratio = np.full(shape, 0.0, dtype=np.float32)  # Ratio stable!
    valid = np.ones(shape, dtype=bool)

    cmap, intensity, uncertainty, _ = classify_seven_classes(
        delta_hh_db=dhh,
        delta_hv_db=dhv,
        delta_ratio_db=dratio,
        valid_intersection=valid,
    )

    # Must be Class 1 (No Significant Change / Seasonality)
    assert np.all(cmap == 1)
    assert np.all(intensity == 0.0)
    assert np.all(uncertainty == 0.05)


def test_missing_polarization_channel_handling():
    """Verify that missing channels (NaNs in HH or HV) route cleanly to Class 7."""
    shape = (3, 3)
    dhh = np.full(shape, -0.5, dtype=np.float32)
    dhv = np.full(shape, -0.5, dtype=np.float32)
    dratio = np.full(shape, 0.0, dtype=np.float32)
    valid = np.ones(shape, dtype=bool)

    # Corrupt channel at (1, 1) with NaN
    dhv[1, 1] = np.nan

    cmap, intensity, uncertainty, summary = classify_seven_classes(
        delta_hh_db=dhh,
        delta_hv_db=dhv,
        delta_ratio_db=dratio,
        valid_intersection=valid,
    )

    assert cmap[1, 1] == 7
    assert np.isnan(intensity[1, 1])
    assert np.isnan(uncertainty[1, 1])
    assert summary["total_unobserved_pixels"] == 1


# ---------------------------------------------------------------------------
# 3. ML Safety & DataSufficiencyError Tests
# ---------------------------------------------------------------------------

def test_ml_safety_guard_raises_datasufficiencyerror():
    """Verify that attempting supervised ML training with inadequate reference samples is blocked."""
    # Under authentic conditions (43 positive samples), assert_ml_training_permitted must raise
    with pytest.raises(DataSufficiencyError) as exc_info:
        assert_ml_training_permitted(
            override_counts={
                "positive_disturbance_pixels": 43,
                "negative_stable_pixels": 7574034,
                "uncertain_pixels": 5009469,
            }
        )

    err = exc_info.value
    assert "Supervised ML training is prohibited by scientific safety policy" in str(err)
    assert err.details["positive_samples"] == 43
    assert err.details["status"] == "BLOCKED_BY_DATA"


def test_ml_safety_guard_permits_when_sufficient():
    """Verify that assert_ml_training_permitted succeeds when diverse samples >= 1000 exist."""
    audit = assert_ml_training_permitted(
        override_counts={
            "positive_disturbance_pixels": 1500,
            "negative_stable_pixels": 500000,
            "uncertain_pixels": 50000,
        }
    )
    assert audit.is_sufficient_for_supervised_ml is True


# ---------------------------------------------------------------------------
# 4. API Endpoints & Transparency Tests
# ---------------------------------------------------------------------------

def test_api_status_endpoint_transparency(client: TestClient):
    """Verify GET /api/v1/forests/status exposes available vs blocked capabilities and observation count."""
    res = client.get("/api/v1/forests/status")
    assert res.status_code == 200
    data = res.json()

    assert data["observation_count"] == 2
    assert data["temporal_baseline_days"] == 48.0
    assert "capabilities_audit" in data
    audit = data["capabilities_audit"]

    # Available
    assert "tier1_instantaneous_candidate_detection" in audit["available_capabilities"]
    assert "seven_class_deterministic_screening" in audit["available_capabilities"]

    # Blocked
    assert "supervised_machine_learning_classifier" in audit["blocked_capabilities"]
    assert audit["blocked_capabilities"]["supervised_machine_learning_classifier"]["status"] == "BLOCKED_BY_DATA"
    assert "multi_temporal_seasonal_reference_baseline" in audit["blocked_capabilities"]


def test_api_capabilities_endpoint(client: TestClient):
    """Verify GET /api/v1/forests/capabilities provides complete unblocking requirements."""
    res = client.get("/api/v1/forests/capabilities")
    assert res.status_code == 200
    data = res.json()

    blocked = data["blocked_capabilities"]
    assert "tier2_temporally_sustained_anomaly_classifier" in blocked
    assert blocked["tier2_temporally_sustained_anomaly_classifier"]["status"] == "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"
    assert "≥ 3 consecutive" in blocked["tier2_temporally_sustained_anomaly_classifier"]["missing_data_requirements"]


def test_api_ml_train_blocked_returns_422(client: TestClient):
    """Verify POST /api/v1/forests/ml/train returns HTTP 422 with DataSufficiencyError details."""
    res = client.post("/api/v1/forests/ml/train")
    assert res.status_code == 422
    data = res.json()

    assert data["error"] == "DataSufficiencyError"
    assert data["status"] == "BLOCKED_BY_DATA"
    assert "prohibited by scientific safety policy" in data["detail"]


def test_api_temporal_metrics_transparency(client: TestClient):
    """Verify GET /api/v1/forests/temporal-metrics includes explicit blocked audit and provenance."""
    res = client.get("/api/v1/forests/temporal-metrics")
    assert res.status_code == 200
    data = res.json()

    dist = data["disturbance_classification"]
    assert dist["tier1_instantaneous"]["status"] in ("ACTIVE_CANDIDATE", "AVAILABLE_ACTIVE_CANDIDATE")
    assert dist["tier2_temporally_sustained"]["status"] in ("UNAVAILABLE_UNVERIFIABLE", "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS")
    assert dist["tier2_temporally_sustained"].get("state") == "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"
    assert dist["tier3_long_term_persistent"].get("state") == "UNVERIFIABLE_INSUFFICIENT_TEMPORAL_COVERAGE"
    assert dist["canopy_recovery"].get("state") == "UNVERIFIABLE_NO_POST_EVENT_OBSERVATIONS"

    assert "blocked_capabilities_audit" in data
    assert "sensor_provenance" in data


def test_detector_seven_class_integration():
    """Verify StatisticalForestDisturbanceDetector runs 7-class framework without regressions."""
    detector = StatisticalForestDisturbanceDetector()
    shape = (8, 8)
    hh0 = np.full(shape, 0.05)
    hv0 = np.full(shape, 0.01)
    hh1 = np.full(shape, 0.05)
    hv1 = np.full(shape, 0.01)

    # Disturbance at (2, 2)
    hv1[2, 2] = 0.002
    hh1[2, 2] = 0.04

    res = detector.classify_seven_classes(
        baseline={"hh": hh0, "hv": hv0},
        target={"hh": hh1, "hv": hv1},
    )

    assert res.classification_map.shape == shape
    assert res.class_counts["class_3_strong_instantaneous_candidate"] >= 1
    assert res.capability_states["tier1"] == "AVAILABLE"
    assert res.capability_states["tier2"] == "UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS"
