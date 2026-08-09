## Common Errors and Troubleshooting

Each infrastructure and deployment script (`scripts/infrastructure-bootstrap.sh`, `scripts/runtime-iam-config.sh`, `scripts/agent-runtime-deployment.py`, and `scripts/cloud-run-deployment.sh`) is designed to be idempotent. If a script execution fails, first check the error message details in your shell, then try re-running the command. If the issue persists, review the common error patterns and resolution steps below.

---

## Reading Application Errors

The application raises a small set of named error types (defined in `agent/errors.py`) instead of generic exceptions. The web UI translates each one into a plain-language message followed by a `Technical Details:` line that contains the underlying exception text. The error name in the technical details tells you which subsystem failed:

| Error type | What failed | Where to start |
| --- | --- | --- |
| `ConfigError` | Required configuration or credentials are missing or invalid (e.g. `GCS_BUCKET` unset, Gemini credentials absent, a placeholder left in the runtime resource name). | Fix the environment variable, then redeploy the affected service. |
| `ArticleFetchError` | The article body could not be retrieved: non-HTTP(S) scheme, unresolvable host, blocked private/reserved address, too many redirects, or a failed request. | Retry with a different public article URL. |
| `ArticleTooLargeError` | The article response exceeded `ARTICLE_FETCH_MAX_BYTES`. | Use a shorter article, or raise the byte cap and redeploy. |
| `GeminiError` | A Gemini text or image call failed after all retries, or its structured response could not be parsed. | Check Agent Runtime logs, model IDs, and quota. The pipeline usually degrades to heuristics or the fallback SVG rather than surfacing this. |
| `ArtifactStorageError` | Storing a generated artifact failed. | Check IAM on the bucket for Cloud Run and Agent Runtime. |
| `SignedUrlError` | The signed URL for a stored image could not be generated (credential load failure, or no signing service account resolved). | Re-run `scripts/runtime-iam-config.sh` and confirm `GCS_SIGNING_SERVICE_ACCOUNT`. |
| `RuntimeContractError` | The Agent Runtime response was missing or did not match the expected JSON contract. | Check the Reasoning Engine logs and redeploy the Agent Runtime. |

Errors that reach the browser also appear in Cloud Logging with a full traceback under `jsonPayload.exception`. See [Diagnostic Logs and Cost Analysis](06-LOG-AND-COST-ANALYSIS.md) for the log queries.

---

## Error Patterns and Resolutions

### Billing Account Not Enabled

**Symptoms:**
```text
Billing account for project ... is not found
UREQ_PROJECT_BILLING_NOT_FOUND
```

**Troubleshooting:**
Go to the Google Cloud Console and link an active billing account to your project.

---

### Cloud Run Source Deployment Fails with 403 Forbidden (`storage.objects.get` denied)

**Symptoms:**
```text
ERROR: (gcloud.run.deploy) INVALID_ARGUMENT: Invalid build request.
could not resolve source: googleapi: Error 403:
<PROJECT_NUMBER>-compute@developer.gserviceaccount.com does not have storage.objects.get access
to the Google Cloud Storage object.
```

**Troubleshooting:**
For Google Cloud projects created after April 2024, the default builder for `gcloud run deploy --source .` uses the Compute Engine default service account rather than the legacy Cloud Build service account. Consequently, it lacks permission to access the temporary source storage bucket, Artifact Registry, or Cloud Logging.

Re-running the latest version of `scripts/infrastructure-bootstrap.sh` will automatically grant the necessary permissions. If you are experiencing this error in an active project deployment, you can also resolve it immediately by running the following command:

```bash
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role "roles/cloudbuild.builds.builder"
```

---

### Python Version Incompatibility (Using Python 3.9 or older)

**Symptoms:**
```text
MCP requires Python 3.10 or above
module 'google.genai.types' has no attribute ...
```

**Troubleshooting:**
Verify your active python version by running `python3 --version`. If it is older than 3.10, install Python 3.10 or newer and recreate your virtual environment (`venv`).

---

### Missing `staging_bucket` Parameter

**Symptoms:**
```text
Please provide a `staging_bucket`
```

**Troubleshooting:**
Ensure you export the `GCS_BUCKET` and `AGENT_RUNTIME_STAGING_BUCKET` environment variables in your active shell before executing the `scripts/agent-runtime-deployment.py` deployment script.

---

### Reserved `GOOGLE_CLOUD_PROJECT` Environment Variable Error

**Symptoms:**
```text
Environment variable name 'GOOGLE_CLOUD_PROJECT' is reserved
```

**Troubleshooting:**
You should not pass `GOOGLE_CLOUD_PROJECT` as a custom environment variable configuration to the Agent Runtime. Make sure you are using the latest version of `scripts/agent-runtime-deployment.py`, which handles this configuration correctly.

---

### Model Not Found (404 Error)

