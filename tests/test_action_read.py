"""Tests for the Action Read layer (signal → actionable interpretation)."""

from alphatide.analytics.action_read import attach_ai_note, build_read, is_high_conviction
from alphatide.core.models import Alert, AlertKind


def _alert(kind, extra, score=80.0):
    return Alert(kind=kind, score=score, headline="h", detail="d", extra=extra)


def test_market_maker_is_non_directional_low_actionability():
    a = _alert(AlertKind.SMART_MONEY, {"entity_type": "market-maker", "direction": "accumulate"})
    r = build_read(a)
    assert r.actionability == "low"
    assert "Neutral" in r.stance


def test_fund_accumulation_is_bullish_lean_medium():
    a = _alert(AlertKind.SMART_MONEY, {"entity_type": "fund", "direction": "accumulate"})
    r = build_read(a)
    assert r.stance == "Bullish-lean"
    assert r.actionability == "medium"


def test_fund_distribution_is_bearish_lean():
    a = _alert(AlertKind.SMART_MONEY, {"entity_type": "fund", "direction": "distribute"})
    assert build_read(a).stance == "Bearish-lean"


def test_convergence_accumulation_is_high_conviction():
    a = _alert(AlertKind.CONVERGENCE, {"direction": "accumulate", "n_entities": 3})
    r = build_read(a)
    assert r.actionability == "high"
    assert is_high_conviction(a) or is_high_conviction(_attach(a))


def _attach(a):
    from alphatide.analytics.action_read import attach_read
    return attach_read(a)


def test_anomaly_is_attention_only():
    a = _alert(AlertKind.ANOMALY, {"zscore": 5.0, "ratio": 8.0})
    assert build_read(a).stance == "Attention only"


def test_every_read_has_a_risk_disclaimer():
    for kind, extra in [
        (AlertKind.SMART_MONEY, {"entity_type": "fund", "direction": "accumulate"}),
        (AlertKind.CONVERGENCE, {"direction": "accumulate", "n_entities": 2}),
        (AlertKind.INFLOW, {"entity_type": "cex"}),
        (AlertKind.ANOMALY, {"zscore": 4.0}),
    ]:
        assert "advice" in build_read(_alert(kind, extra)).risk.lower()


class _FakeSurf:
    """Stand-in Surf client to test AI-note wiring without spending credits."""
    def __init__(self, reply): self.reply = reply
    def chat(self, system, user, model="surf-1.5-instant"): return self.reply


def test_attach_ai_note_sets_note_when_surf_replies():
    a = _alert(AlertKind.CONVERGENCE, {"direction": "accumulate", "n_entities": 3})
    attach_ai_note(a, _FakeSurf("3 funds accumulating — watch for a pullback entry."))
    assert a.ai_note and "funds" in a.ai_note


def test_attach_ai_note_tolerates_no_reply():
    a = _alert(AlertKind.CONVERGENCE, {"direction": "accumulate", "n_entities": 3})
    attach_ai_note(a, _FakeSurf(None))
    assert a.ai_note is None
