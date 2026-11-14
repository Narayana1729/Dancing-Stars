#!/usr/bin/env python3
"""Verify spatial and radiometric compatibility between t0 and t1 Indian NISAR GCOV products."""
from __future__ import annotations

import json
from pathlib import Path
import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
P0 = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
P1 = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"
OUT_JSON = ROOT / "data/reference/india_multitemporal_compatibility.json"


def main():
    print(f"Comparing t0:\n  {P0.name}\nand t1:\n  {P1.name}\n")
    with h5py.File(P0, "r") as h0, h5py.File(P1, "r") as h1:
        g0_a = h0["/science/LSAR/GCOV/grids/frequencyA"]
        g1_a = h1["/science/LSAR/GCOV/grids/frequencyA"]
        g0_b = h0["/science/LSAR/GCOV/grids/frequencyB"]
        g1_b = h1["/science/LSAR/GCOV/grids/frequencyB"]

        # Frequency A checks
        shape_a_t0 = g0_a["HHHH"].shape
        shape_a_t1 = g1_a["HHHH"].shape
        dtype_a_t0 = str(g0_a["HHHH"].dtype)
        dtype_a_t1 = str(g1_a["HHHH"].dtype)
        epsg_t0 = int(g0_a["projection"][()])
        epsg_t1 = int(g1_a["projection"][()])

        dx_a_t0 = float(g0_a["xCoordinateSpacing"][()])
        dx_a_t1 = float(g1_a["xCoordinateSpacing"][()])
        dy_a_t0 = float(g0_a["yCoordinateSpacing"][()])
        dy_a_t1 = float(g1_a["yCoordinateSpacing"][()])

        x0_coords = g0_a["xCoordinates"][:]
        x1_coords = g1_a["xCoordinates"][:]
        y0_coords = g0_a["yCoordinates"][:]
        y1_coords = g1_a["yCoordinates"][:]

        x_coords_match = bool(np.array_equal(x0_coords, x1_coords))
        y_coords_match = bool(np.array_equal(y0_coords, y1_coords))

        # Frequency B checks (quick whole-array stats in RAM)
        shape_b_t0 = g0_b["HHHH"].shape
        shape_b_t1 = g1_b["HHHH"].shape
        dx_b_t0 = float(g0_b["xCoordinateSpacing"][()])
        dx_b_t1 = float(g1_b["xCoordinateSpacing"][()])

        hh_b_t0 = g0_b["HHHH"][:]
        hh_b_t1 = g1_b["HHHH"][:]
        hv_b_t0 = g0_b["HVHV"][:]
        hv_b_t1 = g1_b["HVHV"][:]

        mask0 = ~np.isnan(hh_b_t0)
        mask1 = ~np.isnan(hh_b_t1)
        overlap = mask0 & mask1

        valid_count_t0 = int(np.sum(mask0))
        valid_count_t1 = int(np.sum(mask1))
        overlap_count = int(np.sum(overlap))
        total_pixels = int(mask0.size)

        pct_valid_t0 = float(valid_count_t0 / total_pixels * 100)
        pct_valid_t1 = float(valid_count_t1 / total_pixels * 100)
        pct_overlap_of_t0 = float(overlap_count / valid_count_t0 * 100)

        # Radiometric distribution comparison on overlap (Frequency B)
        hh0_valid = hh_b_t0[overlap]
        hh1_valid = hh_b_t1[overlap]
        hv0_valid = hv_b_t0[overlap]
        hv1_valid = hv_b_t1[overlap]

        hh0_db = 10.0 * np.log10(np.clip(hh0_valid, 1e-7, None))
        hh1_db = 10.0 * np.log10(np.clip(hh1_valid, 1e-7, None))
        hv0_db = 10.0 * np.log10(np.clip(hv0_valid, 1e-7, None))
        hv1_db = 10.0 * np.log10(np.clip(hv1_valid, 1e-7, None))

        diff_hh = hh1_db - hh0_db
        diff_hv = hv1_db - hv0_db

        report = {
            "spatial_compatibility": {
                "identical_grid_definition": shape_a_t0 == shape_a_t1 and x_coords_match and y_coords_match,
                "frequencyA": {
                    "shape_t0": list(shape_a_t0),
                    "shape_t1": list(shape_a_t1),
                    "dtype": dtype_a_t0,
                    "epsg": epsg_t0,
                    "x_spacing_m": dx_a_t0,
                    "y_spacing_m": dy_a_t0,
                    "x_min_m": float(x0_coords[0]),
                    "x_max_m": float(x0_coords[-1]),
                    "y_min_m": float(y0_coords[-1]),
                    "y_max_m": float(y0_coords[0]),
                    "exact_coordinate_match": x_coords_match and y_coords_match,
                },
                "frequencyB": {
                    "shape_t0": list(shape_b_t0),
                    "shape_t1": list(shape_b_t1),
                    "x_spacing_m": dx_b_t0,
                    "total_pixels": total_pixels,
                    "valid_pixels_t0": valid_count_t0,
                    "valid_percent_t0": round(pct_valid_t0, 2),
                    "valid_pixels_t1": valid_count_t1,
                    "valid_percent_t1": round(pct_valid_t1, 2),
                    "coregistered_overlap_pixels": overlap_count,
                    "overlap_percent_of_t0": round(pct_overlap_of_t0, 2),
                },
            },
            "radiometric_summary": {
                "t0_hh_median_db": round(float(np.median(hh0_db)), 2),
                "t1_hh_median_db": round(float(np.median(hh1_db)), 2),
                "t0_hv_median_db": round(float(np.median(hv0_db)), 2),
                "t1_hv_median_db": round(float(np.median(hv1_db)), 2),
                "delta_hh_median_db": round(float(np.median(diff_hh)), 2),
                "delta_hv_median_db": round(float(np.median(diff_hv)), 2),
            },
            "temporal_baseline": {
                "t0_date": "2026-03-04T23:37:20Z",
                "t1_date": "2026-04-21T23:37:20Z",
                "delta_days": 48,
                "orbit_cycles": 4,
                "orbit_cadence_days": 12,
                "track": 98,
                "frame": 12,
                "orbit_direction": "Ascending",
                "software_crid_t0": "P05023",
                "software_crid_t1": "P05023",
            },
        }

        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(report, indent=2))
        print("Verification complete. Results saved to:", OUT_JSON)
        print("\nSummary Results:")
        print(f"  Exact Grid Match: {report['spatial_compatibility']['identical_grid_definition']}")
        print(f"  Shape Freq A: {shape_a_t0} == {shape_a_t1}")
        print(f"  EPSG: {epsg_t0}")
        print(f"  Coordinate array 1-to-1 match: {x_coords_match and y_coords_match}")
        print(f"  Valid pixel overlap: {overlap_count:,} ({pct_overlap_of_t0:.2f}% of t0 footprint)")
        print(f"  Median HH (t0 -> t1): {report['radiometric_summary']['t0_hh_median_db']} dB -> {report['radiometric_summary']['t1_hh_median_db']} dB (Δ = {report['radiometric_summary']['delta_hh_median_db']} dB)")
        print(f"  Median HV (t0 -> t1): {report['radiometric_summary']['t0_hv_median_db']} dB -> {report['radiometric_summary']['t1_hv_median_db']} dB (Δ = {report['radiometric_summary']['delta_hv_median_db']} dB)")


if __name__ == "__main__":
    main()

