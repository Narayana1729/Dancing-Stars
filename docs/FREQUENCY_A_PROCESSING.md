# Scientific Documentation: NISAR Frequency A Processing & Feature Extraction

**Project:** PROJECT NISAR — Forests and Wildfires in India  
**Target Area:** Similipal Tiger Reserve, Mayurbhanj District, Odisha  
**Module:** `backend/app/domains/forests/processing/` (`frequency_a_loader.py`, `polarimetric_features.py`)  
**Status:** Data Loading, Radiometric Interpretation, and Physical Feature Extraction Complete.  

> [!IMPORTANT]
> **Scientific Classification Disclaimer:**
> The extracted polarimetric features documented herein represent calibrated physical radar backscatter differences ($\Delta\gamma^0_{HH}$, $\Delta\gamma^0_{HV}$) and polarimetric cross-ratios ($R_{HV/HH}$, $\Delta R$) in terrain-flattened gamma-naught RTC space. **They DO NOT constitute a validated forest disturbance or wildfire classification.** Disturbance classification requires independent multi-sensor optical cross-validation (Sentinel-2 dNBR/NDVI) and multi-feature statistical or learned decision boundaries. No classification thresholds or machine-learning models are applied in this module.

---

## 1. Source Satellite Datasets & Acquisition Metadata

All calculations are derived from genuine NASA/ISRO NISAR L2 GCOV (Geocoded Polarimetric Covariance) Level-2 measurement granules acquired over Similipal, India:

- **Baseline Observation ($t_0$):**
  - **Granule ID:** `NISAR_L2_PR_GCOV_014_098_A_012_4005_DHDH_A_20260304T233720_20260304T233744_P05023_F_P_J_001`
  - **Acquisition Timestamp:** `2026-03-04T23:37:20.000000000Z`
  - **Local Context:** Late winter / early dry season
  - **Processing CRID:** `P05023`
- **Repeat Observation ($t_1$):**
  - **Granule ID:** `NISAR_L2_PR_GCOV_018_098_A_012_4005_DHDH_A_20260421T233720_20260421T233744_P05023_N_P_J_001`
  - **Acquisition Timestamp:** `2026-04-21T23:37:20.000000000Z`
  - **Local Context:** Peak pre-monsoon dry season (+48 days, exactly 4 orbital repeat cycles of 12 days)
  - **Processing CRID:** `P05023` (software and calibration baseline invariant between dates)
- **Orbital Geometry:**
  - **Orbit Track:** 98
  - **Frame:** 12
  - **Pass Direction:** Ascending
  - **Polarization Mode:** `DHDH` (Transmitted H, Received H and V)

---

## 2. HDF5 Paths & Internal Hierarchy

Features are read directly via windowed slicing from the following internal HDF5 dataset paths:

| Dataset | Internal HDF5 Path | Data Type | Dimensions | Physical Quantity |
| :--- | :--- | :--- | :--- | :--- |
| **HH Covariance** | `/science/LSAR/GCOV/grids/frequencyA/HHHH` | `float32` | $33,696 \times 34,272$ | Geocoded polarimetric covariance $C_{11} = \langle \|S_{HH}\|^2 \rangle$ ($\gamma^0_{RTC}$) |
| **HV Covariance** | `/science/LSAR/GCOV/grids/frequencyA/HVHV` | `float32` | $33,696 \times 34,272$ | Geocoded polarimetric covariance $C_{22} = \langle \|S_{HV}\|^2 \rangle$ ($\gamma^0_{RTC}$) |
| **Subswath Mask** | `/science/LSAR/GCOV/grids/frequencyA/mask` | `uint8` | $33,696 \times 34,272$ | Valid focused sample flag (1: valid, 0: partial/invalid, 255: fill) |
| **Exception Mask**| `/science/LSAR/GCOV/grids/frequencyA/inputDataExceptionMask` | `uint8` | $33,696 \times 34,272$ | Bitwise anomaly flag (0: normal, 2: sample slip) |
| **RTC Scaling Factor** | `/science/LSAR/GCOV/grids/frequencyA/rtcGammaToSigmaFactor` | `float32` | $33,696 \times 34,272$ | Area normalization factor ($\gamma^0 \rightarrow \sigma^0$) |
| **Coordinates** | `/science/LSAR/GCOV/grids/frequencyA/{xCoordinates, yCoordinates}` | `float64` | $34,272$ / $33,696$ | Projected easting and northing in meters |
| **Projection** | `/science/LSAR/GCOV/grids/frequencyA/projection` | `int32` | `()` scalar | EPSG code (`32645` = WGS 84 / UTM Zone 45N) |

