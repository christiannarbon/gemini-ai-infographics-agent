"""Defines structural Pydantic models and dataclasses for structured API outputs and image payloads.

Not responsible for: performing API calls, parsing raw HTML, or rendering graphics.
Depends on: standard library and pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

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


class ArticleContent(BaseModel):
    title: str
    text: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class SummaryToolResult(BaseModel):
    summary_lines: list[str]
    key_points: list[str]
    backend: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)
