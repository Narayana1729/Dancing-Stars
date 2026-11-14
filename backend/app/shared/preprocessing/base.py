from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Preprocessor(ABC):
    """A single preprocessing step (e.g. dB conversion, speckle filtering)."""

    @abstractmethod
    def apply(self, raster: Any) -> Any: ...


class TemporalComparator(ABC):
    """Compare two co-registered acquisitions (baseline t0 vs target t1)."""

    @abstractmethod
    def compare(self, baseline: Any, target: Any) -> Any: ...

