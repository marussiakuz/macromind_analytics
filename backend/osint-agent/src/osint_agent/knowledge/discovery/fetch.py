"""Safe document fetch: SSRF guards, size/time/redirect limits (MIMO_DISCOVERY §3.4)."""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

MAX_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = 20.0
ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254"}


class FetchError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass
class FetchResult:
    ok: bool
    url: str
    final_url: str | None = None
    content_type: str | None = None
    data: bytes | None = None
    sha256: str | None = None
    error_code: str | None = None
    error: str | None = None


def _is_private_host(host: str) -> bool:
    if not host or host.lower() in BLOCKED_HOSTS:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True  # cannot resolve → refuse
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return True
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return True
    return False


def assert_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise FetchError("bad_scheme", f"scheme {parsed.scheme}")
    if not parsed.hostname:
        raise FetchError("bad_host", "no host")
    if _is_private_host(parsed.hostname):
        raise FetchError("blocked_internal", f"host {parsed.hostname}")
    return url


async def fetch_document(url: str, *, client: httpx.AsyncClient | None = None) -> FetchResult:
    """GET with redirect + DNS checks after each hop. Never follow to internal nets."""
    try:
        assert_public_url(url)
    except FetchError as exc:
        return FetchResult(False, url, error_code=exc.code, error=str(exc))

    owns = client is None
    c = client or httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False)
    current = url
    data = b""
    ctype = None
    try:
        for _ in range(MAX_REDIRECTS + 1):
            assert_public_url(current)
            # Stream before buffering: the size limit must apply during download.
            request = c.build_request("GET", current)
            resp = await c.send(request, stream=True)
            if resp.status_code in {301, 302, 303, 307, 308}:
                loc = resp.headers.get("location")
                await resp.aclose()
                if not loc:
                    return FetchResult(False, url, error_code="bad_redirect", error="no location")
                current = str(httpx.URL(current).join(loc))
                continue
            if resp.status_code >= 400:
                await resp.aclose()
                return FetchResult(False, url, final_url=current,
                                   error_code=f"http_{resp.status_code}",
                                   error=f"HTTP {resp.status_code}")
            ctype = resp.headers.get("content-type")
            chunks = []
            size = 0
            try:
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        return FetchResult(False, url, final_url=current,
                                           error_code="too_large", error=f">{MAX_BYTES} bytes")
                    chunks.append(chunk)
            finally:
                await resp.aclose()
            data = b"".join(chunks)
            break
        else:
            return FetchResult(False, url, error_code="too_many_redirects", error="redirect limit")
    except httpx.TimeoutException:
        return FetchResult(False, url, error_code="timeout", error="fetch timeout")
    except httpx.HTTPError as exc:
        return FetchResult(False, url, error_code="network", error=str(exc)[:200])
    except FetchError as exc:
        return FetchResult(False, url, error_code=exc.code, error=str(exc))
    finally:
        if owns:
            await c.aclose()

    return FetchResult(
        True,
        url,
        final_url=current,
        content_type=ctype,
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
    )
