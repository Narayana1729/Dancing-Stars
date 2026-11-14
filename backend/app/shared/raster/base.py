"""SAR raster loading and metadata interfaces (no implementation in Phase 1)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.shared.satellite.base import Mission, SarProduct


@dataclass(frozen=True)
class SarMetadata:
    mission: Mission
    product: SarProduct
    acquired: datetime
    polarizations: tuple[str, ...]
    crs: str
    extra: dict[str, Any] = field(default_factory=dict)


class MetadataExtractor(ABC):
    @abstractmethod
    def extract(self, path: str) -> SarMetadata: ...


class RasterLoader(ABC):
    @abstractmethod
    def load(self, path: str, polarization: str) -> Any:
        """Return a georeferenced backscatter array for one polarization."""

