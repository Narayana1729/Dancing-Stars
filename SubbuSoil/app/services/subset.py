"""Step 5 — Spatial subsetting to the exact AOI polygon (xarray + GeoPandas).

The AOI (EPSG:4326) is reprojected with GeoPandas to the raster CRS, rasterised
onto the dataset's grid (pixel-centre rule by default, or all_touched), and the
dataset is cropped to the polygon's rows/cols. Pixels outside the polygon are
set to NaN (floats) or the layer's fill value (integer flags), and an
`aoi_mask` layer records which pixels are inside.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import xarray as xr
from rasterio.features import geometry_mask
from shapely.geometry.base import BaseGeometry

from app.services.aoi import area_km2


class SubsetError(ValueError):
    pass


def aoi_in_crs(aoi: BaseGeometry, crs) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=[aoi], crs="EPSG:4326").to_crs(crs)


def _fill_for(da: xr.DataArray):
    if np.issubdtype(da.dtype, np.floating):
        return np.nan
    return da.attrs.get("flag_fill_value", 0)


def subset_to_aoi(ds: xr.Dataset, aoi: BaseGeometry, all_touched: bool = False) -> xr.Dataset:
    crs = ds.rio.crs
    if crs is None:
        raise SubsetError("Dataset has no CRS")
    gdf = aoi_in_crs(aoi, crs)

    inside = geometry_mask(
        list(gdf.geometry),
        out_shape=(ds.sizes["y"], ds.sizes["x"]),
        transform=ds.rio.transform(),
        invert=True,
        all_touched=all_touched,
    )
    if not inside.any():
        raise SubsetError("AOI polygon contains no pixel centres of this grid (AOI too small? try all_touched)")

    rows = np.nonzero(inside.any(axis=1))[0]
    cols = np.nonzero(inside.any(axis=0))[0]
    ys, xs = slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1)
    out = ds.isel(y=ys, x=xs)
    inside = inside[ys, xs]
    inside_da = xr.DataArray(inside, dims=("y", "x"))

    for name, da in out.data_vars.items():
        if set(da.dims) >= {"y", "x"}:
            fill = _fill_for(da)
            out[name] = da.where(inside_da, fill).astype(da.dtype)
            out[name].attrs = da.attrs

    out["aoi_mask"] = (("y", "x"), inside.astype("uint8"), {"long_name": "1 = pixel inside AOI polygon"})
    pixel_area_km2 = abs(float(out.attrs["grid_spacing_x"]) * float(out.attrs["grid_spacing_y"])) / 1e6
    out.attrs.update({
        "aoi_wkt": aoi.wkt,
        "aoi_area_km2": round(area_km2(aoi), 3),
        "aoi_all_touched": int(all_touched),
        "n_aoi_pixels": int(inside.sum()),
        "pixel_area_km2": pixel_area_km2,
    })
    return out.rio.write_crs(crs)
