from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StepStatus = Literal["pending", "running", "done", "failed"]


class ProgressStep(BaseModel):
    label: str
    status: StepStatus = "pending"
    detail: str = ""


class SummaryResult(BaseModel):
    session_id: str
    url: str
    title: str
    summary_lines: list[str]
    key_points: list[str]
    article_text: str
    # Note: Domain default is 'mock'; wire-contract default is 'unknown'
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
    # Note: Domain default is 'pop'; wire-contract default is 'business'
    visual_style: str = "pop"
    style_reason: str = ""
    progress: list[ProgressStep] = Field(default_factory=list)
