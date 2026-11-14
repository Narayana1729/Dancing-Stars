from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NISAR Soil Moisture Change API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # NASA Earthdata Login (needed for ASF search/streaming of NISAR data)
    earthdata_username: str | None = None
    earthdata_password: SecretStr | None = None
    earthdata_token: SecretStr | None = None

    # Local working directory for downloads / intermediate rasters
    data_dir: Path = BACKEND_DIR / "data"

    @field_validator(
        "earthdata_username", "earthdata_password", "earthdata_token", mode="before"
    )
    @classmethod
    def _blank_to_none(cls, v):
        # `EARTHDATA_TOKEN=` in .env should mean "not set", not an empty secret
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def earthdata_configured(self) -> bool:
        return bool(
            self.earthdata_token or (self.earthdata_username and self.earthdata_password)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
