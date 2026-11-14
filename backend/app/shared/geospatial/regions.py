from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.shared.geospatial.aoi import AreaOfInterest
from app.shared.geospatial.bbox import BoundingBox


@dataclass
class RegionMetadata:
    """Authoritative metadata and spatial bounds for an Indian monitoring region."""
    region_id: str
    name: str
    state: str
    biome: str
    utm_zone: int
    utm_crs: str
    area_km2: float
    bbox: BoundingBox
    center_coordinates: Dict[str, float]
    geometry: Dict[str, Any]
    is_predefined: bool = True
    is_validated_case_study: bool = False
    country: str = "India"
    description: str = ""
    default_pixel_size_m: float = 80.0
    recommended_satellite: str = "NISAR / Sentinel-2"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "region_id": self.region_id,
            "name": self.name,
            "state": self.state,
            "country": self.country,
            "biome": self.biome,
            "utm_zone": self.utm_zone,
            "utm_crs": self.utm_crs,
            "area_km2": round(self.area_km2, 2),
            "bbox": self.bbox.to_dict(),
            "center_coordinates": self.center_coordinates,
            "is_predefined": self.is_predefined,
            "is_validated_case_study": self.is_validated_case_study,
            "description": self.description,
            "default_pixel_size_m": self.default_pixel_size_m,
            "recommended_satellite": self.recommended_satellite,
            "geometry": self.geometry,
        }

    def to_summary(self) -> Dict[str, Any]:
        """Compact summary excluding large geometry coordinates."""
        d = self.to_dict()
        del d["geometry"]
        return d


