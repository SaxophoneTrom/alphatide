"""Tests for the cross-chain smart money detector and its building blocks."""

from alphatide.analytics.scoring import entity_weight, score_signal, size_factor
from alphatide.analytics.smart_money import CrossChainSmartMoneyDetector
from alphatide.core.models import AddressLabel, TransferEvent
from alphatide.data.mantle_client import _ZERO, large_movers
from alphatide.data.surf_client import SurfClient

WINTERMUTE = "0x0000006daea1723962647b7e189d311d757fb793"
ANON = "0x2222222222222222222222222222222222222222"


def ev(frm, to, usd, sym="mETH"):
    return TransferEvent("0xtx", 1, sym, "0xtok", frm, to, usd, usd)


def test_large_movers_filters_small_and_zero():
    events = [
        ev(WINTERMUTE, "0xpool", 50_000),
        ev(ANON, "0xpool", 500),          # below threshold
        ev(_ZERO, WINTERMUTE, 99_000),    # zero address dropped, WM kept
    ]
    movers = large_movers(events, min_usd=10_000)
    assert WINTERMUTE in movers
    assert ANON not in movers
    assert _ZERO not in movers


def test_size_factor_log_scaled():
    assert size_factor(10_000) == 0.0
    assert 0.4 < size_factor(100_000) < 0.6
    assert size_factor(1_000_000) == 1.0
    assert size_factor(10_000_000) == 1.5  # capped


def test_entity_weight_known_vs_anon():
    fund = AddressLabel("0x", entity_name="Wintermute", entity_type="fund")
    anon = AddressLabel.empty("0x")
    assert entity_weight(fund) == 1.0
    assert entity_weight(anon) == 0.0


def test_score_zero_for_anonymous():
    assert score_signal(AddressLabel.empty("0x"), 1_000_000) == 0.0


def test_score_rewards_identity_and_size():
    fund = AddressLabel("0x", entity_name="Jump", entity_type="fund", confidence=1.0)
    small = score_signal(fund, 20_000)
    big = score_signal(fund, 2_000_000)
    assert big > small > 0


def test_detector_keeps_only_smart_money():
    surf = SurfClient(offline=True)
    detector = CrossChainSmartMoneyDetector(surf)
    events = [
        ev(WINTERMUTE, "0xpool", 408_000),   # labeled fund → keep
        ev(ANON, "0xpool", 999_000),         # anonymous → drop
    ]
    signals = detector.detect(events, min_usd=10_000)
    assert len(signals) == 1
    assert signals[0].label.entity_name == "Wintermute"
    assert signals[0].score > 0
    assert surf.credits_used == 0  # offline mode spends nothing


def test_dex_pool_is_not_smart_money():
    """Regression: a DEX pool (entity_type 'dex') must NOT be flagged as smart money."""
    from alphatide.analytics.smart_money import signals_from_context
    from alphatide.core.models import DetectionContext

    pool = "0x5d54d430d1fd9425976147318e6080479bffc16d"  # Merchant Moe pool (real)
    label = AddressLabel(pool, entity_name="Merchant Moe", entity_type="dex",
                         labels=("Pool",))
    assert entity_weight(label) == 0.0  # the leak is closed
    events = [ev("0xsender", pool, 13_681, sym="WMNT")]
    ctx = DetectionContext(events, large_movers(events, 10_000), {pool: label}, 10_000)
    assert signals_from_context(ctx) == []
