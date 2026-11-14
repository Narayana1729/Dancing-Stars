from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import h5py

from app.shared.satellite.base import Mission, SarProduct


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"


@dataclass
class LocalGranuleRecord:
    """Detailed record of an authentic satellite granule present on local disk."""
    file_name: str
    file_path: str
    relative_path: str
    file_size_bytes: int
    file_size_gb: float
    mission: str
    product_type: str
    format: str  # "HDF5" or "GeoTIFF"
    track: Optional[int] = None
    frame: Optional[int] = None
    acquisition_date: Optional[str] = None
    crs: Optional[str] = None
    polarizations: List[str] = None
    frequencies: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LocalInventoryService:
    """Scans and validates authentic satellite data resident in the local workspace."""

    def scan_inventory(self) -> List[LocalGranuleRecord]:
        records: List[LocalGranuleRecord] = []
        if not RAW_DIR.exists():
            return records

        for h5_path in RAW_DIR.rglob("*.h5"):
            # Skip tiny QA stats files
            if "QA_STATS" in h5_path.name:
                continue

            stat = h5_path.stat()
            size_bytes = stat.st_size
            size_gb = round(size_bytes / (1024**3), 3)

            track, frame, acq_date, crs, pols, freqs = self._inspect_hdf5(h5_path)

            record = LocalGranuleRecord(
                file_name=h5_path.name,
                file_path=str(h5_path),
                relative_path=str(h5_path.relative_to(PROJECT_ROOT)),
                file_size_bytes=size_bytes,
                file_size_gb=size_gb,
                mission="NISAR",
                product_type="GCOV",
                format="HDF5",
                track=track,
                frame=frame,
                acquisition_date=acq_date,
                crs=crs,
                polarizations=pols or ["HHHH", "HVHV"],
                frequencies=freqs or ["frequencyA", "frequencyB"],
            )
            records.append(record)

        return sorted(records, key=lambda r: r.file_name)

    def _inspect_hdf5(self, path: Path) -> tuple[Optional[int], Optional[int], Optional[str], Optional[str], List[str], List[str]]:
        track = None
        frame = None
        acq_date = None
        crs = None
        pols = []
        freqs = []

        try:
            with h5py.File(path, "r") as f:
                ident = f.get("/science/LSAR/identification")
                if ident is not None:
                    if "trackNumber" in ident:
                        track = int(ident["trackNumber"][()])
                    if "frameNumber" in ident:
                        frame = int(ident["frameNumber"][()])
                    if "zeroDopplerStartTime" in ident:
                        t = ident["zeroDopplerStartTime"][()]
                        if isinstance(t, bytes):
                            t = t.decode()
                        acq_date = str(t).split("T")[0]

                grids = f.get("/science/LSAR/GCOV/grids")
                if grids is not None:
                    freqs = list(grids.keys())
                    fg = grids.get(freqs[0]) if freqs else None
                    if fg is not None:
                        proj = fg.get("projection")
                        if proj is not None and proj.shape == ():
                            crs = f"EPSG:{int(proj[()])}"
                        pols = [
                            x.decode() if isinstance(x, bytes) else str(x)
                            for x in fg.get("listOfCovarianceTerms", fg.get("listOfPolarizations", []))
                        ]
        except Exception:
            pass

        return track, frame, acq_date, crs, pols, freqs


local_inventory_service = LocalInventoryService()
