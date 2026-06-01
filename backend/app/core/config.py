from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is three levels up
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # External data ingestion
    BRAWLSTARS_API_KEY: str

    # Internal API protection
    INTERNAL_API_KEY: str

    # Database
    DATABASE_URL: str = Field(default="sqlite:///./brawldrafter.db")

    # CORS
    FRONTEND_ORIGIN: str = Field(default="http://localhost:5173")

    # Hybrid recommendation (per-mode draftnet_{mode_id}.pt under backend/models/)
    RECOMMENDER_ALPHA: float = Field(default=0.6, ge=0.0, le=1.0)
    MODEL_DEVICE: str = Field(default="cpu")

    # Rate limiting (slowapi)
    RATE_LIMIT_RECOMMENDATIONS: str = Field(default="60/minute")

    # Scheduled pipeline (APScheduler)
    SCHEDULER_ENABLED: bool = Field(default=False)
    PIPELINE_INTERVAL_HOURS: int = Field(default=24, ge=1)
    PIPELINE_FETCH_PLAYERS: int = Field(default=50, ge=1)
    PIPELINE_FETCH_MATCHES_PER_PLAYER: int = Field(default=25, ge=1)
    PIPELINE_RETRAIN: bool = Field(default=False)
    PIPELINE_TRAIN_MIN_MATCHES: int = Field(default=100, ge=10)
    PIPELINE_TRAIN_EPOCHS: int = Field(default=50, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
