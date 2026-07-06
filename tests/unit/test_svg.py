import pytest
from agent.tools.svg_renderer import (
    _wrap_svg_text,
    _style_palette,
    render_svg,
)


@pytest.mark.unit
def test_wrap_svg_text():
    # Empty input returns [""]
    assert _wrap_svg_text("", max_chars=10, max_lines=2) == [""]
    assert _wrap_svg_text("   ", max_chars=10, max_lines=2) == [""]

    # Very long single word is wrapped/truncated without crashing
    res = _wrap_svg_text("abcdefghijklmnopqrstuvwxyz", max_chars=10, max_lines=2)
    assert res == ["abcdefghij", "klmnopqrst..."]

    # Text exceeding max_lines is truncated with ellipsis
    res_trunc = _wrap_svg_text("one two three four five six", max_chars=10, max_lines=2)
    # wraps:
    # "one two" (7 chars)
    # remaining: "three four five six"
    # split_at for "three four" (10 chars): split_at = 10 -> "three four"
    # remaining: "five six" -> non-empty, so ellipsis added to second line
    # "three four" -> "three four..."
    assert res_trunc == ["one two", "three four..."]

    # Truncation with punctuation rstrip
    res_punct = _wrap_svg_text("one two. three four", max_chars=8, max_lines=1)
    # first line: "one two."
    # remaining: "three four"
    # ends with: "one two..." (dot/punctuation stripped before adding ellipsis)
    assert res_punct == ["one two..."]


@pytest.mark.unit
def test_style_palette():
    # Distinct palettes for different styles
    business = _style_palette("business")
    pop = _style_palette("pop")
    minimal = _style_palette("minimal")

    assert business != pop
    assert business != minimal
    assert pop != minimal

    assert business == {"accent": "#2563eb", "soft": "#dbeafe", "background": "#f8fafc"}
    assert pop == {"accent": "#ea580c", "soft": "#ffedd5", "background": "#fff7ed"}
    assert minimal == {"accent": "#475569", "soft": "#e2e8f0", "background": "#f8fafc"}

    # Feedback override
    with_feedback = _style_palette("business", feedback="Make it cooler")
    assert with_feedback == {
        "accent": "#0f766e",
        "soft": "#ccfbf1",
        "background": "#f8fafc",
    }


@pytest.mark.unit
@pytest.mark.anyio
async def test_render_svg():
    title = "Test Article Title"
    summary_lines = ["Summary 1", "Summary 2", "Summary 3"]
    key_points = ["Key point A", "Key point B", "Key point C"]

    svg_content = await render_svg(
        title=title,
        summary_lines=summary_lines,
        key_points=key_points,
        visual_plan=[],
        style="business",
    )

    assert "<svg" in svg_content
    assert "</svg>" in svg_content
    assert title in svg_content
    assert "Summary 1" in svg_content
    assert "Summary 2" in svg_content
    assert "Summary 3" in svg_content

    # Check key point circles are rendered
    assert 'cx="774"' in svg_content
    # There should be 3 key points numbered 1, 2, 3
    assert ">1</text>" in svg_content
    assert ">2</text>" in svg_content
    assert ">3</text>" in svg_content
    assert "Key point A" in svg_content
    assert "Key point B" in svg_content
    assert "Key point C" in svg_content
