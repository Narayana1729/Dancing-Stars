from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api_router import api_router
from app.config import Settings, get_settings
from app.core.exceptions import NotYetImplemented


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version=settings.version)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotYetImplemented)
    async def _not_implemented(_: Request, exc: NotYetImplemented) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": str(exc)})

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": settings.version, "environment": settings.environment}

    app.include_router(api_router)
    return app


app = create_app()

