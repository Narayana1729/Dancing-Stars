"""Rainfall, temperature, evapotranspiration and reanalysis soil moisture
from the Open-Meteo historical archive (ECMWF ERA5 / ERA5-Land, ~0.1 deg).
No API key required.

ERA5-Land soil moisture does not model irrigation, which makes it a useful
independent reference: agreement with NISAR suggests a weather-driven change,
disagreement suggests a local (e.g. irrigation) signal or a retrieval artefact.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import numpy as np
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = ["precipitation_sum", "temperature_2m_mean", "temperature_2m_max", "et0_fao_evapotranspiration"]
HOURLY_VARS = ["soil_moisture_0_to_7cm"]


class WeatherError(RuntimeError):
    pass


def sample_points(aoi: BaseGeometry, step: float = 0.1, max_points: int = 30) -> list[tuple[float, float]]:
    """(lat, lon) points on a regular grid inside the AOI (ERA5-Land is ~0.1 deg)."""
    w, s, e, n = aoi.bounds
    while True:
        lats = np.arange(s + step / 2, n, step)
        lons = np.arange(w + step / 2, e, step)
        zone = aoi.buffer(step / 2)
        pts = [(round(float(la), 4), round(float(lo), 4)) for la in lats for lo in lons if zone.contains(Point(lo, la))]
        if len(pts) <= max_points:
            break
        step *= 1.5
    if not pts:
        c = aoi.centroid
        pts = [(round(c.y, 4), round(c.x, 4))]
    return pts


def fetch(points: list[tuple[float, float]], start: date, end: date, timeout: int = 90) -> list[dict]:
    q = {
        "latitude": ",".join(str(p[0]) for p in points),
        "longitude": ",".join(str(p[1]) for p in points),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": ",".join(DAILY_VARS),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
    }
    req = urllib.request.Request(f"{ARCHIVE_URL}?{urllib.parse.urlencode(q)}", headers={"User-Agent": "nisar-sm-backend"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except Exception as e:
        raise WeatherError(f"Open-Meteo request failed: {e}") from e
    if isinstance(data, dict):
        if data.get("error"):
            raise WeatherError(data.get("reason", "Open-Meteo error"))
        data = [data]
    return data


def _arr(v) -> np.ndarray:
    return np.array([np.nan if x is None else x for x in v], dtype=float)


def _window_sum(days: list[str], vals: np.ndarray, end_excl: date, n: int) -> float:
    start = end_excl - timedelta(days=n)
    sel = [(start <= date.fromisoformat(d) < end_excl) for d in days]
    v = vals[np.array(sel)]
    return float(np.nansum(v)) if v.size and np.isfinite(v).any() else float("nan")


def _window_mean(days, vals, start: date, end_excl: date) -> float:
    sel = np.array([(start <= date.fromisoformat(d) < end_excl) for d in days])
    v = vals[sel]
    return float(np.nanmean(v)) if v.size and np.isfinite(v).any() else float("nan")


def _days_since_rain(days, rain, t: date, threshold: float = 5.0) -> int | None:
    for d, r in zip(reversed(days), reversed(rain.tolist())):
        dd = date.fromisoformat(d)
        if dd < t and r is not None and np.isfinite(r) and r >= threshold:
            return (t - dd).days
    return None


def _hourly_at(times: list[str], vals: np.ndarray, t: datetime) -> float:
    key = t.replace(minute=0, second=0, microsecond=0, tzinfo=None).isoformat(timespec="minutes")
    try:
        return float(vals[times.index(key)])
    except ValueError:
        return float("nan")


def point_metrics(p: dict, t1: datetime, t2: datetime, antecedent_days: int) -> dict:
    d = p["daily"]
    days = d["time"]
    rain = _arr(d["precipitation_sum"])
    et0 = _arr(d["et0_fao_evapotranspiration"])
    tmean = _arr(d["temperature_2m_mean"])
    tmax = _arr(d["temperature_2m_max"])
    h = p["hourly"]
    sm = _arr(h["soil_moisture_0_to_7cm"])
    d1, d2 = t1.date(), t2.date()
    n = antecedent_days
    m = {
        "lat": p["latitude"], "lon": p["longitude"],
        f"rain_{n}d_before_t1_mm": _window_sum(days, rain, d1, n),
        f"rain_{n}d_before_t2_mm": _window_sum(days, rain, d2, n),
        "rain_30d_before_t1_mm": _window_sum(days, rain, d1, 30),
        "rain_30d_before_t2_mm": _window_sum(days, rain, d2, 30),
        "rain_between_mm": _window_sum(days, rain, d2, (d2 - d1).days),
        "rainy_days_between": int(np.nansum(_arr(d["precipitation_sum"])[
            np.array([(d1 <= date.fromisoformat(x) < d2) for x in days])] >= 1.0)),
        "days_since_rain_ge5mm_t1": _days_since_rain(days, rain, d1),
        "days_since_rain_ge5mm_t2": _days_since_rain(days, rain, d2),
        f"et0_{n}d_before_t1_mm": _window_sum(days, et0, d1, n),
        f"et0_{n}d_before_t2_mm": _window_sum(days, et0, d2, n),
        "et0_between_mm": _window_sum(days, et0, d2, (d2 - d1).days),
        f"tmax_{n}d_before_t1_c": _window_mean(days, tmax, d1 - timedelta(days=n), d1),
        f"tmax_{n}d_before_t2_c": _window_mean(days, tmax, d2 - timedelta(days=n), d2),
        "tmean_between_c": _window_mean(days, tmean, d1, d2),
        "era5_sm_t1": _hourly_at(h["time"], sm, t1),
        "era5_sm_t2": _hourly_at(h["time"], sm, t2),
    }
    m["era5_sm_delta"] = m["era5_sm_t2"] - m["era5_sm_t1"]
    m["water_balance_between_mm"] = m["rain_between_mm"] - m["et0_between_mm"]
    return m


def weather_context(aoi: BaseGeometry, t1: datetime, t2: datetime, antecedent_days: int = 7,
                    step: float = 0.1) -> dict:
    pts = sample_points(aoi, step)
    start = (t1 - timedelta(days=35)).date()
    end = t2.date()
    data = fetch(pts, start, end)
    per_point = [point_metrics(p, t1, t2, antecedent_days) for p in data]

    keys = [k for k in per_point[0] if k not in ("lat", "lon")]
    aoi_mean = {}
    for k in keys:
        vals = np.array([pm[k] for pm in per_point if pm[k] is not None], dtype=float)
        nd = 1 if (k.startswith("days_since") or k.endswith(("_mm", "_c"))) else 4
        aoi_mean[k] = round(float(np.nanmean(vals)), nd) if vals.size and np.isfinite(vals).any() else None

    # AOI-mean daily series for charts
    days = data[0]["daily"]["time"]
    series = {"date": days}
    for v in ("precipitation_sum", "et0_fao_evapotranspiration", "temperature_2m_mean"):
        series[v] = np.round(np.nanmean(np.stack([_arr(p["daily"][v]) for p in data]), axis=0), 2).tolist()

    return {
        "source": "Open-Meteo archive (ERA5 / ERA5-Land reanalysis)",
        "n_points": len(per_point),
        "antecedent_days": antecedent_days,
        "aoi_mean": aoi_mean,
        "points": [{k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in pm.items()}
                   for pm in per_point],
        "daily_series": series,
    }
