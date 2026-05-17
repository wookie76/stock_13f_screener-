from __future__ import annotations

import random
import time
from dataclasses import dataclass

from loguru import logger


@dataclass(frozen=True)
class RespectfulFetchPolicy:
    base_sleep_seconds: float
    jitter_min_seconds: float = 0.10
    jitter_max_seconds: float = 0.75
    max_sleep_seconds: float = 60.0
    random_seed: int = 42

    def sleep(self, label: str) -> None:
        rng = random.Random(time.monotonic_ns() + self.random_seed)
        jitter = rng.uniform(self.jitter_min_seconds, self.jitter_max_seconds)
        delay = self.base_sleep_seconds + jitter
        logger.debug("{} sleep {:.2f}s", label, delay)
        time.sleep(delay)

    def backoff_sleep(self, label: str, attempt: int) -> None:
        rng = random.Random(time.monotonic_ns() + self.random_seed + attempt)
        jitter = rng.uniform(self.jitter_min_seconds, self.jitter_max_seconds)
        delay = min(self.max_sleep_seconds, (2.0**attempt) + jitter)
        logger.warning("{} backoff attempt={} sleep={:.2f}s", label, attempt, delay)
        time.sleep(delay)
