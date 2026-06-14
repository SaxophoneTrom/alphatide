"""Abuse protection: per-user rate limiting and a global daily credit ceiling.

The bot answers anyone who knows its username, and every Surf call spends the
owner's credits. These two guards cap the damage a stranger can do:

  * RateLimiter      — caps how often a single user can trigger expensive commands
  * DailyCreditBudget — caps total Surf credits spent per UTC day (all users +
                        the background monitor share one budget)
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from typing import Callable


class RateLimiter:
    """Fixed-window per-key limiter: at most `max_per_window` hits per window."""

    def __init__(self, max_per_window: int, window_seconds: int = 60) -> None:
        self.max = max_per_window
        self.window = window_seconds
        self._hits: dict[object, deque[float]] = defaultdict(deque)

    def allow(self, key: object, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        dq = self._hits[key]
        while dq and now - dq[0] > self.window:
            dq.popleft()
        if len(dq) >= self.max:
            return False
        dq.append(now)
        return True

    def retry_after(self, key: object, now: float | None = None) -> int:
        now = now if now is not None else time.time()
        dq = self._hits[key]
        if not dq:
            return 0
        return max(0, int(self.window - (now - dq[0])))


class DailyCreditBudget:
    """Tracks Surf credits spent today and refuses spend past `limit`.

    Resets automatically at UTC midnight. `clock` is injectable for tests.
    """

    def __init__(self, limit: int, clock: Callable[[], datetime] | None = None) -> None:
        self.limit = limit
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._day: date = self._today()
        self.spent: int = 0

    def _today(self) -> date:
        return self._clock().date()

    def _roll(self) -> None:
        d = self._today()
        if d != self._day:
            self._day = d
            self.spent = 0

    def remaining(self) -> int:
        self._roll()
        return max(0, self.limit - self.spent)

    def can_spend(self, n: int = 1) -> bool:
        return self.remaining() >= n

    def record(self, n: int) -> None:
        self._roll()
        self.spent += max(0, n)
