from __future__ import annotations

import httpx


def build_async_client(timeout: float = 10.0) -> httpx.AsyncClient:
    effective_timeout = httpx.Timeout(connect=min(timeout, 15.0), read=max(timeout, 60.0), write=max(timeout, 30.0), pool=min(timeout, 15.0))
    return httpx.AsyncClient(timeout=effective_timeout, follow_redirects=True, trust_env=True)
