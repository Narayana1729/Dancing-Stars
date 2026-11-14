#!/usr/bin/env python3
"""Scientific Raster Inspection & Quality Control for Indian NISAR GCOV Product.

Granule: Similipal Tiger Reserve, Odisha (Track 98, Frame 12, Ascending)
Extracts: HHHH and HVHV spatial measurements, geospatial metadata, valid pixel QC,
and generates multi-panel scientific raster visualizations with Similipal bounds.
"""
from __future__ import annotations

import json
from pathlib import Path
import h5py
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
INDIA_H5 = (
    ROOT
    / "data"
    / "raw"
    / "India"
    / "NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
)
OUTPUT_IMG = ROOT / "data" / "processed" / "india_similipal_scientific_inspection.png"
OUTPUT_JSON = ROOT / "data" / "reference" / "india_similipal_raster_inspection.json"


def inspect_and_process():
    if not INDIA_H5.exists():
        raise FileNotFoundError(f"Input file not found: {INDIA_H5}")

    print(f"Inspecting Indian GCOV granule: {INDIA_H5.name}")
    print(f"File size: {INDIA_H5.stat().st_size:,} bytes")

    results = {}

    with h5py.File(INDIA_H5, "r") as f:
        # Task 1: Identification & HDF5 Metadata
        ident = f["/science/LSAR/identification"]
        id_info = {}
        for k in ident.keys():
            v = ident[k][()]
            if isinstance(v, bytes):
                v = v.decode("utf-8", errors="replace")
            elif isinstance(v, np.ndarray) and v.dtype.kind in ("S", "U"):
                v = [x.decode("utf-8", errors="replace") if isinstance(x, bytes) else str(x) for x in v]
            elif isinstance(v, np.generic):
                v = v.item()
            id_info[k] = v
        results["identification"] = id_info

        # Task 1 & 2: Grids & Geospatial Metadata
        grids = f["/science/LSAR/GCOV/grids"]
        results["available_frequencies"] = list(grids.keys())

        # Inspect Frequency A
        fg_a = grids["frequencyA"]
        proj_a = fg_a["projection"]
        epsg_a = int(proj_a[()]) if proj_a.shape == () else int(proj_a.attrs.get("epsg_code", 0))
        spatial_ref_a = proj_a.attrs.get("spatial_ref", b"").decode("utf-8", errors="replace")

        shape_a = fg_a["HHHH"].shape
        dx_a = float(fg_a["xCoordinateSpacing"][()])
        dy_a = float(fg_a["yCoordinateSpacing"][()])
        x_a = fg_a["xCoordinates"]
        y_a = fg_a["yCoordinates"]
        extent_a = {
            "x_min": float(x_a[0]),
            "x_max": float(x_a[-1]),
            "y_min": float(y_a[-1]),
            "y_max": float(y_a[0]),
        }

        # Inspect Frequency B (Multi-look 80m channel)
        fg_b = grids["frequencyB"]
        shape_b = fg_b["HHHH"].shape
        dx_b = float(fg_b["xCoordinateSpacing"][()])
        dy_b = float(fg_b["yCoordinateSpacing"][()])
        x_b = fg_b["xCoordinates"][:]
        y_b = fg_b["yCoordinates"][:]
        extent_b = {
            "x_min": float(x_b[0]),
            "x_max": float(x_b[-1]),
            "y_min": float(y_b[-1]),
            "y_max": float(y_b[0]),
        }

        results["geospatial_metadata"] = {
            "epsg": epsg_a,
            "crs_wkt": spatial_ref_a,
            "frequencyA": {
                "shape": list(shape_a),
                "resolution_m": [abs(dx_a), abs(dy_a)],
                "pixel_spacing": [dx_a, dy_a],
                "extent_meters": extent_a,
                "units": fg_a["HHHH"].attrs.get("units", b"1").decode(),
                "fill_value": str(fg_a["HHHH"].attrs.get("_FillValue", "NaN")),
            },
            "frequencyB": {
                "shape": list(shape_b),
                "resolution_m": [abs(dx_b), abs(dy_b)],
                "pixel_spacing": [dx_b, dy_b],
                "extent_meters": extent_b,
                "units": fg_b["HHHH"].attrs.get("units", b"1").decode(),
                "fill_value": str(fg_b["HHHH"].attrs.get("_FillValue", "NaN")),
            },
        }

        # Task 3 & 4: Load Frequency B full arrays for full-scene radiometry and QC
        hh_b = fg_b["HHHH"][:].astype("float32")
        hv_b = fg_b["HVHV"][:].astype("float32")

    # Quality Control
    total_px = hh_b.size
    valid_hh = np.isfinite(hh_b) & (hh_b > 0)
    valid_hv = np.isfinite(hv_b) & (hv_b > 0)
    valid_both = valid_hh & valid_hv

    n_valid = int(np.count_nonzero(valid_both))
    n_invalid = int(total_px - n_valid)
    pct_valid = float(n_valid / total_px * 100)
    pct_nodata = float(n_invalid / total_px * 100)

    # Radiometric statistics (Linear and dB)
    hh_vals = hh_b[valid_both]
    hv_vals = hv_b[valid_both]

    hh_db = 10 * np.log10(hh_vals)
    hv_db = 10 * np.log10(hv_vals)
    ratio_db = hh_db - hv_db  # HH/HV in dB

    def calc_stats(arr):
        return {
            "min": float(np.min(arr)),
            "p01": float(np.percentile(arr, 0.1)),
            "p02": float(np.percentile(arr, 2)),
            "p25": float(np.percentile(arr, 25)),
            "median": float(np.median(arr)),
            "mean": float(np.mean(arr)),
            "p75": float(np.percentile(arr, 75)),
            "p98": float(np.percentile(arr, 98)),
            "p999": float(np.percentile(arr, 99.9)),
            "max": float(np.max(arr)),
            "std": float(np.std(arr)),
        }

    results["quality_control"] = {
        "total_pixels": total_px,
        "valid_pixels": n_valid,
        "invalid_nodata_pixels": n_invalid,
        "valid_percentage": pct_valid,
        "nodata_percentage": pct_nodata,
        "HHHH_dB_distribution": calc_stats(hh_db),
        "HVHV_dB_distribution": calc_stats(hv_db),
        "HH_HV_ratio_dB_distribution": calc_stats(ratio_db),
    }

    # Task 5: Multi-panel Scientific Visualization
    # Full spatial 2D array in dB with Similipal bounding box
    img_hh = np.full_like(hh_b, np.nan)
    img_hv = np.full_like(hv_b, np.nan)
    img_ratio = np.full_like(hh_b, np.nan)
    mask_2d = np.zeros_like(hh_b, dtype=np.uint8)

    img_hh[valid_both] = 10 * np.log10(hh_b[valid_both])
    img_hv[valid_both] = 10 * np.log10(hv_b[valid_both])
    img_ratio[valid_both] = img_hh[valid_both] - img_hv[valid_both]
    mask_2d[valid_both] = 1

    x_km = x_b / 1000.0
    y_km = y_b / 1000.0
    extent_km = [x_km[0], x_km[-1], y_km[-1], y_km[0]]

    # Similipal Bounding Box approximate UTM coordinates:
    # 86.05°E to 86.65°E, 21.45°N to 22.05°N
    # In UTM 45N (central meridian 87°E, close to Similipal):
    # Easting approx 401 km to 464 km; Northing approx 2372 km to 2439 km
    # In the GCOV product's native projection (EPSG:32645):
    # Let's verify Similipal's location in native grid coordinates
    sim_xmin, sim_xmax = 401.0, 464.0
    sim_ymin, sim_ymax = 2372.0, 2439.0

    fig, axes = plt.subplots(2, 2, figsize=(16, 14), sharex=True, sharey=True)

    # 1. HHHH Backscatter
    p2_hh = results["quality_control"]["HHHH_dB_distribution"]["p02"]
    p98_hh = results["quality_control"]["HHHH_dB_distribution"]["p98"]
    im0 = axes[0, 0].imshow(img_hh, cmap="gray", vmin=p2_hh, vmax=p98_hh, extent=extent_km)
    axes[0, 0].set_title(r"(a) Calibrated $\gamma^0_{HHHH}$ Co-Pol Backscatter (dB)", fontsize=11, fontweight="bold")
    axes[0, 0].set_ylabel("UTM Northing (km)", fontsize=10)
    fig.colorbar(im0, ax=axes[0, 0], shrink=0.7, label="dB")

    # 2. HVHV Backscatter
    p2_hv = results["quality_control"]["HVHV_dB_distribution"]["p02"]
    p98_hv = results["quality_control"]["HVHV_dB_distribution"]["p98"]
    im1 = axes[0, 1].imshow(img_hv, cmap="gray", vmin=p2_hv, vmax=p98_hv, extent=extent_km)
    axes[0, 1].set_title(r"(b) Calibrated $\gamma^0_{HVHV}$ Cross-Pol Backscatter (dB)", fontsize=11, fontweight="bold")
    fig.colorbar(im1, ax=axes[0, 1], shrink=0.7, label="dB")

    # 3. HH/HV Ratio
    p2_r = results["quality_control"]["HH_HV_ratio_dB_distribution"]["p02"]
    p98_r = results["quality_control"]["HH_HV_ratio_dB_distribution"]["p98"]
    im2 = axes[1, 0].imshow(img_ratio, cmap="viridis", vmin=p2_r, vmax=p98_r, extent=extent_km)
    axes[1, 0].set_title(r"(c) Polarimetric Ratio ($HH / HV$ in dB)", fontsize=11, fontweight="bold")
    axes[1, 0].set_xlabel("UTM Easting (km)", fontsize=10)
    axes[1, 0].set_ylabel("UTM Northing (km)", fontsize=10)
    fig.colorbar(im2, ax=axes[1, 0], shrink=0.7, label="dB")

    # 4. Valid Pixel Mask & Bounding Box Overlay
    im3 = axes[1, 1].imshow(mask_2d, cmap="Blues_r", vmin=0, vmax=1, extent=extent_km)
    # Overlay Similipal target box if within extent
    if (x_km[0] <= sim_xmin <= x_km[-1]) and (y_km[-1] <= sim_ymin <= y_km[0]):
        import matplotlib.patches as patches
        rect = patches.Rectangle(
            (sim_xmin, sim_ymin),
            sim_xmax - sim_xmin,
            sim_ymax - sim_ymin,
            linewidth=2,
            edgecolor="red",
            facecolor="none",
            linestyle="--",
            label="Similipal Reserve Bounding Box",
        )
        axes[1, 1].add_patch(rect)
        axes[1, 1].legend(loc="upper right", fontsize=9)

    axes[1, 1].set_title(r"(d) Valid Swath Mask & Similipal Forest Extent", fontsize=11, fontweight="bold")
    axes[1, 1].set_xlabel("UTM Easting (km)", fontsize=10)
    fig.colorbar(im3, ax=axes[1, 1], shrink=0.7, ticks=[0, 1], label="0=NoData, 1=Valid")

    granule_name = id_info.get("granuleId", INDIA_H5.stem)
    plt.suptitle(
        f"Scientific Raster Inspection: Indian NISAR L2 GCOV\n"
        f"Granule: {granule_name}\n"
        f"Track 98, Frame 12 (Ascending) | Acquired: {id_info.get('zeroDopplerStartTime', '2026-03-04')} | CRS: EPSG:{epsg_a}",
        fontsize=12,
        fontweight="bold",
        y=0.99,
    )
    plt.tight_layout()

    OUTPUT_IMG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_IMG, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved visualization figure to: {OUTPUT_IMG}")

    # Task 6: Reproducibility & Output JSON
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w") as jf:
        json.dump(results, jf, indent=2)
    print(f"Saved raster inspection metadata to: {OUTPUT_JSON}")


if __name__ == "__main__":
    inspect_and_process()

