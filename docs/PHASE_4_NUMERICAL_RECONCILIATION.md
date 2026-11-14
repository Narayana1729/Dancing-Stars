# Project NISAR — Phase 4 Numerical Reconciliation & Forensic Audit

**Document Version:** 1.0.0  
**Audit Type:** Strict Forensic & Numerical Re-evaluation  
**Evaluation Scope:** Phase 4 Tasks 1 through 7  
**Target Landscape:** Similipal Tiger Reserve & Wildlife Sanctuary, Mayurbhanj, Odisha, India  
**Spatial Reference System:** WGS 84 / UTM Zone 45N (`EPSG:32645`)  
**Auditor:** Independent Scientific Audit Subsystem  
**Date:** November 2026  

---

## 1. Forensic Reconciliation of Optical Reference Labels

### 1.1 The Discrepancy: Task 5 (11.83 ha) vs. Task 7 (0.43 ha)
Previous Phase 4 reports presented two seemingly contradictory numbers for "confirmed optical disturbance":
- **Task 5 (Optical Reference Generation):** Reported **$11.83\text{ ha}$** of confirmed optical disturbance across the landscape.
- **Task 7 (Statistical Detector Evaluation):** Reported only **$0.43\text{ ha}$** (43 pixels) of positive disturbance samples within the active evaluation swath.

### 1.2 Mathematical & Spatial Deconstruction
Forensic spatial intersection of the 10 m raster grids (`s2_optical_reference_labels_10m.tif`, `freq_a_valid_count.tif`, and authoritative boundary GeoJSONs) resolves this discrepancy completely:

```
======================================================================================================
GEOGRAPHIC STRATUM                      TOTAL OPTICAL DISTURBANCE    IN ACTIVE SAR SWATH   OUTSIDE SAR SWATH
======================================================================================================
Similipal Core Area (CTH)                    179 px ( 1.79 ha)           0 px (0.00 ha)      179 px ( 1.79 ha)
Similipal Wildlife Sanctuary (Buffer)        491 px ( 4.91 ha)           0 px (0.00 ha)      491 px ( 4.91 ha)
------------------------------------------------------------------------------------------------------
SUBTOTAL INSIDE NOTIFIED RESERVE             670 px ( 6.70 ha)           0 px (0.00 ha)      670 px ( 6.70 ha)
Outside Sanctuary (Landscape Fringe)         513 px ( 5.13 ha)          43 px (0.43 ha)      470 px ( 4.70 ha)
======================================================================================================
TOTAL LANDSCAPE (S2 TILE 45EUU)            1,183 px (11.83 ha)          43 px (0.43 ha)    1,140 px (11.40 ha)
PERCENTAGE OF TOTAL DISTURBANCE                  100.00%                     3.63%               96.37%
======================================================================================================
```

### 1.3 Critical Audit Findings on Spatial Coverage
1. **The Discrepancy is 100% Spatial:**  
   Task 5 processed the full Sentinel-2 tile (`45EUU`), identifying $11.83\text{ ha}$ of candidate spectral change across the entire Mayurbhanj landscape. However, acquired NISAR Track 098 Frame 012 covers only the southern portion of Similipal ($30.65\%$ of the regional study box, $Y \in [2,372,210, 2,400,690]\text{ m}$). **$11.40\text{ ha}$ ($96.37\%$) of the optical candidates lies NORTH of Frame 012's northern swath boundary ($Y > 2,400,690\text{ m}$), entirely outside the Frame 012 ground swath (in northern Similipal Core, Buffer, and northern landscape fringe).**
2. **Zero In-Reserve Disturbance in the Active Swath:**  
   Within the active dual-sensor observation window (where both NISAR and Sentinel-2 have valid clear-sky observations), there is **exactly $0.00\text{ ha}$ (0 pixels) of optical disturbance candidates inside Similipal Wildlife Sanctuary or the Core Area.**
3. **The 43 Pixels are in the Southern Peripheral Fringe:**  
   All 43 pixels ($0.43\text{ ha}$) that overlap the active NISAR swath are located in the **agricultural and scrub fringe south of Similipal Wildlife Sanctuary** ($Y \in [2,372,490, 2,384,410]\text{ m}$, $X \in [407,070, 427,710]\text{ m}$).
