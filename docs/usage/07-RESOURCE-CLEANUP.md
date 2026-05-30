# Resource Cleanup Guide

This guide explains how to tear down and delete all deployed Google Cloud resources associated with the PoC to prevent any ongoing billing.

## What is Resource Cleanup?

For beginners new to the project, here is an explanation of what this step does:
1. **Cloud Run Service Deletion**: Removes the serverless container instance of the web frontend so that you no longer run web host revisions.
2. **Cloud Storage Bucket Deletion**: Deletes the GCS bucket containing generated infographics images, summaries, and temporary dependencies.
3. **Agent Runtime Deletion**: Deletes the provisioning record of the ADK Agent Reasoning Engine from Google Cloud Vertex AI.
4. **Project Deletion (Optional)**: If you provisioned a temporary, disposable Google Cloud project dedicated solely to this PoC, you can delete the entire project in one step to clean up IAM service accounts and logging profiles.

---

## 1. Clean Up Google Cloud Resources

Run the cleanup script to remove all deployed PoC components:

```bash
./scripts/resource-cleanup.sh
```

By default, the script asks for confirmation. To skip confirmation (e.g. for CI workflows, automated rehearsal runs, or scripts testing), pass the `--yes` or `-y` flag:

```bash
./scripts/resource-cleanup.sh --yes
```

> [!TIP]
> If you want to check the status of your deployments before executing the deletion, run the diagnostic script:
> ```bash
> ./scripts/deployment-log-analysis.sh
> ```

---

## 2. Delete the Google Cloud Project (Optional)

The cleanup script removes the specific resources created for the PoC, but it **does not delete the Google Cloud project itself**. 

If you are using a dedicated, disposable Google Cloud project, deleting the entire project is the easiest and most thorough way to ensure no leftover configurations or logs accrue costs.

> [!CAUTION]
> This step is **only** for projects that are dedicated solely to this PoC. **Never** execute this on shared, corporate, or personal projects. Double-check your current active project ID and selector in the Google Cloud Console before running this:

```bash
gcloud projects describe "${PROJECT_ID}"
```

If you are certain you want to delete the project:

> [!CAUTION]
> Project deletion is permanent. Once deleted, all services, buckets, and configurations are permanently removed and cannot be restored.

```bash
gcloud projects delete "${PROJECT_ID}"
```