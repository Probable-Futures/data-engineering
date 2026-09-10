"""Database write stage. Built in Phase 1 but OFF by default; enabled in Phase 3."""

from .writer import StatWriter

__all__ = ["StatWriter"]
