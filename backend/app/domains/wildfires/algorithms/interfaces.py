"""Wildfire module interfaces (Phase 1: contracts only, no algorithms)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.shared.analysis import ChangeDetector


class BurnedAreaAssessor(ABC):
    @abstractmethod
    def assess(self, baseline: Any, target: Any) -> Any:
        """Map burned area from pre/post-fire SAR backscatter."""


__all__ = ["ChangeDetector", "BurnedAreaAssessor"]

