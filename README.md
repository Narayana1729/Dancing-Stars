# NISAR – Dancing with the SARs (NASA Space Apps)

A planned SAR-based platform for **forest and wildfire monitoring** (floods/wetlands and soil/agriculture are out of scope for now).

> **Status: Phase 1 (foundation).** There is no satellite data acquisition, SAR processing, ML or scientific analysis yet. The dashboard shows **illustrative mock data**.

## Implemented and tested
- FastAPI backend: app factory, `/health`, CORS, `/api/v1` routing, env config, 501 responses for unimplemented analysis (`backend/tests`, 14 passing).
- Backend interfaces (no implementations): satellite provider, raster loader, metadata extractor, preprocessing / temporal comparison, forest and wildfire detectors.
- React + Vite dashboard with before/after slider, side panel, loading/error/empty states, backend health indicator.

## Not implemented (planned)
NISAR / Sentinel-1 acquisition, raster loading, calibration, change detection, forest disturbance, deforestation, burned area, ML, validation, deployment (Dockerfile / compose are empty).

## Quick start
See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Data products: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

# Dancing-Stars
