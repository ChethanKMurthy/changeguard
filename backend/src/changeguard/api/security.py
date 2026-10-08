"""Authentication, rate limiting, and transport-level protections."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from changeguard.config import Settings
from changeguard.errors import AuthenticationError, PayloadTooLargeError, RateLimitedError


def presented_key(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.headers.get("x-api-key") or None


def check_api_key(settings: Settings, request: Request) -> None:
    """Require a configured API key when keys are set; constant-time comparison."""
    if not settings.auth_required:
        return
    supplied = presented_key(request)
    if not supplied:
        raise AuthenticationError(
            "an API key is required (Authorization: Bearer <key> or X-API-Key)"
        )
    supplied_bytes = supplied.encode()
    if not any(
        hmac.compare_digest(supplied_bytes, k.get_secret_value().encode())
        for k in settings.api_keys
    ):
        raise AuthenticationError("the API key is not valid")


def client_identity(settings: Settings, request: Request) -> str:
    """Who a rate-limit bucket belongs to.

    Behind a trusted proxy (the web app forwards every browser with the same API
    key), the forwarded client address comes first, so one visitor cannot use up
    everyone's quota. Otherwise the API key, then the socket address.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return "ip:" + forwarded.split(",")[0].strip()
    key = presented_key(request)
    if key:
        return "key:" + hashlib.sha256(key.encode()).hexdigest()[:16]
    return "ip:" + (request.client.host if request.client else "unknown")


class RateLimiter:
    """Sliding-window limiter (per process). Sufficient for a single-instance deployment."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, identity: str) -> None:
        if self.per_minute <= 0:
            return
        now = time.monotonic()
        with self._lock:
            window = self._hits.setdefault(identity, deque())
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.per_minute:
                retry = int(60 - (now - window[0])) + 1
                raise RateLimitedError(
                    f"rate limit of {self.per_minute} analyses per minute exceeded; retry in {retry}s",
                    detail={"retry_after": retry},
                )
            window.append(now)
            if len(self._hits) > 10_000:  # bound memory under address churn
                for stale in [k for k, v in self._hits.items() if not v or now - v[-1] > 60]:
                    del self._hits[stale]


class BodySizeLimitMiddleware:
    """Reject request bodies above ``max_bytes`` while streaming (works without Content-Length)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await _reject_too_large(send, self.max_bytes)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise PayloadTooLargeError(
                        f"request body exceeds {self.max_bytes // 1_000_000} MB"
                    )
            return message

        await self.app(scope, limited_receive, send)


async def _reject_too_large(send: Send, limit: int) -> None:
    import json

    body = json.dumps(
        {
            "type": "about:blank",
            "title": "Payload too large",
            "status": 413,
            "detail": f"request body exceeds {limit // 1_000_000} MB",
            "code": "payload_too_large",
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/problem+json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


async def security_headers_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Any]]
) -> Any:
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    response = await call_next(request)
    headers: MutableMapping[str, str] = response.headers
    for name, value in SECURITY_HEADERS.items():
        headers.setdefault(name, value)
    headers["X-Request-ID"] = request_id
    if request.url.path.startswith("/api/v1/analyses"):
        headers.setdefault("Cache-Control", "no-store")
    return response
