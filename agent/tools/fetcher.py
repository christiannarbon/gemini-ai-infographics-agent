from __future__ import annotations

import asyncio
import gzip
import html
import ipaddress
import logging
import re
import socket
import zlib
from typing import Optional, Union
from urllib.parse import urljoin, urlparse

import httpx

from agent.tools.gemini_client import article_fetch_max_bytes, is_mock_mode

try:
    import trafilatura
except ImportError:
    trafilatura = None

logger = logging.getLogger(__name__)


async def fetch_article(url: str) -> dict[str, str]:
    """Fetch a public article URL and return its title plus cleaned article text.

    Args:
        url: Public HTTP or HTTPS article URL to fetch.

    Returns:
        A dictionary with `title` and cleaned `text` keys.
    """
    if is_mock_mode():
        host = urlparse(url).netloc or "example.com"
        title = f"Learning Agent Runtime from {host}'s Article"
        body = (
            "This article introduces how to embed AI Agents into enterprise business applications. "
            "The Agent retrieves information from a URL, and executes summarization, structuring, and artifact generation as a sequence of actions. "
            "Using Google ADK, you can define the Agent's behavior while separating the responsibilities of tools, "
            "and deploy it to Agent Runtime to be called stably from a Web App. "
            "Cloud Run runs the FastAPI Web frontend, and Cloud Storage saves the generated images or SVGs. "
            "In the demo, we first verify the UX and processing order in mock mode without depending on external APIs, "
            "and then replace it with Gemini text model and Nano Banana Pro / Gemini image model."
        )
        return {"title": title, "text": body}

    response = await _fetch_public_url(url)

    title, text = await _extract_article_text(response.text, str(response.url))
    return {"title": title, "text": text[:12000]}


async def _fetch_public_url(url: str) -> httpx.Response:
    current_url = url
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "User-Agent": "GeminiEnterpriseAgentPoC/1.0",
    }
    async with httpx.AsyncClient(
        follow_redirects=False, timeout=15, headers=headers
    ) as client:
        for _ in range(5):
            await _assert_public_http_url(current_url)
            async with client.stream("GET", current_url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        break
                    current_url = urljoin(str(response.url), location)
                    continue
                response.raise_for_status()
                raw_content = await _read_limited_response(
                    response, article_fetch_max_bytes()
                )
                content = _decode_response_content(raw_content, response.headers)
                headers = httpx.Headers(response.headers)
                headers.pop("content-encoding", None)
                headers["content-length"] = str(len(content))
                return httpx.Response(
                    response.status_code,
                    headers=headers,
                    content=content,
                    request=response.request,
                    extensions=response.extensions,
                )
    raise ValueError("Too many redirects while fetching article")


async def _read_limited_response(response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_raw():
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"Article response exceeds {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_response_content(raw_content: bytes, headers: httpx.Headers) -> bytes:
    encoding = headers.get("content-encoding", "").lower().strip()
    if not encoding or encoding == "identity":
        return raw_content

    try:
        if encoding == "gzip":
            return gzip.decompress(raw_content)
        if encoding == "deflate":
            return zlib.decompress(raw_content)
    except (OSError, zlib.error) as exc:
        logger.warning(
            "Ignoring invalid Content-Encoding=%s while fetching article: %s",
            encoding,
            exc,
        )
        return raw_content

    logger.warning(
        "Ignoring unsupported Content-Encoding=%s while fetching article", encoding
    )
    return raw_content


async def _extract_article_text(raw_html: str, url: str) -> tuple[str, str]:
    title = _extract_title(raw_html) or url

    if trafilatura:
        extracted = await asyncio.to_thread(
            trafilatura.extract,
            raw_html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        if extracted and extracted.strip():
            return title, _normalize_text(extracted)

    return title, _clean_html(raw_html)


async def _assert_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("URL host is required")

    host = parsed.hostname
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None

    if literal_ip:
        _reject_private_address(literal_ip)
        return

    addresses = await _resolve_host(host)
    if not addresses:
        raise ValueError("URL host could not be resolved")

    for address in addresses:
        _reject_private_address(ipaddress.ip_address(address))


async def _resolve_host(host: str) -> set[str]:
    def resolve() -> set[str]:
        return {
            result[4][0]
            for result in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        }

    return await asyncio.to_thread(resolve)


def _reject_private_address(
    address: Union[ipaddress.IPv4Address, ipaddress.IPv6Address],
) -> None:
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValueError(
            "Private, local, or reserved network addresses are not allowed"
        )


def _clean_html(raw_html: str) -> str:
    without_scripts = re.sub(
        r"<(script|style).*?</\1>", " ", raw_html, flags=re.I | re.S
    )
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    unescaped = html.unescape(without_tags)
    return _normalize_text(unescaped)


def _extract_title(raw_html: str) -> Optional[str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.I | re.S)
    return _clean_html(title_match.group(1)) if title_match else None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()
