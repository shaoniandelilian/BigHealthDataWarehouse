# -*- coding: utf-8 -*-
import threading
import time

class RateLimiter:
    """
    简单的全局限流：保证相邻请求至少间隔 1/rps 秒。
    (注意：这仅适用于单进程架构。如果在分布式 Celery 中，应使用 redis 限流器)。
    """
    def __init__(self, rps: float):
        self.min_interval = 1.0 / max(rps, 1e-9)
        self._lock = threading.Lock()
        self._next_time = 0.0

    def acquire(self):
        with self._lock:
            now = time.time()
            if now < self._next_time:
                time.sleep(self._next_time - now)
            self._next_time = time.time() + self.min_interval
