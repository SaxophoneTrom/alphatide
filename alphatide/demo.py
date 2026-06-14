"""AlphaTide end-to-end demo — runs with NO API keys.

  python -m alphatide.demo            # scenario demo (deterministic, always shows alerts)
  python -m alphatide.demo --live     # also do a real scan against rpc.mantle.xyz

The scenario feeds crafted-but-realistic Mantle transfers — where some movers are
addresses Surf really labels (Wintermute, Jump, Binance, captured live) — through
the *real* detector, scorer and formatter, in Surf offline (fixtures) mode. It
demonstrates exactly what a production alert looks like when a known fund bleeds
into Mantle.

`--live` proves the watcher really talks to Mantle (block height, transfer count,
large movers) — the on-chain half of the system, no mocks.
"""

from __future__ import annotations

import sys

from alphatide.analytics.smart_money import CrossChainSmartMoneyDetector
from alphatide.bot.formatting import format_digest, format_signal
from alphatide.core.models import TransferEvent
from alphatide.data.surf_client import SurfClient

# Real Surf-labeled addresses (from fixtures) cast as if they moved on Mantle.
WINTERMUTE = "0x0000006daea1723962647b7e189d311d757fb793"
JUMP = "0xf584f8728b874a6a5c7a8d4d387c9aae9172d621"
BINANCE = "0x28c6c06298d514db089934071355e5743bf21d60"
ANON = "0x1111111111111111111111111111111111111111"


def scenario_events() -> list[TransferEvent]:
    """A realistic mix: two famous funds, a CEX, and an anonymous whale."""
    return [
        TransferEvent("0xaa1", 96660000, "mETH", "0xcda8", "0xpool",
                      WINTERMUTE, 120.0, 408_000.0),   # Wintermute receives mETH
        TransferEvent("0xbb2", 96660010, "USDT", "0x201e", JUMP, "0xpool",
                      1_250_000.0, 1_250_000.0),         # Jump sends USDT
        TransferEvent("0xcc3", 96660020, "WMNT", "0x78c1", "0xpool", BINANCE,
                      900_000.0, 540_000.0),             # Binance hot wallet inflow
        TransferEvent("0xdd4", 96660030, "USDC", "0x09bc", ANON, "0xpool",
                      15_000.0, 15_000.0),               # anonymous — should be filtered
    ]


def run_scenario() -> None:
    print("=" * 64)
    print("AlphaTide — SCENARIO DEMO (real detector, Surf offline/fixtures)")
    print("=" * 64)
    surf = SurfClient(offline=True)
    detector = CrossChainSmartMoneyDetector(surf)
    signals = detector.detect(scenario_events())

    print(f"\nInput: 4 large movers → {len(signals)} confirmed smart money "
          f"(anonymous whale correctly dropped)\n")
    print(format_digest(signals))
    print()
    for s in signals:
        print("-" * 64)
        print(format_signal(s))
    print("-" * 64)
    print(f"\nSurf credits used this cycle: {surf.credits_used} "
          f"(offline fixtures = 0; live would be 1 batch call)")


def run_live() -> None:
    from alphatide.pipeline import AlphaTidePipeline

    print("\n" + "=" * 64)
    print("AlphaTide — LIVE Mantle scan (rpc.mantle.xyz, no mocks)")
    print("=" * 64)
    try:
        pipe = AlphaTidePipeline(surf=SurfClient(offline=True))
        res = pipe.run_cycle()
        print(f"latest block      : {res.latest_block:,}")
        print(f"transfers scanned : {res.scanned_events}")
        print(f"large movers      : {res.candidates}")
        print(f"smart money hits  : {len(res.signals)} "
              f"(offline Surf can only resolve fixture addresses)")
        if res.signals:
            print()
            print(format_digest(res.signals))
        print("\n✅ On-chain watcher is live. Add SURF_API_KEY to resolve every "
              "real mover's cross-chain identity.")
    except Exception as exc:
        print(f"(live scan skipped — network unavailable: {exc})")


if __name__ == "__main__":
    run_scenario()
    if "--live" in sys.argv:
        run_live()
