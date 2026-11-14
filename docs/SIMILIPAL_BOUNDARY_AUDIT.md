# Similipal Tiger Reserve Authoritative Boundary Audit

**Project:** NISAR — Forests and Wildfires in India  
**Study Area:** Similipal Tiger Reserve, Mayurbhanj District, Odisha, India  
**Phase:** Phase 4 — Task 1: Authoritative Boundary Investigation and NISAR Swath Spatial Overlap Audit  
**Date of Audit:** 2026-11-14  
**Status:** COMPLETE & INDEPENDENTLY VERIFIED  

---

## 1. Authoritative Sources Investigated

To obtain and verify the official geographic boundaries of Similipal Tiger Reserve, five authoritative institutional sources and primary data platforms were independently investigated:

1. **National Tiger Conservation Authority (NTCA), Ministry of Environment, Forest and Climate Change (MoEFCC), Govt. of India:**
   - **Portal Investigated:** `https://ntca.gov.in/tiger-reserves/`
   - **Primary Evidence Retrieved:** The authentic statutory gazette notification document `Notification_Similipal.pdf` (`data/reference/boundaries/original/Notification_Similipal.pdf`, 9.54 MB).
   - **Statutory Contents:** Contains *Schedule A* (Location & Area: Core/CTH $1,194.75\text{ km}^2$, Buffer $1,555.25\text{ km}^2$, Total $2,750.00\text{ km}^2$; Latitudes $20^\circ 17'\text{N}$ to $22^\circ 54'\text{N}$, Longitudes $85^\circ 40'\text{E}$ to $87^\circ 10'\text{E}$) and *Schedule B* (Metes-and-bounds survey description of the outer boundary of Similipal Tiger Reserve across Mayurbhanj district).

2. **Wildlife Institute of India (WII) / National Wildlife Database:**
   - **Portal Investigated:** `https://wii.gov.in/tiger_reserves`
   - **Status:** Provides descriptive spatial records and PA gazette listings matching NTCA area designations ($1,194.75\text{ km}^2$ Core, $1,555.25\text{ km}^2$ Buffer). No direct public GIS vector download endpoint was available on the main web portal.

3. **Odisha Forest Department (Field Directorate, Similipal Tiger Reserve, Baripada):**
   - **Portal Investigated:** `https://odishaforest.in` and `https://www.similipal.org`
   - **Status:** Validated administrative zoning: Similipal Tiger Reserve is split into two administrative forest divisions:
     - **Similipal North Wildlife Division** (headquarters at Rairangpur / Jashipur).
     - **Similipal South Wildlife Division** (headquarters at Baripada).
     - Contains 8 constituent wildlife ranges: Barehipani, Chahala, Gurguria, Jenabil, Kendumundi, Nawana North, Talabandha, and Thakurmunda.

4. **Survey of India (SoI) / Bhuvan ISRO:**
   - **Portal Investigated:** `https://surveyofindia.gov.in` and `https://bhuvan.nrsc.gov.in` (WMS/WFS vector catalogue).
   - **Status:** Vector endpoints for sensitive protected area boundaries are restricted or require departmental authorization. Published open layers contain generalized district-level boundaries rather than compartment-level legal reserve vectors.

5. **UNEP-WCMC World Database on Protected Areas (WDPA) / Protected Planet:**
   - **Portal Investigated:** UNEP-WCMC Enterprise ArcGIS FeatureServer (`data-gis.unep-wcmc.org`), Layer 1 (`WDPA_poly_latest`).
   - **Status:** Contains the authoritative GIS polygon vector submitted and authenticated by the Ministry of Environment, Forest and Climate Change (MoEFCC), Government of India (updated 2026). This dataset directly provides the legal boundaries for Similipal Reserve Forest (Core Area) and its 7 constituent wildlife ranges.

---

## 2. Datasets Obtained

The following GIS layers and official source documents were retrieved and catalogued under `data/reference/boundaries/`:

### Original Preserved Data (`data/reference/boundaries/original/`)

