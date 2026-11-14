from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from app.core.earthdata import EarthdataNotConfigured
from app.schemas.discovery import AOI_EXAMPLES
from app.schemas.processing import PrepareRequest, PrepareResponse
from app.services.acquisition import AcquisitionError
from app.services.align import AlignmentError
from app.services.aoi import InvalidAOI
from app.services.discovery import DiscoveryError
from app.services.pipeline import prepare

router = APIRouter(prefix="/processing", tags=["processing"])


@router.post("/prepare", response_model=PrepareResponse)
def prepare_rasters(
    req: Annotated[PrepareRequest, Body(openapi_examples=AOI_EXAMPLES)],
) -> PrepareResponse:
    """Steps 3-7: acquire, extract, clip to the AOI polygon, apply QC masks,
    verify units and align all observations onto one grid."""
    try:
        return prepare(req)
    except (InvalidAOI, AcquisitionError, AlignmentError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EarthdataNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except DiscoveryError as e:
        raise HTTPException(status_code=502, detail=str(e))
