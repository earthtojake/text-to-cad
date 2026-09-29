"""The engine's systems, in assembly (and explode) order.

Each system is one model `src/<name>.py` wrapping `lib/<name>.py:build()`.
A system joins the assembly as soon as its `lib/<name>.py` exists, so builders
can land one at a time; the animation addresses parts by LABEL, never by
occurrence id, so ids shifting as systems land breaks nothing.
"""

from __future__ import annotations

from pathlib import Path

SYSTEMS = [
    ("crankcase", "split power-section crankcase, cylinder pads, studs, main-bearing housings"),
    ("crankshaft", "two-piece single-throw crankshaft, counterweights, main bearings, drive gears"),
    ("rods", "master rod + flange, 8 knuckle pins + retainers, crankpin bearing, 8 articulating rods"),
    ("pistons", "9 pistons, 54 rings, 9 wrist pins + plugs"),
    ("barrels", "9 finned steel cylinder barrels + hold-down nuts"),
    ("heads", "9 aluminium heads: deep fins, rocker boxes, covers, guides, seats, 18 spark plugs"),
    ("valvetrain", "18 valves, springs, retainers, keepers, 18 rockers + shafts"),
    ("cam", "cam ring, cam idler, 18 tappets + rollers"),
    ("pushrods", "18 pushrods, 18 pushrod tubes, packing nuts, connectors"),
    ("nose", "nose case, tappet guides, thrust-bearing housing, governor pad"),
    ("reduction", "planetary reduction: bell gear, fixed sun, 6 planets, carrier, propeller shaft, thrust bearing"),
    ("propeller", "hub, three blades, spinner, retention hardware"),
    ("blower", "blower section, diffuser, impeller, impeller drive gears"),
    ("intake", "9 intake pipes, couplings, carburettor"),
    ("accessory", "accessory case, 2 magnetos, starter, generator, fuel + oil pumps, oil sump"),
    ("ignition", "harness ring, 18 leads, plug elbows, magneto feeds"),
    ("exhaust", "9 stacks, collector ring, outlet, clamps"),
    ("mount", "engine mount ring, bosses, bushings, bolts"),
]

NAMES = [n for n, _ in SYSTEMS]
LIB = Path(__file__).resolve().parent


def ready() -> list[str]:
    return [n for n in NAMES if (LIB / f"{n}.py").exists()]
