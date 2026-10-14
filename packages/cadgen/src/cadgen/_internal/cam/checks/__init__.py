"""Every check a CAM plan runs (spec section 9), by name: built, or registered and skipped until its module lands.

The registry pre-lists every check with its level and a lazy ``"module:function"``; :func:`run_checks` imports each
one whose module this cadgen has and calls ``run(ctx: CheckContext) -> list[finding]`` (the dict shape in
:mod:`.base`). A check whose module is absent is skipped and named in the result's ``skipped`` list, never an error:
adding a check is adding its module. Error-level findings make the verdict "N to fix"; warnings do not.

A check can also not reach a setup: the ones judged on the simulated stock (:data:`ON_STOCK`) are not evaluated for
a setup the simulator skipped (a side setup on a heightfield), and a check that could not read what it judges says
so with a ``not_judged`` finding. Each is a ``skipped`` entry naming the check, the setup (and operation) and why,
and a setup the simulator skipped gets one warning finding naming the checks it went without: never a silent pass.
A check none of whose setups it could judge is not listed as run.

Stdlib only at import.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from cadgen._internal.cam.checks.base import by_severity

__all__ = ["CHECK_NAMES", "Entry", "REGISTRY", "run_checks"]

_PACKAGE = "cadgen._internal.cam.checks"


@dataclass(frozen=True)
class Entry:
    name: str
    level: str          # the level its findings usually carry: "error" | "warning" | "info"
    target: str         # "cadgen._internal.cam.checks.reach:run"
    plain: str


def _entry(name: str, level: str, plain: str) -> Entry:
    return Entry(name, level, f"{_PACKAGE}.{name}:run", plain)


REGISTRY: tuple[Entry, ...] = (
    _entry("gouge", "error", "a feed move cuts into the part beyond tolerance"),
    _entry("holder_collision", "error", "the holder or shank above the flutes touches stock or part"),
    _entry("reach", "error", "the cut is deeper than the flutes or the stickout"),
    _entry("rapid_into_stock", "error", "a rapid move passes through uncut stock"),
    _entry("travel", "error", "the path leaves the machine's travel"),
    _entry("corner_radius", "warning", "an inside corner is tighter than the tool's radius"),
    _entry("material_left", "warning", "stock is left above the part after every operation"),
    _entry("fixture", "error", "a move enters a fixture keep-out"),
    _entry("limits", "warning", "a feed or speed was clamped by the machine"),
    _entry("machine", "error", "an operation needs an axis the machine does not have"),
    _entry("empty_operation", "error", "an operation cuts nothing (a warning when it names no faces or region)"),
    _entry("through_stock_bottom", "warning", "a cut goes below the stock's bottom"),
    _entry("long_stickout", "warning", "an end mill sticks out more than four times its diameter"),
    _entry("full_slot", "warning", "an operation cuts at the tool's full width for more than five diameters"),
    _entry("prepared_hole", "warning", "a tap or thread mill works a hole no earlier operation made"),
    _entry("uncut_feature", "warning", "a hole or pocket a setup reaches that no operation cuts"),
    _entry("thin_wall", "warning", "a hole or pocket the job cuts leaves under 1 mm of wall to the outside"),
    _entry("unused_tool", "info", "a tool the job lists that no operation runs"),
)
CHECK_NAMES = tuple(entry.name for entry in REGISTRY)


#: Checks judged on the simulated stock, and what a setup the simulator skipped goes without. ``whole``: the check
#: judges nothing else, so it did not run at all when no setup was simulated.
ON_STOCK = {
    "rapid_into_stock": ("rapids are not checked against the uncut stock", True),
    "holder_collision": ("the holder and shank are checked against the part only, not the stock", False),
    "material_left": ("material left after its cuts is not judged", True),
}


def run_checks(ctx) -> tuple[list[dict], list[str], list[dict]]:
    """``(findings errors first, checks run, checks skipped)``: a skipped entry is ``{"check", "why"}``, with
    ``"setup"`` (and ``"operation"``) when the check did not reach that setup or operation."""
    from cadgen._internal.cam.checks.base import finding

    found: list[dict] = []
    ran: list[str] = []
    skipped: list[dict] = []
    # Every registered check is built: one that cannot be imported fails the plan (nothing is written), never a
    # check quietly left out of a verdict that says "Ready to cut".
    for entry in REGISTRY:
        module, function = entry.target.split(":")
        found.extend(getattr(importlib.import_module(module), function)(ctx))
        ran.append(entry.name)
    # Setups the simulator skipped: the stock checks did not judge them.
    reports = getattr(ctx, "sim_reports", {}) or {}
    unsimulated = [(setup_id, report.skipped) for setup_id, report in reports.items() if report.skipped]
    for setup_id, why in unsimulated:
        names = [name for name in ON_STOCK if name in ran]
        if not names:
            continue
        skipped += [{"check": name, "setup": setup_id, "why": f"{why}: {ON_STOCK[name][0]}"} for name in names]
        found.append(finding(
            "checks", "warning", "setup_not_simulated",
            f"Setup '{setup_id}' is not simulated, so {', '.join(names)} did not judge it",
            f"{why}. Not judged there: {'; '.join(ON_STOCK[name][0] for name in names)}. Check that setup by hand: "
            "air-cut it or run it single-block first",
            [{"setup": setup_id, "checks": names}]))
    if reports and len(unsimulated) == len(reports):
        ran = [name for name in ran if not (name in ON_STOCK and ON_STOCK[name][1])]
        # ... and what it found on stock nothing cut is not a finding (material left: the whole uncut block).
        found = [item for item in found if not (item.get("check") in ON_STOCK and ON_STOCK[item["check"]][1])]
    # A cut below the stock that already runs into a fixture box is that box's finding, not a second one.
    into_fixture = {(where.get("setup"), where.get("operation")) for item in found if item["check"] == "fixture"
                    for where in item["items"]}
    found = [item for item in found if not (item["check"] == "through_stock_bottom" and all(
        (where.get("setup"), where.get("operation")) in into_fixture for where in item["items"]))]
    # A check that could not read what it judges said so (``not_judged``): a skipped entry too.
    for item in found:
        if item.get("type") == "not_judged":
            for where in item["items"]:
                skipped.append({"check": item["check"], **{k: where[k] for k in ("setup", "operation") if k in where},
                                "why": item["summary"]})
    return by_severity(found), ran, skipped
