#!/usr/bin/env bash
#
# Preflight Validation Script for Gemini AI Infographics Agent Platform
#
# This script validates your local/Cloud Shell environment settings, tool installation,
# and Google Cloud authentication before bootstrapping the infrastructure.
#
set -euo pipefail

# --------------------------------------------------
# Environment Variable Checks
# --------------------------------------------------

# Ensure PROJECT_ID is set; provide a friendly error message if missing
if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "========================================================================="
  echo " Error: PROJECT_ID environment variable is not set."
  echo "-------------------------------------------------------------------------"
  echo " This script requires you to specify the target Google Cloud Project ID."
  echo " Please set it by running the following command in your terminal:"
  echo "   export PROJECT_ID=\"your-google-cloud-project-id\""
  echo "========================================================================="
  exit 1
fi

# Set default values for regional configurations if not already specified
: "${REGION:=asia-northeast1}"
: "${AGENT_RUNTIME_LOCATION:=us-central1}"
: "${GCS_BUCKET:=${PROJECT_ID}-infographics-artifacts}"

# Track check failures
failures=0

# --------------------------------------------------
# Helper Logging Functions
# --------------------------------------------------

# Print a successful check result
pass() {
  echo "  [✓] OK: $*"
}

# Print a non-blocking warning check result
warn() {
  echo "  [!] WARNING: $*" >&2
}

# Print a critical failure check result
fail() {
  echo "  [✗] FAILED: $*" >&2
  failures=$((failures + 1))
}

# Print a formatted section divider
section() {
  echo
  echo "--------------------------------------------------"
  echo " Checking: $*"
  echo "--------------------------------------------------"
}

# Check if a command line utility exists on PATH
require_command() {
  local command_name="$1"
  if command -v "${command_name}" >/dev/null 2>&1; then
    pass "Command '${command_name}' is installed."
  else
    fail "Command '${command_name}' is missing. Please install it to proceed."
  fi
}

# --------------------------------------------------
# Execution of Preflight Checks
# --------------------------------------------------

section "Target Project Configuration"
echo "Project ID:             ${PROJECT_ID}"
echo "Deployment Region:      ${REGION}"
echo "Agent Runtime Location: ${AGENT_RUNTIME_LOCATION}"
echo "Infographics Bucket:    gs://${GCS_BUCKET}"

section "Local CLI Tools & Environments"
require_command gcloud
require_command python3

# If python3 is available, verify the version and existence of venv module
if command -v python3 >/dev/null 2>&1; then
  # Python 3.10+ is required for the backend packages
  if python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
  then
    pass "python3 version is compatible: $(python3 --version)"
  else
    fail "python3 version is $(python3 --version). It must be 3.10 or newer."
  fi

  # The virtual environment module (venv) is essential for local isolation
  if python3 -m venv --help >/dev/null 2>&1; then
    pass "python3 'venv' module is available."
  else
    fail "python3 'venv' module is missing. (On Ubuntu/Debian, install it with 'sudo apt-get install python3-venv')"
  fi
fi

section "Google Cloud Authentication & Credentials"

# Verify that the gcloud configuration can use the specified Project ID
if gcloud config set project "${PROJECT_ID}" >/dev/null; then
  pass "Google Cloud project successfully set to '${PROJECT_ID}'."
else
  fail "Could not set Google Cloud project to '${PROJECT_ID}'. Please verify your PROJECT_ID."
fi

# Ensure there is an active authenticated user/service account
active_account="$(gcloud auth list --filter='status:ACTIVE' --format='value(account)' 2>/dev/null | head -n 1 || true)"
if [[ -n "${active_account}" ]]; then
  pass "Authenticated Google Cloud account: ${active_account}"
else
  fail "No active Google Cloud account found. Please log in by running: gcloud auth login"
fi

# Ensure Application Default Credentials (ADC) are configured for Python libraries
if gcloud auth application-default print-access-token >/dev/null 2>&1; then
  pass "Application Default Credentials (ADC) are configured."
