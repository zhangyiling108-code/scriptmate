from __future__ import annotations

import asyncio
import random
import httpx
from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")


async def with_retry(
    func: Callable[[], Awaitable[T]],
    retries: int = 2,
    delay: float = 0.2,
) -> T:
    last_error = None
    for attempt in range(retries + 1):
        try:
            return await func()
        except Exception as exc:  # pragma: no cover - simple shared helper
            last_error = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {408, 429, 500, 502, 503, 504}:
                raise
            if attempt >= retries:
                raise
            retry_delay = delay * (2 ** attempt) + random.uniform(0, delay * 0.25)
            if isinstance(exc, httpx.HTTPStatusError):
                try:
                    retry_delay = max(retry_delay, min(float(exc.response.headers.get("Retry-After", "0")), 30.0))
                except ValueError:
                    pass
            await asyncio.sleep(retry_delay)
    raise last_error  # type: ignore[misc]
