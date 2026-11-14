"""Step 6 — Preprocessing: unit verification, quality masking, analysis-ready layers.

Each QC rule sets one bit in `mask_reason` so every removed pixel can be
explained later (step 11). Rules only use information verified against the
data (see extraction.py): the documented retrieval-recommended bit, land-cover
classes, water-body fraction, uncertainty and the product's valid range.
The surfaceQualityFlag is NOT used because its bit meanings are undocumented
for current products.
"""
from __future__ import annotations

import numpy as np
import xarray as xr
from pydantic import BaseModel, Field

from app.services.extraction import INT_FILL, LAND_COVER_CLASSES

# product valid range (spec + file min/max attrs)
SM_VALID_RANGE = (0.02, 0.60)
_VOLUMETRIC_UNITS = {"meter^3/meter^3", "m^3/m^3", "m3/m3", "m3 m-3", "cm^3/cm^3", "cm3/cm3"}
_PERCENT_UNITS = {"%", "percent", "vol%", "% vol"}

MASK_BITS = {
    0: "outside_aoi",
    1: "no_retrieval",
    2: "out_of_valid_range",
    3: "not_recommended",
    4: "excluded_land_cover",
    5: "high_water_fraction",
    6: "high_uncertainty",
}
BIT_OF = {v: k for k, v in MASK_BITS.items()}


class QCParams(BaseModel):
    require_recommended: bool = Field(
        True, description="Drop retrievals flagged 'not recommended' (retrievalQualityFlag bit0)"
    )
    exclude_land_cover: list[int] = Field(
        [5, 7, 8], description="Land-cover classes to drop (default: Built-up, Snow & ice, Permanent water)"
    )
    max_waterbody_fraction: float | None = Field(0.1, ge=0, le=1)
    max_uncertainty: float | None = Field(
        0.06, ge=0, description="m3/m3; 0.06 is the NISAR soil-moisture accuracy goal"
    )


class UnitError(ValueError):
    pass


def verify_units(ds: xr.Dataset) -> tuple[xr.Dataset, str]:
    """Ensure soil moisture and uncertainty are volumetric m3/m3."""
    notes = []
    for name in ("soil_moisture", "soil_moisture_uncertainty"):
        units = str(ds[name].attrs.get("units", "")).strip().lower()
        if units in _VOLUMETRIC_UNITS:
            continue
        if units in _PERCENT_UNITS:
            attrs = ds[name].attrs | {"units": "m3/m3"}
            ds[name] = ds[name] / 100.0
            ds[name].attrs = attrs
            notes.append(f"{name}: converted percent -> m3/m3")
            continue
        raise UnitError(f"{name} has unexpected units '{units}'")
    for name in ("soil_moisture", "soil_moisture_uncertainty"):
        ds[name].attrs["units"] = "m3/m3"
    vmax = float(ds.soil_moisture.max(skipna=True)) if ds.soil_moisture.notnull().any() else 0.0
    if vmax > 1.0:
        raise UnitError(f"soil_moisture max {vmax:.3f} > 1 — not volumetric fraction")
    return ds, "; ".join(notes) or "units verified: m3/m3"


def preprocess(ds: xr.Dataset, qc: QCParams) -> tuple[xr.Dataset, dict]:
    ds, unit_note = verify_units(ds.copy())

    sm = ds.soil_moisture.values
    unc = ds.soil_moisture_uncertainty.values
    inside = ds.aoi_mask.values.astype(bool) if "aoi_mask" in ds else np.ones(sm.shape, bool)
    has_sm = np.isfinite(sm)
    rules: dict[str, np.ndarray] = {
        "outside_aoi": ~inside,
        "no_retrieval": inside & ~has_sm,
    }
    lo, hi = SM_VALID_RANGE
    eps = 1e-6
    rules["out_of_valid_range"] = has_sm & ((sm < lo - eps) | (sm > hi + eps))

    rqf = ds.retrieval_quality_flag.values
    if qc.require_recommended:
        # bit0 = 1 -> not recommended; a missing flag on a retrieved pixel is treated as not recommended
        rules["not_recommended"] = has_sm & ((rqf == INT_FILL) | ((rqf & 1) == 1))

    if qc.exclude_land_cover and "land_cover" in ds:
        rules["excluded_land_cover"] = has_sm & np.isin(ds.land_cover.values, qc.exclude_land_cover)

    if qc.max_waterbody_fraction is not None and "waterbody_fraction" in ds:
        wf = ds.waterbody_fraction.values
        rules["high_water_fraction"] = has_sm & np.isfinite(wf) & (wf > qc.max_waterbody_fraction)

    if qc.max_uncertainty is not None:
        rules["high_uncertainty"] = has_sm & np.isfinite(unc) & (unc > qc.max_uncertainty)

    reason = np.zeros(sm.shape, dtype="uint8")
    for name, m in rules.items():
        reason |= (m.astype("uint8") << BIT_OF[name])
    valid = reason == 0

    out = ds.copy()
    out["soil_moisture"] = ds.soil_moisture.where(valid)
    out["soil_moisture_uncertainty"] = ds.soil_moisture_uncertainty.where(valid)
    out["soil_moisture_raw"] = ds.soil_moisture.where(inside)
    out["soil_moisture_raw"].attrs = ds.soil_moisture.attrs | {"long_name": "Soil moisture before QC (AOI only)"}
    out["valid"] = (("y", "x"), valid.astype("uint8"), {"long_name": "1 = passed all QC rules"})
    out["mask_reason"] = (("y", "x"), reason, {
        "long_name": "QC bitmask; 0 = valid",
        "flag_masks": [1 << b for b in MASK_BITS],
        "flag_meanings": " ".join(MASK_BITS.values()),
    })
    for name in ("soil_moisture", "soil_moisture_uncertainty"):
        out[name].attrs = ds[name].attrs

    n_aoi = int(inside.sum())
    n_valid = int(valid.sum())
    removed = {name: int(m[inside].sum()) for name, m in rules.items() if name != "outside_aoi"}
    lc_removed = {}
    if "excluded_land_cover" in rules:
        lc = ds.land_cover.values[rules["excluded_land_cover"] & inside]
        v, c = np.unique(lc, return_counts=True)
        lc_removed = {LAND_COVER_CLASSES.get(int(k), str(k)): int(n) for k, n in zip(v, c)}

    report = {
        "units": unit_note,
        "n_aoi_pixels": n_aoi,
        "n_with_retrieval": int((has_sm & inside).sum()),
        "n_valid": n_valid,
        "valid_fraction": round(n_valid / n_aoi, 4) if n_aoi else 0.0,
        "removed_by_rule": removed,
        "removed_land_cover_classes": lc_removed,
        "qc_params": qc.model_dump(),
    }
    out.attrs["qc_valid_fraction"] = report["valid_fraction"]
    return out, report
