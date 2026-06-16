from __future__ import annotations

import threading
import time


class RateLimiter:
    """Thread-safe rate limiter for API calls.

    Args:
        requests_per_second: Maximum number of requests per second.
            Set to 0 to disable rate limiting.
    """

    def __init__(self, requests_per_second: float = 5):
        self._lock = threading.Lock()
        self._last_time = 0.0
        self._min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0

    def wait(self):
        with self._lock:
            elapsed = time.perf_counter() - self._last_time
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_time = time.perf_counter()
