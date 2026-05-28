#!/usr/bin/env bash
#
# =========================================================================
# Runtime IAM Permissions Configuration Script
# =========================================================================
#
# What this script does:
# ----------------------
# This script sets up permissions (IAM roles) in your Google Cloud Project.
# It ensures that:
# 1. Your Cloud Run web app can access and sign storage URLs.
# 2. The Vertex AI Agent Runtime can write generated infographics to your bucket.
# 3. Google's internal Vertex AI agents can sign files on your behalf.
#
# Prerequisite:
# -------------
# You must set the PROJECT_ID and GCS_BUCKET environment variables before running:
#   export PROJECT_ID="your-project-id"
#   export GCS_BUCKET="your-project-id-infographics-artifacts"
#   ./scripts/runtime-iam-config.sh
#
# =========================================================================

set -euo pipefail

# -------------------------------------------------------------------------
# Helper Functions for Visual Logging
# -------------------------------------------------------------------------
pass() {
  echo "  [PASS] $*"
}

warn() {
  echo "  [WARN] $*" >&2
}

fail() {
  echo "  [FAIL] $*" >&2
  exit 1
}

info() {
  echo "  [INFO] $*"
}

section() {
  echo
  echo "=================================================="
  echo " $*"
  echo "=================================================="
}

# -------------------------------------------------------------------------
# Step 1: Verify Input Environment Variables
# -------------------------------------------------------------------------

# Ensure PROJECT_ID is configured
if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "========================================================================="
  echo " ERROR: PROJECT_ID environment variable is not set."
  echo "========================================================================="
  echo " Please set it by running:"
  echo "   export PROJECT_ID=\"your-google-cloud-project-id\""
  echo "========================================================================="
  exit 1
fi

# Ensure GCS_BUCKET is configured
if [[ -z "${GCS_BUCKET:-}" ]]; then
  echo "========================================================================="
  echo " ERROR: GCS_BUCKET environment variable is not set."
  echo "========================================================================="
  echo " Please run the preflight script first, or set it manually by running:"
  echo "   export GCS_BUCKET=\"\${PROJECT_ID}-infographics-artifacts\""
  echo "========================================================================="
  exit 1
fi

# Fetch Project Number (necessary for forming the service account names)
info "Fetching Project Number for project '${PROJECT_ID}'..."
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null || true)"
if [[ -z "${PROJECT_NUMBER}" ]]; then
  fail "Could not retrieve the project number. Check your PROJECT_ID and gcloud login."
fi

# Determine the Cloud Run Service Account (defaults to Compute Engine default service account)
CLOUD_RUN_SA="${CLOUD_RUN_SA:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"

# Display active target settings
section "Target Configuration Settings"
echo "  • Google Cloud Project ID:          ${PROJECT_ID}"
echo "  • Google Cloud Project Number:      ${PROJECT_NUMBER}"
echo "  • Infographics Storage Bucket:      gs://${GCS_BUCKET}"
echo "  • Cloud Run Service Account:        ${CLOUD_RUN_SA}"

# -------------------------------------------------------------------------
# Step 2: Initialize Vertex AI Service Identity
# -------------------------------------------------------------------------
# Google Cloud creates a default, internal service account for Vertex AI when
# the API is used. We explicitly trigger its creation to make sure it exists
# before assigning permission policies.
# -------------------------------------------------------------------------
section "Initializing Vertex AI Service Identity"
info "Ensuring the Vertex AI service agent is created..."

if gcloud beta services identity create \
  --service=aiplatform.googleapis.com \
  --project="${PROJECT_ID}" \
  --quiet >/dev/null 2>&1 || true; then
  pass "Vertex AI service identity confirmed/created."
else
  warn "Could not verify Vertex AI identity creation. (This is normal if it already exists or if you lack identity creation permissions)."
fi

# Define the identities representing Vertex AI runtime agents that require bucket access
RUNTIME_IDENTITIES=(
  "service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com"
  "service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
)

# If an additional custom identity is defined for the agent runtime, append it to the list
if [[ -n "${AGENT_RUNTIME_EFFECTIVE_IDENTITY:-}" ]]; then
  info "Custom runtime identity detected: ${AGENT_RUNTIME_EFFECTIVE_IDENTITY}"
  RUNTIME_IDENTITIES+=("${AGENT_RUNTIME_EFFECTIVE_IDENTITY}")
fi

# -------------------------------------------------------------------------
# Step 3: Grant Cloud Run Storage Access
# -------------------------------------------------------------------------
# The Cloud Run web application needs permissions to read and list generated
# infographic images inside the Cloud Storage bucket.
# -------------------------------------------------------------------------
section "Granting Web App Storage Access"
info "Granting Object Admin permissions to Cloud Run Service Account..."

if gcloud storage buckets add-iam-policy-binding "gs://${GCS_BUCKET}" \
  --member "serviceAccount:${CLOUD_RUN_SA}" \
  --role "roles/storage.objectAdmin" \
  --quiet >/dev/null; then
  pass "Cloud Run Service Account '${CLOUD_RUN_SA}' granted Admin access to bucket."
else
  fail "Could not grant bucket permissions to Cloud Run Service Account. Do you have Owner/IAM Admin permissions?"
fi

# -------------------------------------------------------------------------
# Step 4: Grant Vertex AI Agents Storage and Signer Permissions
# -------------------------------------------------------------------------
# For each Vertex AI runtime agent identity:
# 1. Grant GCS Storage Object Admin access so it can save infographic files.
# 2. Grant the Token Creator role on the Cloud Run service account so it can sign URLs.
# -------------------------------------------------------------------------
section "Configuring Runtime Agent Permissions"

for runtime_identity in "${RUNTIME_IDENTITIES[@]}"; do
  info "Configuring permissions for agent: ${runtime_identity}"
  
  # 1. Bucket access
  if gcloud storage buckets add-iam-policy-binding "gs://${GCS_BUCKET}" \
    --member "serviceAccount:${runtime_identity}" \
    --role "roles/storage.objectAdmin" \
    --quiet >/dev/null 2>&1 || true; then
    pass "Granted Object Admin on bucket to: ${runtime_identity}"
  else
    warn "Could not grant bucket permissions to ${runtime_identity}. (You might need to rerun with higher permissions)."
  fi

  # 2. Service Account Token Creator permission
  # This allows the AI agent runtime to generate temporary signed URLs for private images.
  if gcloud iam service-accounts add-iam-policy-binding "${CLOUD_RUN_SA}" \
    --member "serviceAccount:${runtime_identity}" \
    --role "roles/iam.serviceAccountTokenCreator" \
    --quiet >/dev/null 2>&1 || true; then
    pass "Granted Service Account Token Creator on ${CLOUD_RUN_SA} to: ${runtime_identity}"
  else
    warn "Could not grant Token Creator role to ${runtime_identity}."
  fi
done

# -------------------------------------------------------------------------
# Step 5: Finish
# -------------------------------------------------------------------------
section "Configuration Completed Successfully"
echo "Make sure the following variables are active in your deployment environment:"
echo "------------------------------------------------------------------"
echo "export CLOUD_RUN_SA=\"${CLOUD_RUN_SA}\""
echo "export GCS_SIGNING_SERVICE_ACCOUNT=\"${CLOUD_RUN_SA}\""
echo "------------------------------------------------------------------"
