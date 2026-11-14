from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import box, shape, Polygon

from app.shared.geospatial.aoi import AreaOfInterest
from app.shared.geospatial.bbox import BoundingBox
from app.shared.geospatial.transform import PyprojGeoTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "data"
NISAR_CATALOG_FILE = DATA_DIR / "reference" / "nisar_catalogue" / "nisar_similipal_full_catalog.json"
S2_CATALOG_FILE = DATA_DIR / "reference" / "sentinel2_catalogue" / "sentinel2_similipal_full_catalog.json"


@dataclass
class CatalogueQuery:
    """Multi-sensor satellite imagery search query."""
    bbox: Optional[BoundingBox] = None
    geometry: Optional[Dict[str, Any]] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    missions: List[str] = field(default_factory=lambda: ["NISAR", "SENTINEL-2"])
    max_cloud_cover_percent: Optional[float] = 30.0
    polarizations: Optional[List[str]] = None
    limit: int = 50


@dataclass
class CatalogueItem:
    """Unified metadata record for a satellite observation granule."""
    granule_id: str
    mission: str
    product_type: str
    sensor_type: str  # "SAR" or "OPTICAL"
    acquisition_date: str
    acquisition_time_utc: Optional[str] = None
    cloud_cover_percent: Optional[float] = None
    polarizations: List[str] = field(default_factory=list)
    track: Optional[int] = None
    frame: Optional[int] = None
    relative_orbit: Optional[str] = None
    mgrs_tile: Optional[str] = None
    footprint_wgs84: Optional[Dict[str, Any]] = None
    overlap_percent: float = 0.0
    is_locally_available: bool = False
    local_file_path: Optional[str] = None
    download_url: Optional[str] = None
    size_mb: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SatelliteCatalogueService:
    """Multi-mission satellite catalogue supporting spatial polygon and temporal queries."""

    def __init__(self) -> None:
        self._transformer = PyprojGeoTransformer()
        self._local_granules_index: Dict[str, str] = {}
        self._index_local_files()

    def _index_local_files(self) -> None:
        """Index raw and processed satellite data files present on disk."""
        raw_dir = DATA_DIR / "raw"
        if raw_dir.exists():
            for h5 in raw_dir.rglob("*.h5"):
                stem = h5.stem
                self._local_granules_index[stem] = str(h5)
                # Also index scene IDs parsed from standard naming
                self._local_granules_index[h5.name] = str(h5)

    def search(self, query: CatalogueQuery) -> List[CatalogueItem]:
        """Search available granules matching spatial geometry, dates, and missions."""
        results: List[CatalogueItem] = []

        # Determine target search geometry
        search_geom: Optional[Polygon] = None
        aoi_area_km2 = 1.0
        if query.geometry:
            search_geom = shape(query.geometry)
            aoi_area_km2 = max(0.01, self._transformer.compute_projected_area_km2(search_geom, crs="EPSG:4326"))
        elif query.bbox:
            search_geom = query.bbox.to_polygon()
            aoi_area_km2 = max(0.01, self._transformer.compute_projected_area_km2(search_geom, crs="EPSG:4326"))

        # 1. Search NISAR Catalog
        if "NISAR" in query.missions and NISAR_CATALOG_FILE.exists():
            results.extend(self._search_nisar_catalog(query, search_geom, aoi_area_km2))

        # 2. Search Sentinel-2 Catalog
        if "SENTINEL-2" in query.missions and S2_CATALOG_FILE.exists():
            results.extend(self._search_sentinel2_catalog(query, search_geom, aoi_area_km2))

        # Sort results by acquisition date descending
        results.sort(key=lambda item: item.acquisition_date, reverse=True)
        return results[: query.limit]

    def _search_nisar_catalog(
        self,
        query: CatalogueQuery,
        search_geom: Optional[Polygon],
        aoi_area_km2: float,
    ) -> List[CatalogueItem]:
        items: List[CatalogueItem] = []
        try:
            with open(NISAR_CATALOG_FILE, "r") as f:
                entries = json.load(f)
        except Exception:
            return items

        # Similipal NISAR Track 098 Frame 012 standard geographic footprint
        # Approx: 86.15 to 86.60 E, 21.50 to 21.80 N
        track98_geom = box(86.15, 21.50, 86.60, 21.80)

        for entry in entries:
            acq_str = entry.get("acquisition_date")
            if not acq_str:
                continue
            acq_dt = date.fromisoformat(acq_str)

            # Date filtering
            if query.start_date and acq_dt < query.start_date:
                continue
            if query.end_date and acq_dt > query.end_date:
                continue

            scene_id = entry.get("scene_id", "")
            h5_name = entry.get("h5_file_name", "")
            is_local = (scene_id in self._local_granules_index) or (h5_name in self._local_granules_index)
            local_path = self._local_granules_index.get(scene_id) or self._local_granules_index.get(h5_name)

            # Spatial overlap calculation
            overlap_pct = entry.get("aoi_coverage_percent", 0.0)
            footprint_geom = track98_geom
            if search_geom is not None:
                if search_geom.intersects(footprint_geom):
                    inter = search_geom.intersection(footprint_geom)
                    inter_km2 = self._transformer.compute_projected_area_km2(inter, crs="EPSG:4326")
                    overlap_pct = min(100.0, (inter_km2 / aoi_area_km2) * 100.0)
                else:
                    overlap_pct = 0.0
                    # Skip if spatial geometry specified and strictly zero overlap
                    continue

            size_mb = round(entry.get("h5_size_bytes", 0) / (1024 * 1024), 2) if entry.get("h5_size_bytes") else None

            item = CatalogueItem(
                granule_id=scene_id,
                mission="NISAR",
                product_type="GCOV",
                sensor_type="SAR",
                acquisition_date=acq_str,
                acquisition_time_utc=entry.get("start_time", "").replace("Z", "").split("T")[-1] if "T" in entry.get("start_time", "") else None,
                cloud_cover_percent=None,
                polarizations=["HH", "HV"],
                track=entry.get("track"),
                frame=entry.get("frame"),
                relative_orbit=str(entry.get("track")),
                footprint_wgs84=BoundingBox(west=86.15, south=21.50, east=86.60, north=21.80).to_geojson(),
                overlap_percent=round(overlap_pct, 2),
                is_locally_available=is_local,
                local_file_path=local_path,
                download_url=entry.get("download_url"),
                size_mb=size_mb,
                extra={
                    "orbit_direction": entry.get("orbit_direction"),
                    "cycle_number": entry.get("cycle_number"),
                    "crid": entry.get("crid"),
                    "frequency_bands": entry.get("frequency_bands"),
                    "is_workspace_baseline": entry.get("is_workspace_baseline", False),
                },
            )
            items.append(item)

        return items

    def _search_sentinel2_catalog(
        self,
        query: CatalogueQuery,
        search_geom: Optional[Polygon],
        aoi_area_km2: float,
    ) -> List[CatalogueItem]:
        items: List[CatalogueItem] = []
        try:
            with open(S2_CATALOG_FILE, "r") as f:
                entries = json.load(f)
        except Exception:
            return items

        # MGRS Tile footprint approximation (T45QVD / T45QVE over Odisha)
        # Approx: 86.0 to 87.0 E, 21.0 to 22.0 N
        s2_geom = box(86.0, 21.0, 87.0, 22.0)

        for entry in entries:
            acq_str = entry.get("acquisition_date")
            if not acq_str:
                continue
            acq_dt = date.fromisoformat(acq_str)

            # Date filtering
            if query.start_date and acq_dt < query.start_date:
                continue
            if query.end_date and acq_dt > query.end_date:
                continue

            # Cloud cover filter
            cloud_pct = float(entry.get("cloud_cover_percent", 0.0))
            if query.max_cloud_cover_percent is not None and cloud_pct > query.max_cloud_cover_percent:
                continue

            prod_id = entry.get("product_id", "")
            overlap_pct = entry.get("aoi_coverage_percent", 0.0)

            if search_geom is not None:
                if search_geom.intersects(s2_geom):
                    inter = search_geom.intersection(s2_geom)
                    inter_km2 = self._transformer.compute_projected_area_km2(inter, crs="EPSG:4326")
                    overlap_pct = min(100.0, (inter_km2 / aoi_area_km2) * 100.0)
                else:
                    overlap_pct = 0.0
                    continue

            size_mb = round(entry.get("product_size_bytes", 0) / (1024 * 1024), 2) if entry.get("product_size_bytes") else None

            item = CatalogueItem(
                granule_id=prod_id,
                mission="SENTINEL-2",
                product_type="L2A",
                sensor_type="OPTICAL",
                acquisition_date=acq_str,
                acquisition_time_utc=entry.get("acquisition_time_utc"),
                cloud_cover_percent=cloud_pct,
                polarizations=[],
                mgrs_tile=entry.get("mgrs_tile"),
                relative_orbit=entry.get("relative_orbit"),
                footprint_wgs84=BoundingBox(west=86.0, south=21.0, east=87.0, north=22.0).to_geojson(),
                overlap_percent=round(overlap_pct, 2),
                is_locally_available=False,
                download_url=entry.get("download_url"),
                size_mb=size_mb,
                extra={
                    "satellite": entry.get("satellite"),
                    "suitability": entry.get("suitability"),
                    "bands_available": entry.get("bands_available"),
                    "indices_supported": entry.get("indices_supported"),
                },
            )
            items.append(item)

        return items


# Global singleton instance
catalogue_service = SatelliteCatalogueService()
