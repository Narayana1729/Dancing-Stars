"""Forest module interfaces (Phase 1: contracts only, no algorithms)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.shared.analysis import ChangeDetector


class ForestDisturbanceDetector(ABC):
    @abstractmethod
    def detect(self, baseline: Any, target: Any) -> Any:
        """Detect canopy disturbance from calibrated GCOV/GSLC backscatter."""


class DeforestationAssessor(ABC):
    @abstractmethod
    def assess(self, disturbance_mask: Any) -> Any:
        """Quantify deforestation from a validated disturbance mask."""


__all__ = ["ChangeDetector", "ForestDisturbanceDetector", "DeforestationAssessor"]

