# Runtime IAM Permissions Configuration

This step configures the Identity and Access Management (IAM) permissions. This ensures that the Agent Runtime and Cloud Run services have the necessary permissions to read, write, and secure generated infographic images in Google Cloud Storage.

To set up these permissions automatically, run the configuration script:

```bash
./scripts/runtime-iam-config.sh
```

---

## What Does This Script Do? (Beginner Guide)

In Google Cloud, services cannot talk to each other or access files by default. We must explicitly grant them permission. This script configures three critical permissions:

### 1. Initialize Vertex AI Service Identity
It checks for (or creates) the built-in system service agent for Vertex AI. This is a special Google-managed account that allows Vertex AI to act on resources inside your project.

### 2. Grant Storage Access (`roles/storage.objectAdmin`)
It grants full object administration access (read, write, delete) on your Cloud Storage bucket to:
* **The Cloud Run Service Account**: So the web application can list and display the files.
* **The Vertex AI Agent Runtime Services**: So the AI Agent can save newly generated infographic files directly into your storage bucket.

### 3. Grant Service Account Token Creator Access (`roles/iam.serviceAccountTokenCreator`)
It grants the Vertex AI Service Agents permission to act as your Cloud Run Service Account.
* **Why is this needed?** When an infographic is generated, it is stored in a private bucket. To show it in the user's browser securely, the application generates a temporary, time-limited link called a **Signed URL**. The AI runtime needs the token creator permission to sign these links on behalf of your service account.

---

## Verifying the Outputs

At the end of the script execution, it will display a message with the environment variables to export:

```text
Export these values before deploy:
export CLOUD_RUN_SA="..."
export GCS_SIGNING_SERVICE_ACCOUNT="..."
```

If you already configured these environment variables in [Infra Bootstrapping](02-INFRA-BOOTSTRAPPING.md), you do not need to run the `export` commands again, as they will be identical. 

Just verify that the values match the following pattern:
* `CLOUD_RUN_SA` should be `${PROJECT_NUMBER}-compute@developer.gserviceaccount.com`
* `GCS_SIGNING_SERVICE_ACCOUNT` should be exactly the same as `CLOUD_RUN_SA`