# Cloud Deployment and Local Testing Guide

This guide describes how to deploy the web application to Google Cloud Run and perform a smoke test, as well as how to run local tests in Mock Mode if you run into cloud configuration issues.

## What is Cloud Deployment and Local Testing?

For beginners new to the project, here is an explanation of what the deployment and testing steps do:
1. **Cloud Run Deployment**: Runs the `scripts/cloud-run-deployment.sh` script to upload the source code, build a Docker container in the cloud, and deploy the FastAPI web frontend onto a serverless hosting service called **Google Cloud Run**.
2. **Smoke Testing**: Validates the end-to-end functionality by opening the deployed web app in a browser, logging in, entering a blog URL, and verifying that the agent generates a summary and creates the infographics image.
3. **Mock Mode (Local Testing)**: A local-only fallback mode that bypasses Google Cloud deployment, billing, and IAM setups. It runs the FastAPI web app on your local machine or Cloud Shell using mock database caches and local agent pipelines, allowing you to preview the application instantly.

---

## 1. Deploy the Web App to Cloud Run

> [!NOTE]
> This command can take **5 to 10 minutes** to complete. Google Cloud will compile your source code, build the container image, publish it, configure the revision, and set up routing traffic.

If you encounter issues during deployment, you can fall back to Mock Mode (see Section 3 below) to preview the user interface locally.

Set up the required environment variables and run the deployment script:

```bash
export MOCK_MODE="false"
export AGENT_BACKEND="runtime"
export AGENT_RUNTIME_LOCATION="us-central1"
export GOOGLE_CLOUD_LOCATION="global"
export GCS_SIGNING_SERVICE_ACCOUNT="${CLOUD_RUN_SA}"

./scripts/cloud-run-deployment.sh
```

Upon successful completion, the script prints your service URL:

```text
Service URL: https://infographics-agent-demo-PROJECT_NUMBER.REGION.run.app
```

Copy and save this URL.

> [!IMPORTANT]
> When redeploying the service, make sure to keep using the same `APP_SECRET_KEY` generated in Phase 0. Changing the key invalidates existing login cookies, requiring all active users to log in again. To avoid losing the key when closing the Cloud Shell tab, print and save the current key using `echo "${APP_SECRET_KEY}"`.

---

## 2. Browser Smoke Test

Open your Cloud Run service URL in a web browser:

```text
https://infographics-agent-demo-PROJECT_NUMBER.REGION.run.app
```

1.  **Login**: Access the login page and enter the password configured in `APP_PASSWORD`.
2.  **Use Verified URL**: We recommend testing with one of the following blog URLs first. Some sites block crawlers or have complex markups that cause summary extractions to fail. Verifying first with these working links ensures your deployment functions correctly:
    *   [`https://zenn.dev/chrispy_jp/articles/6da4c8042a2211`](https://zenn.dev/chrispy_jp/articles/6da4c8042a2211)
    *   [`https://zenn.dev/chrispy_jp/articles/6da4c8042a2211`](https://zenn.dev/chrispy_jp/articles/512a3a93b088f3)`
    
3.  **Summarize**: Paste the URL and click **Start Agent** to request article summarization.
4.  **Retrieval Status**: Verify that the UI displays processing logs like "Processing in Agent Runtime", elapsed time, and "Current Estimate" milestones.
5.  **Confirm Summary**: Once retrieval finishes, the 3-line summary and key points review screen will load.
6.  **Generate Infographics**: Click **Generate Infographic** to kick off image generation.
7.  **Generation Status**: Verify that the progress status indicators and estimations display.
8.  **View Result**: Confirm that the infographics result, the chosen **Agent Style** (visual style), and the style reasoning are displayed.
9.  **Save Image**: Verify the image artifact displays in the canvas and that the **Save Image** button downloads the file.
10. **Refine**: Type a refinement request in the feedback textarea (e.g. *"make it more professional"* or *"use business colors"*) and click **Regenerate with Feedback** to test the iterative design flow.

> [!NOTE]
> Infographics image generation can take **1 to 3 minutes**. If the progress screen seems paused but the elapsed seconds counter continues to increment, the Cloud Run client polling is active. If generation takes unusually long, a caution banner will appear on-screen.

---

## 3. Troubleshooting fallback: Mock Mode

If you are blocked by Google Cloud billing setup, IAM configurations, or Agent Runtime deployment issues, you can run the application in **Mock Mode** to test the web frontend locally. No cloud resources or deployments are required.

Run the following commands in your Cloud Shell terminal:

```bash
export MOCK_MODE="true"
export AGENT_BACKEND="local"
export APP_PASSWORD="mock"
export APP_SECRET_KEY="mock-secret-key-for-local-only"

python -m uvicorn web.main:app --host 0.0.0.0 --port 8080
```

Once running, go to **localhost:8080**
*   **Login Password**: `mock`
*   *Note: This mode uses mock local outputs and does not interact with Vertex AI Agent Runtime, GCS buckets, or signed URLs.*
