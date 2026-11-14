from fastapi import APIRouter

from app.api.routes import acquisition, analysis, discovery, extraction, forest, health, processing, results

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(discovery.router)
api_router.include_router(acquisition.router)
api_router.include_router(extraction.router)
api_router.include_router(processing.router)
api_router.include_router(analysis.router)
api_router.include_router(results.router)
api_router.include_router(forest.router)