---

## 3. Spatial Resolution versus Pixel Spacing

A critical remote-sensing distinction must be maintained between geocoded pixel spacing and effective spatial resolution:

- **Geocoded Pixel Spacing:** **$10.0\text{ m} \times 10.0\text{ m}$**. This is the uniform grid sampling rate on the projected map grid.
- **RF Channel Characteristics:**
  - Center Frequency: $1239.0\text{ MHz}$ ($1.239\text{ GHz}$)
  - Range Bandwidth: **$40.0\text{ MHz}$** ($8\times$ wider than Frequency B's $5.0\text{ MHz}$)
  - Slant Range Resolution: $3.75\text{ m}$
  - Azimuth Resolution: $5.36\text{ m}$
- **Ground Range Resolution:** At local incidence angle $\theta_{\text{inc}} \approx 38^\circ$:
  $$\delta_{\text{ground}} = \frac{3.75\text{ m}}{\sin(38^\circ)} \approx 6.09\text{ m}$$
- **Effective Spatial Resolution (Multi-Looked Independent Cell):**
  - Frequency A natively averages approximately $4.69$ looks per cell.
  - Due to interpolation and multi-looking, the **effective radiometrically independent resolution cell is approximately $15\text{ m} \times 15\text{ m}$ to $20\text{ m} \times 20\text{ m}$**.
  - While it resolves canopy gaps an order of magnitude smaller than Frequency B ($80\text{ m}$ grid, $50\text{ m}$ ground resolution), individual $10\text{ m}$ pixels exhibit single-pixel speckle fluctuation ($\sigma/\mu = 1/\sqrt{4.69} \approx 0.46$, or $\approx \pm 1.8\text{ dB}$). Spatial filtering is mandatory before thresholding.

---

## 4. Radiometric Conventions & RTC Factor Handling

### 4.1 Gamma-Naught vs. Sigma-Naught
- **Physical Standard:** The HDF5 `HHHH` and `HVHV` arrays represent **radiometrically terrain-corrected gamma-naught ($\gamma^0_{RTC}$)** normalized by projected illuminated area.
- **Why $\gamma^0_{RTC}$ is Preferred for Forestry:** In rugged topography (such as the Similipal hills rising from $100\text{ m}$ to $1,165\text{ m}$), $\sigma^0$ depends strongly on local slope and aspect. $\gamma^0_{RTC}$ removes this geometric illumination bias, making backscatter directly proportional to canopy volume density and biomass.
- **RTC Factor Behavior across Similipal ($N = 12,636,059$ valid pixels):**
  - $t_0$ Factor: $\text{min} = 0.00118$, $\text{max} = 0.99919$, $\text{mean} = 0.69826$, $\text{std} = 0.09184$
  - $t_1$ Factor: $\text{min} = 0.00154$, $\text{max} = 0.99922$, $\text{mean} = 0.69835$, $\text{std} = 0.09183$
  - Max Absolute Difference ($|t_1 - t_0|$): **$0.11254$**
  - *Conclusion:* Because orbit tubes and local incidence angles vary slightly between passes, the RTC conversion factor **does NOT cancel identically** between dates in mountainous terrain. Converting $\gamma^0_{RTC} \rightarrow \sigma^0$ would introduce up to several dB of false topographic edge differences. The pipeline strictly maintains all calculations in **$\gamma^0_{RTC}$** space.

---

## 5. Mathematical Feature Equations & Numerics

All features are extracted using numerically safe float32 operations, clipping sub-noise values to $\epsilon = 10^{-7}$ ($-70\text{ dB}$, well below the NISAR NESZ of $-28\text{ dB}$):

1. **Temporal HH Backscatter Difference:**
   $$\Delta\gamma^0_{HH,\text{dB}} = 10 \cdot \log_{10}\left(\frac{\gamma^0_{HH}(t_1)}{\gamma^0_{HH}(t_0)}\right) = \gamma^0_{HH,\text{dB}}(t_1) - \gamma^0_{HH,\text{dB}}(t_0)$$
2. **Temporal HV Backscatter Difference:**
   $$\Delta\gamma^0_{HV,\text{dB}} = 10 \cdot \log_{10}\left(\frac{\gamma^0_{HV}(t_1)}{\gamma^0_{HV}(t_0)}\right) = \gamma^0_{HV,\text{dB}}(t_1) - \gamma^0_{HV,\text{dB}}(t_0)$$
3. **Cross-Polarization Ratio at $t_0$:**
   $$R_{HV/HH,t0} = 10 \cdot \log_{10}\left(\frac{\gamma^0_{HV}(t_0)}{\gamma^0_{HH}(t_0)}\right) = \gamma^0_{HV,\text{dB}}(t_0) - \gamma^0_{HH,\text{dB}}(t_0)$$
4. **Cross-Polarization Ratio at $t_1$:**
   $$R_{HV/HH,t1} = 10 \cdot \log_{10}\left(\frac{\gamma^0_{HV}(t_1)}{\gamma^0_{HH}(t_1)}\right) = \gamma^0_{HV,\text{dB}}(t_1) - \gamma^0_{HH,\text{dB}}(t_1)$$
5. **Temporal Cross-Ratio Change:**
   $$\Delta R_{HV/HH} = R_{HV/HH,t1} - R_{HV/HH,t0} = \Delta\gamma^0_{HV,\text{dB}} - \Delta\gamma^0_{HH,\text{dB}}$$

---

## 6. Invalid-Pixel Treatment & Quality Masking

Pixels are classified as valid only when satisfying all four conditions:
1. Native NISAR subswath valid mask: `mask == 1` (excludes fill values `255` outside acquisition swath and edge partial samples `0`).
2. Input data exception mask: `inputDataExceptionMask == 0` (excludes instrument sample slips).
3. Value sanity: $\text{isfinite}(P) \text{ and } P > 10^{-7}$.
4. Multi-temporal intersection: Pixel must be valid in **both** $t_0$ and $t_1$.

Any pixel failing these criteria is assigned `np.nan` in the output float32 GeoTIFFs, and `0` in `valid_mask.tif`.

---

## 7. Known Scientific Limitations

1. **Environmental Phenology Confounding:** Over the 48-day baseline (March 04 to April 21), Sal forests (*Shorea robusta*) shed leaves, and soils desiccate under $>40^\circ\text{C}$ pre-monsoon heat. A negative $\Delta\gamma^0_{HV}$ alone cannot distinguish severe foliar desiccation from tree felling without optical dNBR corroboration.
2. **Speckle Variance at 10 m:** With $4.7$ looks, individual pixels have $\pm 1.8\text{ dB}$ radiometric noise. Feature maps must be spatially smoothed (e.g. 3x3 Lee filter or multi-pixel object grouping) before applying decision boundaries.
3. **Absence of Quad-Pol Phase Coherence:** In dual-polarization `DHDH`, off-diagonal complex covariance terms ($C_{12}$) are not transmitted, preventing full polarimetric target decomposition (Freeman-Durden / Cloude-Pottier). Disturbance detection must rely on intensity differences and cross-ratios.

