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

### How Configuration is Loaded

Both the web app and the agent read configuration through a single typed settings object (`agent/config.py`, built on `pydantic-settings`). You do not need to know the internals, but two behaviors matter when you set things up:

*   **`.env` file support**: Settings are loaded from a `.env` file in the repository root if one exists. Copy `.env.example` to `.env` for local development instead of re-exporting shell variables in every new terminal.
*   **Shell variables win**: Real environment variables take priority over values in `.env`, so the `export` commands above (and the variables that Cloud Run and Agent Runtime inject) always override the file.

Every setting has a safe default and is range-checked, so a malformed value falls back to the default instead of crashing at startup. For example, `ARTICLE_FETCH_MAX_BYTES` is clamped to a minimum of 1024, `GEMINI_MAX_ATTEMPTS` to a minimum of 1, and both TTL values to a minimum of 60 seconds.

> [!NOTE]
> `AGENT_RUNTIME_URL` is no longer used. The web app addresses the deployed agent solely through `AGENT_RUNTIME_RESOURCE_NAME` (and `AGENT_RUNTIME_LOCATION`). Remove `AGENT_RUNTIME_URL` from any older `.env` file you may be carrying over.

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

---

## 3. Optional Tuning Variables

The variables below are optional. Defaults are shown, and you only need to set them if you want to change the behavior. All of them can also be placed in `.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENT_BACKEND` | `local` | Selects the execution backend: `local` (in-process tool pipeline), `adk` (adds an ADK narration turn before the local pipeline), or `runtime` (calls the deployed Agent Runtime). |
| `MOCK_MODE` | `true` | When `true`, the pipeline returns canned results and the fallback SVG instead of calling Gemini. Deployment scripts force this to `false`. |
| `MOCK_STEP_DELAY` | `0.45` | Artificial per-step delay (seconds) in mock mode so progress screens are observable. |
| `GEMINI_MAX_ATTEMPTS` | `3` | Number of attempts per Gemini call before the pipeline falls back. |
| `GEMINI_RETRY_BASE_DELAY_SECONDS` | `0.6` | Base delay for the exponential backoff between Gemini retries. |
| `LOG_LEVEL` | `INFO` | Python log level for the web app. |
| `APP_LOG_FORMAT` | `json` | `json` emits structured logs for Cloud Logging; any other value emits plain text, which is easier to read locally. |
| `APP_ENV` | *(empty)* | Set to `production` to enforce the production auth checks outside Cloud Run. On Cloud Run this is detected automatically from `K_SERVICE`. |
| `AUTH_COOKIE_MAX_AGE_SECONDS` | `28800` | Lifetime of the signed login cookie. |
| `AGENT_RUNTIME_USER_ID` | `poc-user` | User ID sent with Agent Runtime session calls. |
| `AGENT_RUNTIME_REQUIREMENTS_FILE` | `constraints.txt` | Dependency file packaged into the Agent Runtime deployment. |
| `ARTIFACT_DIR` | `artifacts` | Local directory for generated artifacts, also served at `/artifacts` by the web app. |
| `GOOGLE_GENAI_USE_VERTEXAI` | `false` | Use Vertex AI with ADC instead of an API key. Deployment scripts force this to `true`. |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | *(empty)* | Gemini Developer API key for local runs without Vertex AI. Not needed for the Cloud Run / Agent Runtime deployment path. |
