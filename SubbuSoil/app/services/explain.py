"""Step 11 — Explainable analysis engine (deterministic, rule-based).

Answers WHAT changed, WHERE, WHEN, HOW MUCH and WHICH FACTORS MAY HAVE
CONTRIBUTED. Every factor is evaluated by an explicit, documented rule over
measured evidence and returns:

    verdict   supports | contradicts | inconclusive | unavailable
    strength  weak | moderate | strong        (for supports/contradicts)
    evidence  the numbers the rule used
    rule      the rule in words
    statement plain-language sentence

Wording is deliberately non-causal ("consistent with", "may have contributed"):
the evidence is correlational and from coarse/independent datasets.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

STRENGTH_SCORE = {"weak": 1, "moderate": 2, "strong": 3}
NATURAL_LC = ("Tree cover", "Shrublands", "Grassland", "Bare/sparse vegetation", "Herbaceous wetland")


# ---------------------------------------------------------------- helpers
def _f(v, nd=3, signed=False):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    return f"{v:+.{nd}f}" if signed else f"{v:.{nd}f}"


def _date(s: str) -> str:
    return pd.Timestamp(s).strftime("%d %b %Y").lstrip("0")


def _factor(fid, name, verdict, strength, evidence, rule, statement):
    return {"id": fid, "name": name, "verdict": verdict, "strength": strength,
            "evidence": evidence, "rule": rule, "statement": statement}


def _unavailable(fid, name, why):
    return _factor(fid, name, "unavailable", None, {}, "", f"{name}: data unavailable ({why}).")


def _rho_strength(rho: float) -> str | None:
    a = abs(rho)
    return "strong" if a >= 0.5 else "moderate" if a >= 0.35 else "weak" if a >= 0.2 else None


def _overall(stats: dict) -> dict:
    cls = {c["name"]: c for c in stats["classes"]}
    dry = cls["drying"]["area_km2"] + cls["strong_drying"]["area_km2"]
    wet = cls["wetting"]["area_km2"] + cls["strong_wetting"]["area_km2"]
    total = stats["compared_area_km2"] or 1.0
    changed_pct = 100 * (dry + wet) / total
    if changed_pct < 10:
        direction = "stable"
    elif wet >= 1.5 * dry:
        direction = "wetting"
    elif dry >= 1.5 * wet:
        direction = "drying"
    else:
        direction = "mixed"
    return {"direction": direction, "wet_km2": round(wet, 2), "dry_km2": round(dry, 2),
            "wet_pct": round(100 * wet / total, 1), "dry_pct": round(100 * dry / total, 1),
            "changed_pct": round(changed_pct, 1)}


# ---------------------------------------------------------------- factors
def _rain_factor(w: dict, direction: str, n: int) -> dict:
    name = "Rainfall"
    if not w.get("available"):
        return _unavailable("rainfall", name, w.get("error", "no data"))
    m = w["aoi_mean"]
    a1, a2 = m.get(f"rain_{n}d_before_t1_mm"), m.get(f"rain_{n}d_before_t2_mm")
    between = m.get("rain_between_mm")
    if a1 is None or a2 is None:
        return _unavailable("rainfall", name, "missing values")
    d = a2 - a1
    ev = {f"rain_{n}d_before_t1_mm": round(a1, 1), f"rain_{n}d_before_t2_mm": round(a2, 1),
          "difference_mm": round(d, 1), "rain_between_dates_mm": _round(between, 1),
          "days_since_rain_ge5mm_t1": m.get("days_since_rain_ge5mm_t1"),
          "days_since_rain_ge5mm_t2": m.get("days_since_rain_ge5mm_t2")}
    rule = (f"Compare rain in the {n} days before each date. Wetting is supported if the later date had "
            f">=10 mm more (strong >=30 mm); drying if it had >=10 mm less. The opposite contradicts.")
    ctx = f"{a2:.0f} mm fell in the {n} days before the second date vs {a1:.0f} mm before the first"
    if direction in ("stable", "mixed"):
        return _factor("rainfall", name, "inconclusive", None, ev, rule,
                       f"Rainfall: {ctx}; the soil-moisture response is {direction}, so no single direction to attribute.")
    sign = 1 if direction == "wetting" else -1
    s = sign * d
    if s >= 10:
        st = "strong" if s >= 30 else "moderate"
        return _factor("rainfall", name, "supports", st, ev, rule,
                       f"Rainfall: {ctx} — consistent with the {direction}.")
    if s <= -10:
        st = "strong" if s <= -30 else "moderate"
        return _factor("rainfall", name, "contradicts", st, ev, rule,
                       f"Rainfall: {ctx} — recent rain does not explain the {direction}.")
    return _factor("rainfall", name, "inconclusive", "weak", ev, rule,
                   f"Rainfall: {ctx} — too similar to explain the {direction}.")


def _round(v, nd):
    return None if v is None else round(v, nd)


def _evap_factor(w: dict, direction: str, n: int) -> dict:
    name = "Evaporative demand (temperature / ET0)"
    if not w.get("available"):
        return _unavailable("evaporation", name, w.get("error", "no data"))
    m = w["aoi_mean"]
    e1, e2 = m.get(f"et0_{n}d_before_t1_mm"), m.get(f"et0_{n}d_before_t2_mm")
    t1, t2 = m.get(f"tmax_{n}d_before_t1_c"), m.get(f"tmax_{n}d_before_t2_c")
    if e1 is None or e2 is None:
        return _unavailable("evaporation", name, "missing values")
    d = e2 - e1
    ev = {f"et0_{n}d_before_t1_mm": round(e1, 1), f"et0_{n}d_before_t2_mm": round(e2, 1),
          "et0_difference_mm": round(d, 1), f"tmax_{n}d_before_t1_c": _round(t1, 1),
          f"tmax_{n}d_before_t2_c": _round(t2, 1),
          "water_balance_between_mm": m.get("water_balance_between_mm")}
    rule = (f"Reference evapotranspiration (ET0) over the {n} days before each date. Drying is supported "
            f"if ET0 rose by >=3 mm (strong >=8 mm); wetting weakly supported if ET0 fell by >=3 mm.")
    ctx = f"ET0 {e1:.0f} -> {e2:.0f} mm, mean Tmax {_f(t1, 1)} -> {_f(t2, 1)} degC"
    if direction == "drying" and d >= 3:
        return _factor("evaporation", name, "supports", "strong" if d >= 8 else "moderate", ev, rule,
                       f"Evaporative demand increased ({ctx}), consistent with drying.")
    if direction == "wetting" and d <= -3:
        return _factor("evaporation", name, "supports", "weak", ev, rule,
                       f"Evaporative demand decreased ({ctx}), reducing soil-water loss.")
    if direction == "drying" and d <= -3:
        return _factor("evaporation", name, "contradicts", "weak", ev, rule,
                       f"Evaporative demand decreased ({ctx}), so it does not explain the drying.")
    return _factor("evaporation", name, "inconclusive", None, ev, rule,
                   f"Evaporative demand changed little ({ctx}).")


def _reanalysis_factor(w: dict, stats: dict, direction: str) -> dict:
    name = "Weather-driven change (ERA5-Land reanalysis agreement)"
    if not w.get("available"):
        return _unavailable("reanalysis", name, w.get("error", "no data"))
    m = w["aoi_mean"]
    era = m.get("era5_sm_delta")
    nis = stats["delta"]["mean"] if stats.get("delta") else None
    if era is None or nis is None:
        return _unavailable("reanalysis", name, "missing values")
    ev = {"era5_land_sm_t1": m.get("era5_sm_t1"), "era5_land_sm_t2": m.get("era5_sm_t2"),
          "era5_land_delta": round(era, 4), "nisar_mean_delta": round(nis, 4)}
    rule = ("ERA5-Land (0-7 cm, weather-driven model, no irrigation) change vs NISAR mean change. Same sign "
            "with |ERA5 change| >= 0.02 supports a weather-driven change; NISAR wetting while ERA5 dries "
            "(or vice versa) contradicts a purely weather-driven explanation.")
    if abs(era) >= 0.02 and np.sign(era) == np.sign(nis):
        st = "strong" if abs(era) >= 0.05 else "moderate"
        return _factor("reanalysis", name, "supports", st, ev, rule,
                       f"The weather-driven ERA5-Land model also shows a change of {_f(era, 3, True)} m3/m3, "
                       f"consistent with NISAR ({_f(nis, 3, True)}): the change is likely weather-driven.")
    if direction in ("wetting", "drying") and np.sign(era) != np.sign(nis) and abs(era) >= 0.01:
        return _factor("reanalysis", name, "contradicts", "moderate", ev, rule,
                       f"ERA5-Land shows {_f(era, 3, True)} m3/m3 while NISAR shows {_f(nis, 3, True)}: "
                       f"weather alone does not reproduce the observed {direction}, pointing to a local "
                       f"cause (e.g. irrigation) or a retrieval effect.")
    return _factor("reanalysis", name, "inconclusive", None, ev, rule,
                   f"ERA5-Land change ({_f(era, 3, True)} m3/m3) is too small to confirm or contradict NISAR "
                   f"({_f(nis, 3, True)}).")


def _vegetation_factor(v: dict) -> dict:
    name = "Vegetation / crop dynamics (Sentinel-2 NDVI)"
    if not v.get("available"):
        return _unavailable("vegetation", name, v.get("error", "no data"))
    corr = v.get("corr_sm_delta_vs_ndvi_delta")
    dn = v.get("ndvi_delta_mean")
    ev = {"ndvi_t1_mean": _round(v.get("ndvi_t1_mean"), 3), "ndvi_t2_mean": _round(v.get("ndvi_t2_mean"), 3),
          "ndvi_delta_mean": _round(dn, 3), "spearman_sm_delta_vs_ndvi_delta": corr,
          "scene_t1": v["scene_t1"]["date"], "scene_t2": v["scene_t2"]["date"],
          "ndvi_coverage_of_compared": v.get("ndvi_coverage_of_compared")}
    rule = ("Spearman correlation between pixel soil-moisture change and NDVI change. |rho| >= 0.2 weak, "
            ">= 0.35 moderate, >= 0.5 strong. The sign pattern is interpreted (greening+wetting = crop growth "
            "with water input; greening+drying = crop water uptake; browning+drying = senescence/harvest; "
            "browning+wetting = harvest/tillage/flooding).")
    if corr is None or dn is None:
        return _factor("vegetation", name, "inconclusive", None, ev, rule,
                       "Vegetation: too few cloud-free pixels to relate NDVI to soil-moisture change.")
    rho = corr["rho"]
    st = _rho_strength(rho)
    green = dn > 0.02
    brown = dn < -0.02
    if rho > 0 and green:
        pattern = "areas that greened up also became wetter — consistent with crop growth supported by water input (rain or irrigation)"
    elif rho < 0 and green:
        pattern = "areas that greened up became drier — consistent with growing crops drawing water from the soil (transpiration)"
    elif rho > 0 and brown:
        pattern = "areas that lost greenness also dried — consistent with crop senescence or harvest exposing drying soil"
    elif rho < 0 and brown:
        pattern = "areas that lost greenness became wetter — consistent with harvest, tillage or surface flooding"
    else:
        pattern = "NDVI changed little overall"
    text = (f"Vegetation: mean NDVI {_f(ev['ndvi_t1_mean'], 2)} -> {_f(ev['ndvi_t2_mean'], 2)} "
            f"(Sentinel-2 {ev['scene_t1']} / {ev['scene_t2']}); rho = {rho:+.2f}; {pattern}.")
    if st is None:
        return _factor("vegetation", name, "inconclusive", "weak", ev, rule, text)
    return _factor("vegetation", name, "supports", st, ev, rule, text)


def _irrigation_factor(stats: dict, direction: str, rain: dict, rean: dict) -> dict:
    name = "Irrigation / agricultural water management"
    rows = {r["land_cover"]: r for r in stats.get("land_cover_breakdown", [])}
    crop = rows.get("Cropland")
    nat = [rows[k] for k in NATURAL_LC if k in rows]
    total = sum(r["n_pixels"] for r in rows.values()) or 1
    if not crop or crop["n_pixels"] / total < 0.05 or not nat:
        return _unavailable("irrigation", name, "needs both cropland and natural land cover in the AOI")
    nat_px = sum(r["n_pixels"] for r in nat)
    nat_delta = sum(r["mean_delta"] * r["n_pixels"] for r in nat) / nat_px
    diff = crop["mean_delta"] - nat_delta
    ev = {"cropland_mean_delta": round(crop["mean_delta"], 4), "natural_mean_delta": round(nat_delta, 4),
          "difference": round(diff, 4), "cropland_pct_wetting": crop["pct_wetting"],
          "natural_land_covers": [r["land_cover"] for r in nat],
          "rainfall_verdict": rain["verdict"], "reanalysis_verdict": rean["verdict"]}
    rule = ("Cropland wetting more than natural land (difference >= 0.05 m3/m3) suggests managed water. "
            "Strength rises when rainfall and/or the weather-driven reanalysis do NOT explain the wetting.")
    if diff >= 0.05:
        n_against = sum(f["verdict"] == "contradicts" for f in (rain, rean))
        n_for = sum(f["verdict"] == "supports" for f in (rain, rean))
        st = "strong" if n_against >= 1 and n_for == 0 else "moderate" if n_for == 0 else "weak"
        alt = (" An alternative to rule out in the field: a growing crop canopy can raise radar backscatter "
               "and bias the soil-moisture retrieval upward." if n_against else "")
        return _factor("irrigation", name, "supports", st, ev, rule,
                       f"Cropland became wetter ({_f(crop['mean_delta'], 3, True)} m3/m3) than natural land "
                       f"({_f(nat_delta, 3, True)}): a crop-specific wetting consistent with irrigation or "
                       f"field water management" + (", which weather data do not explain." if n_against else ".")
                       + alt)
    if diff <= -0.05:
        return _factor("irrigation", name, "inconclusive", "weak", ev, rule,
                       f"Cropland dried more than natural land ({_f(crop['mean_delta'], 3, True)} vs "
                       f"{_f(nat_delta, 3, True)}), consistent with crop water uptake or reduced irrigation.")
    return _factor("irrigation", name, "inconclusive", None, ev, rule,
                   f"Cropland and natural land changed similarly ({_f(crop['mean_delta'], 3, True)} vs "
                   f"{_f(nat_delta, 3, True)} m3/m3): no crop-specific signal.")


def _soil_factor(s: dict, direction: str) -> dict:
    name = "Soil texture (water retention)"
    if not s.get("available"):
        return _unavailable("soil", name, s.get("error", "no data"))
    cs, cc = s.get("corr_sm_delta_vs_sand"), s.get("corr_sm_delta_vs_clay")
    ev = {"texture_class": s.get("texture_class"), "sand_pct_mean": s.get("sand_pct_mean"),
          "clay_pct_mean": s.get("clay_pct_mean"), "sand_pct_p5_p95": s.get("sand_pct_range"),
          "spearman_sm_delta_vs_sand": cs, "spearman_sm_delta_vs_clay": cc}
    rule = ("Sandy soils drain and dry faster; clay soils retain water. Supported if soil-moisture change "
            "correlates with sand (negatively) or clay (positively) with |rho| >= 0.2.")
    base = f"Soil: predominantly {s.get('texture_class') or 'unknown'} (sand {_f(s.get('sand_pct_mean'), 0)}%, clay {_f(s.get('clay_pct_mean'), 0)}%)"
    best = None
    if cs and cs["rho"] <= -0.2:
        best = ("sand", cs["rho"], "sandier soils lost more / gained less water")
    if cc and cc["rho"] >= 0.2 and (best is None or abs(cc["rho"]) > abs(best[1])):
        best = ("clay", cc["rho"], "clay-rich soils retained / gained more water")
    if best:
        return _factor("soil", name, "supports", _rho_strength(best[1]), ev, rule,
                       f"{base}; {best[2]} (rho vs {best[0]} = {best[1]:+.2f}) — texture modulated the change.")
    rng = s.get("sand_pct_range") or [None, None]
    narrow = rng[0] is not None and rng[1] is not None and rng[1] - rng[0] < 10
    return _factor("soil", name, "inconclusive", None, ev, rule,
                   f"{base}; no clear link between texture and change"
                   + (" (texture varies little across the area)." if narrow else "."))


# ---------------------------------------------------------------- sections
def _when(stats: dict, aoi_lon: float) -> dict:
    t1, t2 = pd.Timestamp(stats["t1"]), pd.Timestamp(stats["t2"])
    local = lambda t: (t + timedelta(hours=aoi_lon / 15)).strftime("%H:%M")  # noqa: E731
    return {
        "t1": stats["t1"], "t2": stats["t2"], "days_between": stats["days"],
        "t1_local_solar_time": local(t1), "t2_local_solar_time": local(t2),
        "statement": (f"Compared {_date(stats['t1'])} with {_date(stats['t2'])} ({stats['days']:.0f} days apart), "
                      f"both acquired around {local(t2)} local solar time on the same orbit track."),
    }


def _how_much(stats: dict, ov: dict) -> dict:
    d = stats["delta"] or {}
    return {
        "mean_sm_t1": stats["mean_sm_t1"], "mean_sm_t2": stats["mean_sm_t2"],
        "mean_delta": d.get("mean"), "median_delta": d.get("median"),
        "p5_delta": d.get("p5"), "p95_delta": d.get("p95"),
        "wetter_area_km2": ov["wet_km2"], "wetter_pct": ov["wet_pct"],
        "drier_area_km2": ov["dry_km2"], "drier_pct": ov["dry_pct"],
        "compared_area_km2": stats["compared_area_km2"],
        "statement": (f"Average soil moisture went from {_f(stats['mean_sm_t1'])} to {_f(stats['mean_sm_t2'])} m3/m3 "
                      f"({_f(d.get('mean'), 3, True)}; middle 90% of pixels between {_f(d.get('p5'), 2, True)} and "
                      f"{_f(d.get('p95'), 2, True)}). {ov['wet_pct']}% of the analysed {stats['compared_area_km2']:.0f} km2 "
                      f"became significantly wetter and {ov['dry_pct']}% significantly drier."),
    }


def _where(summary: dict, regions: list[dict], n_top: int) -> dict:
    by = summary["by_direction"]
    parts = []
    for d in ("wetting", "drying"):
        s = by.get(d, {})
        if s.get("n_regions"):
            locs = list(s["area_by_location_km2"].items())[:2]
            loc_txt = " and ".join(f"{k} ({v:.0f} km2)" for k, v in locs)
            parts.append(f"{s['n_regions']} {d} regions totalling {s['area_km2']:.0f} km2, mainly in the {loc_txt}")
    return {
        "by_direction": by,
        "top_regions": [r["region_id"] for r in regions[:n_top]],
        "statement": ("Changes are concentrated as " + "; ".join(parts) + ".") if parts
        else "No coherent change regions above the minimum size were found.",
    }


def _quality(stats: dict, veg: dict, factors: list[dict] | None = None) -> dict:
    d = stats["delta"] or {}
    sigma = stats.get("median_combined_uncertainty")
    snr = abs(d.get("mean", 0)) / sigma if sigma else None
    notes = ["NISAR SME2 data are from the PROVISIONAL collection and not fully calibrated."]
    if stats["compared_fraction"] < 0.6:
        notes.append(f"Only {stats['compared_fraction']:.0%} of the AOI could be compared on both dates.")
    nr = stats["not_compared_reasons"]
    top = sorted(((k, v) for k, v in nr.items() if v), key=lambda kv: -kv[1])[:3]
    if top:
        notes.append("Main reasons pixels were excluded: " + ", ".join(f"{k.replace('_', ' ')} ({v})" for k, v in top) + ".")
    if snr is not None and snr < 1:
        notes.append(f"The mean change is smaller than the typical retrieval uncertainty (signal/noise {snr:.1f}).")
    if veg.get("available") and veg.get("ndvi_delta_mean") is not None and abs(veg["ndvi_delta_mean"]) > 0.15:
        notes.append("Vegetation changed strongly; radar soil-moisture retrievals can be affected by vegetation "
                     "water content, so part of the signal may be vegetation-related.")
    by_id = {f["id"]: f for f in (factors or [])}
    if by_id.get("reanalysis", {}).get("verdict") == "contradicts":
        notes.append("NISAR and the weather-driven ERA5-Land model disagree on the direction of change; "
                     "ERA5-Land does not simulate irrigation, but its 0-7 cm layer and ~9 km resolution also "
                     "differ from NISAR's ~5 cm / 200 m retrieval. Field or in-situ checks are advised.")
    return {"compared_fraction": stats["compared_fraction"],
            "median_combined_uncertainty": sigma,
            "signal_to_noise": None if snr is None else round(snr, 2),
            "excluded_pixels_by_reason": nr, "caveats": notes}


def _region_text(r: dict, ctx: dict | None, n: int) -> str:
    txt = (f"Region #{r['rank']} ({r['area_km2']:.1f} km2, {r['location_in_aoi']} of the AOI, "
           f"{r['dominant_land_cover_pct']:.0f}% {r['dominant_land_cover']}) became "
           f"{'wetter' if r['direction'] == 'wetting' else 'drier'} by {_f(r['mean_delta'], 3, True)} m3/m3 "
           f"({_f(r['mean_sm_t1'])} -> {_f(r['mean_sm_t2'])}).")
    if not ctx:
        return txt
    extra = []
    if ctx.get("ndvi_t1") is not None and ctx.get("ndvi_t2") is not None:
        extra.append(f"NDVI {ctx['ndvi_t1']:.2f} -> {ctx['ndvi_t2']:.2f}")
    if ctx.get("soil_texture"):
        extra.append(f"{ctx['soil_texture']} soil")
    w = ctx.get("weather") or {}
    a1, a2 = w.get(f"rain_{n}d_before_t1_mm"), w.get(f"rain_{n}d_before_t2_mm")
    if a1 is not None and a2 is not None:
        extra.append(f"{n}-day rain {a1:.0f} -> {a2:.0f} mm")
    if w.get("era5_sm_delta") is not None:
        extra.append(f"ERA5-Land change {w['era5_sm_delta']:+.3f}")
    if extra:
        txt += " Context: " + "; ".join(extra) + "."
    if (r["direction"] == "wetting" and r["dominant_land_cover"] == "Cropland" and a1 is not None
            and a2 is not None and a2 - a1 < 10 and (w.get("era5_sm_delta") or 0) <= 0.01):
        txt += " Wetting of cropland without matching rain or modelled wetting suggests irrigation."
    return txt


# ---------------------------------------------------------------- entry point
def explain_pair(stats: dict, regions_summary: dict, regions: list[dict], context: dict,
                 antecedent_days: int = 7, n_top_regions: int = 5) -> dict:
    ov = _overall(stats)
    w = context.get("weather", {"available": False, "error": "not run"})
    v = context.get("vegetation", {"available": False, "error": "not run"})
    s = context.get("soil", {"available": False, "error": "not run"})
    n = antecedent_days

    rain = _rain_factor(w, ov["direction"], n)
    rean = _reanalysis_factor(w, stats, ov["direction"])
    factors = [
        rain,
        _evap_factor(w, ov["direction"], n),
        rean,
        _vegetation_factor(v),
        _irrigation_factor(stats, ov["direction"], rain, rean),
        _soil_factor(s, ov["direction"]),
    ]
    drivers = sorted((f for f in factors if f["verdict"] == "supports"),
                     key=lambda f: -STRENGTH_SCORE.get(f["strength"] or "weak", 1))
    ranked = [{"factor": f["name"], "strength": f["strength"]} for f in drivers]

    ctx_by_id = {c["region_id"]: c for c in context.get("regions", [])}
    region_expl = [{"region_id": r["region_id"], "rank": r["rank"], "direction": r["direction"],
                    "area_km2": r["area_km2"], "statement": _region_text(r, ctx_by_id.get(r["region_id"]), n),
                    "context": ctx_by_id.get(r["region_id"])}
                   for r in regions[:n_top_regions]]

    aoi_lon = (w.get("points") or [{"lon": 0}])[0]["lon"] if w.get("available") else 0
    when = _when(stats, aoi_lon)
    how = _how_much(stats, ov)
    where = _where(regions_summary, regions, n_top_regions)
    quality = _quality(stats, v, factors)

    d = stats["delta"] or {}
    verb = {"wetting": "became wetter", "drying": "became drier", "mixed": "showed mixed wetting and drying",
            "stable": "remained largely stable"}[ov["direction"]]
    drivers_txt = ("; ".join(f"{x['factor']} ({x['strength']})" for x in ranked[:3])
                   if ranked else "no factor stood out")
    headline = (f"Between {_date(stats['t1'])} and {_date(stats['t2'])} the area {verb} "
                f"(mean {_f(d.get('mean'), 3, True)} m3/m3). Most likely contributing factors: {drivers_txt}.")

    narrative = "\n\n".join([
        f"**What & how much.** {how['statement']}",
        f"**Where.** {where['statement']}",
        f"**When.** {when['statement']}",
        "**Why (possible factors).** " + " ".join(f["statement"] for f in factors if f["verdict"] != "unavailable"),
        "**Largest regions.** " + " ".join(r["statement"] for r in region_expl) if region_expl else "",
        "**Caveats.** " + " ".join(quality["caveats"]),
    ]).strip()

    return {
        "headline": headline,
        "overall_direction": ov["direction"],
        "what": {"direction": ov["direction"], "changed_pct_of_compared": ov["changed_pct"],
                 "classes": stats["classes"], "land_cover_breakdown": stats["land_cover_breakdown"]},
        "where": where,
        "when": when,
        "how_much": how,
        "factors": factors,
        "likely_drivers": ranked,
        "regions": region_expl,
        "data_quality": quality,
        "narrative": narrative,
        "method": "Deterministic rule-based attribution; evidence is correlational, not causal proof.",
    }
