"""Persist the DuckDB warehouse file to Supabase Storage between cron runs.

GitHub Actions runners are ephemeral, so the DuckDB file must be restored at the
start of a run and saved at the end. It is stored as a gzip-compressed tarball
under the 'warehouse/' prefix in the artifacts bucket.

This is the standard pattern for the hybrid lakehouse: Storage holds the durable
copy, the runner works on a local extraction.
"""

from __future__ import annotations

import os
import tarfile
import tempfile

from .supabase_client import get_bucket_name, get_storage_client

WAREHOUSE_PREFIX = "warehouse"
REMOTE_NAME = "retaillens_duckdb.tar.gz"


def _remote_path() -> str:
    return f"{WAREHOUSE_PREFIX}/{REMOTE_NAME}"


def _export_bronze_only(src_db_path: str) -> str:
    """Create a temp DuckDB containing only the bronze schema.

    Silver and Gold are derived by dbt on every run, so they need not be
    persisted. Persisting only Bronze (the source of truth) keeps the archive
    well under Storage's per-file size limit.
    """
    import duckdb

    fd, bronze_path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.remove(bronze_path)  # duckdb needs to create it fresh
    con = duckdb.connect(bronze_path)
    con.execute(f"ATTACH '{src_db_path}' AS srcdb (READ_ONLY)")
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_catalog = 'srcdb' AND table_schema = 'bronze'"
    ).fetchall()
    for (t,) in tables:
        con.execute(f'CREATE TABLE bronze."{t}" AS SELECT * FROM srcdb.bronze."{t}"')
    con.execute("DETACH srcdb")
    con.execute("CHECKPOINT")
    con.close()
    return bronze_path


def save_duckdb(local_db_path: str) -> str:
    """Compress and upload the Bronze layer to Storage. Returns remote path.

    Only Bronze is archived; Silver and Gold are rebuilt by dbt on restore.
    """
    bronze_path = _export_bronze_only(local_db_path)

    client = get_storage_client()
    bucket = get_bucket_name()
    fd, tar_path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(bronze_path, arcname=os.path.basename(local_db_path))
    size_mb = os.path.getsize(tar_path) / 1e6
    with open(tar_path, "rb") as f:
        data = f.read()
    os.remove(tar_path)
    os.remove(bronze_path)

    storage = client.storage.from_(bucket)
    try:
        storage.remove([_remote_path()])
    except Exception:
        pass
    try:
        storage.upload(
            _remote_path(),
            data,
            {"content-type": "application/gzip", "upsert": "true"},
        )
    except Exception as exc:
        raise SystemExit(
            f"Upload failed ({exc}). Archive is {size_mb:.1f} MB. If this is a "
            "'Payload too large' error, raise the bucket file size limit in "
            "Supabase (Storage -> bucket -> Edit -> File size limit; free tier "
            "allows up to 50 MB)."
        )
    return _remote_path()


def restore_duckdb(local_db_path: str) -> bool:
    """Download and extract the DuckDB file from Storage.

    Returns True if restored, False if no remote copy exists yet (first run).
    """
    client = get_storage_client()
    bucket = get_bucket_name()
    try:
        data = client.storage.from_(bucket).download(_remote_path())
    except Exception:
        return False

    fd, tar_path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    with open(tar_path, "wb") as f:
        f.write(data)
    target_dir = os.path.dirname(os.path.abspath(local_db_path)) or "."
    os.makedirs(target_dir, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tar:
        # Extract the single member to the target path.
        members = tar.getmembers()
        if not members:
            os.remove(tar_path)
            return False
        member = members[0]
        member.name = os.path.basename(local_db_path)
        tar.extract(member, path=target_dir)
    os.remove(tar_path)
    return True


if __name__ == "__main__":
    # CLI: save or restore the warehouse. Used for the one-time bootstrap.
    #   python pipeline/utils/db_persistence.py save <path>
    #   python pipeline/utils/db_persistence.py restore <path>
    import sys

    from dotenv import load_dotenv

    load_dotenv()
    if len(sys.argv) != 3 or sys.argv[1] not in ("save", "restore"):
        print("Usage: python -m pipeline.utils.db_persistence save|restore <db_path>")
        sys.exit(1)
    action, path = sys.argv[1], sys.argv[2]
    if action == "save":
        print(f"Saved to {save_duckdb(path)}")
    else:
        print("Restored" if restore_duckdb(path) else "No remote warehouse found")
