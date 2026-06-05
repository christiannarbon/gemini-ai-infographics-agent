import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["MOCK_MODE"] = "true"
os.environ["AGENT_BACKEND"] = "local"
os.environ["MOCK_STEP_DELAY"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.main import app  # noqa: E402


def test_phase1_url_to_svg_regeneration_flow():
    client = TestClient(app)

    root = client.get("/")
    assert root.status_code == 200

    summary_job = client.post(
        "/summaries", data={"url": "https://example.com/blog/demo"}
    )
    assert summary_job.status_code == 200
    assert "Current Estimate" in summary_job.text
    assert "Sending summarization workflow to Agent Runtime" in summary_job.text
    summary_job_id = _job_id(summary_job.text, "summary")

    summary = _poll_job(client, summary_job_id)
    assert "Review Summary" in summary
    assert "3-Line Summary" in summary
    assert "data-summary-review" in summary
    assert 'hx-target="#infographics-stage"' in summary
    assert 'id="infographics-stage"' in summary
    assert "Start Over from Summary" not in summary
    assert "Step 2 of 4" not in summary
    assert "Step 5-8" not in summary

    session_id = summary.split('name="session_id" value="', 1)[1].split('"', 1)[0]
    graphic_job = client.post(
        "/infographics",
        data={
            "session_id": session_id,
            "summary_text": "Edited Summary 1\nEdited Summary 2\nEdited Summary 3",
            "key_points_text": "Edited Point A\nEdited Point B",
        },
    )
    assert graphic_job.status_code == 200
    assert 'hx-swap-oob="true"' in graphic_job.text
    assert 'data-workflow-step="3"' in graphic_job.text
    assert "Step 3 of 4" not in graphic_job.text
    graphic_job_id = _job_id(graphic_job.text, "infographics")

    graphic = _poll_job(client, graphic_job_id)
    assert "Infographic Result" in graphic
    assert "Save Image" in graphic
    assert f'href="/infographics/{session_id}/download"' in graphic
    assert "Open Image" not in graphic
    assert "Open and Save Image" not in graphic
    assert 'data-workflow-step="4"' in graphic
    assert 'data-current-step="4"' in graphic
    assert 'hx-swap-oob="true"' in graphic
    assert 'aria-current="step"' in graphic
    assert "Step 4 of 4" not in graphic
    assert "Step 5-8" not in graphic
    assert "Generating..." not in graphic
    assert "Generation Complete" in graphic
    assert "Generated Image" in graphic
    assert "Processing Log and Generation Info" in graphic
    assert "<svg" in graphic
    assert "Edited Summary 1" in graphic
    assert "Agent style:" in graphic
    assert "Reasoning:" in graphic

    regen_job = client.post(
        "/infographics/regenerate",
        data={"session_id": session_id, "feedback": "Emphasize business flow"},
    )
    assert regen_job.status_code == 200
    regen_job_id = _job_id(regen_job.text, "infographics")

    regenerated = _poll_job(client, regen_job_id)
    assert "Feedback:" not in regenerated
    assert "Agent Flow" not in regenerated
    assert "Visual Plan" not in regenerated
    assert "<svg" in regenerated


def test_real_fetch_rejects_localhost_when_mock_disabled(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")

    from agent.tools import _assert_public_http_url
    import asyncio
    import pytest

    with pytest.raises(ValueError):
        asyncio.run(_assert_public_http_url("http://127.0.0.1:8000"))


def test_non_mock_text_tools_fallback_without_gemini_credentials(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)

    from agent.tools import create_visual_plan, summarize_article
    import asyncio

    summary = asyncio.run(
        summarize_article("Demo", "First. Second. Third. Fourth. Fifth. Sixth.")
    )
    plan = asyncio.run(
        create_visual_plan(summary["summary_lines"], summary["key_points"])
    )

    assert summary["summary_lines"] == ["First.", "Second.", "Third."]
    assert summary["backend"].startswith("heuristic")
    assert len(plan) >= 4


def test_style_decision_affects_plan_in_mock(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")

    from agent.tools import create_visual_plan_for_style, decide_style
    import asyncio

    decision = asyncio.run(
        decide_style(
            ["This article is for general readers."], ["Deliver to note readers."]
        )
    )
    plan = asyncio.run(create_visual_plan_for_style(["a"], ["b"], style=decision.style))

    assert decision.style == "pop"
    assert any("brightly" in item or "colorful" in item for item in plan)


def test_gemini_vertex_credentials_detection(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")

    from agent.tools import has_gemini_credentials

    assert has_gemini_credentials() is True


def test_image_artifact_helpers():
    from agent.tools import (
        _extension_for_mime_type,
        _render_image_svg,
        artifact_url_for_path,
        display_model_name,
    )

    svg = _render_image_svg(b"abc", "image/png")

    assert "data:image/png;base64,YWJj" in svg
    assert _extension_for_mime_type("image/png") == ".png"
    assert (
        artifact_url_for_path("/tmp/custom-artifacts/abc.png") == "/artifacts/abc.png"
    )
    assert display_model_name("gemini-2.5-flash-image").endswith("(Nano Banana)")
    assert display_model_name("gemini-3-pro-image-preview").endswith(
        "(Nano Banana Pro)"
    )


def test_fallback_svg_keeps_heading_and_summary_text_separate():
    from agent.tools import render_svg
    import asyncio

    svg = asyncio.run(
        render_svg(
            "Demo",
            [
                "The Agent drives the workflow from fetching to summarization and rendering.",
                "In ADK, we implement tools like fetch, summarize, plan, and render separately.",
                "Phase 1 uses mock mode and fallback SVG without needing external APIs.",
            ],
            ["The web app interfaces with the agent running on Agent Runtime."],
            ["Place the summary in the center."],
        )
    )

    assert 'y="180" class="label">3-line Summary' in svg
    assert '<tspan x="78" y="224">' in svg
    assert 'class="summary"><tspan' in svg
    assert "Agent Flow" not in svg
    assert "Visual Plan" not in svg
    assert "Demo..." not in svg


def test_graphic_prompt_excludes_workshop_runtime_scaffolding(monkeypatch):
    from agent import tools
    import asyncio

    captured = {}

    async def fake_generate_image_data(prompt: str):
        captured["prompt"] = prompt
        return b"png", "image/png"

    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(tools, "_generate_image_data", fake_generate_image_data)

    image = asyncio.run(
        tools.generate_image_artifact(
            ["Place the 3-line summary in the center and key points on the right."],
            style="business",
            summary_lines=["Summary 1", "Summary 2", "Summary 3"],
            key_points=["Point 1", "Point 2"],
        )
    )

    assert image.data == b"png"
    assert "Summary 1" in captured["prompt"]
    assert "Point 1" in captured["prompt"]
    for forbidden in [
        "Workshop",
        "Demo",
        "Fetch URL",
        "Agent Runtime",
        "ADK",
        "Cloud Run",
        "Cloud Storage",
        "Visual Plan",
    ]:
        assert forbidden not in captured["prompt"]


def test_svg_text_wrap_only_adds_ellipsis_when_truncated():
    from agent.tools import _wrap_svg_text

    assert _wrap_svg_text("Demo", max_chars=34, max_lines=2) == ["Demo"]
    assert _wrap_svg_text("Short Title", max_chars=34, max_lines=2) == ["Short Title"]
    assert _wrap_svg_text("a" * 40, max_chars=29, max_lines=2) == [
        "a" * 29,
        "a" * 11,
    ]
    assert _wrap_svg_text("a" * 80, max_chars=15, max_lines=3)[-1].endswith("...")


def test_fallback_svg_wraps_dense_japanese_text():
    from agent.tools import _wrap_svg_text, render_svg
    import asyncio
    import html
    import re

    wrapped = _wrap_svg_text("a" * 80, max_chars=15, max_lines=3)

    assert len(wrapped) == 3
    assert all(len(line) <= 18 for line in wrapped)
    assert wrapped[-1].endswith("...")

    svg = asyncio.run(
        render_svg(
            "A demo to convert a very long title blog post into an infographic using Agent Runtime",
            ["a" * 80, "b" * 80, "c" * 80],
            ["d" * 80, "e" * 80, "f" * 80, "g" * 80],
            ["h" * 90, "i" * 90, "j" * 90],
        )
    )
    key_point_lines = [
        html.unescape(match)
        for match in re.findall(r'<tspan x="808" y="[^"]+">([^<]+)</tspan>', svg)
    ]

    assert 'class="title"><tspan' in svg
    assert key_point_lines
    assert all(len(line) <= 16 for line in key_point_lines)


def test_summary_lock_does_not_target_result_feedback_textarea():
    index = (
        Path(__file__).resolve().parents[1] / "web/templates/index.html"
    ).read_text()
    styles = (Path(__file__).resolve().parents[1] / "web/static/styles.css").read_text()

    assert 'return review.querySelectorAll(".summary-card-grid textarea");' in index
    assert 'review.querySelectorAll("textarea")' not in index
    assert (
        '[data-summary-review][data-locked="true"] .summary-card-grid textarea'
        in styles
    )
    assert '[data-summary-review][data-locked="true"] textarea' not in styles


def test_graphic_failure_unlocks_summary_review_and_preserves_stage_until_swap():
    index = (
        Path(__file__).resolve().parents[1] / "web/templates/index.html"
    ).read_text()
    job = (
        Path(__file__).resolve().parents[1] / "web/templates/partials/job.html"
    ).read_text()
    infographics = (
        Path(__file__).resolve().parents[1] / "web/templates/partials/infographics.html"
    ).read_text()

    assert 'data-workflow-status="{{ job.status }}"' in job
    assert 'data-workflow-status="done"' in infographics
    assert 'updatedStep.dataset.workflowStatus === "failed"' in index
    assert "unlockSummaryReview(review);" in index
    assert "stage.innerHTML" not in index
    assert "data-infographics-workflow" in infographics


def test_job_polling_and_swap_animation_are_calm():
    job = (
        Path(__file__).resolve().parents[1] / "web/templates/partials/job.html"
    ).read_text()
    job_content = (
        Path(__file__).resolve().parents[1] / "web/templates/partials/job_content.html"
    ).read_text()
    styles = (Path(__file__).resolve().parents[1] / "web/static/styles.css").read_text()

    assert 'hx-trigger="every 2s"' in job
    assert 'hx-target="#{{ job.job_id }}-content"' in job
    assert 'hx-swap="innerHTML"' in job
    assert 'id="{{ job.job_id }}-content"' in job
    assert "every 600ms" not in job
    assert 'job.kind == "summary"' in job_content
    assert "#graphic-stage > section" in styles
    assert "@keyframes fade-in" in styles
    assert "form.htmx-request button" in styles


def test_job_polling_updates_inner_content_until_terminal_swap():
    from web.main import AgentJob, jobs

    client = TestClient(app)
    job = AgentJob(job_id="summary-test-poll", kind="summary", title="Summarizing")
    jobs[job.job_id] = job
    try:
        running = client.get(
            f"/jobs/{job.job_id}",
            headers={"HX-Request": "true", "HX-Target": f"{job.job_id}-content"},
        )
        assert running.status_code == 200
        assert f'id="{job.job_id}"' not in running.text
        assert "Agent is processing" in running.text

        job.status = "failed"
        job.error = "boom"
        failed = client.get(
            f"/jobs/{job.job_id}",
            headers={"HX-Request": "true", "HX-Target": f"{job.job_id}-content"},
        )
        assert failed.status_code == 200
        assert failed.headers["HX-Retarget"] == f"#{job.job_id}"
        assert failed.headers["HX-Reswap"] == "outerHTML"
        assert f'id="{job.job_id}"' in failed.text
    finally:
        jobs.pop(job.job_id, None)


def test_graphic_download_uses_attachment_response(tmp_path):
    from agent.models import GraphicResult
    from web.main import infographics_cache

    artifact = tmp_path / "session-download.png"
    artifact.write_bytes(b"png-data")
    graphic = GraphicResult(
        session_id="session-download",
        visual_plan=[],
        artifact_path=str(artifact),
        artifact_mime_type="image/png",
    )
    infographics_cache[graphic.session_id] = graphic
    client = TestClient(app)

    try:
        response = client.get(f"/infographics/{graphic.session_id}/download")
    finally:
        infographics_cache.pop(graphic.session_id, None)

    assert response.status_code == 200
    assert response.content == b"png-data"
    assert response.headers["content-type"] == "image/png"
    assert "attachment" in response.headers["content-disposition"]
    assert "infographics-" in response.headers["content-disposition"]


def test_adk_backend_adds_narration_progress(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("MOCK_STEP_DELAY", "0")

    from web.agent_client import AdkAgentClient
    import asyncio

    summary = asyncio.run(
        AdkAgentClient().summarize_url("https://example.com/adk-demo")
    )

    assert summary.progress[0].label == "ADK LlmAgent explaining summarize_url action"
    assert summary.progress[0].detail == "adk:dry-run:mock-mode"


def test_password_auth_redirects_and_allows_login(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "demo-password")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")

    client = TestClient(app, follow_redirects=False)

    root = client.get("/")
    assert root.status_code == 303
    assert root.headers["location"] == "/login?next=/"

    blocked_post = client.post("/summaries", data={"url": "https://example.com"})
    assert blocked_post.status_code == 401
    assert blocked_post.headers["hx-redirect"] == "/login"

    bad_login = client.post(
        "/login",
        data={"password": "wrong", "next_path": "/"},
    )
    assert bad_login.status_code == 401

    good_login = client.post(
        "/login",
        data={"password": "demo-password", "next_path": "/"},
    )
    assert good_login.status_code == 303
    assert "gea_poc_auth" in good_login.headers["set-cookie"]

    authenticated_root = client.get("/")
    assert authenticated_root.status_code == 200
    assert "Turn a blog post into a single infographic" in authenticated_root.text


def test_production_requires_app_password(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    monkeypatch.setenv("K_SERVICE", "cloud-run-service")

    from web.auth import assert_auth_config
    import pytest

    with pytest.raises(RuntimeError):
        assert_auth_config()

    monkeypatch.setenv("APP_PASSWORD", "demo-password")
    with pytest.raises(RuntimeError, match="APP_SECRET_KEY"):
        assert_auth_config()

    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    assert_auth_config()


def test_runtime_backend_requires_resource_name(monkeypatch):
    monkeypatch.setenv("AGENT_BACKEND", "runtime")
    monkeypatch.delenv("AGENT_RUNTIME_RESOURCE_NAME", raising=False)

    from web.agent_client import build_agent_client
    import asyncio
    import pytest

    client = build_agent_client()
    with pytest.raises(RuntimeError, match="AGENT_RUNTIME_RESOURCE_NAME"):
        asyncio.run(client.summarize_url("https://example.com"))


def test_runtime_backend_rejects_placeholder_resource_name(monkeypatch):
    monkeypatch.setenv("AGENT_BACKEND", "runtime")
    monkeypatch.setenv(
        "AGENT_RUNTIME_RESOURCE_NAME",
        "projects/PROJECT_NUMBER/locations/us-central1/reasoningEngines/RESOURCE_ID",
    )

    from web.agent_client import build_agent_client
    import asyncio
    import pytest

    client = build_agent_client()
    with pytest.raises(RuntimeError, match="placeholder"):
        asyncio.run(client.summarize_url("https://example.com"))


def test_deploy_builds_use_constraints():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    deploy_script = (root / "scripts" / "agent-runtime-deployment.py").read_text(
        encoding="utf-8"
    )

    assert "COPY requirements.txt constraints.txt" in dockerfile
    assert (
        "pip install --no-cache-dir -r requirements.txt -c constraints.txt"
        in dockerfile
    )
    assert "constraints.txt" in deploy_script
    assert '"requirements": runtime_requirements_file' in deploy_script


def test_agent_runtime_requirements_file_omits_comments_and_blank_lines(
    tmp_path, monkeypatch
):
    import importlib.util
    import google.auth

    monkeypatch.setattr(
        google.auth, "default", lambda *args, **kwargs: (None, "demo-project")
    )

    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "agent-runtime-deployment.py"
    spec = importlib.util.spec_from_file_location(
        "agent_runtime_deployment", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    source = tmp_path / "constraints.txt"
    source.write_text(
        "\n".join(
            [
                "# PoC constraints.",
                "",
                "  # indented comment",
                "google-adk==1.34.0",
                "google-cloud-aiplatform==1.153.1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    prepared = Path(
        module.prepare_runtime_requirements_file(str(source), tmp_path / "out")
    )

    assert prepared.read_text(encoding="utf-8") == (
        "google-adk==1.34.0\ngoogle-cloud-aiplatform==1.153.1\n"
    )


def test_user_facing_error_message_mapping():
    from web.main import _display_error

    model_error = _display_error(
        RuntimeError(
            "Publisher Model projects/demo/locations/us-central1/models/gemini-3.5-flash was not found"
        )
    )
    signed_url_error = _display_error(RuntimeError("signBlob permission denied"))
    empty_error = _display_error(AssertionError())

    assert "Gemini model not found" in model_error
    assert "Technical Details:" in model_error
    assert "Insufficient permissions to generate the signed URL" in signed_url_error
    assert "AssertionError" in empty_error


def test_slow_job_message_after_threshold():
    from datetime import timedelta
    from web.main import AgentJob

    job = AgentJob(job_id="graphic-test", kind="graphic", title="Generating")
    job.started_at = job.started_at - timedelta(seconds=241)

    assert job.is_slow is True
    assert "Agent Runtime logs" in job.slow_message


def test_runtime_contract_round_trip():
    from agent.models import ProgressStep, SummaryResult
    from agent.runtime_contract import RuntimeSummaryPayload, RuntimeWorkflowResponse

    summary = SummaryResult(
        session_id="session-1",
        url="https://example.com",
        title="Demo",
        summary_lines=["a", "b", "c"],
        key_points=["p1", "p2", "p3", "p4"],
        article_text="body",
        text_backend="gemini:test",
        progress=[ProgressStep("done", "done", "ok")],
    )

    response = RuntimeWorkflowResponse(
        operation="summarize_url",
        summary=RuntimeSummaryPayload.from_result(summary),
    )
    restored = RuntimeWorkflowResponse.model_validate_json(response.model_dump_json())

    assert restored.summary is not None
    assert restored.summary.to_result().title == "Demo"
    assert restored.summary.to_result().progress[0].detail == "ok"


def test_runtime_client_parses_function_response_event():
    from web.agent_client import _runtime_response_from_event

    event = {
        "content": {
            "parts": [
                {
                    "function_response": {
                        "name": "runtime_summarize_url",
                        "response": {
                            "operation": "summarize_url",
                            "summary": {
                                "session_id": "s1",
                                "url": "https://example.com",
                                "title": "Title",
                                "summary_lines": ["a", "b", "c"],
                                "key_points": ["p1", "p2", "p3", "p4"],
                                "article_text": "body",
                                "text_backend": "runtime",
                                "progress": [],
                            },
                        },
                    }
                }
            ]
        }
    }

    response = _runtime_response_from_event(event)

    assert response is not None
    assert response.operation == "summarize_url"
    assert response.summary is not None
    assert response.summary.title == "Title"


def test_runtime_client_parses_text_response_event():
    from web.agent_client import _runtime_response_from_event

    event = {
        "content": {
            "parts": [
                {
                    "text": (
                        '{"operation":"summarize_url","summary":{'
                        '"session_id":"s1","url":"https://example.com","title":"Title",'
                        '"summary_lines":["a","b","c"],"key_points":["p1"],'
                        '"article_text":"body","text_backend":"runtime","progress":[]}}'
                    )
                }
            ]
        }
    }

    response = _runtime_response_from_event(event)

    assert response is not None
    assert response.operation == "summarize_url"
    assert response.summary is not None
    assert response.summary.title == "Title"


def test_runtime_operation_sync_accepts_text_part_contract():
    from web.agent_client import RuntimeAgentClient

    class RemoteAgent:
        def stream_query(self, user_id: str, message: str):
            yield {
                "author": "graphic_recording_runtime_workflow",
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"operation":"summarize_url","summary":{'
                                '"session_id":"s1","url":"https://example.com","title":"Title",'
                                '"summary_lines":["a","b","c"],"key_points":["p1"],'
                                '"article_text":"body","text_backend":"runtime","progress":[]}}'
                            )
                        }
                    ]
                },
            }

    response = RuntimeAgentClient()._run_runtime_operation_sync(
        RemoteAgent(),
        {"operation": "summarize_url"},
    )

    assert response.summary is not None
    assert response.summary.title == "Title"


def test_runtime_agent_returns_error_contract_for_bad_payload(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from agent import adk_agent
    from agent.runtime_contract import RuntimeWorkflowResponse

    class FakeEvent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakePart:
        def __init__(self, text: str):
            self.text = text

    class FakeContent:
        def __init__(self, role: str, parts: list):
            self.role = role
            self.parts = parts

    monkeypatch.setattr(adk_agent, "Event", FakeEvent)
    monkeypatch.setattr(
        adk_agent, "types", SimpleNamespace(Content=FakeContent, Part=FakePart)
    )

    try:
        runtime_agent = adk_agent.RuntimeWorkflowAgent(
            name="runtime",
            description="runtime test",
        )
    except TypeError:
        runtime_agent = adk_agent.RuntimeWorkflowAgent()
        runtime_agent.name = "runtime"
    ctx = SimpleNamespace(
        invocation_id="invocation-1",
        branch=None,
        user_content=SimpleNamespace(parts=[SimpleNamespace(text="{bad json")]),
    )

    async def collect_events():
        return [event async for event in runtime_agent._run_async_impl(ctx)]

    events = asyncio.run(collect_events())
    response = RuntimeWorkflowResponse.model_validate_json(
        events[0].content.parts[0].text
    )

    assert response.operation == "unknown"
    assert "JSONDecodeError" in response.error


def test_runtime_dispatcher_calls_summary_workflow_directly(monkeypatch):
    import asyncio

    from agent.models import ProgressStep, SummaryResult
    from agent import runtime_workflows

    async def fake_summarize_url(url: str) -> SummaryResult:
        return SummaryResult(
            session_id="session-1",
            url=url,
            title="Direct",
            summary_lines=["a", "b", "c"],
            key_points=["p1", "p2", "p3", "p4"],
            article_text="body",
            text_backend="test",
            progress=[ProgressStep("direct dispatch", "done", "ok")],
        )

    monkeypatch.setattr(runtime_workflows, "summarize_url", fake_summarize_url)

    response = asyncio.run(
        runtime_workflows.dispatch_runtime_operation(
            {"operation": "summarize_url", "url": "https://example.com"}
        )
    )

    assert response.operation == "summarize_url"
    assert response.summary is not None
    assert response.summary.title == "Direct"


def test_runtime_payload_parser_reads_user_message_json():
    from types import SimpleNamespace

    from agent.adk_agent import _runtime_payload_from_context

    ctx = SimpleNamespace(
        user_content=SimpleNamespace(
            parts=[
                SimpleNamespace(
                    text='{"operation":"summarize_url","url":"https://example.com"}'
                )
            ]
        )
    )

    assert _runtime_payload_from_context(ctx) == {
        "operation": "summarize_url",
        "url": "https://example.com",
    }


def test_article_fetch_size_limit_helpers(monkeypatch):
    monkeypatch.setenv("ARTICLE_FETCH_MAX_BYTES", "4096")

    from agent.tools import article_fetch_max_bytes, signed_artifact_url_ttl_seconds

    assert article_fetch_max_bytes() == 4096

    monkeypatch.setenv("ARTICLE_FETCH_MAX_BYTES", "not-a-number")
    assert article_fetch_max_bytes() == 2_000_000

    monkeypatch.setenv("GCS_SIGNED_URL_TTL_SECONDS", "120")
    assert signed_artifact_url_ttl_seconds() == 120

    monkeypatch.setenv("GCS_SIGNED_URL_TTL_SECONDS", "bad")
    assert signed_artifact_url_ttl_seconds() == 28800


def test_signed_url_credentials_uses_explicit_signing_service_account(monkeypatch):
    from agent import tools

    class Credentials:
        token = "token"

        def refresh(self, _request):
            self.token = "fresh-token"

    monkeypatch.setenv(
        "GCS_SIGNING_SERVICE_ACCOUNT", "runtime@example.iam.gserviceaccount.com"
    )
    monkeypatch.setattr(tools, "google_auth_default_for_test", None, raising=False)

    import google.auth

    monkeypatch.setattr(
        google.auth, "default", lambda scopes: (Credentials(), "project")
    )

    credentials, service_account_email = tools._signed_url_credentials()

    assert credentials.token == "fresh-token"
    assert service_account_email == "runtime@example.iam.gserviceaccount.com"


def test_read_limited_response_rejects_oversized_body():
    from agent.tools import _read_limited_response
    import asyncio
    import pytest

    class Response:
        async def aiter_raw(self):
            yield b"abc"
            yield b"def"

    with pytest.raises(ValueError, match="exceeds 5 bytes"):
        asyncio.run(_read_limited_response(Response(), 5))


def test_invalid_content_encoding_falls_back_to_raw_body():
    from agent.tools import _decode_response_content
    import httpx

    body = b"<html><title>Plain HTML</title></html>"
    decoded = _decode_response_content(
        body, httpx.Headers({"content-encoding": "gzip"})
    )

    assert decoded == body


def test_retryable_exception_detection():
    from agent.tools import _is_retryable_exception

    class RetryableError(Exception):
        status_code = 429

    class FatalError(Exception):
        status_code = 400

    assert _is_retryable_exception(RetryableError("quota")) is True
    assert _is_retryable_exception(FatalError("bad request")) is False


def test_call_with_retries_succeeds_after_retry(monkeypatch):
    from agent import tools
    import asyncio

    class RetryableError(Exception):
        status_code = 503

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(tools.asyncio, "sleep", no_sleep)

    attempts = {"count": 0}

    async def operation():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RetryableError("temporarily unavailable")
        return "ok"

    result = asyncio.run(tools._call_with_retries(lambda: operation(), "test-op"))

    assert result == "ok"
    assert attempts["count"] == 2


def test_call_with_retries_stops_on_fatal_error():
    from agent import tools
    import asyncio
    import pytest

    class FatalError(Exception):
        status_code = 400

    attempts = {"count": 0}

    async def operation():
        attempts["count"] += 1
        raise FatalError("bad request")

    with pytest.raises(FatalError):
        asyncio.run(tools._call_with_retries(lambda: operation(), "test-op"))

    assert attempts["count"] == 1


def _job_id(html: str, prefix: str) -> str:
    marker = f'id="{prefix}-'
    return prefix + "-" + html.split(marker, 1)[1].split('"', 1)[0]


def _poll_job(client: TestClient, job_id: str) -> str:
    for _ in range(20):
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        if f'id="{job_id}"' not in response.text:
            return response.text
    raise AssertionError(f"job did not finish: {job_id}")
