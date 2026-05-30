#!/usr/bin/env bash
#
# =========================================================================
# Deployment Log Analysis Script for Gemini AI Infographics Agent Platform
# =========================================================================
#
# What this script does:
# ----------------------
# This script is a diagnostics utility designed to scan, analyze, and aggregate
# deployment settings and runtime execution logs from Google Cloud.
#
# What we check:
# --------------
# 1. Summary Scan: Quickly validates the status of Cloud Run service endpoints,
#    GCS buckets, Agent Runtime configurations, and recent log errors.
# 2. Config Details: Inspects environment configurations injected into Cloud Run
#    revisions (redacting sensitive passwords and keys).
# 3. Execution Timings: Queries Cloud Logging to analyze task durations (such as
#    generation and runtime engine call times).
# 4. Stream Logs: Retrieves the most recent execution logs directly from Cloud Run
#    revisions and Vertex AI Reasoning Engine tasks.
#
# How to run this:
# ----------------
#   ./scripts/deployment-log-analysis.sh
#
# =========================================================================

set -euo pipefail

# 1. Load configuration and defaults.
: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project ID.}"
: "${REGION:=asia-northeast1}"
: "${SERVICE_NAME:=infographics-agent-demo}"
: "${AGENT_RUNTIME_LOCATION:=us-central1}"
: "${GCS_BUCKET:=${PROJECT_ID}-infographics-artifacts}"

# Setup a temporary directory to download Cloud Run descriptions for analysis.
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

project_number="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null || true)"
cloud_run_json="${tmp_dir}/cloud-run.json"
cloud_run_status="not deployed"
cloud_run_url=""
cloud_run_revision=""
runtime_from_cloud_run=""
signer_from_cloud_run=""

# Helper function to check if a value still has unresolved placeholders.
looks_like_placeholder() {
  local value="$1"
  [[ "${value}" == *PROJECT_NUMBER* || "${value}" == *RESOURCE_ID* || "${value}" == *SERVICE_AGENT_EMAIL_FROM_EFFECTIVE_IDENTITY* || "${value}" == *YOUR_PROJECT_ID* || "${value}" == *CHANGE_ME* ]]
}

# 2. Inspect Cloud Run service configuration if deployed.
# Extracts environment variables and active endpoints using inline python parsing.
if gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format=json >"${cloud_run_json}" 2>/dev/null; then
  cloud_run_status="deployed"
  read -r cloud_run_url cloud_run_revision runtime_from_cloud_run signer_from_cloud_run < <(
    python3 - "${cloud_run_json}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)

env = {
    item.get("name"): item.get("value", "")
    for container in data.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    for item in container.get("env", [])
}

values = [
    data.get("status", {}).get("url", ""),
    data.get("status", {}).get("latestReadyRevisionName", ""),
    env.get("AGENT_RUNTIME_RESOURCE_NAME", ""),
    env.get("GCS_SIGNING_SERVICE_ACCOUNT", ""),
]
print("\t".join(values))
PY
  )
fi

# 3. Check Google Cloud Storage bucket existence.
agent_runtime_resource="${AGENT_RUNTIME_RESOURCE_NAME:-${runtime_from_cloud_run}}"
bucket_status="missing"
if gcloud storage buckets describe "gs://${GCS_BUCKET}" >/dev/null 2>&1; then
  bucket_status="exists"
fi

# 4. Check Agent Runtime (Reasoning Engine) deployment resource format.
runtime_status="not detected"
runtime_id=""
if [[ -n "${agent_runtime_resource}" ]]; then
  runtime_status="configured"
  runtime_id="${agent_runtime_resource##*/}"
  if looks_like_placeholder "${agent_runtime_resource}"; then
    runtime_status="placeholder value"
  fi
fi

# 5. Retrieve the most recent error log message from Google Cloud Logging within the last 5 minutes.
recent_error="$(
  gcloud logging read \
    'severity>=ERROR' \
    --project="${PROJECT_ID}" \
    --freshness=5m \
    --limit=1 \
    --format='value(timestamp,severity,textPayload,jsonPayload.message,jsonPayload.error)' 2>/dev/null \
    | head -n 1 || true
)"

