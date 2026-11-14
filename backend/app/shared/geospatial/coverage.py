from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from shapely.geometry import box, shape, Polygon, MultiPolygon

from app.shared.geospatial.aoi import AreaOfInterest
from app.shared.geospatial.bbox import BoundingBox
from app.shared.geospatial.transform import PyprojGeoTransformer


class CoverageStatus(str, Enum):
    FULL_COVERAGE = "FULL_COVERAGE"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    NO_COVERAGE = "NO_COVERAGE"


@dataclass
class SwathDefinition:
    """Satellite orbit pass or sensor footprint definition."""
    swath_id: str
    mission: str
    track: int
    frame: int
    description: str
    geometry_wgs84: Polygon
    observation_count: int = 0
    acquisition_dates: List[str] = field(default_factory=list)
    polarizations: List[str] = field(default_factory=list)
    native_spacing_m: float = 10.0


# Authentic local NISAR Track 098 Frame 012 footprint
# Derived from GCOV UTM bounds: X: 410000 - 450000, Y: 2380000 - 2400690 in UTM 45N
_transformer = PyprojGeoTransformer()
_nisar_track98_utm = box(410000.0, 2380000.0, 450000.0, 2400690.0)
_nisar_track98_wgs84 = _transformer.reproject_geometry(
    _nisar_track98_utm, source_crs="EPSG:32645", target_crs="EPSG:4326"
)

AUTHENTIC_NISAR_SWATHS: Dict[str, SwathDefinition] = {
    "NISAR_T098_F012": SwathDefinition(
        swath_id="NISAR_T098_F012",
        mission="NISAR",
        track=98,
        frame=12,
        description="Authentic NASA-ISRO NISAR L2 GCOV (Oct 2024 / Nov 2024) descending pass",
        geometry_wgs84=_nisar_track98_wgs84,
        observation_count=2,
        acquisition_dates=["2024-10-22T00:19:27", "2024-11-15T00:19:26"],
        polarizations=["HHHH", "HVHV"],
        native_spacing_m=10.0,
    )
}


@dataclass
class CoverageAssessment:
    """Rigorous evaluation of satellite observation coverage over a user AOI."""
    aoi_id: str
    mission: str
    swath_id: Optional[str]
    coverage_status: CoverageStatus
    aoi_area_km2: float
    covered_area_km2: float
    overlap_percentage: float
    available_observations: int
    observation_dates: List[str]
    missing_coverage_km2: float
    scientific_notice: str
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aoi_id": self.aoi_id,
            "mission": self.mission,
            "swath_id": self.swath_id,
            "coverage_status": self.coverage_status.value,
            "aoi_area_km2": round(self.aoi_area_km2, 2),
            "covered_area_km2": round(self.covered_area_km2, 2),
            "overlap_percentage": round(self.overlap_percentage, 2),
            "available_observations": self.available_observations,
            "observation_dates": self.observation_dates,
            "missing_coverage_km2": round(self.missing_coverage_km2, 2),
            "scientific_notice": self.scientific_notice,
            "recommendations": self.recommendations,
        }


class ObservationCoverageChecker:
    """Evaluates spatial overlap between arbitrary user AOIs and satellite coverage."""

    def __init__(self, swaths: Optional[Dict[str, SwathDefinition]] = None) -> None:
        self.swaths = swaths or AUTHENTIC_NISAR_SWATHS
        self._transformer = PyprojGeoTransformer()

    def evaluate_aoi_coverage(
        self,
        aoi: AreaOfInterest,
        swath_id: str = "NISAR_T098_F012",
    ) -> CoverageAssessment:
        """Check intersection of AOI with given satellite swath."""
        swath = self.swaths.get(swath_id)
        aoi_geom = aoi.shapely_geometry

        if swath is None:
            return CoverageAssessment(
                aoi_id=aoi.aoi_id,
                mission="UNKNOWN",
                swath_id=None,
                coverage_status=CoverageStatus.NO_COVERAGE,
                aoi_area_km2=aoi.area_km2,
                covered_area_km2=0.0,
                overlap_percentage=0.0,
                available_observations=0,
                observation_dates=[],
                missing_coverage_km2=aoi.area_km2,
                scientific_notice=f"Unknown or uncatalogued satellite swath '{swath_id}'.",
                recommendations=["Query satellite catalogue for available overpasses in this region."],
            )

        # Compute intersection in WGS84
        if not aoi_geom.intersects(swath.geometry_wgs84):
            return CoverageAssessment(
                aoi_id=aoi.aoi_id,
                mission=swath.mission,
                swath_id=swath.swath_id,
                coverage_status=CoverageStatus.NO_COVERAGE,
                aoi_area_km2=aoi.area_km2,
                covered_area_km2=0.0,
                overlap_percentage=0.0,
                available_observations=0,
                observation_dates=[],
                missing_coverage_km2=aoi.area_km2,
                scientific_notice=(
                    f"AOI '{aoi.name}' lies completely outside {swath.mission} swath {swath.swath_id}. "
                    "Zero observations are available in the local repository."
                ),
                recommendations=[
                    "Acquire additional satellite orbit passes covering this coordinate box.",
                    "Switch to Sentinel-2 or Sentinel-1 for wide-swath Indian regional monitoring.",
                ],
            )

        inter_geom = aoi_geom.intersection(swath.geometry_wgs84)
        inter_area_km2 = self._transformer.compute_projected_area_km2(inter_geom, crs="EPSG:4326")
        overlap_pct = min(100.0, (inter_area_km2 / aoi.area_km2) * 100.0)
        missing_km2 = max(0.0, aoi.area_km2 - inter_area_km2)

        if overlap_pct >= 95.0:
            status = CoverageStatus.FULL_COVERAGE
            notice = f"AOI has complete ({overlap_pct:.1f}%) coverage by {swath.swath_id}."
            recommendations = ["Proceed with multi-temporal change detection and feature extraction."]
        else:
            status = CoverageStatus.PARTIAL_COVERAGE
            notice = (
                f"AOI has partial ({overlap_pct:.1f}%) coverage by {swath.swath_id}. "
                f"{missing_km2:.1f} km² remain outside swath boundaries."
            )
            recommendations = [
                "Clip analysis to the valid intersection footprint to avoid boundary artifacts.",
                "Acquire adjacent track/frame data to achieve seamless composite coverage.",
            ]

        return CoverageAssessment(
            aoi_id=aoi.aoi_id,
            mission=swath.mission,
            swath_id=swath.swath_id,
            coverage_status=status,
            aoi_area_km2=aoi.area_km2,
            covered_area_km2=inter_area_km2,
            overlap_percentage=overlap_pct,
            available_observations=swath.observation_count,
            observation_dates=swath.acquisition_dates,
            missing_coverage_km2=missing_km2,
            scientific_notice=notice,
            recommendations=recommendations,
        )


# Global singleton instance
coverage_checker = ObservationCoverageChecker()
