"""Persists generated artifacts locally and mirrors them to Google Cloud Storage.

Not responsible for: fetch operations, prompting, rendering, or workflow orchestrations.
Depends on: agent.config (and stdlib/google-cloud-storage).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from agent.config import get_settings
from agent.errors import ArtifactStorageError, SignedUrlError

logger = logging.getLogger(__name__)


async def save_artifact(session_id: str, svg: str) -> str:
    """Save a generated SVG artifact locally and optionally mirror it to Cloud Storage.

    Args:
        session_id: Stable session identifier used as the artifact filename.
        svg: SVG markup to save.

    Returns:
        Local artifact path.
    """
    path, _signed_url = await save_artifact_with_url(session_id, svg)
    return path


async def save_artifact_with_url(session_id: str, svg: str) -> tuple[str, str]:
    """Save a generated SVG artifact and return a browser URL when available."""
    artifact_dir = Path(get_settings().artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{session_id}.svg"
    path.write_text(svg, encoding="utf-8")
    signed_url = await _upload_artifact_to_gcs(path, "image/svg+xml")
    return str(path), signed_url


async def save_binary_artifact(session_id: str, data: bytes, mime_type: str) -> str:
    """Save a generated binary artifact locally and optionally mirror it to Cloud Storage.

    Args:
        session_id: Stable session identifier used as the artifact filename.
        data: Binary artifact bytes.
        mime_type: MIME type for file extension and Cloud Storage metadata.

    Returns:
        Local artifact path.
    """
    path, _signed_url = await save_binary_artifact_with_url(session_id, data, mime_type)
    return path


async def save_binary_artifact_with_url(
    session_id: str,
    data: bytes,
    mime_type: str,
) -> tuple[str, str]:
    """Save a generated binary artifact and return a browser URL when available."""
    artifact_dir = Path(get_settings().artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{session_id}{_extension_for_mime_type(mime_type)}"
    path.write_bytes(data)
    signed_url = await _upload_artifact_to_gcs(path, mime_type)
    return str(path), signed_url


def artifact_url_for_path(artifact_path: str) -> str:
    return f"/artifacts/{Path(artifact_path).name}"


async def _upload_artifact_to_gcs(path: Path, content_type: str) -> str:
    bucket_name = get_settings().gcs_bucket
    if not bucket_name:
        return ""

    def upload() -> str:
        from google.cloud import storage

        prefix = get_settings().gcs_artifact_prefix.strip("/")
        object_name = f"{prefix}/{path.name}" if prefix else path.name
        client = storage.Client()
        blob = client.bucket(bucket_name).blob(object_name)
        blob.upload_from_filename(str(path), content_type=content_type)
        return _generate_signed_artifact_url(blob)

    try:
        return await asyncio.to_thread(upload)
    except Exception as exc:
        if isinstance(exc, (SignedUrlError, ArtifactStorageError)):
            raise exc
        logger.warning("Cloud Storage artifact upload failed: %s", exc)
        return ""


def _generate_signed_artifact_url(blob) -> str:
    try:
        ttl_seconds = signed_artifact_url_ttl_seconds()
        credentials, service_account_email = _signed_url_credentials()
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=ttl_seconds),
            method="GET",
            credentials=credentials,
            service_account_email=service_account_email,
            access_token=credentials.token,
        )
    except Exception as exc:
        if isinstance(exc, (SignedUrlError, ArtifactStorageError)):
            raise exc
        raise SignedUrlError(f"Failed to generate signed URL: {exc}") from exc


def signed_artifact_url_ttl_seconds() -> int:
    return get_settings().gcs_signed_url_ttl_seconds


def _signed_url_credentials():
    import google.auth
    from google.auth.transport.requests import Request

    try:
        credentials, _project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_request = Request()
        credentials.refresh(auth_request)
    except Exception as exc:
        raise SignedUrlError(
            f"Failed to load credentials for GCS signing: {exc}"
        ) from exc

    service_account_email = get_settings().gcs_signing_service_account or getattr(
        credentials,
        "service_account_email",
        "",
    )
    if not service_account_email:
        raise SignedUrlError(
            "Could not determine the service account email for signed URL generation. "
            "Set GCS_SIGNING_SERVICE_ACCOUNT to the Agent Runtime service account."
        )
    return credentials, service_account_email


def _extension_for_mime_type(mime_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(mime_type, ".bin")
