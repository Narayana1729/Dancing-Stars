#!/usr/bin/env python3
"""Inspect a downloaded NISAR GCOV HDF5 file and save a basic backscatter quick-look.

STATUS: written in Phase 2 but NOT yet run against a real granule (no Earthdata
credentials were available, so no NISAR file has been downloaded). Treat as untested.

  backend/.venv/bin/python scripts/preprocessing/inspect_gcov.py --file data/raw/<GCOV>.h5 \
      --out data/processed/quicklook.png [--pol HHHH] [--max-px 1500]

Prints the HDF5 tree, identification metadata, polarizations, projection, nodata/NaN stats, and
plots a linear->dB backscatter image (strided down for display only; no analysis is performed).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


def _tree(f: h5py.File, max_depth: int = 6) -> None:
    def visit(name: str, obj) -> None:
        if name.count("/") >= max_depth:
            return
        kind = f"dataset {obj.shape} {obj.dtype}" if isinstance(obj, h5py.Dataset) else "group"
        print(f"  /{name}  [{kind}]")
    f.visititems(visit)


def _find_frequency_group(f: h5py.File) -> h5py.Group:
    grids = f["/science/LSAR/GCOV/grids"]
    freqs = [k for k in grids if k.startswith("frequency")]
    if not freqs:
        raise SystemExit("no frequency* group under /science/LSAR/GCOV/grids")
    return grids[sorted(freqs)[0]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pol", default=None, help="e.g. HHHH or HVHV (default: first diagonal term found)")
    ap.add_argument("--max-px", type=int, default=1500)
    a = ap.parse_args()

    with h5py.File(a.file) as f:
        print("== structure"); _tree(f)
        ident = f["/science/LSAR/identification"]
        print("== identification")
        for k in ("productType", "missionId", "trackNumber", "frameNumber", "orbitPassDirection",
                  "zeroDopplerStartTime", "zeroDopplerEndTime", "isGeocoded", "listOfFrequencies"):
            if k in ident:
                v = ident[k][()]
                print(f"  {k}: {v.decode() if isinstance(v, bytes) else v}")
        fg = _find_frequency_group(f)
        pols_ds = fg.get("listOfPolarizations")
        pols = [p.decode() for p in pols_ds[()]] if pols_ds is not None else []
        print("== polarization channels:", pols)
        diag = [k for k in fg if len(k) == 4 and k[:2] == k[2:] and isinstance(fg[k], h5py.Dataset)]
        print("== measurement layers present:", diag)
        pol = a.pol or (diag[0] if diag else None)
        if pol is None:
            raise SystemExit("no diagonal covariance layer (e.g. HHHH) found")
        ds = fg[pol]
        print(f"== layer {pol}: shape {ds.shape} dtype {ds.dtype} fillValue attr: {ds.attrs.get('_FillValue')}")
        if "projection" in fg:
            pr = fg["projection"]
            print("== projection: epsg", pr[()], {k: (v.decode() if isinstance(v, bytes) else v) for k, v in pr.attrs.items() if k in ("spatial_ref", "epsg_code")})
        for k in ("xCoordinates", "yCoordinates", "xCoordinateSpacing", "yCoordinateSpacing"):
            if k in fg:
                v = fg[k][()]
                print(f"  {k}: {v if np.ndim(v) == 0 else (float(v[0]), float(v[-1]), len(v))}")
        sx, sy = max(1, ds.shape[1] // a.max_px), max(1, ds.shape[0] // a.max_px)
        arr = ds[::sy, ::sx].astype("float32")

    nan = np.isnan(arr).sum(); zero = (arr == 0).sum(); neg = (arr < 0).sum()
    print(f"== nodata check (subsampled {arr.shape}): NaN={nan} zeros={zero} negative={neg} total={arr.size}")
    valid = np.isfinite(arr) & (arr > 0)
    db = np.full(arr.shape, np.nan, dtype="float32")
    db[valid] = 10 * np.log10(arr[valid])
    lo, hi = np.nanpercentile(db, [2, 98])
    print(f"== dB stats: min {np.nanmin(db):.2f} 2% {lo:.2f} median {np.nanmedian(db):.2f} 98% {hi:.2f} max {np.nanmax(db):.2f}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 9 * arr.shape[0] / arr.shape[1]))
    im = ax.imshow(db, cmap="gray", vmin=lo, vmax=hi)
    ax.set_title(f"{Path(a.file).name}\n{pol} backscatter (dB), strided {sy}x{sx} for display", fontsize=7)
    ax.axis("off"); fig.colorbar(im, ax=ax, shrink=0.6, label="dB")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out, dpi=150, bbox_inches="tight")
    print("saved", a.out)


if __name__ == "__main__":
    main()

