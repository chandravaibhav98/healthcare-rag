from __future__ import annotations

import pytest

from app.core.rate_limit import Rate, RateLimitExceededError, TokenBucketLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize(
    ("spec", "capacity", "period"),
    [("60/minute", 60, 60.0), ("5/second", 5, 1.0), ("100/hour", 100, 3600.0)],
)
def test_parse(spec: str, capacity: int, period: float) -> None:
    assert Rate.parse(spec) == Rate(capacity, period)


@pytest.mark.parametrize("spec", ["", "0/minute", "ten/minute", "5/fortnight", "5 per minute"])
def test_parse_rejects_bad_specs(spec: str) -> None:
    with pytest.raises(ValueError, match="invalid rate"):
        Rate.parse(spec)


def test_burst_then_refill() -> None:
    clock = FakeClock()
    limiter = TokenBucketLimiter(Rate(3, 3.0), clock=clock)  # 1 token per second
    for _ in range(3):
        limiter.hit("a")
    with pytest.raises(RateLimitExceededError) as exc:
        limiter.hit("a")
    assert exc.value.retry_after_s == 1
    limiter.hit("b")  # other clients are unaffected
    clock.now = 1.0
    limiter.hit("a")  # one token refilled


def test_key_store_is_bounded() -> None:
    limiter = TokenBucketLimiter(Rate(1, 60.0), clock=FakeClock(), max_keys=2)
    limiter.hit("a")
    limiter.hit("b")
    limiter.hit("c")  # evicts "a", the least recently seen
    limiter.hit("a")  # so "a" starts with a full bucket again
    with pytest.raises(RateLimitExceededError):
        limiter.hit("c")
