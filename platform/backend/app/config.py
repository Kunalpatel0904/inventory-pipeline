from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./idea_board.db"
    cors_origins: str = "http://localhost:5173"
    ai_provider: Literal["deterministic", "openai_compatible"] = "deterministic"
    ai_api_key: str | None = None
    ai_model: str = "configured-model"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: float = Field(default=20.0, gt=0, le=120)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
