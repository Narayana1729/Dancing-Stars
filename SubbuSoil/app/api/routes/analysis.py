from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from app.core.earthdata import EarthdataNotConfigured
from app.schemas.analysis import (
    ChangeRequest,
    ChangeResponse,
    ExplainRequest,
    FullChangeResponse,
    RunAnalysisRequest,
)
from app.schemas.discovery import AOI_EXAMPLES
from app.services.acquisition import AcquisitionError
from app.services.align import AlignmentError
from app.services.analysis import RunNotFound, analyse_run
from app.services.aoi import InvalidAOI
from app.services.change import ChangeParams
from app.services import progress as P
from app.services.aoi import parse_aoi
from app.services.discovery import DiscoveryError
from app.services.pipeline import prepare

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/change", response_model=FullChangeResponse)
def change_full(
    req: Annotated[ChangeRequest, Body(openapi_examples=AOI_EXAMPLES)],
) -> FullChangeResponse:
    """Steps 3-9 in one call: prepare rasters, detect change, extract change regions."""
    try:
        prep = prepare(req)
        result = analyse_run(prep.run_id, req.change)
    except (InvalidAOI, AcquisitionError, AlignmentError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EarthdataNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except DiscoveryError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return FullChangeResponse(**result, preparation=prep)


@router.post("/runs/{run_id}/change", response_model=ChangeResponse)
def change_for_run(run_id: str, params: ChangeParams | None = None) -> ChangeResponse:
    """Steps 8-9 on an already prepared run (fast; no network). Use this to try
    other thresholds or date pairs."""
    try:
        return ChangeResponse(**analyse_run(run_id, params or ChangeParams()))
    except RunNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/runs/{run_id}/context", response_model=ChangeResponse)
def context_for_run(run_id: str, req: RunAnalysisRequest | None = None) -> ChangeResponse:
    """Steps 8-10 on a prepared run: change, regions and supporting data
    (rainfall, temperature, ET0, ERA5-Land, Sentinel-2 NDVI, SoilGrids)."""
    req = req or RunAnalysisRequest()
    try:
        return ChangeResponse(**analyse_run(run_id, req.change, context=req.context))
    except RunNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/runs/{run_id}/explain", response_model=ChangeResponse)
def explain_for_run(run_id: str, req: RunAnalysisRequest | None = None) -> ChangeResponse:
    """Steps 8-11 on a prepared run: adds the explanation (what / where / when /
    how much / contributing factors, with evidence)."""
    req = req or RunAnalysisRequest()
    try:
        return ChangeResponse(**analyse_run(run_id, req.change, context=req.context, explain=True,
                                            n_top_regions=req.n_top_regions))
    except RunNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/explain", response_model=FullChangeResponse)
def explain_full(
    req: Annotated[ExplainRequest, Body(openapi_examples=AOI_EXAMPLES)],
) -> FullChangeResponse:
    """Steps 3-11 in one call."""
    try:
        prep = prepare(req)
        result = analyse_run(prep.run_id, req.change, context=req.context, explain=True,
                             n_top_regions=req.n_top_regions)
    except (InvalidAOI, AcquisitionError, AlignmentError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EarthdataNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except DiscoveryError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return FullChangeResponse(**result, preparation=prep)


@router.post("/explain/jobs", status_code=202)
def start_explain_job(
    req: Annotated[ExplainRequest, Body(openapi_examples=AOI_EXAMPLES)],
) -> dict:
    """Start steps 3-11 in the background. Poll GET /analysis/jobs/{job_id} for progress."""
    try:
        parse_aoi(bbox=req.bbox, geometry=req.geometry, wkt=req.wkt)
    except InvalidAOI as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        job_id = P.start_job(lambda report: P.explain_task(req, report), "explain")
    except P.JobBusy as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"job_id": job_id, "status": "running"}


@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    """Progress of a background job: percent, stage, elapsed time and, when done, run_id."""
    job = P.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job (jobs are kept in memory and reset on restart)")
    return P.public(job)
