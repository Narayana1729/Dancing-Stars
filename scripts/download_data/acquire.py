#!/usr/bin/env python3
"""Search / inspect / download / verify SAR observations from ASF DAAC.

Run from the repo root with the backend venv:
  backend/.venv/bin/python scripts/download_data/acquire.py search --mission nisar --product GCOV \
      --bbox -63.5 -10.5 -62.5 -9.5 --start 2026-01-01 --end 2026-11-13
  ... download --scene-id <ID> [--yes]      (prints size first; needs --yes to proceed)
  ... verify  --file data/raw/<file>.h5

Downloads need EARTHDATA_TOKEN (env) or ~/.netrc. Credentials are never printed or stored.
Files go to data/raw/ (git-ignored); acquisitions are logged to data/raw/manifest.jsonl.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.shared.geospatial.bbox import BoundingBox  # noqa: E402
from app.shared.satellite.asf import AsfProvider, AuthenticationRequired, now_iso, sha256_of  # noqa: E402
from app.shared.satellite.base import Mission, SarProduct, SceneQuery  # noqa: E402

def _load_env(path=ROOT / ".env"):
    """Load KEY=VALUE lines from .env into os.environ (existing variables win). Never prints values."""
    import os
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.jsonl"
MISSIONS = {"nisar": Mission.NISAR, "sentinel1": Mission.SENTINEL_1}


def _query(a) -> SceneQuery:
    w, s, e, n = a.bbox
    return SceneQuery(BoundingBox(w, s, e, n), date.fromisoformat(a.start), date.fromisoformat(a.end),
                      MISSIONS[a.mission], SarProduct(a.product))


def _mb(b):
    return "?" if b is None else f"{b / 2**20:,.0f} MB"


def cmd_search(a):
    scenes = AsfProvider().search(_query(a), a.max_results)
    print(f"{len(scenes)} scene(s)")
    for s in scenes:
        print(f"{s.extra['startTime']}  {s.flight_direction[:3] if s.flight_direction else '?'}  "
              f"path {s.path} frame {s.frame}  pol {','.join(s.polarizations) or '?'}  {_mb(s.size_bytes)}  {s.scene_id}")


def _find(a):
    for s in AsfProvider().search(_query(a), a.max_results):
        if s.scene_id == a.scene_id:
            return s
    sys.exit(f"scene {a.scene_id} not found with these search parameters")


def cmd_info(a):
    s = _find(a)
    print(json.dumps({"scene_id": s.scene_id, "mission": s.mission.value, "product": s.product.value,
                      "acquired": s.acquired.isoformat(), "size": _mb(s.size_bytes), "path": s.path, "frame": s.frame,
                      "direction": s.flight_direction, "polarizations": s.polarizations, "url": s.download_url,
                      **s.extra}, indent=2, default=str))


def cmd_download(a):
    s = _find(a)
    print(f"{s.scene_id}\nsize: {_mb(s.size_bytes)}")
    if not a.yes:
        sys.exit("Not downloading. Re-run with --yes to confirm.")
    try:
        path = AsfProvider().download(s, str(RAW))
    except AuthenticationRequired as e:
        sys.exit(f"AUTH REQUIRED: {e}")
    rec = {"scene_id": s.scene_id, "mission": s.mission.value, "product": s.product.value,
           "acquired": s.acquired.isoformat(), "url": s.download_url, "file": path,
           "bytes": Path(path).stat().st_size, "expected_bytes": s.size_bytes,
           "sha256": sha256_of(path), "downloaded_at": now_iso()}
    with open(MANIFEST, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print("saved", path, "| size ok:", rec["bytes"] == s.size_bytes)


def cmd_verify(a):
    p = Path(a.file)
    ok = p.exists()
    recs = [json.loads(l) for l in open(MANIFEST)] if MANIFEST.exists() else []
    rec = next((r for r in recs if r["file"].endswith(p.name)), None)
    print("exists:", ok)
    if ok:
        manifest_size = rec.get("bytes") if rec else None
        expected_size = rec.get("expected_bytes", manifest_size) if rec else None
        print("size:", p.stat().st_size, "| manifest size:", manifest_size, "| expected:", expected_size)
        print("sha256 matches manifest:", bool(rec) and sha256_of(str(p)) == rec.get("sha256"))
        if p.suffix == ".h5":
            import h5py
            with h5py.File(p) as f:
                print("valid HDF5; top-level groups:", list(f))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("search", cmd_search), ("info", cmd_info), ("download", cmd_download)):
        sp = sub.add_parser(name)
        sp.add_argument("--mission", choices=MISSIONS, default="nisar")
        sp.add_argument("--product", default="GCOV")
        sp.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
        sp.add_argument("--start", required=True)
        sp.add_argument("--end", required=True)
        sp.add_argument("--max-results", type=int, default=200)
        if name != "search":
            sp.add_argument("--scene-id", required=True)
        if name == "download":
            sp.add_argument("--yes", action="store_true", help="confirm download after reviewing size")
        sp.set_defaults(fn=fn)
    sp = sub.add_parser("verify")
    sp.add_argument("--file", required=True)
    sp.set_defaults(fn=cmd_verify)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

