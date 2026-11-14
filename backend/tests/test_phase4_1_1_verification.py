"""
Project NISAR — Phase 4.1.1 Independent Verification Tests

Unit tests verifying:
1. Native HDF5 Frequency A and Frequency B 8:1 exact nesting and zero coordinate error.
2. Continuous block mean and categorical modal voting 8x8 aggregation accuracy.
3. Exact reconstruction of all three reference evaluation populations and subset containment.
4. Independent 6-way geographical intersection and north-south coordinate extents.
5. Exact confusion matrix counts, error rate disentanglement (FPR vs FDR), and mathematical identities.
"""

import json
import hashlib
from pathlib import Path

import numpy as np
import pytest
import rasterio
import rasterio.features
import h5py
from scipy import stats
from scipy.ndimage import zoom
from shapely.geometry import shape

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = WORKSPACE_ROOT / "data"
RAW_DIR = DATA_DIR / "raw" / "India"
PROCESSED_DIR = DATA_DIR / "processed"
VALIDATION_DIR = PROCESSED_DIR / "validation"
TEMPORAL_DIR = PROCESSED_DIR / "temporal"
OPTICAL_DIR = PROCESSED_DIR / "optical_reference"
DETECTION_DIR = PROCESSED_DIR / "detection"
REF_DIR = DATA_DIR / "reference"
BOUNDARIES_DIR = REF_DIR / "boundaries"

from app.domains.forests.processing.alignment import (
    aggregate_continuous_10m_to_80m,
    aggregate_categorical_10m_to_80m,
)


def compute_sha256(arr: np.ndarray) -> str:
    return hashlib.sha256(arr.tobytes()).hexdigest()


def test_native_hdf5_frequency_a_b_alignment():
    """Verify native NISAR GCOV HDF5 product coordinates have zero error and 8:1 nesting."""
    fpath = RAW_DIR / "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
    assert fpath.exists(), f"HDF5 file missing: {fpath}"

    with h5py.File(fpath, "r") as f:
        gA = f["science/LSAR/GCOV/grids/frequencyA"]
        gB = f["science/LSAR/GCOV/grids/frequencyB"]

        xA, yA = gA["xCoordinates"][:], gA["yCoordinates"][:]
        xB, yB = gB["xCoordinates"][:], gB["yCoordinates"][:]
        dxA, dyA = float(gA["xCoordinateSpacing"][()]), float(gA["yCoordinateSpacing"][()])
        dxB, dyB = float(gB["xCoordinateSpacing"][()]), float(gB["yCoordinateSpacing"][()])

        # Check integer ratio
        assert len(xA) / len(xB) == 8.0
        assert len(yA) / len(yB) == 8.0
        assert dxB / dxA == 8.0
        assert dyB / dyA == 8.0

        # Check outer bounding box alignment
        left_A = xA[0] - dxA / 2.0
        top_A = yA[0] - dyA / 2.0
        left_B = xB[0] - dxB / 2.0
        top_B = yB[0] - dyB / 2.0

        assert left_A == left_B == 361440.0
        assert top_A == top_B == 2467440.0

        # Check pixel center alignment (each Frequency B center must equal mean of 8 Frequency A centers)
        centers_from_A_x = (xA[::8][:len(xB)] + xA[7::8][:len(xB)]) / 2.0
        centers_from_A_y = (yA[::8][:len(yB)] + yA[7::8][:len(yB)]) / 2.0

        max_err_x = float(np.max(np.abs(centers_from_A_x - xB)))
        max_err_y = float(np.max(np.abs(centers_from_A_y - yB)))

        assert max_err_x == 0.0
        assert max_err_y == 0.0


def test_continuous_and_categorical_aggregation():
    """Verify continuous block mean and modal voting aggregation functions."""
    # Test continuous on synthetic block
    block_10m = np.ones((16, 16), dtype=np.float32) * 5.0
    block_10m[0, 0] = np.nan
    agg_cont = aggregate_continuous_10m_to_80m(block_10m)
    assert agg_cont.shape == (2, 2)
    assert np.isclose(agg_cont[0, 0], 5.0)

    # Test categorical modal voting (majority class 4: 40 elements vs 24 elements of 2)
    cat_10m = np.zeros((8, 8), dtype=np.uint8)
    cat_10m[:3, :] = 2  # 24 elements of 2
    cat_10m[3:, :] = 4  # 40 elements of 4
    agg_cat = aggregate_categorical_10m_to_80m(cat_10m)
    assert agg_cat.shape == (1, 1)
    assert agg_cat[0, 0] == 4


