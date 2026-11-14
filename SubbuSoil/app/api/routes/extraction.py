from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from app.core.earthdata import EarthdataNotConfigured
from app.schemas.acquisition import AcquisitionRequest
from app.schemas.discovery import AOI_EXAMPLES
from app.schemas.extraction import ExtractedObservation, ExtractionResponse
from app.services.acquisition import AcquisitionError, acquire
from app.services.aoi import InvalidAOI, parse_aoi
from app.services.discovery import DiscoveryError
from app.services.extraction import extract_sme2, summarize

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post("/extract", response_model=ExtractionResponse)
def extract(
    req: Annotated[AcquisitionRequest, Body(openapi_examples=AOI_EXAMPLES)],
) -> ExtractionResponse:
    """Acquire 2+ observations (step 3) and extract soil moisture, uncertainty,
    quality flags, land cover and coordinates for the AOI window (step 4)."""
    try:
        aoi = parse_aoi(bbox=req.bbox, geometry=req.geometry, wkt=req.wkt)
        acq = acquire(req)
    except (InvalidAOI, AcquisitionError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EarthdataNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except DiscoveryError as e:
        raise HTTPException(status_code=502, detail=str(e))

    def work(o) -> ExtractedObservation:
        out = ExtractedObservation(granule_id=o.granule_id, start_time=o.start_time, track_key=o.track_key)
        if not o.verified:
            out.error = f"not acquired: {o.error}"
            return out
        try:
            ds, path = extract_sme2(o.local_path or o.https_url, aoi)
            out.netcdf_path = str(path)
            out.summary = summarize(ds)
        except Exception as e:
            out.error = f"{type(e).__name__}: {e}"
        return out

    with ThreadPoolExecutor(max_workers=min(4, len(acq.observations))) as pool:
        results = list(pool.map(work, acq.observations))

    return ExtractionResponse(
        aoi=acq.aoi, track_key=acq.track_key, n_observations=len(results), observations=results
    )
