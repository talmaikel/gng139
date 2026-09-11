from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql+asyncpg://shaked:shaked@localhost:5432/shaked_engine"
    database_url_sync: str = "postgresql://shaked:shaked@localhost:5432/shaked_engine"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_lifetime_seconds: int = 3600

    openai_api_key: str | None = None
    openai_extraction_model: str = "gpt-4o-mini"

    tesseract_cmd: str = "/usr/bin/tesseract"
    tesseract_lang: str = "heb+eng"

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
