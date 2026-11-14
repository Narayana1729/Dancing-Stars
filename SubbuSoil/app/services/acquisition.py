"""Step 3 — Data acquisition.

Streaming follows NISAR_Cookbook/notebooks/search_stream_NISAR_asf_search.ipynb:
an fsspec HTTP filesystem with the EDL bearer token, 8 MB background-cached
blocks, opened with xarray/h5netcdf on the `/science/LSAR/SME2/grids` group.

S3 direct access (the Cookbook's s3fs variant) only works from AWS us-west-2,
so HTTPS is used here. Optional DOWNLOAD mode caches whole files locally.
"""
from __future__ import annotations

import contextlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterator

import fsspec
import h5py
import xarray as xr

from app.core.config import get_settings
from app.core.earthdata import get_asf_session
from app.schemas.acquisition import (
    AccessMode,
    AcquiredObservation,
    AcquisitionRequest,
    AcquisitionResponse,
    SelectionStrategy,
)
from app.schemas.discovery import DiscoveryResponse, Observation
from app.services.discovery import search_sme2

SME2_GRIDS = "/science/LSAR/SME2/grids"
CORE_VARIABLES = (
    "soilMoisture",
    "soilMoistureUncertainty",
    "retrievalQualityFlag",
    "surfaceQualityFlag",
    "xCoordinates",
    "yCoordinates",
    "projection",
)
BLOCK_SIZE = 8 * 1024 * 1024  # 8 MB, as in the Cookbook


class AcquisitionError(RuntimeError):
    pass


# ---------------------------------------------------------------- auth / fs
def get_bearer_token() -> str:
    """EDL token from the authenticated ASF session (works for token or user/pass)."""
    auth = get_asf_session().headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AcquisitionError("ASF session has no bearer token")
    return auth.split(" ", 1)[1]


def http_filesystem() -> fsspec.AbstractFileSystem:
    return fsspec.filesystem(
        "http",
        headers={"Authorization": f"Bearer {get_bearer_token()}"},
        cache_type="background",
        block_size=BLOCK_SIZE,
    )


def raw_dir() -> Path:
    d = get_settings().data_dir / "raw"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- selection
def select_observations(
    discovery: DiscoveryResponse, req: AcquisitionRequest
) -> tuple[str, list[Observation]]:
    by_id = {o.granule_id: o for o in discovery.observations}

    if req.granule_ids:
        missing = [g for g in req.granule_ids if g not in by_id]
        if missing:
            raise AcquisitionError(f"Granules not found for this AOI/time window: {missing}")
        chosen = sorted((by_id[g] for g in dict.fromkeys(req.granule_ids)), key=lambda o: o.start_time)
        tracks = {o.track_key for o in chosen}
        if len(tracks) > 1:
            raise AcquisitionError(
                f"Granules span several tracks {sorted(tracks)}; compare observations "
                "from the same track (same viewing geometry and local time)"
            )
        return chosen[0].track_key, chosen

    candidates = [t for t in discovery.tracks if t.n_observations >= 2]
    if req.track_key:
        candidates = [t for t in candidates if t.track_key == req.track_key]
        if not candidates:
            raise AcquisitionError(f"Track {req.track_key} has fewer than 2 observations here")
    if not candidates:
        raise AcquisitionError(
            "No track has 2+ observations covering this AOI; widen the date range "
            "or lower min_coverage"
        )
    track = candidates[0]  # discovery sorts best coverage first
    obs = sorted((by_id[g] for g in track.granule_ids), key=lambda o: o.start_time)

    n = req.max_observations
    if req.strategy == SelectionStrategy.FIRST_LAST:
        picked = [obs[0], obs[-1]] if n == 2 else _evenly_spaced(obs, n)
    elif req.strategy == SelectionStrategy.LATEST:
        picked = obs[-n:]
    else:
        picked = obs[:n]
    return track.track_key, picked


