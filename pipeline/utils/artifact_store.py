"""Model artifact storage on Supabase Storage.

Training scripts upload fitted artifacts here; the API downloads them at
startup. This separates model versioning from code deployment - the standard
train-offline / serve-online pattern.

Artifacts are stored under the 'models/' prefix in the configured bucket.
"""

from __future__ import annotations

import os
import tempfile

from .supabase_client import get_bucket_name, get_storage_client

MODELS_PREFIX = "models"


def upload_artifact(local_path: str, remote_name: str) -> str:
    """Upload a local file to Storage under models/<remote_name>.

    Overwrites any existing artifact with the same name.

    Returns:
        The remote path written.
    """
    client = get_storage_client()
    bucket = get_bucket_name()
    remote_path = f"{MODELS_PREFIX}/{remote_name}"

    with open(local_path, "rb") as f:
        data = f.read()

    storage = client.storage.from_(bucket)
    # Remove first so re-uploads do not fail on "already exists".
    try:
        storage.remove([remote_path])
    except Exception:
        pass
    storage.upload(remote_path, data)
    return remote_path


def download_artifact(remote_name: str, local_path: str | None = None) -> str:
    """Download models/<remote_name> from Storage to a local path.

    Args:
        remote_name: artifact file name.
        local_path: where to write; defaults to a temp file.

    Returns:
        The local path written.
    """
    client = get_storage_client()
    bucket = get_bucket_name()
    remote_path = f"{MODELS_PREFIX}/{remote_name}"

    data = client.storage.from_(bucket).download(remote_path)
    if local_path is None:
        fd, local_path = tempfile.mkstemp(suffix=f"_{remote_name}")
        os.close(fd)
    with open(local_path, "wb") as f:
        f.write(data)
    return local_path
