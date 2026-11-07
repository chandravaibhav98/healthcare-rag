"""`.env.example` is the documentation of every config key, so it must not drift."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import REPO_ROOT, AppEnv, Settings

ENV_EXAMPLE = REPO_ROOT / ".env.example"
_KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def _example_keys() -> set[str]:
    return set(_KEY_RE.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore the developer's real environment and .env so tests are reproducible."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def _settings(**kwargs: Any) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_env_example_documents_exactly_the_settings_fields() -> None:
    backend_keys = {k for k in _example_keys() if not k.startswith("VITE_")}
    expected = {name.upper() for name in Settings.model_fields}
    assert backend_keys == expected, (
        f"missing from .env.example: {sorted(expected - backend_keys)}; "
        f"unknown in .env.example: {sorted(backend_keys - expected)}"
    )


def test_every_env_example_key_has_a_comment() -> None:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if _KEY_RE.match(line):
            assert i > 0, f"undocumented key: {line}"
            assert lines[i - 1].startswith("#"), f"undocumented key: {line}"


def test_env_example_loads_and_matches_defaults() -> None:
    from_file = Settings(_env_file=ENV_EXAMPLE)
    assert from_file.confidence_threshold == 0.6
    assert from_file.embedding_dim == 256
    assert from_file.database_url is not None
    assert from_file.openai_api_key is None  # empty value means "unset"


def test_relative_paths_are_anchored_at_repo_root() -> None:
    settings = _settings(corpus_dir=Path("corpus"))
    assert settings.corpus_dir == REPO_ROOT / "corpus"


def test_cors_origins_accept_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://a.test, http://b.test")
    assert _settings().cors_allow_origins == ["http://a.test", "http://b.test"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"confidence_weight_coverage": 0.5}, "sum to 1.0"),
        ({"retrieval_top_k_default": 10, "retrieval_top_k_max": 5}, "top_k_default"),
        ({"generator": "llm"}, "requires OPENAI_API_KEY"),
        ({"rate_limit_qa": "lots"}, "String should match pattern"),
    ],
)
def test_invalid_combinations_are_rejected(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _settings(**kwargs)


def test_production_rejects_dev_defaults() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        _settings(app_env=AppEnv.PRODUCTION)


def test_production_rejects_question_logging() -> None:
    with pytest.raises(ValidationError, match="LOG_QUESTION_TEXT"):
        _settings(app_env=AppEnv.PRODUCTION, jwt_secret="x" * 32, log_question_text=True)


def test_production_accepts_hardened_settings() -> None:
    settings = _settings(app_env=AppEnv.PRODUCTION, jwt_secret="x" * 32, log_question_text=False)
    assert settings.app_env is AppEnv.PRODUCTION
