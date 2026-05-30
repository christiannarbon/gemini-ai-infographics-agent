# Diagnostic Logs and Cost Analysis Guide

This guide explains how to inspect deployment logs, troubleshoot errors, and monitor Google Cloud service costs.

## What is Log and Cost Analysis?

For beginners new to the project, here is what this step helps you do:
1. **Unified Diagnostics**: Instead of checking multiple separate GCP console tabs, the diagnostic script `scripts/deployment-log-analysis.sh` aggregates configuration status, Cloud Run revision info, GCS bucket existence, and recent errors into a single terminal output.
2. **Cloud Run Logs**: Retrieves recent execution logs of the FastAPI web container to trace HTTP requests, login attempts, and client-side HTMX polls.
3. **Agent Runtime Logs**: Inspects the Vertex AI Reasoning Engine execution logs to debug prompt narration, style classification, image model requests, and signed URL generation issues.
4. **Billing Audits**: Guides you on how to check real-time billing metrics to ensure you clean up unused resources and avoid unwanted GCP charges.

---

## 1. Diagnostics and Log Inspection

To run a full diagnostic scan of your deployment, execute the following script:

```bash
./scripts/deployment-log-analysis.sh
```

The script prints a `SUMMARY` section at the top to help quickly isolate issues with Cloud Run, Agent Runtime, GCS buckets, and recent errors. The `DETAILS` section follows to provide raw execution details.

### Inspecting Cloud Run Logs

To view logs specifically for the Cloud Run frontend container, run:

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="'"${SERVICE_NAME}"'"' \
  --project="${PROJECT_ID}" \
  --limit=100 \
  --format='value(timestamp,severity,textPayload,jsonPayload.message,jsonPayload.error)'
```

### Inspecting Agent Runtime Logs

To view logs for the Vertex AI Reasoning Engine execution backend, run:

```bash
RUNTIME_ID="$(echo "${AGENT_RUNTIME_RESOURCE_NAME}" | awk -F/ '{print $NF}')"
gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND resource.labels.reasoning_engine_id="'"${RUNTIME_ID}"'"' \
  --project="${PROJECT_ID}" \
  --limit=100 \
  --format='value(timestamp,textPayload)'
```

### Inspecting Staging and Artifact Buckets

To verify that staging packages and infographics image artifacts are correctly uploaded to GCS, list the bucket contents:

```bash
# Check Agent Runtime packages
gcloud storage ls -r "gs://${GCS_BUCKET}/agent_engine/**"

# Check generated infographics artifacts
gcloud storage ls -r "gs://${GCS_BUCKET}/${GCS_ARTIFACT_PREFIX}/**" | tail
```

---

## 2. Cost Analysis

Exact charge details cannot be retrieved via `gcloud` terminal commands alone. You should view them in the Cloud Billing Console:

1. Open the **Billing** page in the **Google Cloud Console**.
2. Select **Reports** from the navigation menu.
3. Apply a filter on your `PROJECT_ID`.
4. Set the **Time range** to today.
5. Review the costs itemized by service name.

### Services Subject to Charges in this PoC:
*   **Cloud Build** (container building)
*   **Artifact Registry** (container image storage)
*   **Cloud Run** (serverless hosting)
*   **Vertex AI / Agent Runtime** (orchestration engine)
*   **Gemini Text Model** (`gemini-3.5-flash` invocation)
*   **Gemini Image Model** (`gemini-3-pro-image` invocation)
*   **Cloud Storage** (artifact storage)
*   **Cloud Logging** (log ingestion)

> [!WARNING]
> While a short validation demo is relatively inexpensive, Vertex AI image generation and Agent Runtime provisioning can incur charges. To avoid unexpected costs, make sure to clean up and delete resources after testing is complete.