def test_evaluation_populations_exact_reconstruction():
    """Verify reconstruction of Population 1, 2, and 3, subset containment, and SHA-256 hashes."""
    with rasterio.open(TEMPORAL_DIR / "freq_a_valid_count.tif") as src:
        sar_vc = src.read(1)
    with rasterio.open(OPTICAL_DIR / "s2_valid_observation_count_10m.tif") as src:
        opt_vc = src.read(1)
    with rasterio.open(OPTICAL_DIR / "s2_optical_reference_labels_10m.tif") as src:
        opt_labels = src.read(1)
        H, W = opt_labels.shape
    with rasterio.open(REF_DIR / "similipal_reference_forest_cover.tif") as src:
        fc_80m = src.read(1)
    with rasterio.open(TEMPORAL_DIR / "freq_a_delta_hv.tif") as src:
        dhv = src.read(1)

    forest_mask_10m = zoom((fc_80m >= 30).astype(np.uint8), (8, 8), order=0).astype(bool)[:H, :W]

    both_valid = (sar_vc == 2) & (opt_vc == 2)
    pop1_mask = both_valid
    pop2_mask = both_valid & forest_mask_10m
    pop3_mask = pop2_mask & np.isin(opt_labels, [1, 2]) & ~np.isnan(dhv)

    # Counts
    assert np.sum(pop1_mask) == 12583546
    assert np.sum(pop2_mask) == 2974668
    assert np.sum(pop3_mask) == 2302966

    # Positives
    assert np.sum(pop1_mask & (opt_labels == 1)) == 43
    assert np.sum(pop2_mask & (opt_labels == 1)) == 43
    assert np.sum(pop3_mask & (opt_labels == 1)) == 43

    # Negatives
    assert np.sum(pop1_mask & (opt_labels == 2)) == 7574034
    assert np.sum(pop2_mask & (opt_labels == 2)) == 2302923
    assert np.sum(pop3_mask & (opt_labels == 2)) == 2302923

    # Subset containment
    assert np.all(pop2_mask[pop3_mask])
    assert np.all(pop1_mask[pop2_mask])

    # SHA-256 hashes
    assert compute_sha256(pop1_mask) == "7af134fa503868d9e83eaf2642cf7c7f6dc8f4cf6dec5d7e6e585b75ae76bbf3"
    assert compute_sha256(pop2_mask) == "56ba1c11cbd2d4adf66f3c03e1f7c6c2204e0d282e69dec342f8c74c5f9da0d6"
    assert compute_sha256(pop3_mask) == "4f322a215b3eb5e1647443494e11fd26163eaf8795e9b412828da5e876caac08"


