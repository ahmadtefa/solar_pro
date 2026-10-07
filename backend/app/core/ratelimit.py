"""Rate limiting middleware.

A token-bucket / sliding-window limiter that works in-process.  For multi
worker deployments the same interface can be backed by Redis (see
``docs/deployment.md``); the limiter is intentionally pluggable so the switch
does not touch route code.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

WINDOW_SECONDS = 60


@dataclass(slots=True)
class RateLimitRule:
    limit: int
    window: int = WINDOW_SECONDS


class SlidingWindowLimiter:
    """In-memory sliding window counter keyed by an arbitrary string."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window: int = WINDOW_SECONDS) -> tuple[bool, int]:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False, 0
        bucket.append(now)
        return True, limit - len(bucket)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


limiter = SlidingWindowLimiter()

_SENSITIVE_PATHS = {
    "/api/v1/auth/login": settings.login_rate_limit_per_minute,
    "/api/v1/auth/refresh": settings.login_rate_limit_per_minute,
    "/api/v1/auth/forgot-password": 10,
    "/api/v1/auth/reset-password": 10,
    "/api/v1/auth/change-password": 10,
}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject abusive traffic with 429 before hitting business logic."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.rate_limit_enabled or settings.is_testing:
            return await call_next(request)

        path = request.url.path
        if path.startswith(("/docs", "/openapi.json", "/health")):
            return await call_next(request)

        limit = _SENSITIVE_PATHS.get(path)
        if limit is None:
            limit = settings.rate_limit_requests_per_minute

        identity = request.headers.get("authorization") or _client_ip(request)
        key = f"{identity}:{path if limit != settings.rate_limit_requests_per_minute else 'global'}"
        allowed, remaining = limiter.check(key, limit)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "rate_limited",
                    "message": "Too many requests, please slow down",
                    "details": {"retry_after_seconds": WINDOW_SECONDS},
                },
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
