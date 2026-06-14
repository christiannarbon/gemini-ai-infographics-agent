from __future__ import annotations

import asyncio
import base64
import logging
from typing import Optional

from agent.config import get_settings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_GENAI_CLIENT = None


def _get_genai_client():
    global _GENAI_CLIENT
    if _GENAI_CLIENT is None:
        _GENAI_CLIENT = _build_genai_client()
    return _GENAI_CLIENT


def _build_genai_client():
    from google import genai

    return genai.Client()


def close_genai_client() -> None:
    global _GENAI_CLIENT
    if _GENAI_CLIENT is None:
        return
    close = getattr(_GENAI_CLIENT, "close", None)
    if close:
        close()
    _GENAI_CLIENT = None


async def _call_with_retries(operation_factory, operation: str):
    max_attempts = get_settings().gemini_max_attempts
    base_delay = get_settings().gemini_retry_base_delay_seconds
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation_factory()
        except Exception as exc:
            last_error = exc
            if attempt >= max_attempts or not _is_retryable_exception(exc):
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "%s failed with retryable error on attempt %s/%s; retrying in %.1fs: %s",
                operation,
                attempt,
                max_attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"{operation} failed") from last_error


def _is_retryable_exception(exc: Exception) -> bool:
    status_code = _exception_status_code(exc)
    if status_code in RETRYABLE_STATUS_CODES:
        return True
    message = str(exc)
    return any(str(code) in message for code in RETRYABLE_STATUS_CODES)


def _exception_status_code(exc: Exception) -> Optional[int]:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, int):
            return enum_value

    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code if isinstance(status_code, int) else None


async def _generate_structured_content(prompt: str, schema_model):
    if not get_settings().has_gemini_credentials:
        raise RuntimeError(
            "GEMINI_API_KEY, GOOGLE_API_KEY, or Vertex AI Gemini environment settings are required"
        )

    async_client = _get_genai_client().aio
    response = await _call_with_retries(
        lambda: async_client.models.generate_content(
            model=get_settings().gemini_text_model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema_model,
            },
        ),
        operation="gemini-structured-content",
    )
    if response.parsed is not None:
        return response.parsed
    return schema_model.model_validate_json(response.text)


async def _generate_image_data(prompt: str) -> tuple[bytes, str]:
    from google.genai import types

    async_client = _get_genai_client().aio
    response = await _call_with_retries(
        lambda: async_client.models.generate_content(
            model=get_settings().gemini_image_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
                candidate_count=1,
            ),
        ),
        operation="gemini-image-generation",
    )
    if not response.candidates:
        return b"", "image/png"
    parts = (
        response.candidates[0].content.parts if response.candidates[0].content else []
    )
    for part in parts:
        if part.inline_data and part.inline_data.data:
            data = part.inline_data.data
            if isinstance(data, str):
                data = base64.b64decode(data)
            return data, part.inline_data.mime_type or "image/png"
    return b"", "image/png"


def is_mock_mode() -> bool:
    return get_settings().mock_mode


def text_model_name() -> str:
    return get_settings().gemini_text_model


def image_model_name() -> str:
    return get_settings().gemini_image_model


def has_gemini_credentials() -> bool:
    return get_settings().has_gemini_credentials


def article_fetch_max_bytes() -> int:
    return get_settings().article_fetch_max_bytes


def display_model_name(model_name: str) -> str:
    labels = {
        "gemini-2.5-flash-image": "gemini-2.5-flash-image (Nano Banana)",
        "gemini-3-pro-image-preview": "gemini-3-pro-image-preview (Nano Banana Pro)",
        "gemini-3-pro-image": "gemini-3-pro-image (Nano Banana Pro)",
    }
    return labels.get(model_name, model_name)
