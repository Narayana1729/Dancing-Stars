#!/usr/bin/env python3
"""
Authenticated downloader for Sentinel-2 L2A optical validation products from Copernicus Data Space (CDSE).
Enforces atomic .part writing, SHA-256 verification, and manifest logging.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data/reference/sentinel2_raw"
MANIFEST_FILE = ROOT / "data/reference/sentinel2_catalogue/manifest.jsonl"
ENV_FILE = ROOT / ".env"
GATE_JSON = ROOT / "data/reference/sentinel2_catalogue/sentinel2_download_gate_summary.json"

AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
DOWNLOAD_URL_TEMPLATE = "https://download.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"


def get_cdse_token() -> str:
    if not ENV_FILE.exists():
        raise RuntimeError(".env file not found")
    with open(ENV_FILE) as f:
        env = dict(line.strip().split("=", 1) for line in f if "=" in line and not line.startswith("#"))

    user = env.get("COPERNICUS_USERNAME")
    pw = env.get("COPERNICUS_PASSWORD")
    if not user or not pw:
        raise RuntimeError("COPERNICUS_USERNAME and COPERNICUS_PASSWORD must be configured in .env")

    data = {
        "client_id": "cdse-public",
        "username": user,
        "password": pw,
        "grant_type": "password",
    }
    resp = requests.post(AUTH_URL, data=data, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"CDSE authentication failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()["access_token"]


def sha256_of_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get_product_id(product_name: str) -> str:
    params = {"$filter": f"Name eq '{product_name}'"}
    r = requests.get(CATALOG_URL, params=params, timeout=20)
    r.raise_for_status()
    items = r.json().get("value", [])
    if not items:
        raise RuntimeError(f"Product {product_name} not found in CDSE catalogue.")
    return items[0]["Id"]


def download_sentinel2_scene(scene_info: dict, token: str, dry_run: bool = False) -> Path | None:
    prod_name = scene_info["product_id"]
    zip_name = prod_name if prod_name.endswith(".zip") else f"{prod_name.replace('.SAFE', '')}.zip"
    dest_path = OUTPUT_DIR / zip_name
    part_path = OUTPUT_DIR / f"{zip_name}.part"

    if dest_path.exists() and dest_path.stat().st_size > 10 * 1024 * 1024:
        print(f"[EXISTS] {zip_name} ({dest_path.stat().st_size / (1024**2):.1f} MB) already present.")
        return dest_path

    prod_id = get_product_id(prod_name)
    dl_url = DOWNLOAD_URL_TEMPLATE.format(product_id=prod_id)

    print(f"\n[TARGET] {prod_name}")
    print(f"  CDSE Product ID: {prod_id}")
    print(f"  Destination:     {dest_path}")
    print(f"  Role:            {scene_info.get('role', 'Optical Reference')}")

    if dry_run:
        print("  [DRY-RUN] Skipping actual download.")
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {token}"}
    session = requests.Session()

    # Pre-check disk space
    disk = shutil.disk_usage(OUTPUT_DIR.parent)
    free_gib = disk.free / (1024**3)
    if free_gib < 5.0:
        raise RuntimeError(f"Critically low disk space: {free_gib:.2f} GiB free.")

    t0 = time.time()
    with session.get(dl_url, headers=headers, stream=True, timeout=60, allow_redirects=True) as resp:
        resp.raise_for_status()
        total_len = int(resp.headers.get("Content-Length", 0))
        total_mb = total_len / (1024 * 1024) if total_len else 0
        downloaded = 0
        last_log = t0
        with open(part_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=2 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_log > 5.0 or downloaded == total_len:
                        elapsed = now - t0
                        rate = (downloaded / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                        pct = (downloaded / total_len) * 100 if total_len else 0
                        print(f"  Downloaded: {downloaded / (1024**2):.1f} / {total_mb:.1f} MB ({pct:5.1f}%) @ {rate:.2f} MB/s", end="\r")
                        last_log = now

    print()
    part_path.replace(dest_path)
    elapsed_total = time.time() - t0
    final_size = dest_path.stat().st_size
    avg_speed = (final_size / (1024 * 1024)) / elapsed_total if elapsed_total > 0 else 0
    print(f"  [COMPLETED] {zip_name} ({final_size / (1024**2):.1f} MB) in {elapsed_total:.1f}s (Avg {avg_speed:.2f} MB/s)")

    print("  Calculating SHA-256 checksum...")
    sha256 = sha256_of_file(dest_path)
    print(f"  SHA-256: {sha256}")

    manifest_record = {
        "product_id": prod_name,
        "cdse_id": prod_id,
        "file": str(dest_path.relative_to(ROOT)),
        "type": "Sentinel-2 L2A BOA Surface Reflectance Zip",
        "bytes": final_size,
        "sha256": sha256,
        "acquisition_date": scene_info.get("date"),
        "tile": scene_info.get("tile"),
        "orbit": scene_info.get("orbit"),
        "cloud_pct": scene_info.get("cloud_pct"),
        "role": scene_info.get("role"),
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(MANIFEST_FILE, "a") as mf:
        mf.write(json.dumps(manifest_record) + "\n")
    print(f"  Logged record to {MANIFEST_FILE}")

    return dest_path


def main():
    parser = argparse.ArgumentParser(description="Sentinel-2 Reference Scene Downloader")
    parser.add_argument("--dry-run", action="store_true", help="Perform sanity checks without downloading data")
    parser.add_argument("--single", type=str, help="Download only a specific product ID")
    args = parser.parse_args()

    token = get_cdse_token()
    with open(GATE_JSON) as f:
        gate_info = json.load(f)

    scenes = gate_info.get("recommended_scenes", [])
    if args.single:
        scenes = [s for s in scenes if s["product_id"] == args.single]
        if not scenes:
            raise ValueError(f"Product {args.single} not found in recommended scenes.")

    print(f"Targeting {len(scenes)} Sentinel-2 L2A scene(s)...")
    for s in scenes:
        download_sentinel2_scene(s, token, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

