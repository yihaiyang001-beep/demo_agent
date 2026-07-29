"""Dependency assembly entry points."""

from __future__ import annotations

from .config import Config
from .storage.database import Database


def initialize_foundation(config: Config) -> Database:
    """Create and initialize the storage dependency used by later phases."""
    database = Database(config.db_path)
    database.initialize()
    return database

