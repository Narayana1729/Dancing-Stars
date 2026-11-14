from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from app.core.earthdata import EarthdataNotConfigured
from app.schemas.discovery import AOI_EXAMPLES, DiscoveryRequest, DiscoveryResponse
from app.services.aoi import InvalidAOI
from app.services.discovery import DiscoveryError, search_sme2

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.post("/search", response_model=DiscoveryResponse)
def search(
    req: Annotated[DiscoveryRequest, Body(openapi_examples=AOI_EXAMPLES)],
) -> DiscoveryResponse:
    """Find NISAR L3 SME2 soil moisture granules intersecting an AOI and time window."""
    try:
        return search_sme2(req)
    except InvalidAOI as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EarthdataNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except DiscoveryError as e:
        raise HTTPException(status_code=502, detail=str(e))
