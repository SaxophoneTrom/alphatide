"""Tests for alert-history persistence (audit trail of pushed alerts)."""

from alphatide.bot.state import append_alert, load_recent_alerts, load_subscribers, save_subscribers
from alphatide.core.models import Alert, AlertKind


def _alert(score=88.0, kind=AlertKind.SMART_MONEY):
    return Alert(
        kind=kind, score=score, headline="Wintermute — receive $408,000 mETH",
        detail="d", token="mETH", address="0xabc", tx_hash="0xdead",
    )


def test_alert_history_roundtrip(tmp_path):
    path = str(tmp_path / "alerts.jsonl")
    append_alert(path, _alert(score=10), ts="2026-06-15T03:00:00+00:00")
    append_alert(path, _alert(score=20, kind=AlertKind.ANOMALY), ts="2026-06-15T03:05:00+00:00")
    rows = load_recent_alerts(path, n=10)
    assert len(rows) == 2
    assert rows[-1]["kind"] == "anomaly"
    assert rows[0]["score"] == 10
    assert rows[0]["headline"].startswith("Wintermute")


def test_load_recent_caps_n(tmp_path):
    path = str(tmp_path / "alerts.jsonl")
    for i in range(20):
        append_alert(path, _alert(score=i), ts=f"2026-06-15T03:{i:02d}:00+00:00")
    rows = load_recent_alerts(path, n=5)
    assert len(rows) == 5
    assert rows[-1]["score"] == 19  # most recent last


def test_load_recent_missing_file(tmp_path):
    assert load_recent_alerts(str(tmp_path / "nope.jsonl")) == []


def test_subscribers_roundtrip(tmp_path):
    path = str(tmp_path / "subs.json")
    save_subscribers(path, {1, 2, 3})
    assert load_subscribers(path) == {1, 2, 3}
