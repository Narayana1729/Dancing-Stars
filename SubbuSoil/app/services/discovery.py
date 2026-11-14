"""Step 2 — NISAR SME2 discovery.

Ported from NISAR_Cookbook/notebooks/search_stream_NISAR_asf_search.ipynb:
  * asf.search with dataset=NISAR, processingLevel=SME2,
    productionConfiguration=PR, dataMaturity=PROVISIONAL
  * keep .h5 files, drop QA_STATS
  * keep only the latest CRID per product (same regex as the Cookbook)
"""
import ast
import re
from collections import defaultdict
from datetime import datetime, time, timezone

import asf_search as asf
from shapely.geometry import shape

from app.core.earthdata import get_asf_session
from app.schemas.discovery import (
    AOIInfo,
    DiscoveryRequest,
    DiscoveryResponse,
    Observation,
    TrackGroup,
)
from app.services.aoi import area_km2, coverage_fraction, parse_aoi

PRODUCT_TYPE = "SME2"

# Cookbook regex: (<product id without CRID>)_(<CRID>)
_PRODUCT_CRID_RE = re.compile(
    r"(NISAR_L[123]_PR_[GRS][COSUIM][OFLNE][CGFVW2](?:_[^_]+){9,11})_([PX]\d{5})"
)


class DiscoveryError(RuntimeError):
    pass


def _as_list(v) -> list:
    """asf_search sometimes returns list-valued properties as their str() repr."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.startswith("["):
        try:
            return list(ast.literal_eval(v))
        except (ValueError, SyntaxError):
            return []
    return [v]


def _pick_h5(urls: list[str]) -> str | None:
    for u in urls:
        if u.endswith(".h5") and "QA_STATS" not in u:
            return u
    return None


def _size_bytes(props: dict, file_name: str) -> int | None:
    b = props.get("bytes")
    if isinstance(b, str):
        try:
            b = ast.literal_eval(b)
        except (ValueError, SyntaxError):
            return None
    if isinstance(b, dict) and file_name in b:
        return b[file_name].get("bytes")
    return None


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _cycle_from_name(name: str) -> int:
    # NISAR_L3_PR_SME2_<cycle>_<track>_<dir>_<frame>_...
    return int(name.split("_")[4])


def _latest_crid_only(products: list[asf.ASFProduct]) -> list[asf.ASFProduct]:
    best: dict[str, tuple[str, asf.ASFProduct]] = {}
    for p in products:
        m = _PRODUCT_CRID_RE.search(p.properties.get("sceneName") or "")
        if not m:
            continue
        key, crid = m.groups()
        if key not in best or crid > best[key][0]:
            best[key] = (crid, p)
    return [p for _, p in best.values()]


def search_sme2(req: DiscoveryRequest) -> DiscoveryResponse:
    aoi = parse_aoi(bbox=req.bbox, geometry=req.geometry, wkt=req.wkt)

    opts = {
        "intersectsWith": aoi.wkt,
        "dataset": ["NISAR"],
        "processingLevel": [PRODUCT_TYPE],
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
        raise DiscoveryError(f"ASF search failed: {e}") from e

    observations: list[Observation] = []
    for p in _latest_crid_only(list(results)):
        props = p.properties
        https_url = _pick_h5([props.get("url")] + _as_list(props.get("additionalUrls")))
        if not https_url:
            continue
        footprint = shape(p.geometry)
        cov = coverage_fraction(aoi, footprint)
        if cov < req.min_coverage:
            continue
        name = props["sceneName"]
        direction = props["flightDirection"]
        track, frame = int(props["pathNumber"]), int(props["frameNumber"])
        observations.append(
            Observation(
                granule_id=name,
                start_time=_parse_time(props["startTime"]),
                stop_time=_parse_time(props["stopTime"]),
                flight_direction=direction,
                track=track,
                frame=frame,
                cycle=_cycle_from_name(name),
                orbit=props.get("orbit"),
                track_key=f"{direction[0]}_{track:03d}_{frame:03d}",
                crid=props.get("crid") or _PRODUCT_CRID_RE.search(name).group(2),
                https_url=https_url,
                s3_url=_pick_h5(_as_list(props.get("s3Urls"))),
                size_bytes=_size_bytes(props, props.get("fileName") or https_url.rsplit("/", 1)[-1]),
                aoi_coverage=cov,
                footprint=p.geometry,
            )
        )

    observations.sort(key=lambda o: o.start_time)

    groups: dict[str, list[Observation]] = defaultdict(list)
    for o in observations:
        groups[o.track_key].append(o)
    tracks = [
        TrackGroup(
            track_key=k,
            flight_direction=obs[0].flight_direction,
            track=obs[0].track,
            frame=obs[0].frame,
            n_observations=len(obs),
            mean_aoi_coverage=round(sum(o.aoi_coverage for o in obs) / len(obs), 4),
            granule_ids=[o.granule_id for o in obs],
        )
        for k, obs in groups.items()
    ]
    tracks.sort(key=lambda t: (-t.mean_aoi_coverage, -t.n_observations))

    return DiscoveryResponse(
        aoi=AOIInfo(wkt=aoi.wkt, bounds=list(aoi.bounds), area_km2=round(area_km2(aoi), 2)),
        start_date=req.start_date,
        end_date=req.end_date,
        n_observations=len(observations),
        observations=observations,
        tracks=tracks,
    )
