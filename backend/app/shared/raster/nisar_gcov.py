"""NASA NISAR L2 GCOV HDF5 raster loader and metadata extractor."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import h5py
import numpy as np

from app.shared.raster.base import MetadataExtractor, RasterLoader, SarMetadata
from app.shared.satellite.base import Mission, SarProduct


@dataclass(frozen=True)
class GeocodedRaster:
    array: np.ndarray
    polarization: str
    frequency: str
    crs: str
    x_coords: np.ndarray
    y_coords: np.ndarray
    pixel_spacing: tuple[float, float]
    fill_value: float


class NisarGcovLoader(RasterLoader, MetadataExtractor):
    """Loads and extracts metadata from authentic NISAR L2 GCOV HDF5 granules."""

    def extract(self, path: str) -> SarMetadata:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"GCOV file not found: {path}")

        with h5py.File(p, "r") as f:
            ident = f["/science/LSAR/identification"]
            t_start = ident["zeroDopplerStartTime"][()]
            if isinstance(t_start, bytes):
                t_start = t_start.decode()

            grids = f["/science/LSAR/GCOV/grids"]
            freq_name = "frequencyA" if "frequencyA" in grids else sorted(grids.keys())[0]
            fg = grids[freq_name]

            pols = [
                x.decode() if isinstance(x, bytes) else str(x)
                for x in fg.get("listOfCovarianceTerms", fg.get("listOfPolarizations", []))
            ]

            proj = fg.get("projection")
            epsg = int(proj[()]) if proj is not None and proj.shape == () else 0
            crs = f"EPSG:{epsg}" if epsg else "UNKNOWN"

            extra = {
                "track": int(ident["trackNumber"][()]),
                "frame": int(ident["frameNumber"][()]),
                "orbit_direction": (
                    ident["orbitPassDirection"][()].decode()
                    if isinstance(ident["orbitPassDirection"][()], bytes)
                    else str(ident["orbitPassDirection"][()])
                ),
                "frequencies": list(grids.keys()),
                "x_spacing": float(fg["xCoordinateSpacing"][()]) if "xCoordinateSpacing" in fg else None,
                "y_spacing": float(fg["yCoordinateSpacing"][()]) if "yCoordinateSpacing" in fg else None,
                "grid_shape": fg[pols[0]].shape if pols and pols[0] in fg else None,
            }

            dt = datetime.fromisoformat(t_start.split(".")[0])
            return SarMetadata(
                mission=Mission.NISAR,
                product=SarProduct.GCOV,
                acquired=dt,
                polarizations=tuple(pols),
                crs=crs,
                extra=extra,
            )

    def load(
        self,
        path: str,
        polarization: str = "HHHH",
        frequency: str = "frequencyB",
        stride: int = 1,
    ) -> GeocodedRaster:
        """Load 2D measurement backscatter array from the GCOV HDF5 file.

        Args:
            path: Path to the .h5 file.
            polarization: Covariance term dataset name (e.g. 'HHHH' or 'HVHV').
            frequency: 'frequencyA' (10m high-res) or 'frequencyB' (80m sideband).
            stride: Decimation step (> 1) for rapid downsampling.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"GCOV file not found: {path}")

        with h5py.File(p, "r") as f:
            grids = f["/science/LSAR/GCOV/grids"]
            if frequency not in grids:
                raise KeyError(f"Frequency group '{frequency}' not found. Available: {list(grids.keys())}")
            fg = grids[frequency]

            if polarization not in fg:
                raise KeyError(f"Polarization '{polarization}' not in {frequency}. Available: {list(fg.keys())}")

            ds = fg[polarization]
            arr = ds[::stride, ::stride].astype("float32")
            fill = float(ds.attrs.get("_FillValue", np.nan))

            proj = fg.get("projection")
            epsg = int(proj[()]) if proj is not None and proj.shape == () else 0
            crs = f"EPSG:{epsg}" if epsg else "UNKNOWN"

            x_all = fg["xCoordinates"][::stride]
            y_all = fg["yCoordinates"][::stride]
            dx = float(fg["xCoordinateSpacing"][()]) * stride
            dy = float(fg["yCoordinateSpacing"][()]) * stride

            return GeocodedRaster(
                array=arr,
                polarization=polarization,
                frequency=frequency,
                crs=crs,
                x_coords=x_all,
                y_coords=y_all,
                pixel_spacing=(dx, dy),
                fill_value=fill,
            )

