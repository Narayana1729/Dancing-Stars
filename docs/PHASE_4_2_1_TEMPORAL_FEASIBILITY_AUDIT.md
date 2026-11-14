# PROJECT NISAR — Phase 4.2 Task 4.2.1: Multi-Temporal Data Inventory and Feasibility Audit

**Workspace:** `/Users/srimannarayanadeevi/NISAR`  
**Date:** November 14, 2026  
**Status:** Completed and Verified (66/66 Backend Pytest Tests Passing)  
**Deliverables Generated:**
- Audit Script: [`scripts/run_phase4_2_1_temporal_audit.py`](file:///Users/srimannarayanadeevi/NISAR/scripts/run_phase4_2_1_temporal_audit.py)
- Acquisition Matrix (JSON): [`data/processed/validation/phase4_2_1_acquisition_matrix.json`](file:///Users/srimannarayanadeevi/NISAR/data/processed/validation/phase4_2_1_acquisition_matrix.json)
- Acquisition Matrix (CSV): [`data/processed/validation/phase4_2_1_acquisition_matrix.csv`](file:///Users/srimannarayanadeevi/NISAR/data/processed/validation/phase4_2_1_acquisition_matrix.csv)
- Feasibility Summary (JSON): [`data/processed/validation/phase4_2_1_feasibility_summary.json`](file:///Users/srimannarayanadeevi/NISAR/data/processed/validation/phase4_2_1_feasibility_summary.json)
- Pytest Test Suite: [`backend/tests/test_phase4_2_1_temporal_audit.py`](file:///Users/srimannarayanadeevi/NISAR/backend/tests/test_phase4_2_1_temporal_audit.py)

---

## 1. Executive Summary

Phase 4.2 Task 4.2.1 establishes the authoritative data inventory and scientific feasibility boundaries for multi-temporal forest disturbance monitoring in PROJECT NISAR. Preceding Phase 4.1.1 closed all radiometric calibration discrepancies and established the non-interchangeability of Frequency A (10 m) and Frequency B (80 m).

Task 4.2.1 audited every raw satellite product, reference catalogue, manifest, processed raster, and backend processing module. The fundamental scientific findings are:

1. **Local Satellite Data Reality:**
   - In Similipal Tiger Reserve, India, exactly **two NISAR L-band SAR acquisitions** are present in local storage: `2026-03-04` ($t_0$, Cycle 014) and `2026-04-21` ($t_1$, Cycle 018), separated by a **48-day temporal baseline** ($\Delta t = 48\text{ days}$). Both represent Track 098, Frame 012, Ascending pass.
   - Exactly **four Sentinel-2 L2A raw products** (two pre-event on `2026-03-02`, two post-event on `2026-04-16`, covering tiles `T45QVD` and `T45QVE` on relative orbit `R076`) are present in local storage, providing a **45-day optical temporal baseline**.
   - Exactly **one non-India calibration scene** (`NISAR_L2_PR_GCOV_002_109_..._20251012`) exists in `data/raw/` (Track 109, Frame 063, Descending pass, Rondonia / European UTM 32N coordinates), serving purely as a format validation artifact.

2. **The Two-Date Proof Boundary:**
   - **What Two Dates CAN Prove:** The mathematical backscatter change $\Delta \gamma^0 = \gamma^0(t_1) - \gamma^0(t_0)$, the cross-polarization ratio change $\Delta R$, whether the change exceeds radiometric noise floors and 95% speckle uncertainty, and spatial co-occurrence with optical $\Delta \text{NDVI}$ and $\text{dNBR}$.
   - **What Two Dates CANNOT Prove:** Two dates **strictly cannot prove temporal persistence**, **cannot distinguish permanent canopy loss from temporary deciduous leaf-off or dielectric desiccation**, **cannot determine the exact date of disturbance**, and **cannot track vegetation recovery**.
   - **Methodological Correction:** Naming a two-date drop metric a "persistence indicator" is a scientific misnomer. Establishing true persistence mathematically requires a minimum of **three distinct temporal epochs** ($t_0, t_1, t_2$) spanning at least 72–96 days.

3. **Spatial Swath Boundary Discovery:**
   - Local NISAR Frame 012 covers only the **southern 30.65%** of the Similipal study area ($Y \le 2,400,690\text{ m}$).
   - The northern 69.35% of the reserve (including 11.40 ha of optical disturbance candidates detected in Phase 4.1) falls into **Frame 013**.
   - Comprehensive external catalogue audit revealed that **Frame 013 was not scheduled or acquired by the NISAR mission during March–May 2026**. Frame 013 only exists in winter 2025/2026 (Cycles 006–010) and summer/monsoon 2026 (Cycle 023 onwards). Hence, missing northern coverage during spring 2026 is an inherent satellite mission scheduling reality.

4. **External Time-Series Bridge Opportunity:**
   - For Track 098 Frame 012, the external ASF GCOV catalogue contains **five intermediate and subsequent scenes** in spring 2026: Cycle 015 (`2026-03-16`, +12d), Cycle 017 (`2026-04-09`, -12d before $t_1$), Cycle 019 (`2026-05-03`, +12d after $t_1$), Cycle 020 (`2026-05-15`, +24d), and Cycle 021 (`2026-05-27`, +36d).
   - In accordance with project instructions, **zero files were downloaded**. These 5 scenes are formulated as Priority Rank 1 for user approval, which would bridge the 48-day gap into an unbroken 8-epoch 12-day time series.

---

## 2. Comprehensive Local Satellite Inventory

### 2.1 Locally Downloaded NISAR Acquisitions

| Granule ID | Observation Date (UTC) | Track / Frame / Pass | File Path | Size (GiB) | SHA256 Checksum | Operational Role & Processing Status |
| :--- | :---: | :---: | :--- | :---: | :--- | :--- |
| `NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_..._F_P_J_001` | `2026-03-04T23:37:20Z` | Track 098<br>Frame 012<br>Ascending | `data/raw/India/NISAR_L2_PR_GCOV_014_..._001.h5` | 3.688 | `f5bc144e8efc69b00ec0db65a39bf296bbad8479799ae3f4f56dd3b6b0b0a3b3` | **Pre-Event SAR Baseline ($t_0$)**<br>Cycle 014, CRID P05023.<br>Fully processed to 10m/80m features. |
| `NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_..._N_P_J_001` | `2026-04-21T23:37:20Z` | Track 098<br>Frame 012<br>Ascending | `data/raw/India/NISAR_L2_PR_GCOV_018_..._001.h5` | 3.684 | `2a2f65730000197fefdbbdbd86b04fdc43c0d1559f08b32c6c41c8734f2b3c8e` | **Post-Event SAR Epoch ($t_1$)**<br>Cycle 018, CRID P05023.<br>Fully processed to 10m/80m features. |
| `NISAR_L2_PR_GCOV_002_109_D_063_4005_DHDH_A_20251012T182508_..._N_P_J_001` | `2025-10-12T18:25:08Z` | Track 109<br>Frame 063<br>Descending | `data/raw/NISAR_L2_PR_GCOV_002_109_..._001.h5` | 4.504 | `919df2dfa5ab30ccfacc2ea83208a849b78e5d067310dea1019ff4a25602820e` | **Non-India Test Granule**<br>Cycle 002, CRID X05010.<br>Raw test file (UTM 32N / Europe). |

### 2.2 Locally Downloaded Sentinel-2 L2A Zips

| Product ID | Acquisition Date | Tile / Orbit | File Path | Size (GiB) | Cloud (%) | SHA256 Checksum | Operational Role & Processing Status |
| :--- | :---: | :---: | :--- | :---: | :---: | :--- | :--- |
| `S2C_MSIL2A_20260302T044721_N0512_R076_T45QVD_...` | `2026-03-02` | T45QVD<br>R076 | `data/reference/sentinel2_raw/...T45QVD...zip` | 0.623 | 0.00% | `b6acd53df93655cbfd507da45fd803af33b28ef8720d374558a390ac084182d7` | **Pre-Event Optical Baseline**<br>Southern Similipal tile. SCL masked, processed to NDVI/NDMI/NBR. |
| `S2C_MSIL2A_20260302T044721_N0512_R076_T45QVE_...` | `2026-03-02` | T45QVE<br>R076 | `data/reference/sentinel2_raw/...T45QVE...zip` | 0.871 | 6.50% | `6cbd39b096f229cd256390f4980fe5e866f9f01e7d10f4e10802622b8a6ca697` | **Pre-Event Optical Baseline**<br>Northern Similipal tile. SCL masked, processed to NDVI/NDMI/NBR. |
| `S2B_MSIL2A_20260416T044659_N0512_R076_T45QVD_...` | `2026-04-16` | T45QVD<br>R076 | `data/reference/sentinel2_raw/...T45QVD...zip` | 0.630 | 6.64% | `62e94f654e3dd5a35a36e8a71e317de4d379be4c4a386e664837e270e30ae097` | **Post-Event Optical Assessment**<br>Southern Similipal tile. SCL masked, processed to dNBR/$\Delta$NDVI. |
| `S2B_MSIL2A_20260416T044659_N0512_R076_T45QVE_...` | `2026-04-16` | T45QVE<br>R076 | `data/reference/sentinel2_raw/...T45QVE...zip` | 0.877 | 2.09% | `cc1b2f9b50ad50e6334f25ccde8cdcff1291b5e764de41d73b46c5be77fd2426` | **Post-Event Optical Assessment**<br>Northern Similipal tile. SCL masked, processed to dNBR/$\Delta$NDVI. |

---

## 3. Date-by-Date Temporal Acquisition Matrix

The unified matrix integrates all 286 catalogued and local satellite observations across Similipal Tiger Reserve and reference datasets.

```
Total Catalogued Observations: 286
├── External Catalogue Only:   279 (153 NISAR + 126 Sentinel-2)
├── Downloaded Local Raw:        1 (NISAR Rondonia test granule)
└── Successfully Processed:      6 (2 NISAR India + 4 Sentinel-2 India)
```

### 3.1 Inventory Status Breakdown

1. **Successfully Processed ($N = 6$):**
   - Both Similipal NISAR acquisitions (`2026-03-04` and `2026-04-21`) calibrated and processed to Frequency A (10 m) and Frequency B (80 m) polarimetric rasters.
   - All four Sentinel-2 L2A raw zips processed into 10 m and 80 m reference layers ($\text{NDVI}$, $\text{NDMI}$, $\text{NBR}$, $\text{dNBR}$, and discrete validation labels).
2. **Downloaded Local Raw ($N = 1$):**
   - `NISAR_L2_PR_GCOV_002_109_..._20251012.h5` (4.504 GiB) verified on disk; non-study area format check.
3. **External Catalogue Only ($N = 279$):**
   - 153 NISAR scenes in ASF DAAC GCOV catalogue covering Similipal across tracks 098, 026, 120, 019, 048.
   - 126 Sentinel-2 L2A products in Copernicus Data Space Ecosystem covering tiles T45QVD and T45QVE across orbits R076 and R033.
4. **Scientifically Suitable ($N = 89$):**
   - 89 observations satisfy geometry matching (Track 098 Ascending for NISAR, Orbit R076 or clear R033 for Sentinel-2) and cloud threshold ($< 10\%$).

### 3.2 Multi-Sensor Chronological Alignment (Spring 2026 Focus Window)

| Observation Date | Sensor | Granule / Product | Geometry | Local Status | Scientific Role |
| :---: | :---: | :--- | :--- | :---: | :--- |
| **2026-03-02** | Sentinel-2C | `..._R076_T45QVD` + `T45QVE` | Orbit R076 | **PROCESSED** | Pre-event optical baseline (0.0% & 6.5% cloud). |
| **2026-03-04** | **NISAR L-SAR** | `..._014_098_A_012_...` | Track 098 Frame 012 | **PROCESSED** | **SAR $t_0$ Pre-Event Baseline** (Cycle 014, Ascending). |
| *2026-03-16* | NISAR L-SAR | `..._015_098_A_012_...` | Track 098 Frame 012 | External Only | 12-day SAR follow-up (+12d); in external catalogue. |
| *2026-03-27* | Sentinel-2B | `..._R076_T45QVD` + `T45QVE` | Orbit R076 | External Only | Clear optical observation (0.0% cloud); in catalogue. |
| *2026-04-01* | Sentinel-2C | `..._R076_T45QVD` + `T45QVE` | Orbit R076 | External Only | Clear optical observation (0.0% cloud); in catalogue. |
| *2026-04-09* | NISAR L-SAR | `..._017_098_A_012_...` | Track 098 Frame 012 | External Only | 12-day pre-T1 SAR observation (-12d); in external catalogue. |
| *2026-04-11* | Sentinel-2C | `..._R076_T45QVD` + `T45QVE` | Orbit R076 | External Only | Clear optical observation (0.7% cloud); in catalogue. |
| **2026-04-16** | Sentinel-2B | `..._R076_T45QVD` + `T45QVE` | Orbit R076 | **PROCESSED** | Post-event optical assessment (6.6% & 2.1% cloud). |
| **2026-04-21** | **NISAR L-SAR** | `..._018_098_A_012_...` | Track 098 Frame 012 | **PROCESSED** | **SAR $t_1$ Post-Event Epoch** (Cycle 018, Ascending). |
| *2026-05-03* | NISAR L-SAR | `..._019_098_A_012_...` | Track 098 Frame 012 | External Only | 12-day post-T1 SAR observation (+12d); in external catalogue. |
| *2026-05-15* | NISAR L-SAR | `..._020_098_A_012_...` | Track 098 Frame 012 | External Only | 24-day post-T1 SAR observation (+24d); in external catalogue. |
| *2026-05-27* | NISAR L-SAR | `..._021_098_A_012_...` | Track 098 Frame 012 | External Only | 36-day post-T1 SAR observation (+36d); in external catalogue. |

The optical pre-event baseline is acquired **2 days before SAR $t_0$**, and the optical post-event assessment is acquired **5 days before SAR $t_1$**. Both multi-sensor pairs are tightly temporally coupled.

---

## 4. Evaluation of Scientific Feasibility Across Core Objectives

### 4.1 Two-Date Change Detection ($t_0 = \text{March 4}$, $t_1 = \text{April 21}$, 2026)
- **Feasibility:** `FEASIBLE_WITH_CAVEATS`
- **Capabilities:**
  - Computation of calibrated backscatter power differencing: $\Delta \gamma^0_{HH} = \gamma^0_{HH}(t_1) - \gamma^0_{HH}(t_0)$ and $\Delta \gamma^0_{HV} = \gamma^0_{HV}(t_1) - \gamma^0_{HV}(t_0)$.
  - Depolarization ratio differencing: $\Delta R = R(t_1) - R(t_0) = \Delta \gamma^0_{HV} - \Delta \gamma^0_{HH}$.
  - Radiometric thresholding against noise floor and 95% speckle uncertainty envelopes.
  - Stratification across management zones (Core Reserve vs Sanctuary Buffer) inside Frame 012.
- **Caveats:**
  - Changes observed over a 48-day baseline represent a temporal composite.
  - Spatial coverage is limited to southern Similipal ($Y \le 2,400,690\text{ m}$).

### 4.2 Short-Term Temporal Change (<12 Days, 12-Day, 24-Day)
- **Feasibility:** `INFEASIBLE_WITH_LOCAL_DATA`
- **Scientific Rationale:**
  - The local SAR dataset contains only two dates with a 48-day gap ($\Delta t = 48\text{ days}$).
  - No 12-day or 24-day observations are present in local storage.
  - Intermediate dynamic processes (abrupt logging vs progressive drying vs fire progression) cannot be resolved.

### 4.3 Seasonal Baseline Estimation (Dry vs Monsoon vs Post-Monsoon)
- **Feasibility:** `INFEASIBLE_WITH_LOCAL_DATA`
- **Scientific Rationale:**
  - Both available dates lie within a single late-winter/mid-spring dry season.
  - Tropical dry deciduous forests in eastern India exhibit natural annual backscatter cycles ($\sigma_{\text{seasonal}} \sim 1.5 - 2.5\text{ dB}$) due to canopy foliage flush, monsoon soil moisture saturation, and dry-season leaf senescence.
  - Characterizing this baseline requires a minimum of 12–24 continuous months of observation across wet, transition, and dry seasons.

### 4.4 Persistent Disturbance Detection
- **Feasibility:** `INFEASIBLE_WITH_TWO_DATES`
- **Mathematical Proof Boundary:**
  - A two-date difference proves only that $\Delta \gamma^0 \ne 0$ between March 4 and April 21, 2026.
  - A backscatter reduction $\Delta \gamma^0_{HV} \le -2.5\text{ dB}$ can be caused by:
    1. Permanent forest canopy removal (deforestation, clear-felling).
    2. Temporary deciduous leaf-off and moisture loss.
    3. Severe soil dielectric desiccation.
    4. Scorching of understory biomass without structural canopy destruction.
  - To prove persistence, a minimum of **three sequential epochs** ($t_0, t_1, t_2$) is required:
    $$\text{Persistence Condition: } \gamma^0(t_1) \le \gamma^0(t_0) - \tau \quad \land \quad \gamma^0(t_2) \le \gamma^0(t_0) - \tau_{\text{persist}}$$
    Where $t_2$ is observed 30–60 days after $t_1$ to confirm that the canopy has not recovered.

### 4.5 Recovery Assessment (Secondary Regrowth and Greening)
- **Feasibility:** `INFEASIBLE_WITH_LOCAL_DATA`
- **Scientific Rationale:**
  - The latest locally available SAR observation is $t_1$ (`2026-04-21`).
  - Zero post-$t_1$ satellite observations are present in local storage.
  - Assessing post-disturbance recovery requires observations during the subsequent monsoon (July–September 2026) and post-monsoon (October–December 2026) seasons.

### 4.6 Wildfire Impact Assessment
- **Feasibility:** `PARTIALLY_FEASIBLE_POST_EVENT_ONLY`
- **Capabilities:**
  - Retrospective burn scar severity mapping using paired Sentinel-2 $\text{NBR}$ and $\text{dNBR}$ (March 2 vs April 16, 2026).
  - Cross-comparison of L-band backscatter drops against optical burn severity classes.
- **Limitations:**
  - Infeasible for active fire front tracking (revisit intervals of 12 days for NISAR and 5 days for Sentinel-2 are far too coarse compared to MODIS/VIIRS 6-hour thermal alerts).
  - The primary optical disturbance area (11.40 ha) lies entirely north of local NISAR Frame 012.

### 4.7 The Two-Date Proof Boundary Table

| Feature / Objective | Provable with 2 Dates ($t_0, t_1$) | NOT Provable with 2 Dates ($t_0, t_1$) | Minimum Requirement for Proof |
| :--- | :---: | :---: | :--- |
| **Instantaneous Backscatter Change** | **YES** | — | 2 dates with verified radiometric calibration. |
| **Speckle Uncertainty Exceedance** | **YES** | — | 2 dates with known equivalent number of looks (ENL). |
| **Dual-Polarization Corroboration** | **YES** | — | 2 dates with co-registered HH and HV channels. |
| **Optical Coincident Change** | **YES** | — | Near-synchronous optical pair ($\Delta \text{NDVI}$, $\text{dNBR}$). |
| **Exact Disturbance Date** | NO | **CANNOT PROVE** | Dense daily-to-weekly time series. |
| **Abrupt vs Gradual Distinction** | NO | **CANNOT PROVE** | Intervening 12-day observations ($t_{0+12d}$, $t_{0+24d}$, $t_{0+36d}$). |
| **Decoupling Moisture from Defoliation** | NO | **CANNOT PROVE** | Multi-temporal polarimetric decomposition or in situ sensors. |
| **Temporal Persistence** | NO | **CANNOT PROVE** | At least 3 sequential epochs ($t_0, t_1, t_2$). |
| **Vegetation Recovery / Greening** | NO | **CANNOT PROVE** | Post-disturbance time series spanning subsequent growing seasons. |
| **Annual Seasonal Baseline** | NO | **CANNOT PROVE** | Multi-year time series across all 4 astronomical seasons. |

---

## 5. Acquisition Compatibility Audit

### 5.1 Track and Frame Consistency
- Local NISAR files share identical track and frame parameters: **Track 098, Frame 012, Ascending pass**.
- Swath geometry is along-track bounded at $Y = 2,400,690\text{ m}$.
- Similipal Tiger Reserve extends north to $Y = 2,438,360\text{ m}$.
- Frame 012 covers **30.65%** of the regional bounding box ($Y \in [2,372,200, 2,400,690]\text{ m}$).
- Frame 013 covers the remaining **88.91%** of the AOI and **99.5%** of the Sanctuary.
- External catalogue audit proves Frame 013 was not scheduled or acquired in March–April 2026 for Track 098.

### 5.2 Ascending vs Descending Orbit Separation
- Track 098 is an **ASCENDING** pass (south-to-north ground track, evening acquisition ~23:37 UTC, left-looking).
- Catalogued scenes for Track 120, Track 019, and Track 048 are **DESCENDING** passes (north-to-south ground track, morning acquisition ~12:52 UTC, left-looking).
- Differencing Ascending against Descending acquisitions is **scientifically invalid**: rugged topography in Similipal (elevations 300 m to 1,180 m) causes inverted foreshortening, layover, and shadowing from opposing look angles. Strict separation is mandatory.

### 5.3 Frequency A (10 m) vs Frequency B (80 m)
- Phase 4.1.1 proved that Frequency A and Frequency B are **fundamentally non-interchangeable**.
- Native pixel-to-pixel correlation between Frequency A and B is $r = 0.178$ at $t_0$ and $r = 0.187$ at $t_1$.
- Correlation increases monotonically with spatial aggregation ($r = 0.44$ at 80 m, $r = 0.81$ at 1,280 m).
- Differencing Frequency A at $t_0$ against Frequency B at $t_1$ is strictly prohibited. Both frequencies must remain independent processing pipelines.

### 5.4 Spatial Grid Alignment and Swath Margins
- Frequency A: $dx = 10.0\text{ m}$, $dy = -10.0\text{ m}$, exact UTM Zone 45N grid.
- Frequency B: $dx = 80.0\text{ m}$, $dy = -80.0\text{ m}$, exact UTM Zone 45N grid.
- Frequency B pixel centers align mathematically with the exact centroids of $8 \times 8$ blocks of Frequency A pixels.
- The active intersection mask between $t_0$ and $t_1$ contains exactly **197,385 valid pixels at 80 m** and **12,632,640 valid pixels at 10 m**. Zero geometric offset or misregistration exists between $t_0$ and $t_1$.

---

## 6. Pipeline Implementation Gaps for Multi-Date Stacking

The inspection of `backend/app/domains/forests/processing/temporal_analysis/` and `scripts/run_multitemporal_analysis.py` identified five specific architectural limitations for multi-date time-series processing:

```
Multi-Temporal Pipeline Architecture Limitations:
├── GAP 1: Hardcoded Two-Date Data Structures (Assumes len(files) == 2, delta_hv_list[0])
├── GAP 2: Hardcoded Output Filenames (_t0.tif, _t1.tif, _delta_hh.tif)
├── GAP 3: Absence of Spatio-Temporal Data Cube Abstraction (No [time, y, x] tensor)
├── GAP 4: Misnamed "persistence_indicator" (Computes single-drop severity, not persistence)
└── GAP 5: Static Two-Point Recovery Trajectory (Cannot fit curves or recovery slopes)
```

1. **Gap 1 — Hardcoded Pairwise Data Structures:**
   - In `temporal_loader.py` and `pipeline.py`, algorithms assume an input list of exactly two files. Supplying $\ge 3$ files causes subsequent zonal extraction to read only `delta_hv_list[0]` ($t_1 - t_0$) and ignore remaining epochs.
2. **Gap 2 — Hardcoded File Naming Conventions:**
   - Export logic writes static filenames (`_hh_t0.tif`, `_delta_hh.tif`) without date or cycle timestamps. Processing multiple temporal pairs currently overwrites previous outputs.
3. **Gap 3 — Absence of Spatio-Temporal Data Cube Abstraction:**
   - The pipeline currently stores lists of 2D NumPy arrays rather than a 3D/4D spatio-temporal data cube ($T \times Y \times X$). This prevents per-pixel time-series algorithms (rolling median/MAD, Theil-Sen slope estimation, BFAST, LandTrendr, or CCDC break-point detection).
4. **Gap 4 — Misnamed Persistence Metric:**
   - In `temporal_features.py` (lines 200–218), `persistence_indicator` is defined as $\sqrt{\max(-\Delta HV, 0) \times \max(-\Delta R, 0)}$. This is an instantaneous drop severity index, not a persistence indicator. It should be refactored to `instantaneous_drop_intensity`.
5. **Gap 5 — Static Recovery Trajectory:**
   - Defined as $HV(t_{\text{last}}) - HV(t_{\text{previous}})$. It cannot evaluate multi-epoch trajectories or calculate post-fire greening rates.

*In accordance with project scope, existing processing code was audited without code refactoring. Stable baseline execution is preserved.*

---

## 7. Ranked List of Proposed Additional Acquisitions (For User Approval)

> [!IMPORTANT]
> **Zero Satellite Products Have Been Downloaded.**
> The following list is submitted for user review and approval. All candidates exist in public external archives (ASF DAAC and Copernicus Data Space Ecosystem).

### Priority Rank 1: Track 098 Frame 012 Dense Spring 2026 Time-Series Bridge
- **Objective:** Bridges the 48-day temporal gap in southern Similipal, transforming the isolated 2-date pair into an unbroken 8-epoch 12-day time series from March 4 to May 27, 2026.
- **Disk Requirement:** 18.5 GiB (5 scenes $\times \approx 3.7\text{ GiB}$).
- **Proposed Scenes:**

| # | Product ID | Observation Date | Cycle | Cadence Step | Size |
| :-: | :--- | :---: | :---: | :---: | :---: |
| 1 | `NISAR_L2_PR_GCOV_015_098_A_012_4005_DHDH_A_20260316T233721_..._001` | `2026-03-16` | 015 | $+12\text{ days after } t_0$ | 3.7 GiB |
| 2 | `NISAR_L2_PR_GCOV_017_098_A_012_4005_DHDH_A_20260409T233720_..._001` | `2026-04-09` | 017 | $-12\text{ days before } t_1$ ($+36\text{d}$) | 3.7 GiB |
| 3 | `NISAR_L2_PR_GCOV_019_098_A_012_4005_DHDH_A_20260503T233720_..._001` | `2026-05-03` | 019 | $+12\text{ days after } t_1$ ($+60\text{d}$) | 3.7 GiB |
| 4 | `NISAR_L2_PR_GCOV_020_098_A_012_4005_DHDH_A_20260515T233719_..._001` | `2026-05-15` | 020 | $+24\text{ days after } t_1$ ($+72\text{d}$) | 3.7 GiB |
| 5 | `NISAR_L2_PR_GCOV_021_098_A_012_4005_DHDH_A_20260527T233718_..._001` | `2026-05-27` | 021 | $+36\text{ days after } t_1$ ($+84\text{d}$) | 3.7 GiB |

### Priority Rank 2: Full-Reserve Northern Coverage Anchor (NISAR Frame 013)
- **Objective:** Provides full-reserve coverage (99.5% Sanctuary, 99.2% Core) before and after the 2026 dry season, enabling SAR inspection of the northern 11.40 ha optical disturbance area.
- **Disk Requirement:** 13.1 GiB (2 scenes $\times \approx 6.55\text{ GiB}$).
- **Proposed Scenes:**

| # | Product ID | Observation Date | Cycle | Cadence Step | Size |
| :-: | :--- | :---: | :---: | :---: | :---: |
| 1 | `NISAR_L2_PR_GCOV_010_098_A_013_4005_DHDH_A_20260115T233741_..._001` | `2026-01-15` | 010 | Pre-fire winter baseline | 6.54 GiB |
| 2 | `NISAR_L2_PR_GCOV_023_098_A_013_4005_DHDH_A_20260620T233740_..._001` | `2026-06-20` | 023 | Post-fire early monsoon assessment | 6.55 GiB |

### Priority Rank 3: Sentinel-2 Multi-Temporal Clear Validation Pairs
- **Objective:** Acquires clear Sentinel-2 L2A observations on identical relative orbit R076 during peak fire activity to track optical burn scar progression and decouple phenological leaf-off from fire damage.
- **Disk Requirement:** 4.5 GiB (3 pairs / 6 zips $\times \approx 0.75\text{ GiB}$).
- **Proposed Scenes:**

| # | Tile Pair | Observation Date | Orbit | Cloud (%) | Size |
| :-: | :--- | :---: | :---: | :---: | :---: |
| 1 | `T45QVD` + `T45QVE` | `2026-03-27` | R076 | 0.00% / 0.00% | 1.5 GiB |
| 2 | `T45QVD` + `T45QVE` | `2026-04-01` | R076 | 0.00% / 0.00% | 1.5 GiB |
| 3 | `T45QVD` + `T45QVE` | `2026-04-11` | R076 | 1.10% / 0.30% | 1.5 GiB |

### Disk Storage Budget Summary
- Current Available Disk Space: **120.66 GiB**
- Total Storage Required for All Proposals (Priority 1 + 2 + 3): **36.1 GiB**
- Projected Available Space After All Downloads: **84.56 GiB** (well above the 20 GiB safety reserve threshold)

---

## 8. Verification and Test Results

The audit script and test suite were executed in `backend/.venv`:
1. Audit script execution: `backend/.venv/bin/python3 scripts/run_phase4_2_1_temporal_audit.py`
   - Generated: [`phase4_2_1_acquisition_matrix.json`](file:///Users/srimannarayanadeevi/NISAR/data/processed/validation/phase4_2_1_acquisition_matrix.json) (286 records)
   - Generated: [`phase4_2_1_acquisition_matrix.csv`](file:///Users/srimannarayanadeevi/NISAR/data/processed/validation/phase4_2_1_acquisition_matrix.csv)
   - Generated: [`phase4_2_1_feasibility_summary.json`](file:///Users/srimannarayanadeevi/NISAR/data/processed/validation/phase4_2_1_feasibility_summary.json)
2. Pytest suite execution: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/ -v`
   - **66 passed, 0 failed, 16 warnings in 9.57 s**.
   - All 6 new automated tests in [`backend/tests/test_phase4_2_1_temporal_audit.py`](file:///Users/srimannarayanadeevi/NISAR/backend/tests/test_phase4_2_1_temporal_audit.py) passed, verifying:
     - `test_local_satellite_inventory_integrity`
     - `test_temporal_acquisition_matrix_structure_and_order`
     - `test_scientific_feasibility_proof_boundaries`
     - `test_acquisition_compatibility_rules`
     - `test_pipeline_implementation_gaps_identified`
     - `test_ranked_acquisition_proposals_and_approval_gate`

---

## 9. Next Steps

With Task 4.2.1 completed, verified, and passing all tests:
1. Present the feasibility findings, two-date proof boundaries, and ranked acquisition proposals to the user.
2. Await user instructions regarding whether to proceed with Task 4.2.2 or authorize downloading any Priority Rank 1/2/3 satellite scenes.
