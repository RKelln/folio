"""Tests for thread-safe rate limiter in folio.core.throttle."""

from __future__ import annotations

import threading
import time
import pytest

from folio.core.throttle import RateLimiter


class TestRateLimiterWait:
    """Tests for RateLimiter.wait()."""

    def test_wait_with_rate_enabled_sleeps(self):
        """With rate=10, two rapid calls should sleep on the second one."""
        limiter = RateLimiter(requests_per_second=10)
        t0 = time.perf_counter()
        limiter.wait()
        t1 = time.perf_counter()
        limiter.wait()
        t2 = time.perf_counter()

        first_elapsed = t1 - t0
        second_elapsed = t2 - t1

        assert first_elapsed < 0.01
        assert second_elapsed >= 0.05

    def test_wait_with_rate_disabled_zero(self):
        """Rate of 0 disables limiting; wait() returns immediately."""
        limiter = RateLimiter(requests_per_second=0)
        t0 = time.perf_counter()
        limiter.wait()
        limiter.wait()
        limiter.wait()
        t1 = time.perf_counter()
        elapsed = t1 - t0
        assert elapsed < 0.01

    def test_wait_with_negative_rate_disabled(self):
        """Negative rate is treated as disabled; wait() returns immediately."""
        limiter = RateLimiter(requests_per_second=-5)
        t0 = time.perf_counter()
        limiter.wait()
        limiter.wait()
        t1 = time.perf_counter()
        elapsed = t1 - t0
        assert elapsed < 0.01

    def test_throughput_matches_rate(self):
        """With rate=50, 50 calls should complete in roughly 1 second."""
        limiter = RateLimiter(requests_per_second=50)
        t0 = time.perf_counter()
        for _ in range(50):
            limiter.wait()
        t1 = time.perf_counter()
        elapsed = t1 - t0
        assert 0.8 <= elapsed <= 1.5

    def test_throughput_rate_10(self):
        """With rate=10, 10 calls should take roughly 1 second."""
        limiter = RateLimiter(requests_per_second=10)
        t0 = time.perf_counter()
        for _ in range(10):
            limiter.wait()
        t1 = time.perf_counter()
        elapsed = t1 - t0
        assert 0.7 <= elapsed <= 1.3

    def test_wait_with_very_high_rate(self):
        """Very high rate effectively disables limiting."""
        limiter = RateLimiter(requests_per_second=1000000)
        t0 = time.perf_counter()
        for _ in range(1000):
            limiter.wait()
        t1 = time.perf_counter()
        elapsed = t1 - t0
        assert elapsed < 0.1

    def test_first_call_never_sleeps(self):
        """The first call to wait() always returns immediately."""
        for rate in [0.1, 1, 10, 100]:
            limiter = RateLimiter(requests_per_second=rate)
            t0 = time.perf_counter()
            limiter.wait()
            t1 = time.perf_counter()
            assert (t1 - t0) < 0.01

    def test_wait_with_rate_1(self):
        """With rate=1, two consecutive calls must be ~1 second apart."""
        limiter = RateLimiter(requests_per_second=1)
        limiter.wait()
        t0 = time.perf_counter()
        limiter.wait()
        t1 = time.perf_counter()
        elapsed = t1 - t0
        assert 0.8 <= elapsed <= 1.5

    def test_wait_with_rate_2(self):
        """With rate=2, two calls should be ~0.5 seconds apart."""
        limiter = RateLimiter(requests_per_second=2)
        limiter.wait()
        t0 = time.perf_counter()
        limiter.wait()
        t1 = time.perf_counter()
        elapsed = t1 - t0
        assert 0.3 <= elapsed <= 0.8


class TestRateLimiterConcurrency:
    """Tests for concurrent access to RateLimiter."""

    def test_concurrent_threads_no_crash(self):
        """Multiple threads calling wait() concurrently should not crash."""
        limiter = RateLimiter(requests_per_second=100)
        errors = []
        barrier = threading.Barrier(10)

        def worker():
            try:
                barrier.wait()
                for _ in range(50):
                    limiter.wait()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_concurrent_threads_call_count(self):
        """Multiple threads each call wait() a known number of times without failure."""
        limiter = RateLimiter(requests_per_second=200)
        results = []
        lock = threading.Lock()

        def worker(thread_id):
            count = 0
            try:
                for _ in range(30):
                    limiter.wait()
                    count += 1
            except Exception as e:
                with lock:
                    results.append(f"error: {e}")
            with lock:
                results.append(count)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 8
        assert all(r == 30 for r in results)

    def test_two_threads_share_limiter(self):
        """Two threads sharing a limiter respect the combined rate."""
        limiter = RateLimiter(requests_per_second=100)
        counts = []
        lock = threading.Lock()

        def worker():
            count = 0
            for _ in range(50):
                limiter.wait()
                count += 1
            with lock:
                counts.append(count)

        t0 = time.perf_counter()
        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        t1_time = time.perf_counter()

        elapsed = t1_time - t0
        assert len(counts) == 2
        assert counts == [50, 50]
        assert elapsed < 3.0


class TestRateLimiterEdgeCases:
    """Edge case tests for RateLimiter."""

    def test_default_rate_is_5(self):
        """Default requests_per_second is 5."""
        limiter = RateLimiter()
        assert limiter._min_interval == pytest.approx(0.2)

    def test_min_interval_calculation(self):
        """_min_interval is correctly calculated as 1/rate."""
        limiter = RateLimiter(requests_per_second=4)
        assert limiter._min_interval == pytest.approx(0.25)

    def test_rate_zero_min_interval_zero(self):
        """Rate of 0 sets _min_interval to 0."""
        limiter = RateLimiter(requests_per_second=0)
        assert limiter._min_interval == 0.0

    def test_rate_negative_min_interval_zero(self):
        """Negative rate sets _min_interval to 0."""
        limiter = RateLimiter(requests_per_second=-10)
        assert limiter._min_interval == 0.0

    def test_lock_is_reentrant_safe(self):
        """Lock attribute is a threading.Lock instance."""
        limiter = RateLimiter()
        assert isinstance(limiter._lock, type(threading.Lock()))

    def test_wait_does_not_deadlock_on_rapid_calls(self):
        """Thousands of rapid calls should not deadlock."""
        limiter = RateLimiter(requests_per_second=1000)
        for _ in range(1000):
            limiter.wait()
