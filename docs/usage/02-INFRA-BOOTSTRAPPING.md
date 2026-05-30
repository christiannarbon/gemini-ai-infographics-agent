## 1. Enable Google Cloud APIs and Configure IAM Permissions

In this step, we will prepare your Google Cloud environment by enabling the required API services and setting up the initial Identity and Access Management (IAM) permissions.

To do this automatically, execute the bootstrap script:

```bash
./scripts/infrastructure-bootstrap.sh
```

### What does this script do?
- **Enables Google Cloud APIs**: It activates services like **Vertex AI** (for Gemini model access), **Cloud Run** (to host the web app), **Cloud Build** (to compile code), and **Artifact Registry** (to store container images).
- **Configures IAM Policy**: It grants the default Compute Engine service account the permissions required to write to Cloud Storage, generate signed URLs, and execute Agent workflows.

When the script runs successfully, it will print your **Google Cloud Project Number** and the **Cloud Run Runtime Service Account**.

> [!NOTE]
> If you are running this in a new Google Cloud Project, or if this is the first time you are using Vertex AI/Gemini in this account, you might see a confirmation prompt in the Google Cloud Console or terminal. Agree to the prompts and rerun the `./scripts/infrastructure-bootstrap.sh` command if it fails or gets interrupted.

Next, set the following environment variables in your active terminal session. These variables represent derived project identifiers that subsequent deployment scripts will rely on:

```bash
# Retrieve your unique numeric Google Cloud Project Number
export PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

# Define the default Compute Engine Service Account, which Cloud Run will assume at runtime
export CLOUD_RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Set the signing service account used to generate secure temporary links (Signed URLs) for private images
export GCS_SIGNING_SERVICE_ACCOUNT="${CLOUD_RUN_SA}"
```

## 2. Create the Cloud Storage Artifact Bucket

Next, create a Google Cloud Storage (GCS) bucket. This bucket acts as our centralized storage space in the cloud.

Run the following command to create the bucket:

```bash
gcloud storage buckets create "gs://${GCS_BUCKET}" --location="${REGION}"
```

### What is this bucket used for?
We will use this single bucket for two main purposes:
1. **Staging for Agent Runtime Deployment**: Temporary storage used by Google Cloud when uploading and configuring your ADK Agent workflows.
2. **Infographics & Artifacts Storage**: Permanent, secure storage where the final generated infographic images and summary files are saved.

### Troubleshooting Tips
- **Globally Unique Names**: Google Cloud Storage bucket names must be globally unique across all users. By default, our script defines `GCS_BUCKET` using your project ID (e.g., `your-project-id-infographics-artifacts`) to prevent naming conflicts.
- **Already Exists Error**: If you run this command and it tells you that the bucket already exists, it is safe to ignore the error as long as the bucket belongs to your project. Verify the bucket name is correct and proceed to the next step.
