## 1. Clone the Repository

```bash
git clone https://github.com/christiannarbon/gemini-ai-infographics-agent.git
cd gemini-ai-infographics-agent
```

Check your Python version:

```bash
python3 --version
```

Enable the virtual environment (`venv`) and install the required dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt -c constraints.txt
```

The `constraints.txt` file is used to ensure consistent, pinned versions across Cloud Shell, Cloud Run, and Agent Runtime builds.

## 2. Configure Environment Variables

Replace `YOUR_PROJECT_ID` with your own Google Cloud project ID. Set `APP_PASSWORD` to your desired secure password for the web application.

```bash
export PROJECT_ID="YOUR_PROJECT_ID"
export REGION="asia-northeast1"
export AGENT_RUNTIME_LOCATION="us-central1"
export GOOGLE_CLOUD_LOCATION="global"

export SERVICE_NAME="infographics-agent"
export APP_PASSWORD="CHANGE_ME_TO_YOUR_PASSWORD"
export APP_SECRET_KEY="$(openssl rand -hex 32)"

export GEMINI_TEXT_MODEL="gemini-3.5-flash"
export GEMINI_IMAGE_MODEL="gemini-3-pro-image"
export ARTICLE_FETCH_MAX_BYTES="2000000"

export GCS_BUCKET="${PROJECT_ID}-infographics-artifacts"
export AGENT_RUNTIME_STAGING_BUCKET="${GCS_BUCKET}"
export GCS_ARTIFACT_PREFIX="artifacts"
export GCS_SIGNED_URL_TTL_SECONDS="28800"
```

Verify the project configuration and authentication status of the `gcloud` CLI:

```bash
gcloud config set project "${PROJECT_ID}"
gcloud auth list
gcloud config get-value account
```

If `gcloud config get-value account` is empty or displays an incorrect Google account, run the following commands to authenticate:

```bash
gcloud auth login
gcloud config set account "YOUR_EMAIL"
```

Next, configure the Application Default Credentials (ADC) used by the Python SDK and Google client libraries:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project "${PROJECT_ID}"
gcloud auth application-default print-access-token >/dev/null && echo "ADC ok"
gcloud beta billing projects describe "${PROJECT_ID}"
```

> [!IMPORTANT]
> If `billingEnabled: true` is not shown, please link a billing account to your project in the Google Cloud Console before proceeding.

Next, run the preflight verification script to ensure everything has been set up correctly:

```bash
./scripts/infographic-agent-preflight.sh
```

**If you see `Preflight passed.`, the verification was successful!**

If the `infographic-agent-preflight.sh` script fails, resolve the reported `[NG]` (No Good / Failed) items and run it again. The preflight check also verifies your Python version and the presence of the `venv` module.
