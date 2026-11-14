# Independent Audit: Frequency A (10 m) Implementation & Generated Outputs

**Project:** PROJECT NISAR — Forests and Wildfires in India  
**Target Area:** Similipal Tiger Reserve, Mayurbhanj District, Odisha  
**Audit Scope:** Verification of Windowed Loader, Radiometric Interpretation, Feature Mathematics, Georeferencing, and Output GeoTIFFs  
**Audit Date:** 2026-11-14  

---

## Executive Audit Scorecard

| Check # | Verification Item | Status | Key Evidence / Observations |
| :--- | :--- | :--- | :--- |
| **1** | **HDF5 Dataset Paths** | **PASS** | `science/LSAR/GCOV/grids/frequencyA/{HHHH, HVHV}` read directly via windowed slicing. |
| **2** | **Radiometric Interpretation** | **PASS** | Covariance diagonal elements $C_{11}, C_{22}$ correctly interpreted as terrain-flattened $\gamma^0_{RTC}$ in linear power (`units = '1'`). |
| **3** | **Quality Masks & NaN Handling** | **PASS** | Combined condition requires `mask == 1`, `inputDataExceptionMask == 0`, and finite power $> 10^{-7}$. Fill (`255`) and edge partials (`0`) excluded. |
| **4** | **Coordinate Transform & Georeferencing** | **PASS** | Cell-edge transform `from_origin(401640.0, 2438360.0, 10.0, 10.0)` in `EPSG:32645`. Aligns with Frequency B at exact 8:1 integer ratio. |
| **5** | **Multi-Temporal Alignment ($t_0$ vs $t_1$)** | **PASS** | `np.array_equal` confirms identical coordinate arrays (`xCoordinates`, `yCoordinates`). 0.0 m offset. |
| **6** | **Feature Math ($\Delta HH, \Delta HV, R, \Delta R$)** | **PASS** | Logarithmic decibel calculations validated by 10/10 automated property tests in `backend/tests/test_frequency_a.py`. |
| **7** | **RTC Factor Handling** | **PASS** | `rtcGammaToSigmaFactor` extracted for both dates. Proved non-cancellation ($|t_1 - t_0| \le 0.1125$). Maintained in $\gamma^0_{RTC}$ space. |
| **8** | **Valid Pixel Counts & Coverage** | **PASS** | $12,636,059$ valid pixels ($1,263.61\text{ km}^2$). Matches Frequency B coverage ($1,263.3\text{ km}^2$) within $0.02\%$. |
| **9** | **Peak RAM & Execution Time** | **PASS** | Peak RAM: $2.352\text{ GB}$ ($< 10\%$ of 24 GB RAM). Processing runtime: $22.08\text{ seconds}$. |
| **10** | **GIS Software Compatibility** | **PASS** | 6 GeoTIFFs formatted as Cloud-Optimized tiled Deflate rasters ($256 \times 256$ blocks) with valid EPSG:32645 projection and NoData tags. |

**Overall Audit Result: 10 / 10 CHECKS PASSED**

---

## Detailed Audit Findings

### 1. Correct HDF5 Dataset Paths
- The loader accesses:
  - `/science/LSAR/GCOV/grids/frequencyA/HHHH`
  - `/science/LSAR/GCOV/grids/frequencyA/HVHV`
  - `/science/LSAR/GCOV/grids/frequencyA/mask`
  - `/science/LSAR/GCOV/grids/frequencyA/inputDataExceptionMask`
  - `/science/LSAR/GCOV/grids/frequencyA/rtcGammaToSigmaFactor`
- Slicing is executed via `h5py` dataset indexers `[y_slice, x_slice]`, pulling only the $6616 \times 6232$ ROI without reading full 4.8 GB scenes into RAM.

### 2. Radiometric Interpretation as RTC Gamma-Naught
- Attributes in the HDF5 file confirm `description = b'Covariance between HH and HH'`, `units = b'1'`.
- In NISAR L2 GCOV products, these values are terrain-flattened gamma-naught ($\gamma^0_{RTC}$).
- The code variables consistently use:
  - `gamma0_rtc_hh_t0`
  - `gamma0_rtc_hv_t0`
  - `gamma0_rtc_hh_t1`
  - `gamma0_rtc_hv_t1`
- No erroneous conversions to $\sigma^0$ are performed.

### 3. Handling of Quality Masks and NoData
- In NISAR GCOV, `mask` is a subswath sample mask:
  - `255`: Unobserved / fill area outside radar swath.
  - `0`: Partially focused or edge-corrupted sample.
  - `1`: Fully-focused valid subswath 1 radar sample.
- The loader enforces `(mask0 == 1) & (mask1 == 1) & (ex0 == 0) & (ex1 == 0) & isfinite & (power > 1e-7)`.
- Output GeoTIFFs assign `np.nan` with GDAL metadata `nodata = nan`.

### 4. Coordinate Transformation & Georeferencing
- Coordinate arrays: `sub_x` ($6,232$ values), `sub_y` ($6,616$ values).
- Coordinate spacing: $\Delta x = +10.0\text{ m}$, $\Delta y = -10.0\text{ m}$.
- Affine Transform:
  $$\begin{bmatrix} 10.0 & 0.0 & 401640.0 \\ 0.0 & -10.0 & 2438360.0 \end{bmatrix}$$
- Top-left corner matches the Frequency B grid origin `(401640.0, 2438360.0)` exactly ($80\text{ m} / 10\text{ m} = 8$).

### 5. Alignment Between Dates
- Verified by:
  ```python
  np.array_equal(sub_x0, sub_x1) == True
  np.array_equal(sub_y0, sub_y1) == True
  ```
