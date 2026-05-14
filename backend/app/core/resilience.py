"""Tiny retry + circuit-breaker primitives without pulling tenacity/pybreaker."""

import asyncio
import functools
import logging
import random
import time
from typing import Awaitable, Callable, TypeVar

log = logging.getLogger(__name__)
T = TypeVar("T")


def async_retry(
    *,
    attempts: int = 3,
    base_delay: float = 0.2,
    max_delay: float = 5.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
):
    """Exponential backoff with full jitter. Re-raises the final exception."""

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> T:
            for i in range(attempts):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as e:
                    if i == attempts - 1:
                        raise
                    sleep = min(max_delay, base_delay * (2**i))
                    sleep = random.uniform(0, sleep)
                    log.warning(
                        "retry %s/%s after %.2fs: %s", i + 1, attempts, sleep, e
                    )
                    await asyncio.sleep(sleep)
            raise RuntimeError("unreachable")

        return wrapper

    return decorator


class CircuitBreaker:
    """Half-open circuit breaker.

    States:
      closed   → calls pass through; failures increment a counter.
      open     → calls fast-fail until `reset_after` elapses.
      half-open→ one probe call is allowed; on success we close, otherwise re-open.
    """

    def __init__(self, *, failure_threshold: int = 5, reset_after: float = 30.0):
        self.failure_threshold = failure_threshold
        self.reset_after = reset_after
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at < self.reset_after:
            return "open"
        return "half-open"

    async def call(self, fn: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        state = self.state
        if state == "open":
            raise CircuitOpenError("circuit open")
        try:
            result = await fn(*args, **kwargs)
        except Exception:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.monotonic()
            raise
        # success → reset
        self._failures = 0
        self._opened_at = None
        return result


class CircuitOpenError(RuntimeError):
    pass
