#!/usr/bin/env bash
#
# =========================================================================
# Resource Cleanup Script for Gemini AI Infographics Agent Platform
# =========================================================================
#
# What this script does:
# ----------------------
# This script is designed to safely tear down and delete all provisioned
# Google Cloud resources created for this PoC deployment. This is crucial
# to avoid incurring unexpected, ongoing Google Cloud billing charges.
#
# What we delete:
# ---------------
# 1. Cloud Run service: The serverless web application hosting the frontend.
# 2. Cloud Storage bucket: The storage location where generated infographics
#    and agent dependencies are saved.
# 3. Agent Runtime: The deployed ADK Agent Reasoning Engine on Vertex AI.
#
# How to run this:
# ----------------
#   ./scripts/resource-cleanup.sh
#
# By default, the script asks for manual confirmation. You can bypass
# confirmation using the --yes or -y flag:
#
#   ./scripts/resource-cleanup.sh --yes
#
# =========================================================================

set -euo pipefail

# Parse command line arguments for the --yes or -y confirmation bypass flag.
yes="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y)
      yes="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--yes]" >&2
      exit 2
      ;;
  esac
done

# Load configuration and default values.
: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project ID.}"
: "${REGION:=asia-northeast1}"
: "${SERVICE_NAME:=infographics-agent-demo}"
: "${AGENT_RUNTIME_LOCATION:=us-central1}"
: "${GCS_BUCKET:=${PROJECT_ID}-infographics-artifacts}"

# Display target deletion overview.
cat <<EOF
This will delete PoC resources in project ${PROJECT_ID}:

- Cloud Run service: ${SERVICE_NAME} (${REGION})
- Cloud Storage bucket: gs://${GCS_BUCKET}
- Agent Runtime: ${AGENT_RUNTIME_RESOURCE_NAME:-not set; skipped}

This script does NOT delete the Google Cloud project itself.
EOF

# Prompt user for confirmation unless bypassed using --yes or SKIP_CONFIRM="yes".
if [[ "${yes}" != "true" && "${SKIP_CONFIRM:-}" != "yes" ]]; then
  echo
  read -r -p "Type 'delete' to confirm: " confirm
  if [[ "${confirm}" != "delete" ]]; then
    echo "Cleanup cancelled."
    exit 1
  fi
fi

echo
# 1. Delete the Google Cloud Run service.
echo "Deleting Cloud Run service if it exists..."
gcloud run services delete "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --quiet >/dev/null 2>&1 || true

# 2. Delete the GCS storage bucket and all its contents (summaries, infographics, cache).
echo "Deleting Cloud Storage bucket if it exists..."
gcloud storage rm --recursive "gs://${GCS_BUCKET}" >/dev/null 2>&1 || true

# 3. Delete the deployed reasoning engine (Agent Runtime) using the Vertex AI client.
if [[ -n "${AGENT_RUNTIME_RESOURCE_NAME:-}" ]]; then
  echo "Deleting Agent Runtime..."
  python3 - <<'PY'
import os
import vertexai

client = vertexai.Client(
    project=os.environ["PROJECT_ID"],
    location=os.environ.get("AGENT_RUNTIME_LOCATION", "us-central1"),
)
client.agent_engines.delete(
    name=os.environ["AGENT_RUNTIME_RESOURCE_NAME"],
    force=True,
)
print(f"Deleted {os.environ['AGENT_RUNTIME_RESOURCE_NAME']}")
PY
else
  echo "AGENT_RUNTIME_RESOURCE_NAME is not set; skipping Agent Runtime deletion."
fi

# Print final instructions.
cat <<'EOF'

Cleanup completed.

If this was a disposable PoC project, delete the project separately from
Google Cloud Console or with:

  gcloud projects delete "${PROJECT_ID}"

Only delete the project if you are certain it contains no resources you need.
EOF
