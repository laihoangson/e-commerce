"""
Supabase client wrapper for RetailLens.

Provides:
- Postgres connection via supabase-py
- Storage upload/download helpers
- Health check entry point
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from supabase import Client, create_client

load_dotenv()


def get_client(service_role: bool = True) -> Client:
    """Return a Supabase client. service_role=True for write access."""
    url = os.environ["SUPABASE_URL"]
    key = (
        os.environ["SUPABASE_SERVICE_KEY"]
        if service_role
        else os.environ["SUPABASE_ANON_KEY"]
    )
    return create_client(url, key)


def health_check() -> bool:
    """Verify Supabase connectivity. Returns True if healthy."""
    logger.info("Running Supabase health check...")
    try:
        client = get_client()
        buckets = client.storage.list_buckets()
        logger.info(f"Storage buckets visible: {len(buckets)}")
        logger.success("Supabase health check passed")
        return True
    except Exception as e:
        logger.error(f"Supabase health check failed: {e}")
        return False


def ensure_bucket(bucket_name: str | None = None) -> None:
    """Create the artifacts bucket if it doesn't exist."""
    bucket_name = bucket_name or os.environ.get(
        "SUPABASE_STORAGE_BUCKET", "retaillens-artifacts"
    )
    client = get_client()
    existing = [b.name for b in client.storage.list_buckets()]
    if bucket_name in existing:
        logger.info(f"Bucket already exists: {bucket_name}")
        return
    client.storage.create_bucket(bucket_name, options={"public": False})
    logger.success(f"Created bucket: {bucket_name}")


def upload_file(local_path: str | Path, remote_path: str) -> None:
    """Upload local file to Supabase Storage."""
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(local_path)

    bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "retaillens-artifacts")
    client = get_client()

    with open(local_path, "rb") as f:
        client.storage.from_(bucket).upload(
            path=remote_path,
            file=f,
            file_options={"upsert": "true"},
        )
    logger.info(f"Uploaded {local_path} -> {bucket}/{remote_path}")


def download_file(remote_path: str, local_path: str | Path) -> None:
    """Download file from Supabase Storage to local path."""
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "retaillens-artifacts")
    client = get_client()

    data = client.storage.from_(bucket).download(remote_path)
    local_path.write_bytes(data)
    logger.info(f"Downloaded {bucket}/{remote_path} -> {local_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Supabase client utilities")
    parser.add_argument(
        "--health-check", action="store_true", help="Run health check and exit"
    )
    parser.add_argument(
        "--ensure-bucket", action="store_true", help="Create artifacts bucket"
    )
    args = parser.parse_args()

    if args.health_check:
        sys.exit(0 if health_check() else 1)
    elif args.ensure_bucket:
        ensure_bucket()
    else:
        parser.print_help()