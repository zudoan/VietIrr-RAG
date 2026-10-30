from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    allowed_origins: tuple[str, ...]
    public_mode: bool
    public_evidence_excerpts: bool
    auto_create_schema: bool
    auto_seed: bool
    rate_limit_per_minute: int
    search_timeout_seconds: float
    max_request_bytes: int
    search_analytics_enabled: bool
    r6_enabled: bool
    r6_max_concurrency: int
    r6_context_budget_tokens: int
    root: Path = ROOT

    @classmethod
    def from_env(cls, root: Path = ROOT) -> "Settings":
        configured_root = Path(os.getenv("VIETIRR_ROOT", str(root))).resolve()
        environment = os.getenv("VIETIRR_ENV", "development").strip().lower()
        database_url = os.getenv(
            "DATABASE_URL",
            "sqlite+pysqlite:///./vietirr.db",
        )
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif database_url.startswith("postgresql://") and "+" not in database_url.split(":", 1)[0]:
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if environment == "production" and not database_url.startswith("postgresql+"):
            raise ValueError("Production requires a PostgreSQL DATABASE_URL.")

        origins = tuple(
            origin.strip().rstrip("/")
            for origin in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
            if origin.strip()
        )
        return cls(
            environment=environment,
            database_url=database_url,
            allowed_origins=origins,
            public_mode=_as_bool(os.getenv("VIETIRR_PUBLIC_MODE"), environment == "production"),
            public_evidence_excerpts=_as_bool(os.getenv("VIETIRR_PUBLIC_EVIDENCE_EXCERPTS"), False),
            auto_create_schema=_as_bool(os.getenv("VIETIRR_AUTO_CREATE_SCHEMA"), environment != "production"),
            auto_seed=_as_bool(os.getenv("VIETIRR_AUTO_SEED"), True),
            rate_limit_per_minute=max(1, int(os.getenv("VIETIRR_RATE_LIMIT_PER_MINUTE", "60"))),
            search_timeout_seconds=max(0.1, float(os.getenv("VIETIRR_SEARCH_TIMEOUT_SECONDS", "8"))),
            max_request_bytes=max(1024, int(os.getenv("VIETIRR_MAX_REQUEST_BYTES", "65536"))),
            search_analytics_enabled=_as_bool(os.getenv("VIETIRR_SEARCH_ANALYTICS"), False),
            r6_enabled=_as_bool(os.getenv("VIETIRR_R6_ENABLED"), True),
            r6_max_concurrency=max(1, int(os.getenv("VIETIRR_R6_MAX_CONCURRENCY", "1"))),
            r6_context_budget_tokens=max(512, int(os.getenv("VIETIRR_R6_CONTEXT_BUDGET_TOKENS", "4000"))),
            root=configured_root,
        )
