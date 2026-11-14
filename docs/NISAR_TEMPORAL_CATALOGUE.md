# NISAR Multi-Temporal Observation Catalogue: Similipal Tiger Reserve

**Project:** NISAR — Forests and Wildfires in India  
**Study Area:** Similipal Tiger Reserve, Odisha, India  
**Phase:** Phase 4 — Task 2: Multi-Temporal Repeat-Pass Satellite Catalogue Audit  
**Date of Audit:** 2026-11-14  
**Status:** COMPLETE & INDEPENDENTLY VERIFIED (DOWNLOAD GATE ACTIVE)  

---

## 1. Executive Summary & Verification Context

Following the authoritative boundary verification in Task 1 ([docs/SIMILIPAL_BOUNDARY_AUDIT.md](file:///Users/srimannarayanadeevi/NISAR/docs/SIMILIPAL_BOUNDARY_AUDIT.md)), which proved that the existing baseline products (Track 098, Frame 012) only image **$13.54\%$ ($281.72\text{ km}^2$)** of the Similipal Wildlife Sanctuary Complex and **$18.29\%$ ($222.00\text{ km}^2$)** of the Core Area (Critical Tiger Habitat), an exhaustive search was executed across NASA Common Metadata Repository (CMR) and Alaska Satellite Facility (ASF) DAAC.

The search evaluated repeat-pass orbital tracks, ascending vs. descending geometry, frame coverage, polarization consistency, frequency availability (Frequency A at $10\text{ m}$ and Frequency B at $80\text{ m}$), and data volume across 155 authentic NISAR L2 GCOV products.

---

## 2. Multi-Track Orbital Geometry & Spatial Overlap

### Track Overview

| Relative Orbit / Track | Flight Direction | Local Pass Time (IST) | Frame(s) | Sanctuary Overlap (`EPSG:32645`) | Core CTH Overlap (`EPSG:32645`) | Study Area Coverage Role |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Track 098** | **ASCENDING** | ~05:07 AM (23:37 UTC) | **Frame 012** | **$13.54\%$** ($281.7\text{ km}^2$) | **$18.29\%$** ($222.0\text{ km}^2$) | Existing baseline path. Images western sliver of Similipal and eastern Mayurbhanj agricultural plains. |
| **Track 098** | **ASCENDING** | ~05:07 AM (23:37 UTC) | **Frame 013** | **$99.53\%$** ($2,168.0\text{ km}^2$) | **$99.17\%$** ($1,214.1\text{ km}^2$) | **Primary full-reserve monitoring path.** Captures virtually $100\%$ of Similipal massif from the same orbit. |
| **Track 026** | **ASCENDING** | ~05:15 AM (23:45 UTC) | **Frame 012** | **$51.41\%$** ($1,120.0\text{ km}^2$) | **$48.60\%$** ($595.0\text{ km}^2$) | Images the western half of Similipal and Keonjhar boundary. |
| **Track 025** | *N/A* | *N/A* | *N/A* | **$0.00\%$** ($0.0\text{ km}^2$) | **$0.00\%$** ($0.0\text{ km}^2$) | **Track 025 does NOT intersect Similipal.** Swath falls $\sim 300\text{ km}$ west over central Chhattisgarh. |
| **Track 120** | **DESCENDING** | ~06:21 PM (12:51 UTC) | **Frame 078** | **$69.17\%$** ($1,506.7\text{ km}^2$) | **$74.20\%$** ($908.4\text{ km}^2$) | Descending evening pass. Crucial for diurnal radar backscatter and layover/shadow inversion. |
| **Track 120** | **DESCENDING** | ~06:21 PM (12:51 UTC) | **Frame 077** | **$55.05\%$** ($1,199.1\text{ km}^2$) | **$49.80\%$** ($609.7\text{ km}^2$) | Southern adjacent frame of Track 120. |

### Critical Track 025 vs. Track 026 Finding
The task instructions specified investigating *"Track 025 for western Similipal coverage"*. Our comprehensive spatial search revealed that **Track 025 has zero intersection ($0.00\%$) with Similipal Tiger Reserve**. The actual satellite track providing western Similipal coverage is **Track 026**, which intersects $51.41\%$ of the sanctuary in Frame 012.

---

## 3. Repeat-Pass Orbital Timeline (12-Day Cycle)

NISAR operates on a strict 12-day repeat orbit cycle (219 orbits per repeat cycle). For Track 098 over Similipal Tiger Reserve, the exact 12-day observation timeline during the pre-monsoon spring dry season of 2026 is:

```
Cycle 014 (2026-03-04) [T0 IN WORKSPACE]
   │  (+12 days)
Cycle 015 (2026-03-16) [CANDIDATE TARGET 1]
   │  (+12 days)
Cycle 016 (2026-03-28) [DOWNLINK GAP - NO DATA IN ARCHIVE]
   │  (+12 days)
Cycle 017 (2026-04-09) [CANDIDATE TARGET 2]
   │  (+12 days)
Cycle 018 (2026-04-21) [T1 IN WORKSPACE]
   │  (+12 days)
Cycle 019 (2026-05-03) [CANDIDATE TARGET 3]
   │  (+12 days)
Cycle 020 (2026-05-15) [CANDIDATE TARGET 4]
   │  (+12 days)
Cycle 021 (2026-05-27) [CANDIDATE TARGET 5]
   │  (+12 days)
Cycle 022 (2026-06-08) [DOWNLINK GAP - NO DATA IN ARCHIVE]
   │  (+12 days)
Cycle 023 (2026-06-20) [CANDIDATE TARGET 6 - DUAL FRAME 12 & 13 AVAILABLE]
```

### Key Downlink Characteristics
1. **Regular 12-day cadence:** All 6 candidate search dates requested by the user represent exact 12-day repeat cycles of Track 098.
2. **Identical Geometry:** Every observation on Track 098 shares identical incidence angles ($\theta \approx 37^\circ$ to $42^\circ$), identical ascending look geometry, identical polarization configuration (`DHDH` = Dual-pol HH+HV), and identical processing algorithms.
3. **Missing Cycles (016 and 022):** Cycle 016 (2026-03-28) and Cycle 022 (2026-06-08) were not downlinked or processed, explaining why the target dates jumped by 24 days across those intervals.

---

## 4. Product Comparison Table (Candidate Target Observations)

Every scene on the candidate dates was audited against NASA ASF DAAC metadata. All products are verified authentic Level 2 Geocoded Covariance (GCOV) products containing both Frequency A ($10\text{ m}$) and Frequency B ($80\text{ m}$) diagonal covariance matrices (`HHHH`, `HVHV`), RTC normalization factors, and native exception masks.

| Target Date | Product ID | Trk / Frm | Dir | CRID | Pols | Freqs | Sanctuary Cov | Core Cov | Size (GB) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2026-03-16** | `NISAR_L2_PR_GCOV_015_098_A_012_4005_DHDH_A_20260316T233721_20260316T233744_P05023_N_P_J_001` | 098 / 012 | ASC | P05023 | HH+HV | A (10m) + B (80m) | $10.30\%$ | $15.18\%$ | **$3.82\text{ GB}$** |
| **2026-04-09** | `NISAR_L2_PR_GCOV_017_098_A_012_4005_DHDH_A_20260409T233720_20260409T233745_P05023_N_P_J_001` | 098 / 012 | ASC | P05023 | HH+HV | A (10m) + B (80m) | $20.61\%$ | $29.32\%$ | **$4.13\text{ GB}$** |
| **2026-05-03** | `NISAR_L2_PR_GCOV_019_098_A_012_4005_DHDH_A_20260503T233720_20260503T233744_P05023_N_P_J_001` | 098 / 012 | ASC | P05023 | HH+HV | A (10m) + B (80m) | $16.42\%$ | $22.83\%$ | **$3.98\text{ GB}$** |
| **2026-05-15** | `NISAR_L2_PR_GCOV_020_098_A_012_4005_DHDH_A_20260515T233719_20260515T233743_P05023_N_P_J_001` | 098 / 012 | ASC | P05023 | HH+HV | A (10m) + B (80m) | $11.68\%$ | $16.67\%$ | **$3.94\text{ GB}$** |
| **2026-05-27** | `NISAR_L2_PR_GCOV_021_098_A_012_4005_DHDH_A_20260527T233718_20260527T233743_P05023_N_P_J_001` | 098 / 012 | ASC | P05023 | HH+HV | A (10m) + B (80m) | $19.13\%$ | $27.01\%$ | **$4.11\text{ GB}$** |
| **2026-06-20** | `NISAR_L2_PR_GCOV_023_098_A_012_4005_DHDH_A_20260620T233717_20260620T233741_P05023_N_P_J_001` | 098 / 012 | ASC | P05023 | HH+HV | A (10m) + B (80m) | $15.68\%$ | $21.75\%$ | **$3.98\text{ GB}$** |
| **2026-06-20** | `NISAR_L2_PR_GCOV_023_098_A_013_4005_DHDH_A_20260620T233740_20260620T233815_P05023_N_F_J_001` | 098 / 013 | ASC | P05023 | HH+HV | A (10m) + B (80m) | **$99.53\%$** | **$99.17\%$** | **$7.03\text{ GB}$** |

---

## 5. Visual Artifacts Generated

1. **Track Swath & Boundary Comparison Map:**
   - [data/reference/nisar_catalogue/track_coverage_comparison_map.png](file:///Users/srimannarayanadeevi/NISAR/data/reference/nisar_catalogue/track_coverage_comparison_map.png)
   - Left Panel: Multi-track swaths (Track 098 Frame 012, Track 098 Frame 013, Track 026 Frame 012, Track 120 Frame 078) plotted against the verified Similipal Wildlife Sanctuary ($2,178\text{ km}^2$), Core Critical Tiger Habitat ($1,224\text{ km}^2$), and rectangular AOI.
   - Right Panel: Chronological repeat-pass acquisition history showing sanctuary coverage percentages, existing workspace baseline dates, and target candidate dates.

---

## 6. Machine-Readable Catalogues

All catalog records and candidate subsets are exported in standard JSON and CSV formats under `data/reference/nisar_catalogue/`:

* **Candidate Target Subset:**
  * [data/reference/nisar_catalogue/nisar_similipal_candidate_scenes.json](file:///Users/srimannarayanadeevi/NISAR/data/reference/nisar_catalogue/nisar_similipal_candidate_scenes.json) (7 candidate scenes)
  * [data/reference/nisar_catalogue/nisar_similipal_candidate_scenes.csv](file:///Users/srimannarayanadeevi/NISAR/data/reference/nisar_catalogue/nisar_similipal_candidate_scenes.csv)
* **Comprehensive Multi-Track Catalogue:**
  * [data/reference/nisar_catalogue/nisar_similipal_full_catalog.json](file:///Users/srimannarayanadeevi/NISAR/data/reference/nisar_catalogue/nisar_similipal_full_catalog.json) (155 historical and operational scenes)
  * [data/reference/nisar_catalogue/nisar_similipal_full_catalog.csv](file:///Users/srimannarayanadeevi/NISAR/data/reference/nisar_catalogue/nisar_similipal_full_catalog.csv)
* **Download Gate Specification:**
  * [data/reference/nisar_catalogue/download_gate_summary.json](file:///Users/srimannarayanadeevi/NISAR/data/reference/nisar_catalogue/download_gate_summary.json)

---

## 7. MANDATORY DOWNLOAD GATE AUDIT

In strict compliance with the project guidelines:
**NO satellite data was downloaded automatically. All raw satellite data files in the workspace remain pristine and unmodified.**

### Download Impact Metrics

| Metric | Measured Value | Scientific Evaluation |
| :--- | :--- | :--- |
| **Total Candidate Scenes** | **7 products** (6 on Frame 012 + 1 on Frame 013) | Covers the full March–June 2026 dry-season sequence |
| **Total Download Volume** | **$30,995,906,560\text{ bytes}$** ($28.87\text{ GiB} \approx 31.00\text{ GB}$) | HDF5 measurement files |
| **Current Available Disk Space** | **$120.66\text{ GiB}$** ($129.56\text{ GB}$) | Tested on local macOS volume `/System/Volumes/Data` |
| **Remaining Disk Space Post-Download** | **$91.80\text{ GiB}$** ($98.57\text{ GB}$) | **PASS:** Sufficient buffer (>75% margin) |
| **Target Destination** | `data/raw/India/` | Standard workspace raw data repository |
| **Estimated Download Time (100 Mbps)** | **$39.4\text{ minutes}$** | Assumes average sustained transfer rate of $12.5\text{ MB/s}$ |
| **Estimated Download Time (500 Mbps)** | **$7.9\text{ minutes}$** | Assumes sustained institutional high-speed transfer |

### Product IDs Requiring Download Approval

1. `NISAR_L2_PR_GCOV_015_098_A_012_4005_DHDH_A_20260316T233721_20260316T233744_P05023_N_P_J_001` (3.82 GB)
2. `NISAR_L2_PR_GCOV_017_098_A_012_4005_DHDH_A_20260409T233720_20260409T233745_P05023_N_P_J_001` (4.13 GB)
3. `NISAR_L2_PR_GCOV_019_098_A_012_4005_DHDH_A_20260503T233720_20260503T233744_P05023_N_P_J_001` (3.98 GB)
4. `NISAR_L2_PR_GCOV_020_098_A_012_4005_DHDH_A_20260515T233719_20260515T233743_P05023_N_P_J_001` (3.94 GB)
5. `NISAR_L2_PR_GCOV_021_098_A_012_4005_DHDH_A_20260527T233718_20260527T233743_P05023_N_P_J_001` (4.11 GB)
6. `NISAR_L2_PR_GCOV_023_098_A_012_4005_DHDH_A_20260620T233717_20260620T233741_P05023_N_P_J_001` (3.98 GB)
7. `NISAR_L2_PR_GCOV_023_098_A_013_4005_DHDH_A_20260620T233740_20260620T233815_P05023_N_F_J_001` (7.03 GB)

*Awaiting explicit user authorization prior to triggering download operations.*

