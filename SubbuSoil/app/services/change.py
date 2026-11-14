"""Step 8 — Pixel-wise soil moisture change detection.

For each pair of dates (t1 < t2), on pixels valid in BOTH observations:

    delta    = SM(t2) - SM(t1)                         [m3/m3]
    sigma    = sqrt(unc(t1)^2 + unc(t2)^2)              combined retrieval uncertainty
    z        = delta / sigma

A pixel has *changed* only if |delta| >= min_change AND |delta| >= k * sigma,
i.e. the change is both practically meaningful and larger than the product's
own stated uncertainty. Classes:

    0 no_data | 1 strong_drying | 2 drying | 3 no_significant_change
    4 wetting | 5 strong_wetting
"""
from __future__ import annotations

from itertools import combinations
from typing import Literal

import numpy as np
import pandas as pd
import xarray as xr
from pydantic import BaseModel, Field, model_validator

from app.services.extraction import LAND_COVER_CLASSES
from app.services.preprocess import MASK_BITS

CHANGE_CLASSES = {
    0: "no_data",
    1: "strong_drying",
    2: "drying",
    3: "no_significant_change",
    4: "wetting",
    5: "strong_wetting",
}


class ChangeParams(BaseModel):
    pairs: Literal["first_last", "consecutive", "all"] = Field(
        "first_last", description="Which date pairs to compare"
    )
    min_change: float = Field(0.05, gt=0, description="m3/m3; smaller differences are 'no significant change'")
    strong_change: float = Field(0.10, gt=0, description="m3/m3; threshold for strong drying/wetting")
    significance_k: float = Field(
        1.0, ge=0, description="Change must also exceed k x combined uncertainty (0 disables)"
    )
    # step 9
    min_region_pixels: int = Field(10, ge=1, description="Drop changed patches smaller than this (~0.04 km2/pixel)")
    connectivity: Literal[4, 8] = 8
    max_regions: int = Field(200, ge=1, le=5000, description="Max region polygons returned per pair")

    @model_validator(mode="after")
    def _check(self):
        if self.strong_change < self.min_change:
            raise ValueError("strong_change must be >= min_change")
        return self


def pair_indices(n: int, mode: str) -> list[tuple[int, int]]:
    if n < 2:
        raise ValueError("Need at least 2 observations")
    if mode == "first_last":
        return [(0, n - 1)]
    if mode == "consecutive":
        return [(i, i + 1) for i in range(n - 1)]
    return list(combinations(range(n), 2))


def _stats(a: np.ndarray) -> dict | None:
    a = a[np.isfinite(a)]
    if a.size == 0:
        return None
    p5, p25, p50, p75, p95 = np.percentile(a, [5, 25, 50, 75, 95])
    return {
        "mean": float(a.mean()), "std": float(a.std()), "min": float(a.min()), "max": float(a.max()),
        "p5": float(p5), "p25": float(p25), "median": float(p50), "p75": float(p75), "p95": float(p95),
    }