def _evenly_spaced(obs: list[Observation], n: int) -> list[Observation]:
    if len(obs) <= n:
        return obs
    idx = sorted({round(i * (len(obs) - 1) / (n - 1)) for i in range(n)})
    return [obs[i] for i in idx]


# ---------------------------------------------------------------- access
def download(obs: Observation, fs: fsspec.AbstractFileSystem | None = None) -> Path:
    """Cache the granule under DATA_DIR/raw. Skips if a complete copy exists."""
    dest = raw_dir() / f"{obs.granule_id}.h5"
    if dest.exists() and (obs.size_bytes is None or dest.stat().st_size == obs.size_bytes):
        return dest
    fs = fs or http_filesystem()
    tmp = dest.with_suffix(".h5.part")
    with fs.open(obs.https_url, "rb", block_size=BLOCK_SIZE) as src, open(tmp, "wb") as dst:
        while chunk := src.read(BLOCK_SIZE):
            dst.write(chunk)
    os.replace(tmp, dest)
    return dest


@contextlib.contextmanager
def open_source(source: str) -> Iterator:
    """File-like object for a local path or an HTTPS URL (streamed)."""
    if source.startswith(("http://", "https://")):
        with http_filesystem().open(source, "rb") as f:
            yield f
    else:
        with open(source, "rb") as f:
            yield f


@contextlib.contextmanager
def open_sme2_grids(source: str) -> Iterator[xr.Dataset]:
    """Lazily open the SME2 `grids` group as an xarray Dataset (Cookbook settings)."""
    with open_source(source) as f:
        ds = xr.open_dataset(
            f,
            engine="h5netcdf",
            decode_timedelta=False,
            phony_dims="access",
            chunks="auto",
            group=SME2_GRIDS,
        )
        try:
            yield ds
        finally:
            ds.close()


def _verify(item: AcquiredObservation) -> AcquiredObservation:
    """Open remotely/locally and confirm the product has what later steps need."""
    source = item.local_path or item.https_url
    try:
        with open_source(source) as f, h5py.File(f, "r") as h:
            g = h[SME2_GRIDS]
            present = [v for v in CORE_VARIABLES if v in g]
            missing = sorted(set(CORE_VARIABLES) - set(present))
            item.variables = present
            item.grid_shape = list(g["soilMoisture"].shape) if "soilMoisture" in g else None
            if "projection" in g:
                item.epsg = int(g["projection"].attrs.get("epsg_code", g["projection"][()]))
            gid = h["science/LSAR/identification/granuleId"][()]
            gid = gid.decode() if isinstance(gid, bytes) else str(gid)
            if not item.granule_id.startswith(gid[:40]):
                raise AcquisitionError(f"granuleId mismatch in file: {gid}")
            if missing:
                raise AcquisitionError(f"missing variables: {missing}")
            item.verified = True
    except Exception as e:
        item.verified = False
        item.error = f"{type(e).__name__}: {e}"
    return item


def acquire(req: AcquisitionRequest) -> AcquisitionResponse:
    discovery = search_sme2(req)
    track_key, chosen = select_observations(discovery, req)

    items: list[AcquiredObservation] = []
    for o in chosen:
        items.append(
            AcquiredObservation(
                granule_id=o.granule_id,
                start_time=o.start_time,
                track_key=o.track_key,
                aoi_coverage=o.aoi_coverage,
                https_url=o.https_url,
                mode=req.mode,
                size_bytes=o.size_bytes,
            )
        )

    def work(pair):
        o, item = pair
        if req.mode == AccessMode.DOWNLOAD:
            try:
                item.local_path = str(download(o))
            except Exception as e:
                item.error = f"download failed: {type(e).__name__}: {e}"
                return item
        return _verify(item)

    with ThreadPoolExecutor(max_workers=min(4, len(items))) as pool:
        items = list(pool.map(work, zip(chosen, items)))

    days = (items[-1].start_time - items[0].start_time).total_seconds() / 86400
    return AcquisitionResponse(
        aoi=discovery.aoi,
        track_key=track_key,
        n_observations=len(items),
        days_spanned=round(days, 2),
        observations=items,
    )
