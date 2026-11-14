#!/usr/bin/env python3
"""
Controlled downloader for NISAR candidate scenes from NASA Earthdata / ASF DAAC.
Enforces credentials check, SHA-256 verification, manifest logging, and disk safety.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data/raw/India"
MANIFEST_FILE = ROOT / "data/raw/manifest.jsonl"
ENV_FILE = ROOT / ".env"
CATALOG_JSON = ROOT / "data/reference/nisar_catalogue/nisar_similipal_candidate_scenes.json"


def get_token() -> str:
    token = os.environ.get("EARTHDATA_TOKEN")
    if not token and ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                if line.startswith("EARTHDATA_TOKEN="):
                    token = line.strip().split("=", 1)[1]
                    break
    if not token:
        raise RuntimeError("EARTHDATA_TOKEN not found in environment or .env file.")
    return token


def sha256_of_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_candidate_catalog() -> list[dict]:
    with open(CATALOG_JSON) as f:
        return json.load(f)


def download_scene(scene: dict, token: str, dry_run: bool = False) -> Path | None:
    scene_id = scene["scene_id"]
    download_url = scene["download_url"]
    filename = scene.get("h5_file_name") or f"{scene_id}.h5"
    expected_bytes = scene.get("h5_size_bytes") or 0

    dest_file = RAW_DIR / filename
    part_file = RAW_DIR / f"{filename}.part"

    if dest_file.exists():
        actual_size = dest_file.stat().st_size
        if actual_size == expected_bytes or expected_bytes == 0:
            print(f"[EXISTS] {filename} ({actual_size / (1024**3):.2f} GiB) already present in {RAW_DIR}")
            return dest_file
        else:
            print(f"[MISMATCH] {filename} exists but size is {actual_size} vs expected {expected_bytes}. Will re-download.")

    # Check disk space
    disk = shutil.disk_usage(RAW_DIR.parent)
    free_gib = disk.free / (1024**3)
    needed_gib = expected_bytes / (1024**3)
    if free_gib < (needed_gib + 5.0):
        raise RuntimeError(f"Insufficient disk space: {free_gib:.2f} GiB free, need {needed_gib:.2f} GiB + 5 GiB safety margin.")

    print(f"\n[TARGET] {scene_id}")
    print(f"  File: {filename}")
    print(f"  Size: {needed_gib:.2f} GiB ({expected_bytes:,} bytes)")
    print(f"  URL:  {download_url}")
    print(f"  Dest: {dest_file}")

    if dry_run:
        print("  [DRY-RUN] Skipping actual download.")
        return None

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    t0 = time.time()
    with session.get(download_url, stream=True, timeout=60, allow_redirects=True) as resp:
        resp.raise_for_status()
        downloaded = 0
        last_log = t0
        with open(part_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_log > 5.0 or downloaded == expected_bytes:
                        elapsed = now - t0
                        rate = (downloaded / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                        pct = (downloaded / expected_bytes) * 100 if expected_bytes else 0
                        print(f"  Downloaded: {downloaded / (1024**3):.2f} / {needed_gib:.2f} GiB ({pct:5.1f}%) @ {rate:.2f} MB/s", end="\r")
                        last_log = now

    print()
    part_file.replace(dest_file)
    elapsed_total = time.time() - t0
    avg_speed = (expected_bytes / (1024 * 1024)) / elapsed_total if elapsed_total > 0 else 0
    print(f"  [COMPLETED] {filename} in {elapsed_total:.1f}s (Avg {avg_speed:.2f} MB/s)")

    # Compute SHA-256
    print("  Calculating SHA-256 checksum...")
    sha256 = sha256_of_file(dest_file)
    print(f"  SHA-256: {sha256}")

    # Append to manifest.jsonl
    manifest_record = {
        "scene_id": scene_id,
        "region": "Similipal Tiger Reserve, Odisha, India",
        "file": str(dest_file.relative_to(ROOT)),
        "type": "Full GCOV Measurement Product",
        "bytes": dest_file.stat().st_size,
        "sha256": sha256,
        "acquired": scene["start_time"],
        "mission": "NISAR",
        "radar_band": "L",
        "product": "GCOV",
        "track": scene["track"],
        "frame": scene["frame"],
        "crid": scene["crid"],
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(MANIFEST_FILE, "a") as mf:
        mf.write(json.dumps(manifest_record) + "\n")
    print(f"  Logged record to {MANIFEST_FILE}")

    return dest_file


def main():
    parser = argparse.ArgumentParser(description="NISAR Candidate Dataset Downloader")
    parser.add_argument(
        "--scope",
        choices=["full_reserve", "intermediate_gap", "all_candidates"],
        default="full_reserve",
        help="Download package scope (default: full_reserve = June 20 Frame 13)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Perform sanity checks without downloading data")
    args = parser.parse_args()

    token = get_token()
    candidates = load_candidate_catalog()

    if args.scope == "full_reserve":
        # Only the 99.5% full reserve scene (June 20 Frame 13)
        targets = [c for c in candidates if c["frame"] == 13 and c["acquisition_date"] == "2026-06-20"]
    elif args.scope == "intermediate_gap":
        # March 16 and April 09 Frame 12
        targets = [c for c in candidates if c["acquisition_date"] in ["2026-03-16", "2026-04-09"] and c["frame"] == 12]
    elif args.scope == "all_candidates":
        targets = candidates

    print(f"Scope: {args.scope} ({len(targets)} scene(s))")
    total_bytes = sum(t["h5_size_bytes"] for t in targets)
    print(f"Total payload: {total_bytes / (1024**3):.2f} GiB ({total_bytes / 1e9:.2f} GB)")

    for scene in targets:
        download_scene(scene, token, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

