"""Multi-temporal NISAR processing and polarimetric time-series analysis package."""
from app.domains.forests.processing.temporal_analysis.metadata import (
    AcquisitionMetadata,
    FeatureDistributionStats,
    PipelinePerformance,
    TemporalSeriesMetadata,
    ZonalStats,
)
from app.domains.forests.processing.temporal_analysis.temporal_features import (
    MultiTemporalFeatures,
    compute_distribution_stats,
    compute_local_spatial_std,
    extract_multitemporal_features,
)
from app.domains.forests.processing.temporal_analysis.temporal_loader import (
    LoadedTemporalSeries,
    NOISE_FLOOR_EPS,
    SIMILIPAL_X_MAX,
    SIMILIPAL_X_MIN,
    SIMILIPAL_Y_MAX,
    SIMILIPAL_Y_MIN,
    extract_acquisition_metadata,
    find_grid_slice,
    load_multitemporal_series,
)
from app.domains.forests.processing.temporal_analysis.temporal_statistics import (
    compute_db_temporal_statistics,
    compute_linear_temporal_statistics,
    compute_relative_normalized_difference,
    compute_tiled_theil_sen_slope,
)
from app.domains.forests.processing.temporal_analysis.disturbance_indicators import (
    classify_physical_change_regimes,
    evaluate_tier1_instantaneous_candidate,
    evaluate_tier2_sustained_anomaly,
    evaluate_tier3_persistent_candidate,
)
from app.domains.forests.processing.temporal_analysis.temporal_validation import (
    GridVerificationContext,
    compare_raster_baselines,
    validate_acquisition_compatibility,
)

__all__ = [
    "AcquisitionMetadata",
    "FeatureDistributionStats",
    "PipelinePerformance",
    "TemporalSeriesMetadata",
    "ZonalStats",
    "MultiTemporalFeatures",
    "compute_distribution_stats",
    "compute_local_spatial_std",
    "extract_multitemporal_features",
    "LoadedTemporalSeries",
    "NOISE_FLOOR_EPS",
    "SIMILIPAL_X_MAX",
    "SIMILIPAL_X_MIN",
    "SIMILIPAL_Y_MAX",
    "SIMILIPAL_Y_MIN",
    "extract_acquisition_metadata",
    "find_grid_slice",
    "load_multitemporal_series",
    "compute_linear_temporal_statistics",
    "compute_db_temporal_statistics",
    "compute_relative_normalized_difference",
    "compute_tiled_theil_sen_slope",
    "classify_physical_change_regimes",
    "evaluate_tier1_instantaneous_candidate",
    "evaluate_tier2_sustained_anomaly",
    "evaluate_tier3_persistent_candidate",
    "GridVerificationContext",
    "compare_raster_baselines",
    "validate_acquisition_compatibility",
]

