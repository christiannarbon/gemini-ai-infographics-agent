#!/usr/bin/env bash
#
# =========================================================================
# Publication Safety Validation Script
# =========================================================================
#
# What this script does:
# ----------------------
# This script is a safety check run prior to publishing or sharing the code
# (e.g. to public GitHub, open-source directories, or external stakeholders).
# It scans the project repository to ensure that no credentials, private keys,
# or sensitive environment files are accidentally tracked or hardcoded.
#
# What we check:
# --------------
# 1. Git tracking of .env: Ensures the local environment file '.env' is NOT
#    tracked by Git (to prevent uploading sensitive credentials).
# 2. Key ignore files: Confirms that '.dockerignore' and '.gcloudignore' exist
#    so build processes do not upload local secrets/credentials.
# 3. Code secrets scan: Recursively searches project code (.py, .html, .md, .sh)
#    for hardcoded Google API Keys (AIza...) or private keys.
#
# =========================================================================

set -euo pipefail

# -------------------------------------------------------------------------
# Step 1: Verify .env is not tracked by Git
# -------------------------------------------------------------------------
# Local environment variables containing passwords and secret keys are stored
# in '.env'. This file must remain ignored by git.
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo "ERROR: The '.env' file is tracked by git. Please remove it from git history before publishing." >&2
  exit 1
fi

# -------------------------------------------------------------------------
# Step 2: Confirm ignore files exist
# -------------------------------------------------------------------------
# Build systems (Docker and Cloud Build) require ignore files to prevent
# copying local credential files (.env, .venv) into build images.
if [[ ! -f .dockerignore ]]; then
  echo "ERROR: '.dockerignore' is missing from the project root." >&2
  exit 1
fi

if [[ ! -f .gcloudignore ]]; then
  echo "ERROR: '.gcloudignore' is missing from the project root." >&2
  exit 1
fi

# -------------------------------------------------------------------------
# Step 3: Scan code files for hardcoded API keys and private keys
# -------------------------------------------------------------------------
# Performs a regex-based search for Google API keys (AIza...) and private keys.
# Excludes development folders like .venv, pytest caches, and infographics artifacts.
if grep -R --line-number \
  --exclude-dir=.git \
  --exclude-dir=.venv \
  --exclude-dir='.venv-*' \
  --exclude-dir=.pytest_cache \
  --exclude-dir=__pycache__ \
  --exclude-dir=artifacts \
  --include='*.py' --include='*.html' --include='*.md' --include='*.sh' \
  -E 'AIza[0-9A-Za-z_-]{35}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----' .; then
  echo "ERROR: Potential secret or private key found. Inspect the lines listed above." >&2
  exit 1
fi

echo "Publication safety checks passed. The repository is clean and ready for public sharing."
