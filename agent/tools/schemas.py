from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


class ArticleSummary(BaseModel):
    summary_lines: list[str] = Field(
        description="Exactly three concise English lines that summarize the article's story.",
        min_length=3,
        max_length=3,
    )
    key_points: list[str] = Field(
        description="Four to six English article-reading notes for infographic material.",
        min_length=4,
        max_length=6,
    )


class VisualPlan(BaseModel):
    plan_items: list[str] = Field(
        description="Four to six English composition instructions for an infographic.",
        min_length=4,
        max_length=6,
    )


class StyleDecision(BaseModel):
    style: Literal["business", "pop", "minimal"] = Field(
        description="Best visual style for this article."
    )
    reason: str = Field(
        description="One concise English sentence explaining the style choice."
    )


@dataclass
class GeneratedImage:
    data: bytes
    mime_type: str
    backend: str
    error: str = ""
