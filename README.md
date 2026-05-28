# gemini-ai-infographics-agent

Infographics generation Agent using Gemini Enterprise Agent Platform from information extracted from blog posts

# Gemini Enterprise Agent Platform

This application takes a blog post URL, uses an ADK Agent on Agent Runtime to summarize the article, and generates an infographic image.

Users can clone this repository in Google Cloud Shell or a local terminal, and deploy Agent Runtime and Cloud Run to their Google Cloud project.

## System Components

- Cloud Run: Web UI, authentication, job progress display, and invoking Agent Runtime.
- Agent Runtime: Executing the ADK Agent workflow.
- Vertex AI / Gemini: Article summarization, style classification, layout planning, and image generation.
- Cloud Storage: Storing generated infographic images and artifacts.
- Signed URL: Displaying images from private buckets in the browser.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -c constraints.txt

export MOCK_MODE=true
export AGENT_BACKEND=local
export APP_PASSWORD=mock
export APP_SECRET_KEY=mock-secret-key-for-local-only

uvicorn web.main:app --reload
```

Open `http://127.0.0.1:8000` in your browser and log in with the password `mock`.

## Directory Structure

- `web/`: FastAPI Web Application
- `agent/`: ADK Agent, workflow, and tool implementations
- `scripts/`: Scripts for setup, deployment, diagnostics, and teardown
- `docs/`: Documentation
- `tests/`: Tests for main workflows