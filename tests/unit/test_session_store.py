from __future__ import annotations

import pytest
from agent.models import SummaryResult, GraphicResult, ProgressStep
from web.services.sessions import (
    SessionStore,
    SessionSummaryDictWrapper,
    SessionInfographicsDictWrapper,
)


@pytest.mark.unit
def test_session_store_symmetric_deletes():
    store = SessionStore(max_size=10, ttl_seconds=3600.0)
    summaries = SessionSummaryDictWrapper(store)
    infographics = SessionInfographicsDictWrapper(store)

    session_id = "test-session-123"

    summary = SummaryResult(
        session_id=session_id,
        url="https://example.com",
        title="Demo",
        summary_lines=["a", "b", "c"],
        key_points=["p1", "p2"],
        article_text="body",
        text_backend="gemini:test",
        progress=[ProgressStep("done", "done", "ok")],
    )

    graphic = GraphicResult(
        session_id=session_id,
        visual_plan=[],
        artifact_path="/tmp/fake.png",
        artifact_mime_type="image/png",
    )

    # 1. Set both summary and infographic
    summaries[session_id] = summary
    infographics[session_id] = graphic

    # Both must be present in their respective dicts
    assert session_id in summaries
    assert session_id in infographics
    assert session_id in store._last_accessed

    # 2. Delete the summary
    del summaries[session_id]

    # The summary is gone, but the infographic is still there
    assert session_id not in summaries
    assert session_id in infographics
    # Crucially, _last_accessed must still track the session_id because the infographic exists!
    assert session_id in store._last_accessed

    # 3. Delete the infographic
    del infographics[session_id]

    # Now both are gone, and _last_accessed must no longer track the session_id
    assert session_id not in summaries
    assert session_id not in infographics
    assert session_id not in store._last_accessed
