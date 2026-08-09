# Agent Runtime Deployment Guide

This guide explains how to deploy the ADK Agent to Google Cloud's Agent Runtime (Vertex AI Reasoning Engine) and configure its IAM roles.

## What is Agent Runtime Deployment?

For beginners new to the project, here is what `python scripts/agent-runtime-deployment.py` does behind the scenes:
1. **Dependency Packaging**: It reads the Python requirements/constraints file (`AGENT_RUNTIME_REQUIREMENTS_FILE`, default `constraints.txt`), cleans it up, and prepares the necessary python dependencies.
2. **Code Uploading**: It packages the local `agent` package (including the `agent/tools/` modules: article fetcher, Gemini client, pipeline, prompts, storage, and the fallback SVG renderer) and uploads it along with dependencies to a staging Google Cloud Storage (GCS) bucket.
3. **Reasoning Engine Creation**: It registers the Agent on Google Cloud Vertex AI's **Reasoning Engine (Agent Runtime)** service.
4. **Environment Setup**: It configures the deployed Agent Runtime with runtime environment variables (such as target Gemini text/image models, storage buckets, and API configurations).
5. **Effective Identity Output**: It returns the unique identity (service account) used by the running engine so that it can be granted access to GCS and other resources.

The script no longer reads these settings from `os.getenv` one by one; it resolves them through the shared typed settings object in `agent/config.py`. In practice this means your `export` values and any `.env` file are both honored, and each value is validated before it is baked into the deployment.

### Environment Variables Injected into the Runtime

The script sends the following configuration into the deployed Agent Runtime environment. Values marked *fixed* are set by the script and cannot be overridden from your shell:

| Variable | Value |
| --- | --- |
| `MOCK_MODE` | `false` *(fixed)* |
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` *(fixed)* |
| `GOOGLE_CLOUD_LOCATION` | Your value, or `global` when unset |
| `GEMINI_TEXT_MODEL` / `GEMINI_IMAGE_MODEL` | Your values, or the defaults from `agent/config.py` |
| `GCS_BUCKET` / `GCS_ARTIFACT_PREFIX` | Artifact destination for generated infographics |
| `GCS_SIGNED_URL_TTL_SECONDS` / `GCS_SIGNING_SERVICE_ACCOUNT` | Signed URL lifetime and signing identity |
| `ARTICLE_FETCH_MAX_BYTES` | Article body byte cap |
| `GEMINI_MAX_ATTEMPTS` / `GEMINI_RETRY_BASE_DELAY_SECONDS` | Gemini retry attempts and backoff base delay |

> [!IMPORTANT]
> `GCS_BUCKET` must be set before the runtime generates infographics. Cloud Run cannot serve files from the Agent Runtime filesystem, so the runtime raises a configuration error ("GCS_BUCKET is required for Agent Runtime infographics generation") if the bucket is missing. Re-run this deployment script after setting the bucket.

---

## 1. Deploy the Agent Runtime

> [!NOTE]
> This command can take **10 to 15 minutes** to complete. Even if the output appears to pause or freeze, Google Cloud Build and Vertex AI are provisioning the runtime in the background. Please wait until the command completes or outputs an error.

If you run into issues or blockages during deployment, you can switch to Mock Mode to preview and test the web UI functionality locally.

Set up the required environment variables and run the deployment script:

```bash
export AGENT_DISPLAY_NAME="infographics-agent"
export AGENT_RUNTIME_STAGING_BUCKET="${GCS_BUCKET}"
export GCS_SIGNING_SERVICE_ACCOUNT="${CLOUD_RUN_SA}"
export GOOGLE_CLOUD_LOCATION="global"

python scripts/agent-runtime-deployment.py
```

Upon successful deployment, the script outputs two lines:

```text
projects/887643395015/locations/us-central1/reasoningEngines/1234567890123456789
effective_identity=service-887643395015@gcp-sa-aiplatform-re.iam.gserviceaccount.com
```

### Configure the Resource Name

Copy the `projects/.../locations/.../reasoningEngines/...` resource path from the first line of the output and export it as `AGENT_RUNTIME_RESOURCE_NAME`:

> [!WARNING]
> The project number and reasoning engine ID shown above are illustrative examples. You **must** copy and paste the actual resource name returned by your command.

```bash
# Paste the first line of the script output (projects/.../reasoningEngines/...)
export AGENT_RUNTIME_RESOURCE_NAME="PASTE_HERE"
```

### Configure IAM for the Effective Identity

**Only if** `effective_identity=...` is printed on the second line of the output, export it and run `configure-runtime-iam.sh` again to apply the required permissions. If this line is not printed, no additional IAM configurations are required, and you can proceed directly to the next section.

```bash
# Paste the email address following "effective_identity="
export AGENT_RUNTIME_EFFECTIVE_IDENTITY="PASTE_HERE"
./scripts/runtime-iam-config.sh
```

---

## Technical Notes

*   **Project Env Variable**: In the Agent Runtime deployment environment, `GOOGLE_CLOUD_PROJECT` is a reserved system name and should not be set manually.
*   **Gemini Location**: The Gemini model location is fixed as `GOOGLE_CLOUD_LOCATION=global`.
*   **Model Troubleshooting**: If you receive a `404` error for the `gemini-3.5-flash` model, check the Vertex AI Runtime logs, verify the model ID, or ask support staff for region availability.
