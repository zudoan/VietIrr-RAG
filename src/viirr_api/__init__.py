"""Production API for the VietIrr-RAG research website.

Imports are lazy so research-only runtimes can use ``r6_service`` without
installing FastAPI merely as a package side effect.
"""

__all__ = ["PhaseERepository", "app", "create_app"]


def __getattr__(name: str):
    if name == "PhaseERepository":
        from .repository import PhaseERepository
        return PhaseERepository
    if name in {"app", "create_app"}:
        from .app import app, create_app
        return {"app": app, "create_app": create_app}[name]
    raise AttributeError(name)
