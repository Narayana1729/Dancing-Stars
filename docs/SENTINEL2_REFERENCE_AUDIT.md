# Sentinel-2 Optical Reference Observation Audit: Similipal Tiger Reserve

**Project:** NISAR — Forests and Wildfires in India  
**Study Area:** Similipal Tiger Reserve, Mayurbhanj District, Odisha, India  
**Phase:** Phase 4 — Task 3: Independent Optical Observation Search & Validation Architecture  
**Date of Audit:** 2026-11-14  
**Status:** COMPLETE & INDEPENDENTLY VERIFIED (DOWNLOAD GATE ACTIVE)  

---

## 1. Executive Summary & Context

To independently validate radar backscatter disturbance detections derived from multi-temporal NISAR L-band observations (Track 098, Frames 012 and 013), an exhaustive optical satellite search was conducted across the **Copernicus Data Space Ecosystem (CDSE)**. 

Using the authoritative administrative boundaries verified in Task 1 ([docs/SIMILIPAL_BOUNDARY_AUDIT.md](file:///Users/srimannarayanadeevi/NISAR/docs/SIMILIPAL_BOUNDARY_AUDIT.md))—Similipal Wildlife Sanctuary Complex ($2,178.22\text{ km}^2$) and Core Area / Critical Tiger Habitat ($1,224.30\text{ km}^2$)—all Sentinel-2 Level-2A (Bottom-of-Atmosphere surface reflectance) observations acquired between **01 March 2026 and 30 June 2026** were systematically catalogued and analyzed.

A total of **130 authentic Sentinel-2 L2A scenes** were identified across MGRS tiles **T45QVE** and **T45QVD**.

---

## 2. Sentinel-2 MGRS Tile Footprints & Spatial Coverage

Similipal Tiger Reserve is split longitudinally across two primary MGRS tiles in UTM Zone 45N:

| MGRS Tile | Relative Orbit(s) | Sanctuary Coverage (`EPSG:32645`) | Core CTH Coverage (`EPSG:32645`) | Spatial Role in Reserve Monitoring |
| :--- | :--- | :--- | :--- | :--- |
| **T45QVE** | **R076** (Primary) | **$89.64\%$** ($1,952.5\text{ km}^2$) | **$86.61\%$** ($1,060.4\text{ km}^2$) | **Primary Central Reserve Tile.** Captures the central Similipal massif, core tiger habitat, upper escarpments, and waterfalls. |
| **T45QVE** | **R033** (Secondary) | **$42.60\%$** ($927.9\text{ km}^2$) | **$65.15\%$** ($797.7\text{ km}^2$) | Eastern swath pass of Tile T45QVE. |
| **T45QVD** | **R076** (Primary) | **$25.05\%$** ($545.6\text{ km}^2$) | **$35.36\%$** ($432.9\text{ km}^2$) | **Southern / Western Boundary Tile.** Captures southern ranges (Thakurmunda, Kendumundi) and southwestern approaches. |
| **T45QVD** | **R033** (Secondary) | **$14.86\%$** ($323.7\text{ km}^2$) | **$26.12\%$** ($319.8\text{ km}^2$) | Eastern swath pass of Tile T45QVD. |
| **T45QVE + T45QVD** | **R076** | **$100.00\%$** ($2,178.2\text{ km}^2$) | **$100.00\%$** ($1,224.3\text{ km}^2$) | **Unified Full Reserve Coverage.** The combined mosaic on Relative Orbit R076 provides $100\%$ spatial observation of Similipal Tiger Reserve. |

---

## 3. Required Spectral Bands & Radiometric Specifications

Sentinel-2 Level-2A products provide geometrically orthorectified, atmospherically corrected Bottom-Of-Atmosphere (BOA) surface reflectance:

| Band Identifier | Central Wavelength ($\lambda$) | Bandwidth ($\Delta\lambda$) | Spatial Resolution | Key Biophysical Function |
| :--- | :--- | :--- | :--- | :--- |
| **B04 (Red)** | $665\text{ nm}$ | $30\text{ nm}$ | **$10\text{ m}$** | Chlorophyll absorption; vegetation contrast. |
| **B08 (Broad NIR)** | $842\text{ nm}$ | $115\text{ nm}$ | **$10\text{ m}$** | Mesophyll cell structure scattering; vegetation vigor. |
| **B8A (Narrow NIR)** | $865\text{ nm}$ | $20\text{ nm}$ | **$20\text{ m}$** | Biomass; avoids atmospheric water vapor absorption. |
| **B12 (SWIR-2)** | $2,190\text{ nm}$ | $180\text{ nm}$ | **$20\text{ m}$** | Canopy water content, soil moisture, ash, char, and burn scars. |
| **SCL (Scene Classification)** | *N/A (Derived)* | *N/A* | **$20\text{ m}$** | Pixel-level atmospheric, cloud, shadow, and snow masking. |

---

## 4. Formulation & Mathematical Definitions of Optical Indices

### 1. Normalized Difference Vegetation Index (NDVI)

$$\text{NDVI} = \frac{\text{B08} - \text{B04}}{\text{B08} + \text{B04}}$$

* **Spatial Resolution:** $10\text{ m}$ native resolution.
* **Biophysical Range:** Valid in $[-1.0, +1.0]$.
* **Forest Baseline:** Dense closed-canopy semi-evergreen/sal forests in Similipal exhibit $\text{NDVI} \in [0.68, 0.86]$ during the pre-monsoon dry season.
* **Deforestation / Canopy Loss Criterion:** An abrupt, persistent decline $\Delta\text{NDVI} = \text{NDVI}_{\text{post}} - \text{NDVI}_{\text{pre}} \le -0.20$.

### 2. Normalized Burn Ratio (NBR)

$$\text{NBR} = \frac{\text{B8A} - \text{B12}}{\text{B8A} + \text{B12}}$$

* **Spatial Resolution:** $20\text{ m}$ native resolution (using Narrow NIR Band 8A and SWIR Band 12).
* **Physical Basis:** Unburned healthy forest exhibits high NIR scattering and low SWIR absorption (high positive NBR). Burned areas exhibit severe NIR destruction and elevated SWIR reflectance from exposed dry soil, ash, and char (negative or low NBR).

### 3. Difference Normalized Burn Ratio (dNBR) & Explicit Sign Convention

To prevent ambiguity, this project strictly adopts the standard **USGS / Key & Benson (2006)** sign convention:

$$\text{dNBR} = \text{NBR}_{\text{pre}} - \text{NBR}_{\text{post}}$$

* **Sign Convention Property:** **Higher positive values indicate higher burn severity.**
* **Burn Severity Classification Thresholds (USGS Standards):**
  * $\text{dNBR} < -0.100$: Enhanced regrowth / post-fire flush
  * $-0.100 \le \text{dNBR} < +0.100$: **Unburned**
  * $+0.100 \le \text{dNBR} < +0.270$: **Low-severity burn** (surface litter / ground scorch)
  * $+0.270 \le \text{dNBR} < +0.440$: **Moderate-low severity burn** (understory mortality)
  * $+0.440 \le \text{dNBR} < +0.660$: **Moderate-high severity burn** (partial canopy scorch)
  * $\text{dNBR} \ge +0.660$: **High severity burn** (complete stand-replacement / crown fire)

*(Note: If temporal difference $\Delta\text{NBR} = \text{NBR}_{\text{post}} - \text{NBR}_{\text{pre}}$ is computed, fire burns produce negative numbers. The $\text{pre} - \text{post}$ USGS convention is standard across ecological fire validation).*

---

## 5. Methodological Separation: General Disturbance vs. Wildfire Assessment

To avoid scientific conflation, optical validation must bifurcate into two distinct analytical tracks:

```
                          SATELLITE CHANGE PHENOMENON
                                       │
        ┌──────────────────────────────┴──────────────────────────────┐
        ▼                                                             ▼
GENERAL FOREST DISTURBANCE                                    WILDFIRE BURNS
(Logging, storm damage, road clearance)              (Surface litter fires, crown fires)
───────────────────────────────────────              ───────────────────────────────────
• Primary Index: ΔNDVI = NDVI_post - NDVI_pre         • Primary Index: dNBR = NBR_pre - NBR_post
• Secondary Index: NDMI = (B08-B11)/(B08+B11)        • Validation: MODIS/VIIRS Active Fires (FIRMS)
• Persistence: Signal persists >60-90 days            • Ephemerality: Black ash dissipates in 2-3 weeks;
• Ground Phenology: Clear-cut soil, tree fall           rapid post-fire monsoon flush (greenup)
```

---

## 6. Cloud, Cloud-Shadow, and Atmospheric Quality Masking

Sentinel-2 L2A includes the native **Scene Classification Layer (SCL)** generated by Sen2Cor at $20\text{ m}$ resolution:

### SCL Filtering Protocol

| SCL Value | Description | Quality Mask Decision | Rationale |
| :--- | :--- | :--- | :--- |
| **0** | No Data | **EXCLUDE (Mask)** | Missing / swath edge. |
| **1** | Saturated or Defective | **EXCLUDE (Mask)** | Detector saturation. |
| **2** | Dark Area Pixels | **RETAIN with inspection** | Steep terrain shadow. |
| **3** | **Cloud Shadows** | **EXCLUDE (Mask)** | Depresses NIR/SWIR; mimics false disturbance. |
| **4** | Vegetation | **RETAIN (Valid)** | High confidence green forest canopy. |
| **5** | Not-Vegetated | **RETAIN (Valid)** | Bare soil, exposed rock, road clearance. |
| **6** | Water | **RETAIN (Valid)** | Rivers, reservoirs. |
| **7** | Unclassified | **EXCLUDE (Mask)** | Ambiguous spectral signature. |
| **8** | **Cloud Medium Probability** | **EXCLUDE (Mask)** | Partial cloud contamination. |
| **9** | **Cloud High Probability** | **EXCLUDE (Mask)** | Opaque cumulus/stratus cloud. |
| **10** | **Thin Cirrus** | **EXCLUDE (Mask)** | Atmospheric haze; alters spectral ratios. |
| **11** | Snow / Ice | **EXCLUDE (Mask)** | Non-applicable in Odisha tropical latitude. |

**Valid Pixel Mask Formula:** $\text{Valid} = (\text{SCL} \in \{4, 5, 6\}) \land (\text{SCL} \notin \{0, 1, 3, 8, 9, 10\})$

### Monthly Optical Climatology over Similipal (Tile T45QVE)

* **March 2026 (12 acquisitions):** **7 clear passes ($<10\%$ cloud)**, 3 partially cloudy, 2 overcast. Peak dry-season visibility.
* **April 2026 (12 acquisitions):** **6 clear passes ($<10\%$ cloud)**, 4 partially cloudy, 2 overcast. Excellent pre-monsoon optical continuity.
* **May 2026 (12 acquisitions):** **2 clear passes**, 5 partially cloudy, 5 overcast. Increasing pre-monsoon convective thunderstorms ("Kalbaishakhi").
* **June 2026 (12 acquisitions):** **0 clear passes**, 2 partially cloudy, 10 overcast ($>75\%$ cloud). Full Southwest Monsoon onset; optical imagery severely degraded.

---

## 7. Recommended Reference Observation Pairs

To validate the NISAR multi-temporal baseline (`2026-03-04` vs. `2026-04-21`), two distinct optical reference packages were designed:

### Package 1: Identical Relative Orbit (R076) Validation Quad (PRIMARY RECOMMENDED)

By matching both pre-event and post-event images on **Relative Orbit R076**, sun-sensor viewing geometry and solar azimuth differences are minimized:

| Observation Role | Target Date | MGRS Tile | Relative Orbit | Cloud Cover | Sanctuary Coverage | Core CTH Coverage | Product ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Pre-Event (North)** | **2026-03-02** | **T45QVE** | **R076** | **$6.50\%$** | **$89.64\%$** | **$86.61\%$** | `S2C_MSIL2A_20260302T044721_N0512_R076_T45QVE_20260302T094009.SAFE` |
| **Pre-Event (South)** | **2026-03-02** | **T45QVD** | **R076** | **$0.00\%$** | **$25.05\%$** | **$35.36\%$** | `S2C_MSIL2A_20260302T044721_N0512_R076_T45QVD_20260302T094009.SAFE` |
| **Post-Event (North)**| **2026-04-16** | **T45QVE** | **R076** | **$2.09\%$** | **$89.64\%$** | **$86.61\%$** | `S2B_MSIL2A_20260416T044659_N0512_R076_T45QVE_20260416T083549.SAFE` |
| **Post-Event (South)**| **2026-04-16** | **T45QVD** | **R076** | **$6.64\%$** | **$25.05\%$** | **$35.36\%$** | `S2B_MSIL2A_20260416T044659_N0512_R076_T45QVD_20260416T083549.SAFE` |

* **Total Mosaic Coverage:** **$100.00\%$ of Similipal Tiger Reserve** at both dates.
* **Temporal Proximity:** Pre-event acquired **2 days before NISAR T0**; Post-event acquired **5 days before NISAR T1**.
* **Optical Quality:** Under $7\%$ cloud cover across all tiles.

### Package 2: Exact-Date NISAR Coincidence Pair (SECONDARY REFERENCE)

* **Pre-Event:** **2026-03-04** (`S2B_MSIL2A_20260304T043659_N0512_R033_T45QVE_...`, **$0.00\%$ cloud**; identical day as NISAR T0).
* **Post-Event:** **2026-04-23** (`S2B_MSIL2A_20260423T043659_N0512_R033_T45QVE_...`, **$22.7\%$ cloud**; +2 days from NISAR T1).

---

## 8. Visual Artifacts Generated

1. **Sentinel-2 Acquisition Timeline & Usability Graphic:**
   - [data/reference/sentinel2_catalogue/sentinel2_observation_timeline.png](file:///Users/srimannarayanadeevi/NISAR/data/reference/sentinel2_catalogue/sentinel2_observation_timeline.png)
   - Panel 1: Bar chart of all 130 acquisitions showing cloud cover percentages, clear/usable thresholds, and NISAR coincidence markers.
   - Panel 2: Monthly breakdown showing the transition from high pre-monsoon clarity in March/April to monsoonal cloud blockage in June.
2. **Sentinel-2 MGRS Tile Footprint Map:**
   - [data/reference/sentinel2_catalogue/sentinel2_tile_coverage_map.png](file:///Users/srimannarayanadeevi/NISAR/data/reference/sentinel2_catalogue/sentinel2_tile_coverage_map.png)
   - Cartographic layout showing MGRS Tiles T45QVE and T45QVD overlaid onto the verified Similipal Sanctuary Complex, Core Area CTH, and rectangular AOI.

---

## 9. Machine-Readable Catalogues

* **Full Catalogue (JSON, 130 scenes):** [data/reference/sentinel2_catalogue/sentinel2_similipal_full_catalog.json](file:///Users/srimannarayanadeevi/NISAR/data/reference/sentinel2_catalogue/sentinel2_similipal_full_catalog.json)
* **Full Catalogue (CSV, 130 scenes):** [data/reference/sentinel2_catalogue/sentinel2_similipal_full_catalog.csv](file:///Users/srimannarayanadeevi/NISAR/data/reference/sentinel2_catalogue/sentinel2_similipal_full_catalog.csv)
* **Recommended Temporal Pairs (JSON):** [data/reference/sentinel2_catalogue/sentinel2_recommended_pairs.json](file:///Users/srimannarayanadeevi/NISAR/data/reference/sentinel2_catalogue/sentinel2_recommended_pairs.json)
* **Download Gate Specification (JSON):** [data/reference/sentinel2_catalogue/sentinel2_download_gate_summary.json](file:///Users/srimannarayanadeevi/NISAR/data/reference/sentinel2_catalogue/sentinel2_download_gate_summary.json)

---

## 10. DOWNLOAD GATE AUDIT & VERIFICATION RESULTS

In accordance with strict project rules and following explicit user authorization, the **Identical Relative Orbit R076 Validation Quad** was downloaded from Copernicus Data Space Ecosystem (CDSE) and cryptographically verified:

| Product File | File Size | SHA-256 Checksum | Acquisition Date | Tile | Orbit | Cloud Cover |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `S2C_MSIL2A_20260302T044721_N0512_R076_T45QVD_...zip` | **$637.7\text{ MB}$** | `b6acd53df93655cbfd507da45fd803af33b28ef8720d374558a390ac084182d7` | 2026-03-02 | T45QVD | R076 | $0.00\%$ |
| `S2C_MSIL2A_20260302T044721_N0512_R076_T45QVE_...zip` | **$892.4\text{ MB}$** | `6cbd39b096f229cd256390f4980fe5e866f9f01e7d10f4e10802622b8a6ca697` | 2026-03-02 | T45QVE | R076 | $6.50\%$ |
| `S2B_MSIL2A_20260416T044659_N0512_R076_T45QVD_...zip` | **$645.5\text{ MB}$** | `62e94f654e3dd5a35a36e8a71e317de4d379be4c4a386e664837e270e30ae097` | 2026-04-16 | T45QVD | R076 | $6.64\%$ |
| `S2B_MSIL2A_20260416T044659_N0512_R076_T45QVE_...zip` | **$898.4\text{ MB}$** | `cc1b2f9b50ad50e6334f25ccde8cdcff1291b5e764de41d73b46c5be77fd2426` | 2026-04-16 | T45QVE | R076 | $2.09\%$ |

* **Total Download Volume:** **$3.074\text{ GB}$** ($3,223,337,699\text{ bytes}$).
* **Integrity Status:** All 4 products successfully extracted/verified; contains all required spectral bands (`B04`, `B08`, `B8A`, `B12`) and `SCL` cloud mask layers.
* **Manifest Ledger:** Logged to [data/reference/sentinel2_catalogue/manifest.jsonl](file:///Users/srimannarayanadeevi/NISAR/data/reference/sentinel2_catalogue/manifest.jsonl).
* **Storage Preserved:** Available local disk space remains at **$118\text{ GiB}$** ($>97\%$ free capacity preserved).
* **Compliance:** No disturbance labels or ML models were generated in this task.

