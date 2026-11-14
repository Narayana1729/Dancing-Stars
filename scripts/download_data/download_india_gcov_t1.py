#!/usr/bin/env python3
"""Download the second NISAR L2 GCOV HDF5 measurement granule for Similipal, India (t1).

Destination: data/raw/India/
Target Granule: Track 98, Frame 12 (Ascending), 2026-04-21T23:37:20Z (48-day repeat from t0)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
import h5py
import requests

ROOT = Path(__file__).resolve().parents[2]
DEST_DIR = ROOT / "data" / "raw" / "India"
MANIFEST = ROOT / "data" / "raw" / "manifest.jsonl"

NISAR_URL = (
    "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/"
    "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001/"
    "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"
)
FILE_NAME = "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001.h5"
SCENE_ID = "NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001"


def get_token() -> str:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("EARTHDATA_TOKEN="):
                tok = line.split("=", 1)[1].strip()
                if tok:
                    return tok
    tok = os.getenv("EARTHDATA_TOKEN")
    if tok:
        return tok
    raise RuntimeError("EARTHDATA_TOKEN not found in .env or environment")


def download_india_gcov_t1() -> str:
    token = get_token()
    dest = DEST_DIR / FILE_NAME
    part = DEST_DIR / (FILE_NAME + ".part")
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        print(f"File already exists: {dest} ({dest.stat().st_size:,} bytes)")
    else:
        downloaded = part.stat().st_size if part.exists() else 0

        s = requests.Session()
        h = {"Authorization": f"Bearer {token}"}
        resp = s.get(NISAR_URL, headers=h, allow_redirects=False)
        while resp.status_code in (301, 302, 303, 307):
            new_url = resp.headers["Location"]
            if "s3.amazonaws.com" in new_url or "s3-" in new_url or "cloudfront.net" in new_url:
                h.pop("Authorization", None)
            else:
                h["Authorization"] = f"Bearer {token}"
            if downloaded > 0:
                h["Range"] = f"bytes={downloaded}-"
            resp = s.get(new_url, headers=h, allow_redirects=False, stream=True)

        if downloaded > 0 and resp.status_code == 206:
            print(f"Resuming download from byte {downloaded:,}...")
            total_size = downloaded + int(resp.headers.get("Content-Length", 0))
        elif resp.status_code == 200:
            downloaded = 0
            total_size = int(resp.headers.get("Content-Length", 0))
        else:
            raise RuntimeError(f"Unexpected response status: {resp.status_code}")

        print(f"Starting download of Indian GCOV Granule t1: {FILE_NAME}")
        print(f"Target size: {total_size / 1024**3:.2f} GB ({total_size:,} bytes)")
        print(f"Destination: {dest}")

        chunk_size = 8 * 1024 * 1024  # 8 MB chunks
        last_log = time.time()
        t_start = time.time()
        bytes_session = 0

        mode = "ab" if downloaded > 0 else "wb"
        with open(part, mode) as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    bytes_session += len(chunk)
                    now = time.time()
                    if now - last_log > 10:
                        elapsed = now - t_start
                        rate = (bytes_session / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                        pct = (downloaded / total_size) * 100 if total_size else 0
                        eta = (total_size - downloaded) / (rate * 1024 * 1024) if rate > 0 else 0
                        print(
                            f"Progress: {pct:5.1f}% | {downloaded / 1024**3:.2f}/{total_size / 1024**3:.2f} GB "
                            f"| Speed: {rate:5.1f} MB/s | ETA: {int(eta // 60)}m {int(eta % 60)}s"
                        )
                        last_log = now

        part.rename(dest)
        print(f"\nDownload complete: {dest} ({dest.stat().st_size:,} bytes)")

    print("Computing SHA256 integrity hash...")
    sha = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            sha.update(chunk)
    digest = sha.hexdigest()
    print(f"SHA256: {digest}")

    print("Verifying HDF5 file integrity...")
    with h5py.File(dest, "r") as h5:
        top_groups = list(h5.keys())
        grids = list(h5["/science/LSAR/GCOV/grids"].keys())
        pols_a = list(h5["/science/LSAR/GCOV/grids/frequencyA"].keys())
        print(f"  Valid HDF5 structure: {top_groups}")
        print(f"  Available grid frequencies: {grids}")
        print(f"  Frequency A datasets: {pols_a}")

    # Check existing manifest entries to avoid duplicates
    manifest_records = []
    if MANIFEST.exists():
        for line in MANIFEST.read_text().splitlines():
            if line.strip():
                try:
                    manifest_records.append(json.loads(line))
                except Exception:
                    pass

    if not any(r.get("scene_id") == SCENE_ID for r in manifest_records):
        rec = {
            "scene_id": SCENE_ID,
            "region": "Similipal Tiger Reserve, Odisha, India",
            "file": str(dest.relative_to(ROOT)),
            "type": "Full GCOV Measurement Product",
            "bytes": dest.stat().st_size,
            "sha256": digest,
            "acquired": "2026-04-21T23:37:20Z",
            "mission": "NISAR",
            "radar_band": "L",
            "product": "GCOV",
            "track": 98,
            "frame": 12,
            "crid": "P05023",
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(MANIFEST, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"Recorded in {MANIFEST}")
    else:
        print(f"Already recorded in {MANIFEST}")

    return str(dest)


if __name__ == "__main__":
    download_india_gcov_t1()

