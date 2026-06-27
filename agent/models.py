from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

StepStatus = Literal["pending", "running", "done", "failed"]


class ProgressStep(BaseModel):
    label: str
    status: StepStatus = "pending"
    detail: str = ""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if len(args) >= 1:
            kwargs["label"] = args[0]
        if len(args) >= 2:
            kwargs["status"] = args[1]
        if len(args) >= 3:
            kwargs["detail"] = args[2]
        super().__init__(**kwargs)


class SummaryResult(BaseModel):
    session_id: str
    url: str
    title: str
    summary_lines: list[str]
    key_points: list[str]
    article_text: str
    text_backend: str = "mock"
    progress: list[ProgressStep] = Field(default_factory=list)


class GraphicResult(BaseModel):
    session_id: str
    visual_plan: list[str]
    artifact_path: str
    svg: str = ""
    image_backend: str = "fallback-svg"
    artifact_url: str = ""
    artifact_mime_type: str = "image/svg+xml"
    visual_style: str = "pop"
    style_reason: str = ""
    progress: list[ProgressStep] = Field(default_factory=list)
