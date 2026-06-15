"""Generates SVG markup for fallback infographics and wraps base64 images inside SVG tags.

Not responsible for: fetching articles, generating prompts, or storage management.
Depends on: standard library.
"""

from __future__ import annotations

import base64
import html
import re


async def render_svg(
    title: str,
    summary_lines: list[str],
    key_points: list[str],
    visual_plan: list[str],
    feedback: str = "",
    style: str = "business",
) -> str:
    """Render a deterministic fallback SVG infographic.

    Args:
        title: Article title.
        summary_lines: Three summary lines to render.
        key_points: Important points to render.
        visual_plan: Kept for workflow API symmetry; not rendered in the fallback SVG.
        feedback: Optional user feedback from regeneration.
        style: Selected visual style.

    Returns:
        SVG markup for the generated fallback artifact.
    """
    palette = _style_palette(style, feedback)
    accent = palette["accent"]
    title_node = _title_node(title)
    summary_items = "".join(
        _summary_node(i, line) for i, line in enumerate(summary_lines)
    )
    point_items = "".join(
        _point_node(i, point, accent) for i, point in enumerate(key_points[:6])
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="680" viewBox="0 0 1100 680" role="img" aria-label="Infographic">
  <style>
    .bg {{ fill: #f8fafc; }}
    .panel {{ fill: #ffffff; stroke: #cbd5e1; stroke-width: 2; }}
    .title {{ font: 800 30px sans-serif; fill: #ffffff; }}
    .label {{ font: 700 16px sans-serif; fill: #475569; }}
    .summary {{ font: 600 18px sans-serif; fill: #0f172a; }}
    .small {{ font: 500 14px sans-serif; fill: #334155; }}
    .arrow {{ stroke: #64748b; stroke-width: 3; fill: none; marker-end: url(#arrow); }}
  </style>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
      <path d="M0,0 L0,6 L9,3 z" fill="#64748b" />
    </marker>
  </defs>
  <rect width="1100" height="680" rx="0" fill="{palette["background"]}" />
  <rect x="40" y="36" width="1020" height="92" rx="8" fill="{accent}" />
  {title_node}

  <rect class="panel" x="54" y="150" width="640" height="410" rx="8" />
  <text x="78" y="180" class="label">3-line Summary</text>
  {summary_items}

  <rect class="panel" x="732" y="150" width="314" height="410" rx="8" />
  <text x="758" y="184" class="label">Key Points</text>
  {point_items}
</svg>"""


def _render_image_svg(image_bytes: bytes, mime_type: str = "image/png") -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="680" viewBox="0 0 1100 680" role="img" aria-label="Infographic">
  <rect width="1100" height="680" fill="#ffffff" />
  <image href="data:{html.escape(mime_type)};base64,{encoded}" x="0" y="0" width="1100" height="680" preserveAspectRatio="xMidYMid meet" />
</svg>"""


def _style_palette(style: str, feedback: str = "") -> dict[str, str]:
    if feedback.strip():
        return {"accent": "#0f766e", "soft": "#ccfbf1", "background": "#f8fafc"}
    if style == "pop":
        return {"accent": "#ea580c", "soft": "#ffedd5", "background": "#fff7ed"}
    if style == "minimal":
        return {"accent": "#475569", "soft": "#e2e8f0", "background": "#f8fafc"}
    return {"accent": "#2563eb", "soft": "#dbeafe", "background": "#f8fafc"}


def _style_image_directive(style: str) -> str:
    directives = {
        "business": "Colors: Calm blue/gray. Lines: Thin and orderly. Icons: Corporate presentation style. Whitespace: Standard.",
        "pop": "Colors: Vivid yellow, orange, turquoise. Lines: Thick hand-drawn style. Icons: Round and friendly. Expression: Bright and active.",
        "minimal": "Colors: Monotone + 1 accent color. Lines: Thin and sharp. Whitespace: Plenty. Element count: Kept low. Atmosphere: Quiet.",
    }
    return directives.get(style, directives["business"])


def _title_node(title: str) -> str:
    tspans = _svg_tspans(
        title, x=72, first_y=76, max_chars=34, max_lines=2, line_gap=34
    )
    return f'<text class="title">{tspans}</text>'


def _summary_node(index: int, line: str) -> str:
    y = 224 + index * 108
    text = f"{index + 1}. {line}"
    tspans = _svg_tspans(text, x=78, first_y=y, max_chars=29, max_lines=3, line_gap=22)
    return f'<text class="summary">{tspans}</text>'


def _point_node(index: int, point: str, accent: str) -> str:
    y = 220 + index * 56
    tspans = _svg_tspans(
        point, x=808, first_y=y - 14, max_chars=13, max_lines=2, line_gap=16
    )
    return f"""
  <circle cx="774" cy="{y}" r="18" fill="{accent}" opacity="0.9" />
  <text x="768" y="{y + 6}" font-family="sans-serif" font-size="17" font-weight="800" fill="#ffffff">{index + 1}</text>
  <text class="small">{tspans}</text>"""


def _svg_tspans(
    text: str, x: int, first_y: int, max_chars: int, max_lines: int, line_gap: int
) -> str:
    lines = _wrap_svg_text(text, max_chars=max_chars, max_lines=max_lines)
    return "".join(
        f'<tspan x="{x}" y="{first_y + i * line_gap}">{html.escape(line)}</tspan>'
        for i, line in enumerate(lines)
    )


def _wrap_svg_text(text: str, max_chars: int, max_lines: int) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return [""]

    lines: list[str] = []
    remaining = compact
    while remaining and len(lines) < max_lines:
        if len(remaining) <= max_chars:
            lines.append(remaining)
            remaining = ""
            break
        split_at = remaining.rfind(" ", 0, max_chars + 1)
        if split_at < max_chars // 2:
            split_at = max_chars
        lines.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining and lines:
        lines[-1] = lines[-1].rstrip("。,.、") + "..."
    return lines