| File Name | Format | Source Authority | Coordinate Reference System | Description |
| :--- | :--- | :--- | :--- | :--- |
| `Notification_Similipal.pdf` | PDF (9.54 MB) | NTCA / Govt of Odisha | Text / Metes & Bounds | Official legal gazette notification (Schedules A & B). |
| `wdpa_similipal_raw_4326.geojson` | GeoJSON (739 KB) | MoEFCC / UNEP-WCMC WDPA | `EPSG:4326` (WGS 84 geographic) | 11 official legal polygon features covering Similipal. |

### Processed Working Copies (`data/reference/boundaries/processed/`)

| File Name | Format | Coordinate Reference System | Entities Represented | Planar Area (`EPSG:32645`) |
| :--- | :--- | :--- | :--- | :--- |
| `similipal_core_epsg32645.geojson` | GeoJSON (210 KB) | `EPSG:32645` (UTM Zone 45N) | Similipal Core Area (Critical Tiger Habitat, WDPA Site ID `556167801`) | **$1,224.30\text{ km}^2$** |
| `similipal_sanctuary_epsg32645.geojson` | GeoJSON (678 KB) | `EPSG:32645` (UTM Zone 45N) | Dissolved unified Similipal Wildlife Sanctuary Complex | **$2,178.22\text{ km}^2$** |
| `similipal_ranges_epsg32645.geojson` | GeoJSON (748 KB) | `EPSG:32645` (UTM Zone 45N) | 7 constituent peripheral wildlife ranges + Core parcel | **$2,178.22\text{ km}^2$** |

---

## 3. Official vs. Secondary Boundary Distinctions

It is critical to distinguish between statutory gazette notifications, government GIS vector submissions, and secondary/approximate boundaries:

1. **Statutory Legal Gazetted Notifications (Primary Legal Authority):**
   - **Similipal Wildlife Sanctuary:** Notified on **03 December 1979** under Section 18 of the *Wildlife (Protection) Act, 1972* ($2,200.00\text{ km}^2$).
   - **Similipal Core Area (Critical Tiger Habitat):** Notified via Notification No. **8F(T)-13/2007-20807/F&E**, dated **31 December 2007**, under Section 38V of the *Wildlife (Protection) Act, 1972* ($1,194.75\text{ km}^2$).
   - **Similipal Tiger Reserve (Core + Buffer):** Notified via Notification No. **8F(T)-13/2012-16279/F&E**, dated **18 August 2012** ($2,750.00\text{ km}^2$: Core $1,194.75\text{ km}^2$, Buffer $1,555.25\text{ km}^2$).

2. **Official MoEFCC-Submitted WDPA GIS Vector (Statutory GIS Representation):**
   - Directly submitted by the Government of India MoEFCC to the United Nations Environment Programme (UNEP).
   - Core polygon measures **$1,224.30\text{ km}^2$** in UTM Zone 45N, representing a **$+2.47\%$** variance from the gazetted $1,194.75\text{ km}^2$ (attributable to planar projection distortion and geodesic watershed contour boundary delineation).
   - Unified Sanctuary vector measures **$2,178.22\text{ km}^2$**, representing a **$99.01\%$ match** ($-0.99\%$ variance) to the gazetted $2,200.00\text{ km}^2$.

3. **Secondary / Synthetic Approximations (Rejected):**
   - OpenStreetMap (OSM) relations and generic administrative bounding boxes which do not track forest compartment boundaries or gazetted CTH notification pillars were explicitly rejected.
   - The rectangular AOI ($4,123.09\text{ km}^2$) used in earlier phases is an engineering bounding box, not an official reserve boundary.

---

## 4. Geometry Validation Results

Every feature in the raw and processed GIS vector layers was systematically evaluated using `shapely`:
- **Topological Validity:** `geom.is_valid == True` for all 11 constituent features.
- **Empty Geometries:** Zero empty geometries detected (`geom.is_empty == False`).
- **Self-Intersections / Rings:** Zero ring self-intersections or duplicate consecutive vertices detected.
- **Winding Order:** Standard OGC exterior counter-clockwise and interior clockwise winding verified.
- **CRS Transformation:** Successfully reprojected from `EPSG:4326` to `EPSG:32645` using pyproj with standard high-precision geodetic transformation parameters.

