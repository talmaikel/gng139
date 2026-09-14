from functools import lru_cache
from secrets import token_urlsafe

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    # Development defaults rely on local/peer authentication and contain no
    # repository-stored credentials. Deployments should set both URLs.
    database_url: str = "postgresql+asyncpg://localhost/shaked_engine"
    database_url_sync: str = "postgresql://localhost/shaked_engine"

    # Keeps a zero-config development process usable without publishing a
    # shared key. Deployments must provide a stable JWT_SECRET explicitly.
    jwt_secret: str = Field(default_factory=lambda: token_urlsafe(32))
    jwt_lifetime_seconds: int = 3600

    openai_api_key: str | None = None
    openai_extraction_model: str = "gpt-4o-mini"

    tesseract_cmd: str = "/usr/bin/tesseract"
    tesseract_lang: str = "heb+eng"

    # Public data sources (see app/sources/client.py and app/evidence.py)
    source_cache_dir: str = ".cache/sources"
    source_cache_ttl_seconds: int = 86400
    source_max_age_days: int = 30  # evidence older than this cannot decide an eligibility check
    # מגבלת שטח לאזור חיפוש מצויר. הערך ייקבע בפיילוט (PRD MAP-01);
    # 250 דונם הוא הערך שה-POC עבד לפיו והוא נקודת המוצא.
    max_search_area_sqm: float = 250_000

    market_data_radius_m: int = Field(default=500, ge=100, le=2_000)
    market_data_lookback_months: int = Field(default=12, ge=1, le=36)
    market_data_cache_days: int = Field(default=7, ge=0, le=30)

    # ‏localhost ו-127.0.0.1 הם מקורות שונים לדפדפן, ושניהם בשימוש בהרצה
    # מקומית — origin אחד בלבד נכשל ב-CORS בלי שהשרת מדווח על כלום.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
