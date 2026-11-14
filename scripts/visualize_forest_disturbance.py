#!/usr/bin/env python3
"""Generate a publication-quality 6-panel forest disturbance analysis figure for Similipal."""
from __future__ import annotations

from pathlib import Path
import h5py
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import ListedColormap
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
OUT_PNG = ROOT / "data/processed/india_similipal_forest_disturbance_analysis.png"

P0 = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001.h5"
P1 = ROOT / "data/raw/India/NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"
FOREST_COVER_TIF = ROOT / "data/reference/similipal_reference_forest_cover.tif"
GFC_LOSS_TIF = ROOT / "data/reference/similipal_reference_gfc_loss.tif"

# Frequency B Similipal Reserve slice
Y_SLICE = slice(363, 1190)
X_SLICE = slice(502, 1281)


def main():
    print("Loading NISAR multi-temporal arrays...")
    with h5py.File(P0, "r") as h0, h5py.File(P1, "r") as h1:
        g0 = h0["/science/LSAR/GCOV/grids/frequencyB"]
        g1 = h1["/science/LSAR/GCOV/grids/frequencyB"]

        hh0 = g0["HHHH"][Y_SLICE, X_SLICE]
        hv0 = g0["HVHV"][Y_SLICE, X_SLICE]
        hh1 = g1["HHHH"][Y_SLICE, X_SLICE]
        hv1 = g1["HVHV"][Y_SLICE, X_SLICE]

        x_coords = g0["xCoordinates"][X_SLICE]
        y_coords = g0["yCoordinates"][Y_SLICE]

    with rasterio.open(FOREST_COVER_TIF) as src_tc:
        tree_cover = src_tc.read(1)
        forest_mask = tree_cover >= 30

    with rasterio.open(GFC_LOSS_TIF) as src_loss:
        ref_loss = src_loss.read(1)

    # Valid SAR mask
    eps = 1e-7
    valid = (hh0 > eps) & (hh1 > eps) & (hv0 > eps) & (hv1 > eps)
    valid_forest = valid & forest_mask

    # Decibels
    hh0_db = np.where(valid, 10.0 * np.log10(np.clip(hh0, eps, None)), np.nan)
    hh1_db = np.where(valid, 10.0 * np.log10(np.clip(hh1, eps, None)), np.nan)
    hv0_db = np.where(valid, 10.0 * np.log10(np.clip(hv0, eps, None)), np.nan)
    hv1_db = np.where(valid, 10.0 * np.log10(np.clip(hv1, eps, None)), np.nan)

    delta_hh = hh1_db - hh0_db
    delta_hv = hv1_db - hv0_db

    # Disturbance detection: ΔHV <= -2.5 dB restricted to forest mask
    raw_disturbed = valid_forest & (delta_hv <= -2.5)

    # Apply spatial consistency filter (MMU = 3 pixels = 1.92 ha)
    labeled, num_features = ndimage.label(raw_disturbed)
    sizes = ndimage.sum(raw_disturbed, labeled, range(num_features + 1))
    clean_disturbed = raw_disturbed.copy()
    remove_indices = np.where(sizes < 3)[0]
    clean_disturbed[np.isin(labeled, remove_indices)] = False

    # SAR Disturbance Index (SDI): (hv0 - hv1) / (hv0 + hv1)
    sdi = np.where(valid_forest, (hv0 - hv1) / (hv0 + hv1 + 1e-9), np.nan)

    extent = [x_coords[0] / 1000, x_coords[-1] / 1000, y_coords[-1] / 1000, y_coords[0] / 1000]

    fig, axes = plt.subplots(2, 3, figsize=(19, 12), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    # Panel 1: t0 HV
    ax1 = axes[0, 0]
    ax1.set_facecolor("#111827")
    im1 = ax1.imshow(hv0_db, extent=extent, cmap="viridis", vmin=-30, vmax=-16, origin="upper")
    ax1.set_title("1. Baseline HV Volume Scattering\n(t₀: 2026-03-04)", color="white", fontsize=11, fontweight="bold")
    cb1 = fig.colorbar(im1, ax=ax1, shrink=0.75, pad=0.03)
    cb1.set_label("σ°_HV (dB)", color="white", fontsize=9)
    cb1.ax.tick_params(colors="#9ca3af")

    # Panel 2: t1 HV
    ax2 = axes[0, 1]
    ax2.set_facecolor("#111827")
    im2 = ax2.imshow(hv1_db, extent=extent, cmap="viridis", vmin=-30, vmax=-16, origin="upper")
    ax2.set_title("2. Repeat HV Volume Scattering\n(t₁: 2026-04-21, +48d)", color="white", fontsize=11, fontweight="bold")
    cb2 = fig.colorbar(im2, ax=ax2, shrink=0.75, pad=0.03)
    cb2.set_label("σ°_HV (dB)", color="white", fontsize=9)
    cb2.ax.tick_params(colors="#9ca3af")

    # Panel 3: ΔHH change map
    ax3 = axes[0, 2]
    ax3.set_facecolor("#111827")
    im3 = ax3.imshow(delta_hh, extent=extent, cmap="RdBu_r", vmin=-5, vmax=5, origin="upper")
    ax3.set_title("3. ΔHH Co-Pol Change Map\n(t₁ − t₀: Surface / Double-Bounce)", color="white", fontsize=11, fontweight="bold")
    cb3 = fig.colorbar(im3, ax=ax3, shrink=0.75, pad=0.03)
    cb3.set_label("Δσ°_HH (dB)", color="white", fontsize=9)
    cb3.ax.tick_params(colors="#9ca3af")

    # Panel 4: ΔHV change map
    ax4 = axes[1, 0]
    ax4.set_facecolor("#111827")
    im4 = ax4.imshow(delta_hv, extent=extent, cmap="PuOr", vmin=-4, vmax=4, origin="upper")
    ax4.set_title("4. ΔHV Volume Scattering Change\n(t₁ − t₀: Negative Drop = Canopy Loss)", color="white", fontsize=11, fontweight="bold")
    cb4 = fig.colorbar(im4, ax=ax4, shrink=0.75, pad=0.03)
    cb4.set_label("Δσ°_HV (dB)", color="white", fontsize=9)
    cb4.ax.tick_params(colors="#9ca3af")

    # Panel 5: Forest Mask & Detected Disturbance Regions
    ax5 = axes[1, 1]
    ax5.set_facecolor("#111827")
    # Base tree canopy layer (grayscale green)
    tc_display = np.where(tree_cover > 0, tree_cover, np.nan)
    ax5.imshow(tc_display, extent=extent, cmap="Greens", vmin=0, vmax=100, origin="upper", alpha=0.55)

    # Highlight detected disturbance in vivid orange/red
    disturbed_display = np.where(clean_disturbed, 1.0, np.nan)
    disturbed_cmap = ListedColormap(["#ef4444"])
    ax5.imshow(disturbed_display, extent=extent, cmap=disturbed_cmap, origin="upper", zorder=3)
    ax5.set_title("5. Detected Forest Canopy Disturbance\n(ΔHV ≤ −2.5 dB, MMU ≥ 1.92 ha)", color="white", fontsize=11, fontweight="bold")
    # Add dummy legend patches
    ax5.plot([], [], color="#22c55e", linewidth=4, label="Reference Forest (≥30% Canopy)")
    ax5.plot([], [], color="#ef4444", linewidth=4, label="NISAR Disturbance Clusters")
    ax5.legend(loc="lower right", facecolor="#1f2937", edgecolor="#374151", labelcolor="white", fontsize=8)

    # Panel 6: Disturbance Severity & Reference Validation
    ax6 = axes[1, 2]
    ax6.set_facecolor("#111827")
    im6 = ax6.imshow(sdi, extent=extent, cmap="YlOrRd", vmin=-0.2, vmax=0.4, origin="upper")
    ax6.set_title("6. SAR Disturbance Index (SDI) &\nReference Validation", color="white", fontsize=11, fontweight="bold")
    cb6 = fig.colorbar(im6, ax=ax6, shrink=0.75, pad=0.03)
    cb6.set_label("SDI [(HV₀ − HV₁) / (HV₀ + HV₁)]", color="white", fontsize=9)
    cb6.ax.tick_params(colors="#9ca3af")

    # Overlay historical reference loss points (Hansen GFC)
    loss_y, loss_x = np.where((ref_loss > 0) & valid_forest)
    if len(loss_x) > 0:
        loss_x_coords = (x_coords[0] + loss_x * 80.0) / 1000
        loss_y_coords = (y_coords[0] - loss_y * 80.0) / 1000
        ax6.scatter(loss_x_coords, loss_y_coords, s=8, color="#38bdf8", alpha=0.8, label="Hansen Historical Loss", zorder=4)
        ax6.legend(loc="lower right", facecolor="#1f2937", edgecolor="#374151", labelcolor="white", fontsize=8)

    # Common styling
    for ax in axes.flat:
        ax.set_xlabel("UTM 45N Easting (km)", color="#9ca3af", fontsize=8)
        ax.set_ylabel("UTM 45N Northing (km)", color="#9ca3af", fontsize=8)
        ax.tick_params(colors="#9ca3af", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#374151")

    fig.suptitle(
        "NISAR L2 GCOV Forest Canopy Disturbance Analysis — Similipal Tiger Reserve, Odisha, India\n"
        "Multi-Temporal Pair: 2026-03-04 (t₀) to 2026-04-21 (t₁) | Track 98, Frame 12 (Ascending) | 80 m Multi-Looked Grid",
        color="white",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Disturbance analysis figure saved to: {OUT_PNG}")


if __name__ == "__main__":
    main()

