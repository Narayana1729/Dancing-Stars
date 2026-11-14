"""Step 13 — read-only access to stored results.

There is no database yet (step 12 is deferred). The run folders under
DATA_DIR/processed are the store:

  processed/<run_id>/manifest.json        request + preparation report
  processed/<run_id>/stack.nc             aligned analysis stack
  processed/<run_id>/change/<pair>/       summary.json, regions.geojson, delta.tif, ...

Responses never contain local file paths; files are named by role only.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import numpy as np
import rioxarray  # noqa: F401  (registers .rio accessor)
import xarray as xr
from matplotlib import colormaps
from matplotlib.image import imsave

from app.core.config import get_settings

ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,80}$")  # blocks path traversal such as ../
DELTA_LIMIT = 0.2  # colour scale for change maps, m3/m3


class ResultNotFound(FileNotFoundError):
    pass


def _check_id(value: str) -> str:
    if not ID_RE.match(value):
        raise ResultNotFound(f"invalid id {value!r}")
    return value


def _r(x, nd: int = 4):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def processed_root() -> Path:
    return get_settings().data_dir / "processed"


def run_path(run_id: str) -> Path:
    d = processed_root() / _check_id(run_id)
    if not (d / "stack.nc").exists() or not (d / "manifest.json").exists():
        raise ResultNotFound(f"run {run_id} not found")
    return d


def pair_path(run_id: str, pair_id: str) -> Path:
    d = run_path(run_id) / "change" / _check_id(pair_id)
    if not (d / "summary.json").exists():
        raise ResultNotFound(f"pair {pair_id} not found in run {run_id}")
    return d


def _pairs(run_dir: Path) -> list[str]:
    root = run_dir / "change"
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "summary.json").exists())


def _manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- runs
def list_runs() -> list[dict]:
    out = []
    root = processed_root()
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        try:
            rd = run_path(d.name)
        except ResultNotFound:
            continue
        res = _manifest(rd)["result"]
        out.append({
            "run_id": d.name,
            "track_key": res["track_key"],
            "n_observations": res["n_observations"],
            "dates": [o["start_time"][:10] for o in res["observations"]],
            "aoi_km2": res["aoi"]["area_km2"],
            "n_common_valid_pixels": res["n_common_valid_pixels"],
            "pairs": _pairs(rd),
        })
    return out


def run_detail(run_id: str) -> dict:
    rd = run_path(run_id)
    man = _manifest(rd)
    result = dict(man["result"])
    result["pairs"] = _pairs(rd)
    return {"run_id": run_id, "request": man["request"], "result": result}


def history(run_id: str) -> dict:
    """Per-date statistics across the stack: the 'historical comparison' view."""
    rd = run_path(run_id)
    with xr.open_dataset(rd / "stack.nc", engine="h5netcdf") as ds:
        sm = ds.soil_moisture.values
        unc = ds.soil_moisture_uncertainty.values
        valid = ds.valid.values == 1
        aoi = ds.aoi_mask.values == 1
        times = [str(t)[:19] for t in ds.time.values]
        gids = [str(g) for g in ds.granule_id.values]

    series = []
    for i, t in enumerate(times):
        v = sm[i][valid[i]]
        u = unc[i][valid[i]]
        n_aoi = int(aoi[i].sum())
        has = v.size > 0
        series.append({
            "time": t,
            "granule_id": gids[i],
            "n_aoi_pixels": n_aoi,
            "n_valid": int(valid[i].sum()),
            "valid_fraction": _r(valid[i].sum() / max(n_aoi, 1), 4),
            "mean_sm": _r(v.mean()) if has else None,
            "median_sm": _r(np.median(v)) if has else None,
            "p10_sm": _r(np.percentile(v, 10)) if has else None,
            "p90_sm": _r(np.percentile(v, 90)) if has else None,
            "mean_uncertainty": _r(u.mean()) if has else None,
        })
    return {"run_id": run_id, "series": series}


# ---------------------------------------------------------------- pairs
def pair_detail(run_id: str, pair_id: str) -> dict:
    pd_ = pair_path(run_id, pair_id)
    s = json.loads((pd_ / "summary.json").read_text(encoding="utf-8"))
    s.pop("regions", None)
    s["files"] = {k: Path(v).name for k, v in s.get("files", {}).items()}
    s["pair_id"] = pair_id
    s["available_layers"] = sorted(p.name for p in pd_.iterdir() if p.is_file())
    return s


def regions(run_id: str, pair_id: str) -> dict:
    return json.loads((pair_path(run_id, pair_id) / "regions.geojson").read_text(encoding="utf-8"))


def _delta_4326(pd_: Path):
    da = rioxarray.open_rasterio(pd_ / "delta.tif", masked=True).squeeze("band", drop=True)
    return da.rio.reproject("EPSG:4326")


def delta_bounds(run_id: str, pair_id: str) -> dict:
    da = _delta_4326(pair_path(run_id, pair_id))
    west, south, east, north = da.rio.bounds()
    return {
        "bounds": [[south, west], [north, east]],  # Leaflet order
        "value_range": [-DELTA_LIMIT, DELTA_LIMIT],
        "units": "m3/m3",
        "colormap": "RdBu (red = drier, blue = wetter)",
    }


def delta_png(run_id: str, pair_id: str) -> bytes:
    da = _delta_4326(pair_path(run_id, pair_id))
    arr = da.values.astype("float32")
    norm = np.clip((np.nan_to_num(arr, nan=0.0) + DELTA_LIMIT) / (2 * DELTA_LIMIT), 0, 1)
    rgba = colormaps["RdBu"](norm)
    rgba[..., 3] = np.where(np.isfinite(arr), 0.85, 0.0)
    buf = io.BytesIO()
    imsave(buf, rgba, format="png")
    return buf.getvalue()


def panels_png(run_id: str, pair_id: str) -> bytes:
    """Three panels as in data_reading.ipynb: observation 1, observation 2 (aligned),
    difference. Uses the QC-passed soil moisture from the aligned stack, so grey
    pixels are those that had no valid retrieval on that date."""
    from matplotlib import colormaps as cmaps
    from matplotlib.figure import Figure

    rd = run_path(run_id)
    stats = json.loads((pair_path(run_id, pair_id) / "summary.json").read_text(encoding="utf-8"))["stats"]
    with xr.open_dataset(rd / "stack.nc", engine="h5netcdf") as ds:
        gids = [str(g) for g in ds.granule_id.values]
        i1, i2 = gids.index(stats["granule_t1"]), gids.index(stats["granule_t2"])
        sm1 = ds.soil_moisture.isel(time=i1).values.astype("float32")
        sm2 = ds.soil_moisture.isel(time=i2).values.astype("float32")
    delta = np.where(np.isfinite(sm1) & np.isfinite(sm2), sm2 - sm1, np.nan)

    panels = [
        (sm1, f"Observation 1 ({stats['t1'][:10]})", "YlGnBu", 0.0, 0.6, "Soil moisture (m³/m³)"),
        (sm2, f"Observation 2 ({stats['t2'][:10]}), aligned", "YlGnBu", 0.0, 0.6, "Soil moisture (m³/m³)"),
        (delta, "Difference (obs 2 − obs 1)", "RdYlBu", -0.3, 0.3, "Change (m³/m³)"),
    ]
    fig = Figure(figsize=(15, 5), dpi=100)
    axes = fig.subplots(1, 3)
    for ax, (arr, title, cmap, lo, hi, label) in zip(axes, panels):
        cm = cmaps[cmap].copy()
        cm.set_bad(color="#d9d9d9")
        im = ax.imshow(np.ma.masked_invalid(arr), cmap=cm, vmin=lo, vmax=hi)
        ax.set_title(title)
        ax.set_xticks([])
        ax.set_yticks([])
        fig.colorbar(im, ax=ax, label=label, fraction=0.046, pad=0.04)
    fig.suptitle(f"Soil moisture change over {stats['days']:.0f} days (grey = no valid retrieval)")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()
