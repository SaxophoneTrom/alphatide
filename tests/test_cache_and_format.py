"""Tests for the TTL cache and Telegram (Alert-based) formatting."""

from alphatide.bot.formatting import format_alert, format_digest
from alphatide.core.cache import TTLCache
from alphatide.core.models import Alert, AlertKind


def test_ttl_cache_expiry():
    c = TTLCache(ttl=100)
    c.set("a", {"x": 1}, now=0)
    assert c.get("a", now=50) == {"x": 1}
    assert c.get("a", now=200) is None  # expired


def test_ttl_cache_missing_dedups_and_filters():
    c = TTLCache(ttl=100)
    c.set("a", 1, now=0)
    miss = c.missing(["a", "b", "b", "c"], now=10)
    assert miss == ["b", "c"]  # 'a' cached, 'b' deduped


def _alert(kind=AlertKind.SMART_MONEY, score=88.0):
    return Alert(
        kind=kind, score=score, emoji="🧠",
        headline="Wintermute — receive $408,000 mETH",
        detail="known cross-chain smart money on Mantle",
        token="mETH",
        address="0xabcdef0000000000000000000000000000001234",
        tx_hash="0xdeadbeef00aa",
    )


def test_format_alert_contains_key_facts():
    out = format_alert(_alert())
    assert "Wintermute" in out
    assert "mETH" in out
    assert "88" in out
    assert "mantlescan.xyz" in out


def test_format_digest_empty():
    assert "calm" in format_digest([]).lower()


def test_format_digest_ranks_and_dedup_key():
    a = _alert(score=40)
    b = _alert(kind=AlertKind.CONVERGENCE, score=90)
    out = format_digest([a, b])
    assert "Wintermute" in out
    # dedup keys differ by kind
    assert a.dedup_key != b.dedup_key
