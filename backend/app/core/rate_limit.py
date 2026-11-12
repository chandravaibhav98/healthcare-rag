"""In-process token-bucket rate limiter for `/qa` (plan §4 Phase 3).

Chosen over `slowapi` because it is about 60 lines, fully typed, has an injectable clock
for deterministic tests, and needs no decorator that changes the handler signature.
Limits are per process: with several replicas, move the bucket store to Redis behind the
same interface (ADR-0008). Memory is bounded: least-recently-seen keys are evicted.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

_PERIODS: Final = {"second": 1.0, "minute": 60.0, "hour": 3600.0, "day": 86400.0}


class RateLimitExceededError(Exception):
    def __init__(self, retry_after_s: float) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after_s = retry_after_s


@dataclass(frozen=True, slots=True)
class Rate:
    capacity: int
    period_s: float

    @classmethod
    def parse(cls, spec: str) -> Rate:
        m = re.fullmatch(r"(\d+)/(second|minute|hour|day)", spec.strip())
        if not m or int(m.group(1)) < 1:
            raise ValueError(f"invalid rate {spec!r}; expected '<n>/<second|minute|hour|day>'")
        return cls(capacity=int(m.group(1)), period_s=_PERIODS[m.group(2)])


class TokenBucketLimiter:
    def __init__(
        self,
        rate: Rate,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self._rate = rate
        self._clock = clock
        self._max_keys = max_keys
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()  # key → (tokens, ts)
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        """Consume one token for `key` or raise RateLimitExceededError with Retry-After."""
        refill_per_s = self._rate.capacity / self._rate.period_s
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.pop(key, (float(self._rate.capacity), now))
            tokens = min(float(self._rate.capacity), tokens + (now - last) * refill_per_s)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                raise RateLimitExceededError(retry_after_s=math.ceil((1.0 - tokens) / refill_per_s))
            self._buckets[key] = (tokens - 1.0, now)
            while len(self._buckets) > self._max_keys:
                self._buckets.popitem(last=False)
