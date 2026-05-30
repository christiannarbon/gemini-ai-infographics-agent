## Common Errors and Troubleshooting

Each infrastructure and deployment script (`scripts/infrastructure-bootstrap.sh`, `scripts/runtime-iam-config.sh`, `scripts/agent-runtime-deployment.py`, and `scripts/cloud-run-deployment.sh`) is designed to be idempotent. If a script execution fails, first check the error message details in your shell, then try re-running the command. If the issue persists, review the common error patterns and resolution steps below.

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
Redeploy the Cloud Run service to get the latest revision. The current application codebase is configured to output the error class/type name even if the exception message details are empty, and it will output the full stack traceback to Cloud Logging for easier inspection.

---

### Signed URL Access Denied (403 Error)

**Troubleshooting:**
Re-run `scripts/runtime-iam-config.sh`. Verify that the Cloud Run service account is authorized as a token creator (`roles/iam.serviceAccountTokenCreator`) on the Vertex AI Reasoning Engine's effective service account so it can sign resource URLs for the generated infographics.
