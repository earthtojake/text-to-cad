"""The findings shape every CAM check writes, and the context a check reads.

A finding is a dict in the KiCad/FEA shape, so an agent reads CAM, FEA and board findings alike::

    {"check": "reach", "severity": "error" | "warning" | "info", "type": "reach_flutes",
     "summary": "Tool too long for this pocket: ...", "description": "...", "items": [{...}, ...]}

``check`` is the check's registry name (spec section 9); ``type`` the specific kind within it. ``items`` locate it:
each item may carry ``setup`` (id), ``operation`` (the global operation index the viewer's rows use), ``at`` (a
point in part mm) and numbers. :func:`by_severity` sorts errors first.

:class:`CheckContext` is what every check reads: the job, the part, the stock and its simulator's reports, and per
setup (:class:`SetupPlan`) its WCS, heights, toolpath (WCS) and part sections; per operation (:class:`OpPlan`) its
spec, tool, feeds, plan facts (``meta``) and times. A check is ``run(ctx) -> list[finding]``. Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["CheckContext", "FINDING_TYPES", "OpPlan", "SetupPlan", "assumed_lengths", "by_severity", "finding", "xyz"]

_SEVERITY = {"error": 0, "warning": 1, "info": 2}

#: Every finding a plan can carry, by ``check``: the closed set of its ``type`` (law 9; the skill's checks.md names
#: each). A finding of a check or type not listed here is a bug in cadgen, refused where it is made. The plan error
#: kinds are :data:`~cadgen._internal.cam.job_errors.PLAN_ERROR_KINDS`.
FINDING_TYPES: dict[str, tuple[str, ...]] = {
    "job": ("job", "internal_error"),
    "plan": ("empty_operation", "too_deep", "unreachable", "tool_too_large", "tool_too_small", "gouge", "note"),
    "post": ("no_post_support",),
    "checks": ("setup_not_simulated",),
    "gouge": ("gouge_2d", "gouge_3d", "gouge_turning", "gouge_multiaxis", "swarf_skipped", "not_judged"),
    "holder_collision": ("shank_part", "holder_part", "shank_stock", "holder_stock", "holder_multiaxis",
                         "not_judged"),
    "reach": ("reach_flutes", "reach_holder", "not_judged"),
    "rapid_into_stock": ("rapid_into_stock",),
    "travel": ("travel", "rotary_travel"),
    "corner_radius": ("corner_radius",),
    "material_left": ("material_left", "not_judged"),
    "fixture": ("fixture", "assumed_fixture"),
    "limits": ("limits",),
    "machine": ("machine_axes",),
    "empty_operation": ("empty_operation",),
    "through_stock_bottom": ("through_stock_bottom",),
    "long_stickout": ("long_stickout",),
    "full_slot": ("full_slot",),
    "prepared_hole": ("assumes_prepared_hole",),
    "uncut_feature": ("uncut_feature",),
    "thin_wall": ("thin_wall",),
    "unused_tool": ("unused_tool",),
    "drill": ("hole_size", "hole_floor", "tap_thread", "no_hole_in_model"),
}


def assumed_lengths(tool, keys) -> list[str]:
    """The lengths among ``keys`` the job left to the catalogue (``Tool.assumed``). A finding that stands on one is a
    ``not_judged`` warning, never an error built on a guess."""
    return [key for key in keys if key in tool.assumed]


def finding(check: str, severity: str, kind: str, summary: str, description: str = "", items=()) -> dict:
    if severity not in _SEVERITY:
        raise ValueError(f"severity {severity!r} is not error, warning or info")
    if kind not in FINDING_TYPES.get(check, ()):
        raise ValueError(f"finding type {kind!r} of check {check!r} is not in FINDING_TYPES")
    return {"check": check, "severity": severity, "type": kind, "summary": summary, "description": description,
            "items": list(items)}


def by_severity(found) -> list[dict]:
    """Errors first, then warnings, then notes; stable within each."""
    return sorted(found, key=lambda item: _SEVERITY[item["severity"]])


def xyz(point, digits: int = 3) -> list[float]:
    return [round(float(c), digits) + 0.0 for c in point]


@dataclass
class OpPlan:
    """One planned operation, as the checks, the results and the GLB read it."""

    index: int                      # global, in program order across setups
    setup: str
    spec: Any                       # job.OpSpec
    operation: Any                  # operations.base.Operation
    tool: Any                       # tools.Tool | None
    feeds: Any                      # feeds.Feeds | None
    params: Any = None
    meta: dict = field(default_factory=dict)
    summary: str = ""
    time_s: float = 0.0
    t0: float = 0.0                 # program time, s, across setups
    t1: float = 0.0
    #: Its moves in its setup's toolpath: ``[start, end)``.
    start: int = 0
    end: int = 0


@dataclass
class SetupPlan:
    setup: Any                      # job.Setup
    wcs: Any                        # wcs.WCS
    heights: Any                    # linking.Heights
    toolpath: Any = None            # ir.Toolpath, WCS
    sections: Any = None            # geom2d.Sections of the part in this WCS
    t0: float = 0.0
    time_s: float = 0.0
    #: Each vise or plate with a size the job did not state: ``{"fixture", "type", "assumed": {key: value}}``
    #: (``workholding.holding_boxes``); the ``fixture`` check says them.
    fixture_assumed: list = field(default_factory=list)


@dataclass
class CheckContext:
    job: Any
    part: Any
    stock: Any                      # stock.StockGeometry
    sim: Any                        # the StockSim after every setup
    sim_reports: dict               # setup id -> stock.SimReport
    setups: list                    # [SetupPlan]
    ops: list                       # [OpPlan]
    tolerance_mm: float
    logger: Any = None

    def setup_plan(self, setup_id: str) -> SetupPlan:
        return next(plan for plan in self.setups if plan.setup.id == setup_id)

    def ops_in(self, setup_id: str) -> list:
        return [op for op in self.ops if op.setup == setup_id]
