#!/usr/bin/env bash
#
# =========================================================================
# Infrastructure Bootstrapping Script for Gemini AI Infographics Agent Platform
# =========================================================================
#
# What this script does:
# ----------------------
# This script configures and prepares your Google Cloud project for deploying
# the infographics agent reasoning engine and web frontend. It automates:
# 1. Setting the active project configuration for the gcloud CLI.
# 2. Enabling all necessary Google Cloud APIs required for serverless hosting,
#    Vertex AI Reasoning Engine execution, and build automation.
# 3. Provisioning and validating the default Cloud Run service account,
#    specifically granting the Vertex AI User ('roles/aiplatform.user') and
#    Cloud Build Builder ('roles/cloudbuild.builds.builder') roles.
# 4. Creating the Cloud Build Service Agent and granting it Cloud Run Builder
#    permissions ('roles/run.builder') to enable seamless source-based deployments.
#
# Checks/Actions Performed:
# -------------------------
# - Verifies that the required PROJECT_ID environment variable is set.
# - Automates API activation, verifying that default Cloud Run/Compute service accounts
#   are properly provisioned.
# - Applies standard security/IAM role assignments to default service accounts.
#
# How to run this:
# ----------------
# Set the PROJECT_ID environment variable before running the script:
#
#   PROJECT_ID="your-gcp-project-id" ./scripts/infrastructure-bootstrap.sh
#
# Optional overrides:
# - REGION: Override default Region (default: asia-northeast1). E.g.:
#   PROJECT_ID="your-gcp-project-id" REGION="us-central1" ./scripts/infrastructure-bootstrap.sh
#
# Notes:
# ------
# - Run this script once per Google Cloud project before attempting any deployments.
# - If you plan to use Cloud Storage (via GCS_BUCKET), ensure you grant the default
#   runtime service account Storage Object Admin permissions on that bucket.
# =========================================================================

# Exit immediately if a command exits with a non-zero status,
# treat unset variables as errors, and fail pipelines if any command fails.
set -euo pipefail

# Ensure the required PROJECT_ID environment variable is set, otherwise terminate.
: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project ID.}"
# Default the deployment region to 'asia-northeast1' if not overridden.
: "${REGION:=asia-northeast1}"

# Set the active project for the gcloud CLI. All subsequent commands will target this project.
gcloud config set project "${PROJECT_ID}"

echo "Enabling required APIs for ${PROJECT_ID}..."
# Enable the suite of Google Cloud APIs necessary for this PoC deployment:
# - serviceusage: Enables managing API enablement.
# - cloudresourcemanager: Enables project-level metadata operations.
# - iam & iamcredentials: Required for service account creation and token generation.
# - compute: Provisions the default Compute Engine service account.
# - logging: For centralizing application logs (Cloud Logging).
# - run: The serverless hosting platform where our Web frontend runs.
# - cloudbuild: Auto-builds container images for deployment.
# - artifactregistry: Stores built container images securely.
# - aiplatform: Powers Vertex AI and the Reasoning Engine runtime.
# - storage: Cloud Storage for storing generated infographics artifacts and assets.
gcloud services enable \
  serviceusage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  compute.googleapis.com \
  logging.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  storage.googleapis.com

# Fetch the unique project number needed to construct default service account emails.
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
# Define the default Compute Engine service account which Cloud Run uses as its identity.
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "Checking default Cloud Run runtime service account..."
# Verify that the default runtime service account has been created.
# API enablement (especially compute.googleapis.com) takes a moment to provision it.
if ! gcloud iam service-accounts describe "${RUNTIME_SA}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  echo "WARNING: ${RUNTIME_SA} is not visible yet." >&2
  echo "Compute Engine API may still be provisioning the default service account." >&2
  echo "Wait 1-2 minutes, then rerun this script before deploying." >&2
fi

echo "Granting Cloud Run runtime service account permissions..."
# Grant the default runtime service account access to Vertex AI resources (needed by the Agent).
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${RUNTIME_SA}" \
  --role "roles/aiplatform.user" \
  --quiet

# The Compute Engine default SA doubles as the Cloud Build worker for
# `gcloud run deploy --source .` in projects created after 2024-04, so it
# needs storage / Artifact Registry / Cloud Logging access via this bundle role.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${RUNTIME_SA}" \
  --role "roles/cloudbuild.builds.builder" \
  --quiet

# Configure Cloud Build service agent roles if needed, ensuring it can perform
# direct deployments to Cloud Run using source-based deployments.
if gcloud services identity create --service cloudbuild.googleapis.com --project "${PROJECT_ID}" >/dev/null 2>&1; then
  CLOUD_BUILD_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
  echo "Granting Cloud Build service agent Cloud Run builder permissions..."
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member "serviceAccount:${CLOUD_BUILD_SERVICE_AGENT}" \
    --role "roles/run.builder" \
    --quiet
else
  echo "WARNING: Could not create or confirm the Cloud Build service agent." >&2
  echo "If source deployment fails, check Cloud Build service account permissions." >&2
fi

echo "Bootstrap completed."
echo "Project: ${PROJECT_ID}"
echo "Project number: ${PROJECT_NUMBER}"
echo "Default Cloud Run runtime service account: ${RUNTIME_SA}"
echo
echo "If you use GCS_BUCKET, grant this runtime service account Storage Object Admin on the bucket or project."
echo "If a deploy fails immediately after API enablement, wait 1-2 minutes and retry."