---

## 5. Area Calculations

### Constituent Administrative Units (Planar UTM Zone 45N)

| Unit Name | WDPA Site ID | Legal Designation | Calculated GIS Area | Gazetted Area Reference |
| :--- | :--- | :--- | :--- | :--- |
| **Similipal Reserve Forest (Core Area)** | `556167801` | Critical Tiger Habitat | **$1,224.30\text{ km}^2$** | $1,194.75\text{ km}^2$ |
| **Kendumundi Wildlife Range** | `556167798` | Wildlife Sanctuary Range | **$186.33\text{ km}^2$** | Internal Range |
| **Gurguria Wildlife Range** | `556167800` | Wildlife Sanctuary Range | **$177.69\text{ km}^2$** | Internal Range |
| **Barehipani Wildlife Range** | `556167797` | Wildlife Sanctuary Range | **$153.05\text{ km}^2$** | Internal Range |
| **Talabandha Wildlife Range** | `556167795` | Wildlife Sanctuary Range | **$133.83\text{ km}^2$** | Internal Range |
| **Chahala Wildlife Range** | `556167804` | Wildlife Sanctuary Range | **$127.67\text{ km}^2$** | Internal Range |
| **Nawana North Wildlife Range (4 parcels)** | `556167794, 796, 799, 803` | Wildlife Sanctuary Range | **$100.34\text{ km}^2$** | Internal Range |
| **Thakurmunda Wildlife Range** | `556167802` | Wildlife Sanctuary Range | **$75.00\text{ km}^2$** | Internal Range |
| **Total Similipal Sanctuary Complex** | *Dissolved* | **Sanctuary (Core + 7 Ranges)** | **$2,178.22\text{ km}^2$** | **$2,200.00\text{ km}^2$** |

---

## 6. NISAR Coverage Calculations (Frequency A vs. Frequency B)

The rectangular engineering AOI spans $62.320\text{ km} \times 66.160\text{ km}$ ($4,123.09\text{ km}^2$), defined by UTM coordinates:
- Easting: $[401,600.0\text{ m}, 463,920.0\text{ m}]$
- Northing: $[2,372,240.0\text{ m}, 2,438,400.0\text{ m}]$

Rasterizing the verified reserve boundaries onto both NISAR observation grids (Track 098, Frame 012; March 4, 2026 vs. April 21, 2026) reveals the exact spatial coverage:

### Comparison Matrix

| Spatial Entity | Total Entity Area in AOI | Frequency B (80 m Grid) Observed | Frequency B Unobserved | Frequency A (10 m Grid) Observed | Frequency A Unobserved |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Similipal Core Area (CTH)** | $1,213.44\text{ km}^2$ | **$222.76\text{ km}^2$ ($18.36\%$)** | $990.80\text{ km}^2$ ($81.64\%$) | **$221.96\text{ km}^2$ ($18.29\%$)** | $991.77\text{ km}^2$ ($81.71\%$) |
| **Internal Wildlife Ranges (Buffer)** | $867.32\text{ km}^2$ | **$60.10\text{ km}^2$ ($6.93\%$)** | $807.48\text{ km}^2$ ($93.07\%$) | **$59.74\text{ km}^2$ ($6.88\%$)** | $808.03\text{ km}^2$ ($93.12\%$) |
| **Total Similipal Sanctuary** | $2,080.76\text{ km}^2$ | **$282.86\text{ km}^2$ ($13.59\%$)** | **$1,798.27\text{ km}^2$ ($86.41\%$)** | **$281.70\text{ km}^2$ ($13.53\%$)** | **$1,799.80\text{ km}^2$ ($86.47\%$)** |
| **Non-Reserve Landscape in AOI** | $2,042.33\text{ km}^2$ | **$980.41\text{ km}^2$ ($48.01\%$)** | $1,061.92\text{ km}^2$ ($51.99\%$) | **$978.76\text{ km}^2$ ($47.92\%$)** | $1,063.57\text{ km}^2$ ($52.08\%$) |
| **Total Rectangular AOI** | $4,123.09\text{ km}^2$ | **$1,263.27\text{ km}^2$ ($30.64\%$)** | $2,859.82\text{ km}^2$ ($69.36\%$) | **$1,260.46\text{ km}^2$ ($30.57\%$)** | $2,862.63\text{ km}^2$ ($69.43\%$) |

