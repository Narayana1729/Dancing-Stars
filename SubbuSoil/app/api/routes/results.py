from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services import results as R

router = APIRouter(prefix="/results", tags=["results"])


def _call(fn, *args):
    try:
        return fn(*args)
    except R.ResultNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/runs")
def list_runs():
    """All prepared runs with their available date pairs."""
    return {"runs": _call(R.list_runs)}


@router.get("/runs/{run_id}")
def run_detail(run_id: str):
    """Request, grid, observations and QC report for one run."""
    return _call(R.run_detail, run_id)


@router.get("/runs/{run_id}/history")
def run_history(run_id: str):
    """Per-date soil-moisture statistics across the run (historical comparison)."""
    return _call(R.history, run_id)


@router.get("/runs/{run_id}/pairs/{pair_id}")
def pair_detail(run_id: str, pair_id: str):
    """Change statistics, region summary, supporting context and explanation."""
    return _call(R.pair_detail, run_id, pair_id)


@router.get("/runs/{run_id}/pairs/{pair_id}/regions")
def pair_regions(run_id: str, pair_id: str):
    """Change-region polygons (GeoJSON, EPSG:4326), largest first."""
    return _call(R.regions, run_id, pair_id)


@router.get("/runs/{run_id}/pairs/{pair_id}/overlay")
def pair_overlay(run_id: str, pair_id: str):
    """Bounds and colour scale for drawing the change map on a web map."""
    return _call(R.delta_bounds, run_id, pair_id)


@router.get("/runs/{run_id}/pairs/{pair_id}/delta.png", responses={200: {"content": {"image/png": {}}}})
def pair_delta_png(run_id: str, pair_id: str):
    """Change map as a transparent PNG in EPSG:4326."""
    return Response(content=_call(R.delta_png, run_id, pair_id), media_type="image/png")


@router.get("/runs/{run_id}/pairs/{pair_id}/panels.png", responses={200: {"content": {"image/png": {}}}})
def pair_panels_png(run_id: str, pair_id: str):
    """Observation 1, observation 2 and their difference side by side (as in data_reading.ipynb)."""
    return Response(content=_call(R.panels_png, run_id, pair_id), media_type="image/png")
