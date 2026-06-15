"""Inline keyboards for alerts — one-tap wallet tracking.

The valuable thing to track is an *unlabeled* address (an anonymous mover behind
a spike). Labeled actors are already named, so they get no button.
Telegram callback_data is capped at 64 bytes; "track:" + a 42-char address = 48.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from alphatide.core.models import Alert

TRACK_PREFIX = "track:"


def trackable_addresses(alert: Alert) -> list[str]:
    """Unlabeled addresses worth offering a one-tap /track for (deduped, ≤3)."""
    out: list[str] = []
    for c in alert.extra.get("contributors", []):
        addr = c.get("addr")
        if addr and not c.get("who"):  # unlabeled only
            out.append(addr)
    seen: set[str] = set()
    uniq: list[str] = []
    for a in out:
        al = a.lower()
        if al.startswith("0x") and len(al) == 42 and al not in seen:
            seen.add(al)
            uniq.append(al)
    return uniq[:3]


def build_track_keyboard(alert: Alert) -> InlineKeyboardMarkup | None:
    addrs = trackable_addresses(alert)
    if not addrs:
        return None
    rows = [
        [InlineKeyboardButton(
            f"🔍 Track {a[:6]}…{a[-4:]}", callback_data=f"{TRACK_PREFIX}{a}"
        )]
        for a in addrs
    ]
    return InlineKeyboardMarkup(rows)
