import asyncio
import pytest

from agent.tools.gemini_client import (
    _call_with_retries,
    _is_retryable_exception,
)


@pytest.mark.unit
@pytest.mark.anyio
async def test_retry_success_first_attempt(monkeypatch):
    attempts = 0

    async def mock_op():
        nonlocal attempts
        attempts += 1
        return "success"

    sleep_called = []

    async def mock_sleep(delay):
        sleep_called.append(delay)

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    res = await _call_with_retries(mock_op, "test_op")
    assert res == "success"
    assert attempts == 1
    assert len(sleep_called) == 0


@pytest.mark.unit
@pytest.mark.anyio
async def test_retryable_error_retries_max(monkeypatch):
    monkeypatch.setenv("GEMINI_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("GEMINI_RETRY_BASE_DELAY_SECONDS", "1.0")
    from agent.config import get_settings

    get_settings.cache_clear()

    attempts = 0

    class RetryableException(Exception):
        status_code = 500

    async def mock_op():
        nonlocal attempts
        attempts += 1
        raise RetryableException("Transient error")

    sleep_called = []

    async def mock_sleep(delay):
        sleep_called.append(delay)

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    with pytest.raises(RetryableException):
        await _call_with_retries(mock_op, "test_op")

    assert attempts == 3
    # Exponential delays: 1.0 * 2^0 = 1.0, 1.0 * 2^1 = 2.0
    assert sleep_called == [1.0, 2.0]


@pytest.mark.unit
@pytest.mark.anyio
async def test_non_retryable_error_no_retry(monkeypatch):
    monkeypatch.setenv("GEMINI_MAX_ATTEMPTS", "3")
    from agent.config import get_settings

    get_settings.cache_clear()

    attempts = 0

    class FatalException(Exception):
        status_code = 400

    async def mock_op():
        nonlocal attempts
        attempts += 1
        raise FatalException("Fatal error")

    sleep_called = []

    async def mock_sleep(delay):
        sleep_called.append(delay)

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    with pytest.raises(FatalException):
        await _call_with_retries(mock_op, "test_op")

    assert attempts == 1
    assert len(sleep_called) == 0


@pytest.mark.unit
def test_is_retryable_exception():
    class StatusException(Exception):
        def __init__(self, code):
            self.status_code = code

    class CodeException(Exception):
        def __init__(self, code):
            self.code = code

    class EnumVal:
        def __init__(self, val):
            self.value = val

    class EnumException(Exception):
        def __init__(self, val):
            self.code = EnumVal(val)

    class ResponseObj:
        def __init__(self, code):
            self.status_code = code

    class ResponseException(Exception):
        def __init__(self, code):
            self.response = ResponseObj(code)

    # Status code checks
    for code in [429, 500, 502, 503, 504]:
        assert _is_retryable_exception(StatusException(code)) is True
        assert _is_retryable_exception(CodeException(code)) is True
        assert _is_retryable_exception(EnumException(code)) is True
        assert _is_retryable_exception(ResponseException(code)) is True

    # Non-retryable
    for code in [400, 404]:
        assert _is_retryable_exception(StatusException(code)) is False

    # Message checks
    assert _is_retryable_exception(Exception("Error status 429 encountered")) is True
    assert _is_retryable_exception(Exception("Random failure 500 error")) is True
    assert _is_retryable_exception(Exception("Random 404 error")) is False


@pytest.mark.unit
@pytest.mark.anyio
async def test_retry_single_attempt_no_sleep(monkeypatch):
    monkeypatch.setenv("GEMINI_MAX_ATTEMPTS", "1")
    from agent.config import get_settings

    get_settings.cache_clear()

    attempts = 0

    class RetryableException(Exception):
        status_code = 500

    async def mock_op():
        nonlocal attempts
        attempts += 1
        raise RetryableException("Transient error")

    sleep_called = []

    async def mock_sleep(delay):
        sleep_called.append(delay)

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    with pytest.raises(RetryableException):
        await _call_with_retries(mock_op, "test_op")

    assert attempts == 1
    assert len(sleep_called) == 0
