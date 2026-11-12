"""Centralised, typed configuration (pydantic-settings).

Every field here has a matching, documented entry in the repository-root
`.env.example`. `tests/unit/test_config.py` fails if the two drift apart.
Environment variables override `.env` and both override the defaults.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.api.schemas.qa import TOP_K_MAX

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
DEV_JWT_SECRET: Final = "change-me-dev-only"  # noqa: S105  (rejected in production below)


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class GeneratorKind(StrEnum):
    EXTRACTIVE = "extractive"
    LLM = "llm"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # the shared .env also carries frontend (VITE_*) keys
    )

    # --- runtime -------------------------------------------------------------
    app_env: AppEnv = AppEnv.DEVELOPMENT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"
    log_question_text: bool = True

    # --- HTTP ----------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_allow_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    allow_anonymous_qa: bool = True
    rate_limit_qa: str = Field(default="60/minute", pattern=r"^\d+/(second|minute|hour|day)$")

    # --- corpus, index and embeddings (SC1: changing these changes index_version)
    corpus_dir: Path = Path("corpus")
    index_dir: Path = Path("artifacts/index")
    embedding_dim: int = Field(default=256, ge=16, le=4096)
    embedding_hash_salt: str = Field(default="hc-rag-v1", min_length=1)
    chunk_min_tokens: int = Field(default=80, ge=20)
    chunk_max_tokens: int = Field(default=160, ge=40)
    chunk_overlap_ratio: float = Field(default=0.15, ge=0.0, lt=0.5)

    # --- retrieval and generation --------------------------------------------
    retrieval_top_k_default: int = Field(default=5, ge=1, le=TOP_K_MAX)
    retrieval_top_k_max: int = Field(default=TOP_K_MAX, ge=1, le=TOP_K_MAX)
    rrf_k: int = Field(default=60, ge=1)
    retrieval_candidate_k: int = Field(default=50, ge=1, le=500)
    query_expansion_enabled: bool = True
    # Absolute cosine(question, best evidence chunk); below it → abstain before generation.
    retrieval_floor: float = Field(default=0.15, ge=0.0, le=1.0)
    answer_max_sentences: int = Field(default=3, ge=1, le=10)
    answer_mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)
    answer_min_relative_score: float = Field(default=0.5, ge=0.0, le=1.0)
    generator: GeneratorKind = GeneratorKind.EXTRACTIVE

    # --- validation and confidence (ADR-0002) --------------------------------
    confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    confidence_weight_coverage: float = Field(default=0.40, ge=0.0, le=1.0)
    confidence_weight_query_support: float = Field(default=0.35, ge=0.0, le=1.0)
    confidence_weight_retrieval: float = Field(default=0.25, ge=0.0, le=1.0)

    # --- optional LLM generator (off by default) -----------------------------
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None

    # --- persistence and auth (Phase 5) ---------------------------------------
    database_url: SecretStr | None = None
    query_log_retention_days: int = Field(default=30, ge=1)
    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_access_ttl_minutes: int = Field(default=15, ge=1)
    jwt_refresh_ttl_days: int = Field(default=7, ge=1)

    # --- observability ----------------------------------------------------------
    metrics_enabled: bool = True
    otel_exporter_otlp_endpoint: str | None = None

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "openai_api_key",
        "openai_model",
        "database_url",
        "otel_exporter_otlp_endpoint",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("corpus_dir", "index_dir", mode="after")
    @classmethod
    def _anchor_to_repo_root(cls, value: Path) -> Path:
        # Relative paths mean "relative to the repo", regardless of the working directory.
        return value if value.is_absolute() else REPO_ROOT / value

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        weights = (
            self.confidence_weight_coverage
            + self.confidence_weight_query_support
            + self.confidence_weight_retrieval
        )
        if abs(weights - 1.0) > 1e-6:
            raise ValueError(f"confidence weights must sum to 1.0, got {weights:.4f}")
        if self.chunk_min_tokens > self.chunk_max_tokens:
            raise ValueError("chunk_min_tokens must be <= chunk_max_tokens")
        if self.retrieval_top_k_default > self.retrieval_top_k_max:
            raise ValueError("retrieval_top_k_default must be <= retrieval_top_k_max")
        if self.generator is GeneratorKind.LLM and (
            self.openai_api_key is None or not self.openai_model
        ):
            raise ValueError("generator=llm requires OPENAI_API_KEY and OPENAI_MODEL")
        if self.app_env is AppEnv.PRODUCTION:
            secret = self.jwt_secret.get_secret_value()
            if secret == DEV_JWT_SECRET or len(secret) < 32:
                raise ValueError("production requires a JWT_SECRET of at least 32 characters")
            if self.log_question_text:
                raise ValueError("LOG_QUESTION_TEXT must be false in production (ADR-0009)")
            if "*" in self.cors_allow_origins:
                raise ValueError("wildcard CORS origins are not allowed in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, injected via FastAPI dependencies (Phase 3)."""
    return Settings()
