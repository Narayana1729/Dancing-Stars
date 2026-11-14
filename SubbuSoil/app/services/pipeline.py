"""Runs steps 3-7: acquire -> extract -> subset -> preprocess -> align -> save.

Outputs under DATA_DIR/processed/<run_id>/:
  stack.nc                              aligned (time, y, x) analysis-ready stack
  <YYYYMMDD>_soil_moisture.tif          QC'd soil moisture, Cloud-Optimized GeoTIFF
  <YYYYMMDD>_mask_reason.tif            QC bitmask (0 = valid)
  manifest.json                         request + reports
"""
from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.schemas.processing import (
    AlignmentReport,
    GridInfo,
    PreparedObservation,
    PrepareRequest,
    PrepareResponse,
    QCReport,
)
from app.services.acquisition import AcquisitionError, acquire
from app.services.align import align
from app.services.aoi import parse_aoi
from app.services.extraction import extract_sme2
from app.services.preprocess import preprocess
from app.services.subset import subset_to_aoi


def _run_id(aoi_wkt: str, granules: list[str], req: PrepareRequest) -> str:
    key = json.dumps(
        {"aoi": aoi_wkt, "g": sorted(granules), "qc": req.qc.model_dump(), "t": req.all_touched},
        sort_keys=True,
    )
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def prepare(req: PrepareRequest, report=None) -> PrepareResponse:
    report = report or (lambda *a, **k: None)
    aoi = parse_aoi(bbox=req.bbox, geometry=req.geometry, wkt=req.wkt)
    report("Finding and checking granules on ASF", 2, "")
    acq = acquire(req)
    report("Granules found", 8, f"{len(acq.observations)} observations selected")

    def process(o):
        rec = PreparedObservation(granule_id=o.granule_id, start_time=o.start_time)
        if not o.verified:
            rec.error = f"not acquired: {o.error}"
            return rec, None
        try:
            ds, _ = extract_sme2(o.local_path or o.https_url, aoi)       # step 4
            ds = subset_to_aoi(ds, aoi, all_touched=req.all_touched)     # step 5
            ds, qc = preprocess(ds, req.qc)                              # step 6
            rec.qc = QCReport(**qc)
            return rec, ds
        except Exception as e:
            rec.error = f"{type(e).__name__}: {e}"
            return rec, None

    done = {"n": 0}
    lock = threading.Lock()

    def process_and_report(o):
        out = process(o)
        with lock:
            done["n"] += 1
            report("Extracting and cleaning", 10 + 25 * done["n"] / len(acq.observations),
                   f"{done['n']} of {len(acq.observations)} observations")
        return out

    with ThreadPoolExecutor(max_workers=min(4, len(acq.observations))) as pool:
        results = list(pool.map(process_and_report, acq.observations))

    good = [(r, ds) for r, ds in results if ds is not None]
    if len(good) < 2:
        errs = [r.error for r, _ in results if r.error]
        raise AcquisitionError(f"Fewer than 2 observations could be prepared: {errs}")

    report("Aligning grids", 37, "")
    stack, align_reports = align([ds for _, ds in good])                # step 7
    by_gid = {a["granule_id"]: a for a in align_reports}

    run_id = _run_id(aoi.wkt, [r.granule_id for r, _ in good], req)
    out_dir = get_settings().data_dir / "processed" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    for rec, _ in good:
        a = by_gid.get(rec.granule_id)
        rec.alignment = AlignmentReport(**a) if a else None

    report("Saving rasters", 40, "")
    for i, t in enumerate(stack.time.values):
        gid = str(stack.granule_id.values[i])
        rec = next(r for r, _ in good if r.granule_id == gid)
        day = pd.Timestamp(t).strftime("%Y%m%d")
        sm_path = out_dir / f"{day}_soil_moisture.tif"
        mr_path = out_dir / f"{day}_mask_reason.tif"
        sm = stack.soil_moisture.isel(time=i).astype("float32").rio.write_nodata(np.nan, encoded=False)
        sm.rio.to_raster(sm_path, driver="COG", compress="DEFLATE")
        stack.mask_reason.isel(time=i).astype("uint8").rio.to_raster(mr_path, driver="COG", compress="DEFLATE")
        rec.soil_moisture_cog, rec.mask_reason_cog = str(sm_path), str(mr_path)

    nc_path = out_dir / "stack.nc"
    tmp = nc_path.with_suffix(".nc.part")
    stack.to_netcdf(tmp, engine="h5netcdf")
    tmp.replace(nc_path)

    common_valid = (stack.valid == 1).all("time")
    n_common = int(common_valid.sum())
    pixel_km2 = abs(stack.attrs["grid_spacing_x"] * stack.attrs["grid_spacing_y"]) / 1e6
    rx, ry = stack.rio.resolution()
    t = stack.rio.transform()

    observations = [r for r, _ in results]
    resp = PrepareResponse(
        run_id=run_id,
        aoi=acq.aoi,
        track_key=acq.track_key,
        grid=GridInfo(
            crs=str(stack.rio.crs),
            shape=[int(stack.sizes["y"]), int(stack.sizes["x"])],
            resolution_m=[abs(rx), abs(ry)],
            bounds=[float(b) for b in stack.rio.bounds()],
            transform=[t.a, t.b, t.c, t.d, t.e, t.f],
            pixel_area_km2=round(pixel_km2, 6),
        ),
        n_observations=len(good),
        n_common_valid_pixels=n_common,
        common_valid_area_km2=round(n_common * pixel_km2, 2),
        observations=observations,
        stack_netcdf=str(nc_path),
        output_dir=str(out_dir),
    )
    (out_dir / "manifest.json").write_text(
        json.dumps({"request": req.model_dump(mode="json"), "result": resp.model_dump(mode="json")}, indent=2),
        encoding="utf-8",
    )
    return resp
