"""Configurable HTTP adapter used to call the application under test."""
import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from .ssrf import BlockedTarget, resolve_safe

MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_TEMPLATE = {"question": "{{input}}"}
DEFAULT_MAPPING = {"answer": "answer", "citations": "citations"}


@dataclass
class AdapterResult:
    ok: bool
    latency_ms: int
    status_code: int | None = None
    raw_text: str = ""
    body: Any = None  # parsed JSON, if any
    answer: str | None = None
    citations: list = field(default_factory=list)
    error: str | None = None


def _fill(template: Any, value: str) -> Any:
    if isinstance(template, str):
        return template.replace("{{input}}", value)
    if isinstance(template, dict):
        return {k: _fill(v, value) for k, v in template.items()}
    if isinstance(template, list):
        return [_fill(v, value) for v in template]
    return template


def _dig(obj: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            return None
    return obj


async def call_application(*, url: str, question: str, template: dict | None, mapping: dict | None, auth_type: str,
                           auth_secret: str | None, auth_header: str | None, timeout_s: float,
                           allow_private: bool) -> AdapterResult:
    started = time.perf_counter()
    ms = lambda: int((time.perf_counter() - started) * 1000)  # noqa: E731
    try:
        host, ip = await resolve_safe(url, allow_private)
    except BlockedTarget as e:
        return AdapterResult(False, ms(), error=f"blocked: {e}")

    u = urlparse(url)
    port = f":{u.port}" if u.port else ""
    pinned = urlunparse(u._replace(netloc=f"{ip}{port}" if ":" not in ip else f"[{ip}]{port}"))
    headers = {"Host": u.netloc.split("@")[-1], "Content-Type": "application/json", "Accept": "application/json"}
    if auth_type == "bearer" and auth_secret:
        headers[auth_header or "Authorization"] = f"Bearer {auth_secret}" if not auth_header else auth_secret
    payload = _fill(template or DEFAULT_TEMPLATE, question)
    ext = {"sni_hostname": host} if u.scheme == "https" else {}
    try:
        # verify against the hostname, connect to the vetted IP, never follow redirects (they could point inside).
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=False, verify=True) as client:
            async with client.stream("POST", pinned, json=payload, headers=headers, extensions=ext) as resp:
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        return AdapterResult(False, ms(), resp.status_code, error="response exceeds 1 MB limit")
                    chunks.append(chunk)
                raw = b"".join(chunks).decode("utf-8", errors="replace")
                status = resp.status_code
    except httpx.TimeoutException:
        return AdapterResult(False, ms(), error=f"timeout after {timeout_s:g} s")
    except httpx.HTTPError as e:
        return AdapterResult(False, ms(), error=f"connection error: {type(e).__name__}")

    result = AdapterResult(200 <= status < 300, ms(), status, raw)
    if not result.ok:
        result.error = f"HTTP {status}"
        return result
    try:
        result.body = json.loads(raw)
    except json.JSONDecodeError:
        return result  # not JSON: deterministic checks decide whether that is acceptable
    m = {**DEFAULT_MAPPING, **(mapping or {})}
    ans = _dig(result.body, m["answer"])
    result.answer = ans if isinstance(ans, str) else (None if ans is None else json.dumps(ans))
    cites = _dig(result.body, m["citations"])
    result.citations = cites if isinstance(cites, list) else []
    return result