def test_six_way_geographical_intersection():
    """Verify six-way geographical counts and north-south coordinate bounds."""
    with rasterio.open(OPTICAL_DIR / "s2_optical_reference_labels_10m.tif") as src:
        opt_labels = src.read(1)
        transform_10m = src.transform
        H, W = opt_labels.shape

    with rasterio.open(TEMPORAL_DIR / "freq_a_valid_count.tif") as src:
        sar_vc = src.read(1)

    with open(BOUNDARIES_DIR / "similipal_sanctuary_epsg32645.geojson") as f:
        s_data = json.load(f)
    with open(BOUNDARIES_DIR / "similipal_core_epsg32645.geojson") as f:
        c_data = json.load(f)

    geoms_s = [shape(feat["geometry"]) for feat in s_data["features"]]
    sanctuary_mask = rasterio.features.rasterize([(g, 1) for g in geoms_s], out_shape=(H, W), transform=transform_10m, fill=0, dtype=np.uint8) == 1

    geoms_c = [shape(feat["geometry"]) for feat in c_data["features"]]
    core_mask = rasterio.features.rasterize([(g, 1) for g in geoms_c], out_shape=(H, W), transform=transform_10m, fill=0, dtype=np.uint8) == 1

    buffer_mask = sanctuary_mask & ~core_mask
    outside_mask = ~sanctuary_mask
    swath_mask = (sar_vc == 2)
    opt_cand_mask = (opt_labels == 1)

    c_in = int(np.sum(opt_cand_mask & core_mask & swath_mask))
    c_out = int(np.sum(opt_cand_mask & core_mask & ~swath_mask))
    b_in = int(np.sum(opt_cand_mask & buffer_mask & swath_mask))
    b_out = int(np.sum(opt_cand_mask & buffer_mask & ~swath_mask))
    o_in = int(np.sum(opt_cand_mask & outside_mask & swath_mask))
    o_out = int(np.sum(opt_cand_mask & outside_mask & ~swath_mask))

    assert c_in == 0
    assert c_out == 179
    assert b_in == 0
    assert b_out == 491
    assert o_in == 43
    assert o_out == 470
    assert (c_in + c_out + b_in + b_out + o_in + o_out) == 1183

    # Check coordinates: 43 swath pixels are SOUTH (Y < 2384410 m)
    rows_in, cols_in = np.where(opt_cand_mask & swath_mask)
    ys_in = transform_10m[5] + rows_in * transform_10m[4]
    assert np.all(ys_in < 2385000.0)

    # Check coordinates: 1140 outside pixels
    rows_out, cols_out = np.where(opt_cand_mask & ~swath_mask)
    ys_out = transform_10m[5] + rows_out * transform_10m[4]
    xs_out = transform_10m[2] + cols_out * transform_10m[0]
    assert np.all(ys_out > 2397000.0)

    # Deconstruct relative to swath apex (2,400,690 m) and inclined edge
    n_north_of_apex = np.sum(ys_out > 2400690.0)
    n_within_bbox = np.sum((ys_out >= 2372210.0) & (ys_out <= 2400690.0))
    assert n_north_of_apex == 1082
    assert n_within_bbox == 58

    # All 58 pixels within bbox are north of local swath edge at their Easting
    for r, c, y in zip(rows_out[ys_out <= 2400690.0], cols_out[ys_out <= 2400690.0], ys_out[ys_out <= 2400690.0]):
        col_swath = np.where(sar_vc[:, c] == 2)[0]
        assert len(col_swath) > 0
        local_max_y = transform_10m[5] + col_swath.min() * transform_10m[4]
        assert y > local_max_y, f"Pixel at Y={y} is not north of local swath edge {local_max_y}"


def test_spatial_mapping_coordinate_sample_windows():
    """Verify that Frequency A 8x8 blocks map exactly to Frequency B bounding boxes in sample windows."""
    fpath = RAW_DIR / "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
    with h5py.File(fpath, "r") as f:
        gA = f["science/LSAR/GCOV/grids/frequencyA"]
        gB = f["science/LSAR/GCOV/grids/frequencyB"]
        xA = gA["xCoordinates"][:]
        yA = gA["yCoordinates"][:]
        xB = gB["xCoordinates"][:]
        yB = gB["yCoordinates"][:]

    for rb, cb in [(1000, 1000), (1500, 2000), (2000, 1500), (2500, 2500), (3000, 3000)]:
        xb_c, yb_c = float(xB[cb]), float(yB[rb])
        xb_box = (xb_c - 40.0, xb_c + 40.0)
        yb_box = (yb_c - 40.0, yb_c + 40.0)

        xa_slice = xA[cb * 8 : (cb + 1) * 8]
        ya_slice = yA[rb * 8 : (rb + 1) * 8]
        xa_box = (float(xa_slice[0] - 5.0), float(xa_slice[-1] + 5.0))
        ya_box = (float(ya_slice[-1] - 5.0), float(ya_slice[0] + 5.0))

        assert xa_box == xb_box
        assert ya_box == yb_box


