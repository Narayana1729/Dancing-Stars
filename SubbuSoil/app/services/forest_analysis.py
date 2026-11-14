"""Forest disturbance analysis from NISAR GCOV backscatter (HH and HV).

This module is separate from the soil-moisture pipeline. The soil-moisture code
(discovery for SME2, extraction, change, explanation) is not modified.

Shared infrastructure is imported, not copied:
  aoi.py          AOI parsing, area and coverage
  earthdata.py    authenticated ASF session
  acquisition.py  HTTPS streaming (open_source) and cached download
  subset.py       exact polygon clipping
  align.py        grid alignment across dates
  spatial.py      connected change regions and polygons

Step 1 (this file): product definition only. No processing yet.
The planned steps are listed in PLANNED_STEPS.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timezone

import asf_search as asf
import h5py
import rioxarray  # noqa: F401  (registers .rio)
import xarray as xr
from shapely.geometry import shape

from app.core.config import get_settings
from app.core.earthdata import get_asf_session
from app.schemas.acquisition import AcquiredObservation, AcquisitionRequest, AcquisitionResponse, AccessMode
from app.schemas.discovery import AOIInfo, DiscoveryRequest, DiscoveryResponse, Observation, TrackGroup
from app.services.acquisition import AcquisitionError, download, open_source, select_observations
from app.services.aoi import area_km2, coverage_fraction, parse_aoi
from app.services.discovery import (
    DiscoveryError,
    _as_list,
    _cycle_from_name,
    _latest_crid_only,
    _parse_time,
    _pick_h5,
    _size_bytes,
)


@dataclass(frozen=True)
class GCOVProduct:
    """Where the backscatter lives in a NISAR GCOV granule.

    Taken from NISAR_Cookbook/notebooks (GCOV streaming and subsetting cells):
    the GCOV grids live under science/LSAR/GCOV/grids/frequencyA, and the
    backscatter variables are named by polarisation, e.g. HHHH and HVHV.
    Step 4 verifies these against a real granule before anything relies on them.
    """

    product_type: str = "GCOV"
    group: str = "/science/LSAR/GCOV/grids/frequencyA"
    # GCOV backscatter variables used for forest change (step 5)
    polarisations: tuple[str, ...] = ("HHHH", "HVHV")


@dataclass(frozen=True)
class ForestParams:
    """Settings for forest change (steps 9 and 10)."""

    smooth_px: int = 5               # 5 x 5 pixels (50 m) averaged in linear power before differencing
    change_db: float = 3.0           # |dB change| needed to count as change
    min_region_pixels: int = 20      # 20 pixels = 0.2 ha at 10 m
    worldcover_tree_class: int = 10  # ESA WorldCover class 10 = tree cover


WORLDCOVER_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
                  "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif")


# ---------------------------------------------------------------- step 2: discovery
def search_gcov(req: DiscoveryRequest, product: GCOVProduct = GCOVProduct()) -> DiscoveryResponse:
    """GCOV granules intersecting the AOI. Same ASF options as the SME2 search,
    with processingLevel=GCOV. The helper functions are shared with discovery.py."""
    aoi = parse_aoi(bbox=req.bbox, geometry=req.geometry, wkt=req.wkt)
    opts = {
        "intersectsWith": aoi.wkt,
        "dataset": ["NISAR"],
        "processingLevel": [product.product_type],
        "productionConfiguration": ["PR"],
        "dataMaturity": "PROVISIONAL",
        "start": datetime.combine(req.start_date, time.min, tzinfo=timezone.utc),
        "end": datetime.combine(req.end_date, time.max, tzinfo=timezone.utc),
        "maxResults": req.max_results,
        "session": get_asf_session(),
    }
    if req.flight_direction:
        opts["flightDirection"] = req.flight_direction.value
    try:
        results = asf.search(opts=asf.ASFSearchOptions(**opts))
    except Exception as e:
        raise DiscoveryError(f"ASF GCOV search failed: {e}") from e

    observations: list[Observation] = []
    for p in _latest_crid_only(list(results)):
        props = p.properties
        https_url = _pick_h5([props.get("url")] + _as_list(props.get("additionalUrls")))
        if not https_url:
            continue
        cov = coverage_fraction(aoi, shape(p.geometry))
        if cov < req.min_coverage:
            continue
        name = props["sceneName"]
        direction = props["flightDirection"]
        track, frame = int(props["pathNumber"]), int(props["frameNumber"])
        observations.append(Observation(
            granule_id=name,
            start_time=_parse_time(props["startTime"]),
            stop_time=_parse_time(props["stopTime"]),
            flight_direction=direction,
            track=track,
            frame=frame,
            cycle=_cycle_from_name(name),
            orbit=props.get("orbit"),
            track_key=f"{direction[0]}_{track:03d}_{frame:03d}",
            crid=props.get("crid") or "",
            https_url=https_url,
            s3_url=_pick_h5(_as_list(props.get("s3Urls"))),
            size_bytes=_size_bytes(props, props.get("fileName") or https_url.rsplit("/", 1)[-1]),
            aoi_coverage=cov,
            footprint=p.geometry,
        ))
    observations.sort(key=lambda o: o.start_time)

    groups: dict[str, list[Observation]] = defaultdict(list)
    for o in observations:
        groups[o.track_key].append(o)
    tracks = [
        TrackGroup(
            track_key=k, flight_direction=obs[0].flight_direction, track=obs[0].track, frame=obs[0].frame,
            n_observations=len(obs), mean_aoi_coverage=round(sum(o.aoi_coverage for o in obs) / len(obs), 4),
            granule_ids=[o.granule_id for o in obs],
        )
        for k, obs in groups.items()
    ]
    tracks.sort(key=lambda t: (-t.mean_aoi_coverage, -t.n_observations))
    return DiscoveryResponse(
        aoi=AOIInfo(wkt=aoi.wkt, bounds=list(aoi.bounds), area_km2=round(area_km2(aoi), 2)),
        start_date=req.start_date, end_date=req.end_date,
        n_observations=len(observations), observations=observations, tracks=tracks,
    )


# ---------------------------------------------------------------- step 3: acquisition
GCOV_VARIABLES = ("HHHH", "HVHV")


def verify_gcov(source: str, expected_granule: str | None = None) -> dict:
    """Open the granule's header and check the backscatter layers are present.
    Reads metadata and only the chunks needed for the check (over HTTPS if a URL)."""
    group = GCOVProduct().group.lstrip("/")
    with open_source(source) as f, h5py.File(f, "r") as h:
        if group not in h:
            raise AcquisitionError(f"{group} not found: not a GCOV granule?")
        g = h[group]
        missing = [v for v in GCOV_VARIABLES if v not in g]
        if missing:
            raise AcquisitionError(f"missing backscatter layers: {missing}")
        gid = h["science/LSAR/identification/granuleId"][()]
        gid = gid.decode() if isinstance(gid, bytes) else str(gid)
        if expected_granule and not expected_granule.startswith(gid[:40]):
            raise AcquisitionError(f"granuleId mismatch in file: {gid}")
        return {"granule_id": gid, "layers": [v for v in GCOV_VARIABLES if v in g],
                "shape": list(g["HHHH"].shape)}


def acquire_gcov(req: AcquisitionRequest) -> AcquisitionResponse:
    """Pick two or more GCOV observations on one track and check each one.
    Track selection (select_observations) and downloads are shared with the SME2 path."""
    discovery = search_gcov(req)
    track_key, chosen = select_observations(discovery, req)

    items: list[AcquiredObservation] = []
    for o in chosen:
        item = AcquiredObservation(
            granule_id=o.granule_id, start_time=o.start_time, track_key=o.track_key,
            aoi_coverage=o.aoi_coverage, https_url=o.https_url, mode=req.mode, size_bytes=o.size_bytes,
        )
        try:
            if req.mode == AccessMode.DOWNLOAD:
                item.local_path = str(download(o))  # GCOV is ~6 GB per granule: prefer streaming
            info = verify_gcov(item.local_path or item.https_url, o.granule_id)
            item.verified, item.grid_shape, item.variables = True, info["shape"], info["layers"]
        except Exception as e:
            item.error = f"{type(e).__name__}: {e}"
        items.append(item)

    days = (items[-1].start_time - items[0].start_time).total_seconds() / 86400
    return AcquisitionResponse(aoi=discovery.aoi, track_key=track_key, n_observations=len(items),
                               days_spanned=round(days, 2), observations=items)


PLANNED_STEPS = [
    "2. Discovery: ASF search for GCOV granules (reuse acquisition/discovery patterns)",
    "3. Acquisition: two or more dates of the same forest region",
    "4. HDF5 inspection: confirm HHHH/HVHV layers, CRS, spacing and units",
    "5. Backscatter extraction: read the polarisation layers for the AOI window",
    "6. GeoTIFF conversion: reuse the writer, with GCOV-specific checks",
    "7. Quality masks: GCOV quality layers and NoData",
    "8. Alignment: reuse align.py",
    "9. Change: HH and HV separately",
    "10. Forest disturbance: forest-cover mask, then change regions",
    "11. Validation: independent forest-cover or optical data",
    "12. Visualisation: backscatter, change, locations, explanations",
]


# ---------------------------------------------------------------- step 4: HDF5 inspection
def _attr_text(v) -> str:
    import numpy as np
    if isinstance(v, np.ndarray):
        v = v.item() if v.size == 1 else v.tolist()
    return v.decode() if isinstance(v, bytes) else str(v)


def inspect_gcov(source: str) -> dict:
    """List the GCOV grid layers with shape, dtype, units, fill value and description,
    plus the projection and grid spacing. Reads headers only."""
    group = GCOVProduct().group.lstrip("/")
    out: dict = {"layers": {}, "projection": {}, "grid": {}}
    with open_source(source) as f, h5py.File(f, "r") as h:
        g = h[group]
        for name in g.keys():
            obj = g[name]
            if isinstance(obj, h5py.Dataset):
                out["layers"][name] = {
                    "shape": list(obj.shape), "dtype": str(obj.dtype), "chunks": list(obj.chunks or []),
                    "units": _attr_text(obj.attrs.get("units", "")),
                    "fill": _attr_text(obj.attrs.get("_FillValue", "")),
                    "description": _attr_text(obj.attrs.get("description", ""))[:160],
                }
            else:
                out["layers"][name + "/"] = {"members": list(obj.keys())[:20]}
        for name in ("projection",):
            if name in g:
                out["projection"] = {k: _attr_text(v) for k, v in g[name].attrs.items()
                                     if k in ("epsg_code", "grid_mapping_name", "spatial_ref")}
        for k in ("xCoordinateSpacing", "yCoordinateSpacing"):
            if k in g:
                out["grid"][k] = float(g[k][()])
        for k in ("xCoordinates", "yCoordinates"):
            if k in g:
                c = g[k]
                out["grid"][k] = {"n": int(c.shape[0]), "first": float(c[0]), "last": float(c[-1])}
        out["granule_id"] = _attr_text(h["science/LSAR/identification/granuleId"][()])
    return out


# ---------------------------------------------------------------- step 5: backscatter extraction
GCOV_QUALITY_LAYERS = ("mask", "inputDataExceptionMask", "numberOfLooks", "rtcGammaToSigmaFactor")
MASK_FILL = 255  # GCOV 'mask' fill value: sample not from a valid subswath


def _utm_bounds(aoi, epsg: int) -> tuple[float, float, float, float]:
    from pyproj import Transformer
    from shapely.ops import transform as shp_transform
    tf = Transformer.from_crs(4326, epsg, always_xy=True).transform
    return shp_transform(tf, aoi).bounds


def extract_gcov(source: str, aoi, pad_pixels: int = 2, use_cache: bool = True):
    """Read HHHH and HVHV (linear power) for the AOI window, with GCOV quality layers.

    The layers are stored in the granule's own UTM grid. Only the chunks covering
    the window are read, which matters because a full layer is ~1.1 billion pixels.
    Returns (dataset, cache_path)."""
    import hashlib

    import numpy as np
    import rioxarray  # noqa: F401
    import xarray as xr

    from app.core.config import get_settings
    from app.services.extraction import ExtractionError

    group = GCOVProduct().group.lstrip("/")
    with open_source(source) as f, h5py.File(f, "r") as h:
        g = h[group]
        granule = _attr_text(h["science/LSAR/identification/granuleId"][()])
        epsg = int(g["projection"][()])
        x = g["xCoordinates"][:]
        y = g["yCoordinates"][:]
        dx = float(g["xCoordinateSpacing"][()])
        dy = float(g["yCoordinateSpacing"][()])  # negative: north-up

        minx, miny, maxx, maxy = _utm_bounds(aoi, epsg)
        cols = np.nonzero((x + abs(dx) / 2 >= minx) & (x - abs(dx) / 2 <= maxx))[0]
        rows = np.nonzero((y + abs(dy) / 2 >= miny) & (y - abs(dy) / 2 <= maxy))[0]
        if cols.size == 0 or rows.size == 0:
            raise ExtractionError("AOI does not intersect this GCOV granule")
        r0, r1 = max(rows[0] - pad_pixels, 0), min(rows[-1] + pad_pixels + 1, y.size)
        c0, c1 = max(cols[0] - pad_pixels, 0), min(cols[-1] + pad_pixels + 1, x.size)
        rs, cs = slice(r0, r1), slice(c0, c1)

        cache_dir = get_settings().data_dir / "forest" / "extracted"
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1(f"{r0}:{r1}:{c0}:{c1}".encode()).hexdigest()[:10]
        cache = cache_dir / f"{granule}__{key}.nc"
        if use_cache and cache.exists():
            ds = xr.load_dataset(cache, engine="h5netcdf")
            return ds.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(epsg), cache

        data = {
            "HHHH": (("y", "x"), g["HHHH"][rs, cs].astype("float32"), {"units": "1", "long_name": "HH covariance (linear gamma-0)"}),
            "HVHV": (("y", "x"), g["HVHV"][rs, cs].astype("float32"), {"units": "1", "long_name": "HV covariance (linear gamma-0)"}),
        }
        for name in GCOV_QUALITY_LAYERS:
            if name in g:
                data[name] = (("y", "x"), g[name][rs, cs], {"long_name": name})

    ds = xr.Dataset(data, coords={"x": ("x", x[cs], {"units": "m"}), "y": ("y", y[rs], {"units": "m"})})
    ds.attrs.update({
        "granule_id": granule, "epsg": epsg, "grid_spacing_x": dx, "grid_spacing_y": dy,
        "window_rows": f"{r0}:{r1}", "window_cols": f"{c0}:{c1}",
    })
    ds = ds.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(epsg)
    tmp = cache.with_suffix(".nc.part")
    ds.to_netcdf(tmp, engine="h5netcdf")
    tmp.replace(cache)
    return ds, cache


def summarize_gcov(ds) -> dict:
    """Quick numbers for checking an extraction: valid share, dB ranges, quality counts."""
    import numpy as np
    hh, hv = ds.HHHH.values, ds.HVHV.values
    valid = np.isfinite(hh) & np.isfinite(hv)
    if "mask" in ds:
        valid &= ds["mask"].values != MASK_FILL
    def db_stats(a):
        a = a[valid & (a > 0)]
        if a.size == 0:
            return None
        db = 10 * np.log10(a)
        return {"p5": round(float(np.percentile(db, 5)), 2), "median": round(float(np.median(db)), 2),
                "p95": round(float(np.percentile(db, 95)), 2)}
    out = {
        "window_shape": [int(ds.sizes["y"]), int(ds.sizes["x"])],
        "n_pixels": int(hh.size),
        "n_valid": int(valid.sum()),
        "valid_fraction": round(float(valid.mean()), 4),
        "HH_dB": db_stats(hh),
        "HV_dB": db_stats(hv),
    }
    if "inputDataExceptionMask" in ds:
        out["n_with_exception_flag"] = int((ds["inputDataExceptionMask"].values != 0).sum())
    return out


# ---------------------------------------------------------------- step 7: quality masks
# Invalid-pixel rules use the GCOV layers, not guesses. Each rule is counted separately,
# so the report shows why pixels were removed.
def apply_gcov_quality(ds):
    """Mask invalid GCOV pixels and add dB versions of HH and HV.

    A pixel is valid only if HH and HV are finite and positive, the subswath mask is
    not the fill value (255), and the input-exception flag is zero. Returns the masked
    dataset and a count per rule. Counts overlap, because one pixel can fail several rules."""
    import numpy as np

    hh, hv = ds.HHHH.values, ds.HVHV.values
    finite = np.isfinite(hh) & np.isfinite(hv)
    rules = {
        "non_finite": ~finite,
        "non_positive": finite & ~((hh > 0) & (hv > 0)),
    }
    if "mask" in ds:
        rules["invalid_subswath"] = ds["mask"].values == MASK_FILL
    if "inputDataExceptionMask" in ds:
        rules["data_exception"] = ds["inputDataExceptionMask"].values != 0
    bad = np.zeros(hh.shape, bool)
    for m in rules.values():
        bad |= m
    valid = ~bad

    out = ds.copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out["HHHH"] = ds.HHHH.where(valid)
        out["HVHV"] = ds.HVHV.where(valid)
        out["HH_db"] = (("y", "x"), np.where(valid, 10 * np.log10(np.where(valid, hh, 1.0)), np.nan).astype("float32"),
                        {"units": "dB", "long_name": "HH backscatter (gamma-0)"})
        out["HV_db"] = (("y", "x"), np.where(valid, 10 * np.log10(np.where(valid, hv, 1.0)), np.nan).astype("float32"),
                        {"units": "dB", "long_name": "HV backscatter (gamma-0)"})
    out["valid"] = (("y", "x"), valid.astype("uint8"), {"long_name": "1 = passed all GCOV quality rules"})
    # raw quality layers are not needed after masking and would confuse alignment fill values
    out = out.drop_vars([v for v in GCOV_QUALITY_LAYERS if v in out.data_vars])
    report = {"n_pixels": int(hh.size), "n_valid": int(valid.sum()),
              "valid_fraction": round(float(valid.mean()), 4),
              "removed_by_rule": {k: int(v.sum()) for k, v in rules.items()}}
    return out, report


# ---------------------------------------------------------------- step 6: GeoTIFF conversion
def write_gcov_geotiffs(stack, out_dir) -> list[dict]:
    """One COG per layer per date, with the CRS, spacing and units checked after writing."""
    import numpy as np
    import rasterio
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    expected_epsg = int(stack.attrs["epsg"])
    spacing = abs(float(stack.attrs["grid_spacing_x"]))
    written = []
    for i, t in enumerate(stack.time.values):
        day = str(t)[:10].replace("-", "")
        for layer, units in (("HH_db", "dB"), ("HV_db", "dB"), ("valid", "1")):
            arr = stack[layer].isel(time=i)
            path = out_dir / f"{day}_{layer}.tif"
            arr = arr.astype("float32") if layer != "valid" else arr.astype("uint8")
            arr.rio.write_crs(expected_epsg).rio.to_raster(path, driver="COG", compress="DEFLATE",
                                                          tags={"units": units, "granule_id": str(stack.granule_id.values[i])})
            with rasterio.open(path) as src:
                checks = {
                    "crs_ok": src.crs.to_epsg() == expected_epsg,
                    "spacing_ok": bool(np.isclose(abs(src.res[0]), spacing) and np.isclose(abs(src.res[1]), spacing)),
                    "units": src.tags().get("units"),
                }
            written.append({"file": path.name, "date": day, "layer": layer, **checks})
    bad = [w["file"] for w in written if not (w["crs_ok"] and w["spacing_ok"])]
    if bad:
        raise AcquisitionError(f"GeoTIFF checks failed: {bad}")
    return written


# ---------------------------------------------------------------- step 8: alignment
def align_gcov(datasets: list):
    """Put all dates on one grid. Reuses align.align(): exact when the grids already share
    a lattice (the usual case on one track), otherwise nearest-neighbour reprojection."""
    from app.services.align import align

    return align(datasets)


# ---------------------------------------------------------------- steps 6-8 together
def prepare_forest(req) -> dict:
    """Acquire (3), extract (5), mask (7), align (8) and write GeoTIFFs (6) for one forest AOI.
    Writes DATA_DIR/forest/runs/<run_id>/ with report.json, stack.nc and the COGs."""
    import hashlib
    import json

    from app.core.config import get_settings
    from app.services.aoi import parse_aoi

    aoi = parse_aoi(bbox=req.bbox, geometry=req.geometry, wkt=req.wkt)
    acq = acquire_gcov(req)

    datasets, qc, errors = [], [], []
    for o in acq.observations:
        if not o.verified:
            errors.append(f"{o.granule_id}: {o.error}")
            continue
        ds, _ = extract_gcov(o.local_path or o.https_url, aoi)
        ds.attrs["start_time"] = o.start_time.isoformat()
        ds, report = apply_gcov_quality(ds)
        datasets.append(ds)
        qc.append({"granule_id": o.granule_id, "date": o.start_time.date().isoformat(), **report})
    if len(datasets) < 2:
        raise AcquisitionError(f"Fewer than 2 GCOV observations could be prepared: {errors}")

    stack, align_reports = align_gcov(datasets)
    key = hashlib.sha1(json.dumps(
        {"aoi": aoi.wkt, "granules": sorted(o.granule_id for o in acq.observations)}, sort_keys=True).encode()
    ).hexdigest()[:12]
    out_dir = get_settings().data_dir / "forest" / "runs" / key
    geotiffs = write_gcov_geotiffs(stack, out_dir)
    stack.to_netcdf(out_dir / "stack.nc", engine="h5netcdf")
    result = {
        "run_id": key, "track_key": acq.track_key, "aoi_wkt": aoi.wkt,
        "n_dates": len(datasets), "errors": errors,
        "qc": qc, "alignment": align_reports, "geotiffs": geotiffs, "output_dir": str(out_dir),
    }
    (out_dir / "report.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


# ---------------------------------------------------------------- step 9: change, HH and HV separately
POLARISATION_LAYERS = {"HH": "HHHH", "HV": "HVHV"}


def _multilook(lin, valid, k: int):
    """Mean of valid linear-power pixels in a k x k window. Windows with under half
    valid pixels are left as NaN, so edges and gaps are not filled in from a few pixels."""
    import numpy as np
    from scipy import ndimage

    num = ndimage.uniform_filter(np.where(valid, lin, 0.0).astype("float32"), size=k, mode="nearest")
    den = ndimage.uniform_filter(valid.astype("float32"), size=k, mode="nearest")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0.5, num / den, np.nan)


def change_arrays(ds1, ds2, p: "ForestParams") -> dict:
    """Per-polarisation change in dB (date 2 minus date 1) from multilooked backscatter.

    Returns the dB change for HH and HV, and a class per polarisation:
    -1 decrease at or beyond p.change_db, +1 increase, 0 no significant change."""
    import numpy as np

    v1, v2 = ds1.valid.values == 1, ds2.valid.values == 1
    both = v1 & v2
    out: dict = {"compared": both}
    for pol, var in POLARISATION_LAYERS.items():
        m1 = _multilook(ds1[var].values, v1, p.smooth_px)
        m2 = _multilook(ds2[var].values, v2, p.smooth_px)
        with np.errstate(divide="ignore", invalid="ignore"):
            d = 10 * np.log10(m2) - 10 * np.log10(m1)
        d = np.where(both & np.isfinite(d), d, np.nan).astype("float32")
        cls = np.zeros(d.shape, "int8")
        cls[d <= -p.change_db] = -1
        cls[d >= p.change_db] = 1
        out[f"delta_{pol}_db"] = d
        out[f"class_{pol}"] = cls
    return out


# ---------------------------------------------------------------- step 10: forest mask and disturbances
def tree_cover_mask(transform, crs_epsg: int, width: int, height: int, bounds_ll, p: "ForestParams"):
    """Boolean tree-cover mask on the analysis grid, from ESA WorldCover (2021, 10 m).
    Reads only the 3x3-degree tiles that touch the AOI and warps each onto the analysis grid.
    Returns (mask, tiles_used, tiles_missing)."""
    import math

    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    west, south, east, north = bounds_ll
    mask = np.zeros((height, width), bool)
    used, missing = [], []
    for lat in range(int(math.floor(south / 3) * 3), int(math.ceil(north / 3) * 3), 3):
        for lon in range(int(math.floor(west / 3) * 3), int(math.ceil(east / 3) * 3), 3):
            tile = f"N{lat:02d}E{lon:03d}"
            try:
                with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"), \
                        rasterio.open("/vsicurl/" + WORLDCOVER_URL.format(tile=tile)) as src, \
                        WarpedVRT(src, crs=f"EPSG:{crs_epsg}", transform=transform, width=width,
                                  height=height, resampling=Resampling.nearest, nodata=0) as vrt:
                    arr = vrt.read(1)
            except Exception:
                missing.append(tile)
                continue
            mask |= arr == p.worldcover_tree_class
            used.append(tile)
    return mask, used, missing


def disturbances(change: dict, forest, transform, crs_epsg: int, p: "ForestParams"):
    """Possible forest disturbance: forest pixels with a significant HV decrease.

    HV is the more sensitive polarisation for forest structure, so it defines
    disturbance. Each region also reports how often HH dropped as well. Patches
    smaller than p.min_region_pixels are dropped. Returns (GeoDataFrame, summary)."""
    import geopandas as gpd
    import numpy as np
    from rasterio.features import shapes
    from scipy import ndimage
    from shapely.geometry import shape
    from shapely.ops import unary_union

    compared = change["compared"]
    dist = forest & compared & (change["class_HV"] == -1)
    lab, n = ndimage.label(dist, structure=ndimage.generate_binary_structure(2, 2))
    records = []
    keep: list[int] = []
    if n:
        sizes = np.bincount(lab.ravel(), minlength=n + 1)
        keep = [i for i in range(1, n + 1) if sizes[i] >= p.min_region_pixels]
        slices = ndimage.find_objects(lab)
        for rid in keep:
            sl = slices[rid - 1]
            m = lab[sl] == rid
            hv = change["delta_HV_db"][sl][m]
            hh = change["delta_HH_db"][sl][m]
            records.append({
                "region_id": rid, "n_pixels": int(sizes[rid]),
                "area_ha": round(float(sizes[rid]) * 100 / 10_000, 2),
                "mean_HV_db": round(float(np.nanmean(hv)), 2),
                "mean_HH_db": round(float(np.nanmean(hh)), 2),
                "fraction_HH_also_dropped": round(float(np.mean(hh <= -p.change_db)), 2),
                "geometry": None,
            })
        polys: dict[int, list] = {}
        for geom, val in shapes(lab.astype("int32"), mask=np.isin(lab, keep), transform=transform,
                                connectivity=8):
            polys.setdefault(int(val), []).append(shape(geom))
        for r in records:
            r["geometry"] = unary_union(polys[r["region_id"]]).buffer(0)

    crs = f"EPSG:{crs_epsg}"
    if records:
        gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=crs)
        gdf = gdf.sort_values("area_ha", ascending=False).reset_index(drop=True)
        gdf["rank"] = np.arange(1, len(gdf) + 1)
    else:
        gdf = gpd.GeoDataFrame(columns=["region_id", "n_pixels", "area_ha", "geometry"], geometry="geometry", crs=crs)

    forest_valid = forest & compared
    n_forest = int(forest_valid.sum())
    summary = {
        "forest_area_ha": round(n_forest * 100 / 10_000, 1),
        "disturbed_ha": round(float(dist.sum()) * 100 / 10_000, 1),
        "disturbed_share_of_forest": round(float(dist.sum()) / max(n_forest, 1), 4),
        "n_regions": int(len(gdf)),
        "wetter_forest_ha": round(float((forest_valid & (change["class_HV"] == 1)).sum()) * 100 / 10_000, 1),
        "median_HV_change_db": round(float(np.nanmedian(change["delta_HV_db"][forest_valid])), 2) if n_forest else None,
        "median_HH_change_db": round(float(np.nanmedian(change["delta_HH_db"][forest_valid])), 2) if n_forest else None,
    }
    return gdf, summary


def analyse_forest(run_id: str, p: "ForestParams | None" = None) -> dict:
    """Steps 9 and 10 for a run saved by prepare_forest().

    Compares the first and last date, applies the tree-cover mask and writes:
      forest_change/delta_HH_db.tif, delta_HV_db.tif, disturbances.geojson, summary.json
    """
    import dataclasses
    import json

    import numpy as np
    import rioxarray  # noqa: F401
    import xarray as xr
    from shapely import wkt as shapely_wkt

    p = p or ForestParams()
    run = get_settings().data_dir / "forest" / "runs" / run_id
    if not (run / "stack.nc").exists():
        raise FileNotFoundError(f"no forest run '{run_id}' (run prepare_forest first)")
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))

    stack = xr.load_dataset(run / "stack.nc", engine="h5netcdf")
    epsg = int(stack.attrs["epsg"])
    stack = stack.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(epsg)
    n_dates = stack.sizes["time"]
    if n_dates < 2:
        raise ValueError("Forest change needs at least two dates")
    first, last = stack.isel(time=0), stack.isel(time=n_dates - 1)

    change = change_arrays(first, last, p)                      # step 9
    tf = stack.rio.transform()
    height, width = stack.sizes["y"], stack.sizes["x"]
    forest, tiles_used, tiles_missing = tree_cover_mask(        # step 10: forest mask
        tf, epsg, width, height, shapely_wkt.loads(report["aoi_wkt"]).bounds, p)
    gdf, summary = disturbances(change, forest, tf, epsg, p)    # step 10: disturbances

    out = run / "forest_change"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("delta_HH_db", "delta_HV_db"):
        arr = xr.DataArray(change[name], coords={"y": stack.y.values, "x": stack.x.values}, dims=("y", "x"))
        arr.rio.write_crs(epsg).rio.write_nodata(np.nan, encoded=False).rio.to_raster(
            out / f"{name}.tif", driver="COG", compress="DEFLATE")
    fc = json.loads(gdf.to_crs(4326).to_json()) if len(gdf) else {"type": "FeatureCollection", "features": []}
    (out / "disturbances.geojson").write_text(json.dumps(fc), encoding="utf-8")

    summary.update({
        "run_id": run_id,
        "dates": [str(first.time.values)[:10], str(last.time.values)[:10]],
        "tree_tiles_used": tiles_used,
        "tree_tiles_missing": tiles_missing,
        "params": dataclasses.asdict(p),
        "outputs": str(out),
    })
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


# ---------------------------------------------------------------- Sentinel-2 NDVI on the forest grid
def forest_ndvi(aoi, t, transform, crs_epsg: int, width: int, height: int,
                window_days: int = 30, max_cloud: float = 60):
    """NDVI on the forest grid (UTM), from the same Sentinel-2 scenes and SCL cloud mask
    used by the soil analysis.

    A separate reader is needed because the soil reader hard-codes the EASE grid (EPSG:6933);
    the scene choice and the reflectance scaling are reused from vegetation.py."""
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    from app.services.context.vegetation import GDAL_ENV, SCL_VALID, _scale_offset, choose_scene

    day, items, coverage, cloud = choose_scene(aoi, t, window_days, max_cloud)

    def warp(href, resampling):
        with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src, WarpedVRT(
            src, crs=f"EPSG:{crs_epsg}", transform=transform, width=width, height=height,
            resampling=resampling, nodata=0,
        ) as vrt:
            return vrt.read(1)

    ndvi = np.full((height, width), np.nan, "float32")
    masked = 0
    for it in items:
        red_dn = warp(it.assets["red"].href, Resampling.average)
        nir_dn = warp(it.assets["nir"].href, Resampling.average)
        scl = warp(it.assets["scl"].href, Resampling.mode)
        rs, ro = _scale_offset(it, "red")
        ns, no = _scale_offset(it, "nir")
        red = red_dn.astype("float32") * rs + ro
        nir = nir_dn.astype("float32") * ns + no
        has = (red_dn > 0) & (nir_dn > 0)
        ok = has & np.isin(scl, SCL_VALID)
        masked += int((has & ~ok).sum())
        with np.errstate(divide="ignore", invalid="ignore"):
            v = (nir - red) / (nir + red)
        fill = ok & np.isnan(ndvi) & np.isfinite(v)
        ndvi[fill] = np.clip(v[fill], -1, 1)
    meta = {"date": day, "scene_cloud_cover_pct": cloud, "aoi_coverage": coverage,
            "tiles": [it.id for it in items], "masked_pixels": masked}
    return ndvi, meta


# ---------------------------------------------------------------- step 11: validation
def validate_disturbances(run_id: str, min_ha: float = 1.0, ndvi_drop: float = 0.1,
                          window_days: int = 45, max_cloud: float = 60) -> dict:
    """Check candidate disturbances against Sentinel-2 NDVI at the same two dates.

    Optical vegetation is independent of the radar. A real clearing should lower NDVI
    inside the region. Each candidate region (at least min_ha) is compared with the
    forest that was not flagged, which shows how often an unflagged patch also drops.
    Writes forest_change/validation.json."""
    import json
    from datetime import datetime

    import geopandas as gpd
    import numpy as np
    from rasterio.features import geometry_mask
    from shapely import wkt as shapely_wkt

    run = get_settings().data_dir / "forest" / "runs" / run_id
    out = run / "forest_change"
    if not (out / "disturbances.geojson").exists():
        raise FileNotFoundError("run analyse_forest first")
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    stack = xr.load_dataset(run / "stack.nc", engine="h5netcdf")
    epsg = int(stack.attrs["epsg"])
    stack = stack.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(epsg)
    tf = stack.rio.transform()
    H, W = stack.sizes["y"], stack.sizes["x"]
    aoi = shapely_wkt.loads(report["aoi_wkt"])
    t1 = datetime.fromisoformat(str(stack.time.values[0])[:19])
    t2 = datetime.fromisoformat(str(stack.time.values[-1])[:19])

    n1, m1 = forest_ndvi(aoi, t1, tf, epsg, W, H, window_days, max_cloud)
    n2, m2 = forest_ndvi(aoi, t2, tf, epsg, W, H, window_days, max_cloud)
    d_ndvi = n2 - n1
    both = np.isfinite(d_ndvi)

    forest, _, _ = tree_cover_mask(tf, epsg, W, H, aoi.bounds, ForestParams())
    gdf = gpd.read_file(out / "disturbances.geojson")
    if len(gdf):
        gdf = gdf.to_crs(epsg)
    cand = gdf[gdf.area_ha >= min_ha] if len(gdf) else gdf

    flagged = np.zeros((H, W), bool)
    rows = []
    for _, r in cand.iterrows():
        m = geometry_mask([r.geometry], out_shape=(H, W), transform=tf, invert=True)
        flagged |= m
        vals = d_ndvi[m & both]
        if vals.size == 0:
            rows.append({"region_id": int(r.region_id), "area_ha": float(r.area_ha), "ndvi_checked": False})
            continue
        rows.append({
            "region_id": int(r.region_id), "area_ha": float(r.area_ha), "ndvi_checked": True,
            "mean_ndvi_change": round(float(vals.mean()), 3),
            "fraction_ndvi_drop": round(float((vals <= -ndvi_drop).mean()), 3),
            "confirmed_by_optics": bool(vals.mean() <= -ndvi_drop),
        })

    background = forest & both & ~flagged
    bg = d_ndvi[background]
    bg_drop = float((bg <= -ndvi_drop).mean()) if bg.size else None
    checked = [r for r in rows if r.get("ndvi_checked")]
    confirmed = [r for r in checked if r["confirmed_by_optics"]]
    fl = float(np.mean([r["fraction_ndvi_drop"] for r in checked])) if checked else None

    result = {
        "run_id": run_id,
        "ndvi_dates": [m1["date"], m2["date"]],
        "ndvi_scene_cloud_pct": [m1["scene_cloud_cover_pct"], m2["scene_cloud_cover_pct"]],
        "min_region_ha": min_ha,
        "ndvi_drop_threshold": ndvi_drop,
        "n_candidates": int(len(cand)),
        "n_checked": len(checked),
        "n_confirmed_by_optics": len(confirmed),
        "share_confirmed": round(len(confirmed) / len(checked), 3) if checked else None,
        "unflagged_forest_drop_rate": round(bg_drop, 3) if bg_drop is not None else None,
        "candidate_drop_rate": round(fl, 3) if fl is not None else None,
        "regions": rows,
    }
    (out / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


# ---------------------------------------------------------------- step 12: visualisation and explanation
FOREST_LAYERS = {
    "hh_t1": ("HH backscatter, first date (dB)", "viridis", -20.0, 0.0),
    "hv_t1": ("HV backscatter, first date (dB)", "viridis", -25.0, -5.0),
    "hh_t2": ("HH backscatter, last date (dB)", "viridis", -20.0, 0.0),
    "hv_t2": ("HV backscatter, last date (dB)", "viridis", -25.0, -5.0),
    "delta_hh": ("HH change (dB, last minus first)", "RdBu", -6.0, 6.0),
    "delta_hv": ("HV change (dB, last minus first)", "RdBu", -6.0, 6.0),
}


def _forest_run_dir(run_id: str) -> Path:
    run = get_settings().data_dir / "forest" / "runs" / run_id
    if not (run / "report.json").exists():
        raise FileNotFoundError(f"no forest run '{run_id}'")
    return run


def forest_layer_png(run_id: str, layer: str) -> bytes:
    """One forest layer as a transparent PNG in EPSG:4326, for a web map overlay."""
    import io

    import numpy as np
    import rioxarray  # noqa: F401
    import xarray as xr
    from matplotlib import colormaps
    from matplotlib.image import imsave

    if layer not in FOREST_LAYERS:
        raise KeyError(f"unknown layer '{layer}'")
    _, cmap, lo, hi = FOREST_LAYERS[layer]
    run = _forest_run_dir(run_id)
    if layer.startswith("delta"):
        path = run / "forest_change" / f"delta_{layer.split('_')[1].upper()}_db.tif"
        da = rioxarray.open_rasterio(path, masked=True).squeeze("band", drop=True)
    else:
        stack = xr.load_dataset(run / "stack.nc", engine="h5netcdf")
        idx = 0 if layer.endswith("t1") else stack.sizes["time"] - 1
        var = "HH_db" if "hh" in layer else "HV_db"
        da = stack[var].isel(time=idx).rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(
            int(stack.attrs["epsg"]))
    da = da.rio.reproject("EPSG:4326", shape=(1100, 1100))  # web-map size; full grid would be ~15 MB
    arr = da.values.astype("float32")
    norm = np.clip((np.nan_to_num(arr, nan=lo) - lo) / (hi - lo), 0, 1)
    rgba = colormaps[cmap](norm)
    rgba[..., 3] = np.where(np.isfinite(arr), 0.85, 0.0)
    buf = io.BytesIO()
    imsave(buf, rgba, format="png")
    return buf.getvalue()


def forest_overlay_bounds(run_id: str, layer: str) -> dict:
    import rioxarray  # noqa: F401
    import xarray as xr

    run = _forest_run_dir(run_id)
    if layer.startswith("delta"):
        da = rioxarray.open_rasterio(run / "forest_change" / f"delta_{layer.split('_')[1].upper()}_db.tif")
    else:
        stack = xr.load_dataset(run / "stack.nc", engine="h5netcdf")
        da = stack.HH_db.isel(time=0).rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(int(stack.attrs["epsg"]))
    west, south, east, north = da.rio.reproject("EPSG:4326").rio.bounds()
    _, _, lo, hi = FOREST_LAYERS[layer]
    return {"layer": layer, "label": FOREST_LAYERS[layer][0], "bounds": [[south, west], [north, east]],
            "value_range": [lo, hi]}


def forest_explanation(summary: dict, validation: dict | None) -> dict:
    """Plain-language findings from the measured numbers. Each sentence cites its number."""
    lines = []
    lines.append(
        f"The forest covers {summary['forest_area_ha']:,.0f} ha of the area. "
        f"{summary['disturbed_ha']:.0f} ha ({100 * summary['disturbed_share_of_forest']:.2f}%) shows a significant "
        f"HV decrease of at least {summary['params']['change_db']:g} dB, in {summary['n_regions']} patches (most under 1 ha)."
    )
    lines.append(
        f"The median change across the forest is {summary['median_HV_change_db']:+.2f} dB for HV and "
        f"{summary['median_HH_change_db']:+.2f} dB for HH, which is small compared with the 3 dB threshold."
    )
    if validation and validation.get("n_checked"):
        conf, n = validation["n_confirmed_by_optics"], validation["n_checked"]
        lines.append(
            f"Of the {validation['n_candidates']} patches of at least {validation['min_region_ha']:g} ha, "
            f"{n} could be checked against Sentinel-2 NDVI. {conf} of them show a vegetation drop of "
            f"{validation['ndvi_drop_threshold']:g} or more: these are the strongest candidates for clearing or harvest."
        )
        lines.append(
            f"Across unflagged forest, {100 * (validation['unflagged_forest_drop_rate'] or 0):.1f}% of pixels show the "
            f"same NDVI drop, so the optical check is meaningful."
        )
        if n - conf > 0:
            lines.append(
                f"The other {n - conf} checked patch(es) show no vegetation drop. The radar signal there is more "
                f"likely soil moisture or seasonal change than loss of forest."
            )
    elif validation:
        lines.append("No candidate patch could be checked against optical imagery, because no cloud-free scene was found.")
    lines.append(
        "Possible causes to check: clearing or harvest (HH and HV both drop, NDVI drops), changes in soil moisture or "
        "understorey wetness (HV and HH move together, NDVI does not), and leaf growth, which raises backscatter rather than lowering it."
    )
    lines.append(
        "Caveats: the forest mask is WorldCover 2021, a single snapshot. The two dates are 2 months apart in "
        "the monsoon, which changes soil moisture as well as forest structure. Treat results as candidates for field checking."
    )
    return {"lines": lines, "text": "\n\n".join(lines)}
