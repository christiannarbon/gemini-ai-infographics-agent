#!/usr/bin/env bash
#
# =========================================================================
# Preflight Validation Script for Gemini AI Infographics Agent Platform
# =========================================================================
#
# What this script does:
# ----------------------
# This script is a "health check" for your environment. It ensures that your
# local terminal or Google Cloud Shell is correctly configured, authenticated,
# and ready to deploy the Infographics Agent Platform.
#
# What we check:
# --------------
# 1. Environment variables (like your Google Cloud Project ID).
# 2. Local tools (gcloud CLI and Python 3.10+).
# 3. Google Cloud Authentication (login status and Application Default Credentials).
# 4. Project status and Billing enablement (required for Vertex AI and Cloud Run).
# 5. Enabled Google Cloud APIs (such as Vertex AI, Cloud Build, and Cloud Run).
#
# How to run this:
# ----------------
#   ./scripts/infographic-agent-preflight.sh
#
# Make sure to run 'export PROJECT_ID="your-project-id"' before running this.
#
# =========================================================================

set -euo pipefail

# -------------------------------------------------------------------------
# Step 1: Verify Environment Variables
# -------------------------------------------------------------------------
# We need to know which Google Cloud project you want to use. This is stored
# in the PROJECT_ID environment variable. If it's missing, we cannot proceed.

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "========================================================================="
  echo " ERROR: PROJECT_ID environment variable is not set."
  echo "========================================================================="
  echo " To deploy this application, you must specify your Google Cloud Project ID."
  echo " Please set it by running the following command in your terminal:"
  echo ""
  echo "   export PROJECT_ID=\"your-google-cloud-project-id\""
  echo ""
  echo " Hint: You can find your Project ID in the Google Cloud Console dashboard."
  echo "========================================================================="
  exit 1
fi

# Set default values for regional configurations if they are not already set.
# - REGION: The main location where Cloud Run and other resources will be deployed.
# - AGENT_RUNTIME_LOCATION: The region where the Gemini Agent Runtime will execute.
# - GCS_BUCKET: The Cloud Storage bucket that will store the generated infographics.
: "${REGION:=asia-northeast1}"
: "${AGENT_RUNTIME_LOCATION:=us-central1}"
: "${GCS_BUCKET:=${PROJECT_ID}-infographics-artifacts}"

# Track check failures. If this is greater than 0 at the end, the preflight fails.
failures=0

# -------------------------------------------------------------------------
# Helper Functions for Visual Feedback
# -------------------------------------------------------------------------

# Print a successful check result (green checkmark)
pass() {
  echo "  [PASS] $*"
}

# Print a non-blocking warning. The script will still pass.
warn() {
  echo "  [WARN] $*" >&2
}

# Print a critical failure. This will block successful preflight.
fail() {
  echo "  [FAIL] $*" >&2
  failures=$((failures + 1))
}

# Print a formatted section header to guide the user through the process
section() {
  echo
  echo "=================================================="
  echo " Checking: $*"
  echo "=================================================="
}

# Verify if a CLI command is installed and available in the user's PATH.
require_command() {
  local command_name="$1"
  if command -v "${command_name}" >/dev/null 2>&1; then
    pass "Command '${command_name}' is installed and ready."
  else
    fail "Command '${command_name}' was not found. Please install it on your system."
  fi
}

# -------------------------------------------------------------------------
# Start of Checks
# -------------------------------------------------------------------------

section "Target Project Configuration"
echo "We will use the following settings for the deployment:"
echo "  • Google Cloud Project ID:  ${PROJECT_ID}"
echo "  • Deployment Region:       ${REGION}"
echo "  • Agent Runtime Location:  ${AGENT_RUNTIME_LOCATION}"
echo "  • Infographics Storage:    gs://${GCS_BUCKET}"

