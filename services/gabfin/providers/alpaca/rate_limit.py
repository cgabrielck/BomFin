"""A token bucket that records what it had to do, not just what it did.

A rate limiter that silently truncates is worse than no limiter: the
caller cannot tell a short read from a complete one. This bucket counts
the waits it performed, so a caller can report that the request was
throttled rather than pretending it was not.
"""
import time
from dataclasses import dataclass, field

#: Token arithmetic tolerance. Without it, a bucket refilled by exactly the
#: requested amount falls a fraction short of the target through floating
#: point rounding, and the wait loop never converges.
EPSILON = 1e-9


@dataclass
class TokenBucket:
    """A token bucket sized in requests per minute.

    The clock and sleep functions are injected so a test can advance time
    without waiting for it.
    """

    rate_per_minute: int
    capacity: int | None = None
    monotonic: object = time.monotonic
    sleep: object = time.sleep
    _tokens: float = field(init=False, default=0.0)
    _updated: float = field(init=False, default=0.0)
    waits: int = field(init=False, default=0)
    waited_seconds: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        if self.rate_per_minute <= 0:
            raise ValueError('A rate limiter needs a positive rate')
        if self.capacity is None:
            self.capacity = self.rate_per_minute
        self._tokens = float(self.capacity)
        self._updated = self.monotonic()

    @property
    def tokens_per_second(self) -> float:
        return self.rate_per_minute / 60.0

    def acquire(self, tokens: int = 1) -> float:
        """Take tokens, sleeping if needed. Returns the seconds waited.

        The wait is computed once and then honoured, rather than being
        recomputed in a loop. A loop that recomputes the shortfall after
        sleeping can never finish, because the refilled amount lands a
        rounding error short of the target and the loop asks for more.
        """
        if tokens > self.capacity:
            raise ValueError('A request cannot exceed the bucket capacity')
        waited = 0.0
        while True:
            now = self.monotonic()
            self._tokens = min(
                float(self.capacity),
                self._tokens + (now - self._updated) * self.tokens_per_second,
            )
            self._updated = now
            if self._tokens + EPSILON >= tokens:
                self._tokens = max(0.0, self._tokens - tokens)
                return waited
            needed = (tokens - self._tokens) / self.tokens_per_second
            if needed <= EPSILON:
                # The shortfall is rounding noise; grant the tokens rather
                # than sleep for a duration that would not change anything.
                self._tokens = max(0.0, self._tokens - tokens)
                return waited
            waited += needed
            self.waits += 1
            self.waited_seconds += needed
            self.sleep(needed)
