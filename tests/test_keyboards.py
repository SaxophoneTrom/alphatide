"""Tests for the one-tap Track inline keyboard."""

from alphatide.bot.keyboards import TRACK_PREFIX, build_track_keyboard, trackable_addresses
from alphatide.core.models import Alert, AlertKind

ADDR = "0xcf76984119c7f6ae56fafe680d39c08278b7ecf4"


def _anomaly(contributors):
    return Alert(kind=AlertKind.ANOMALY, score=80, headline="h", detail="d",
                 extra={"contributors": contributors})


def test_trackable_only_unlabeled_contributors():
    a = _anomaly([
        {"who": "Binance", "addr": "0x28c6c06298d514db089934071355e5743bf21d60", "usd": 540_000},
        {"who": None, "addr": ADDR, "usd": 129_000},
    ])
    assert trackable_addresses(a) == [ADDR]  # labeled Binance excluded


def test_trackable_dedups_and_caps():
    contribs = [{"who": None, "addr": ADDR, "usd": 1}] * 5
    assert trackable_addresses(_anomaly(contribs)) == [ADDR]


def test_build_keyboard_callback_data_within_limit():
    kb = build_track_keyboard(_anomaly([{"who": None, "addr": ADDR, "usd": 1}]))
    assert kb is not None
    button = kb.inline_keyboard[0][0]
    assert button.callback_data == f"{TRACK_PREFIX}{ADDR}"
    assert len(button.callback_data.encode()) <= 64   # Telegram hard limit


def test_no_keyboard_when_nothing_trackable():
    # all contributors labeled → no button
    a = _anomaly([{"who": "Binance", "addr": "0x28c6", "usd": 1}])
    assert build_track_keyboard(a) is None
    # smart-money alert (no contributors) → no button
    sm = Alert(kind=AlertKind.SMART_MONEY, score=85, headline="h", detail="d",
               address="0xabc", extra={"entity_type": "fund"})
    assert build_track_keyboard(sm) is None
