"""Tests for Phase 4.2 Task 4.2.1: Multi-Temporal Data Inventory and Feasibility Audit."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]

MATRIX_JSON_PATH = ROOT / "data/processed/validation/phase4_2_1_acquisition_matrix.json"
MATRIX_CSV_PATH = ROOT / "data/processed/validation/phase4_2_1_acquisition_matrix.csv"
FEASIBILITY_JSON_PATH = ROOT / "data/processed/validation/phase4_2_1_feasibility_summary.json"


@pytest.fixture(scope="module")
def audit_data():
    """Load audit deliverables."""
    assert MATRIX_JSON_PATH.exists(), f"Missing {MATRIX_JSON_PATH}"
    assert MATRIX_CSV_PATH.exists(), f"Missing {MATRIX_CSV_PATH}"
    assert FEASIBILITY_JSON_PATH.exists(), f"Missing {FEASIBILITY_JSON_PATH}"

    with open(MATRIX_JSON_PATH, "r", encoding="utf-8") as f:
        matrix = json.load(f)

    with open(FEASIBILITY_JSON_PATH, "r", encoding="utf-8") as f:
        summary = json.load(f)

    return {"matrix": matrix, "summary": summary}


def test_local_satellite_inventory_integrity(audit_data):
    """Verify that all locally downloaded satellite acquisitions are accounted for."""
    summary = audit_data["summary"]
    local_acq = summary["local_acquisitions"]

    # Exactly 3 local NISAR granules (2 India Similipal, 1 Rondonia test scene)
    nisar_scenes = local_acq["local_nisar_scenes"]
    assert len(nisar_scenes) == 3, f"Expected 3 NISAR scenes, got {len(nisar_scenes)}"

    india_nisar = [s for s in nisar_scenes if s["track"] == 98]
    assert len(india_nisar) == 2, "Expected 2 India Similipal scenes"

    t0_scene = [s for s in india_nisar if s["acquisition_date"] == "2026-03-04"][0]
    t1_scene = [s for s in india_nisar if s["acquisition_date"] == "2026-04-21"][0]

    assert t0_scene["cycle"] == "014"
    assert t0_scene["frame"] == 12
    assert t0_scene["orbit_direction"] == "ASCENDING"
    assert t0_scene["sha256"] == "f5bc144e8efc69b00ec0db65a39bf296bbad8479799ae3f4f56dd3b6b0b0a3b3"

    assert t1_scene["cycle"] == "018"
    assert t1_scene["frame"] == 12
    assert t1_scene["orbit_direction"] == "ASCENDING"
    assert t1_scene["sha256"] == "2a2f65730000197fefdbbdbd86b04fdc43c0d1559f08b32c6c41c8734f2b3c8e"

    rondonia_scene = [s for s in nisar_scenes if s["track"] == 109][0]
    assert rondonia_scene["frame"] == 63
    assert rondonia_scene["orbit_direction"] == "DESCENDING"
    assert rondonia_scene["processing_status"] == "RAW_NON_STUDY_AREA"

    # Exactly 4 local Sentinel-2 L2A Zips (2 pre-event March 2, 2 post-event April 16)
    s2_scenes = local_acq["local_sentinel2_scenes"]
    assert len(s2_scenes) == 4, f"Expected 4 local S2 scenes, got {len(s2_scenes)}"

    tiles = {s["tile"] for s in s2_scenes}
    assert tiles == {"T45QVD", "T45QVE"}, "Must cover both southern (T45QVD) and northern (T45QVE) Similipal tiles"

    orbits = {s["relative_orbit"] for s in s2_scenes}
    assert orbits == {"R076"}, "All local S2 zips must share identical relative orbit R076"

    dates = {s["acquisition_date"] for s in s2_scenes}
    assert dates == {"2026-03-02", "2026-04-16"}, "Must be pre-event (March 2) and post-event (April 16)"


def test_temporal_acquisition_matrix_structure_and_order(audit_data):
    """Validate matrix schema, chronological ordering, and inventory classifications."""
    matrix = audit_data["matrix"]
    assert len(matrix) == 286, f"Expected 286 catalogued observations, found {len(matrix)}"

    required_keys = [
        "observation_date",
        "timestamp_utc",
        "sensor",
        "product_type",
        "granule_id",
        "track_or_orbit",
        "frame_or_tile",
        "orbit_direction",
        "cycle_number",
        "inventory_status",
        "is_downloaded_locally",
        "is_scientifically_suitable",
        "scientific_suitability_reason",
    ]

    for row in matrix:
        for k in required_keys:
            assert k in row, f"Row missing required key: {k}"
        assert row["inventory_status"] in {
            "EXTERNAL_CATALOGUE_ONLY",
            "DOWNLOADED_LOCAL_RAW",
            "SUCCESSFULLY_PROCESSED",
        }

    # Verify chronological sorting
    for i in range(len(matrix) - 1):
        d_curr = matrix[i]["observation_date"]
        d_next = matrix[i + 1]["observation_date"]
        assert d_curr <= d_next, f"Matrix not chronologically ordered: {d_curr} > {d_next}"

    # Verify inventory classification counts
    status_counts = {}
    for r in matrix:
        status_counts[r["inventory_status"]] = status_counts.get(r["inventory_status"], 0) + 1

    assert status_counts["EXTERNAL_CATALOGUE_ONLY"] == 279
    assert status_counts["DOWNLOADED_LOCAL_RAW"] == 1
    assert status_counts["SUCCESSFULLY_PROCESSED"] == 6


def test_scientific_feasibility_proof_boundaries(audit_data):
    """Verify that scientific feasibility rigorously adheres to two-date proof boundaries."""
    feasibility = audit_data["summary"]["temporal_feasibility"]["core_objectives_feasibility"]

    # Two-date change detection is feasible with caveats
    assert feasibility["two_date_change_detection"]["feasibility"] == "FEASIBLE_WITH_CAVEATS"
    assert feasibility["two_date_change_detection"]["available_temporal_baseline_days"] == 48

    # Short-term change is infeasible with local data
    assert feasibility["short_term_temporal_change"]["feasibility"] == "INFEASIBLE_WITH_LOCAL_DATA"

    # Persistent disturbance is INFEASIBLE with 2 dates (requires at least 3 epochs)
    assert feasibility["persistent_disturbance_detection"]["feasibility"] == "INFEASIBLE_WITH_TWO_DATES"
    proof_boundary = feasibility["persistent_disturbance_detection"]["proof_boundary"]
    assert "cannot prove persistence" in proof_boundary.lower()

    # Seasonal baseline estimation is infeasible with 2 dates inside a single dry season
    assert feasibility["seasonal_baseline_estimation"]["feasibility"] == "INFEASIBLE_WITH_LOCAL_DATA"

    # Recovery assessment is infeasible because t1 is the latest epoch
    assert feasibility["recovery_assessment"]["feasibility"] == "INFEASIBLE_WITH_LOCAL_DATA"

    # Wildfire impact assessment is partially feasible (retrospective burn scar only)
    assert feasibility["wildfire_impact_assessment"]["feasibility"] == "PARTIALLY_FEASIBLE_POST_EVENT_ONLY"


def test_acquisition_compatibility_rules(audit_data):
    """Test compatibility rules for tracks, frames, orbits, frequencies, and swaths."""
    compat = audit_data["summary"]["acquisition_compatibility"]

    # Track/Frame: Frame 012 covers southern sector; Frame 013 required for northern sector
    tf = compat["track_frame_consistency"]
    assert "COMPATIBLE_FOR_FRAME_012" in tf["status"]
    assert any("30.65%" in s for s in tf["findings"])
    assert any("Frame 013" in s for s in tf["findings"])

    # Orbit pass: Ascending and Descending mixing is strictly prohibited
    orbit = compat["orbit_pass_compatibility"]
    assert orbit["status"] == "STRICT_SEPARATION_MANDATORY"
    assert any("ASCENDING" in s for s in orbit["findings"])
    assert any("DESCENDING" in s for s in orbit["findings"])

    # Frequency: Non-interchangeable
    freq = compat["frequency_compatibility"]
    assert freq["status"] == "NON_INTERCHANGEABLE_VERIFIED"
    assert any("0.178" in s or "0.18" in s for s in freq["findings"])

    # Spatial grid alignment: 10m vs 80m mathematically exact
    grid = compat["spatial_grid_alignment"]
    assert "EXACT_SUB_PIXEL_ALIGNMENT_CONFIRMED" in grid["status"]


def test_pipeline_implementation_gaps_identified(audit_data):
    """Ensure multi-temporal pipeline architectural gaps are documented."""
    gaps_info = audit_data["summary"]["pipeline_implementation_gaps"]["pipeline_architecture_assessment"]
    assert gaps_info["current_state"] == "HARDCODED_TWO_DATE_PAIRWISE_ARCHITECTURE"

    gap_ids = [g["gap_id"] for g in gaps_info["implementation_gaps"]]
    assert "GAP_1_HARDCODED_TWO_DATE_DATA_STRUCTURES" in gap_ids
    assert "GAP_2_HARDCODED_FILE_NAMING_CONVENTIONS" in gap_ids
    assert "GAP_3_ABSENCE_OF_TEMPORAL_CUBE_ABSTRACTION" in gap_ids
    assert "GAP_4_MISNAMED_PERSISTENCE_INDICATOR" in gap_ids


def test_ranked_acquisition_proposals_and_approval_gate(audit_data):
    """Ensure proposed acquisitions are strictly ranked and gated behind user approval."""
    proposals = audit_data["summary"]["ranked_proposals"]
    ranked_list = proposals["ranked_acquisition_proposals"]

    assert len(ranked_list) == 3, "Expected 3 priority packages"
    assert ranked_list[0]["priority_rank"] == 1
    assert "Frame 012" in ranked_list[0]["package_name"]
    assert len(ranked_list[0]["proposed_scenes"]) == 5

    assert ranked_list[1]["priority_rank"] == 2
    assert "Frame 013" in ranked_list[1]["package_name"]
    assert len(ranked_list[1]["proposed_scenes"]) == 2

    assert ranked_list[2]["priority_rank"] == 3
    assert "Sentinel-2" in ranked_list[2]["package_name"]
    assert len(ranked_list[2]["proposed_scenes"]) == 3

    # Confirm user approval gate policy
    gate = proposals["disk_budget_and_gate_policy"]
    assert gate["policy"] == "STRICT_USER_APPROVAL_GATE"
    assert "USER AUTHORIZATION REQUIRED" in gate["enforcement"].upper()
    assert gate["current_available_disk_gib"] > gate["total_all_proposals_gib"]