# 6. Output the Diagnostics Summary
echo "=== SUMMARY ==="
echo "Project: ${PROJECT_ID}${project_number:+ (${project_number})}"
echo "Region: ${REGION}"
echo "Cloud Run: ${cloud_run_status}${cloud_run_revision:+ (revision: ${cloud_run_revision})}"
echo "Cloud Run URL: ${cloud_run_url:-n/a}"
echo "Agent Runtime: ${runtime_status}${runtime_id:+ (${runtime_id})}"
if [[ "${runtime_status}" == "placeholder value" ]]; then
  echo "Action required: set AGENT_RUNTIME_RESOURCE_NAME to the real projects/.../reasoningEngines/... value and redeploy Cloud Run."
fi
echo "Bucket: ${bucket_status} (gs://${GCS_BUCKET})"
echo "Signed URL signer: ${signer_from_cloud_run:-${GCS_SIGNING_SERVICE_ACCOUNT:-n/a}}"
echo "Last ERROR log in 5 min: ${recent_error:-none}"
echo

# 7. Output the Detailed Settings and Logs
echo "=== DETAILS ==="
echo
echo "[Cloud Run env]"
if [[ "${cloud_run_status}" == "deployed" ]]; then
  python3 - "${cloud_run_json}" <<'PY'
import json
import sys

redacted = {"APP_PASSWORD", "APP_SECRET_KEY"}
interesting = {
    "MOCK_MODE",
    "AGENT_BACKEND",
    "AGENT_RUNTIME_RESOURCE_NAME",
    "AGENT_RUNTIME_LOCATION",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GEMINI_TEXT_MODEL",
    "GEMINI_IMAGE_MODEL",
    "GCS_BUCKET",
    "GCS_ARTIFACT_PREFIX",
    "GCS_SIGNING_SERVICE_ACCOUNT",
    "ARTICLE_FETCH_MAX_BYTES",
}

with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)

env = {
    item.get("name"): item.get("value", "")
    for container in data.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    for item in container.get("env", [])
}

for name in sorted(interesting | redacted):
    if name in env:
        value = "[redacted]" if name in redacted else env[name]
        print(f"{name}={value}")
PY
else
  echo "Cloud Run service was not found."
fi

echo
echo "[Agent Runtime list]"
if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY' 2>/dev/null || echo "Could not list Agent Runtime. Activate .venv and install requirements first."
import os
import vertexai

project = os.environ["PROJECT_ID"]
location = os.environ.get("AGENT_RUNTIME_LOCATION", "us-central1")
client = vertexai.Client(project=project, location=location)
for agent in client.agent_engines.list():
    print(agent.api_resource.name, agent.api_resource.display_name)
PY
else
  echo "python3 is not available."
fi

echo
echo "[Recent duration logs]"
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="'"${SERVICE_NAME}"'" AND (textPayload:"job_duration" OR textPayload:"runtime_call_duration")' \
  --project="${PROJECT_ID}" \
  --freshness=30m \
  --limit=20 \
  --format='value(timestamp,textPayload)' 2>/dev/null || true
if [[ -n "${runtime_id}" ]]; then
  gcloud logging read \
    'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND resource.labels.reasoning_engine_id="'"${runtime_id}"'" AND textPayload:"workflow_duration"' \
    --project="${PROJECT_ID}" \
    --freshness=30m \
    --limit=20 \
    --format='value(timestamp,textPayload)' 2>/dev/null || true
fi

echo
echo "[Recent Cloud Run logs]"
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="'"${SERVICE_NAME}"'"' \
  --project="${PROJECT_ID}" \
  --freshness=15m \
  --limit=10 \
  --format='value(timestamp,severity,textPayload,jsonPayload.message,jsonPayload.error)' 2>/dev/null || true

echo
echo "[Recent Agent Runtime logs]"
if [[ -n "${runtime_id}" ]]; then
  gcloud logging read \
    'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND resource.labels.reasoning_engine_id="'"${runtime_id}"'"' \
    --project="${PROJECT_ID}" \
    --freshness=15m \
    --limit=10 \
    --format='value(timestamp,textPayload)' 2>/dev/null || true
else
  echo "AGENT_RUNTIME_RESOURCE_NAME is not set and Cloud Run does not expose one."
fi
