"""Tiny persistence for push subscribers so a restart doesn't drop them.

Stored as a JSON list of chat IDs at settings.subscribers_file (gitignored).
"""

from __future__ import annotations

import json
from pathlib import Path


def load_subscribers(path: str) -> set[int]:
    p = Path(path)
    if not p.exists():
        return set()
    try:
        return {int(x) for x in json.loads(p.read_text(encoding="utf-8"))}
    except Exception:
        return set()


def save_subscribers(path: str, subs: set[int]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(subs)), encoding="utf-8")
