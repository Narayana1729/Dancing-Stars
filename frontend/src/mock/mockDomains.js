// MOCK / ILLUSTRATIVE DATA ONLY.
// Nothing here was computed by this platform. Images, dates and statistics are
// hand-entered placeholders and have NOT been verified against source products.
// Replace with API responses once the backend analysis pipeline exists.
export const domainsData = {
  floods: {
    title: "Floods & Wetlands",
    subtitle: "All-weather inundation mapping using L-band/S-band SAR backscatter.",
    regions: [
      {
        id: "mozambique_chokwe",
        name: "Chókwè Basin (Mozambique)",
        dataSource: "NISAR L-band False-Color Composite (HH/HV/Ratio)",
        beforeDate: "Pre Flood\nJan. 5th, 2026",
        afterDate: "Active Flood\nJan. 17th, 2026",
        locationLabel: "Chókwè",
        impactStats: {
          metricLabel: "Inundated Extent",
          metricValue: "450 km²",
          secondaryLabel: "Displaced Risk",
          secondaryValue: "600,000+ affected",
        },
        confidence: "High",
        // Direct high-res NASA SVS 5661 frames for Chokwe / Mozambique
        beforeImg: "https://svs.gsfc.nasa.gov/vis/a000000/a005600/a005661/Pre_Chokwe.png",
        afterImg: "https://svs.gsfc.nasa.gov/vis/a000000/a005600/a005661/Post_Chokwe.png",
      },
      {
        id: "mozambique_macia",
        name: "Macia & Xai-Xai Basins (Mozambique)",
        dataSource: "NISAR L-band False-Color Composite (HH/HV/Ratio)",
        beforeDate: "Pre Flood\nJan. 5th, 2026",
        afterDate: "Active Flood\nJan. 17th, 2026",
        locationLabel: "Macia",
        impactStats: {
          metricLabel: "Basin Overflow Area",
          metricValue: "320 km²",
          secondaryLabel: "Cropland Impact",
          secondaryValue: "400,000 acres",
        },
        confidence: "High",
        // Direct high-res NASA SVS 5661 frames for Macia
        beforeImg: "https://svs.gsfc.nasa.gov/vis/a000000/a005600/a005661/Pre_Macia.png",
        afterImg: "https://svs.gsfc.nasa.gov/vis/a000000/a005600/a005661/Post_Macia.png",
      },
    ],
  },
  forests: {
    title: "Forests & Wildfires",
    subtitle: "Calibrated multi-temporal volume scattering analysis for canopy disturbance.",
    regions: [
      {
        id: "similipal_india",
        name: "Similipal Tiger Reserve (Odisha, India) — AUTHENTIC NISAR",
        dataSource: "NISAR L2 GCOV (Track 098 / Frame 012 / Dual-Pol HH+HV / 80m Grid)",
        beforeDate: "Pre-Season Baseline (t₀)\nMarch 04, 2026",
        afterDate: "Peak Dry Season (t₁)\nApril 21, 2026",
        locationLabel: "Similipal Core & Buffer (UTM Zone 45N)",
        impactStats: {
          metricLabel: "Candidate Radiometric Drop (Unvalidated)",
          metricValue: "68.5 ha (0.68 km²)",
          secondaryLabel: "Forest Monitored",
          secondaryValue: "297.7 km² (46,515 px)",
        },
        confidence: "Experimental (Candidate Statistical Change; Not Ground-Validated)",
        beforeImg: "/india_similipal_multitemporal_comparison.png",
        afterImg: "/india_similipal_forest_disturbance_analysis.png",
      },
      {
        id: "indonesia_forest",
        name: "Mount Rinjani Ecosystem (Indonesia) — Demo Placeholder",
        dataSource: "NISAR S-band GCOV (HH+HV Polarimetric Composite)",
        beforeDate: "Pre-Disturbance\nDec. 12, 2025",
        afterDate: "Post-Wildfire\nJan. 14, 2026",
        locationLabel: "Rinjani Sector",
        impactStats: {
          metricLabel: "Canopy Volume Shift",
          metricValue: "~18.4 km² loss",
          secondaryLabel: "Scattering Change",
          secondaryValue: "Volume to Surface Bounce",
        },
        confidence: "Demo Mock",
        beforeImg: "https://www.isro.gov.in/media_isro/image/NISAR/NISAR_S2_PR_GCOV_025_024_A_173_3700_DHNA_A_20260709T215709_20260709T215746_P00500_M_F_I_001.png",
        afterImg: "https://www.isro.gov.in/media_isro/image/NISAR/NISAR_S2_PR_GCOV_025_024_A_173_3700_DHNA_A_20260709T215709_20260709T215746_P00500_M_F_I_001.png",
      },
    ],
  },
  agriculture: {
    title: "Soil Moisture & Agriculture",
    subtitle: "High-resolution field-level backscatter and dielectric constant tracking.",
    regions: [
      {
        id: "idaho_agri",
        name: "Burley Agricultural Region (Idaho, USA)",
        dataSource: "NISAR S-SAR HH+HV False-Color Composite",
        beforeDate: "Pre-Harvest\nMay 01, 2026",
        afterDate: "Post-Irrigation\nMay 15, 2026",
        locationLabel: "Sector 7-B",
        impactStats: {
          metricLabel: "Surface Moisture Proxy",
          metricValue: "-28% dielectric shift",
          secondaryLabel: "Field Boundary Definition",
          secondaryValue: "100% vector aligned",
        },
        confidence: "High",
        beforeImg: "https://www.isro.gov.in/media_isro/image/NISAR/NISAR_S2_PR_GCOV_025_013_D_067_3700_DHNA_A_20260709T023820_20260709T023857_P00500_M_F_I_001.png",
        afterImg: "https://www.isro.gov.in/media_isro/image/NISAR/NISAR_S2_PR_GCOV_025_013_D_067_3700_DHNA_A_20260709T023820_20260709T023857_P00500_M_F_I_001.png",
      },
    ],
  },
};
