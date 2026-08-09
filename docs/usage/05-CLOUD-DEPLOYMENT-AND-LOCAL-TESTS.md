# Cloud Deployment and Local Testing Guide

This guide describes how to deploy the web application to Google Cloud Run and perform a smoke test, as well as how to run local tests in Mock Mode if you run into cloud configuration issues.

## What is Cloud Deployment and Local Testing?

For beginners new to the project, here is an explanation of what the deployment and testing steps do:
1. **Cloud Run Deployment**: Runs the `scripts/cloud-run-deployment.sh` script to upload the source code, build a Docker container in the cloud, and deploy the FastAPI web frontend onto a serverless hosting service called **Google Cloud Run**.
2. **Smoke Testing**: Validates the end-to-end functionality by opening the deployed web app in a browser, logging in, entering a blog URL, and verifying that the agent generates a summary and creates the infographics image.
3. **Mock Mode (Local Testing)**: A local-only fallback mode that bypasses Google Cloud deployment, billing, and IAM setups. It runs the FastAPI web app on your local machine using mock session stores and local agent pipelines, allowing you to preview the application instantly.
4. **Unit Tests**: Runs the `pytest` suite (`make test`) to verify settings parsing, the article fetcher, Gemini retry behavior, artifact storage, SVG rendering, the job/session stores, and that every web router and agent tool module imports cleanly.

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

The script injects `APP_ENV=production` and `APP_LOG_FORMAT=json` into the container, and configures the Cloud Run startup and liveness probes against the app's `/healthz` endpoint. `/healthz` and `/login` are the only paths exempt from password authentication.

> [!IMPORTANT]
> `APP_PASSWORD` and `APP_SECRET_KEY` are mandatory in production. Because `APP_ENV=production` is set (and Cloud Run also injects `K_SERVICE`), the app refuses to start with a `RuntimeError` if either value is missing, and the Cloud Run health probes will fail the revision.

Upon successful completion, the script prints your service URL:

```text
Service URL: https://SERVICE_NAME-PROJECT_NUMBER.REGION.run.app
```

Copy and save this URL. The host name is derived from the `SERVICE_NAME` you exported during environment prep (the script defaults to `infographics-agent-demo` when `SERVICE_NAME` is unset).

> [!IMPORTANT]
> When redeploying the service, make sure to keep using the same `APP_SECRET_KEY` generated in environment prep phase. Changing the key invalidates existing login cookies, requiring all active users to log in again. To avoid losing the key when closing the terminal, print and save the current key using `echo "${APP_SECRET_KEY}"` and store it somewhere secure.

---

## 2. Browser Smoke Test

Open your Cloud Run service URL in a web browser:

```text
https://SERVICE_NAME-PROJECT_NUMBER.REGION.run.app
```

