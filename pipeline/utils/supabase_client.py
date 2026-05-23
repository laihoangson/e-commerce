"""Supabase clients — Storage (holds the DuckDB file) + Postgres (Gold serving).

Required env (see .env.example):
    SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_BUCKET, SUPABASE_DB_URL
"""

from __future__ import annotations

import os

from supabase import Client, create_client


def get_storage_client() -> Client:
    """Create a Supabase client using the service key (Storage + Postgres R/W).

    Raises:
        RuntimeError: if a required env var is missing.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_KEY. "
            "Copy .env.example -> .env and fill in the values."
        )
    return create_client(url, key)


def get_bucket_name() -> str:
    """Return the Storage bucket name that holds the DuckDB file."""
    return os.getenv("SUPABASE_BUCKET", "retaillens-artifacts")


def check_bucket_exists(client: Client, bucket: str | None = None) -> bool:
    """Return True if the bucket exists on Supabase Storage."""
    bucket = bucket or get_bucket_name()
    try:
        buckets = client.storage.list_buckets()
        names = {b.name for b in buckets}
        return bucket in names
    except Exception:
        return False
