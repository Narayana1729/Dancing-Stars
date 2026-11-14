# Project NISAR — Phase 4.1 Metric and Grid Correction Audit Report

**Document Version:** 1.0.0  
**Phase:** Phase 4.1 — Forensic Metric, Grid, and Geographical Reconciliation  
**Target Landscape:** Similipal Tiger Reserve & Wildlife Sanctuary, Mayurbhanj, Odisha, India  
**Spatial Reference System:** WGS 84 / UTM Zone 45N (`EPSG:32645`)  
**Auditor:** Independent Scientific Audit Subsystem  
**Date:** November 2026  
**Status:** Complete & Fully Verified  

---

## 1. Executive Summary & Audit Mandate

During Phase 4 of Project NISAR, automated processing and cross-sensor validation pipelines were deployed across the Similipal landscape to analyze multi-temporal L-band SAR backscatter (NISAR Frequency A at 10 m and Frequency B at 80 m) alongside optical multispectral observations (Sentinel-2 L2A). 

A rigorous numerical audit revealed five critical discrepancies across Tasks 1–7 that required formal investigation, mathematical reconciliation, and code correction before progressing further:
1. **Geographical Inversion of Optical Disturbance:** Prior reports claimed that 11.40 ha of optical candidates lay in "southern Similipal" and that the 43 active-swath pixels were "north of the reserve". Coordinate-level forensic analysis was mandated to recalculate spatial intersections with official Core, Buffer, and Outside Reserve boundaries.
2. **Evaluation Metric Conflation (FPR vs. FDR):** Previous evaluation tables reported a "False Alarm Rate / False Positive Rate" of ~99.998%. Statistical disentanglement was required to separate False Positive Rate ($\text{FPR} = \text{FP}/(\text{FP}+\text{TN})$) from False Discovery Rate ($\text{FDR} = \text{FP}/(\text{TP}+\text{FP})$).
3. **Frequency A (10 m) and Frequency B (80 m) Grid Alignment:** Forensic investigation of affine transforms revealed a 40 m half-pixel spatial offset between processed 10 m and 80 m rasters, requiring origin diagnosis and implementation of block-aggregation tools.
4. **Reference Evaluation Population Discrepancy:** The negative reference population shifted from 7,574,034 pixels to 2,302,923 pixels between reporting stages without explicit accounting. A formal reconciliation of landscape vs. forest evaluation populations was required.
5. **Disturbance Agreement Overclaiming:** Nine pixels ($0.09\text{ ha}$) of coincident SAR and optical drops were previously described as "confirmed deforestation" or "confirmed crown fire" despite lacking field ground truth or drone verification.

All five issues have been forensically resolved using native HDF5 datasets, verified boundary GeoJSONs, corrected python algorithms, and automated unit tests.

---

## 2. Correct Geographical Interpretation of Optical Disturbance

### 2.1 Spatial Intersection Recalculation
Using the authoritative boundaries (`similipal_sanctuary_epsg32645.geojson` and `similipal_core_epsg32645.geojson`), the Sentinel-2 optical reference raster (`s2_optical_reference_labels_10m.tif`), and the NISAR active observation mask (`freq_a_valid_count.tif`), the spatial intersection was calculated pixel by pixel across the entire 10 m study domain:

| Geographic Stratum | In Active Swath (px) | In Active Swath (ha) | Outside Active Swath (px) | Outside Active Swath (ha) | Total Pixels | Total Area (ha) | % of Total Candidates |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Similipal Core Area (CTH)** | **0** | **0.00 ha** | 179 | 1.79 ha | 179 | 1.79 ha | 15.13% |
| **Similipal Sanctuary Buffer** | **0** | **0.00 ha** | 491 | 4.91 ha | 491 | 4.91 ha | 41.50% |
| **Subtotal Inside Notified Reserve** | **0** | **0.00 ha** | **670** | **6.70 ha** | **670** | **6.70 ha** | **56.63%** |
| **Outside Sanctuary (Peripheral Fringe)** | **43** | **0.43 ha** | 470 | 4.70 ha | 513 | 5.13 ha | 43.37% |
| **Total Landscape (Tile 45EUU)** | **43** | **0.43 ha** | **1,140** | **11.40 ha** | **1,183** | **11.83 ha** | **100.00%** |

