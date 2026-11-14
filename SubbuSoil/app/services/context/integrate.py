"""Step 10 — Supporting data integration for one change pair.

Brings rainfall / temperature / ET0 / reanalysis soil moisture (Open-Meteo),
Sentinel-2 NDVI and SoilGrids topsoil texture onto the SME2 analysis grid,
then relates them to the soil-moisture change: AOI-level summaries, land-cover
breakdowns, pixel-level Spearman correlations and per-region values.

Every source is optional and fails independently: a failed source is reported
as {"available": false, "error": ...} and the rest still runs.

Cache: DATA_DIR/processed/<run_id>/context/
  soil.nc                               (per run grid)
  ndvi_<YYYYMMDD>_w<win>_c<cloud>.nc    (per NISAR date)
  weather_<t1>_<t2>_a<n>_g<step>.json   (per pair)
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from pydantic import BaseModel, Field
from scipy import ndimage, stats
from shapely import wkt as shapely_wkt

from app.services.context.soil import soil_on_grid, texture_class
from app.services.context.vegetation import ndvi_on_grid
from app.services.context.weather import weather_context
from app.services.extraction import LAND_COVER_CLASSES


class ContextParams(BaseModel):
    include_weather: bool = True
    include_vegetation: bool = True
    include_soil: bool = True
    antecedent_days: int = Field(7, ge=1, le=30, description="Days of rain/ET0 before each date")
    weather_grid_deg: float = Field(0.1, ge=0.05, le=1.0)
    s2_window_days: int = Field(15, ge=1, le=60, description="Search +/- days around each NISAR date")
    s2_max_cloud: float = Field(60, ge=0, le=100)


def _ts(t) -> datetime:
    t = pd.Timestamp(t)
    return (t.tz_convert(None) if t.tzinfo else t).to_pydatetime()


def _spearman(a: np.ndarray, b: np.ndarray, max_n: int = 50_000) -> dict | None:
    m = np.isfinite(a) & np.isfinite(b)
    n = int(m.sum())
    if n < 30:
        return None
    a, b = a[m], b[m]
    if n > max_n:
        idx = np.random.default_rng(0).choice(n, max_n, replace=False)
        a, b = a[idx], b[idx]
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    r = stats.spearmanr(a, b)
    return {"rho": round(float(r.statistic), 3), "p_value": float(r.pvalue), "n": n}


def _clean(v):
    if isinstance(v, float) and not np.isfinite(v):
        return None
    if isinstance(v, (np.floating,)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    return v


def _grid(change: xr.Dataset):
    return change.rio.transform(), change.sizes["x"], change.sizes["y"]


# ---------------------------------------------------------------- cached sources
def _soil(ctx_dir: Path, change: xr.Dataset) -> dict[str, np.ndarray]:
    path = ctx_dir / "soil.nc"
    if path.exists():
        ds = xr.load_dataset(path, engine="h5netcdf")
        if ds.sizes.get("y") == change.sizes["y"] and ds.sizes.get("x") == change.sizes["x"]:
            return {k: ds[k].values for k in ds.data_vars}
    tr, w, h = _grid(change)
    arrays = soil_on_grid(tr, w, h)
    xr.Dataset({k: (("y", "x"), v) for k, v in arrays.items()},
               coords={"y": change.y.values, "x": change.x.values}).to_netcdf(path, engine="h5netcdf")
    return arrays


def _ndvi(ctx_dir: Path, change: xr.Dataset, aoi, t: datetime, cp: ContextParams):
    # v2: BOA offset handling fixed (v1 cache files had NDVI biased towards 1)
    path = ctx_dir / f"ndvi_v2_{t:%Y%m%d}_w{cp.s2_window_days}_c{int(cp.s2_max_cloud)}.nc"
    if path.exists():
        ds = xr.load_dataset(path, engine="h5netcdf")
        return ds.ndvi.values, json.loads(ds.attrs["meta"])
    tr, w, h = _grid(change)
    ndvi, meta = ndvi_on_grid(aoi, t, tr, w, h, cp.s2_window_days, cp.s2_max_cloud)
    xr.Dataset({"ndvi": (("y", "x"), ndvi)}, coords={"y": change.y.values, "x": change.x.values},
               attrs={"meta": json.dumps(meta)}).to_netcdf(path, engine="h5netcdf")
    return ndvi, meta


def _weather(ctx_dir: Path, aoi, t1: datetime, t2: datetime, cp: ContextParams) -> dict:
    path = ctx_dir / f"weather_{t1:%Y%m%d}_{t2:%Y%m%d}_a{cp.antecedent_days}_g{cp.weather_grid_deg}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    w = weather_context(aoi, t1, t2, cp.antecedent_days, cp.weather_grid_deg)
    path.write_text(json.dumps(w, default=_clean), encoding="utf-8")
    return w


# ---------------------------------------------------------------- main
def pair_context(
    run_dir: Path,
    change: xr.Dataset,
    region_ids: np.ndarray,
    regions_gdf,
    aoi_wkt: str,
    cp: ContextParams,
    out_dir: Path | None = None,
    report=None,
) -> dict:
    ctx_dir = run_dir / "context"
    ctx_dir.mkdir(parents=True, exist_ok=True)
    report = report or (lambda *a, **k: None)
    aoi = shapely_wkt.loads(aoi_wkt)
    t1, t2 = _ts(change.attrs["t1"]), _ts(change.attrs["t2"])
    delta = change.delta.values
    compared = np.isfinite(delta)
    lc = change.land_cover.values if "land_cover" in change else None
    out: dict = {}
    layers: dict[str, np.ndarray] = {}

    # ---- weather ----
    report("Fetching rainfall and temperature (Open-Meteo)", 45, "")
    if cp.include_weather:
        try:
            out["weather"] = {"available": True, **_weather(ctx_dir, aoi, t1, t2, cp)}
        except Exception as e:
            out["weather"] = {"available": False, "error": f"{type(e).__name__}: {e}"}
    else:
        out["weather"] = {"available": False, "error": "disabled"}

    # ---- vegetation ----
    if cp.include_vegetation:
        try:
            report("Reading Sentinel-2 vegetation, first date", 55, "")
            n1, m1 = _ndvi(ctx_dir, change, aoi, t1, cp)
            report("Reading Sentinel-2 vegetation, second date", 65, "")
            n2, m2 = _ndvi(ctx_dir, change, aoi, t2, cp)
            dn = n2 - n1
            layers.update(ndvi_t1=n1, ndvi_t2=n2, ndvi_delta=dn)
            both = compared & np.isfinite(dn)
            by_lc = []
            if lc is not None:
                for code in np.unique(lc[both]):
                    m = both & (lc == code)
                    if m.sum() < 30:
                        continue
                    by_lc.append({
                        "land_cover": LAND_COVER_CLASSES.get(int(code), f"class {int(code)}"),
                        "n_pixels": int(m.sum()),
                        "ndvi_t1": round(float(np.nanmean(n1[m])), 3),
                        "ndvi_t2": round(float(np.nanmean(n2[m])), 3),
                        "ndvi_delta": round(float(np.nanmean(dn[m])), 3),
                        "sm_delta": round(float(np.nanmean(delta[m])), 4),
                    })
                by_lc.sort(key=lambda r: -r["n_pixels"])
            out["vegetation"] = {
                "available": True,
                "source": "Sentinel-2 L2A (Earth Search STAC), NDVI with SCL cloud mask",
                "scene_t1": m1, "scene_t2": m2,
                "n_pixels_with_ndvi": int(both.sum()),
                "ndvi_coverage_of_compared": round(float(both.sum()) / max(int(compared.sum()), 1), 3),
                "ndvi_t1_mean": _clean(float(np.nanmean(n1[both]))) if both.any() else None,
                "ndvi_t2_mean": _clean(float(np.nanmean(n2[both]))) if both.any() else None,
                "ndvi_delta_mean": _clean(float(np.nanmean(dn[both]))) if both.any() else None,
                "corr_sm_delta_vs_ndvi_delta": _spearman(delta, dn),
                "corr_sm_delta_vs_ndvi_t2": _spearman(delta, n2),
                "by_land_cover": by_lc,
            }
        except Exception as e:
            out["vegetation"] = {"available": False, "error": f"{type(e).__name__}: {e}"}
    else:
        out["vegetation"] = {"available": False, "error": "disabled"}

    # ---- soil ----
    if cp.include_soil:
        try:
            report("Reading soil texture (SoilGrids)", 75, "")
            soil = _soil(ctx_dir, change)
            layers.update({f"soil_{k}": v for k, v in soil.items()})
            m = compared & np.isfinite(soil["sand"])
            sand = float(np.nanmean(soil["sand"][m])) if m.any() else float("nan")
            clay = float(np.nanmean(soil["clay"][m])) if m.any() else float("nan")
            out["soil"] = {
                "available": True,
                "source": "ISRIC SoilGrids 2.0, 0-5 cm",
                "sand_pct_mean": _clean(round(sand, 1)),
                "clay_pct_mean": _clean(round(clay, 1)),
                "silt_pct_mean": _clean(round(float(np.nanmean(soil["silt"][m])), 1)) if m.any() else None,
                "soc_g_per_kg_mean": _clean(round(float(np.nanmean(soil["soc"][m])), 1)) if m.any() else None,
                "sand_pct_range": [_clean(round(float(np.nanpercentile(soil["sand"][m], q)), 1)) for q in (5, 95)] if m.any() else None,
                "texture_class": texture_class(sand, clay) if np.isfinite(sand) and np.isfinite(clay) else None,
                "corr_sm_delta_vs_sand": _spearman(delta, soil["sand"]),
                "corr_sm_delta_vs_clay": _spearman(delta, soil["clay"]),
            }
        except Exception as e:
            out["soil"] = {"available": False, "error": f"{type(e).__name__}: {e}"}
    else:
        out["soil"] = {"available": False, "error": "disabled"}

    # ---- per region ----
    regions = []
    if len(regions_gdf):
        ids = regions_gdf.region_id.to_numpy()
        means = {name: ndimage.mean(np.nan_to_num(arr, nan=0.0), region_ids, ids) for name, arr in layers.items()}
        counts = {name: ndimage.sum_labels(np.isfinite(arr).astype(float), region_ids, ids) for name, arr in layers.items()}
        sums = {name: ndimage.sum_labels(np.nan_to_num(arr, nan=0.0), region_ids, ids) for name, arr in layers.items()}
        pts = out["weather"].get("points", []) if out["weather"].get("available") else []
        for k, row in enumerate(regions_gdf.itertuples()):
            rec = {"region_id": int(row.region_id)}
            for name in layers:
                c = counts[name][k]
                rec[name] = round(float(sums[name][k] / c), 4) if c > 0 else None
            if rec.get("soil_sand") is not None and rec.get("soil_clay") is not None:
                rec["soil_texture"] = texture_class(rec["soil_sand"], rec["soil_clay"])
            if pts:
                lat, lon = getattr(row, "centroid_lat"), getattr(row, "centroid_lon")
                near = min(pts, key=lambda p: (p["lat"] - lat) ** 2 + (p["lon"] - lon) ** 2)
                rec["weather"] = {k2: v for k2, v in near.items()}
            regions.append(rec)
        del means
    out["regions"] = regions

    # ---- save layers ----
    if out_dir is not None and layers:
        ds = xr.Dataset({k: (("y", "x"), v.astype("float32")) for k, v in layers.items()},
                        coords={"y": change.y.values, "x": change.x.values})
        ds = ds.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(change.rio.crs)
        ds.to_netcdf(out_dir / "context.nc", engine="h5netcdf")
        if "ndvi_delta" in ds:
            ds.ndvi_delta.rio.write_nodata(np.nan, encoded=False).rio.to_raster(
                out_dir / "ndvi_delta.tif", driver="COG", compress="DEFLATE")
        out["files"] = {"context_netcdf": str(out_dir / "context.nc")}
        if "ndvi_delta" in ds:
            out["files"]["ndvi_delta_cog"] = str(out_dir / "ndvi_delta.tif")
    return out
