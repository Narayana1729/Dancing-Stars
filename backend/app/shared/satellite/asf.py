"""ASF DAAC search/download provider (NISAR and Sentinel-1).

Search is public (no credentials). Download requires NASA Earthdata
authentication via the EARTHDATA_TOKEN environment variable or ~/.netrc.
Credentials are never logged or written to disk by this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.shared.satellite.base import (
    Mission,
    SarProduct,
    SatelliteProvider,
    SceneQuery,
    SceneRecord,
)

ASF_SEARCH_URL = "https://api.daac.asf.alaska.edu/services/search/param"


class AuthenticationRequired(RuntimeError):
    """Raised when a download is attempted without Earthdata credentials."""


@dataclass(frozen=True)
class AsfScene(SceneRecord):
    size_bytes: int | None = None
    flight_direction: str | None = None
    path: int | None = None
    frame: int | None = None
    polarizations: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


def _query_params(q: SceneQuery, max_results: int) -> dict[str, str]:
    b = q.bbox
    p = {
        "intersectsWith": f"POLYGON(({b.west} {b.south},{b.east} {b.south},{b.east} {b.north},"
        f"{b.west} {b.north},{b.west} {b.south}))",
        "start": f"{q.start.isoformat()}T00:00:00Z",
        "end": f"{q.end.isoformat()}T23:59:59Z",
        "output": "geojson",
        "maxResults": str(max_results),
    }
    if q.mission is Mission.NISAR:
        p["dataset"] = "NISAR"
        p["processingLevel"] = q.product.value
    else:
        p["platform"] = "S1"
        p["processingLevel"] = q.product.value
    return p


def _parse(feature: dict) -> AsfScene:
    pr = feature["properties"]
    sizes = pr.get("bytes")
    size = None
    if isinstance(sizes, dict):
        main = sizes.get(pr.get("fileName"))
        size = main.get("bytes") if main else None
    elif isinstance(sizes, (int, float)):
        size = int(sizes)
    pols = pr.get("mainBandPolarization") or ([pr["polarization"]] if pr.get("polarization") else [])
    mission = Mission.NISAR if pr.get("platform") == "NISAR" else Mission.SENTINEL_1
    level = pr.get("processingLevel", "")
    try:
        product = SarProduct(level)
    except ValueError:
        product = SarProduct.GRD_HD
    return AsfScene(
        scene_id=pr.get("sceneName") or pr["fileID"],
        mission=mission,
        product=product,
        acquired=datetime.fromisoformat(pr["startTime"].replace("Z", "+00:00")).date(),
        download_url=pr.get("url"),
        size_bytes=size,
        flight_direction=pr.get("flightDirection"),
        path=pr.get("pathNumber"),
        frame=pr.get("frameNumber"),
        polarizations=tuple(pols),
        extra={
            k: pr.get(k)
            for k in ("startTime", "stopTime", "orbit", "sensor", "frameCoverage", "rangeBandwidth",
                      "crid", "collectionName", "processingDate", "beamModeType", "fileName", "md5sum")
        },
    )


class AsfProvider(SatelliteProvider):
    def search(self, query: SceneQuery, max_results: int = 200) -> list[AsfScene]:
        url = f"{ASF_SEARCH_URL}?{urllib.parse.urlencode(_query_params(query, max_results))}"
        with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 (fixed https host)
            data = json.load(r)
        scenes = [_parse(f) for f in data.get("features", [])]
        return sorted(scenes, key=lambda s: s.extra.get("startTime") or "")

    def download(self, scene: SceneRecord, dest_dir: str) -> str:
        import requests  # imported lazily: only downloads need it

        if not scene.download_url:
            raise ValueError("scene has no download URL")
        token = os.getenv("EARTHDATA_TOKEN")
        if not token and not (Path.home() / ".netrc").exists():
            raise AuthenticationRequired(
                "Set EARTHDATA_TOKEN or create ~/.netrc for urs.earthdata.nasa.gov before downloading."
            )
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        out = dest / scene.download_url.rsplit("/", 1)[-1]
        part = out.with_suffix(out.suffix + ".part")
        session = requests.Session()
        if token:
            session.headers["Authorization"] = f"Bearer {token}"  # requests strips it on cross-host redirects
        with session.get(scene.download_url, stream=True, timeout=60, allow_redirects=True) as r:
            r.raise_for_status()
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        part.replace(out)
        return str(out)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = ["AsfProvider", "AsfScene", "AuthenticationRequired", "sha256_of", "now_iso", "date"]