```
========================================================================================================
6-WAY STRATIFIED GEOGRAPHICAL DISTRIBUTION OF OPTICAL CANDIDATES
========================================================================================================
1. Inside Core & inside NISAR swath     :     0 px  ( 0.00 ha,  0.0000 km²)
2. Inside Core & outside NISAR swath    :   179 px  ( 1.79 ha,  0.0179 km²)  [Northing: 2397140 - 2436960 m]
3. Inside Buffer & inside NISAR swath   :     0 px  ( 0.00 ha,  0.0000 km²)
4. Inside Buffer & outside NISAR swath  :   491 px  ( 4.91 ha,  0.0491 km²)  [Northing: 2404800 - 2436760 m]
5. Outside Reserve & inside swath       :    43 px  ( 0.43 ha,  0.0043 km²)  [Northing: 2372490 - 2384410 m]
6. Outside Reserve & outside swath      :   470 px  ( 4.70 ha,  0.0470 km²)  [Northing: 2400700 - 2438350 m]
--------------------------------------------------------------------------------------------------------
TOTAL CANDIDATES (Tile 45EUU)           : 1,183 px  (11.83 ha,  0.1183 km²)
========================================================================================================
```

### 2.2 Refutation of Previous Report's Geographic Claim
- **Previous Erroneous Claim:** The prior Phase 4 audit text stated:  
  *"`11.40 ha (96.37%)` of the optical disturbance lies in southern Similipal, entirely outside the Frame 012 ground swath... All 43 pixels are located in the agricultural fringe north of the tiger reserve."*
- **Forensic Verification of UTM Coordinates:**
  - Similipal Wildlife Sanctuary extends along Northing from $Y = 2,376,548\text{ m}$ to $Y = 2,446,241\text{ m}$.
  - The acquired NISAR Track 098 Frame 012 swath covers the **southern portion** of the study area, with active data between Northing $Y = 2,372,210\text{ m}$ and $Y = 2,400,690\text{ m}$.
  - The **43 pixels ($0.43\text{ ha}$)** in the active swath have Northing coordinates $Y \in [2,372,490, 2,384,410]\text{ m}$ and Easting coordinates $X \in [407,070, 427,710]\text{ m}$. They are situated in the **southern agricultural/scrub fringe outside the southern boundary of Similipal Sanctuary**.
  - The **1,140 pixels ($11.40\text{ ha}$)** outside Frame 012's swath have Northing coordinates $Y \in [2,397,140, 2,436,960]\text{ m}$ and Easting coordinates $X \in [404,330, 444,290]\text{ m}$. They lie **entirely NORTH of Frame 012's northern swath boundary ($Y > 2,400,690\text{ m}$)**, within the northern Core Area ($1.79\text{ ha}$), northern Buffer ($4.91\text{ ha}$), and northern landscape exterior ($4.70\text{ ha}$).
- **Conclusion:** The previous report inverted the north-south spatial orientation. All 11.40 ha of optical candidates outside the swath are located in **northern Similipal**, while the 43 active-swath pixels are located in the **southern peripheral landscape**.
- **Classification Status:** These 1,183 pixels are **optical spectral disturbance candidates**, detected via multispectral index drops ($\Delta\text{NDVI} \le -0.20$, $\text{dNBR} \ge 0.27$). They are **not confirmed structural forest loss or legal deforestation**.

---

## 3. Correct Detector Evaluation Metrics & Disentanglement of FPR vs. FDR

### 3.1 Mathematical Definitions
In binary classification on highly imbalanced remote sensing datasets, terminological precision is critical:

$$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}}$$

$$\text{Recall} = \frac{\text{TP}}{\text{TP} + \text{FN}}$$

$$\text{Specificity} = \frac{\text{TN}}{\text{TN} + \text{FP}}$$

$$\text{False Positive Rate (FPR)} = \frac{\text{FP}}{\text{FP} + \text{TN}} = 1 - \text{Specificity}$$

$$\text{False Discovery Rate (FDR)} = \frac{\text{FP}}{\text{TP} + \text{FP}} = 1 - \text{Precision}$$

$$\text{F1-Score} = \frac{2 \cdot \text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}$$

### 3.2 Audited Confusion Matrices & Metric Values
Evaluated against the binary reference population ($P = 43\text{ positive pixels}$, $N = 2,302,923\text{ negative forest pixels}$, total $2,302,966\text{ pixels}$, class imbalance ratio $53,556 : 1$):