def test_native_frequency_a_b_radiometric_agreement():
    """Verify high static backscatter correlation between Frequency A and B across valid pixels."""
    fpath_0 = RAW_DIR / "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
    with h5py.File(fpath_0, "r") as f0:
        gA0, gB0 = f0["science/LSAR/GCOV/grids/frequencyA"], f0["science/LSAR/GCOV/grids/frequencyB"]
        col_min, col_max = 502, 1281
        row_min, row_max = 834, 1190

        hv_b = gB0["HVHV"][row_min:row_max, col_min:col_max]
        hh_b = gB0["HHHH"][row_min:row_max, col_min:col_max]
        hv_a = gA0["HVHV"][row_min * 8 : row_max * 8, col_min * 8 : col_max * 8]
        hh_a = gA0["HHHH"][row_min * 8 : row_max * 8, col_min * 8 : col_max * 8]

    H_B, W_B = hv_b.shape
    hv_a_agg = np.nanmean(hv_a.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)
    hh_a_agg = np.nanmean(hh_a.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)

    valid = (hv_b > 0) & (hh_b > 0) & (hv_a_agg > 0) & (hh_a_agg > 0) & ~np.isnan(hv_a_agg) & ~np.isnan(hh_a_agg)
    hv_a_db = 10.0 * np.log10(hv_a_agg[valid])
    hv_b_db = 10.0 * np.log10(hv_b[valid])
    hh_a_db = 10.0 * np.log10(hh_a_agg[valid])
    hh_b_db = 10.0 * np.log10(hh_b[valid])

    r_hv = np.corrcoef(hv_a_db, hv_b_db)[0, 1]
    r_hh = np.corrcoef(hh_a_db, hh_b_db)[0, 1]

    assert r_hv > 0.95
    assert r_hh > 0.94
    assert abs(np.mean(hv_a_db - hv_b_db)) < 0.20
    assert abs(np.mean(hh_a_db - hh_b_db)) < 0.20


def test_detector_confusion_matrix_identities():
    """Verify confusion matrix values, FPR vs FDR separation, and mathematical identities."""
    with rasterio.open(OPTICAL_DIR / "s2_optical_reference_labels_10m.tif") as src:
        opt_labels = src.read(1)
        H, W = opt_labels.shape
    with rasterio.open(TEMPORAL_DIR / "freq_a_valid_count.tif") as src:
        sar_vc = src.read(1)
    with rasterio.open(OPTICAL_DIR / "s2_valid_observation_count_10m.tif") as src:
        opt_vc = src.read(1)
    with rasterio.open(REF_DIR / "similipal_reference_forest_cover.tif") as src:
        fc_80m = src.read(1)
    with rasterio.open(TEMPORAL_DIR / "freq_a_delta_hv.tif") as src:
        dhv = src.read(1)
    with rasterio.open(TEMPORAL_DIR / "freq_a_delta_ratio.tif") as src:
        dr = src.read(1)
    with rasterio.open(DETECTION_DIR / "freq_a_robust_zscore_10m.tif") as src:
        z_scores = src.read(1)

    forest_mask_10m = zoom((fc_80m >= 30).astype(np.uint8), (8, 8), order=0).astype(bool)[:H, :W]
    pop3_mask = (sar_vc == 2) & (opt_vc == 2) & forest_mask_10m & np.isin(opt_labels, [1, 2]) & ~np.isnan(dhv)

    y_true = (opt_labels[pop3_mask] == 1)
    dhv_eval = dhv[pop3_mask]
    dr_eval = dr[pop3_mask]
    z_eval = z_scores[pop3_mask]

    # Rule 1: Historical ΔHV <= -2.5 dB
    y_p1 = dhv_eval <= -2.5
    tp1 = int(np.sum(y_true & y_p1))
    fp1 = int(np.sum(~y_true & y_p1))
    fn1 = int(np.sum(y_true & ~y_p1))
    tn1 = int(np.sum(~y_true & ~y_p1))

    assert tp1 == 10
    assert fp1 == 523703
    assert fn1 == 33
    assert tn1 == 1779220

    fpr1 = fp1 / (fp1 + tn1)
    fdr1 = fp1 / (tp1 + fp1)
    spec1 = tn1 / (tn1 + fp1)
    prec1 = tp1 / (tp1 + fp1)

    assert np.isclose(fpr1, 0.22740795)
    assert np.isclose(fdr1, 0.99998090)
    assert np.isclose(fpr1 + spec1, 1.0)
    assert np.isclose(prec1 + fdr1, 1.0)

    # Rule 4: Robust Multi-Feature
    y_p4 = (z_eval <= -2.0) & (dr_eval <= -1.0)
    tp4 = int(np.sum(y_true & y_p4))
    fp4 = int(np.sum(~y_true & y_p4))
    fn4 = int(np.sum(y_true & ~y_p4))
    tn4 = int(np.sum(~y_true & ~y_p4))

    assert tp4 == 0
    assert fp4 == 53836
    assert fn4 == 43
    assert tn4 == 2249087

    fpr4 = fp4 / (fp4 + tn4)
    spec4 = tn4 / (tn4 + fp4)
    assert np.isclose(fpr4, 0.02337725)
    assert np.isclose(spec4, 0.97662275)
    assert np.isclose(fpr4 + spec4, 1.0)


