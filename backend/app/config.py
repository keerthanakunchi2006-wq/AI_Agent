"""Application configuration loaded from environment variables.

All settings are secrets-free defaults; override via `.env` or real env vars.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- App ----
    APP_NAME: str = "Supply Chain Disruption & Replanning System"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8000,http://127.0.0.1:8000"

    # ---- Database ----
    DATABASE_URL: str = "sqlite:///./supply_chain.db"

    # ---- LangGraph checkpoint store ----
    CHECKPOINT_DB_URL: str = ""

    # ---- Redis ----
    REDIS_URL: str = ""

    # ---- Auth ----
    JWT_SECRET: str = "change-me-in-production-please-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # ---- Seed/demo ----
    SEED_DEMO_DATA: bool = True
    DATASET_CSV: str = "data/supply_chain_dataset.csv"
    NUM_DATASET_RECORDS: int = 12000

    # ---- Human-in-the-loop thresholds ----
    APPROVAL_COST_THRESHOLD: float = 25000.0
    APPROVAL_DELAY_THRESHOLD_DAYS: int = 7

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _strip_cors(cls, v: str) -> str:
        return ",".join(part.strip() for part in v.split(",") if part.strip())

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def use_postgres_checkpoint(self) -> bool:
        return bool(self.CHECKPOINT_DB_URL) and "postgres" in self.CHECKPOINT_DB_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
