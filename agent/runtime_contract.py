from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from agent.models import GraphicResult, ProgressStep, SummaryResult


RuntimeOperation = Literal["unknown", "summarize_url", "generate_graphic", "regenerate_graphic"]


class RuntimeProgressStep(BaseModel):
    label: str
    status: Literal["pending", "running", "done", "failed"] = "pending"
    detail: str = ""

    def to_result(self) -> ProgressStep:
        return ProgressStep(label=self.label, status=self.status, detail=self.detail)

    @classmethod
    def from_result(cls, step: ProgressStep) -> "RuntimeProgressStep":
        return cls(label=step.label, status=step.status, detail=step.detail)


class RuntimeSummaryPayload(BaseModel):
    session_id: str
    url: str
    title: str
    summary_lines: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    article_text: str = ""
    text_backend: str = "unknown"
    progress: list[RuntimeProgressStep] = Field(default_factory=list)

    def to_result(self) -> SummaryResult:
        return SummaryResult(
            session_id=self.session_id,
            url=self.url,
            title=self.title,
            summary_lines=self.summary_lines,
            key_points=self.key_points,
            article_text=self.article_text,
            text_backend=self.text_backend,
            progress=[step.to_result() for step in self.progress],
        )

    @classmethod
    def from_result(cls, summary: SummaryResult) -> "RuntimeSummaryPayload":
        return cls(
            session_id=summary.session_id,
            url=summary.url,
            title=summary.title,
            summary_lines=summary.summary_lines,
            key_points=summary.key_points,
            article_text=summary.article_text,
            text_backend=summary.text_backend,
            progress=[RuntimeProgressStep.from_result(step) for step in summary.progress],
        )


class RuntimeGraphicPayload(BaseModel):
    session_id: str
    visual_plan: list[str] = Field(default_factory=list)
    artifact_path: str
    svg: str = ""
    image_backend: str = "fallback-svg"
    artifact_url: str = ""
    artifact_mime_type: str = "image/svg+xml"
    visual_style: str = "business"
    style_reason: str = ""
    progress: list[RuntimeProgressStep] = Field(default_factory=list)

    def to_result(self) -> GraphicResult:
        return GraphicResult(
            session_id=self.session_id,
            visual_plan=self.visual_plan,
            artifact_path=self.artifact_path,
            svg=self.svg,
            image_backend=self.image_backend,
            artifact_url=self.artifact_url,
            artifact_mime_type=self.artifact_mime_type,
            visual_style=self.visual_style,
            style_reason=self.style_reason,
            progress=[step.to_result() for step in self.progress],
        )

    @classmethod
    def from_result(cls, graphic: GraphicResult) -> "RuntimeGraphicPayload":
        return cls(
            session_id=graphic.session_id,
            visual_plan=graphic.visual_plan,
            artifact_path=graphic.artifact_path,
            svg=graphic.svg,
            image_backend=graphic.image_backend,
            artifact_url=graphic.artifact_url,
            artifact_mime_type=graphic.artifact_mime_type,
            visual_style=graphic.visual_style,
            style_reason=graphic.style_reason,
            progress=[RuntimeProgressStep.from_result(step) for step in graphic.progress],
        )


class RuntimeWorkflowResponse(BaseModel):
    operation: RuntimeOperation
    summary: Optional[RuntimeSummaryPayload] = None
    graphic: Optional[RuntimeGraphicPayload] = None
    error: str = ""