def test_comparison_population_reconciliation():
    """Verify exact sample counts for all-valid (197,385) and forest subset (46,514)."""
    with rasterio.open(REF_DIR / "similipal_reference_forest_cover.tif") as src:
        fc_80m = src.read(1)

    fpath_0 = RAW_DIR / "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
    fpath_1 = RAW_DIR / "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"

    with h5py.File(fpath_0, "r") as f0, h5py.File(fpath_1, "r") as f1:
        gA0, gB0 = f0["science/LSAR/GCOV/grids/frequencyA"], f0["science/LSAR/GCOV/grids/frequencyB"]
        gA1, gB1 = f1["science/LSAR/GCOV/grids/frequencyA"], f1["science/LSAR/GCOV/grids/frequencyB"]
        col_min, col_max = 502, 1281
        row_min, row_max = 834, 1190

        hv_b0 = gB0["HVHV"][row_min:row_max, col_min:col_max]
        hh_b0 = gB0["HHHH"][row_min:row_max, col_min:col_max]
        hv_b1 = gB1["HVHV"][row_min:row_max, col_min:col_max]
        hh_b1 = gB1["HHHH"][row_min:row_max, col_min:col_max]

        hv_a0 = gA0["HVHV"][row_min*8:row_max*8, col_min*8:col_max*8]
        hh_a0 = gA0["HHHH"][row_min*8:row_max*8, col_min*8:col_max*8]
        hv_a1 = gA1["HVHV"][row_min*8:row_max*8, col_min*8:col_max*8]
        hh_a1 = gA1["HHHH"][row_min*8:row_max*8, col_min*8:col_max*8]

    H_B, W_B = hv_b0.shape
    hv_a0_agg = np.nanmean(hv_a0.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)
    hh_a0_agg = np.nanmean(hh_a0.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)
    hv_a1_agg = np.nanmean(hv_a1.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)
    hh_a1_agg = np.nanmean(hh_a1.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)

    val_all = (
        (hv_b0 > 0) & (hv_b1 > 0) & (hh_b0 > 0) & (hh_b1 > 0)
        & (hv_a0_agg > 0) & (hv_a1_agg > 0) & (hh_a0_agg > 0) & (hh_a1_agg > 0)
        & ~np.isnan(hv_a0_agg) & ~np.isnan(hv_a1_agg) & ~np.isnan(hh_a0_agg) & ~np.isnan(hh_a1_agg)
    )

    fc_sub = fc_80m[471:471+H_B, :W_B]
    val_forest = val_all & (fc_sub >= 30)
    val_non_forest = val_all & (fc_sub < 30)

    n_all = int(np.sum(val_all))
    n_forest = int(np.sum(val_forest))
    n_non_forest = int(np.sum(val_non_forest))

    assert n_all == 197385
    assert n_forest in (46514, 46515)
    assert n_forest + n_non_forest == n_all


