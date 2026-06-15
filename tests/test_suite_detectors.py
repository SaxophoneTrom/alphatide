"""Tests for the detector suite: B (convergence), C (inflow), I (anomaly)."""

from alphatide.analytics.anomaly import VolumeAnomalyDetector
from alphatide.analytics.convergence import ConvergenceDetector
from alphatide.analytics.inflow import InflowDetector
from alphatide.core.models import AddressLabel, AlertKind, DetectionContext, TransferEvent
from alphatide.data.mantle_client import large_movers

WM = "0x0000006daea1723962647b7e189d311d757fb793"
JUMP = "0xf584f8728b874a6a5c7a8d4d387c9aae9172d621"
BINANCE = "0x28c6c06298d514db089934071355e5743bf21d60"
FRESH = "0xfreshwallet000000000000000000000000beef00"


def _ev(frm, to, usd, sym="mETH", tx="0xtx"):
    return TransferEvent(tx, 1, sym, "0xtok", frm, to, usd, usd)


def _ctx(events, labels, history=None):
    movers = large_movers(events, 10_000)
    return DetectionContext(events, movers, labels, 10_000, history or {})


def test_convergence_fires_on_two_entities_same_token():
    events = [_ev("0xpool", WM, 408_000), _ev("0xpool", JUMP, 323_000)]
    labels = {
        WM: AddressLabel(WM, entity_name="Wintermute", entity_type="fund"),
        JUMP: AddressLabel(JUMP, entity_name="Jump", entity_type="fund"),
    }
    alerts = ConvergenceDetector().detect_ctx(_ctx(events, labels))
    assert len(alerts) == 1
    assert alerts[0].kind == AlertKind.CONVERGENCE
    assert "mETH" in alerts[0].headline


def test_convergence_silent_on_single_entity():
    events = [_ev("0xpool", WM, 408_000)]
    labels = {WM: AddressLabel(WM, entity_name="Wintermute", entity_type="fund")}
    assert ConvergenceDetector().detect_ctx(_ctx(events, labels)) == []


def test_inflow_fires_on_cex_outbound():
    events = [_ev(BINANCE, FRESH, 540_000, sym="WMNT")]
    labels = {
        BINANCE: AddressLabel(BINANCE, entity_name="Binance", entity_type="cex",
                              labels=("Hot Wallet",)),
    }
    alerts = InflowDetector().detect_ctx(_ctx(events, labels))
    assert len(alerts) == 1
    assert alerts[0].kind == AlertKind.INFLOW
    assert "Binance" in alerts[0].headline


def test_inflow_ignores_fund_and_inbound():
    # a fund (not bridge/cex) and an inbound-to-cex transfer → no inflow alert
    events = [_ev("0xpool", BINANCE, 540_000)]  # money going TO the cex, not out
    labels = {BINANCE: AddressLabel(BINANCE, entity_name="Binance", entity_type="cex")}
    assert InflowDetector().detect_ctx(_ctx(events, labels)) == []


def test_anomaly_fires_on_volume_spike_with_history():
    events = [_ev("0xa", "0xb", 500_000, sym="mETH")]
    history = {"mETH": [50_000.0] * 10}  # baseline ~50k, current 500k → big z
    alerts = VolumeAnomalyDetector(threshold=3.0).detect_ctx(_ctx(events, {}, history))
    assert len(alerts) == 1
    assert alerts[0].kind == AlertKind.ANOMALY
    assert alerts[0].extra["zscore"] > 3
    assert "spike" in alerts[0].headline


def test_anomaly_silent_without_history():
    events = [_ev("0xa", "0xb", 500_000, sym="mETH")]
    alerts = VolumeAnomalyDetector().detect_ctx(_ctx(events, {}, {}))
    assert alerts == []  # not enough history to judge


def test_anomaly_silent_on_volume_drop():
    """A volume *drop* is just quiet, not alpha — must never alert."""
    events = [_ev("0xa", "0xb", 5_000, sym="mETH")]   # current far below baseline
    history = {"mETH": [50_000.0] * 10}
    det = VolumeAnomalyDetector(threshold=3.0, min_volume_usd=0)  # isolate spike logic
    assert det.detect_ctx(_ctx(events, {}, history)) == []


def test_anomaly_silent_below_volume_floor():
    """A spike on trivial absolute volume is noise — filtered by the floor."""
    events = [_ev("0xa", "0xb", 12_000, sym="mETH")]  # 12x of $1k baseline but tiny
    history = {"mETH": [1_000.0] * 10}
    det = VolumeAnomalyDetector(threshold=3.0, min_volume_usd=50_000)
    assert det.detect_ctx(_ctx(events, {}, history)) == []


def test_anomaly_silent_on_statistically_odd_but_tiny_ratio():
    """The real-world '1.7× baseline' case: 3σ but economically nothing → no alert."""
    # very stable history (low variance) → a 1.7x move clears 3σ but not 3x ratio
    history = {"WMNT": [100_000.0, 101_000, 99_000, 100_500, 99_500, 100_200, 99_800, 100_100]}
    events = [_ev("0xa", "0xb", 170_000, sym="WMNT")]  # 1.7x baseline
    det = VolumeAnomalyDetector(threshold=3.0, min_volume_usd=50_000, min_ratio=3.0)
    assert det.detect_ctx(_ctx(events, {}, history)) == []


def test_push_worthiness_gates_weak_anomalies():
    from alphatide.analytics.action_read import is_push_worthy
    from alphatide.core.models import Alert, AlertKind

    weak = Alert(kind=AlertKind.ANOMALY, score=55, headline="h", detail="d",
                 extra={"ratio": 1.7})
    big = Alert(kind=AlertKind.ANOMALY, score=70, headline="h", detail="d",
                extra={"ratio": 8.0})
    fund = Alert(kind=AlertKind.SMART_MONEY, score=60, headline="h", detail="d",
                 extra={"entity_type": "fund"})
    assert not is_push_worthy(weak)   # logged but not pushed
    assert is_push_worthy(big)         # dramatic spike → push
    assert is_push_worthy(fund)        # named actor → always push
