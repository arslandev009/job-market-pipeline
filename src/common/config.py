"""
Central configuration for the whole pipeline.

Two layers, deliberately kept separate (see docs/ARCHITECTURE.md §4):
  - Settings   : infra/secrets, from environment variables (.env). Machine-specific.
  - Profile    : candidate skills, scoring weights, enabled sources (profile.yaml).
                 User-specific, swappable without touching code.

Every module in this project should import from here rather than reading
os.environ or YAML directly — one source of truth, one place to add validation.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Infra & secrets, sourced from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql://jmp_user:devpass@localhost:5432/job_market",
        alias="DATABASE_URL",
    )

    # Base URL only (no path) — the extractor appends /completion itself, since
    # grammar-constrained sampling requires llama.cpp's native endpoint, not the
    # OpenAI-compatible /v1/chat/completions one (which doesn't accept `grammar`).
    llm_base_url: str = Field(default="http://localhost:8080", alias="LLM_BASE_URL")
    llm_timeout_seconds: int = Field(default=30, alias="LLM_TIMEOUT_SECONDS")

    google_sheets_credentials_path: str = Field(
        default="credentials.json", alias="GOOGLE_SHEETS_CREDENTIALS_PATH"
    )
    google_sheet_name: str = Field(default="Job Market Report", alias="GOOGLE_SHEET_NAME")
    # CHANGE 2026-08-16: service accounts can't reliably find shared sheets via
    # Drive's name-search (client.open() by title), and they're structurally
    # forbidden from creating their own spreadsheets (Google enforces a 0-byte
    # Drive quota for service accounts). Opening by ID sidesteps both problems.
    # Get this from the sheet's URL: .../spreadsheets/d/<THIS PART>/edit
    google_sheet_id: Optional[str] = Field(default=None, alias="GOOGLE_SHEET_ID")

    scraper_max_concurrency: int = Field(default=3, alias="SCRAPER_MAX_CONCURRENCY")
    scraper_request_delay_seconds: float = Field(
        default=1.5, alias="SCRAPER_REQUEST_DELAY_SECONDS"
    )
    scraper_timeout_ms: int = Field(default=15000, alias="SCRAPER_TIMEOUT_MS")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: str = Field(default="local", alias="ENVIRONMENT")

    profile_path: str = Field(default="config/profile.yaml", alias="PROFILE_PATH")


class ScoringWeights(BaseModel):
    skill_match: float = 0.5
    salary_fit: float = 0.3
    location_fit: float = 0.2


class Candidate(BaseModel):
    skills: list[str] = Field(default_factory=list)
    preferred_salary_min: float = 0
    preferred_location: str = "Remote"
    currency: str = "USD"


class Scoring(BaseModel):
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    learned_model_path: Optional[str] = None


class Sources(BaseModel):
    enabled: list[str] = Field(default_factory=lambda: ["remoteok", "arbeitnow"])
    scrape_interval_hours: int = 24


class Profile(BaseModel):
    """User-facing config: who you are, what you want, how to weigh it."""

    candidate: Candidate = Field(default_factory=Candidate)
    scoring: Scoring = Field(default_factory=Scoring)
    sources: Sources = Field(default_factory=Sources)

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        path = Path(path)
        if not path.exists():
            example = path.with_name(path.stem + ".example" + path.suffix)
            raise FileNotFoundError(
                f"Profile config not found at {path}. "
                f"Copy {example.name} to {path.name} and edit it first."
            )
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return cls.model_validate(raw)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_profile() -> Profile:
    settings = get_settings()
    profile_path = REPO_ROOT / settings.profile_path
    return Profile.load(profile_path)