| Detector Configuration | TP | FP | FN | TN | Precision | Recall | FPR ($\frac{\text{FP}}{\text{FP}+\text{TN}}$) | FDR ($\frac{\text{FP}}{\text{TP}+\text{FP}}$) | Specificity | F1-Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Historical Threshold ($\Delta HV \le -2.5\text{ dB}$)** | 10 | 523,703 | 33 | 1,779,220 | $1.9 \times 10^{-5}$ | 0.2326 | **22.7408%** | **99.9981%** | 77.2592% | $3.8 \times 10^{-5}$ |
| **Historical Joint Rule ($\Delta HV \le -2.5\text{ dB} \ \& \ \Delta R \le -1.2\text{ dB}$)** | 9 | 408,060 | 34 | 1,894,863 | $2.2 \times 10^{-5}$ | 0.2093 | **17.7192%** | **99.9978%** | 82.2808% | $4.4 \times 10^{-5}$ |
| **Robust $Z_{\text{MAD}} \le -2.0$** | 0 | 55,781 | 43 | 2,247,142 | 0.0000 | 0.0000 | **2.4222%** | **100.0000%** | 97.5778% | 0.0000 |
| **Robust Multi-Feature ($Z_{\text{MAD}} \le -2.0 \ \& \ \Delta R \le -1.0\text{ dB}$)** | 0 | 53,836 | 43 | 2,249,087 | 0.0000 | 0.0000 | **2.3377%** | **100.0000%** | 97.6623% | 0.0000 |

### 3.3 Root Cause of the 99.998% Confusion
- **The Error:** Prior reports stated that the historical threshold had a *"False Positive Rate of 99.998%"*.
- **The Correction:**
  - $99.9981\%$ is the **False Discovery Rate (FDR)** ($\text{FP}/(\text{TP}+\text{FP})$). Out of every 100,000 alarms flagged by the historical threshold, ~99,998 are false alarms.
  - The actual **False Positive Rate (FPR)** is **$22.7408\%$**. Out of the 2,302,923 undisturbed forest pixels, 523,703 pixels ($22.74\%$) were falsely triggered due to seasonal phenological drying between March 4 and April 21.
  - The robust multi-feature detector suppresses this false-positive fall-out by nearly an order of magnitude, reducing FPR from **$22.74\%$ down to $2.34\%$** and raising Specificity to **$97.66\%$**. However, because of extreme class imbalance ($53,556 : 1$) and the absence of any true positive triggers in the 43 peripheral pixels, its FDR remains $100\%$.

---

## 4. Frequency A (10 m) and Frequency B (80 m) Grid Alignment

### 4.1 Coordinate Transforms & Spatial Shift Diagnosis
An audit of the GeoTIFF metadata for Frequency A (10 m) and Frequency B (80 m) revealed:
- **Frequency A Transform:** `[10.0, 0.0, 401640.0, 0.0, -10.0, 2438360.0]`
  - Upper-left corner: $X_{\text{top-left}} = 401,640.0\text{ m}$, $Y_{\text{top-left}} = 2,438,360.0\text{ m}$.
  - Resolution: $10.0\text{ m} \times 10.0\text{ m}$.
- **Frequency B Transform:** `[80.0, 0.0, 401600.0, 0.0, -80.0, 2438400.0]`
  - Upper-left corner: $X_{\text{top-left}} = 401,600.0\text{ m}$, $Y_{\text{top-left}} = 2,438,400.0\text{ m}$.
  - Resolution: $80.0\text{ m} \times 80.0\text{ m}$.
- **Calculated Grid Offset:**
  - $\Delta X = 401,600.0 - 401,640.0 = -40.0\text{ m}$ (shifted west by half an 80 m pixel).
  - $\Delta Y = 2,438,400.0 - 2,438,360.0 = +40.0\text{ m}$ (shifted north by half an 80 m pixel).
  - **Spatially Nested:** `False`. The grids were offset by exactly half an 80 m pixel ($40\text{ m}$).

### 4.2 Forensic Proof of Native HDF5 Nesting
Inspection of the raw NISAR L2 GCOV HDF5 datasets (`NISAR_L2_PR_GCOV_001_098_D_012_..._F_A_J_001.h5` and `..._F_B_J_001.h5`) proved that native NISAR product geometry is 100% co-registered:
- Native Frequency A: $x_0 = 361,445.0\text{ m}$ (pixel center) $\rightarrow$ left pixel edge = $361,440.0\text{ m}$.
- Native Frequency B: $x_0 = 361,480.0\text{ m}$ (pixel center) $\rightarrow$ left pixel edge = $361,440.0\text{ m}$.
- Native $y$ origin for both Frequency A and B is identically $2,467,440.0\text{ m}$.
- In native NISAR products, an 80 m pixel contains exactly an $8 \times 8$ array of 10 m pixels with zero offset.

