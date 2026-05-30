#!/usr/bin/env bash
#
# =========================================================================
# Cloud Run Deployment Script for Gemini AI Infographics Agent Platform
# =========================================================================
#
# What this script does:
# ----------------------
# This script deploys the FastAPI web application frontend to Google Cloud Run,
# compiling and containerizing the local source code in the cloud.
#
# What we configure:
# ------------------
# 1. Environment Verification: Validates that required credentials (such as
#    passwords and secret keys) are set.
# 2. Config Injection: Bundles environment configurations (such as model IDs,
#    GCS buckets, and API settings) to pass to the running container.
# 3. Serverless Deployment: Deploys the service to Google Cloud Run with
#    CPU throttling disabled and startup/liveness probes configured.
#
# How to run this:
# ----------------
#   ./scripts/cloud-run-deployment.sh
#
# =========================================================================

set -euo pipefail

# 1. Ensure required environment variables are set.
# If they are not set, print a friendly error message and terminate the script.
: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project ID.}"
: "${REGION:=asia-northeast1}"
: "${SERVICE_NAME:=infographics-agent-demo}"
: "${APP_PASSWORD:?Set APP_PASSWORD to the demo login password.}"
: "${APP_SECRET_KEY:?Set APP_SECRET_KEY to a long random value.}"
: "${AGENT_BACKEND:=local}"
: "${GEMINI_TEXT_MODEL:=gemini-3.5-flash}"
: "${GEMINI_IMAGE_MODEL:=gemini-3-pro-image}"
: "${GOOGLE_CLOUD_LOCATION:=global}"
: "${ARTICLE_FETCH_MAX_BYTES:=2000000}"
: "${LOG_LEVEL:=INFO}"
: "${GCS_SIGNED_URL_TTL_SECONDS:=28800}"

# Helper function to prevent deploying with configuration placeholders.
reject_placeholder() {
  local name="$1"
  local value="$2"
  if [[ "${value}" == *PROJECT_NUMBER* || "${value}" == *RESOURCE_ID* || "${value}" == *SERVICE_AGENT_EMAIL_FROM_EFFECTIVE_IDENTITY* || "${value}" == *YOUR_PROJECT_ID* || "${value}" == *CHANGE_ME* ]]; then
    echo "ERROR: ${name} still contains a placeholder: ${value}" >&2
    echo "Replace placeholder values with the actual values from your project before deploying." >&2
    exit 1
  fi
}

reject_placeholder "PROJECT_ID" "${PROJECT_ID}"
reject_placeholder "APP_PASSWORD" "${APP_PASSWORD}"

# 2. Build the environment variables string.
# These environment variables will be injected into the container at startup.
ENV_VARS="APP_ENV=production,APP_PASSWORD=${APP_PASSWORD},APP_SECRET_KEY=${APP_SECRET_KEY},APP_LOG_FORMAT=json,LOG_LEVEL=${LOG_LEVEL},MOCK_MODE=false,AGENT_BACKEND=${AGENT_BACKEND},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION},GEMINI_TEXT_MODEL=${GEMINI_TEXT_MODEL},GEMINI_IMAGE_MODEL=${GEMINI_IMAGE_MODEL},ARTICLE_FETCH_MAX_BYTES=${ARTICLE_FETCH_MAX_BYTES},GCS_SIGNED_URL_TTL_SECONDS=${GCS_SIGNED_URL_TTL_SECONDS}"

# Conditionally append Agent Runtime reasoning engine parameters if they are set.
if [[ -n "${AGENT_RUNTIME_RESOURCE_NAME:-}" ]]; then
  reject_placeholder "AGENT_RUNTIME_RESOURCE_NAME" "${AGENT_RUNTIME_RESOURCE_NAME}"
  ENV_VARS="${ENV_VARS},AGENT_RUNTIME_RESOURCE_NAME=${AGENT_RUNTIME_RESOURCE_NAME},AGENT_RUNTIME_LOCATION=${AGENT_RUNTIME_LOCATION:-us-central1}"
fi

# Conditionally append Cloud Storage bucket parameters if configured.
if [[ -n "${GCS_BUCKET:-}" ]]; then
  reject_placeholder "GCS_BUCKET" "${GCS_BUCKET}"
  ENV_VARS="${ENV_VARS},GCS_BUCKET=${GCS_BUCKET},GCS_ARTIFACT_PREFIX=${GCS_ARTIFACT_PREFIX:-artifacts}"
fi

# Conditionally append the signing service account (used for generating GCS signed URLs).
if [[ -n "${GCS_SIGNING_SERVICE_ACCOUNT:-}" ]]; then
  reject_placeholder "GCS_SIGNING_SERVICE_ACCOUNT" "${GCS_SIGNING_SERVICE_ACCOUNT}"
  ENV_VARS="${ENV_VARS},GCS_SIGNING_SERVICE_ACCOUNT=${GCS_SIGNING_SERVICE_ACCOUNT}"
fi

# 3. Configure the active project in gcloud CLI.
gcloud config set project "${PROJECT_ID}"

# 4. Deploy the FastAPI app as a serverless container on Cloud Run.
# - --source .: Uploads the source code of the current folder and automatically builds the container image.
# - --allow-unauthenticated: Makes the web app publicly accessible.
# - --max-instances 1: Sets the auto-scaler limit to a single instance (ideal for cost control and demo usage).
# - --no-cpu-throttling: Ensures CPU is always allocated to handle background operations/polling smoothly.
# - --startup-probe & --liveness-probe: Configures health checks on the /healthz endpoint on port 8080.
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --region "${REGION}" \
  --allow-unauthenticated \
  --max-instances 1 \
  --no-cpu-throttling \
  --startup-probe "httpGet.path=/healthz,httpGet.port=8080,initialDelaySeconds=0,timeoutSeconds=2,periodSeconds=10,failureThreshold=3" \
  --liveness-probe "httpGet.path=/healthz,httpGet.port=8080,initialDelaySeconds=0,timeoutSeconds=2,periodSeconds=30,failureThreshold=3" \
  --set-env-vars "${ENV_VARS}"
