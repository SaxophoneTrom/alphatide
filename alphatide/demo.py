"""AlphaTide end-to-end demo — runs with NO API keys.

  python -m alphatide.demo            # scenario demo (all 4 detectors, deterministic)
  python -m alphatide.demo --live     # also do a real scan against rpc.mantle.xyz

The scenario feeds crafted-but-realistic Mantle transfers — where movers are
addresses Surf really labels (Wintermute, Jump, Binance, captured live) — through
the *real* detector suite in Surf offline (fixtures) mode. It shows exactly what
production alerts look like across all four detectors:

  🧠 smart money (7-A)   🧲 convergence (B)   🌉 inflow (C)   📈 anomaly (I)

`--live` proves the watcher really talks to Mantle (block height, transfers,
large movers) — the on-chain half of the system, no mocks.
"""

from __future__ import annotations

import sys

from alphatide.bot.formatting import format_alert, format_digest
from alphatide.core.models import DetectionContext, TransferEvent
from alphatide.data.mantle_client import large_movers
from alphatide.data.surf_client import SurfClient
from alphatide.analytics.anomaly import VolumeAnomalyDetector
from alphatide.analytics.convergence import ConvergenceDetector
from alphatide.analytics.inflow import InflowDetector
from alphatide.analytics.smart_money import CrossChainSmartMoneyDetector

WINTERMUTE = "0x0000006daea1723962647b7e189d311d757fb793"
JUMP = "0xf584f8728b874a6a5c7a8d4d387c9aae9172d621"
ALAMEDA = "0x83a127952d266a6ea306c40ac62a4a70668fe3bd"
BINANCE = "0x28c6c06298d514db089934071355e5743bf21d60"
ANON = "0x1111111111111111111111111111111111111111"


def scenario_events() -> list[TransferEvent]:
    # THREE funds (Wintermute, Jump, Alameda) accumulate mETH → strong convergence
    # (B, high conviction). Binance (cex) pushes WMNT into a fresh wallet → inflow (C).
    return [
        TransferEvent("0xaa1", 96660000, "mETH", "0xcda8", "0xpool",
                      WINTERMUTE, 120.0, 408_000.0),
        TransferEvent("0xbb2", 96660010, "mETH", "0xcda8", "0xpool",
                      JUMP, 95.0, 323_000.0),
        TransferEvent("0xee5", 96660015, "mETH", "0xcda8", "0xpool",
                      ALAMEDA, 85.0, 290_000.0),
        TransferEvent("0xcc3", 96660020, "WMNT", "0x78c1", BINANCE,
                      "0xfreshwallet000000000000000000000000beef",
                      900_000.0, 540_000.0),
        TransferEvent("0xdd4", 96660030, "USDC", "0x09bc", ANON, "0xpool",
                      15_000.0, 15_000.0),  # anonymous — dropped by 7-A
    ]


def build_demo_alerts(surf=None):
    """Run the canonical demo scenario through the REAL detector suite.

    Labels come from offline fixtures (free, deterministic); the caller may then
    attach a live Surf AI note to the top high-conviction alert. Shared by the
    CLI demo and the bot's /demo command.
    """
    from alphatide.analytics.action_read import attach_read

    surf = surf or SurfClient(offline=True)
    events = scenario_events()
    movers = large_movers(events, 10_000)
    labels = surf.label_addresses(list(movers))
    history = {
        "mETH": [42_000, 55_000, 38_000, 61_000, 47_000, 52_000, 44_000, 58_000],
        "WMNT": [70_000, 55_000, 81_000, 62_000, 49_000, 73_000, 58_000, 66_000],
    }
    ctx = DetectionContext(events, movers, labels, 10_000, history)
    detectors = [
        CrossChainSmartMoneyDetector(surf),
        ConvergenceDetector(),
        InflowDetector(),
        VolumeAnomalyDetector(),
    ]
    alerts = []
    for d in detectors:
        alerts += d.detect_ctx(ctx)
    for a in alerts:
        attach_read(a)
    alerts.sort(key=lambda a: a.score, reverse=True)
    return alerts


def run_scenario() -> None:
    print("=" * 64)
    print("AlphaTide — SCENARIO DEMO (full detector suite, Surf offline/fixtures)")
    print("=" * 64)
    alerts = build_demo_alerts()

    print(f"\nInput: 5 large movers → {len(alerts)} alerts across "
          f"{len({a.kind for a in alerts})} detector types\n")
    print(format_digest(alerts))
    print()
    for a in alerts:
        print("-" * 64)
        print(format_alert(a))
    print("-" * 64)
    print("\nSurf credits: offline fixtures = 0; live would be 1 shared batch "
          "for ALL detectors (+2cr for the AI read on the convergence).")


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
        print(f"alerts            : {len(res.alerts)} "
              f"(offline Surf only resolves fixture addresses)")
        if res.alerts:
            print()
            print(format_digest(res.alerts))
        print("\n✅ On-chain watcher is live. Add SURF_API_KEY to resolve every "
              "real mover's cross-chain identity across all four detectors.")
    except Exception as exc:
        print(f"(live scan skipped — network unavailable: {exc})")


if __name__ == "__main__":
    run_scenario()
    if "--live" in sys.argv:
        run_live()
