from __future__ import annotations

import asyncio
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
            if attempt >= retries:
                raise
            await asyncio.sleep(delay)
    raise last_error  # type: ignore[misc]