def test_multiscale_aggregation_monotonic_correlation():
    """Verify that spatial averaging increases temporal change correlation monotonically."""
    fpath_0 = RAW_DIR / "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
    fpath_1 = RAW_DIR / "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"

    with h5py.File(fpath_0, "r") as f0, h5py.File(fpath_1, "r") as f1:
        gA0, gB0 = f0["science/LSAR/GCOV/grids/frequencyA"], f0["science/LSAR/GCOV/grids/frequencyB"]
        gA1, gB1 = f1["science/LSAR/GCOV/grids/frequencyA"], f1["science/LSAR/GCOV/grids/frequencyB"]
        col_min, col_max = 502, 1281
        row_min, row_max = 834, 1190

        hv_b0 = gB0["HVHV"][row_min:row_max, col_min:col_max]
        hv_b1 = gB1["HVHV"][row_min:row_max, col_min:col_max]
        hh_b0 = gB0["HHHH"][row_min:row_max, col_min:col_max]
        hh_b1 = gB1["HHHH"][row_min:row_max, col_min:col_max]

        hv_a0 = gA0["HVHV"][row_min*8:row_max*8, col_min*8:col_max*8]
        hv_a1 = gA1["HVHV"][row_min*8:row_max*8, col_min*8:col_max*8]
        hh_a0 = gA0["HHHH"][row_min*8:row_max*8, col_min*8:col_max*8]
        hh_a1 = gA1["HHHH"][row_min*8:row_max*8, col_min*8:col_max*8]

    H_B, W_B = hv_b0.shape
    hv_a0_80 = np.nanmean(hv_a0.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)
    hv_a1_80 = np.nanmean(hv_a1.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)
    hh_a0_80 = np.nanmean(hh_a0.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)
    hh_a1_80 = np.nanmean(hh_a1.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)

    corrs_hv = []
    corrs_hh = []
    rmses_hv = []

    for k in [1, 2, 4, 8, 16]:
        hk, wk = H_B // k, W_B // k
        def sc(arr):
            c = arr[:hk*k, :wk*k].reshape(hk, k, wk, k).transpose(0, 2, 1, 3).reshape(hk, wk, k*k)
            return np.nanmean(c, axis=2)

        s_hva0, s_hvb0 = sc(hv_a0_80), sc(hv_b0)
        s_hva1, s_hvb1 = sc(hv_a1_80), sc(hv_b1)
        s_hha0, s_hhb0 = sc(hh_a0_80), sc(hh_b0)
        s_hha1, s_hhb1 = sc(hh_a1_80), sc(hh_b1)

        val = (s_hva0 > 0) & (s_hvb0 > 0) & (s_hva1 > 0) & (s_hvb1 > 0) & (s_hha0 > 0) & (s_hhb0 > 0) & (s_hha1 > 0) & (s_hhb1 > 0)
        dhv_a = 10 * np.log10(s_hva1[val]) - 10 * np.log10(s_hva0[val])
        dhv_b = 10 * np.log10(s_hvb1[val]) - 10 * np.log10(s_hvb0[val])
        dhh_a = 10 * np.log10(s_hha1[val]) - 10 * np.log10(s_hha0[val])
        dhh_b = 10 * np.log10(s_hhb1[val]) - 10 * np.log10(s_hhb0[val])

        r_hv, _ = stats.pearsonr(dhv_a, dhv_b)
        r_hh, _ = stats.pearsonr(dhh_a, dhh_b)
        rmse_hv = np.sqrt(np.mean((dhv_a - dhv_b)**2))

        corrs_hv.append(r_hv)
        corrs_hh.append(r_hh)
        rmses_hv.append(rmse_hv)

    # Monotonic rise in correlation
    assert corrs_hv[0] < corrs_hv[1] < corrs_hv[2] < corrs_hv[3] < corrs_hv[4]
    assert corrs_hh[0] < corrs_hh[1] < corrs_hh[2] < corrs_hh[3] < corrs_hh[4]
    # Monotonic decline in RMSE
    assert rmses_hv[0] > rmses_hv[1] > rmses_hv[2] > rmses_hv[3] > rmses_hv[4]
    # Scale endpoints
    assert corrs_hv[0] < 0.20
    assert corrs_hv[-1] > 0.80


