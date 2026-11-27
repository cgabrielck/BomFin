"""The Alpaca rate limiter records what it had to do."""
import pytest

from gabfin.providers.alpaca.rate_limit import TokenBucket


class FakeClock:
    """A clock that advances only when something sleeps."""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def bucket_for(rate: int = 200) -> tuple[TokenBucket, FakeClock]:
    clock = FakeClock()
    bucket = TokenBucket(
        rate_per_minute=rate,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return bucket, clock


def test_a_fresh_bucket_serves_its_whole_capacity():
    bucket, clock = bucket_for()
    for _ in range(200):
        bucket.acquire()
    assert bucket.waits == 0
    assert clock.sleeps == []


def test_the_bucket_never_exceeds_its_rate():
    """400 requests at 200 per minute takes about a minute of clock time."""
    bucket, clock = bucket_for()
    for _ in range(400):
        bucket.acquire()
    assert clock.now >= 60.0 - 0.01


def test_the_wait_path_is_actually_exercised():
    """The bucket must really sleep, not quietly grant tokens for free."""
    bucket, clock = bucket_for()
    for _ in range(200):
        bucket.acquire()
    assert bucket.waits == 0
    for _ in range(200):
        bucket.acquire()
    assert bucket.waits == 200
    assert bucket.waited_seconds > 0
    assert len(clock.sleeps) == 200


def test_a_wait_is_counted_rather_than_hidden():
    bucket, clock = bucket_for()
    for _ in range(200):
        bucket.acquire()
    bucket.acquire()
    assert bucket.waits == 1
    assert bucket.waited_seconds > 0


def test_a_request_larger_than_the_capacity_is_refused():
    bucket, _ = bucket_for(rate=10)
    with pytest.raises(ValueError):
        bucket.acquire(11)


def test_a_non_positive_rate_is_refused():
    with pytest.raises(ValueError):
        TokenBucket(rate_per_minute=0)
