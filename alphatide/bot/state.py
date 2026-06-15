"""Tiny persistence for runtime state (gitignored under .state/):

  * push subscribers — so a restart doesn't drop them
  * alert history (JSONL) — so we can audit exactly what was pushed and when
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from alphatide.core.models import Alert


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


def append_alert(path: str, alert: Alert, ts: str | None = None) -> None:
    """Append one pushed alert to the JSONL history."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": alert.kind.value,
        "score": alert.score,
        "headline": alert.headline,
        "token": alert.token,
        "address": alert.address,
        "tx_hash": alert.tx_hash,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_recent_alerts(path: str, n: int = 10) -> list[dict]:
    """Return the last `n` alert records (most recent last)."""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows[-n:]
