from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from app.core.earthdata import EarthdataNotConfigured
from app.schemas.acquisition import AcquisitionRequest, AcquisitionResponse
from app.schemas.discovery import AOI_EXAMPLES
from app.services.acquisition import AcquisitionError, acquire
from app.services.aoi import InvalidAOI
from app.services.discovery import DiscoveryError

router = APIRouter(prefix="/acquisition", tags=["acquisition"])


@router.post("/acquire", response_model=AcquisitionResponse)
def acquire_observations(
    req: Annotated[AcquisitionRequest, Body(openapi_examples=AOI_EXAMPLES)],
) -> AcquisitionResponse:
    """Pick 2+ SME2 observations on one track for the AOI and verify they can be
    streamed (or download them with mode='download')."""
    try:
        return acquire(req)
    except (InvalidAOI, AcquisitionError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EarthdataNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except DiscoveryError as e:
        raise HTTPException(status_code=502, detail=str(e))
