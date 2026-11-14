"""Steps 8 + 9 orchestration: load the aligned stack, detect change per date
pair, extract change regions, and write outputs under
DATA_DIR/processed/<run_id>/change/<t1>_<t2>_<params-hash>/:

  delta.tif          SM(t2) - SM(t1), m3/m3 (COG)
  change_class.tif   0..5 change classes (COG, 0 = no data)
  regions.tif        region id per pixel (COG, 0 = none)
  regions.geojson    region polygons, EPSG:4326
  summary.json       statistics + region summary
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from app.core.config import get_settings
from app.services.change import ChangeParams, detect_change, pair_indices
from app.services.context.integrate import ContextParams, pair_context
from app.services.explain import explain_pair
from app.services.spatial import find_regions, regions_geojson


class RunNotFound(FileNotFoundError):
    pass


def run_dir(run_id: str) -> Path:
    d = get_settings().data_dir / "processed" / run_id
    if not (d / "stack.nc").exists():
        raise RunNotFound(f"No prepared run '{run_id}' (run /processing/prepare first)")
    return d


def load_stack(run_id: str) -> xr.Dataset:
    ds = xr.load_dataset(run_dir(run_id) / "stack.nc", engine="h5netcdf")
    return ds.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(6933)


def _records(gdf) -> list[dict]:
    if not len(gdf):
        return []
    df = gdf.drop(columns="geometry")
    return json.loads(df.to_json(orient="records"))


def analyse_run(
    run_id: str,
    p: ChangeParams,
    context: ContextParams | None = None,
    explain: bool = False,
    n_top_regions: int = 5,
    report=None,
) -> dict:
    """Steps 8-9, plus optionally 10 (context) and 11 (explain; implies context)."""
    report = report or (lambda *a, **k: None)
    if explain and context is None:
        context = ContextParams()
    stack = load_stack(run_id)
    aoi_wkt = stack.attrs["aoi_wkt"]
    phash = hashlib.sha1(p.model_dump_json().encode()).hexdigest()[:8]

    pairs = []
    for i, j in pair_indices(stack.sizes["time"], p.pairs):
        report("Detecting change", 42, "")
        change, stats = detect_change(stack, i, j, p)                     # step 8
        gdf, region_summary, region_ids = find_regions(change, aoi_wkt, p)  # step 9

        t1 = pd.Timestamp(stack.time.values[i]).strftime("%Y%m%d")
        t2 = pd.Timestamp(stack.time.values[j]).strftime("%Y%m%d")
        out = run_dir(run_id) / "change" / f"{t1}_{t2}_{phash}"
        out.mkdir(parents=True, exist_ok=True)

        change.delta.rio.write_nodata(np.nan, encoded=False).rio.to_raster(
            out / "delta.tif", driver="COG", compress="DEFLATE")
        change.change_class.rio.write_nodata(0, encoded=False).rio.to_raster(
            out / "change_class.tif", driver="COG", compress="DEFLATE")
        xr.DataArray(region_ids, coords={"y": change.y, "x": change.x}, dims=("y", "x")) \
            .rio.write_crs(change.rio.crs).rio.write_nodata(0, encoded=False) \
            .rio.to_raster(out / "regions.tif", driver="COG", compress="DEFLATE")

        fc_all = regions_geojson(gdf)
        (out / "regions.geojson").write_text(json.dumps(fc_all), encoding="utf-8")

        result = {
            "stats": stats,
            "regions_summary": region_summary,
            "regions": regions_geojson(gdf, limit=p.max_regions),
            "files": {
                "delta_cog": str(out / "delta.tif"),
                "change_class_cog": str(out / "change_class.tif"),
                "regions_cog": str(out / "regions.tif"),
                "regions_geojson": str(out / "regions.geojson"),
            },
        }
        if context is not None:                                           # step 10
            result["context"] = pair_context(run_dir(run_id), change, region_ids, gdf, aoi_wkt, context, out,
                                             report=report)
            result["files"].update(result["context"].pop("files", {}))
        if explain:                                                       # step 11
            report("Writing the explanation", 85, "")
            result["explanation"] = explain_pair(
                stats, region_summary, _records(gdf), result["context"],
                antecedent_days=context.antecedent_days, n_top_regions=n_top_regions,
            )
            (out / "explanation.md").write_text(
                f"# {result['explanation']['headline']}\n\n{result['explanation']['narrative']}\n", encoding="utf-8")
            result["files"]["explanation_md"] = str(out / "explanation.md")

        (out / "summary.json").write_text(
            json.dumps({k: v for k, v in result.items() if k != "regions"} | {"params": p.model_dump()},
                       indent=2, default=str),
            encoding="utf-8",
        )
        pairs.append(result)

    return {
        "run_id": run_id,
        "params": p.model_dump(),
        "context_params": context.model_dump() if context else None,
        "aoi_wkt": aoi_wkt,
        "pairs": pairs,
    }
