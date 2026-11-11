from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import Settings
from app.core.errors import AppError


class InMemoryRateLimiter:
    """Sliding-window limiter for single-process/dev use.

    Production runs multiple workers, so this must be replaced with a Redis
    implementation before horizontal scaling. It is still real enforcement
    (not a stub) for the current single-instance deployment target.
    """

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                raise AppError(
                    429,
                    "rate_limited",
                    "Too many requests. Please try again shortly.",
                    title="Too Many Requests",
                ) from None
            bucket.append(now)


def client_ip(request: Request) -> str:
    # Trust X-Forwarded-For only when the deployment terminates TLS at a known
    # proxy. Documented in infra; default is the socket peer.
    return request.client.host if request.client else "unknown"


def rate_limit_dependency(settings: Settings, bucket_name: str):
    limiter = InMemoryRateLimiter(settings.auth_rate_limit_per_minute)

    async def dependency(request: Request) -> None:
        limiter.check(f"{bucket_name}:{client_ip(request)}")

    return dependency