1.  **Login**: Access the login page and enter the password configured in `APP_PASSWORD`.
2.  **Use Verified URL**: We recommend testing with one of the following blog URLs first. Some sites block crawlers or have complex markups that cause summary extractions to fail. Verifying first with these working links ensures your deployment functions correctly:
    *   [`https://zenn.dev/chrispy_jp/articles/6da4c8042a2211`](https://zenn.dev/chrispy_jp/articles/6da4c8042a2211)
    *   [`https://zenn.dev/chrispy_jp/articles/512a3a93b088f3`](https://zenn.dev/chrispy_jp/articles/512a3a93b088f3)

    Only public `http`/`https` URLs are accepted. The fetcher rejects private, local, and reserved network addresses, so internal hosts and IP literals such as `localhost` will fail with an article retrieval error.
3.  **Summarize**: Paste the URL and click **Start Agent** to request article summarization.
4.  **Retrieval Status**: Verify that the progress screen shows the elapsed seconds counter and the estimated milestones for summarization: *Sending summarization workflow to Agent Runtime* → *Retrieving article body* → *Generating 3-line summary and key points* → *Verifying JSON contract and returning response*. Until the runtime reports its own steps, these are labeled as estimates.
5.  **Confirm Summary**: Once retrieval finishes, the 3-line summary and key points review screen will load. You can edit the summary lines and key points here before generating the image.
6.  **Generate Infographics**: Click **Generate Infographic** to kick off image generation.
7.  **Generation Status**: Verify that the image generation milestones display: *Sending summary to Agent Runtime* → *Agent deciding style and layout plan* → *Generating image with Gemini* → *Saving artifacts to Cloud Storage* → *Preparing signed URL and returning response*.
8.  **View Result**: Confirm that the infographics result, the chosen **Agent Style** (visual style), and the style reasoning are displayed.
9.  **Save Image**: Verify the image artifact displays in the canvas and that the **Save Image** button downloads the file.
10. **Refine**: Type a refinement request in the feedback textarea (e.g. *"make it more professional"* or *"use business colors"*) and click **Regenerate with Feedback** to test the iterative design flow.

> [!NOTE]
> Summarization usually takes **30 to 90 seconds** and infographics image generation **1 to 3 minutes**. If the progress screen seems paused but the elapsed seconds counter continues to increment, the Cloud Run client polling is active. A caution banner appears automatically once a job exceeds 120 seconds (summarization) or 240 seconds (image generation), along with a hint about which logs to check.

> [!NOTE]
> If the Gemini image model is unavailable, quota-limited, or returns an unusable result, the pipeline degrades to a deterministic **fallback SVG** infographic rather than failing the job. Seeing a flat, text-forward SVG layout instead of a generated image is the expected signal that the image model call fell back — check the Agent Runtime logs for the reason.

---

## 3. Troubleshooting fallback: Mock Mode

If you are blocked by Google Cloud billing setup, IAM configurations, or Agent Runtime deployment issues, you can run the application in **Mock Mode** to test the web frontend locally. No cloud resources or deployments are required.

Run the following commands in your terminal:

```bash
export MOCK_MODE="true"
export AGENT_BACKEND="local"
export APP_PASSWORD="mock"
export APP_SECRET_KEY="mock-secret-key-for-local-only"
export APP_LOG_FORMAT="text"

python -m uvicorn web.main:app --host 0.0.0.0 --port 8080
```

Once running, go to **localhost:8080**
*   **Login Password**: `mock`
*   *Note: This mode uses mock local outputs and does not interact with Vertex AI Agent Runtime, GCS buckets, or signed URLs.*

Instead of exporting these variables every time, you can copy `.env.example` to `.env` and edit it there; the app loads `.env` automatically, and any shell variable you export still overrides the file.

`APP_LOG_FORMAT=text` is optional and only switches the console output from structured JSON to a readable one-line format for local work. Set `MOCK_STEP_DELAY` (default `0.45` seconds) to speed up or slow down the simulated per-step progress.

### Choosing a Backend

`AGENT_BACKEND` selects how the web app executes a job. The web app builds the matching client at startup, so restart the process after changing it:

| Value | Behavior | When to use |
| --- | --- | --- |
| `local` | Runs the agent tool pipeline in-process, inside the web app. | Local UI work and mock-mode previews. |
| `adk` | Runs a Google ADK narration turn to describe the next phase, then the same local pipeline. | Checking ADK wiring and narration output without deploying. |
| `runtime` | Calls the deployed Agent Runtime workflow and validates its JSON response contract. | Cloud deployment and end-to-end verification. |

With `AGENT_BACKEND=runtime`, `AGENT_RUNTIME_RESOURCE_NAME` must contain the real `projects/.../reasoningEngines/...` value. A leftover placeholder produces a configuration error in the UI telling you to fix the resource name and redeploy.

In mock mode, artifacts are written to the local `ARTIFACT_DIR` (default `artifacts/`) and served by the web app at `/artifacts`, so no GCS bucket or signed URL is involved.

---

## 4. Unit Tests

The repository ships a `pytest` suite that runs without any Google Cloud access. Run it from the repository root:

```bash
make test          # pytest
make lint          # ruff check, ruff format --check, djlint on templates
make check-all     # lint and tests together
```

The suite covers settings parsing and validation, the article fetcher (including the public-URL guard and host resolution), Gemini retry behavior, artifact storage, SVG rendering, the job and session stores, and import checks that catch a broken web router or agent tool module before you deploy.

> [!TIP]
> Run `make install-hooks` once to install the Git pre-push hook. The hook runs `make lint` before every push; run `make test` yourself (or rely on CI) to cover the test suite.
