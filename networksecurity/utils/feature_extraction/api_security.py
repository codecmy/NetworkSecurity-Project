"""
Lightweight request throttling and optional API-key auth for the prediction
endpoints. In-memory only (single-process, per worker) — swap for Redis when
scaling out.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Dict, List

from fastapi import HTTPException, Request

API_KEY = os.getenv("API_KEY", "").strip()
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))


class _SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            window_start = now - self.window_seconds
            hits = [t for t in self._hits.get(key, []) if t >= window_start]
            if len(hits) >= self.max_requests:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


_limiter = _SlidingWindowLimiter(RATE_LIMIT_PER_MINUTE)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_api_key(request: Request) -> None:
    """Reject requests when an API_KEY is configured and not supplied."""
    if not API_KEY:
        return
    provided = request.headers.get("x-api-key", "")
    if provided != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


def enforce_rate_limit(request: Request) -> None:
    if not _limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please retry shortly.")