### Swath Composition Breakdown

Of the valid radar swath imaged by NISAR Track 098 Frame 012 ($1,263.27\text{ km}^2$ at 80 m, $1,260.46\text{ km}^2$ at 10 m):
- **$77.61\%$ to $77.65\%$ ($978.8\text{ km}^2$ to $980.4\text{ km}^2$)** falls outside the Similipal Wildlife Sanctuary in Mayurbhanj agricultural plains and rural settlements.
- **Only $22.35\%$ to $22.39\%$ ($281.7\text{ km}^2$ to $282.9\text{ km}^2$)** falls inside the protected Similipal Sanctuary Complex.
- **Only $17.61\%$ to $17.63\%$ ($222.0\text{ km}^2$ to $222.8\text{ km}^2$)** falls inside the Core Critical Tiger Habitat.

---

## 7. Data Limitations

1. **Massive Coverage Blind Spot for Track 098:**
   - Because Track 098 Frame 012 is a descending orbit swath with its eastern edge terminating at Easting $\approx 434,120\text{ m}$, **$86.41\%$ to $86.47\%$ of Similipal Wildlife Sanctuary is completely unobserved**.
   - Whole-reserve forest monitoring or carbon loss estimations cannot be derived from this single track alone.
2. **Outer Buffer Zone Delineation:**
   - The notified $1,555.25\text{ km}^2$ outer buffer zone extends beyond the sanctuary into surrounding revenue forest blocks across Baripada, Karanjia, and Rairangpur territorial divisions. While the text description of the outer boundary exists in Schedule B of the NTCA notification, a single unified authoritative GIS polygon for the outer territorial revenue forest boundary is not publicly disseminated as an open vector dataset.
3. **Previous Disturbance Metric Misattribution:**
   - The reported $68.5\text{ ha}$ of forest disturbance in the baseline detector was computed across the full rectangular AOI swath. Because $77.7\%$ of that swath covers non-reserve agricultural land, rural crop cycles and private fallow clearing were erroneously mixed with forest canopy dynamics.

---

## 8. Recommended Boundaries for Subsequent Analysis

For all subsequent Phase 4 analytical workflows, disturbance detection, and validation:

1. **Primary Analysis Mask (Core Area / Critical Tiger Habitat):**
   - Use `data/reference/boundaries/processed/similipal_core_epsg32645.geojson`.
   - Represents the strictly protected, legally inviolable tiger habitat ($1,194.75\text{ km}^2$ notified, $1,224.30\text{ km}^2$ GIS).
   - Observed area under Track 098: **$222.00\text{ km}^2$**.

2. **Secondary Analysis Mask (Similipal Wildlife Sanctuary Complex):**
   - Use `data/reference/boundaries/processed/similipal_sanctuary_epsg32645.geojson`.
   - Represents the complete ecological sanctuary complex ($2,200.00\text{ km}^2$ notified, $2,178.22\text{ km}^2$ GIS).
   - Observed area under Track 098: **$281.72\text{ km}^2$**.

3. **External Control Mask (Non-Reserve Rural Landscape):**
   - Retain the inverted sanctuary mask over the valid swath ($980.41\text{ km}^2$) strictly as an external negative control / agricultural sensitivity baseline.

---

## 9. Verification & Test Suite Integrity

The entire analysis was conducted strictly preserving raw satellite data and existing outputs:
- **Pytest Suite:** 28/28 tests passing (`pytest backend/tests/ -v`).
- **Visual Artifact:** Generated high-resolution 6-panel diagnostic map: `data/processed/boundary_analysis/similipal_boundary_comparison_map.png` (incorporating scale bars, North arrows, legends, and `EPSG:32645` CRS annotations).
- **Statistical JSON:** `data/processed/boundary_analysis/boundary_coverage_statistics.json`.
