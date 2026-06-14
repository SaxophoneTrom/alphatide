"""A tiny TTL cache with optional JSON persistence.

Used to remember Surf address labels so we only ever pay credits once per
address (their identity is near-constant). Deliberately dependency-free.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class TTLCache:
    def __init__(self, ttl: int, path: str | Path | None = None) -> None:
        self.ttl = ttl
        self.path = Path(path) if path else None
        self._store: dict[str, tuple[float, Any]] = {}
        if self.path and self.path.exists():
            self._load()

    def get(self, key: str, now: float | None = None) -> Any | None:
        now = now if now is not None else time.time()
        hit = self._store.get(key)
        if hit is None:
            return None
        ts, value = hit
        if now - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        self._store[key] = (now, value)

    def missing(self, keys: list[str], now: float | None = None) -> list[str]:
        """Return the subset of keys not currently cached (preserves order, dedup)."""
        seen: set[str] = set()
        out: list[str] = []
        for k in keys:
            if k in seen:
                continue
            seen.add(k)
            if self.get(k, now) is None:
                out.append(k)
        return out

    def persist(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._store), encoding="utf-8")

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._store = {k: (v[0], v[1]) for k, v in raw.items()}
        except Exception:
            self._store = {}