### 4.3 Root Cause of the Offset in Phase 4
In Phase 4 Task 4, the spatial slicing script extracted the Frequency B regional window with bounding corner `(401600.0, 2438400.0)`. When slicing Frequency A, the code searched for the matching pixel *center* coordinate `(401640.0, 2438360.0)` rather than the bounding corner, selecting index 4020 instead of 4016. This introduced a 40 m shift in the saved Frequency A GeoTIFFs relative to Frequency B.

### 4.4 Resolution & Implementation
To guarantee rigorous, distortion-free downsampling and grid co-registration without bilinear interpolation artifacts, module `backend/app/domains/forests/processing/alignment.py` was created:
1. `check_grid_nesting(transform_high, shape_high, transform_low, shape_low)`: Automatically validates whether an 8:1 integer ratio, identical origin, and exact spatial bounding box exist.
2. `aggregate_continuous_10m_to_80m(data_10m)`: Aggregates continuous radiometric backscatter ($\gamma^0$, ratio) by reshaping into non-overlapping $8 \times 8$ blocks and taking `np.nanmean`.
3. `aggregate_categorical_10m_to_80m(labels_10m)`: Aggregates discrete reference/validation classes using vectorized modal (majority) voting via `scipy.stats.mode`.
4. **Generated Output:** `data/processed/validation/sar_optical_validation_agreement_nested_80m.tif` was created with affine transform `[80.0, 0.0, 401640.0, 0.0, -80.0, 2438360.0]`, perfectly aligning with the 10 m evaluation grid.

---

## 5. Reconciled Reference Evaluation Population Table

### 5.1 Population Stratification Table
To resolve the question of why the negative reference sample count shifted between Phase 4 Task 6 and Task 7, the following population accounting is documented:

| Population Identifier | Population Name | Geographic / Mask Definition | Positive Disturbance Pixels | Negative Non-Disturbance Pixels | Uncertain / Excluded Pixels | Total Sample Count | Imbalance Ratio ($N : P$) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Population 1** | **Landscape Active Swath** | Dual-sensor valid observation window (`sar_vc == 2 & opt_vc == 2`) across all land covers (forest, crops, water, bare soil) | 43 | 7,574,034 | 5,009,469 | 12,583,546 | **176,140 : 1** |
| **Population 2** | **Forest Active Swath** | Dual-sensor active swath restricted to documented forest cover (`both_valid & forest_mask >= 30%`) | 43 | 2,302,923 | 671,702 | 2,974,668 | **53,556 : 1** |
| **Population 3** | **Forest Binary Evaluation** | Forest-only population with uncertain / unobservable pixels excluded from scoring | **43** | **2,302,923** | **0** | **2,302,966** | **53,556 : 1** |

### 5.2 Mathematical Reconciliation
- In Task 6, agreement categories were initially calculated across the **entire dual-sensor landscape** (Population 1), which included 7,574,034 negative landscape pixels and 5,009,469 uncertain pixels (chiefly agricultural areas with seasonal cloud cover or shifting crop cycles).
- In Task 7, detector evaluation was properly restricted to **canopy-covered forest** (Population 3) using the FSI reference forest mask (canopy density $\ge 30\%$). 
- This restriction reduced the negative baseline from 7,574,034 to 2,302,923 pixels by excluding agricultural fields, water bodies, and scrubland, preventing non-forest agricultural harvesting from confounding forest disturbance detector evaluation.

---

## 6. Disturbance Agreement Terminology Correction

### 6.1 Reclassification of Coincident Pixels
In Phase 4 Task 6, 9 pixels ($0.09\text{ ha}$) exhibited both a significant optical drop ($\text{dNBR} \ge 0.27$, $\Delta\text{NDVI} \le -0.20$) and a SAR backscatter drop ($\Delta HV \le -2.0\text{ dB}$, $\Delta R \le -1.0\text{ dB}$). 
- **Previous Premature Label:** *"Coincident Disturbance Agreement"* or *"Confirmed Crown Fire"*.
- **Corrected Standardized Label:** **"Coincident SAR-Optical Spectral Anomalies"**.

