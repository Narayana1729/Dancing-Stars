from fastapi import APIRouter

from app.core.exceptions import NotYetImplemented

router = APIRouter(prefix="/wildfires", tags=["wildfires"])

CAPABILITIES = ["burned_area_assessment", "change_detection"]


@router.get("/status")
def status() -> dict:
    return {
        "domain": "wildfires",
        "implemented": False,
        "capabilities": {name: "not_implemented" for name in CAPABILITIES},
    }


@router.post("/analyze")
def analyze() -> dict:
    raise NotYetImplemented("Wildfire analysis is not implemented yet (planned for a later phase).")

