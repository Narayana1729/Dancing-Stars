# Data sources

No datasets are downloaded or bundled in Phase 1. Acquisition is planned for a later phase.

## Missions
- **NISAR** (L-band, S-band). Access and sample availability are **unverified**.
- **Sentinel-1** (C-band).

## NISAR product policy
| Product | Use in this project |
|---|---|
| **GCOV** | Default. Radiometrically terrain-corrected backscatter; disturbance detection. |
| **GSLC** | Default. Backscatter amplitude analysis and comparison. |
| GOFF | Not a default forest-monitoring product. |
| GUNW | Not a default forest-monitoring product. |

Encoded in `backend/app/shared/satellite/base.py` and exposed at `GET /api/v1/data-products`.

## Mock imagery
`frontend/src/mock/mockDomains.js` contains placeholder URLs, dates and statistics. They are unverified, some before/after pairs reuse one image, and none were computed here. Do not cite them.


---

# Phase 2: study region and catalogue findings (retrieved 2026-11-13)

All figures below come from live ASF DAAC catalogue queries (metadata only). No pixel data has been downloaded.
Raw results: `data/reference/rondonia_catalogue_search.json`.

## Study region: Rondônia, Brazilian Amazon
- Bounding box (W,S,E,N): **-63.5, -10.5, -62.5, -9.5** (≈ 109 km × 111 km; deforestation frontier).
- Chosen because NISAR coverage there is dense. Other candidates checked (Oregon Cascades, Sierra Nevada, Borneo, Mt Rinjani, Congo) also have coverage; Oregon and Sierra have the most repeat passes.
- Selected track: **NISAR ascending path 60, frame 172** — 11 acquisitions, full-frame coverage, HH+HV (one scene HH only):
  2025-11-02, 2026-06-18, 06-30, 07-12, 07-24, 08-17, 08-29, 09-10, 09-22 (HH only), 10-04, 10-16 (~12-day repeat; gap Nov 2025 → Jun 2026).
  Note the 2025-11-02 scene has CRID `X05009` (different processing configuration from the later `P05023` scenes), which matters for comparisons.

## Products (ASF catalogue)
| Product | Format | Size / scene (this track) | Pol | Notes |
|---|---|---|---|---|
| NISAR L2 GCOV | HDF5 (.h5) | ≈ 1.5–2.0 GB | HH, HV | Terrain-corrected covariance; preferred for backscatter analysis. |
| NISAR L2 GSLC | HDF5 (.h5) | ≈ 6.4–12.5 GB | HH, HV | Complex data; too large for routine use. |
| Sentinel-1 GRD_HD (IW) | SAFE zip | ≈ 1.0 GB | VV+VH | Descending path; 10 scenes 2026-09-09 … 2026-10-03+ over the box. Supplementary only. |

Spatial resolution, nodata value and CRS for NISAR GCOV are **not yet confirmed** — they must be read from a downloaded file (see `scripts/preprocessing/inspect_gcov.py`, untested).

## Access
- Catalogue search: public, no login.
- Download: **requires NASA Earthdata Login** (anonymous request returned HTTP 401 → `urs.earthdata.nasa.gov`). Provide `EARTHDATA_TOKEN` or `~/.netrc`. Credentials are never stored by the scripts.

## Pipeline
`scripts/download_data/acquire.py` (`search`, `info`, `download --yes`, `verify`) on top of `backend/app/shared/satellite/asf.py`. Downloads go to `data/raw/` (git-ignored) with a manifest at `data/raw/manifest.jsonl`.

---

# Primary Study Region: Similipal Tiger Reserve, Odisha, India

## Geographic Definition
- Centroid: 86.35°E, 21.75°N (Mayurbhanj District, Odisha)
- Bounding Box (W, S, E, N): `86.05°E, 21.45°N, 86.65°E, 22.05°N`
- Forest Extent: > 2,750 km² dense moist deciduous and semi-evergreen Sal forest.

## Satellite Data Acquisition Plan
- Primary Sensor: NISAR L-SAR (L-band)
- Product: L2 GCOV (Geocoded Polarimetric Covariance, RTC)
- Primary Orbital Geometry: Track 98, Frame 12 (Ascending Pass)
- Orbit Cadence: Strict 12-day repeat cycle
- Polarizations: Dual-pol (HH + HV)
- Consistent Production Configuration: 21 repeat acquisitions with invariant CRID `P05023` from March 2026 to October 2026.
- Baseline Pre-Fire Observation: `NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001` (2026-03-04, 3,776 MB)
- Target Fire/Post-Fire Observation: `NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001` (2026-04-21, 3,772 MB)
- Complementary C-band Data: 39 Sentinel-1 GRD_HD (IW, VV+VH) scenes.

## Independent Ground-Truth & Validation
- Forest Survey of India (FSI): ISFR 2021/2023 Tiger Reserve Canopy Density Maps (VDF, MDF, OF, Scrub).
- FSI Van Agni: SNPP-VIIRS 375m and MODIS active fire detections and burnt area polygons.
- NASA FIRMS: Active fire anomalies and Fire Radiative Power (FRP).
- ISRO Bhuvan: National LULC 1:50,000 digital vector datasets and fire hazard zonation.

## European Observation Quarantined
The downloaded 4.8 GB European observation (`NISAR_L2_PR_GCOV_002_109_...h5`) in `data/raw/` is retained strictly as an engineering/calibration baseline for testing HDF5 extraction, EPSG transforms, and polarimetric decimation. It is not mixed with Indian science data.
