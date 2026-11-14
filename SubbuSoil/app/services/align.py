"""Step 7 — Raster alignment.

NISAR SME2 products are posted on the global EASE-Grid 2.0 (EPSG:6933, ~200 m),
so observations normally share one pixel lattice. For each observation we check
CRS, resolution and sub-pixel origin offset:

  * same CRS + resolution + offset < 1 % of a pixel -> exact reindex (no resampling)
  * otherwise -> rioxarray reproject_match (nearest neighbour, never interpolates)

All observations are placed on one target grid (the union of their AOI extents)
and stacked along a `time` dimension.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr
from rasterio.enums import Resampling

ALIGN_TOL_PX = 0.01

# value used where an observation has no data on the common grid
_FILL = {"aoi_mask": 0, "valid": 0, "mask_reason": 1}  # 1 = outside_aoi bit


class AlignmentError(ValueError):
    pass


def _fill(name: str, da: xr.DataArray):
    if name in _FILL:
        return _FILL[name]
    if np.issubdtype(da.dtype, np.floating):
        return np.nan
    return da.attrs.get("flag_fill_value", 0)


def _res(ds: xr.Dataset) -> tuple[float, float]:
    rx, ry = ds.rio.resolution()
    return abs(rx), abs(ry)


def _target_grid(datasets: list[xr.Dataset]) -> tuple[np.ndarray, np.ndarray]:
    ref = datasets[0]
    dx, dy = _res(ref)
    x0, y0 = float(ref.x[0]), float(ref.y[0])
    minx = min(float(d.x.min()) for d in datasets)
    maxx = max(float(d.x.max()) for d in datasets)
    miny = min(float(d.y.min()) for d in datasets)
    maxy = max(float(d.y.max()) for d in datasets)
    # snap extent onto the reference lattice
    i0, i1 = np.floor((minx - x0) / dx + 0.5), np.floor((maxx - x0) / dx + 0.5)
    j0, j1 = np.floor((y0 - maxy) / dy + 0.5), np.floor((y0 - miny) / dy + 0.5)
    xs = x0 + np.arange(i0, i1 + 1) * dx
    ys = y0 - np.arange(j0, j1 + 1) * dy  # north -> south
    return xs, ys


def _time_of(ds: xr.Dataset) -> np.datetime64:
    t = pd.Timestamp(ds.attrs["start_time"])
    if t.tzinfo is not None:
        t = t.tz_convert(None)
    return np.datetime64(t.to_datetime64(), "ns")


def align(datasets: list[xr.Dataset]) -> tuple[xr.Dataset, list[dict]]:
    if len(datasets) < 2:
        raise AlignmentError("Need at least 2 observations to align")
    ref = datasets[0]
    ref_crs = ref.rio.crs
    dx, dy = _res(ref)
    xs, ys = _target_grid(datasets)

    template = xr.Dataset(coords={"x": xs, "y": ys}).rio.write_crs(ref_crs)
    template = template.rio.set_spatial_dims(x_dim="x", y_dim="y")

    aligned, reports = [], []
    for ds in datasets:
        same_crs = ds.rio.crs == ref_crs
        rdx, rdy = _res(ds)
        same_res = np.isclose(rdx, dx, rtol=1e-6) and np.isclose(rdy, dy, rtol=1e-6)
        off_x = ((float(ds.x[0]) - xs[0]) / dx) % 1.0
        off_y = ((ys[0] - float(ds.y[0])) / dy) % 1.0
        off_x, off_y = min(off_x, 1 - off_x), min(off_y, 1 - off_y)
        on_lattice = off_x < ALIGN_TOL_PX and off_y < ALIGN_TOL_PX

        if same_crs and same_res and on_lattice:
            method = "exact_reindex"
            out = ds.reindex(
                x=xs, y=ys, method="nearest", tolerance=dx * ALIGN_TOL_PX,
                fill_value={n: _fill(n, da) for n, da in ds.data_vars.items()},
            )
        else:
            method = "reproject_nearest"
            parts = {}
            for name, da in ds.data_vars.items():
                if not {"y", "x"} <= set(da.dims):
                    continue
                fill = _fill(name, da)
                da = da.rio.write_nodata(fill, encoded=False)
                parts[name] = da.rio.reproject_match(template, resampling=Resampling.nearest)
                parts[name] = parts[name].assign_coords(x=xs, y=ys)
            out = xr.Dataset(parts, attrs=ds.attrs)

        for name in out.data_vars:
            out[name].attrs = ds[name].attrs if name in ds else out[name].attrs
        out = out.drop_vars([c for c in ("latitude", "longitude") if c in out.coords])
        reports.append({
            "granule_id": ds.attrs.get("granule_id"),
            "method": method,
            "crs": str(ds.rio.crs),
            "resolution_m": [rdx, rdy],
            "origin_offset_px": [round(off_x, 6), round(off_y, 6)],
            "source_shape": [int(ds.sizes["y"]), int(ds.sizes["x"])],
        })
        aligned.append(out.expand_dims(time=[_time_of(ds)]).assign_coords(
            granule_id=("time", [ds.attrs.get("granule_id", "")])
        ))

    stack = xr.concat(aligned, dim="time", combine_attrs="drop_conflicts").sortby("time")
    stack = stack.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(ref_crs)
    stack.attrs["grid_spacing_x"], stack.attrs["grid_spacing_y"] = dx, -dy

    # post-condition: one grid for all
    t = stack.rio.transform()
    if not (np.isclose(abs(t.a), dx) and np.isclose(abs(t.e), dy)):
        raise AlignmentError("Aligned stack has inconsistent transform")
    return stack, reports
