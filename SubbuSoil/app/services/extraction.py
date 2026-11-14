"""Step 4 — HDF5 extraction of NISAR L3 SME2 layers.

Reads, for the AOI's bounding window only (SME2 layers are stored in 512x512
gzip chunks, so a window read fetches just the chunks it touches — important
when streaming over HTTPS):

  grids/soilMoisture, soilMoistureUncertainty        float32, fill -9999 -> NaN
  grids/retrievalQualityFlag, surfaceQualityFlag      int16, raw (fill -9999 kept)
  grids/ancillaryData/landCover                       int8,  raw (fill -127 kept)
  grids/ancillaryData/waterbodyFraction               float32, fill -> NaN
  grids/xCoordinates, yCoordinates, projection        EASE-Grid 2.0 (EPSG:6933)
  grids/latitude, longitude                           1-D geographic coordinates
  identification/*                                    granule metadata

Output: an xarray.Dataset on dims (y, x) with CRS written via rioxarray,
cached as NetCDF under DATA_DIR/extracted.

Flag semantics
--------------
retrievalQualityFlag bits are taken from the product's own HDF5 description:
  bit0 = 1 -> retrieval NOT recommended; bit1 PMI applied; bit2 TSR applied;
  bit3 DSG applied.
surfaceQualityFlag: the published spec (JPL D-107677 Rev C, Nov 2024) bit table
does NOT match current (R05.x) products — e.g. bit 2 coincides 100% with
built-up land cover and bits 8-12 are undocumented — so bits are reported
numerically, never named.
landCover classes (spec Rev C, verified against data): see LAND_COVER_CLASSES.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import rioxarray  # noqa: F401  (registers .rio accessor)
import xarray as xr
from shapely.geometry.base import BaseGeometry

from app.core.config import get_settings
from app.services.acquisition import open_source
from app.services.aoi import to_equal_area

GRIDS = "science/LSAR/SME2/grids"
IDENT = "science/LSAR/identification"
FLOAT_FILL = -9999.0
INT_FILL = -9999
LAND_COVER_FILL = -127
SME2_EPSG = 6933

LAND_COVER_CLASSES = {
    1: "Tree cover",
    2: "Shrublands",
    3: "Grassland",
    4: "Cropland",
    5: "Built-up",
    6: "Bare/sparse vegetation",
    7: "Snow & ice",
    8: "Permanent water bodies",
    9: "Herbaceous wetland",
    10: "Mangroves",
    11: "Moss & lichen",
}
RETRIEVAL_BITS = {0: "not_recommended", 1: "pmi_applied", 2: "tsr_applied", 3: "dsg_applied"}


class ExtractionError(RuntimeError):
    pass


# ---------------------------------------------------------------- helpers
def _str(v) -> str:
    if isinstance(v, np.ndarray):
        v = v.item() if v.size == 1 else v.tolist()
    return v.decode() if isinstance(v, bytes) else str(v)


def _find(g: h5py.Group, name: str) -> h5py.Dataset | None:
    """Layer in grids/ or grids/ancillaryData/ (layout differs between spec and products)."""
    for path in (name, f"ancillaryData/{name}"):
        if path in g:
            return g[path]
    return None


def _window(x: np.ndarray, y: np.ndarray, dx: float, dy: float, bounds, pad: int):
    """Row/col slices of pixels whose cells intersect `bounds` (EPSG:6933), padded."""
    minx, miny, maxx, maxy = bounds
    hx, hy = abs(dx) / 2, abs(dy) / 2
    cols = np.nonzero((x + hx >= minx) & (x - hx <= maxx))[0]
    rows = np.nonzero((y + hy >= miny) & (y - hy <= maxy))[0]
    if cols.size == 0 or rows.size == 0:
        raise ExtractionError("AOI does not intersect this granule's grid")
    c0, c1 = max(cols[0] - pad, 0), min(cols[-1] + pad + 1, x.size)
    r0, r1 = max(rows[0] - pad, 0), min(rows[-1] + pad + 1, y.size)
    return slice(r0, r1), slice(c0, c1)


def _metadata(h: h5py.File) -> dict:
    idn = h[IDENT]
    get = lambda k: _str(idn[k][()]) if k in idn else None  # noqa: E731
    start = get("zeroDopplerStartTime")
    return {
        "granule_id": get("granuleId"),
        "start_time": start,
        "stop_time": get("zeroDopplerEndTime"),
        "track": get("trackNumber"),
        "frame": get("frameNumber"),
        "orbit_direction": get("orbitPassDirection"),
        "absolute_orbit": get("absoluteOrbitNumber"),
        "crid": get("compositeReleaseId"),
        "product_version": get("productVersion"),
        "processing_datetime": get("processingDateTime"),
    }


def _cache_path(granule_id: str, rows: slice, cols: slice) -> Path:
    d = get_settings().data_dir / "extracted"
    d.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{rows.start}:{rows.stop}:{cols.start}:{cols.stop}".encode()).hexdigest()[:10]
    return d / f"{granule_id}__{key}.nc"


# ---------------------------------------------------------------- main
def extract_sme2(
    source: str,
    aoi: BaseGeometry | None = None,
    pad_pixels: int = 2,
    use_cache: bool = True,
) -> tuple[xr.Dataset, Path]:
    """Extract SME2 layers for the AOI window (or the full grid if aoi is None).

    `source` is a local .h5 path or an HTTPS URL (streamed with the EDL token).
    Returns the dataset (loaded in memory) and the NetCDF cache path.
    """
    with open_source(source) as f, h5py.File(f, "r") as h:
        if GRIDS not in h:
            raise ExtractionError(f"{GRIDS} not found — not an SME2 product?")
        g = h[GRIDS]
        meta = _metadata(h)

        x = g["xCoordinates"][:]
        y = g["yCoordinates"][:]
        dx = float(g["xCoordinateSpacing"][()])
        dy = float(g["yCoordinateSpacing"][()])
        epsg = int(g["projection"].attrs.get("epsg_code", g["projection"][()]))
        if epsg != SME2_EPSG:
            raise ExtractionError(f"Unexpected projection EPSG:{epsg} (expected {SME2_EPSG})")

        if aoi is not None:
            rows, cols = _window(x, y, dx, dy, to_equal_area(aoi).bounds, pad_pixels)
        else:
            rows, cols = slice(0, y.size), slice(0, x.size)

        cache = _cache_path(meta["granule_id"] or Path(source).stem, rows, cols)
        if use_cache and cache.exists():
            cached = xr.load_dataset(cache, engine="h5netcdf")
            cached = cached.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(SME2_EPSG)
            return cached, cache

        def read(name: str, required: bool = True):
            d = _find(g, name)
            if d is None:
                if required:
                    raise ExtractionError(f"Layer {name} missing")
                return None, {}
            attrs = {k: _str(v) for k, v in d.attrs.items() if k not in ("DIMENSION_LIST", "REFERENCE_LIST", "_FillValue")}
            return d[rows, cols], attrs

        sm, sm_attrs = read("soilMoisture")
        unc, unc_attrs = read("soilMoistureUncertainty")
        rqf, rqf_attrs = read("retrievalQualityFlag")
        sqf, sqf_attrs = read("surfaceQualityFlag")
        lc, _ = read("landCover", required=False)
        wf, _ = read("waterbodyFraction", required=False)
        lat = g["latitude"][rows] if "latitude" in g else None
        lon = g["longitude"][cols] if "longitude" in g else None

    def as_float(a):
        a = a.astype("float32")
        a[(a == FLOAT_FILL) | ~np.isfinite(a)] = np.nan
        return a

    dims = ("y", "x")
    data_vars = {
        "soil_moisture": (dims, as_float(sm), {
            "long_name": "Soil moisture", "units": sm_attrs.get("units", ""),
            "source_layer": f"{GRIDS}/soilMoisture",
        }),
        "soil_moisture_uncertainty": (dims, as_float(unc), {
            "long_name": "Soil moisture uncertainty", "units": unc_attrs.get("units", ""),
            "source_layer": f"{GRIDS}/soilMoistureUncertainty",
        }),
        "retrieval_quality_flag": (dims, rqf.astype("int16"), {
            "long_name": "Retrieval quality flag (raw bits)", "flag_fill_value": INT_FILL,
            "flag_bits": "; ".join(f"bit{b}={n}" for b, n in RETRIEVAL_BITS.items()),
            "description": rqf_attrs.get("description", ""),
        }),
        "surface_quality_flag": (dims, sqf.astype("int16"), {
            "long_name": "Surface quality flag (raw bits; meanings undocumented for this product version)",
            "flag_fill_value": INT_FILL,
        }),
    }
    if lc is not None:
        data_vars["land_cover"] = (dims, lc.astype("int8"), {
            "long_name": "Land cover class", "flag_fill_value": LAND_COVER_FILL,
            "flag_values": list(LAND_COVER_CLASSES),
            "flag_meanings": " ".join(n.replace(" ", "_").replace("&", "and").replace("/", "_")
                                      for n in LAND_COVER_CLASSES.values()),
        })
    if wf is not None:
        data_vars["waterbody_fraction"] = (dims, as_float(wf), {"long_name": "Water body fraction", "units": "1"})

    coords = {
        "x": ("x", x[cols], {"units": "m", "standard_name": "projection_x_coordinate"}),
        "y": ("y", y[rows], {"units": "m", "standard_name": "projection_y_coordinate"}),
    }
    if lat is not None:
        coords["latitude"] = ("y", lat.astype("float64"), {"units": "degrees_north"})
    if lon is not None:
        coords["longitude"] = ("x", lon.astype("float64"), {"units": "degrees_east"})

    ds = xr.Dataset(data_vars, coords=coords)
    ds.attrs.update({k: v for k, v in meta.items() if v is not None})
    ds.attrs.update({
        "source": source,
        "grid_spacing_x": dx,
        "grid_spacing_y": dy,
        "window_rows": f"{rows.start}:{rows.stop}",
        "window_cols": f"{cols.start}:{cols.stop}",
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    ds = ds.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(SME2_EPSG)

    tmp = cache.with_suffix(".nc.part")
    ds.to_netcdf(tmp, engine="h5netcdf")
    tmp.replace(cache)
    return ds, cache


# ---------------------------------------------------------------- summaries
def decode_retrieval_flag(rqf: np.ndarray) -> dict[str, np.ndarray]:
    valid = rqf != INT_FILL
    return {name: valid & (((rqf >> bit) & 1) == 1) for bit, name in RETRIEVAL_BITS.items()} | {"flag_valid": valid}


def summarize(ds: xr.Dataset) -> dict:
    sm = ds.soil_moisture.values
    unc = ds.soil_moisture_uncertainty.values
    rqf = ds.retrieval_quality_flag.values
    sqf = ds.surface_quality_flag.values
    n = sm.size
    has_sm = np.isfinite(sm)
    bits = decode_retrieval_flag(rqf)

    def stats(a):
        a = a[np.isfinite(a)]
        if a.size == 0:
            return None
        return {"min": float(a.min()), "max": float(a.max()), "mean": float(a.mean()),
                "median": float(np.median(a)), "std": float(a.std())}

    sqf_valid = sqf != INT_FILL
    surface_bits = {
        f"bit{b}": int((sqf_valid & (((sqf >> b) & 1) == 1)).sum()) for b in range(16)
    }
    surface_bits = {k: v for k, v in surface_bits.items() if v}

    land_cover = {}
    if "land_cover" in ds:
        v, c = np.unique(ds.land_cover.values, return_counts=True)
        land_cover = {LAND_COVER_CLASSES.get(int(k), "No data" if k == LAND_COVER_FILL else f"class {int(k)}"): int(cnt)
                      for k, cnt in zip(v, c)}

    return {
        "window_shape": [int(ds.sizes["y"]), int(ds.sizes["x"])],
        "bounds_epsg6933": [float(b) for b in ds.rio.bounds()],
        "n_pixels": int(n),
        "n_soil_moisture": int(has_sm.sum()),
        "n_recommended": int((has_sm & bits["flag_valid"] & ~bits["not_recommended"]).sum()),
        "n_not_recommended": int((has_sm & bits["not_recommended"]).sum()),
        "algorithms_applied": {k: int((has_sm & bits[k]).sum()) for k in ("pmi_applied", "tsr_applied", "dsg_applied")},
        "soil_moisture": stats(sm),
        "soil_moisture_uncertainty": stats(unc),
        "units": ds.soil_moisture.attrs.get("units"),
        "surface_flag_bits": surface_bits,
        "land_cover": land_cover,
    }
