"""Tests for the /demo scenario builder used by the bot's live demo."""

from alphatide.analytics.action_read import is_high_conviction
from alphatide.core.models import AlertKind
from alphatide.demo import build_demo_alerts


def test_demo_produces_high_conviction_convergence():
    alerts = build_demo_alerts()
    kinds = {a.kind for a in alerts}
    # all four detector types should be represented
    assert {AlertKind.SMART_MONEY, AlertKind.CONVERGENCE, AlertKind.INFLOW,
            AlertKind.ANOMALY} <= kinds

    conv = [a for a in alerts if a.kind == AlertKind.CONVERGENCE]
    assert conv, "demo must yield a convergence signal"
    c = conv[0]
    assert c.extra.get("n_entities") == 3          # 3 funds converging
    assert is_high_conviction(c)                    # → triggers the AI read
    assert c.read and c.read["actionability"] == "high"


def test_demo_top_alert_is_strong():
    alerts = build_demo_alerts()
    # the headline signal should be a labeled-actor alert, not a volume anomaly
    assert alerts[0].kind != AlertKind.ANOMALY
    assert alerts[0].score >= 70


def test_demo_is_deterministic_and_free():
    # offline fixtures → no network, repeatable
    a1 = build_demo_alerts()
    a2 = build_demo_alerts()
    assert [x.headline for x in a1] == [x.headline for x in a2]
