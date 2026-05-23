"""Supabase Postgres helpers for the Gold serving layer.

Uses SQLAlchemy over the SUPABASE_DB_URL connection string. The Gold marts are
written here so Supabase's auto-generated REST API can serve them to the
dashboard.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def get_engine() -> Engine:
    """Create a SQLAlchemy engine for Supabase Postgres.

    Raises:
        RuntimeError: if SUPABASE_DB_URL is missing.
    """
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError(
            "Missing SUPABASE_DB_URL. Find it in Supabase > Project Settings > "
            "Database > Connection string (URI). Fill it into .env."
        )
    # SQLAlchemy expects the postgresql+psycopg2 dialect prefix.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True)


def check_connection(engine: Engine) -> bool:
    """Return True if a simple query succeeds."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