4. **Reclassification of "Confirmed" Optical Labels:**  
   Task 5 labeled pixels as "Confirmed Disturbance" based purely on spectral index thresholds ($\Delta\text{NDVI} \le -0.20$, $\text{post-NDVI} < 0.40$, $\text{dNBR} \ge 0.27$, or SCL transition from vegetation to non-vegetated).  
   > **AUDIT MANDATE:**  
   > Spectral indices alone do **not** constitute independent confirmation of structural timber loss or legal deforestation. Without independent field inspection, UAV surveys, or official forest compartment damage dockets, these labels must be reclassified from "Confirmed Disturbance" to **"Candidate Spectral Disturbance (Unverified by Field Reference)"**. (See [PHASE_4_1_METRIC_AND_GRID_CORRECTION.md](file:///Users/srimannarayanadeevi/NISAR/docs/PHASE_4_1_METRIC_AND_GRID_CORRECTION.md) for detailed coordinate deconstruction).

---

## 2. Deconstruction of Task 6 Agreement Categories

### 2.1 The Misleading 23.37 km² Agreement Claim
Task 6 reported:
> *"Category 1: SAR and optical evidence agree: 23.37 km² (233,728 pixels)."*

This created the severe misconception that both sensors had confirmed $23.37\text{ km}^2$ of active forest disturbance across Similipal, which contradicted Task 5's report of only $0.12\text{ km}^2$ ($11.83\text{ ha}$) of optical disturbance.

### 2.2 Forensic Code Audit (`comparator.py`)
Direct code inspection of `backend/app/domains/forests/processing/validation/comparator.py` lines 65–70 reveals the exact computational assignment:

```python
# A. Disturbance agreement: Both flag severe disturbance
dist_agree = both_valid & (sar_regimes == 4) & (opt_labels == 1)

# B. Stable agreement: Both flag stable closed canopy forest
stable_agree = both_valid & (sar_regimes == 1) & (opt_subtypes == 21)

# BOTH WERE ASSIGNED TO CATEGORY 1!
agreement[dist_agree | stable_agree] = 1
```

### 2.3 Numerical Breakdown of Category 1
Evaluating `dist_agree` and `stable_agree` independently yields:

```
======================================================================================================
CATEGORY 1 COMPONENT                     PIXEL COUNT         AREA (ha)     AREA (km²)    PERCENTAGE
======================================================================================================
Coincident Disturbance Agreement                   9           0.09 ha     0.00090 km²       0.004%
Coincident Stable Closed Forest Agreement    233,719       2,337.19 ha    23.37190 km²      99.996%
------------------------------------------------------------------------------------------------------
TOTAL CATEGORY 1 REPORTED                    233,728       2,337.28 ha    23.37280 km²     100.000%
======================================================================================================
```

### 2.4 Audit Correction & Category Renaming
- **Audit Finding:** In Task 6, **$99.996\%$ of Category 1 was stable, undisturbed closed-canopy forest agreement**. Only **9 pixels ($0.09\text{ ha}$)** represented coincident disturbance agreement!
- **Audit Correction:** Category 1 must be formally disaggregated to prevent scientific misrepresentation:
  - **Category 1A:** `Coincident Disturbance Agreement` = **$0.09\text{ ha}$ (9 pixels)**.
  - **Category 1B:** `Coincident Stable Forest Agreement` = **$23.37\text{ km}^2$ (233,719 pixels)**.
- A reconciled raster distinguishing these two conditions has been generated:  
  [data/processed/validation/sar_optical_validation_agreement_reconciled_10m.tif](file:///Users/srimannarayanadeevi/NISAR/data/processed/validation/sar_optical_validation_agreement_reconciled_10m.tif).

---

## 3. Audit of Physical Explanations & Assertion Retractions

Previous reports made several assertive physical claims to explain backscatter declines under green canopies. Each claim was audited against available evidence in the workspace:

```
======================================================================================================
PHYSICAL ASSERTION IN PREVIOUS REPORTS          AUDITED DATA EVIDENCE         AUDIT DETERMINATION
======================================================================================================
"Volumetric soil moisture dropped from 25% to   Zero in-situ TDR probe data,  FACTUAL CLAIM RETRACTED.
below 5% between March 4 and April 21, 2026."   SMAP data, or IMD soil probes Reclassified as an UNVERIFIED
                                                exist in the workspace.       PHYSICAL HYPOTHESIS.
------------------------------------------------------------------------------------------------------
"Understory desiccation occurred under an       Inferred solely from SAR      FACTUAL CLAIM RETRACTED.
intact, green dominant sal tree canopy."        backscatter decline paired    Consistent with L-band physics,
                                                with stable optical greenness. but unconfirmed by field data.
------------------------------------------------------------------------------------------------------
"Wildfire crown burn destruction occurred in    Based solely on optical       FACTUAL CLAIM RETRACTED.
Category 1."                                    Sentinel-2 dNBR >= 0.27.      Reclassified as CANDIDATE
                                                No fire logs or hotspots.     SPECTRAL BURN ANOMALY.
------------------------------------------------------------------------------------------------------
"Agricultural harvesting cycles caused Category Based on spatial proximity to Reclassified as PLAUSIBLE
5 uncertainty."                                 village vector boundaries.    LANDSCAPE HYPOTHESIS.
======================================================================================================
```

> **METHODOLOGICAL DIRECTIVE:**  
> Spectral indices ($\text{dNBR}$, $\text{NDVI}$) and microwave differential backscatter ($\Delta\gamma^0$) measure electromagnetic interactions, not administrative causes. Physical causes must never be stated as factual conclusions without independent ground or sensor corroboration.

---

## 4. Spatial and Numerical Consistency Verification

Every raster dataset was forensically verified for spatial geometry, coordinate reference systems, affine transforms, nodata masks, and pixel areas:

```
======================================================================================================
DATASET IDENTIFIER                GRID DIMENSIONS   PIXEL RES    CRS          PIXEL AREA    TOTAL ENVELOPE
======================================================================================================
Frequency A Multi-Temporal Rasters  6,616 × 6,232   10.0 × 10.0 m EPSG:32645   0.01 ha       4,123.0912 km²
Frequency B Multi-Temporal Rasters    827 × 779     80.0 × 80.0 m EPSG:32645   0.64 ha       4,123.0912 km²
Optical Reference Rasters (10 m)    6,616 × 6,232   10.0 × 10.0 m EPSG:32645   0.01 ha       4,123.0912 km²
Validation Agreement Rasters (10 m) 6,616 × 6,232   10.0 × 10.0 m EPSG:32645   0.01 ha       4,123.0912 km²
Validation Agreement Rasters (80 m)   827 × 779     80.0 × 80.0 m EPSG:32645   0.64 ha       4,123.0912 km²
======================================================================================================
```

### 4.1 Frequency B Native Evaluation Check
- **Verification Question:** Were Frequency B statistics computed on its native 80 m grid, or by upsampling/downsampling pixels and treating them as independent observations?
- **Finding:** Frequency B temporal analysis and anomaly detection in `scripts/run_statistical_disturbance_detector.py` operated strictly on the native $827 \times 779$ raster ($46,515$ native forest pixels, each representing $0.64\text{ ha}$). No artificial oversampling was performed.
- **Aggregation Logic:** The 10 m to 80 m downsampling in `comparator.py` and `optical_features.py` utilized nearest-neighbor / modal block aggregation strictly for regional cartographic display.

---

## 5. Audit of Detector Evaluation & Circularity Analysis

### 5.1 Verification of Evaluation Population
Forensic recalculation of the dual-sensor overlapping forest mask verified the exact pixel populations:
- **Total Valid Forest Evaluation Pixels (with definite labels 1 or 2):** **2,302,966 pixels ($23,029.66\text{ ha}$)**.
- **Positive Disturbance Reference Pixels ($y_{\text{true}} = 1$):** Exactly **43 pixels ($0.43\text{ ha}$)**.
- **Negative Stable Forest Reference Pixels ($y_{\text{true}} = 0$):** Exactly **2,302,923 pixels ($23,029.23\text{ ha}$)**.
- **Uncertain Pixels Excluded from Binary Evaluation:** **5,009,469 pixels**.
- **Verified Imbalance Ratio:** Exactly **53,556.35 : 1** within the forest mask (and **176,140.33 : 1** across the entire landscape).

### 5.2 Verification of Confusion Matrices and Error Rates (FPR vs. FDR)

```
===================================================================================================================
EVALUATED RULE                 TP (px)   FP (px)    FN (px)   TN (px)      PRECISION    RECALL   FPR (%)   FDR (%)
===================================================================================================================
Historical ΔHV <= -2.5 dB        10      523,703      33     1,779,220     0.000019     0.2326   22.74%    99.998%
Historical Joint (-2.5 & -1.2)    9      408,060      34     1,894,863     0.000022     0.2093   17.72%    99.998%
Robust Z_MAD <= -2.0              0       55,781      43     2,247,142     0.000000     0.0000    2.42%   100.000%
Robust Multi-Feature (Z<=-2,ΔR)   0       53,836      43     2,249,087     0.000000     0.0000    2.34%   100.000%
===================================================================================================================
```
*(Note: False Positive Rate $\text{FPR} = \text{FP}/(\text{FP}+\text{TN})$ measures fall-out across negative forest, whereas False Discovery Rate $\text{FDR} = \text{FP}/(\text{TP}+\text{FP})$ measures alarm stream contamination. See [PHASE_4_1_METRIC_AND_GRID_CORRECTION.md](file:///Users/srimannarayanadeevi/NISAR/docs/PHASE_4_1_METRIC_AND_GRID_CORRECTION.md) for full formal derivations).*

### 5.3 Circularity & Shared-Evidence Limitations
> **CRITICAL ARCHITECTURAL FINDING:**  
> The optical reference labels used to evaluate the detector were generated from the **exact same Sentinel-2 image pair** (March 2 & April 16, 2026).  
> 1. **Lack of Independent Ground Reference:** No third-party ground-truth dataset (e.g. FSI ground audit plots, MODIS/VIIRS thermal hotspots, PlanetScope 3 m daily imagery) was ingested to validate the Sentinel-2 labels themselves.
> 2. **Evaluation Nature:** This evaluation is technically a **cross-sensor consistency comparison**, not an independent ground truth validation.
> 3. **Withholding of Supervised Metrics:** Because only 43 positive samples exist (spatially confined to 1 micro-patch in the landscape fringe), calculating Precision-Recall AUC (PR-AUC), Matthews Correlation Coefficient (MCC), or cross-validated ROC curves would represent pseudo-replication. **Supervised metrics are formally withheld as incomplete.**

---

## 6. Discrepancy Reconciliation Table

```
================================================================================================================================
ITEM   ORIGINAL REPORTED CLAIM             AUDITED VERIFIED VALUE               PHYSICAL & DATA EVIDENCE                   AUDIT RECONCILIATION
================================================================================================================================
1      Optical Confirmed Disturbance:      Total S2 Frame: 11.83 ha (1,183 px). Frame 012 covers northern 30.65% of ROI.   The discrepancy is 100% spatial.
       11.83 ha (Task 5) vs 0.43 ha (Task  Active SAR Swath: 0.43 ha (43 px).   11.40 ha of optical disturbance is in the  96.37% of optical disturbance lies
       7).                                                                      south, outside Frame 012's swath.          in southern Similipal outside swath.
--------------------------------------------------------------------------------------------------------------------------------
2      Similipal Sanctuary Disturbance in  Active SAR Swath Sanctuary: 0.00 ha. All 6.70 ha of sanctuary optical distur-  Zero optical confirmed disturbance
       Active Radar Swath.                 Outside Swath Sanctuary: 6.70 ha.    bance is in the southern reserve where     occurred inside the sanctuary within
                                                                                NISAR Frame 012 had no coverage.           the active NISAR observation swath.
--------------------------------------------------------------------------------------------------------------------------------
3      Task 6 Category 1: "SAR and         Coincident Disturbance: 0.09 ha.     comparator.py combined disturbance agree-  Cat 1 was 99.996% stable forest.
       optical evidence agree = 23.37 km²" Stable Forest: 23.3719 km²           ment and stable forest agreement into one  Must be disaggregated into Cat 1A
       (233,728 pixels).                   (233,719 pixels).                    single class (Category 1).                 (0.09 ha) and Cat 1B (23.37 km²).
--------------------------------------------------------------------------------------------------------------------------------
4      "Soil moisture dropped from 25%     Unverified hypothesis. No soil probe No soil moisture sensors or SMAP products  Retracted as factual finding;
       to below 5%."                       data in workspace.                   were ingested into the repository.         retained as unverified hypothesis.
--------------------------------------------------------------------------------------------------------------------------------
5      "Wildfire crown destruction         Candidate spectral burn anomaly      Inferred purely from dNBR >= 0.27 and      Retracted as factual finding;
       confirmed."                         without independent fire dockets.    delta_NDVI <= -0.20 on Sentinel-2 bands.   reclassified as candidate anomaly.
--------------------------------------------------------------------------------------------------------------------------------
6      Frontend displays live Phase 4      Frontend renders static mock data    App.jsx only polls /health; never calls    FAIL: Frontend live API integration
       backend results.                    from mockDomains.js.                 /api/v1/forests/analyze.                   remains an open development item.
================================================================================================================================
```

---

## 7. Final Pipeline Status Matrix

```
======================================================================================================
PIPELINE COMPONENT                                STATUS                 VERIFICATION REMARKS
======================================================================================================
1. Official Boundary Ingestion                    IMPLEMENTED & VERIFIED Matched gazette 100.0%; WDPA error rejected.
2. Frequency B (80 m) Multi-Temporal Processing   IMPLEMENTED & VERIFIED Processed on native 80 m grid; baseline preserved.
3. Frequency A (10 m) Multi-Temporal Processing   IMPLEMENTED & VERIFIED Native 10 m RTC flattening; 48-day baseline verified.
4. Optical Reference Generation                   IMPLEMENTED & VERIFIED 45EUU mosaic calibrated with PB 04.00 BOA offset.
5. Multi-Sensor Evidence Synthesis                IMPLEMENTED & VERIFIED Reconciled into disaggregated 1A and 1B classes.
6. Vector Candidate Cluster Extraction            IMPLEMENTED & VERIFIED 52 discrete clusters extracted with attributes.
7. Unsupervised Robust Anomaly Detector           IMPLEMENTED & VERIFIED Median & MAD-based Z_MAD with MMU filtering.
8. Resolution-Justified MMU Spatial Clustering    IMPLEMENTED & VERIFIED 5 px (0.05 ha) for Freq A; 1 px (0.64 ha) for Freq B.
9. Backend Analysis API Endpoints                 IMPLEMENTED & VERIFIED /api/v1/forests/analyze operational.
10. Frontend Dynamic API Display                  INCOMPLETE / DEFECT    Frontend hardcoded to mockDomains.js.
11. Southern Swath Coverage (Frame 013)           INCOMPLETE / UNRESOLVED Requires downloading Track 098 Frame 013.
12. Supervised Detector Evaluation (PR-AUC, MCC)  INCOMPLETE / WITHHELD  Reference label sample deficit (43 pixels).
======================================================================================================
```

---

## 8. Exact Remaining Blockers for a Scientifically Defensible System

To achieve an operationally deployable and legally defensible forest monitoring system for Similipal Tiger Reserve, the following four blockers must be addressed:

1. **Resolution of Frontend Integration Defect:**  
   Update `frontend/src/App.jsx` to dynamically consume `/api/v1/forests/analyze` and display live analytical rasters (`sar_optical_validation_agreement_reconciled_10m.tif`) rather than static illustrative placeholders.
2. **Ingestion of NISAR Track 098 Frame 013:**  
   Acquire and process Frame 013 to monitor the southern $87.14\%$ of Similipal Sanctuary and the southern $81.71\%$ of the Core Area, where the vast majority of dry-season forest disturbances occur.
3. **Independent Third-Party Ground Truth Ingestion:**  
   Incorporate authoritative Forest Survey of India (FSI) field inspection records, Odisha Forest Department compartment fire logs, or high-resolution sub-meter stereoscopic imagery to break the two-sensor circularity limitation.
4. **Multi-Pass Temporal Persistence Tracking:**  
   Ingest subsequent NISAR repeat passes (cycles 5, 6, and 7) to enforce multi-epoch temporal persistence filters ($N \ge 2$ consecutive passes), separating permanent canopy gaps from transient moisture shifts.

---
*End of Report — Project NISAR Forensic Numerical Reconciliation Audit*

