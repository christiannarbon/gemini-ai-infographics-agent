import ipaddress
import pytest
import zlib
import gzip
import httpx

from agent.errors import ArticleFetchError
from agent.tools.fetcher import (
    _reject_private_address,
    _assert_public_http_url,
    _decode_response_content,
)


@pytest.mark.unit
def test_reject_private_address_ipv4():
    # IPv4 loopback
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("127.0.0.1"))

    # IPv4 private
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("10.0.0.1"))
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("192.168.1.1"))
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("172.16.0.1"))

    # IPv4 link-local
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("169.254.0.1"))

    # IPv4 multicast
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("224.0.0.1"))

    # IPv4 reserved
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("240.0.0.1"))

    # IPv4 unspecified
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("0.0.0.0"))

    # IPv4 public (should not raise)
    _reject_private_address(ipaddress.ip_address("8.8.8.8"))


@pytest.mark.unit
def test_reject_private_address_ipv6():
    # IPv6 loopback
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("::1"))

    # IPv6 link-local
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("fe80::1"))

    # IPv6 private (unique local)
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("fc00::1"))

    # IPv6 multicast
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("ff00::1"))

    # IPv6 unspecified
    with pytest.raises(ValueError):
        _reject_private_address(ipaddress.ip_address("::"))

    # IPv6 public (should not raise)
    _reject_private_address(ipaddress.ip_address("2001:4860:4860::8888"))


@pytest.mark.unit
@pytest.mark.anyio
async def test_assert_public_http_url_schemes_and_hosts():
    # Invalid schemes
    with pytest.raises(ArticleFetchError, match="Only http and https"):
        await _assert_public_http_url("file:///etc/passwd")
    with pytest.raises(ArticleFetchError, match="Only http and https"):
        await _assert_public_http_url("ftp://example.com/file")

    # Missing host
    with pytest.raises(ArticleFetchError, match="URL host is required"):
        await _assert_public_http_url("http://")


@pytest.mark.unit
@pytest.mark.anyio
async def test_assert_public_http_url_ip_literals():
    # Private IP literal
    with pytest.raises(ArticleFetchError, match="Private, local, or reserved"):
        await _assert_public_http_url("http://127.0.0.1/path")
    with pytest.raises(ArticleFetchError, match="Private, local, or reserved"):
        await _assert_public_http_url("https://10.0.0.1/path")

    # Public IP literal (should return None as connection pinning is skipped/not needed)
    res = await _assert_public_http_url("http://8.8.8.8/path")
    assert res is None


@pytest.mark.unit
@pytest.mark.anyio
async def test_assert_public_http_url_hostname_resolution(monkeypatch):
    from agent.tools import fetcher

    # Hostname resolves to public IP
    async def mock_resolve_public(host):
        return {"8.8.8.8"}

    monkeypatch.setattr(fetcher, "_resolve_host", mock_resolve_public)
    res = await _assert_public_http_url("http://example.com/path")
    assert res == "8.8.8.8"

    # Hostname resolves to private IP
    async def mock_resolve_private(host):
        return {"192.168.1.1"}

    monkeypatch.setattr(fetcher, "_resolve_host", mock_resolve_private)
    with pytest.raises(ArticleFetchError, match="Private, local, or reserved"):
        await _assert_public_http_url("http://example.com/path")

    # Hostname resolution failure (empty)
    async def mock_resolve_empty(host):
        return set()

    monkeypatch.setattr(fetcher, "_resolve_host", mock_resolve_empty)
    with pytest.raises(ArticleFetchError, match="could not be resolved"):
        await _assert_public_http_url("http://example.com/path")

    # Hostname resolution raises exception
    async def mock_resolve_error(host):
        raise OSError("DNS failure")

    monkeypatch.setattr(fetcher, "_resolve_host", mock_resolve_error)
    with pytest.raises(ArticleFetchError, match="could not be resolved"):
        await _assert_public_http_url("http://example.com/path")


@pytest.mark.unit
def test_decode_response_content():
    headers_identity = httpx.Headers({"Content-Encoding": "identity"})
    headers_none = httpx.Headers({})
    headers_gzip = httpx.Headers({"Content-Encoding": "gzip"})
    headers_deflate = httpx.Headers({"Content-Encoding": "deflate"})
    headers_invalid = httpx.Headers({"Content-Encoding": "br"})

    raw = b"hello world"

    # identity
    assert _decode_response_content(raw, headers_identity) == raw
    assert _decode_response_content(raw, headers_none) == raw

    # gzip
    compressed_gzip = gzip.compress(raw)
    assert _decode_response_content(compressed_gzip, headers_gzip) == raw

    # deflate
    compressor = zlib.compressobj()
    compressed_deflate = compressor.compress(raw) + compressor.flush()
    assert _decode_response_content(compressed_deflate, headers_deflate) == raw

    # invalid decompression data (gzip headers but bad payload)
    with pytest.raises(ValueError, match="Failed to decode Content-Encoding=gzip"):
        _decode_response_content(raw, headers_gzip)

    # unsupported encoding
    with pytest.raises(ValueError, match="Unsupported Content-Encoding=br"):
        _decode_response_content(raw, headers_invalid)


@pytest.mark.unit
@pytest.mark.anyio
async def test_resolve_host(monkeypatch):
    import socket
    from agent.tools.fetcher import _resolve_host

    def mock_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        # returns list of 5-tuples: (family, type, proto, canonname, sockaddr)
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("8.8.8.8", 0),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("8.8.4.4", 0),
            ),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)
    ips = await _resolve_host("google-public-dns.com")
    assert ips == {"8.8.8.8", "8.8.4.4"}