class RegionRegistry:
    """In-memory registry of predefined Indian conservation regions and custom user AOIs."""

    def __init__(self) -> None:
        self._regions: Dict[str, RegionMetadata] = {}
        self._initialize_predefined_regions()

    def _initialize_predefined_regions(self) -> None:
        """Register primary conservation biomes across India."""
        # 1. Similipal Tiger Reserve & Wildlife Sanctuary (Primary Validated Case Study)
        similipal_bbox = BoundingBox(west=86.15, south=21.45, east=86.70, north=22.15)
        self._regions["similipal"] = RegionMetadata(
            region_id="similipal",
            name="Similipal Tiger Reserve & Wildlife Sanctuary",
            state="Odisha",
            biome="Tropical Moist & Dry Deciduous Forest (Sal Dominant)",
            utm_zone=45,
            utm_crs="EPSG:32645",
            area_km2=2750.0,
            bbox=similipal_bbox,
            center_coordinates={"latitude": 21.75, "longitude": 86.35},
            geometry=similipal_bbox.to_geojson(),
            is_predefined=True,
            is_validated_case_study=True,
            description="Initial validated case study featuring 2-date NISAR L2 GCOV and Sentinel-2 optical corroboration.",
            recommended_satellite="NISAR Track 098 Frame 012 / Sentinel-2 Tile 45QUU",
        )

        # 2. Sundarbans Biosphere Reserve
        sundarbans_bbox = BoundingBox(west=88.00, south=21.50, east=89.15, north=22.50)
        self._regions["sundarbans"] = RegionMetadata(
            region_id="sundarbans",
            name="Sundarbans Biosphere Reserve & National Park",
            state="West Bengal",
            biome="Littoral Mangrove Swamp & Estuarine Forest",
            utm_zone=45,
            utm_crs="EPSG:32645",
            area_km2=2585.0,
            bbox=sundarbans_bbox,
            center_coordinates={"latitude": 21.95, "longitude": 88.85},
            geometry=sundarbans_bbox.to_geojson(),
            is_predefined=True,
            is_validated_case_study=False,
            description="World heritage tidal halophytic mangrove forest along the Ganges-Brahmaputra Delta.",
            recommended_satellite="NISAR L-band / Sentinel-1 / Sentinel-2",
        )

        # 3. Jim Corbett National Park
        corbett_bbox = BoundingBox(west=78.70, south=29.40, east=79.25, north=29.80)
        self._regions["corbett"] = RegionMetadata(
            region_id="corbett",
            name="Jim Corbett National Park",
            state="Uttarakhand",
            biome="Sub-Himalayan Shivalik Foothills / Sal & Riverine Forest",
            utm_zone=44,
            utm_crs="EPSG:32644",
            area_km2=1318.5,
            bbox=corbett_bbox,
            center_coordinates={"latitude": 29.53, "longitude": 78.96},
            geometry=corbett_bbox.to_geojson(),
            is_predefined=True,
            is_validated_case_study=False,
            description="Sub-Himalayan belt with dense deciduous sal forests and complex topography.",
            recommended_satellite="NISAR L-band (descending) / Sentinel-2",
        )

        # 4. Kaziranga National Park
        kaziranga_bbox = BoundingBox(west=92.95, south=26.50, east=93.75, north=26.85)
        self._regions["kaziranga"] = RegionMetadata(
            region_id="kaziranga",
            name="Kaziranga National Park",
            state="Assam",
            biome="Brahmaputra Alluvial Plains / Semi-Evergreen & Tall Grassland",
            utm_zone=46,
            utm_crs="EPSG:32646",
            area_km2=858.0,
            bbox=kaziranga_bbox,
            center_coordinates={"latitude": 26.67, "longitude": 93.35},
            geometry=kaziranga_bbox.to_geojson(),
            is_predefined=True,
            is_validated_case_study=False,
            description="Eastern Himalayan biodiversity hotspot with fertile alluvial floodplain forests.",
            recommended_satellite="NISAR L-band / ALOS-2 PALSAR-2",
        )

        # 5. Kanha Tiger Reserve
        kanha_bbox = BoundingBox(west=80.35, south=22.05, east=81.15, north=22.50)
        self._regions["kanha"] = RegionMetadata(
            region_id="kanha",
            name="Kanha Tiger Reserve",
            state="Madhya Pradesh",
            biome="Central Indian Highlands / Moist & Dry Deciduous",
            utm_zone=44,
            utm_crs="EPSG:32644",
            area_km2=940.0,
            bbox=kanha_bbox,
            center_coordinates={"latitude": 22.28, "longitude": 80.75},
            geometry=kanha_bbox.to_geojson(),
            is_predefined=True,
            is_validated_case_study=False,
            description="Maikal range of the Satpuras with dense sal and bamboo forests.",
            recommended_satellite="NISAR L-band / Sentinel-2",
        )

        # 6. Wayanad Wildlife Sanctuary / Nilgiri Biosphere
        wayanad_bbox = BoundingBox(west=76.10, south=11.60, east=76.50, north=11.95)
        self._regions["wayanad"] = RegionMetadata(
            region_id="wayanad",
            name="Wayanad Wildlife Sanctuary",
            state="Kerala",
            biome="Western Ghats Moist Deciduous & Semi-Evergreen",
            utm_zone=43,
            utm_crs="EPSG:32643",
            area_km2=344.4,
            bbox=wayanad_bbox,
            center_coordinates={"latitude": 11.75, "longitude": 76.30},
            geometry=wayanad_bbox.to_geojson(),
            is_predefined=True,
            is_validated_case_study=False,
            description="Southern Western Ghats moist montane and deciduous forest corridor.",
            recommended_satellite="NISAR L-band / Sentinel-2",
        )

    def get_region(self, region_id: str) -> Optional[RegionMetadata]:
        """Retrieve region by identifier."""
        return self._regions.get(region_id.lower().strip())

    def list_regions(self, include_predefined: bool = True, include_custom: bool = True) -> List[Dict[str, Any]]:
        """List all registered regions matching filter."""
        results = []
        for reg in self._regions.values():
            if reg.is_predefined and not include_predefined:
                continue
            if not reg.is_predefined and not include_custom:
                continue
            results.append(reg.to_summary())
        return results

    def register_custom_aoi(
        self,
        aoi: AreaOfInterest,
        region_id: Optional[str] = None,
        state: str = "Custom Location",
        biome: str = "User Defined Biome",
    ) -> RegionMetadata:
        """Register a user-defined custom AOI as an active region."""
        rid = (region_id or aoi.aoi_id).lower().strip()
        meta = RegionMetadata(
            region_id=rid,
            name=aoi.name,
            state=state,
            biome=biome,
            utm_zone=aoi.utm_zone,
            utm_crs=aoi.utm_crs,
            area_km2=aoi.area_km2,
            bbox=aoi.bbox,
            center_coordinates={"latitude": aoi.centroid[1], "longitude": aoi.centroid[0]},
            geometry=aoi.geometry_geojson,
            is_predefined=False,
            is_validated_case_study=False,
            description=aoi.description or "User-defined custom polygon AOI in India.",
        )
        self._regions[rid] = meta
        return meta

    def remove_custom_region(self, region_id: str) -> bool:
        """Remove a custom region by ID. Predefined regions cannot be removed."""
        rid = region_id.lower().strip()
        reg = self._regions.get(rid)
        if reg is None:
            return False
        if reg.is_predefined:
            raise ValueError(f"Cannot delete predefined region '{region_id}'.")
        del self._regions[rid]
        return True


# Global singleton instance
region_registry = RegionRegistry()
