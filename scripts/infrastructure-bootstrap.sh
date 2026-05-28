#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project ID.}"
: "${REGION:=asia-northeast1}"

gcloud config set project "${PROJECT_ID}"

echo "Enabling required APIs for ${PROJECT_ID}..."
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

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "Checking default Cloud Run runtime service account..."
if ! gcloud iam service-accounts describe "${RUNTIME_SA}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  echo "WARNING: ${RUNTIME_SA} is not visible yet." >&2
  echo "Compute Engine API may still be provisioning the default service account." >&2
  echo "Wait 1-2 minutes, then rerun this script before deploying." >&2
fi

echo "Granting Cloud Run runtime service account permissions..."
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
