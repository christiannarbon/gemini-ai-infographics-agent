from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


StepStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class ProgressStep:
    label: str
    status: StepStatus = "pending"
    detail: str = ""


@dataclass
class SummaryResult:
    session_id: str
    url: str
    title: str
    summary_lines: list[str]
    key_points: list[str]
    article_text: str
    text_backend: str = "mock"
    progress: list[ProgressStep] = field(default_factory=list)


@dataclass
class GraphicResult:
    session_id: str
    visual_plan: list[str]
    artifact_path: str
    svg: str = ""
    image_backend: str = "fallback-svg"
    artifact_url: str = ""
    artifact_mime_type: str = "image/svg+xml"
    visual_style: str = "pop"
    style_reason: str = ""
    progress: list[ProgressStep] = field(default_factory=list)