def detect_change(stack: xr.Dataset, i: int, j: int, p: ChangeParams) -> tuple[xr.Dataset, dict]:
    a, b = stack.isel(time=i), stack.isel(time=j)
    sm1, sm2 = a.soil_moisture.values, b.soil_moisture.values
    u1, u2 = a.soil_moisture_uncertainty.values, b.soil_moisture_uncertainty.values
    compared = (a.valid.values == 1) & (b.valid.values == 1) & np.isfinite(sm1) & np.isfinite(sm2)

    delta = np.where(compared, sm2 - sm1, np.nan).astype("float32")
    sigma = np.sqrt(np.nan_to_num(u1) ** 2 + np.nan_to_num(u2) ** 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(compared & (sigma > 0), delta / sigma, np.nan).astype("float32")
        rel = np.where(compared & (sm1 > 0), delta / sm1 * 100.0, np.nan).astype("float32")

    mag = np.abs(delta)
    significant = compared & (mag >= p.min_change) & (mag >= p.significance_k * sigma)
    strong = significant & (mag >= p.strong_change)
    cls = np.zeros(delta.shape, "uint8")
    cls[compared] = 3
    cls[significant & (delta < 0)] = 2
    cls[strong & (delta < 0)] = 1
    cls[significant & (delta > 0)] = 4
    cls[strong & (delta > 0)] = 5

    t1, t2 = pd.Timestamp(stack.time.values[i]), pd.Timestamp(stack.time.values[j])
    out = xr.Dataset(
        {
            "delta": (("y", "x"), delta, {"long_name": "Soil moisture change SM(t2)-SM(t1)", "units": "m3/m3"}),
            "relative_change": (("y", "x"), rel, {"long_name": "Relative change", "units": "%"}),
            "zscore": (("y", "x"), z, {"long_name": "delta / combined uncertainty"}),
            "change_class": (("y", "x"), cls, {
                "flag_values": list(CHANGE_CLASSES), "flag_meanings": " ".join(CHANGE_CLASSES.values()),
            }),
            "sm_t1": (("y", "x"), np.where(compared, sm1, np.nan).astype("float32")),
            "sm_t2": (("y", "x"), np.where(compared, sm2, np.nan).astype("float32")),
        },
        coords={"x": stack.x, "y": stack.y},
        attrs={"t1": t1.isoformat(), "t2": t2.isoformat()},
    )
    if "land_cover" in stack:
        out["land_cover"] = (("y", "x"), a.land_cover.values)
    out = out.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(stack.rio.crs)

    pixel_km2 = abs(float(stack.attrs["grid_spacing_x"]) * float(stack.attrs["grid_spacing_y"])) / 1e6
    n_cmp = int(compared.sum())
    classes = []
    for k, name in CHANGE_CLASSES.items():
        if k == 0:
            continue
        n = int((cls == k).sum())
        classes.append({
            "class_id": k, "name": name, "n_pixels": n, "area_km2": round(n * pixel_km2, 3),
            "pct_of_compared": round(100 * n / n_cmp, 2) if n_cmp else 0.0,
        })

    # land-cover breakdown of the change
    lc_rows = []
    if "land_cover" in out:
        lc = out.land_cover.values
        for code in np.unique(lc[compared]):
            m = compared & (lc == code)
            n = int(m.sum())
            lc_rows.append({
                "land_cover": LAND_COVER_CLASSES.get(int(code), f"class {int(code)}"),
                "n_pixels": n,
                "area_km2": round(n * pixel_km2, 3),
                "mean_delta": float(np.nanmean(delta[m])),
                "pct_drying": round(100 * float(np.isin(cls[m], (1, 2)).mean()), 2),
                "pct_wetting": round(100 * float(np.isin(cls[m], (4, 5)).mean()), 2),
            })
        lc_rows.sort(key=lambda r: -r["n_pixels"])

    # why AOI pixels could not be compared (union of both dates' QC reasons)
    in_aoi = (a.aoi_mask.values == 1) | (b.aoi_mask.values == 1)
    reasons = a.mask_reason.values | b.mask_reason.values
    not_compared = {
        name: int(((reasons & (1 << bit)) > 0)[in_aoi & ~compared].sum())
        for bit, name in MASK_BITS.items() if name != "outside_aoi"
    }

    stats = {
        "t1": t1.isoformat(), "t2": t2.isoformat(),
        "granule_t1": str(stack.granule_id.values[i]), "granule_t2": str(stack.granule_id.values[j]),
        "days": round((t2 - t1).total_seconds() / 86400, 2),
        "n_aoi_pixels": int(in_aoi.sum()),
        "n_compared": n_cmp,
        "compared_area_km2": round(n_cmp * pixel_km2, 2),
        "compared_fraction": round(n_cmp / int(in_aoi.sum()), 4) if in_aoi.any() else 0.0,
        "mean_sm_t1": float(np.nanmean(sm1[compared])) if n_cmp else None,
        "mean_sm_t2": float(np.nanmean(sm2[compared])) if n_cmp else None,
        "delta": _stats(delta),
        "median_combined_uncertainty": float(np.median(sigma[compared])) if n_cmp else None,
        "classes": classes,
        "land_cover_breakdown": lc_rows,
        "not_compared_reasons": not_compared,
        "pixel_area_km2": pixel_km2,
    }
    return out, stats
