#!/usr/bin/env python3
"""Download the full NISAR L2 GCOV HDF5 measurement granule.

Features:
- Earthdata Bearer authentication through NASA Thin Egress App (TEA).
- Strips Authorization header when redirected to Cloudfront/S3 signed URLs.
- HTTP Range-based resume capability if interrupted.
- Streams in 8 MB chunks to avoid memory pressure.
- Progress logging and SHA256 integrity verification.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
MANIFEST = RAW_DIR / "manifest.jsonl"

NISAR_URL = (
    "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_BETA_V1/"
    "NISAR_L2_PR_GCOV_002_109_D_063_4005_DHDH_A_20251012T182508_20251012T182531_X05010_N_P_J_001/"
    "NISAR_L2_PR_GCOV_002_109_D_063_4005_DHDH_A_20251012T182508_20251012T182531_X05010_N_P_J_001.h5"
)
FILE_NAME = "NISAR_L2_PR_GCOV_002_109_D_063_4005_DHDH_A_20251012T182508_20251012T182531_X05010_N_P_J_001.h5"


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


def download():
    token = get_token()
    dest = RAW_DIR / FILE_NAME
    part = RAW_DIR / (FILE_NAME + ".part")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        print(f"File already exists: {dest} ({dest.stat().st_size:,} bytes)")
        return str(dest)

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
        print(f"Resuming from byte {downloaded:,}...")
        total_size = downloaded + int(resp.headers.get("Content-Length", 0))
    elif resp.status_code == 200:
        downloaded = 0
        total_size = int(resp.headers.get("Content-Length", 0))
    else:
        raise RuntimeError(f"Unexpected response status: {resp.status_code}")

    print(f"Starting download of {FILE_NAME}:")
    print(f"Target size: {total_size / 1024**3:.2f} GB ({total_size:,} bytes)")

    chunk_size = 8 * 1024 * 1024  # 8 MB
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
                if now - last_log > 10:  # log every 10 seconds
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

    print("Computing SHA256...")
    sha = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            sha.update(chunk)
    digest = sha.hexdigest()
    print(f"SHA256: {digest}")

    rec = {
        "scene_id": "NISAR_L2_PR_GCOV_002_109_D_063_4005_DHDH_A_20251012T182508_20251012T182531_X05010_N_P_J_001",
        "file": str(dest.relative_to(ROOT)),
        "type": "Full GCOV Measurement Product",
        "bytes": dest.stat().st_size,
        "sha256": digest,
        "acquired": "2025-10-12T18:25:08",
        "mission": "NISAR",
        "radar_band": "L",
        "product": "GCOV",
        "track": 109,
        "frame": 63,
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(MANIFEST, "a") as f:
        import json
        f.write(json.dumps(rec) + "\n")
    print(f"Recorded in {MANIFEST}")
    return str(dest)


if __name__ == "__main__":
    download()