else
  fail "Application Default Credentials (ADC) are missing. Please configure them by running: gcloud auth application-default login"
fi

# Try to set the ADC quota project to resolve Gemini API rate limiting/access issues
if gcloud auth application-default set-quota-project "${PROJECT_ID}" >/dev/null 2>&1; then
  pass "Application Default Credentials (ADC) quota project set to '${PROJECT_ID}'."
else
  warn "Could not configure the ADC quota project automatically. If API calls fail later, please run: gcloud auth application-default set-quota-project \"${PROJECT_ID}\""
fi

section "Google Cloud Project Status & Billing"

# Verify project access and retrieve project number
if project_number="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null)"; then
  pass "Google Cloud Project '${PROJECT_ID}' is accessible (Project Number: ${project_number})."
else
  fail "Google Cloud Project '${PROJECT_ID}' is not accessible. Verify that the Project ID is correct and you have permission to access it."
  project_number=""
fi

# Verify if billing is enabled (required for serverless & Gemini API access)
gcloud services enable cloudbilling.googleapis.com --project="${PROJECT_ID}" >/dev/null 2>&1 || true
if billing_enabled="$(gcloud beta billing projects describe "${PROJECT_ID}" --format='value(billingEnabled)' 2>/dev/null)"; then
  if [[ "${billing_enabled}" == "True" || "${billing_enabled}" == "true" ]]; then
    pass "Billing is active on Project '${PROJECT_ID}'."
  else
    fail "Billing is NOT active on Project '${PROJECT_ID}'. Please link a billing account in the Google Cloud Console."
  fi
else
  fail "Could not check billing status. Please check your account/project permissions or verify billing in the Google Cloud Console."
fi

section "Derived Environment Variables"
echo "You can copy and set the following environment variables for subsequent steps:"
echo "--------------------------------------------------"
if [[ -n "${project_number}" ]]; then
  cloud_run_sa="${project_number}-compute@developer.gserviceaccount.com"
  echo "export PROJECT_NUMBER=\"${project_number}\""
  echo "export CLOUD_RUN_SA=\"${cloud_run_sa}\""
  echo "export GCS_SIGNING_SERVICE_ACCOUNT=\"${cloud_run_sa}\""
fi
echo "export GCS_BUCKET=\"${GCS_BUCKET}\""
echo "export AGENT_RUNTIME_STAGING_BUCKET=\"${GCS_BUCKET}\""
echo "--------------------------------------------------"

section "Required Google Cloud APIs"
required_apis=(
  serviceusage.googleapis.com
  cloudresourcemanager.googleapis.com
  iam.googleapis.com
  iamcredentials.googleapis.com
  compute.googleapis.com
  logging.googleapis.com
  run.googleapis.com
  cloudbuild.googleapis.com
  artifactregistry.googleapis.com
  aiplatform.googleapis.com
  storage.googleapis.com
)

# Fetch currently enabled APIs
enabled_apis="$(gcloud services list --enabled --format='value(config.name)' 2>/dev/null || true)"
for api in "${required_apis[@]}"; do
  if grep -qx "${api}" <<<"${enabled_apis}"; then
    pass "API is already enabled: ${api}"
  else
    echo "  [INFO] API is not enabled yet: ${api} (The bootstrap script will automatically enable this)."
  fi
done

# --------------------------------------------------
# Report Results
# --------------------------------------------------
if (( failures > 0 )); then
  echo
  echo "========================================================================="
  echo " Preflight Check FAILED"
  echo "========================================================================="
  echo "We found ${failures} issue(s) that need your attention."
  echo "Please check the [✗] FAILED items listed above, resolve them, and rerun:"
  echo
  echo "  ./scripts/infographic-agent-preflight.sh"
  echo "========================================================================="
  exit 1
fi

cat <<'EOF'

=========================================================================
 Preflight Passed!
=========================================================================
All environment settings and authentications look good.
You are ready to proceed with bootstrapping and infra deployment!
=========================================================================
EOF
