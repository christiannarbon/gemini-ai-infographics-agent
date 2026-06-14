from __future__ import annotations

import asyncio
import gzip
import html
import ipaddress
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
            # Resolve and validate, then pin the connection to the validated IP
            # so httpx does not perform its own (potentially rebound) lookup.
            pinned_ip = await _assert_public_http_url(current_url)
            connect_url, extra_headers, extensions = _pin_connection(
                current_url, pinned_ip
            )
            async with client.stream(
                "GET", connect_url, headers=extra_headers, extensions=extensions
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        break
                    # Join against the logical (hostname) URL, not the pinned-IP one.
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                raw_content = await _read_limited_response(
                    response, article_fetch_max_bytes()
                )
                content = _decode_response_content(raw_content, response.headers)
                response_headers = httpx.Headers(response.headers)
                response_headers.pop("content-encoding", None)
                response_headers["content-length"] = str(len(content))
                return httpx.Response(
                    response.status_code,
                    headers=response_headers,
                    content=content,
                    request=httpx.Request("GET", current_url),
                    extensions=response.extensions,
                )
    raise ValueError("Too many redirects while fetching article")


def _pin_connection(
    url: str, pinned_ip: Optional[str]
) -> tuple[str, dict[str, str], dict[str, str]]:
    """Rewrite a URL to connect to a validated IP while preserving the host.

    Returns the connect URL (host replaced by the pinned IP), the extra request
    headers (a ``Host`` header carrying the original host), and request
    extensions (``sni_hostname`` so TLS SNI and certificate verification still
    use the original hostname). When ``pinned_ip`` is None the URL is an IP
    literal already and is returned unchanged.
    """
    if pinned_ip is None:
        return url, {}, {}

    parsed = urlparse(url)
    host = parsed.hostname or ""
    host_header = host if parsed.port is None else f"{host}:{parsed.port}"

    ip_netloc = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
    if parsed.port is not None:
        ip_netloc += f":{parsed.port}"
    connect_url = parsed._replace(netloc=ip_netloc).geturl()

    return connect_url, {"Host": host_header}, {"sni_hostname": host}


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
        # We request Accept-Encoding: identity, so a body we cannot decode is
        # off-spec. Fail rather than hand undecoded bytes to the HTML parser.
        raise ValueError(
            f"Failed to decode Content-Encoding={encoding} response body"
        ) from exc

    raise ValueError(f"Unsupported Content-Encoding={encoding} in response body")


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


async def _assert_public_http_url(url: str) -> Optional[str]:
    """Validate that ``url`` points at a public host.

    Returns the validated IP address the connection must be pinned to (closing
    the DNS-rebinding TOCTOU), or None when the URL host is already an IP literal.
    """
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
        return None

    addresses = await _resolve_host(host)
    if not addresses:
        raise ValueError("URL host could not be resolved")

    for address in addresses:
        _reject_private_address(ipaddress.ip_address(address))

    return next(iter(addresses))


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
    return _normalize_text(without_tags)


def _extract_title(raw_html: str) -> Optional[str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.I | re.S)
    return _clean_html(title_match.group(1)) if title_match else None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()
