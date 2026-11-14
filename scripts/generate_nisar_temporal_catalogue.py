#!/usr/bin/env python3
"""
Generate comprehensive NISAR temporal observation catalogue for Similipal Tiger Reserve.
Phase 4, Task 2: Repeat-pass catalogue search across NASA CMR and ASF DAAC.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import asf_search as asf
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_DIR = ROOT / "data/reference/nisar_catalogue"
BOUNDARIES_DIR = ROOT / "data/reference/boundaries"
CATALOGUE_DIR.mkdir(parents=True, exist_ok=True)

# Candidate dates requested in task prompt
CANDIDATE_DATES = [
    "2026-03-16",
    "2026-04-09",
    "2026-05-03",
    "2026-05-15",
    "2026-05-27",
    "2026-06-20",
]

EXISTING_WORKSPACE_DATES = [
    "2026-03-04",
    "2026-04-21",
]


def load_boundaries():
    with open(BOUNDARIES_DIR / "original/wdpa_similipal_raw_4326.geojson") as f:
        data = json.load(f)

    sanctuary_union = unary_union([shape(feat["geometry"]) for feat in data["features"]])
    core_feat = next(feat for feat in data["features"] if feat["properties"].get("site_id") == 556167801)
    core_geom = shape(core_feat["geometry"])

    # Rectangular AOI in lat/lon
    # UTM 45N bounds: [401600.0, 2372240.0, 463920.0, 2438400.0]
    import pyproj
    transformer = pyproj.Transformer.from_crs("EPSG:32645", "EPSG:4326", always_xy=True)
    p_ll = transformer.transform(401600.0, 2372240.0)
    p_ur = transformer.transform(463920.0, 2438400.0)
    aoi_box = box(p_ll[0], p_ll[1], p_ur[0], p_ur[1])

    return sanctuary_union, core_geom, aoi_box


def search_nisar_gcov():
    print("Searching NASA ASF DAAC for NISAR GCOV products over Similipal...")
    # Bounding polygon covering Similipal and surrounding satellite swath buffer
    wkt = "POLYGON((85.5 21.0, 87.0 21.0, 87.0 22.5, 85.5 22.5, 85.5 21.0))"
    results = asf.search(
        dataset="NISAR",
        processingLevel="GCOV",
        intersectsWith=wkt,
        maxResults=500,
    )
    print(f"Total NISAR GCOV scenes retrieved: {len(results)}")
    return results


def build_catalog(results, sanctuary_geom, core_geom, aoi_geom):
    catalog = []
    for r in results:
        p = r.properties
        g = shape(r.geometry)

        # Spatial overlaps
        sanc_inter = g.intersection(sanctuary_geom)
        core_inter = g.intersection(core_geom)
        aoi_inter = g.intersection(aoi_geom)

        sanc_cov = (sanc_inter.area / sanctuary_geom.area) * 100.0 if not sanctuary_geom.is_empty else 0.0
        core_cov = (core_inter.area / core_geom.area) * 100.0 if not core_geom.is_empty else 0.0
        aoi_cov = (aoi_inter.area / aoi_geom.area) * 100.0 if not aoi_geom.is_empty else 0.0

        # Extract file size for primary HDF5
        bytes_dict = p.get("bytes") or {}
        h5_bytes = None
        h5_filename = None
        if isinstance(bytes_dict, dict):
            for fname, finfo in bytes_dict.items():
                if fname.endswith(".h5") and "QA" not in fname:
                    h5_bytes = finfo.get("bytes")
                    h5_filename = fname
                    break
        elif isinstance(bytes_dict, (int, float)):
            h5_bytes = int(bytes_dict)

        # Parse CRID and processing type from sceneName
        # Example: NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001
        scene_name = p.get("sceneName") or ""
        tokens = scene_name.split("_")
        proc_type = tokens[2] if len(tokens) > 2 else "PR"
        cycle = tokens[4] if len(tokens) > 4 else ""
        crid = tokens[-4] if len(tokens) >= 4 else (p.get("crid") or "UNKNOWN")
        acq_mode = tokens[7] if len(tokens) > 7 else "DHDH"

        item = {
            "scene_id": scene_name,
            "acquisition_date": p.get("startTime")[:10],
            "start_time": p.get("startTime"),
            "stop_time": p.get("stopTime"),
            "track": p.get("pathNumber"),
            "frame": p.get("frameNumber"),
            "orbit_direction": p.get("flightDirection"),
            "cycle_number": cycle,
            "processing_type": proc_type,
            "crid": crid,
            "acquisition_mode": acq_mode,
            "polarizations": "HH+HV",
            "frequency_bands": "Frequency A (10m) + Frequency B (80m)",
            "sanctuary_coverage_percent": round(sanc_cov, 2),
            "core_coverage_percent": round(core_cov, 2),
            "aoi_coverage_percent": round(aoi_cov, 2),
            "h5_file_name": h5_filename or f"{scene_name}.h5",
            "h5_size_bytes": h5_bytes,
            "h5_size_gb": round(h5_bytes / (1024**3), 3) if h5_bytes else None,
            "download_url": p.get("url"),
            "md5sum": p.get("md5sum"),
            "is_workspace_baseline": p.get("startTime")[:10] in EXISTING_WORKSPACE_DATES and p.get("frameNumber") == 12,
            "is_search_target_candidate": p.get("startTime")[:10] in CANDIDATE_DATES,
        }
        catalog.append(item)

    # Sort descending by date, then track, frame
    catalog.sort(key=lambda x: (x["acquisition_date"], x["track"], x["frame"]), reverse=True)
    return catalog


def render_visuals(catalog, sanctuary_geom, core_geom, aoi_geom, raw_results):
    print("Rendering repeat-pass timeline and track coverage comparison maps...")

    # Visual 1: Track Coverage Comparison Map
    fig, axes = plt.subplots(1, 2, figsize=(18, 9), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    # Left: Track Swaths vs Similipal Boundaries
    ax1 = axes[0]
    ax1.set_facecolor("#111827")

    # Plot boundaries
    from shapely.geometry import MultiPolygon, Polygon

    def plot_geom(ax, geom, edge_color, face_color="none", lw=1.5, ls="-", label=None, alpha=1.0):
        if isinstance(geom, Polygon):
            geoms = [geom]
        elif isinstance(geom, MultiPolygon):
            geoms = list(geom.geoms)
        else:
            return
        for i, g in enumerate(geoms):
            xs, ys = g.exterior.xy
            l = label if i == 0 else None
            ax.plot(xs, ys, color=edge_color, lw=lw, ls=ls, label=l, alpha=alpha)
            if face_color != "none":
                ax.fill(xs, ys, color=face_color, alpha=alpha)

    # Plot official sanctuary and core
    plot_geom(ax1, aoi_geom, "#94a3b8", "none", lw=1.2, ls=":", label="Rectangular AOI (4,123 km²)")
    plot_geom(ax1, sanctuary_geom, "#38bdf8", "#0284c7", lw=2.0, alpha=0.3, label="Similipal Sanctuary (2,178 km²)")
    plot_geom(ax1, core_geom, "#fbbf24", "#d97706", lw=2.0, ls="--", alpha=0.4, label="Similipal Core Area CTH (1,224 km²)")

    # Find sample footprints for:
    # 1. Track 098 Frame 012 (Ascending)
    # 2. Track 098 Frame 013 (Ascending)
    # 3. Track 026 Frame 012 (Ascending)
    # 4. Track 120 Frame 078 (Descending)
    sample_swaths = {}
    for r in raw_results:
        p = r.properties
        key = (p.get("pathNumber"), p.get("frameNumber"), p.get("flightDirection"))
        if key not in sample_swaths and key in [
            (98, 12, "ASCENDING"),
            (98, 13, "ASCENDING"),
            (26, 12, "ASCENDING"),
            (120, 78, "DESCENDING"),
        ]:
            sample_swaths[key] = shape(r.geometry)

    colors = {
        (98, 12, "ASCENDING"): ("#ec4899", "Track 098 Frm 012 (Baseline: 14% Sanctuary)"),
        (98, 13, "ASCENDING"): ("#10b981", "Track 098 Frm 013 (Full Coverage: 99.5% Sanctuary)"),
        (26, 12, "ASCENDING"): ("#8b5cf6", "Track 026 Frm 012 (Western Reserve: 51.4%)"),
        (120, 78, "DESCENDING"): ("#f97316", "Track 120 Frm 078 (Descending PM: 69.2%)"),
    }

    for key, geom in sample_swaths.items():
        col, lbl = colors[key]
        plot_geom(ax1, geom, col, col, lw=2.0, alpha=0.15, label=lbl)

    ax1.set_title("NISAR Multi-Track Orbital Swaths over Similipal Tiger Reserve\nComparison of Track 098 (Frames 12 & 13), Track 026, and Track 120", color="#f9fafb", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Longitude (Degrees East)", color="#9ca3af", fontsize=9)
    ax1.set_ylabel("Latitude (Degrees North)", color="#9ca3af", fontsize=9)
    ax1.tick_params(colors="#9ca3af")
    ax1.legend(loc="lower right", facecolor="#1f2937", edgecolor="#374151", labelcolor="#f9fafb", fontsize=8)
    ax1.grid(True, color="#374151", linestyle="--", alpha=0.5)

    # Right: Repeat-pass 12-day Cycle Timeline for Track 098
    ax2 = axes[1]
    ax2.set_facecolor("#111827")

    # Filter Track 098 scenes
    t98_scenes = [c for c in catalog if c["track"] == 98 and c["frame"] == 12]
    # Reverse to chronological
    t98_scenes.sort(key=lambda x: x["acquisition_date"])

    dates = [s["acquisition_date"] for s in t98_scenes]
    covs = [s["sanctuary_coverage_percent"] for s in t98_scenes]
    is_candidate = [s["is_search_target_candidate"] for s in t98_scenes]
    is_base = [s["is_workspace_baseline"] for s in t98_scenes]

    y_pos = np.arange(len(dates))
    bar_colors = []
    for base, cand in zip(is_base, is_candidate):
        if base:
            bar_colors.append("#38bdf8")  # Cyan for existing T0/T1
        elif cand:
            bar_colors.append("#10b981")  # Green for candidate targets
        else:
            bar_colors.append("#64748b")  # Gray for other passes

    bars = ax2.barh(y_pos, covs, color=bar_colors, height=0.65, edgecolor="#111827", lw=1.2)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(dates, color="#9ca3af", fontsize=8.5)
    ax2.set_xlabel("Sanctuary Area Coverage (%)", color="#9ca3af", fontsize=9)
    ax2.set_title("Track 098 Repeat-Pass Acquisition History (12-day Orbit Interval)\nCyan: In Workspace (T0, T1) | Green: Candidate Target Dates | Slate: Archive Passes", color="#f9fafb", fontsize=11, fontweight="bold")
    ax2.tick_params(colors="#9ca3af")
    ax2.grid(True, axis="x", color="#374151", linestyle="--", alpha=0.5)

    for i, (v, c, b) in enumerate(zip(covs, is_candidate, is_base)):
        status_txt = " (IN WORKSPACE)" if b else (" [CANDIDATE TARGET]" if c else "")
        ax2.text(v + 0.8, i, f"{v:.1f}%{status_txt}", va="center", color="#f8fafc", fontsize=7.5, fontweight="bold" if (c or b) else "normal")

    handles2 = [
        mpatches.Patch(color="#38bdf8", label="Existing Workspace Dates (2026-03-04, 2026-04-21)"),
        mpatches.Patch(color="#10b981", label="Candidate Search Target Dates (March-June 2026)"),
        mpatches.Patch(color="#64748b", label="Other Historical / Future Archive Observations"),
    ]
    ax2.legend(handles=handles2, loc="lower right", facecolor="#1f2937", edgecolor="#374151", labelcolor="#f9fafb", fontsize=8)

    map_png = CATALOGUE_DIR / "track_coverage_comparison_map.png"
    plt.savefig(map_png, dpi=300, facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved track coverage comparison map to: {map_png}")


def main():
    sanctuary_geom, core_geom, aoi_geom = load_boundaries()
    raw_results = search_nisar_gcov()
    catalog = build_catalog(raw_results, sanctuary_geom, core_geom, aoi_geom)

    # 1. Save full catalog JSON & CSV
    full_json = CATALOGUE_DIR / "nisar_similipal_full_catalog.json"
    with open(full_json, "w") as f:
        json.dump(catalog, f, indent=2)
    print(f"Saved full catalogue JSON ({len(catalog)} products) to: {full_json}")

    full_csv = CATALOGUE_DIR / "nisar_similipal_full_catalog.csv"
    if catalog:
        keys = list(catalog[0].keys())
        with open(full_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(catalog)
        print(f"Saved full catalogue CSV to: {full_csv}")

    # 2. Filter candidate target scenes (March 16, April 9, May 3, May 15, May 27, June 20)
    candidates = [
        c for c in catalog
        if c["is_search_target_candidate"] and c["track"] == 98
    ]

    candidate_json = CATALOGUE_DIR / "nisar_similipal_candidate_scenes.json"
    with open(candidate_json, "w") as f:
        json.dump(candidates, f, indent=2)
    print(f"Saved candidate scenes JSON ({len(candidates)} scenes) to: {candidate_json}")

    candidate_csv = CATALOGUE_DIR / "nisar_similipal_candidate_scenes.csv"
    if candidates:
        keys = list(candidates[0].keys())
        with open(candidate_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(candidates)
        print(f"Saved candidate scenes CSV to: {candidate_csv}")

    # 3. Disk space and download gate calculations
    total_candidate_bytes = sum(c["h5_size_bytes"] for c in candidates if c["h5_size_bytes"])
    total_candidate_gb = total_candidate_bytes / (1024**3)

    disk_stat = shutil.disk_usage(ROOT)
    avail_disk_gb = disk_stat.free / (1024**3)

    # Transfer times: 100 Mbps (12.5 MB/s) and 500 Mbps (62.5 MB/s)
    time_100mbps_sec = total_candidate_bytes / (12.5 * 1024 * 1024)
    time_500mbps_sec = total_candidate_bytes / (62.5 * 1024 * 1024)

    gate_info = {
        "candidate_scene_count": len(candidates),
        "total_download_bytes": total_candidate_bytes,
        "total_download_gib": round(total_candidate_gb, 2),
        "available_disk_gib": round(avail_disk_gb, 2),
        "disk_free_after_download_gib": round(avail_disk_gb - total_candidate_gb, 2),
        "target_destination": str(ROOT / "data/raw/India/"),
        "estimated_transfer_time_minutes": {
            "at_100_mbps": round(time_100mbps_sec / 60.0, 1),
            "at_500_mbps": round(time_500mbps_sec / 60.0, 1),
        },
        "candidate_product_ids": [c["scene_id"] for c in candidates],
    }

    gate_json = CATALOGUE_DIR / "download_gate_summary.json"
    with open(gate_json, "w") as f:
        json.dump(gate_info, f, indent=2)
    print(f"Saved download gate summary to: {gate_json}")

    # 4. Render visuals
    render_visuals(catalog, sanctuary_geom, core_geom, aoi_geom, raw_results)


if __name__ == "__main__":
    main()

