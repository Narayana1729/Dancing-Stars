"""Statistical forest disturbance detection for multi-temporal NISAR L2 GCOV.

Scientific basis:
1. L-band cross-polarization (HV) backscatter is dominated by volume scattering in forest canopies.
2. Canopy loss (deforestation, logging, crown fire, treefall) induces a significant drop in HV backscatter:
   Δσ°_HV = σ°_HV(t1) - σ°_HV(t0) < 0.
3. Analysis is strictly constrained to documented forest cover masks to prevent non-forest false positives.
4. Morphological / connected-component spatial filtering enforces a minimum mapping unit (MMU) to mitigate speckle.
5. All processing is statistical and radiometric; no black-box AI claims are made.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import ndimage
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from app.domains.forests.algorithms.interfaces import ForestDisturbanceDetector


@dataclass
class DisturbanceDetectionResult:
    threshold_db: float
    detected_pixels: int
    detected_area_ha: float
    detected_area_km2: float
    total_forest_pixels: int
    total_forest_area_km2: float
    disturbance_fraction_percent: float
    mean_forest_delta_hv_db: float
    std_forest_delta_hv_db: float
    median_forest_delta_hv_db: float
    spatial_filter_applied: bool
    min_cluster_pixels: int
    cluster_count: int
    validation_metrics: Optional[Dict[str, Any]] = None


class StatisticalForestDisturbanceDetector(ForestDisturbanceDetector):
    """Calibrated statistical change detector for forest canopy disturbance."""

    def __init__(
        self,
        default_threshold_db: float = -2.5,
        min_cluster_pixels: int = 3,
        pixel_size_m: float = 80.0,
    ) -> None:
        self.default_threshold_db = default_threshold_db
        self.min_cluster_pixels = min_cluster_pixels
        self.pixel_size_m = pixel_size_m
        self.pixel_area_ha = (pixel_size_m * pixel_size_m) / 10000.0

    def compute_layers(
        self,
        hh0: np.ndarray,
        hv0: np.ndarray,
        hh1: np.ndarray,
        hv1: np.ndarray,
    ) -> Dict[str, np.ndarray]:
        """Compute decibel backscatter, temporal differences, and polarimetric ratios."""
        eps = 1e-7
        valid = (
            ~np.isnan(hh0)
            & ~np.isnan(hv0)
            & ~np.isnan(hh1)
            & ~np.isnan(hv1)
            & (hh0 > eps)
            & (hv0 > eps)
            & (hh1 > eps)
            & (hv1 > eps)
        )

        hh0_db = np.where(valid, 10.0 * np.log10(np.clip(hh0, eps, None)), np.nan)
        hv0_db = np.where(valid, 10.0 * np.log10(np.clip(hv0, eps, None)), np.nan)
        hh1_db = np.where(valid, 10.0 * np.log10(np.clip(hh1, eps, None)), np.nan)
        hv1_db = np.where(valid, 10.0 * np.log10(np.clip(hv1, eps, None)), np.nan)

        delta_hh = hh1_db - hh0_db
        delta_hv = hv1_db - hv0_db

        ratio_0 = hv0_db - hh0_db  # Cross-ratio in dB
        ratio_1 = hv1_db - hh1_db
        delta_ratio = ratio_1 - ratio_0

        return {
            "valid_mask": valid,
            "hh0_db": hh0_db,
            "hv0_db": hv0_db,
            "hh1_db": hh1_db,
            "hv1_db": hv1_db,
            "delta_hh": delta_hh,
            "delta_hv": delta_hv,
            "ratio_0": ratio_0,
            "ratio_1": ratio_1,
            "delta_ratio": delta_ratio,
        }

    def apply_spatial_filter(self, binary_mask: np.ndarray, min_cluster: int) -> Tuple[np.ndarray, int]:
        """Filter out isolated noise pixels that don't meet minimum mapping unit."""
        if min_cluster <= 1 or not np.any(binary_mask):
            labeled, n = ndimage.label(binary_mask)
            return binary_mask.copy(), int(n)

        labeled, num_features = ndimage.label(binary_mask)
        if num_features == 0:
            return binary_mask.copy(), 0

        sizes = ndimage.sum(binary_mask, labeled, range(num_features + 1))
        filtered = binary_mask.copy()
        remove_indices = np.where(sizes < min_cluster)[0]
        remove_mask = np.isin(labeled, remove_indices)
        filtered[remove_mask] = False

        _, remaining_clusters = ndimage.label(filtered)
        return filtered, int(remaining_clusters)

    def detect(
        self,
        baseline: Dict[str, np.ndarray],
        target: Dict[str, np.ndarray],
        forest_mask: np.ndarray,
        threshold_db: Optional[float] = None,
        apply_filter: bool = True,
        min_cluster_pixels: Optional[int] = None,
        reference_disturbance: Optional[np.ndarray] = None,
    ) -> DisturbanceDetectionResult:
        """Detect canopy disturbance within the documented forest mask."""
        thresh = threshold_db if threshold_db is not None else self.default_threshold_db
        min_cluster = min_cluster_pixels if min_cluster_pixels is not None else self.min_cluster_pixels

        layers = self.compute_layers(
            hh0=baseline["hh"],
            hv0=baseline["hv"],
            hh1=target["hh"],
            hv1=target["hv"],
        )

        valid_forest = layers["valid_mask"] & (forest_mask > 0)
        total_forest_pixels = int(np.sum(valid_forest))
        total_forest_area_km2 = (total_forest_pixels * (self.pixel_size_m**2)) / 1e6

        if total_forest_pixels == 0:
            raise ValueError("No valid forest pixels available within the study area.")

        forest_delta_hv = layers["delta_hv"][valid_forest]
        mean_delta = float(np.mean(forest_delta_hv))
        std_delta = float(np.std(forest_delta_hv))
        median_delta = float(np.median(forest_delta_hv))

        # Statistical threshold: significant drop in HV volume scattering
        raw_disturbed = valid_forest & (layers["delta_hv"] <= thresh)

        if apply_filter:
            disturbed_mask, cluster_count = self.apply_spatial_filter(raw_disturbed, min_cluster)
        else:
            disturbed_mask = raw_disturbed
            labeled, cluster_count = ndimage.label(disturbed_mask)

        detected_pixels = int(np.sum(disturbed_mask))
        detected_area_ha = detected_pixels * self.pixel_area_ha
        detected_area_km2 = (detected_pixels * (self.pixel_size_m**2)) / 1e6
        fraction_pct = (detected_pixels / total_forest_pixels) * 100.0

        validation = None
        if reference_disturbance is not None:
            validation = self.evaluate_against_reference(
                pred_mask=disturbed_mask,
                ref_mask=reference_disturbance,
                eval_mask=valid_forest,
            )

        return DisturbanceDetectionResult(
            threshold_db=thresh,
            detected_pixels=detected_pixels,
            detected_area_ha=round(detected_area_ha, 2),
            detected_area_km2=round(detected_area_km2, 4),
            total_forest_pixels=total_forest_pixels,
            total_forest_area_km2=round(total_forest_area_km2, 2),
            disturbance_fraction_percent=round(fraction_pct, 3),
            mean_forest_delta_hv_db=round(mean_delta, 2),
            std_forest_delta_hv_db=round(std_delta, 2),
            median_forest_delta_hv_db=round(median_delta, 2),
            spatial_filter_applied=apply_filter,
            min_cluster_pixels=min_cluster,
            cluster_count=cluster_count,
            validation_metrics=validation,
        )

    def evaluate_against_reference(
        self,
        pred_mask: np.ndarray,
        ref_mask: np.ndarray,
        eval_mask: np.ndarray,
    ) -> Dict[str, Any]:
        """Compute honest precision, recall, F1, confusion matrix, and false-positive rate."""
        y_true = (ref_mask[eval_mask] > 0).astype(int)
        y_pred = (pred_mask[eval_mask] > 0).astype(int)

        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        prec, rec, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, average="binary", zero_division=0
        )
        fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0

        return {
            "true_positive_pixels": int(tp),
            "false_positive_pixels": int(fp),
            "false_negative_pixels": int(fn),
            "true_negative_pixels": int(tn),
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1_score": round(float(f1), 4),
            "false_positive_rate": round(fpr, 5),
            "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        }

    def evaluate_sensitivity(
        self,
        baseline: Dict[str, np.ndarray],
        target: Dict[str, np.ndarray],
        forest_mask: np.ndarray,
        thresholds: List[float],
        min_cluster: int = 3,
        reference_disturbance: Optional[np.ndarray] = None,
    ) -> List[DisturbanceDetectionResult]:
        """Evaluate detector sensitivity across multiple threshold candidates."""
        results = []
        for t in thresholds:
            r = self.detect(
                baseline=baseline,
                target=target,
                forest_mask=forest_mask,
                threshold_db=t,
                apply_filter=True,
                min_cluster_pixels=min_cluster,
                reference_disturbance=reference_disturbance,
            )
            results.append(r)
        return results

