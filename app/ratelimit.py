import threading
import time


class TokenBucket:
    """In-process token-bucket limiter, keyed per client.

    Mirrors the approach in the floodgate project: each key refills at
    rate_per_sec up to burst. Swap this for a Redis-backed version to enforce
    the limit across multiple gateway replicas.
    """

    def __init__(self, rate_per_sec: float, burst: int):
        self.rate = rate_per_sec
        self.burst = float(burst)
        self._state: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_monotonic)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._state.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens >= 1:
                self._state[key] = (tokens - 1, now)
                return True
            self._state[key] = (tokens, now)
            return False
