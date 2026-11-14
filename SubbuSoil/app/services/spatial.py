"""Step 9 — Spatial analysis of change: regions, areas, polygons, location.

Changed pixels (drying = classes 1-2, wetting = 4-5) are grouped into connected
regions (4- or 8-connectivity). Regions smaller than `min_region_pixels` are
dropped as speckle (they are NOT merged into neighbours, so no pixel is ever
relabelled). Each region is polygonised in the equal-area grid CRS (EPSG:6933),
described with zonal statistics, and located relative to the AOI centroid.
"""
from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import xarray as xr
from rasterio.features import shapes
from scipy import ndimage
from shapely import make_valid
from shapely import wkt as shapely_wkt
from shapely.geometry import shape
from shapely.ops import unary_union

from app.services.change import ChangeParams
from app.services.extraction import LAND_COVER_CLASSES
from app.services.subset import aoi_in_crs

DIRECTIONS = {1: "drying", 2: "wetting"}
_COMPASS = ["east", "north-east", "north", "north-west", "west", "south-west", "south", "south-east"]


def _structure(connectivity: int) -> np.ndarray:
    return ndimage.generate_binary_structure(2, 2 if connectivity == 8 else 1)


def _location(dx: float, dy: float, aoi_radius: float) -> str:
    """Compass position of a point relative to the AOI centre (offsets in metres)."""
    if np.hypot(dx, dy) < 0.2 * aoi_radius:
        return "centre"
    ang = (np.degrees(np.arctan2(dy, dx)) + 360) % 360
    return _COMPASS[int(((ang + 22.5) % 360) // 45)]


def find_regions(
    change: xr.Dataset, aoi_wkt: str, p: ChangeParams
) -> tuple[gpd.GeoDataFrame, dict, np.ndarray]:
    cls = change.change_class.values
    delta = change.delta.values
    sm1, sm2 = change.sm_t1.values, change.sm_t2.values
    lc = change.land_cover.values if "land_cover" in change else None
    transform = change.rio.transform()
    crs = change.rio.crs
    pixel_km2 = abs(transform.a * transform.e) / 1e6
    struct = _structure(p.connectivity)

    region_ids = np.zeros(cls.shape, "int32")
    region_dir: dict[int, int] = {}
    speckle = {"drying": 0, "wetting": 0}
    next_id = 1
    for d, name in DIRECTIONS.items():
        mask = np.isin(cls, (1, 2)) if d == 1 else np.isin(cls, (4, 5))
        lab, n = ndimage.label(mask, structure=struct)
        if n == 0:
            continue
        sizes = np.bincount(lab.ravel(), minlength=n + 1)
        keep = sizes >= p.min_region_pixels
        keep[0] = False
        speckle[name] = int(sizes[1:][~keep[1:]].sum())
        mapping = np.zeros(n + 1, "int32")
        n_keep = int(keep.sum())
        mapping[keep] = np.arange(next_id, next_id + n_keep, dtype="int32")
        region_ids = np.where(mask, mapping[lab], region_ids)
        for rid in range(next_id, next_id + n_keep):
            region_dir[rid] = d
        next_id += n_keep

    aoi = aoi_in_crs(shapely_wkt.loads(aoi_wkt), crs).geometry.iloc[0]
    aoi_c = aoi.centroid
    aoi_radius = np.sqrt(aoi.area / np.pi)

    records = []
    if region_dir:
        ids = np.arange(1, next_id)
        lab = region_ids
        n_px = ndimage.sum_labels(np.ones_like(delta), lab, ids)
        mean_d = ndimage.mean(np.nan_to_num(delta), lab, ids)
        min_d = ndimage.minimum(np.nan_to_num(delta), lab, ids)
        max_d = ndimage.maximum(np.nan_to_num(delta), lab, ids)
        mean_1 = ndimage.mean(np.nan_to_num(sm1), lab, ids)
        mean_2 = ndimage.mean(np.nan_to_num(sm2), lab, ids)
        n_strong = ndimage.sum_labels(np.isin(cls, (1, 5)).astype(float), lab, ids)
        lab_slices = ndimage.find_objects(lab)  # bounding box per region id (index = id-1)

        geoms: dict[int, list] = {}
        for geom, val in shapes(lab, mask=lab > 0, transform=transform, connectivity=p.connectivity):
            geoms.setdefault(int(val), []).append(shape(geom))

        for k, rid in enumerate(ids):
            # 8-connected pixels touching only at corners give self-touching rings;
            # make_valid splits them into a valid (Multi)Polygon with identical area.
            poly = make_valid(unary_union(geoms[int(rid)]))
            if poly.geom_type == "GeometryCollection":
                poly = unary_union([g for g in poly.geoms if g.geom_type in ("Polygon", "MultiPolygon")])
            c = poly.centroid
            dom_lc = None
            if lc is not None:
                v, cnt = np.unique(lc[lab_slices[k]][lab[lab_slices[k]] == rid], return_counts=True)
                dom = int(v[np.argmax(cnt)])
                dom_lc = {"class": LAND_COVER_CLASSES.get(dom, f"class {dom}"),
                          "pct": round(100 * float(cnt.max()) / float(cnt.sum()), 1)}
            records.append({
                "region_id": int(rid),
                "direction": DIRECTIONS[region_dir[int(rid)]],
                "n_pixels": int(n_px[k]),
                "area_km2": round(float(n_px[k]) * pixel_km2, 3),
                "mean_delta": round(float(mean_d[k]), 4),
                "min_delta": round(float(min_d[k]), 4),
                "max_delta": round(float(max_d[k]), 4),
                "mean_sm_t1": round(float(mean_1[k]), 4),
                "mean_sm_t2": round(float(mean_2[k]), 4),
                "pct_strong": round(100 * float(n_strong[k]) / float(n_px[k]), 1),
                "dominant_land_cover": dom_lc["class"] if dom_lc else None,
                "dominant_land_cover_pct": dom_lc["pct"] if dom_lc else None,
                "location_in_aoi": _location(c.x - aoi_c.x, c.y - aoi_c.y, aoi_radius),
                "distance_from_aoi_centre_km": round(c.distance(aoi_c) / 1000, 2),
                "geometry": poly,
            })

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=crs) if records else gpd.GeoDataFrame(
        columns=["region_id", "direction", "area_km2", "geometry"], geometry="geometry", crs=crs
    )
    if len(gdf):
        gdf = gdf.sort_values("area_km2", ascending=False).reset_index(drop=True)
        gdf["rank"] = np.arange(1, len(gdf) + 1)
        cent = gpd.GeoSeries(gdf.geometry.centroid, crs=crs).to_crs(4326)
        gdf["centroid_lon"] = cent.x.round(5)
        gdf["centroid_lat"] = cent.y.round(5)

    n_cmp = int((cls > 0).sum())
    summary = {"n_regions": int(len(gdf)), "speckle_pixels_dropped": speckle, "by_direction": {}}
    for name in DIRECTIONS.values():
        sub = gdf[gdf.direction == name] if len(gdf) else gdf
        area = float(sub.area_km2.sum()) if len(sub) else 0.0
        by_loc = {}
        if len(sub):
            for loc, grp in sub.groupby("location_in_aoi"):
                by_loc[loc] = round(float(grp.area_km2.sum()), 3)
        summary["by_direction"][name] = {
            "n_regions": int(len(sub)),
            "area_km2": round(area, 3),
            "pct_of_compared_area": round(100 * area / (n_cmp * pixel_km2), 2) if n_cmp else 0.0,
            "largest_region_km2": round(float(sub.area_km2.max()), 3) if len(sub) else 0.0,
            "area_by_location_km2": dict(sorted(by_loc.items(), key=lambda kv: -kv[1])),
        }
    return gdf, summary, region_ids


def regions_geojson(gdf: gpd.GeoDataFrame, limit: int | None = None) -> dict:
    """GeoJSON FeatureCollection in EPSG:4326 (largest regions first)."""
    if not len(gdf):
        return {"type": "FeatureCollection", "features": []}
    g = gdf.head(limit) if limit else gdf
    return json.loads(g.to_crs(4326).to_json(drop_id=True))