- Sub-millimeter spatial alignment between $t_0$ (2026-03-04) and $t_1$ (2026-04-21).

### 6. Mathematical Feature Extraction
- **Temporal HH Change:**
  $$\Delta\gamma^0_{HH,\text{dB}} = 10 \log_{10}(HH_{t1} / HH_{t0})$$
  Evaluated over valid pixels: $\text{mean} = +0.04\text{ dB}$, $\text{std} = 2.81\text{ dB}$, $\text{median} = +0.04\text{ dB}$.
- **Temporal HV Change:**
  $$\Delta\gamma^0_{HV,\text{dB}} = 10 \log_{10}(HV_{t1} / HV_{t0})$$
  Evaluated over valid pixels: $\text{mean} = -0.14\text{ dB}$, $\text{std} = 2.82\text{ dB}$, $\text{median} = -0.14\text{ dB}$.
- **Cross-Polarization Ratios ($R = 10 \log_{10}(HV / HH)$):**
  - $R_{t0}$: $\text{mean} = -5.73\text{ dB}$, $\text{median} = -5.69\text{ dB}$.
  - $R_{t1}$: $\text{mean} = -5.92\text{ dB}$, $\text{median} = -5.87\text{ dB}$.
- **Temporal Ratio Change:**
  $$\Delta R = R_{t1} - R_{t0} = \Delta\gamma^0_{HV} - \Delta\gamma^0_{HH}$$
  Evaluated over valid pixels: $\text{mean} = -0.19\text{ dB}$, $\text{std} = 3.82\text{ dB}$, $\text{median} = -0.18\text{ dB}$.
- Calculations are verified by automated tests `test_hh_temporal_change_calculation`, `test_hv_temporal_change_calculation`, `test_hv_hh_ratio_calculation`, and `test_temporal_ratio_difference`.

### 7. RTC Factor Stability Check
- Across the $12.64\text{M}$ valid pixels:
  - Factor range: $0.00118$ to $0.99922$.
  - Spatial standard deviation: $\sigma = 0.0918$ (significant topographic variation across the Similipal massif).
  - Temporal difference ($t_1 - t_0$): range $[-0.1125, +0.0784]$.
- The non-zero temporal difference confirms that the RTC factor does not cancel identically on steep topography due to slight orbit tube differences. Operating in $\gamma^0_{RTC}$ prevents this geometric factor from contaminating backscatter differencing.

### 8. Pixel Counts and Spatial Coverage
- Total ROI grid pixels: $41,230,912$ ($6616 \times 6232$).
- Valid co-registered pixels: **$12,636,059$** ($30.65\%$, covering $1,263.61\text{ km}^2$).
- Invalid / outside-swath pixels: $28,594,853$ ($69.35\%$).

### 9. Peak RAM and Execution Profile
- Peak RAM consumption: **$2,408.80\text{ MB}$ ($2.352\text{ GB}$)**.
- Total pipeline execution time: **$22.08\text{ seconds}$**.
- Well within the 24 GB hardware constraint.

### 10. GIS Compatibility of Generated Rasters
All 6 rasters in `data/processed/frequency_a/`:
- `delta_gamma0_hh_db.tif` (44.8 MB)
- `delta_gamma0_hv_db.tif` (44.8 MB)
- `ratio_hv_hh_t0_db.tif` (43.2 MB)
- `ratio_hv_hh_t1_db.tif` (43.2 MB)
- `delta_ratio_hv_hh_db.tif` (44.4 MB)
- `valid_mask.tif` (68.2 KB)

Inspected via `rasterio`:
- Profile: Tiled GeoTIFF ($256 \times 256$ blocks), Deflate compression, float32 (uint8 for mask).
- Valid CRS (`EPSG:32645`), Affine transform, and explicit `nodata = nan`.
- Confirmed ready for standard GIS ingestion (QGIS, ArcGIS, GDAL).

---

## Ledger of Verified Issues and Unresolved Issues

### Verified Issues Resolved in this Implementation
1. **Resolved:** Conflation of $\gamma^0$ and $\sigma^0$ eliminated; variables and equations explicitly standardize on $\gamma^0_{RTC}$.
2. **Resolved:** Coarse $80\text{ m}$ spatial smearing bypassed; native $40\text{ MHz}$ Frequency A ($10\text{ m}$ grid) extracted and processed.
3. **Resolved:** Quality masks (`mask`, `inputDataExceptionMask`) integrated into valid pixel determination.
4. **Resolved:** Memory bloat prevented; windowed reading keeps peak RAM under $2.4\text{ GB}$.

### Unresolved Scientific Issues (Forward Requirements)
1. **Unresolved:** **Single-Pixel Speckle Variance at 10 m:**
   - With $ENL \approx 4.69$, individual $10\text{ m}$ pixels exhibit $\pm 1.8\text{ dB}$ radiometric speckle. Applying a point-based threshold to Frequency A will produce high false alarm rates without spatial filtering (e.g. 3x3 Lee filter or multi-pixel segmentation).
2. **Unresolved:** **Confounding of Pre-Monsoon Phenology & Moisture:**
   - The observed mean $\Delta\gamma^0_{HV} = -0.14\text{ dB}$ reflects broad dry-season stability, but negative excursions occur due to deciduous leaf fall (Sal) and soil desiccation. Two-date differencing cannot isolate canopy removal without optical confirmation.
3. **Unresolved:** **Lack of Concurrent Optical Ground Truth:**
   - Independent cross-validation with Sentinel-2 MSI dNBR / $\Delta\text{NDVI}$ (March–April 2026) is required before any feature combination can be interpreted as verified disturbance.