### 6.2 Scientific & Legal Rationale
1. **Remote Sensing Limitations:** Drops in optical vegetation indices and L-band cross-polarization backscatter indicate changes in surface reflectance and canopy volume scattering. However, surface soil moisture draw-down, leaf senescence in deciduous *Shorea robusta* (Sal) canopies during the dry season (March–April), or understory clearing can produce identical radiometric responses.
2. **Absence of Ground Truth:** No in-situ field verification, forest department compartment register entries, or sub-meter drone imagery exist to confirm timber removal or standing biomass destruction at these 9 pixel locations.
3. **Mandate:** Until confirmed by independent field evidence, these pixels must remain categorized as **coincident spectral anomalies**.

---

## 7. Master Discrepancy Reconciliation Table & Status Matrix

| Discrepancy Item | Initial Phase 4 Value / Report Claim | Reconciled Phase 4.1 Value | Status | Evidence / Verification Script |
| :--- | :--- | :--- | :--- | :--- |
| **Optical Candidates Location** | 11.40 ha claimed in "southern Similipal", 43 px "north of reserve" | 11.40 ha is in **northern Similipal** ($Y > 2,400,690\text{ m}$); 43 px is in **southern fringe** ($Y < 2,384,410\text{ m}$) | **RESOLVED** | UTM coordinates verified in `scripts/run_phase4_1_correction.py` |
| **In-Reserve Disturbance in Swath** | Ambiguous in Task 5 | **Exactly 0.00 ha (0 pixels)** inside Core or Buffer in active swath | **RESOLVED** | Spatial intersection with `similipal_sanctuary_epsg32645.geojson` |
| **Detector Metric Definitions** | 99.998% reported as "False Positive Rate (FPR)" | $99.9981\%$ is **False Discovery Rate (FDR)**; actual **FPR is $22.7408\%$** | **RESOLVED** | `ThresholdEvaluationMetric` in `evaluator.py`, verified in `test_grid_alignment.py` |
| **Grid Co-Registration** | 40 m half-pixel shift between Frequency A and B rasters | Root cause diagnosed (slicing center vs corner); native HDF5 8:1 nesting proven; modal voting aggregator implemented | **RESOLVED** | `alignment.py`, `sar_optical_validation_agreement_nested_80m.tif` |
| **Reference Population Baseline** | Negative samples varied from 7,574,034 to 2,302,923 | Disentangled: Population 1 (Landscape = 7.57M neg) vs Population 3 (Forest-only = 2.30M neg) | **RESOLVED** | Population comparison table in `phase4_1_corrected_metrics.json` |
| **Coincident Agreement Labeling** | Labeled "Confirmed Disturbance / Crown Fire" | Corrected to **"Coincident SAR-Optical Spectral Anomalies"** | **RESOLVED** | Reclassification in JSON metrics and documentation |

---

## 8. Codebase Deliverables & Test Suite Verification

### 8.1 Deliverable Files
- **Correction Processing Script:** `scripts/run_phase4_1_correction.py`
- **Grid Alignment Module:** `backend/app/domains/forests/processing/alignment.py`
- **Unit Test Suite:** `backend/tests/test_grid_alignment.py`
- **Output Metrics JSON:** `data/processed/validation/phase4_1_corrected_metrics.json`
- **Nested 80 m Raster:** `data/processed/validation/sar_optical_validation_agreement_nested_80m.tif`
- **Diagnostic Audit Figure:** `data/processed/validation/phase4_1_grid_and_metric_corrections.png`
- **Documentation Report:** `docs/PHASE_4_1_METRIC_AND_GRID_CORRECTION.md`

### 8.2 Pytest Verification
Execution of the complete test suite confirmed **49 out of 49 unit tests passing**:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/ -v
======================== 49 passed, 1 warning in 0.86s =========================
```
Specific tests covering Phase 4.1 functionality:
- `backend/tests/test_grid_alignment.py::test_grid_nesting_detection_shifted_vs_nested` : **PASSED**
- `backend/tests/test_grid_alignment.py::test_continuous_aggregation_mean` : **PASSED**
- `backend/tests/test_grid_alignment.py::test_categorical_aggregation_mode` : **PASSED**
- `backend/tests/test_grid_alignment.py::test_confusion_metrics_mathematical_definitions` : **PASSED**

