import pytest

from agent.tools.storage import (
    _extension_for_mime_type,
    signed_artifact_url_ttl_seconds,
    artifact_url_for_path,
)


@pytest.mark.unit
def test_extension_for_mime_type():
    assert _extension_for_mime_type("image/png") == ".png"
    assert _extension_for_mime_type("image/jpeg") == ".jpg"
    assert _extension_for_mime_type("image/webp") == ".webp"
    assert _extension_for_mime_type("application/pdf") == ".bin"
    assert _extension_for_mime_type("unknown") == ".bin"


@pytest.mark.unit
def test_signed_artifact_url_ttl_seconds(set_env):
    # Clamps values below 60 up to 60
    set_env("GCS_SIGNED_URL_TTL_SECONDS", "30")
    assert signed_artifact_url_ttl_seconds() == 60

    # Values >= 60 are kept
    set_env("GCS_SIGNED_URL_TTL_SECONDS", "60")
    assert signed_artifact_url_ttl_seconds() == 60
    set_env("GCS_SIGNED_URL_TTL_SECONDS", "180")
    assert signed_artifact_url_ttl_seconds() == 180

    # Falls back to default (28800) on invalid value
    set_env("GCS_SIGNED_URL_TTL_SECONDS", "not-a-number")
    assert signed_artifact_url_ttl_seconds() == 28800


@pytest.mark.unit
def test_artifact_url_for_path():
    assert (
        artifact_url_for_path("some/path/to/my_image.png") == "/artifacts/my_image.png"
    )
    assert artifact_url_for_path("/absolute/path/file.svg") == "/artifacts/file.svg"
    assert artifact_url_for_path("filename.webp") == "/artifacts/filename.webp"
