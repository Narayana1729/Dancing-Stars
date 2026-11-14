"""Interfaces shared by the forest and wildfire modules."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ChangeDetector(ABC):
    @abstractmethod
    def detect(self, baseline: Any, target: Any) -> Any:
        """Return a change mask/map derived from real co-registered rasters."""

