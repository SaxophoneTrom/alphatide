"""Tests for rate limiting, the daily credit budget, and budget-gated Surf."""

from datetime import datetime, timezone

from alphatide.core.limits import DailyCreditBudget, RateLimiter
from alphatide.core.models import AddressLabel
from alphatide.data.surf_client import SurfClient

WM = "0x0000006daea1723962647b7e189d311d757fb793"
ANON = "0x3333333333333333333333333333333333333333"


def test_rate_limiter_blocks_after_max():
    rl = RateLimiter(max_per_window=3, window_seconds=60)
    assert [rl.allow("u", now=0) for _ in range(3)] == [True, True, True]
    assert rl.allow("u", now=1) is False           # 4th in window → blocked
    assert rl.allow("u", now=61) is True            # window passed → allowed


def test_rate_limiter_is_per_key():
    rl = RateLimiter(max_per_window=1)
    assert rl.allow("a", now=0) is True
    assert rl.allow("b", now=0) is True             # different user, own bucket
    assert rl.allow("a", now=0) is False


def test_daily_budget_caps_and_resets():
    days = [datetime(2026, 6, 13, tzinfo=timezone.utc)]
    b = DailyCreditBudget(limit=5, clock=lambda: days[0])
    assert b.can_spend(5) and not b.can_spend(6)
    b.record(4)
    assert b.remaining() == 1
    b.record(10)                                    # overspend recorded
    assert b.remaining() == 0 and not b.can_spend(1)
    days[0] = datetime(2026, 6, 14, tzinfo=timezone.utc)  # next UTC day
    assert b.remaining() == 5                       # auto-reset


def test_surf_respects_budget_falls_back_to_fixtures():
    # budget already exhausted → no live spend, fixtures still answer
    spent = DailyCreditBudget(limit=0)
    s = SurfClient(api_key="x", budget=spent)       # has key but budget=0
    res = s.label_addresses([WM, ANON])
    assert s.credits_used == 0                       # never hit the network
    assert res[WM].entity_name == "Wintermute"       # served from fixtures
    assert not res[ANON].is_labeled
