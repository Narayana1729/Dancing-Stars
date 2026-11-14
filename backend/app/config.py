"""Environment-driven configuration (standard library only)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _split(value: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in value.split(",") if v.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str = "Dancing with the SARs API"
    version: str = "0.1.0"
    environment: str = "development"
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    data_dir: str = "data"


def get_settings() -> Settings:
    """Read settings from environment variables (see .env.example)."""
    defaults = Settings()
    return Settings(
        environment=os.getenv("APP_ENV", defaults.environment),
        cors_origins=_split(os.getenv("CORS_ORIGINS", ",".join(defaults.cors_origins))),
        data_dir=os.getenv("DATA_DIR", defaults.data_dir),
    )

