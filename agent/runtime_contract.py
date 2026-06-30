from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel, Field

RuntimeOperation = Literal[
    "unknown", "summarize_url", "generate_infographics", "regenerate_infographics"
]

T = TypeVar("T", bound=BaseModel)


def convert_model(source: BaseModel, target_type: type[T]) -> T:
    """Helper to convert between compatible Pydantic models by dumping and validating."""
    return target_type.model_validate(source.model_dump())


class RuntimeProgressStep(BaseModel):
    label: str
    status: Literal["pending", "running", "done", "failed"] = "pending"
    detail: str = ""


class RuntimeSummaryPayload(BaseModel):
    session_id: str
    url: str
    title: str
    summary_lines: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    article_text: str = ""
    text_backend: str = "unknown"
    progress: list[RuntimeProgressStep] = Field(default_factory=list)


class RuntimeInfographicsPayload(BaseModel):
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


class RuntimeWorkflowResponse(BaseModel):
    operation: RuntimeOperation
    summary: RuntimeSummaryPayload | None = None
    infographics: RuntimeInfographicsPayload | None = None
    error: str = ""
