from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import vertexai

# Add project root directory to sys.path so we can import modules from 'agent'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.config import get_settings
from agent.runtime_entrypoint import root_agent


def required_env(name: str) -> str:
    """Helper function to fetch a required environment variable or exit if missing."""
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Error: Required environment variable '{name}' is not set.")
    return value


def gcs_uri(value: str) -> str:
    """Ensures a Google Cloud Storage bucket path is formatted correctly with a gs:// prefix."""
    return value if value.startswith("gs://") else f"gs://{value}"


def prepare_runtime_requirements_file(requirements_file: str, output_dir: Path) -> str:
    """Prepares the python dependency requirements file for the Agent Runtime.

    Reads the input requirements/constraints file, filters out comments and blank lines,
    and writes the clean dependency list into a temporary file for reasoning engine deployment.
    """
    source = Path(requirements_file)
    if not source.is_file():
        raise SystemExit(f"Requirements file does not exist: {requirements_file}")

    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / source.name
    dependency_lines = [
        line
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not dependency_lines:
        raise SystemExit(f"Requirements file has no dependencies: {requirements_file}")

    target.write_text("\n".join(dependency_lines) + "\n", encoding="utf-8")
    return str(target)


def main() -> None:
    settings = get_settings()

    # 1. Read and validate environment variables needed for Agent Runtime deployment
    project_id = required_env("PROJECT_ID")
    location = settings.agent_runtime_location
    display_name = settings.agent_display_name
    staging_bucket = gcs_uri(
        os.getenv("AGENT_RUNTIME_STAGING_BUCKET") or required_env("GCS_BUCKET")
    )
    # Default is constraints.txt
    requirements_file = settings.agent_runtime_requirements_file

    # 2. Package python requirements into a clean temporary file
    with tempfile.TemporaryDirectory(prefix="agent-runtime-requirements-") as temp_dir:
        runtime_requirements_file = prepare_runtime_requirements_file(
            requirements_file,
            Path(temp_dir),
        )

        # 3. Initialize Vertex AI client for Agent Engine registration
        client = vertexai.Client(project=project_id, location=location)

        # 4. Deploy/Register the reasoning engine (Agent Runtime)
        # This will package the ADK workflows (root_agent) and push them to Google Vertex AI.
        remote_agent = client.agent_engines.create(
            agent=root_agent,
            config={
                "display_name": display_name,
                "description": "Infographics PoC ADK agent.",
                "staging_bucket": staging_bucket,
                "requirements": runtime_requirements_file,
                "extra_packages": [
                    "agent"
                ],  # Packages the local 'agent' directory code
                "agent_framework": "google-adk",
                "env_vars": {
                    # Environment variables injected into the deployed Agent Runtime environment
                    "MOCK_MODE": "false",
                    "GOOGLE_GENAI_USE_VERTEXAI": "true",
                    "GOOGLE_CLOUD_LOCATION": settings.google_cloud_location or "global",
                    "GEMINI_TEXT_MODEL": settings.gemini_text_model,
                    "GEMINI_IMAGE_MODEL": settings.gemini_image_model,
                    "GCS_BUCKET": settings.gcs_bucket or "",
                    "GCS_ARTIFACT_PREFIX": settings.gcs_artifact_prefix,
                    "GCS_SIGNED_URL_TTL_SECONDS": str(
                        settings.gcs_signed_url_ttl_seconds
                    ),
                    "GCS_SIGNING_SERVICE_ACCOUNT": settings.gcs_signing_service_account
                    or "",
                    "ARTICLE_FETCH_MAX_BYTES": str(settings.article_fetch_max_bytes),
                    "GEMINI_MAX_ATTEMPTS": str(settings.gemini_max_attempts),
                    "GEMINI_RETRY_BASE_DELAY_SECONDS": str(
                        settings.gemini_retry_base_delay_seconds
                    ),
                },
                "min_instances": 0,
                "max_instances": 1,
            },
        )

    # 5. Print the resource name of the deployed Reasoning Engine
    # This value will look like: projects/<PROJECT_NUM>/locations/<LOCATION>/reasoningEngines/<ENGINE_ID>
    print(remote_agent.api_resource.name)

    # 6. Retrieve and print the Effective Identity (service account used by the runtime)
    # If returned, this identity must be granted the necessary IAM roles to sign GCS URLs and access GCS.
    spec = remote_agent.api_resource.spec if remote_agent.api_resource else None
    effective_identity = getattr(spec, "effective_identity", None)
    if effective_identity:
        print(f"effective_identity={effective_identity}")


if __name__ == "__main__":
    main()
