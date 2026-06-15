from __future__ import annotations

from typing import Optional


def build_summary_prompt(title: str, article_text: str) -> str:
    return f"""Summarize the following article in English, and create an article understanding memo to be used for an infographic.

Constraints:
- summary_lines MUST be exactly 3 lines
- summary_lines summarizes the main point and story of the article in 3 lines of natural explanatory text
- key_points must be 4 to 6 items
- key_points should not be a simple paraphrase of summary_lines, but supplementary notes that show how to read the article
- key_points should express background, flow, author's assertions, impressive techniques, concrete examples, and post-reading implications in natural text
- key_points should be about 60 to 120 characters per item, avoiding becoming just classification labels or measure names by being too short
- Do not mechanically attach classification labels like "Technology:", "Solution:", "Metric:" to key_points. Use them naturally only when necessary
- Include proper nouns and numbers only when they are effective for understanding the article or its atmosphere
- Use only the content written in the article, expressing it in a way that retains both the general point and concrete examples
- Output must strictly follow the specified schema
- ALWAYS respond in English regardless of the input language

Title:
{title}

Text:
{article_text[:12000]}
"""


def build_style_prompt(
    summary_lines: list[str],
    key_points: list[str],
    feedback: str,
) -> str:
    return f"""Choose one infographic style that best fits the following summary and key points.

Options:
- business: for enterprises, calm colors, structured diagrams
- pop: for general readers, bright colors, friendly icons
- minimal: limited information, lots of whitespace, quiet presentation style

3-line Summary:
{chr(10).join(summary_lines)}

Key Points:
{chr(10).join(key_points)}

User Feedback:
{feedback or "None"}

Constraints:
- style must be one of business / pop / minimal
- reason must be one English sentence
- Output must strictly follow the specified schema
- ALWAYS respond in English regardless of the input language
"""


def build_visual_plan_prompt(
    summary_lines: list[str],
    key_points: list[str],
    feedback: str,
    style: str,
) -> str:
    return f"""Create an infographic composition plan in English.

3-line Summary:
{chr(10).join(summary_lines)}

Key Points:
{chr(10).join(key_points)}

User Feedback:
{feedback or "None"}

Selected Style:
{style}

Constraints:
- plan_items must be 4 to 6 items
- Instructions should clarify placement on the screen, concepts to emphasize, and eye movement guidance
- Use color tones, density, and icon expressions that fit the selected style
- Use the 3-line summary as the overall story of the article, for top headings, central flows, or short explanatory bands
- Read key points as article understanding memos, and summarize them as short labels, sticky notes, speech bubbles, or annotations next to icons in the image
- Do not treat key points as a categorized list of measures, but make a composition that conveys the article's atmosphere, assertions, flow, and concrete examples
- Do not place the 3-line summary and key points side by side as text boxes of the same granularity
- Limit the text displayed in the image to only the contents of the 3-line summary and key points
- Do not include processing steps of the app, generation infrastructure, or explanatory context that is not part of the article content
- Output must strictly follow the specified schema
- ALWAYS respond in English regardless of the input language
"""


def build_image_prompt(
    style: str,
    summary_lines: Optional[list[str]],
    key_points: Optional[list[str]],
    visual_plan: list[str],
    style_directive: str,
) -> str:
    allowed_summary = summary_lines or []
    allowed_points = key_points or []
    return f"""Generate an English infographic image.

Purpose:
- Express as a single easy-to-read infographic by using the article's 3-line summary as the overall story and the key points as diagram materials
- Diagram the article content itself, not an explanation of the application or generation system

Text allowed to be displayed in the image:
3-line Summary (materials for the overall story):
{chr(10).join(f"- {line}" for line in allowed_summary) or "- 3-line Summary"}

Key Points (article understanding memos. Summarize into short display text if necessary):
{chr(10).join(f"- {point}" for point in allowed_points) or "- Key Points"}

Composition Plan (for placement reference only. Do not write the composition plan text in the image):
{chr(10).join(f"- {item}" for item in visual_plan)}

Selected Style:
{style}

Style Directives:
{style_directive}

Expression:
- 16:9 landscape aspect ratio
- White background, easy-to-read thick lines, icons, arrows, sticky note-style memos
- English text should be short, large, and easy to read
- Treat the 3-line summary as a short story band at the top, or as a large central flow
- Use key points as article understanding memos, rephrasing them shortly as sticky notes, speech bubbles, keyword chips, or labels next to icons in the image
- Do not write out all key points as long sentences as they are, but compress them into short expressions conveying the main point, impressive examples, flow, and implications
- According to the selected style, 'business' should have clear structure, 'pop' should be friendly, and 'minimal' should express with whitespace and few elements
- Do not make a composition that just lines up the 3-line summary and key points in text boxes of the same size
- Do not lean too much towards a boxed layout like tables, long text cards, or presentation slides; make a composition where flow, relationships, contrast, and hierarchy are visible
- Do not add words to the image that are not in the article text, such as app processing steps, generation infrastructure, explanatory contexts, or composition plan labels
- Keep headings only to those that indicate article content, such as "3-line Summary" or "Key Points"
- Do not mix colors or decorations that contradict the selected style
- ALWAYS generate text in English regardless of the input language
"""
