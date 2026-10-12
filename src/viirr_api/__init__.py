"""Runtime API adapter for the VietIrr-RAG Phase E interface."""

from .app import PhaseERepository, create_server

__all__ = ["PhaseERepository", "create_server"]
