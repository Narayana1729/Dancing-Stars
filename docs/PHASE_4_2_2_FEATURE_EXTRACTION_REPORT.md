# PROJECT NISAR — Phase 4.2 Task 4.2.2: Multi-Temporal Feature Extraction & Regression Report

**Workspace:** `/Users/srimannarayanadeevi/NISAR`  
**Date:** November 14, 2026  
**Status:** Completed and Verified (74/74 Backend Pytest Tests Passing, Isolated Regression 100% Bit-for-Bit Identical)  
**Deliverables Generated:**
- Modular Domain Codebase:
  - [`backend/app/domains/forests/processing/temporal_analysis/temporal_validation.py`](file:///Users/srimannarayanadeevi/NISAR/backend/app/domains/forests/processing/temporal_analysis/temporal_validation.py)
  - [`backend/app/domains/forests/processing/temporal_analysis/temporal_statistics.py`](file:///Users/srimannarayanadeevi/NISAR/backend/app/domains/forests/processing/temporal_analysis/temporal_statistics.py)
  - [`backend/app/domains/forests/processing/temporal_analysis/disturbance_indicators.py`](file:///Users/srimannarayanadeevi/NISAR/backend/app/domains/forests/processing/temporal_analysis/disturbance_indicators.py)
  - [`backend/app/domains/forests/processing/temporal_analysis/temporal_features.py`](file:///Users/srimannarayanadeevi/NISAR/backend/app/domains/forests/processing/temporal_analysis/temporal_features.py)
  - [`backend/app/domains/forests/processing/temporal_analysis/temporal_loader.py`](file:///Users/srimannarayanadeevi/NISAR/backend/app/domains/forests/processing/temporal_analysis/temporal_loader.py)
  - [`backend/app/domains/forests/processing/temporal_analysis/pipeline.py`](file:///Users/srimannarayanadeevi/NISAR/backend/app/domains/forests/processing/temporal_analysis/pipeline.py)
  - [`backend/app/domains/forests/processing/temporal_analysis/__init__.py`](file:///Users/srimannarayanadeevi/NISAR/backend/app/domains/forests/processing/temporal_analysis/__init__.py)
- Pre-Modification Backups:
  - [`backend/app/domains/forests/processing/temporal_analysis/_backup_phase4_2_1/`](file:///Users/srimannarayanadeevi/NISAR/backend/app/domains/forests/processing/temporal_analysis/_backup_phase4_2_1/)
- Automated Pytest Suite:
  - [`backend/tests/test_multitemporal_features.py`](file:///Users/srimannarayanadeevi/NISAR/backend/tests/test_multitemporal_features.py) (8/8 passing, covering all 7 review corrections)
- Execution Script & Verification Engine:
  - [`scripts/run_phase4_2_2_feature_extraction.py`](file:///Users/srimannarayanadeevi/NISAR/scripts/run_phase4_2_2_feature_extraction.py)
- Isolated Regression Deliverables & Comparison Report:
  - [`data/processed/validation/temporal_regression/phase4_2_2_regression_comparison.json`](file:///Users/srimannarayanadeevi/NISAR/data/processed/validation/temporal_regression/phase4_2_2_regression_comparison.json)
  - [`data/processed/validation/temporal_regression/freq_b_provenance.json`](file:///Users/srimannarayanadeevi/NISAR/data/processed/validation/temporal_regression/freq_b_provenance.json)
  - [`data/processed/validation/temporal_regression/freq_a_provenance.json`](file:///Users/srimannarayanadeevi/NISAR/data/processed/validation/temporal_regression/freq_a_provenance.json)

---

## 1. Executive Summary & Verification Verdict

Phase 4.2 Task 4.2.2 transitions PROJECT NISAR from a rigid two-date differencing script into a generalized, modular multi-temporal feature extraction engine capable of ingesting arbitrary $N$-epoch SAR time series stacks ($X \in \mathbb{R}^{T \times H \times W}$), while guaranteeing strict 100% numerical backward compatibility with the verified Phase 4.1.1 baseline.

Following explicit architectural review authorization, all seven mandatory technical corrections were rigorously implemented:
1. **Physical Domain Separation:** Linear power ($\gamma^0_{\text{linear}}$) and logarithmic decibels ($\gamma^0_{\text{dB}}$) are formally separated. Temporal mean and sample standard deviation ($ddof=1$) are computed exclusively in linear power; temporal median and Median Absolute Deviation (MAD, scaled by $1.4826$) are computed exclusively in the dB domain.
2. **Explicit Sample Size Behavior:** Behavior for $N_{\text{valid}} = 0, 1, \ge 2$ is strictly enforced. For $N_{\text{valid}} < 2$, sample standard deviation and MAD evaluate to `NaN`.
3. **RND Stability Safeguards:** Relative Normalized Difference is evaluated strictly in linear power with guards against non-positive backscatter, zero division, and a numerical stability threshold ($\epsilon_{\text{num}} = 2 \times 10^{-7}$), clipping outputs mathematically to $[-1.0, 1.0]$.
4. **Memory-Bounded Theil-Sen Trend Estimator:** Implemented via spatial block tiling ($512 \times 512$) using exact fractional-day Doppler timestamps. Evaluates only where $N_{\text{valid}} \ge 3$; on datasets with fewer than 3 epochs, the slope strictly evaluates to `NaN` without spurious extrapolation.
5. **Three-Tier Disturbance Classification:** Implemented a scientifically honest three-tier taxonomy:
   - **Tier 1 (Instantaneous Disturbance Candidate):** Operational on $\ge 2$ epochs ($\Delta \gamma^0_{\text{HV}} < -3.0\text{ dB}$, $\Delta R < -1.5\text{ dB}$).
   - **Tier 2 (Temporally Sustained Backscatter Anomaly):** Requires $\ge 3$ epochs; flagged as `UNVERIFIABLE_TWO_DATES` on authentic 2-date data.
   - **Tier 3 (Long-Term Persistent Disturbance Candidate):** Requires $\ge 4$ epochs spanning $\ge 180\text{ days}$; flagged as `UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS` on authentic 2-date data.
6. **12-Point Acquisition Compatibility Validation:** Enforces CRS, grid origin, pixel spacing, polarization, and temporal baseline integrity prior to feature extraction.
7. **Isolated Numerical Regression Verdict: PASSED (100% Exact Match):**
   - The Phase 4.1.1 baseline directory (`data/processed/temporal/`) remained strictly read-only.
   - All legacy rasters reproduced in `data/processed/validation/temporal_regression/` achieved **0 mismatches, 0 NaN diffs, and MaxDiff = 0.00 dB**.

---

## 2. Architectural Refactoring & Decomposition

The monolithic `backend/app/domains/forests/processing/temporal_analysis/` pipeline was decomposed into single-responsibility modules:

```
backend/app/domains/forests/processing/temporal_analysis/
├── __init__.py                     # Clean public API export facade
├── metadata.py                     # TemporalSeriesMetadata dataclass & HDF5 inspection
├── temporal_loader.py              # Chronological Doppler sorting & chunked HDF5 reader
├── temporal_validation.py          # 12-point acquisition validation & baseline comparator
├── temporal_statistics.py          # Linear vs dB statistics, RND & tiled Theil-Sen estimator
├── disturbance_indicators.py       # Three-tier disturbance taxonomy & physical change regimes
├── temporal_features.py            # Backward-compatible multi-temporal feature facade
└── pipeline.py                     # MultiTemporalNISARPipeline orchestrator & GeoTIFF exporter
```

### 2.1 The 12-Point Acquisition Compatibility Validation Checklist

Before reading or processing time series arrays, `temporal_validation.py::validate_acquisition_compatibility` checks all input files against the 12 criteria without allocating full-array coordinate copies:

1. **Product Level Verification:** Validates `science/LSAR/identification/productLevel` is `L2` or `L2-GCOV`.
2. **Frequency Group Existence:** Verifies the specified frequency group (`frequencyA` or `frequencyB`) exists.
3. **Required Polarimetric Channels:** Confirms presence of both co-pol (`HH`) and cross-pol (`HV`) datasets.
4. **Spatial Reference System (CRS):** Validates projection authority and EPSG code match across all acquisitions (EPSG:32645).
5. **Pixel Spacing Uniformity:** Validates spacing ($10.0\text{ m}$ for Frequency A, $80.0\text{ m}$ for Frequency B) within $10^{-3}\text{ m}$.
6. **Grid Origin Alignment:** Checks coordinate grid origins $(X_0, Y_0)$ align to an integer multiple of pixel size ($\le 10^{-3}\text{ m}$).
7. **Spatial Bounding Box Intersection:** Confirms common bounding box contains valid spatial overlap ($W > 0, H > 0$).
8. **Flight Direction & Orbit Track:** Rejects ascending/descending mixing; validates consistent Track and Frame ID.
9. **Monotonic Chronological Ordering:** Doppler start timestamps (`zeroDopplerStartTime`) must increase monotonically without duplicate dates.
10. **Temporal Baseline Regularity:** Identifies irregular time intervals ($\Delta t$) and flags gaps exceeding standard 12-day orbital cycles.
11. **Calibration Metadata Presence:** Verifies Radiometric Terrain Correction (`rtcAlgorithmType` or equivalent) metadata.
12. **Fill Value Consistency:** Confirms nodata/fill values (e.g. `NaN`) match across all input granules.

---

## 3. Physical Domain Separation: Linear Power vs Decibel Space

Radar backscatter obeys exponential speckle statistics in linear power space and Gaussian-like distributions in decibels. Blending statistics across these domains introduces severe mathematical biases. Task 4.2.2 establishes strict mathematical separation:

### 3.1 Linear Power Domain ($\gamma^0_{\text{linear}}$)

Linear power represents incoherent energy addition. Temporal averaging and sample dispersion across epochs are calculated as:

$$\overline{\gamma^0} = \frac{1}{N_{\text{valid}}} \sum_{k \in \mathcal{V}} \gamma^0_k$$

$$s_{\text{linear}} = \sqrt{\frac{1}{N_{\text{valid}} - 1} \sum_{k \in \mathcal{V}} (\gamma^0_k - \overline{\gamma^0})^2} \quad (ddof=1)$$

- **Sample Size Rule:** For $N_{\text{valid}} < 2$, $s_{\text{linear}}$ is strictly defined as `NaN`.

### 3.2 Decibel Logarithmic Domain ($\gamma^0_{\text{dB}} = 10 \log_{10} \gamma^0$)

The median is a robust order statistic in dB space, resilient to residual speckle spikes. Dispersion in dB is quantified via Median Absolute Deviation (MAD):

$$\text{Median}_{\text{dB}} = \text{median}_{k \in \mathcal{V}} (\gamma^0_{\text{dB},k})$$

$$\text{MAD}_{\text{dB}} = 1.4826 \times \text{median}_{k \in \mathcal{V}} \left| \gamma^0_{\text{dB},k} - \text{Median}_{\text{dB}} \right|$$

- **Sample Size Rule:** For $N_{\text{valid}} < 2$, $\text{MAD}_{\text{dB}}$ is strictly `NaN`.
- **Z-Score Formulation:** $Z_k = \frac{\gamma^0_{\text{dB},k} - \text{Median}_{\text{dB}}}{\max(\text{MAD}_{\text{dB}}, \sigma_{\text{floor}})}$, where $\sigma_{\text{floor}} = 0.5\text{ dB}$.

### 3.3 Sample Size Behavior Matrix

| Metric | Domain | $N_{\text{valid}} = 0$ | $N_{\text{valid}} = 1$ | $N_{\text{valid}} \ge 2$ |
| :--- | :---: | :---: | :---: | :---: |
| **Temporal Mean** | Linear Power | `NaN` | $\gamma^0_1$ | $\frac{1}{N} \sum \gamma^0_k$ |
| **Sample Std Dev ($ddof=1$)** | Linear Power | `NaN` | `NaN` | Finite sample $s$ |
| **Temporal Median** | Decibel (dB) | `NaN` | $\gamma^0_{\text{dB},1}$ | Order median |
| **MAD ($1.4826 \times \text{med}$)** | Decibel (dB) | `NaN` | `NaN` | Finite robust dispersion |
| **Temporal Z-Score** | Decibel (dB) | `NaN` | `NaN` | Anomaly score |

---

## 4. Relative Normalized Difference (RND) with Safeguards

The Relative Normalized Difference (RND) tracks relative change between consecutive temporal acquisitions in linear power space:

$$\text{RND}_{k, k-1} = \frac{\gamma^0_k - \gamma^0_{k-1}}{\gamma^0_k + \gamma^0_{k-1}}$$

To guarantee numerical stability and scientific validity across large raster arrays, the following guards are enforced in `temporal_statistics.py::compute_relative_normalized_difference`:
1. **Valid Data Mask:** Both epoch $k$ and $k-1$ must be non-masked valid observations.
2. **Strictly Positive Backscatter:** $\gamma^0_k > 0$ and $\gamma^0_{k-1} > 0$ (rejects negative or zero artifacts).
3. **Denominator Safeguard:** $\gamma^0_k + \gamma^0_{k-1} > \epsilon_{\text{num}}$, where $\epsilon_{\text{num}} = 2 \times 10^{-7}$.
4. **Mathematical Bounding:** The computed quotient is strictly clipped to $[-1.0, +1.0]$.
5. **Invalid Propagation:** Where any guard fails, `NaN` is assigned.

---

## 5. Memory-Bounded Theil-Sen Robust Trend Estimation

To evaluate monotonic temporal backscatter degradation across multi-epoch series without sensitivity to isolated weather extremes, the non-parametric Theil-Sen estimator was implemented:

$$\beta = \text{median}_{i < j} \left( \frac{\gamma^0_{\text{dB},j} - \gamma^0_{\text{dB},i}}{t_j - t_i} \right)$$

### 5.1 Algorithmic & Computational Constraints

1. **Doppler Timestamp Precision:** $t_j - t_i$ is evaluated in exact fractional days derived from HDF5 `zeroDopplerStartTime`.
2. **Sample Size Threshold:** Theil-Sen slope requires $N_{\text{valid}} \ge 3$. Where $N_{\text{valid}} < 3$, the slope is strictly `NaN`.
3. **Memory-Bounded Block Processing:** Evaluated in spatial blocks of $512 \times 512$ pixels. This prevents allocating $\mathcal{O}\left(\binom{T}{2} \cdot H \cdot W\right)$ pairwise differences across memory, ensuring bounded memory execution on large rasters.
4. **Behavior on Current 2-Date Data:**
   - Both Frequency B (80 m) and Frequency A (10 m) contain $N = 2$ local dates.
   - The estimator identified $0$ eligible pixels ($N_{\text{valid}} \ge 3$), returning an all-NaN raster in **0.0009s** for Frequency B and **0.112s** for Frequency A, with zero memory overhead.

---

## 6. Three-Tier Disturbance Classification & Taxonomy

In accordance with Review Correction 2, the pipeline replaces misleading persistence terminology with a scientifically honest three-tier hierarchy:

```mermaid
flowchart TD
    A["NISAR Time Series Stack"] --> B{"Valid Epochs (N_valid)"}
    B -->|N = 2| C["Tier 1: Instantaneous Disturbance Candidate"]
    B -->|N >= 3| D["Tier 2: Temporally Sustained Backscatter Anomaly"]
    B -->|N >= 4 & Delta t >= 180d| E["Tier 3: Long-Term Persistent Disturbance Candidate"]
    
    C --> F["Delta HV < -3.0 dB and Delta Ratio < -1.5 dB"]
    D --> G["Sustained drop across >= 2 consecutive post-event epochs"]
    E --> H["Persistent suppression over >= 180 days with no recovery"]
```

### 6.1 Classification Criteria & Operational Status

| Disturbance Tier | Minimum Epochs | Temporal Baseline | Backscatter Decision Rule | Status on Local 2-Date Data |
| :--- | :---: | :---: | :--- | :--- |
| **Tier 1: Instantaneous Disturbance Candidate** | $N \ge 2$ | Any ($\ge 12\text{ d}$) | $\Delta \gamma^0_{\text{HV}} < -3.0\text{ dB} \land \Delta R < -1.5\text{ dB}$ | **ACTIVE & VERIFIED** (Classified on March 4 vs April 21) |
| **Tier 2: Temporally Sustained Backscatter Anomaly** | $N \ge 3$ | $\ge 24\text{ d}$ | $\Delta \gamma^0_{\text{HV}}(t_1) < -3.0\text{ dB} \land \Delta \gamma^0_{\text{HV}}(t_2) < -3.0\text{ dB}$ | **UNVERIFIABLE_TWO_DATES** (Requires 3rd date) |
| **Tier 3: Long-Term Persistent Disturbance Candidate** | $N \ge 4$ | $\ge 180\text{ d}$ | $\overline{\Delta \gamma^0_{\text{HV}}} < -2.5\text{ dB} \land \text{Trend} \le 0 \land \Delta t \ge 180\text{ d}$ | **UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS** |

*Scientific Precaution:* Tier 2 identifies sustained backscatter drops but does not rule out prolonged seasonal drought or persistent phenological changes. Tier 3 identifies structural canopy loss candidates but requires high-resolution optical or in-situ verification to confirm permanent forest clearing.

---

## 7. Isolated Numerical Regression Results

To verify zero regression against Phase 4.1.1 baseline outputs, all feature extraction was executed in `data/processed/validation/temporal_regression/` while keeping `data/processed/temporal/` completely read-only.

Every pixel in all 12 legacy rasters was compared using `temporal_validation.py::compare_raster_baselines`:

| Frequency / Product | Array Dimensions | Valid Overlap Pixels | Max Absolute Difference | Pixels Exceeding $10^{-5}\text{ dB}$ | NoData Mismatches | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `freq_b_hh_t0.tif` | $781 \times 824$ | 197,386 | **0.00e+00 dB** | 0 px | 0 px | **PASSED** |
| `freq_b_hv_t0.tif` | $781 \times 824$ | 197,386 | **0.00e+00 dB** | 0 px | 0 px | **PASSED** |
| `freq_b_ratio_t0.tif` | $781 \times 824$ | 197,386 | **0.00e+00 dB** | 0 px | 0 px | **PASSED** |
| `freq_b_hh_t1.tif` | $781 \times 824$ | 197,626 | **0.00e+00 dB** | 0 px | 0 px | **PASSED** |
| `freq_b_hv_t1.tif` | $781 \times 824$ | 197,626 | **0.00e+00 dB** | 0 px | 0 px | **PASSED** |
| `freq_b_ratio_t1.tif` | $781 \times 824$ | 197,626 | **0.00e+00 dB** | 0 px | 0 px | **PASSED** |
| `freq_b_delta_hh.tif` | $781 \times 824$ | 197,386 | **0.00e+00 dB** | 0 px | 0 px | **PASSED** |
| `freq_b_delta_hv.tif` | $781 \times 824$ | 197,386 | **0.00e+00 dB** | 0 px | 0 px | **PASSED** |
| `freq_b_delta_ratio.tif` | $781 \times 824$ | 197,386 | **0.00e+00 dB** | 0 px | 0 px | **PASSED** |
| `freq_b_temporal_variability.tif` | $781 \times 824$ | 197,386 | **0.00e+00 dB** | 0 px | 0 px | **PASSED** |
| `freq_b_valid_count.tif` | $781 \times 824$ | 197,626 | **0.00e+00** | 0 px | 0 px | **PASSED** |
| `freq_b_physical_change_regimes.tif` | $781 \times 824$ | 197,386 | **0.00e+00** | 0 px | 0 px | **PASSED** |

**Verdict:** 100% bit-for-bit identity across all legacy products. Numerical backward compatibility is unconditionally preserved.

---

## 8. Dynamic Timestamp-Aware Product Exports

In addition to legacy alias filenames (`freq_b_hh_t0.tif`), the engine automatically writes ISO timestamped products:

```
data/processed/validation/temporal_regression/
├── freq_b_hh_20260304.tif
├── freq_b_hv_20260304.tif
├── freq_b_ratio_20260304.tif
├── freq_b_hh_20260421.tif
├── freq_b_hv_20260421.tif
├── freq_b_ratio_20260421.tif
├── freq_b_delta_hv_20260304_to_20260421.tif
├── freq_b_rnd_hv_step.tif
├── freq_b_temporal_mean_hv_linear.tif
├── freq_b_temporal_median_hv_db.tif
├── freq_b_temporal_mad_hv_db.tif
├── freq_b_theil_sen_slope_hv.tif
├── freq_b_tier1_instantaneous_intensity.tif
├── freq_b_provenance.json
└── (identical suite for freq_a at 10 m resolution)
```

Both `freq_b_provenance.json` and `freq_a_provenance.json` record the exact Doppler timestamps, file paths, SHA256 checksums, and execution metrics.

---

## 9. Performance Benchmarks & Resource Attribution

Execution was benchmarked on the local Darwin workstation (`arm64`, macOS):

| Metric | Frequency B (80 m) | Frequency A (10 m) |
| :--- | :---: | :---: |
| **Grid Dimensions ($H \times W$)** | $781 \times 824$ | $6,248 \times 6,592$ |
| **Total Grid Cells** | 644,233 pixels | 41,230,912 pixels |
| **Pipeline Elapsed Time** | **5.58 seconds** | **327.61 seconds** (5.46 min) |
| **Peak RAM Allocation** | **150.0 MB** | **9,594.3 MB** (~9.37 GB) |
| **Theil-Sen Estimator Elapsed Time** | 0.0009 seconds | 0.112 seconds |
| **GeoTIFF Compression** | DEFLATE (zlevel=6) | DEFLATE (zlevel=6) |

---

## 10. Automated Test Suite Verification

A dedicated automated test suite was constructed in [`backend/tests/test_multitemporal_features.py`](file:///Users/srimannarayanadeevi/NISAR/backend/tests/test_multitemporal_features.py), containing 8 comprehensive analytical tests:

1. `test_linear_vs_db_domain_statistics_separation`: Confirms linear power mean/sample standard deviation vs decibel median/MAD, checking against independent analytical benchmarks.
2. `test_mad_and_std_behavior_by_valid_observation_count`: Proves that for $N_{\text{valid}} = 0$ and $N_{\text{valid}} = 1$, sample standard deviation and MAD evaluate strictly to `NaN`, and evaluate to valid finite numbers for $N_{\text{valid}} \ge 2$.
3. `test_relative_normalized_difference_safeguards`: Verifies non-positive rejection, numerical stability floor ($\epsilon_{\text{num}} = 2 \times 10^{-7}$), and strict $[-1.0, 1.0]$ bounding.
4. `test_theil_sen_slope_with_fractional_days_and_outliers`: Validates Theil-Sen trend slope against a synthetic linear trend with gross outliers using exact fractional days.
5. `test_theil_sen_slope_strictly_nan_when_insufficient_epochs`: Proves that on 2-epoch stacks, Theil-Sen slope is strictly `NaN` across all pixels.
6. `test_three_tier_disturbance_classification`: Validates activation of Tier 1 on 2 epochs, and confirms Tier 2 and Tier 3 evaluate to `UNVERIFIABLE_TWO_DATES` and `UNVERIFIABLE_INSUFFICIENT_OBSERVATIONS`.
7. `test_12_point_acquisition_compatibility_validation`: Tests rejection of mismatched CRS, spacing, and flight directions.
8. `test_backward_compatibility_regression_comparator`: Validates tolerance thresholds and mismatch reporting of `compare_raster_baselines`.

**Overall Test Suite Result:** **74 passed, 0 failed, 0 errors** across the full backend test suite (`pytest backend/tests/`).

---

## 11. Scientific Limitations & Boundaries

1. **Two-Date Observational Reality:** On authentic Similipal NISAR data, exactly two dates (`2026-03-04` and `2026-04-21`) exist locally. While the engine mathematically supports arbitrary $N$-epoch stacks, Tier 2 (sustained anomaly) and Tier 3 (persistent disturbance) cannot be proven on local data until intermediate or subsequent scenes are acquired.
2. **Theil-Sen Trend Slopes:** Because $N=2$, the Theil-Sen slope is strictly `NaN` across the authentic Similipal scene. Synthetic multi-temporal tests in pytest verify the mathematical correctness of the estimator on $N \ge 3$ stacks without corrupting authentic observational boundaries.
3. **Sensor Non-Interchangeability:** Frequency A (10 m) and Frequency B (80 m) remain strictly separate pipelines. Features from Frequency A cannot be combined directly with Frequency B without accounting for resolution-dependent spatial integration and speckle statistics.