# -------------------------------------------------------------------------
# Local CLI Tools Check
# -------------------------------------------------------------------------
# We need 'gcloud' to manage Google Cloud services, and 'python3' to run
# the local server and helper scripts.
# -------------------------------------------------------------------------
section "Local CLI Tools & Environments"
echo "Checking if the required tools are installed on your machine..."

require_command gcloud
require_command python3

# If Python is installed, check if it's a supported version (3.10 or newer)
if command -v python3 >/dev/null 2>&1; then
  # We run a small inline Python script to check the version programmatically.
  if python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
  then
    pass "Python version is compatible: $(python3 --version)"
  else
    fail "Python version is too old: $(python3 --version). We require Python 3.10 or newer."
  fi

  # Check if the 'venv' module is available. It is needed to create isolated
  # environments for dependencies so they don't conflict with system libraries.
  if python3 -m venv --help >/dev/null 2>&1; then
    pass "Python 'venv' module is installed and working."
  else
    fail "Python 'venv' module is missing. (On Linux/Ubuntu, install it with 'sudo apt-get install python3-venv')"
  fi
fi

# -------------------------------------------------------------------------
# Google Cloud Authentication Check
# -------------------------------------------------------------------------
# To deploy resources, the gcloud command needs permissions. We verify that
# you are logged in, pointing to the correct project, and have set up
# Application Default Credentials (ADC) for Python scripts.
# -------------------------------------------------------------------------
section "Google Cloud Authentication & Credentials"
echo "Verifying your Google Cloud login and API credentials..."

# Set the active project in gcloud config so commands target the correct project.
if gcloud config set project "${PROJECT_ID}" >/dev/null; then
  pass "gcloud CLI is set to project '${PROJECT_ID}'."
else
  fail "gcloud CLI failed to switch to project '${PROJECT_ID}'. Is the Project ID correct?"
fi

# Check if the user is authenticated in gcloud.
active_account="$(gcloud auth list --filter='status:ACTIVE' --format='value(account)' 2>/dev/null | head -n 1 || true)"
if [[ -n "${active_account}" ]]; then
  pass "You are logged in as: ${active_account}"
else
  fail "No active Google Cloud account found. Please log in by running: gcloud auth login"
fi

# Verify Application Default Credentials (ADC).
# Python code runs locally but needs to authenticate as you. ADC provides a secure
# temporary token so the local application can make Vertex AI/Gemini API calls.
if gcloud auth application-default print-access-token >/dev/null 2>&1; then
  pass "Application Default Credentials (ADC) are configured."
else
  fail "Application Default Credentials (ADC) are missing. Please log in by running: gcloud auth application-default login"
fi

# Set the quota project for ADC.
# Without this, calls to Gemini/Vertex AI from your local machine might be rejected
# with quota/billing errors because Google doesn't know which project to charge.
if gcloud auth application-default set-quota-project "${PROJECT_ID}" >/dev/null 2>&1; then
  pass "ADC quota project is set to '${PROJECT_ID}'."
else
  warn "Could not automatically set the ADC quota project. If you experience Gemini API errors later, run: gcloud auth application-default set-quota-project \"${PROJECT_ID}\""
fi

# -------------------------------------------------------------------------
# Google Cloud Project Status & Billing Check
# -------------------------------------------------------------------------
# We verify that the project actually exists and that billing is enabled.
# Vertex AI, Cloud Run, and Cloud Storage require a project with billing active.
# -------------------------------------------------------------------------
section "Google Cloud Project Status & Billing"
echo "Verifying if your project is active and has billing enabled..."

# Check if the project is accessible.
if project_number="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null)"; then
  pass "Project is active. Google Cloud Project Number is: ${project_number}"
else
  fail "Project '${PROJECT_ID}' could not be reached. Verify that the Project ID is spelled correctly and you have owner/editor permissions."
  project_number=""
fi

# Enable the billing service temporarily to check billing status.
gcloud services enable cloudbilling.googleapis.com --project="${PROJECT_ID}" >/dev/null 2>&1 || true