**Symptoms:**
```text
Publisher Model ... locations/us-central1 ... gemini-3.5-flash was not found
```

**Troubleshooting:**
Verify that the `GOOGLE_CLOUD_LOCATION=global` environment variable is correctly configured for the Agent Runtime deployment, then redeploy the Agent Runtime.

---

### Empty Exception or Error Message in the Frontend UI

**Troubleshooting:**
Redeploy the Cloud Run service to get the latest revision. The current application codebase always renders something actionable: when an exception carries no message, the UI falls back to `An unexpected error occurred during processing.` plus a `Technical Details:` line containing the error class name and repr. The full stack traceback is written to Cloud Logging under `jsonPayload.exception`.

---

### Signed URL Access Denied (403 Error)

**Troubleshooting:**
Re-run `scripts/runtime-iam-config.sh`. Verify that the Cloud Run service account is authorized as a token creator (`roles/iam.serviceAccountTokenCreator`) on the Vertex AI Reasoning Engine's effective service account so it can sign resource URLs for the generated infographics.

If the message says the signing service account email could not be determined, export `GCS_SIGNING_SERVICE_ACCOUNT` (normally the same value as `CLOUD_RUN_SA`) and redeploy both the Agent Runtime and Cloud Run so the runtime receives it.

---

### Cloud Run Revision Fails to Start (`APP_PASSWORD` / `APP_SECRET_KEY` Required)

**Symptoms:**
```text
RuntimeError: APP_PASSWORD is required when running on Cloud Run or APP_ENV=production.
RuntimeError: APP_SECRET_KEY is required when running on Cloud Run or APP_ENV=production.
```
The revision never becomes healthy, and the `/healthz` startup probe fails.

**Troubleshooting:**
The application enforces authentication configuration whenever it detects a production environment (Cloud Run sets `K_SERVICE`, and `scripts/cloud-run-deployment.sh` sets `APP_ENV=production`). Export both `APP_PASSWORD` and `APP_SECRET_KEY` before running the deployment script. Reuse the original `APP_SECRET_KEY` on redeploys so existing login cookies stay valid.

---

### Placeholder Left in the Agent Runtime Resource Name

**Symptoms:**
```text
A placeholder remains in the Agent Runtime resource name.
AGENT_RUNTIME_RESOURCE_NAME still contains a placeholder.
Set AGENT_RUNTIME_RESOURCE_NAME when AGENT_BACKEND=runtime.
```

**Troubleshooting:**
Copy the actual `projects/.../locations/.../reasoningEngines/...` value printed by `python scripts/agent-runtime-deployment.py`, export it as `AGENT_RUNTIME_RESOURCE_NAME`, and redeploy Cloud Run.

Both `scripts/cloud-run-deployment.sh` and the runtime client reject values that still contain `PROJECT_NUMBER`, `RESOURCE_ID`, `SERVICE_AGENT_EMAIL_FROM_EFFECTIVE_IDENTITY`, `YOUR_PROJECT_ID`, `CHANGE_ME`, or `PASTE_HERE`, so an unedited value from the guide is caught before it reaches Vertex AI.

---

### Article Retrieval Fails on a Specific URL

**Symptoms:**
```text
Could not retrieve the article body. Try a publicly accessible article URL, or another URL.
Technical Details: Private, local, or reserved network addresses are not allowed
Technical Details: Only http and https URLs are allowed
Technical Details: URL host could not be resolved
```

**Troubleshooting:**
The fetcher only accepts public `http`/`https` URLs and rejects private, local, and reserved network addresses (including IP literals such as `127.0.0.1` and internal hostnames). Use a publicly reachable article URL. If the article is public but still fails, the site may block automated clients or the body may exceed `ARTICLE_FETCH_MAX_BYTES` — try one of the verified URLs in [Cloud Deployment and Local Testing](05-CLOUD-DEPLOYMENT-AND-LOCAL-TESTS.md) to confirm the deployment itself is healthy.

---

### A Plain SVG Appears Instead of a Generated Image

**Troubleshooting:**
This is the intended degradation path, not a crash. When mock mode is on, Gemini credentials are missing, or the image model call fails or returns an unusable result, the pipeline renders a deterministic fallback SVG infographic so the workflow still completes. Check the Agent Runtime logs for the recorded fallback reason, then verify `MOCK_MODE=false`, the image model ID, `GOOGLE_CLOUD_LOCATION=global`, and your Gemini image model quota.

---

### Missing Bucket for Agent Runtime Infographics

**Symptoms:**
```text
GCS_BUCKET is required for Agent Runtime infographics generation because
Cloud Run cannot serve files from the Agent Runtime filesystem.
```

**Troubleshooting:**
The Agent Runtime has no filesystem that Cloud Run can read from, so generated artifacts must go to Cloud Storage. Export `GCS_BUCKET` and re-run `python scripts/agent-runtime-deployment.py` so the bucket is injected into the runtime environment, then redeploy Cloud Run.
