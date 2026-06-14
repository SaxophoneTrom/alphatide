"""Tests for the TTL cache and Telegram formatting."""

from alphatide.bot.formatting import format_digest, format_signal
from alphatide.core.cache import TTLCache
from alphatide.core.models import Action, AddressLabel, SmartMoneySignal


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


def _sig(name="Wintermute", etype="fund", usd=408_000.0, score=88.0):
    label = AddressLabel("0xabc", entity_name=name, entity_type=etype,
                         labels=("Hot Wallet",) if etype == "cex" else ())
    return SmartMoneySignal(
        address="0xabcdef0000000000000000000000000000001234",
        label=label, action=Action.RECEIVE, token_symbol="mETH",
        amount_usd=usd, score=score, reason="test reason", tx_hash="0xdeadbeef00",
        block=1,
    )


def test_format_signal_contains_key_facts():
    out = format_signal(_sig())
    assert "Wintermute" in out
    assert "mETH" in out
    assert "88" in out
    assert "mantlescan.xyz" in out


def test_format_digest_empty():
    assert "calm" in format_digest([]).lower()


def test_format_digest_ranks():
    sigs = [_sig(score=40), _sig(name="Jump", score=90)]
    out = format_digest(sigs)
    assert "Wintermute" in out and "Jump" in out
