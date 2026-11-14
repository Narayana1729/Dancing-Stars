from fastapi import APIRouter

from app.domains.forests.api.routes import router as forests_router
from app.domains.wildfires.api.routes import router as wildfires_router
from app.shared.satellite.base import DEFAULT_FOREST_PRODUCTS, NON_DEFAULT_FOREST_PRODUCTS

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(forests_router)
api_router.include_router(wildfires_router)


@api_router.get("/data-products", tags=["shared"])
def data_products() -> dict:
    """Product-selection policy for forest monitoring (static policy, not observations)."""
    return {
        "default": [p.value for p in DEFAULT_FOREST_PRODUCTS],
        "not_default": [p.value for p in NON_DEFAULT_FOREST_PRODUCTS],
    }

