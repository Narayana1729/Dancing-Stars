#!/usr/bin/env python3
"""Generate a publication-grade multi-temporal comparison figure for Similipal (t0 vs t1)."""
from __future__ import annotations

from pathlib import Path
import h5py
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
P0 = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
P1 = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"
OUT_PNG = ROOT / "data/processed/india_similipal_multitemporal_comparison.png"


def main():
    print("Reading Frequency B arrays from t0 and t1...")
    with h5py.File(P0, "r") as h0, h5py.File(P1, "r") as h1:
        g0_b = h0["/science/LSAR/GCOV/grids/frequencyB"]
        g1_b = h1["/science/LSAR/GCOV/grids/frequencyB"]

        hh0 = g0_b["HHHH"][:]
        hh1 = g1_b["HHHH"][:]
        hv0 = g0_b["HVHV"][:]
        hv1 = g1_b["HVHV"][:]

        x_coords = g0_b["xCoordinates"][:]
        y_coords = g0_b["yCoordinates"][:]

    # Convert to dB with clipping
    hh0_db = np.where(np.isnan(hh0), np.nan, 10.0 * np.log10(np.clip(hh0, 1e-7, None)))
    hh1_db = np.where(np.isnan(hh1), np.nan, 10.0 * np.log10(np.clip(hh1, 1e-7, None)))
    hv0_db = np.where(np.isnan(hv0), np.nan, 10.0 * np.log10(np.clip(hv0, 1e-7, None)))
    hv1_db = np.where(np.isnan(hv1), np.nan, 10.0 * np.log10(np.clip(hv1, 1e-7, None)))

    diff_hh = hh1_db - hh0_db
    diff_hv = hv1_db - hv0_db

    extent = [x_coords[0] / 1000, x_coords[-1] / 1000, y_coords[-1] / 1000, y_coords[0] / 1000]

    fig, axes = plt.subplots(2, 3, figsize=(18, 11), constrained_layout=True)
    fig.patch.set_facecolor("#111827")

    panels = [
        (axes[0, 0], hh0_db, "t₀: HH Backscatter (2026-03-04)", "magma", (-26, -6), "dB"),
        (axes[0, 1], hh1_db, "t₁: HH Backscatter (2026-04-21)", "magma", (-26, -6), "dB"),
        (axes[0, 2], diff_hh, "ΔHH (t₁ − t₀: +48 Days)", "RdBu_r", (-6, 6), "Δ dB"),
        (axes[1, 0], hv0_db, "t₀: HV Cross-Pol (2026-03-04)", "viridis", (-32, -14), "dB"),
        (axes[1, 1], hv1_db, "t₁: HV Cross-Pol (2026-04-21)", "viridis", (-32, -14), "dB"),
        (axes[1, 2], diff_hv, "ΔHV (t₁ − t₀: Volume Scattering Change)", "RdBu_r", (-6, 6), "Δ dB"),
    ]

    for ax, data, title, cmap, (vmin, vmax), unit in panels:
        ax.set_facecolor("#1f2937")
        im = ax.imshow(data, extent=extent, cmap=cmap, vmin=vmin, vmax=vmax, origin="upper")
        ax.set_title(title, color="white", fontsize=12, fontweight="bold", pad=8)
        ax.set_xlabel("UTM Zone 45N Easting (km)", color="#9ca3af", fontsize=9)
        ax.set_ylabel("UTM Zone 45N Northing (km)", color="#9ca3af", fontsize=9)
        ax.tick_params(colors="#9ca3af", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#374151")

        cbar = fig.colorbar(im, ax=ax, orientation="vertical", shrink=0.78, pad=0.03)
        cbar.set_label(unit, color="white", fontsize=9)
        cbar.ax.yaxis.set_tick_params(color="#9ca3af")
        plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="#9ca3af", size=8)

    fig.suptitle(
        "NISAR L2 GCOV Multi-temporal SAR Baseline — Similipal Tiger Reserve, India\n"
        "Orbit Track 098, Frame 012 (Ascending) | 12-day Orbital Repeat Cadence (Δt = 48 days) | Software CRID P05023",
        color="white",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Multi-temporal comparison figure saved to: {OUT_PNG}")


if __name__ == "__main__":
    main()

