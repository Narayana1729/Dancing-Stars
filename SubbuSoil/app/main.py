from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from app.api.router import api_router
from app.core.config import get_settings

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/app")

    @app.get("/app", include_in_schema=False)
    def frontend():
        """Step 14: interactive viewer (map, history, regions, explanation)."""
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/forest", include_in_schema=False)
    def forest_frontend():
        """Forest disturbance viewer (GCOV backscatter, change, validation)."""
        return FileResponse(STATIC_DIR / "forest.html")

    return app


app = create_app()