# Check if a billing account is linked to the project.
if billing_enabled="$(gcloud beta billing projects describe "${PROJECT_ID}" --format='value(billingEnabled)' 2>/dev/null)"; then
  if [[ "${billing_enabled}" == "True" || "${billing_enabled}" == "true" ]]; then
    pass "Billing is enabled on this project."
  else
    fail "Billing is NOT enabled. Vertex AI and Cloud Run require billing. Please link a billing account in the Google Cloud Console."
  fi
else
  fail "Could not verify billing status. Make sure you have the Billing Administrator role or check Console."
fi

# -------------------------------------------------------------------------
# Derived Environment Variables
# -------------------------------------------------------------------------
# These variables are calculated dynamically based on your project number.
# We display them here so you can copy them if you need to configure other scripts manually.
# -------------------------------------------------------------------------
section "Derived Environment Variables"
echo "Here are the environment variables generated from your project status."
echo "You can copy these if you ever need to set up variables manually:"
echo "------------------------------------------------------------------"
if [[ -n "${project_number}" ]]; then
  cloud_run_sa="${project_number}-compute@developer.gserviceaccount.com"
  echo "export PROJECT_NUMBER=\"${project_number}\""
  echo "export CLOUD_RUN_SA=\"${cloud_run_sa}\""
  echo "export GCS_SIGNING_SERVICE_ACCOUNT=\"${cloud_run_sa}\""
fi
echo "export GCS_BUCKET=\"${GCS_BUCKET}\""
echo "export AGENT_RUNTIME_STAGING_BUCKET=\"${GCS_BUCKET}\""
echo "------------------------------------------------------------------"

# -------------------------------------------------------------------------
# Required APIs Check
# -------------------------------------------------------------------------
# The Infographics Agent Platform relies on several Google Cloud APIs.
# We list them here and check if they are already enabled.
# -------------------------------------------------------------------------
section "Required Google Cloud APIs"
echo "Checking if the necessary Google Cloud APIs are enabled..."

required_apis=(
  serviceusage.googleapis.com          # Enables management of other APIs
  cloudresourcemanager.googleapis.com  # Required to query project metadata
  iam.googleapis.com                  # Required for identity and access management
  iamcredentials.googleapis.com       # Required for generating signed URLs
  compute.googleapis.com              # Enables compute services (required by Cloud Run service accounts)
  logging.googleapis.com              # Enables storing application logs
  run.googleapis.com                  # Hosts the Web Frontend application
  cloudbuild.googleapis.com           # Builds the container image for Cloud Run
  artifactregistry.googleapis.com     # Stores the built container images
  aiplatform.googleapis.com           # Connects to Vertex AI / Gemini models
  storage.googleapis.com              # Stores infographic images and templates
)

# Fetch the list of already enabled APIs in one go to keep it fast.
enabled_apis="$(gcloud services list --enabled --format='value(config.name)' 2>/dev/null || true)"
for api in "${required_apis[@]}"; do
  if grep -qx "${api}" <<<"${enabled_apis}"; then
    pass "API is enabled: ${api}"
  else
    # Non-blocking because our bootstrap script will enable these automatically.
    echo "  [INFO] API is not enabled yet: ${api} (Don't worry, the bootstrap/setup script will enable this for you!)"
  fi
done

# -------------------------------------------------------------------------
# Preflight Result Report
# -------------------------------------------------------------------------
if (( failures > 0 )); then
  echo
  echo "========================================================================="
  echo " PREFLIGHT VERIFICATION FAILED"
  echo "========================================================================="
  echo " We found ${failures} issue(s) that must be resolved before proceeding."
  echo " Please check the [FAIL] items listed above, fix them, and run this script again:"
  echo ""
  echo "   ./scripts/infographic-agent-preflight.sh"
  echo "========================================================================="
  exit 1
fi

cat <<'EOF'

=========================================================================
 PREFLIGHT PASSED!
=========================================================================
 Your environment is fully configured and ready!
 You can now safely run the bootstrap script to deploy the application.
=========================================================================
EOF