def test_dense_forest_delta_hv_significance():
    """Verify that Delta HV correlation in Dense Forest is not statistically significant (p > 0.05)."""
    with rasterio.open(REF_DIR / "similipal_reference_forest_cover.tif") as src:
        fc_80m = src.read(1)

    fpath_0 = RAW_DIR / "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
    fpath_1 = RAW_DIR / "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"

    with h5py.File(fpath_0, "r") as f0, h5py.File(fpath_1, "r") as f1:
        gA0, gB0 = f0["science/LSAR/GCOV/grids/frequencyA"], f0["science/LSAR/GCOV/grids/frequencyB"]
        gA1, gB1 = f1["science/LSAR/GCOV/grids/frequencyA"], f1["science/LSAR/GCOV/grids/frequencyB"]
        col_min, col_max = 502, 1281
        row_min, row_max = 834, 1190

        hv_b0 = gB0["HVHV"][row_min:row_max, col_min:col_max]
        hv_b1 = gB1["HVHV"][row_min:row_max, col_min:col_max]
        hv_a0 = gA0["HVHV"][row_min*8:row_max*8, col_min*8:col_max*8]
        hv_a1 = gA1["HVHV"][row_min*8:row_max*8, col_min*8:col_max*8]

    H_B, W_B = hv_b0.shape
    hv_a0_80 = np.nanmean(hv_a0.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)
    hv_a1_80 = np.nanmean(hv_a1.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)

    fc_sub = fc_80m[471:471+H_B, :W_B]
    val_dense = (fc_sub >= 70) & (hv_b0 > 0) & (hv_b1 > 0) & (hv_a0_80 > 0) & (hv_a1_80 > 0)

    dhv_a = 10 * np.log10(hv_a1_80[val_dense]) - 10 * np.log10(hv_a0_80[val_dense])
    dhv_b = 10 * np.log10(hv_b1[val_dense]) - 10 * np.log10(hv_b0[val_dense])

    r, p = stats.pearsonr(dhv_a, dhv_b)
    assert len(dhv_a) == 1007
    assert r < 0.10
    assert p > 0.05  # p = 0.0668 -> NOT statistically significant
    assert abs(np.mean(dhv_a - dhv_b)) < 0.05  # bias is still near zero (+0.0073 dB)


def test_non_interchangeability_verdict():
    """Verify that pixel-level temporal change agreement is weak, confirming non-interchangeability."""
    fpath_0 = RAW_DIR / "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
    fpath_1 = RAW_DIR / "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"

    with h5py.File(fpath_0, "r") as f0, h5py.File(fpath_1, "r") as f1:
        gA0, gB0 = f0["science/LSAR/GCOV/grids/frequencyA"], f0["science/LSAR/GCOV/grids/frequencyB"]
        gA1, gB1 = f1["science/LSAR/GCOV/grids/frequencyA"], f1["science/LSAR/GCOV/grids/frequencyB"]
        col_min, col_max = 502, 1281
        row_min, row_max = 834, 1190

        hv_b0 = gB0["HVHV"][row_min:row_max, col_min:col_max]
        hv_b1 = gB1["HVHV"][row_min:row_max, col_min:col_max]
        hv_a0 = gA0["HVHV"][row_min*8:row_max*8, col_min*8:col_max*8]
        hv_a1 = gA1["HVHV"][row_min*8:row_max*8, col_min*8:col_max*8]

    H_B, W_B = hv_b0.shape
    hv_a0_80 = np.nanmean(hv_a0.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)
    hv_a1_80 = np.nanmean(hv_a1.reshape(H_B, 8, W_B, 8).transpose(0, 2, 1, 3).reshape(H_B, W_B, 64), axis=2)

    val = (hv_b0 > 0) & (hv_b1 > 0) & (hv_a0_80 > 0) & (hv_a1_80 > 0)
    dhv_a = 10 * np.log10(hv_a1_80[val]) - 10 * np.log10(hv_a0_80[val])
    dhv_b = 10 * np.log10(hv_b1[val]) - 10 * np.log10(hv_b0[val])

    r_native_80m, _ = stats.pearsonr(dhv_a, dhv_b)
    # The correlation at 80 m pixel scale is below 0.25
    assert r_native_80m < 0.25
    # This non-interchangeability is fundamental for single-pixel disturbance detection!

