#!/usr/bin/env python3
"""
Generate comprehensive Sentinel-2 L2A optical validation catalogue for Similipal Tiger Reserve.
Phase 4, Task 3: Independent optical observation search across Copernicus Data Space Ecosystem (CDSE).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import requests
from shapely.geometry import Polygon, MultiPolygon, box, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_DIR = ROOT / "data/reference/sentinel2_catalogue"
BOUNDARIES_DIR = ROOT / "data/reference/boundaries"
CATALOGUE_DIR.mkdir(parents=True, exist_ok=True)

CDSE_ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

# Target NISAR observation dates for optical temporal pairing
NISAR_DATES = {
    "T0": "2026-03-04",
    "T1": "2026-04-21",
    "Candidates": ["2026-03-16", "2026-04-09", "2026-05-03", "2026-05-15", "2026-05-27", "2026-06-20"],
}


def load_boundaries():
    with open(BOUNDARIES_DIR / "original/wdpa_similipal_raw_4326.geojson") as f:
        data = json.load(f)

    sanctuary_union = unary_union([shape(feat["geometry"]) for feat in data["features"]])
    core_feat = next(feat for feat in data["features"] if feat["properties"].get("site_id") == 556167801)
    core_geom = shape(core_feat["geometry"])

    import pyproj
    transformer = pyproj.Transformer.from_crs("EPSG:32645", "EPSG:4326", always_xy=True)
    p_ll = transformer.transform(401600.0, 2372240.0)
    p_ur = transformer.transform(463920.0, 2438400.0)
    aoi_box = box(p_ll[0], p_ll[1], p_ur[0], p_ur[1])

    return sanctuary_union, core_geom, aoi_box


def fetch_all_s2_l2a():
    print("Querying Copernicus Data Space Ecosystem (CDSE) for Sentinel-2 L2A observations...")
    all_items = []
    for tile in ["T45QVE", "T45QVD"]:
        filter_expr = (
            f"Collection/Name eq 'SENTINEL-2' and contains(Name,'{tile}') and "
            f"ContentDate/Start ge 2026-03-01T00:00:00.000Z and ContentDate/Start le 2026-06-30T23:59:59.000Z and "
            f"contains(Name,'MSIL2A')"
        )
        skip = 0
        while True:
            params = {
                "$filter": filter_expr,
                "$expand": "Attributes",
                "$top": 100,
                "$skip": skip,
                "$orderby": "ContentDate/Start asc",
            }
            resp = requests.get(CDSE_ODATA_URL, params=params, timeout=30)
            if resp.status_code != 200:
                print(f"Error fetching {tile}: {resp.status_code} {resp.text[:200]}")
                break
            items = resp.json().get("value", [])
            if not items:
                break
            all_items.extend(items)
            skip += len(items)
            if len(items) < 100:
                break
    print(f"Fetched {len(all_items)} Sentinel-2 L2A scenes from CDSE.")
    return all_items


def parse_and_evaluate(items, sanctuary_geom, core_geom, aoi_geom):
    catalog = []
    for it in items:
        name = it.get("Name", "")
        tokens = name.replace(".SAFE", "").split("_")
        if len(tokens) < 7:
            continue
        satellite = tokens[0]  # S2A, S2B, S2C
        acq_time_str = tokens[2]
        date_str = f"{acq_time_str[:4]}-{acq_time_str[4:6]}-{acq_time_str[6:8]}"
        time_str = f"{acq_time_str[9:11]}:{acq_time_str[11:13]}:{acq_time_str[13:15]}"
        baseline = tokens[3]
        orbit_rel = tokens[4]
        mgrs_tile = tokens[5]

        attrs = {a["Name"]: a["Value"] for a in it.get("Attributes", [])}
        cloud_cover = float(attrs.get("cloudCover", 100.0))
        proc_baseline = attrs.get("processorVersion") or attrs.get("processingBaseline") or baseline

        fp = it.get("GeoFootprint")
        g = shape(fp) if fp else None
        if g:
            s_cov = (g.intersection(sanctuary_geom).area / sanctuary_geom.area) * 100.0
            c_cov = (g.intersection(core_geom).area / core_geom.area) * 100.0
            aoi_cov = (g.intersection(aoi_geom).area / aoi_geom.area) * 100.0
        else:
            s_cov, c_cov, aoi_cov = 0.0, 0.0, 0.0

        content_len = it.get("ContentLength")
        size_gb = round(content_len / (1024**3), 3) if content_len else None

        if cloud_cover < 10.0:
            suitability = "HIGH (Clear / Excellent Optical Quality)"
        elif cloud_cover < 25.0:
            suitability = "MODERATE (Partial Clouds / Usable with Masking)"
        elif cloud_cover < 50.0:
            suitability = "MARGINAL (Substantial Cloud Interference)"
        else:
            suitability = "POOR (Heavy Monsoonal / Convective Overcast)"

        catalog.append({
            "product_id": name,
            "satellite": satellite,
            "acquisition_date": date_str,
            "acquisition_time_utc": time_str,
            "mgrs_tile": mgrs_tile,
            "relative_orbit": orbit_rel,
            "cloud_cover_percent": round(cloud_cover, 2),
            "sanctuary_coverage_percent": round(s_cov, 2),
            "core_coverage_percent": round(c_cov, 2),
            "aoi_coverage_percent": round(aoi_cov, 2),
            "processing_baseline": proc_baseline,
            "product_size_bytes": content_len,
            "product_size_gb": size_gb,
            "suitability": suitability,
            "bands_available": "B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12, SCL",
            "indices_supported": "NDVI=(B08-B04)/(B08+B04), NBR=(B8A-B12)/(B8A+B12), dNBR=NBR_pre-NBR_post",
            "download_url": f"{CDSE_ODATA_URL}({it.get('Id')})/$value",
            "geometry": g,
        })

    seen = set()
    deduped = []
    for c in catalog:
        if c["product_id"] not in seen:
            seen.add(c["product_id"])
            deduped.append(c)

    deduped.sort(key=lambda x: (x["acquisition_date"], x["mgrs_tile"]))
    return deduped


def select_recommended_pairs(catalog):
    qve_scenes = [c for c in catalog if c["mgrs_tile"] == "T45QVE" and c["cloud_cover_percent"] < 25.0]

    # Pre-event: March 1-10, 2026
    pre_candidates = [c for c in qve_scenes if "2026-03-01" <= c["acquisition_date"] <= "2026-03-10"]

    # Post-event: April 15-30, 2026
    post_candidates = [c for c in qve_scenes if "2026-04-15" <= c["acquisition_date"] <= "2026-04-30"]

    # Late dry season / wildfire peak: May 2026
    may_candidates = [c for c in qve_scenes if "2026-05-01" <= c["acquisition_date"] <= "2026-05-25"]

    return {
        "pre_event_nisar_t0": pre_candidates,
        "post_event_nisar_t1": post_candidates,
        "pre_monsoon_wildfire_peak": may_candidates,
    }


def render_visuals(catalog, recommended_pairs, sanctuary_geom, core_geom, aoi_geom):
    print("Rendering Sentinel-2 observation timeline and cloud-quality figures...")
    fig, axes = plt.subplots(2, 1, figsize=(18, 11), constrained_layout=True)
    fig.patch.set_facecolor("#0b0f19")

    # Panel 1: Observation Timeline with Cloud Cover & NISAR Coincidence
    ax1 = axes[0]
    ax1.set_facecolor("#111827")

    qve_items = [c for c in catalog if c["mgrs_tile"] == "T45QVE"]
    dates = [c["acquisition_date"] for c in qve_items]
    clouds = [c["cloud_cover_percent"] for c in qve_items]
    x_indices = np.arange(len(dates))

    colors = []
    for cl in clouds:
        if cl < 10.0:
            colors.append("#10b981")
        elif cl < 25.0:
            colors.append("#38bdf8")
        elif cl < 50.0:
            colors.append("#f59e0b")
        else:
            colors.append("#ef4444")

    bars = ax1.bar(x_indices, clouds, color=colors, width=0.6, edgecolor="#111827")
    ax1.axhline(10.0, color="#10b981", linestyle="--", alpha=0.7, label="Clear Optical Threshold (<10%)")
    ax1.axhline(25.0, color="#f59e0b", linestyle=":", alpha=0.7, label="Usable Threshold (<25%)")

    for i, d in enumerate(dates):
        if d == "2026-03-04":
            ax1.annotate("NISAR T0 Coincidence\n(2026-03-04, 0.0% Cloud)", xy=(i, clouds[i] + 3), xytext=(i - 2, clouds[i] + 25),
                         arrowprops=dict(facecolor="#38bdf8", edgecolor="#ffffff", width=1.5, headwidth=6),
                         color="#38bdf8", fontsize=8.5, fontweight="bold", ha="center")
        elif d == "2026-04-16":
            ax1.annotate("Primary R076 Post-Event\n(2026-04-16, 2.1% Cloud)", xy=(i, clouds[i] + 3), xytext=(i, clouds[i] + 25),
                         arrowprops=dict(facecolor="#ec4899", edgecolor="#ffffff", width=1.5, headwidth=6),
                         color="#ec4899", fontsize=8.5, fontweight="bold", ha="center")

    ax1.set_xticks(x_indices[::2])
    ax1.set_xticklabels(dates[::2], rotation=45, ha="right", color="#9ca3af", fontsize=8)
    ax1.set_ylabel("Cloud Cover Percentage (%)", color="#9ca3af", fontsize=9.5)
    ax1.set_title("1. Sentinel-2 L2A Acquisition Timeline over Similipal (Tile T45QVE: March–June 2026)\nClear Pre-Monsoon Optical Window (March–April) vs. Monsoonal Cloud Buildup (June)", color="#f9fafb", fontsize=11, fontweight="bold")
    ax1.tick_params(colors="#9ca3af")
    ax1.grid(True, axis="y", color="#374151", linestyle="--", alpha=0.5)

    handles1 = [
        mpatches.Patch(color="#10b981", label="Clear Optical Quality (<10% Cloud)"),
        mpatches.Patch(color="#38bdf8", label="Good Quality (<25% Cloud)"),
        mpatches.Patch(color="#f59e0b", label="Marginal (<50% Cloud)"),
        mpatches.Patch(color="#ef4444", label="Heavy Overcast (>50% Cloud)"),
    ]
    ax1.legend(handles=handles1, loc="upper right", facecolor="#1f2937", edgecolor="#374151", labelcolor="#f9fafb", fontsize=8)

    # Panel 2: Monthly Cloud Quality Distribution & Valid Pixels
    ax2 = axes[1]
    ax2.set_facecolor("#111827")

    months = ["March 2026", "April 2026", "May 2026", "June 2026"]
    month_keys = ["2026-03", "2026-04", "2026-05", "2026-06"]

    clear_counts = []
    usable_counts = []
    cloudy_counts = []

    for m in month_keys:
        m_items = [c for c in catalog if c["acquisition_date"].startswith(m) and c["mgrs_tile"] == "T45QVE"]
        clear = sum(1 for c in m_items if c["cloud_cover_percent"] < 10.0)
        usable = sum(1 for c in m_items if 10.0 <= c["cloud_cover_percent"] < 30.0)
        cloudy = sum(1 for c in m_items if c["cloud_cover_percent"] >= 30.0)
        clear_counts.append(clear)
        usable_counts.append(usable)
        cloudy_counts.append(cloudy)

    x = np.arange(len(months))
    width = 0.25

    rects1 = ax2.bar(x - width, clear_counts, width, label="Clear (<10% Cloud)", color="#10b981", edgecolor="#111827")
    rects2 = ax2.bar(x, usable_counts, width, label="Partially Cloudy (10-30% Cloud)", color="#38bdf8", edgecolor="#111827")
    rects3 = ax2.bar(x + width, cloudy_counts, width, label="Overcast / Unusable (>30% Cloud)", color="#ef4444", edgecolor="#111827")

    ax2.set_xticks(x)
    ax2.set_xticklabels(months, color="#9ca3af", fontsize=9.5, fontweight="bold")
    ax2.set_ylabel("Number of Tile T45QVE Acquisitions", color="#9ca3af", fontsize=9.5)
    ax2.set_title("2. Monthly Optical Observation Usability over Similipal Tiger Reserve\nMarch and April Offer the Highest Density of Cloud-Free Validation Imagery", color="#f9fafb", fontsize=11, fontweight="bold")
    ax2.tick_params(colors="#9ca3af")
    ax2.grid(True, axis="y", color="#374151", linestyle="--", alpha=0.5)
    ax2.legend(loc="upper right", facecolor="#1f2937", edgecolor="#374151", labelcolor="#f9fafb", fontsize=8.5)

    for rects in [rects1, rects2, rects3]:
        for rect in rects:
            h = rect.get_height()
            if h > 0:
                ax2.annotate(f"{h}", xy=(rect.get_x() + rect.get_width() / 2, h), xytext=(0, 3),
                             textcoords="offset points", ha="center", va="bottom", color="#f8fafc", fontsize=8.5, fontweight="bold")

    out_png = CATALOGUE_DIR / "sentinel2_observation_timeline.png"
    plt.savefig(out_png, dpi=300, facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved timeline graphic to: {out_png}")

    # Visual 2: Sentinel-2 MGRS Tile Coverage Map
    print("Rendering Sentinel-2 MGRS tile coverage map...")
    fig2, ax = plt.subplots(figsize=(12, 10), constrained_layout=True)
    fig2.patch.set_facecolor("#0b0f19")
    ax.set_facecolor("#111827")

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

    # Plot administrative boundaries
    plot_geom(ax, aoi_geom, "#94a3b8", "none", lw=1.5, ls=":", label="Rectangular AOI (4,123 km²)")
    plot_geom(ax, sanctuary_geom, "#38bdf8", "#0284c7", lw=2.2, alpha=0.35, label="Similipal Wildlife Sanctuary (2,178 km²)")
    plot_geom(ax, core_geom, "#fbbf24", "#d97706", lw=2.2, ls="--", alpha=0.45, label="Similipal Core Area CTH (1,224 km²)")

    # Sample footprints for T45QVE and T45QVD
    sample_qve = next((c["geometry"] for c in catalog if c["mgrs_tile"] == "T45QVE" and c["geometry"] is not None), None)
    sample_qvd = next((c["geometry"] for c in catalog if c["mgrs_tile"] == "T45QVD" and c["geometry"] is not None), None)

    if sample_qve:
        plot_geom(ax, sample_qve, "#10b981", "#10b981", lw=2.0, alpha=0.15, label="MGRS Tile T45QVE (Covers 89.6% Sanctuary / 86.6% Core)")
    if sample_qvd:
        plot_geom(ax, sample_qvd, "#a855f7", "#a855f7", lw=2.0, alpha=0.15, label="MGRS Tile T45QVD (Covers 25.1% Sanctuary / 35.4% Core)")

    ax.set_title("Sentinel-2 MGRS Tile Footprints over Similipal Tiger Reserve\nTile T45QVE and Tile T45QVD Provide 100% Comprehensive Optical Reserve Coverage", color="#f9fafb", fontsize=12, fontweight="bold")
    ax.set_xlabel("Longitude (Degrees East)", color="#9ca3af", fontsize=9.5)
    ax.set_ylabel("Latitude (Degrees North)", color="#9ca3af", fontsize=9.5)
    ax.tick_params(colors="#9ca3af")
    ax.legend(loc="lower right", facecolor="#1f2937", edgecolor="#374151", labelcolor="#f9fafb", fontsize=9)
    ax.grid(True, color="#374151", linestyle="--", alpha=0.5)

    cov_png = CATALOGUE_DIR / "sentinel2_tile_coverage_map.png"
    plt.savefig(cov_png, dpi=300, facecolor=fig2.get_facecolor())
    plt.close()
    print(f"Saved tile coverage map to: {cov_png}")


def main():
    sanctuary_geom, core_geom, aoi_geom = load_boundaries()
    items = fetch_all_s2_l2a()
    catalog = parse_and_evaluate(items, sanctuary_geom, core_geom, aoi_geom)

    # 1. Save Full Catalogue JSON & CSV (excluding shapely geometry object from json dump)
    serializable_catalog = [{k: v for k, v in c.items() if k != "geometry"} for c in catalog]

    full_json = CATALOGUE_DIR / "sentinel2_similipal_full_catalog.json"
    with open(full_json, "w") as f:
        json.dump(serializable_catalog, f, indent=2)
    print(f"Saved full Sentinel-2 catalogue JSON ({len(serializable_catalog)} scenes) to: {full_json}")

    full_csv = CATALOGUE_DIR / "sentinel2_similipal_full_catalog.csv"
    if serializable_catalog:
        keys = list(serializable_catalog[0].keys())
        with open(full_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(serializable_catalog)
        print(f"Saved full Sentinel-2 catalogue CSV to: {full_csv}")

    # 2. Select Recommended Pairs
    rec_pairs = select_recommended_pairs(serializable_catalog)
    rec_json = CATALOGUE_DIR / "sentinel2_recommended_pairs.json"
    with open(rec_json, "w") as f:
        json.dump(rec_pairs, f, indent=2)
    print(f"Saved recommended pairs JSON to: {rec_json}")

    # 3. Render Visual Timeline and Usability
    render_visuals(catalog, rec_pairs, sanctuary_geom, core_geom, aoi_geom)

    # 4. Download Gate Audit Summary
    # Recommended Primary Reference Pair on Relative Orbit R076:
    # Pre-event: 2026-03-02 (T45QVE & T45QVD) - Identical Orbit R076
    # Post-event: 2026-04-16 (T45QVE & T45QVD) - Identical Orbit R076
    # Coincident Date Pair: 2026-03-04 (T45QVE & T45QVD)
    primary_scenes = [
        c for c in serializable_catalog
        if c["acquisition_date"] in ["2026-03-02", "2026-04-16"] and c["mgrs_tile"] in ["T45QVE", "T45QVD"]
    ]

    total_primary_bytes = sum(s["product_size_bytes"] for s in primary_scenes if s["product_size_bytes"])
    disk_stat = shutil.disk_usage(ROOT)
    avail_disk_gb = disk_stat.free / (1024**3)

    gate_summary = {
        "primary_recommended_package": "Identical Relative Orbit R076 Pre/Post Validation Quad",
        "scene_count": len(primary_scenes),
        "total_download_bytes": total_primary_bytes,
        "total_download_gib": round(total_primary_bytes / (1024**3), 2),
        "available_disk_gib": round(avail_disk_gb, 2),
        "target_destination": str(ROOT / "data/reference/sentinel2_raw/"),
        "estimated_transfer_time_minutes": round((total_primary_bytes / (2.76 * 1024 * 1024)) / 60.0, 1),
        "recommended_scenes": [
            {
                "date": s["acquisition_date"],
                "tile": s["mgrs_tile"],
                "orbit": s["relative_orbit"],
                "cloud_pct": s["cloud_cover_percent"],
                "sanctuary_cov_pct": s["sanctuary_coverage_percent"],
                "core_cov_pct": s["core_coverage_percent"],
                "size_mb": round(s["product_size_bytes"] / (1024**2), 1),
                "product_id": s["product_id"],
                "role": "Pre-Event Baseline (R076, 2 days before NISAR T0)" if s["acquisition_date"] == "2026-03-02" else "Post-Event Assessment (R076, 5 days before NISAR T1)",
            }
            for s in primary_scenes
        ],
    }

    gate_json = CATALOGUE_DIR / "sentinel2_download_gate_summary.json"
    with open(gate_json, "w") as f:
        json.dump(gate_summary, f, indent=2)
    print(f"Saved download gate summary to: {gate_json}")


if __name__ == "__main__":
    main()
