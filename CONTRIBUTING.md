# Contributing to Gemini AI Infographics Agent

Thank you for your interest in contributing to the Gemini AI Infographics Agent PoC repository! This document guides you through the process of setting up, developing, testing, and submitting your contributions.

## Code of Conduct

Please review and respect our [Code of Conduct](CODE_OF_CONDUCT.md) in all community interactions.

## Getting Started

### 1. Prerequisites

*   Python 3.10 or higher
*   Google Cloud SDK (`gcloud` CLI) installed and authenticated
*   A Google Cloud project with billing enabled (for cloud testing)

### 2. Local Environment Setup

Clone the repository and set up a Python virtual environment:

```bash
git clone https://github.com/christiannarbon/gemini-ai-infographics-agent.git
cd gemini-ai-infographics-agent

python3 -m venv .venv
source .venv/bin/activate

# Install dependencies using pinned constraints to prevent version drift
pip install -r requirements.txt -c constraints.txt
```

---

## Development Standards

To keep the codebase maintainable, secure, and clean, please adhere to these guidelines:

### 1. Formatting and Linting

We use **Ruff** for code formatting and linting. Make sure your changes pass all checks before opening a pull request:

```bash
# Run code formatter
.venv/bin/ruff format

# Run linter checks
.venv/bin/ruff check
```

### 2. Naming Conventions

*   **Infographics Terminology**: Always use the keyword **"infographics"** (plural) instead of "graphic" or "graphic recording". This applies to python variables, function names, API endpoints, file naming, and templates (e.g. `generate_infographics`, `web/templates/partials/infographics.html`, `/infographics`).
*   **Case Conventions**: Standard Python snake_case for variables, methods, and functions; CamelCase for classes.

### 3. Model Configuration

*   Use the stable release **`gemini-3-pro-image`** as the default image model instead of preview versions (like `gemini-3-pro-image-preview`).
*   The default text model is `gemini-3.5-flash`.

---

## Testing Guidelines

### 1. Local Mock Mode (Fastest)

If you are developing frontend features or want to test the FastAPI app without invoking Vertex AI or billing pipelines, run in Mock Mode:

```bash
export MOCK_MODE="true"
export AGENT_BACKEND="local"
export APP_PASSWORD="mock"
export APP_SECRET_KEY="mock-secret-key-for-local-only"

python -m uvicorn web.main:app --host 0.0.0.0 --port 8080
```
Open **`http://localhost:8080`** in your browser and log in with the password `mock`.

### 2. Cloud Integration Mode

To test integration with Google Cloud Vertex AI and Cloud Storage:
1. Complete infrastructure bootstrapping using `scripts/infrastructure-bootstrap.sh`.
2. Configure IAM roles for the service accounts using `scripts/runtime-iam-config.sh`.
3. Deploy the reasoning engine using `python scripts/agent-runtime-deployment.py`.
4. Configure your `.env` variables using your deployed resource names and run the server with `MOCK_MODE=false`.

---

## Submitting Pull Requests

1.  **Create a Branch**: Create a descriptive topic branch off the `main` branch.
    ```bash
    git checkout -b feature/your-feature-name
    ```
2.  **Commit Messages**: Keep commit messages clear, concise, and written in the imperative mood (e.g., `Add pull request template and contributing guide`).
3.  **Self-Check**: Run `ruff check` and `ruff format --check` to verify code format.
4.  **Open a PR**: Open a pull request against the `main` branch of this repository. Fill out the pull request template to explain what the change accomplishes.

Thank you for contributing!
