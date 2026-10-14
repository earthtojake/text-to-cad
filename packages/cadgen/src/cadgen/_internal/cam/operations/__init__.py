"""Every operation ``cadgen cam`` knows, by name: built, or registered as planned.

The registry is written once, here, in the order the skill and the viewer list them (spec section 4): 2.5D
milling, 3D milling, multi-axis, turning, cutting. Each entry names its module (``operations/<op>.py``) and class,
its plain viewer word, its family, the machine kinds it runs on and whether it is ``full`` or ``lite``. An entry
whose module is not in this cadgen makes :func:`get_operation` say so in one sentence ("'contour' is planned but not
in this cadgen yet"), never an ImportError: adding an operation is adding its module, nothing else.

The class (an :class:`~cadgen._internal.cam.operations.base.Operation`) repeats ``name``, ``plain``, ``family``,
``machines`` and ``status``; a test keeps the two in step. Stdlib only: the modules import lazily.
"""

from __future__ import annotations

import difflib
import importlib
import importlib.util
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cadgen._internal.cam.job_errors import CamJobError, shown

if TYPE_CHECKING:
    from cadgen._internal.cam.operations.base import Operation

__all__ = ["Entry", "OPERATION_NAMES", "REGISTRY", "available", "built", "get_operation", "MILLS"]

_PACKAGE = "cadgen._internal.cam.operations"

#: The machine kinds that mill (a 3-axis job runs on any of them; a 3+2 setup needs mill4 or mill5).
MILLS = ("mill", "mill4", "mill5", "router")


@dataclass(frozen=True)
class Entry:
    name: str
    module: str          # "cadgen._internal.cam.operations.pocket"
    cls: str             # "PocketOp"
    plain: str           # "Pocket"
    family: str          # "2.5D milling"
    machines: tuple[str, ...]
    status: str          # "full" | "lite"


def _entry(name: str, cls: str, plain: str, family: str, machines: tuple[str, ...], status: str = "full") -> Entry:
    return Entry(name, f"{_PACKAGE}.{name}", cls, plain, family, machines, status)


_25D, _3D, _MULTI, _TURN, _CUT = "2.5D milling", "3D milling", "Multi-axis", "Turning", "Cutting"

REGISTRY: dict[str, Entry] = {entry.name: entry for entry in (
    _entry("face", "FaceOp", "Face", _25D, MILLS),
    _entry("contour", "ContourOp", "Profile", _25D, MILLS),
    _entry("pocket", "PocketOp", "Pocket", _25D, MILLS),
    _entry("adaptive", "AdaptiveOp", "Adaptive clear", _25D, MILLS, "lite"),
    _entry("slot", "SlotOp", "Slot", _25D, MILLS),
    _entry("drill", "DrillOp", "Drill", _25D, MILLS),
    _entry("thread_mill", "ThreadMillOp", "Thread mill", _25D, MILLS),
    _entry("chamfer", "ChamferOp", "Chamfer", _25D, MILLS),
    _entry("engrave", "EngraveOp", "Engrave", _25D, MILLS),
    _entry("vcarve", "VCarveOp", "V-carve", _25D, MILLS, "lite"),
    _entry("helix_bore", "HelixBoreOp", "Helix bore", _25D, MILLS),
    _entry("circular", "CircularOp", "Circular", _25D, MILLS),
    _entry("trace", "TraceOp", "Trace", _25D, MILLS),
    _entry("rough", "RoughOp", "3D rough", _3D, MILLS),
    _entry("adaptive_3d", "Adaptive3dOp", "3D adaptive clear", _3D, MILLS, "lite"),
    _entry("parallel", "ParallelOp", "Parallel finish", _3D, MILLS),
    _entry("waterline", "WaterlineOp", "Waterline", _3D, MILLS),
    _entry("scallop", "ScallopOp", "Scallop", _3D, MILLS, "lite"),
    _entry("pencil", "PencilOp", "Pencil", _3D, MILLS, "lite"),
    _entry("rest", "RestOp", "Rest machining", _3D, MILLS),
    _entry("rotary", "RotaryOp", "4th-axis wrap", _MULTI, ("mill4", "mill5"), "lite"),
    _entry("swarf", "SwarfOp", "Swarf", _MULTI, ("mill5",), "lite"),
    _entry("surface_normal", "SurfaceNormalOp", "5-axis finish", _MULTI, ("mill5",), "lite"),
    _entry("turn_face", "TurnFaceOp", "Face", _TURN, ("lathe",)),
    _entry("turn_rough", "TurnRoughOp", "Rough turn", _TURN, ("lathe",)),
    _entry("turn_finish", "TurnFinishOp", "Finish turn", _TURN, ("lathe",)),
    _entry("turn_groove", "TurnGrooveOp", "Groove", _TURN, ("lathe",)),
    _entry("turn_thread", "TurnThreadOp", "Thread", _TURN, ("lathe",)),
    _entry("turn_drill", "TurnDrillOp", "Centre drill", _TURN, ("lathe",)),
    _entry("turn_partoff", "TurnPartoffOp", "Part off", _TURN, ("lathe",)),
    _entry("cut", "CutOp", "Cut out", _CUT, ("laser", "plasma", "waterjet", "router")),
    _entry("wire_edm", "WireEdmOp", "Wire cut", _CUT, ("wire_edm",), "lite"),
)}

OPERATION_NAMES = tuple(REGISTRY)


def available(name: str) -> bool:
    """Whether this cadgen has the operation's module."""
    entry = REGISTRY.get(name)
    return entry is not None and importlib.util.find_spec(entry.module) is not None


def built() -> tuple[str, ...]:
    """The operations this cadgen can plan, in registry order."""
    return tuple(name for name in OPERATION_NAMES if available(name))


def entry_for(name: object, where: str = "op") -> Entry:
    """The registry entry for ``name``, or the teaching error naming the operations."""
    if not isinstance(name, str) or name not in REGISTRY:
        close = difflib.get_close_matches(name, OPERATION_NAMES, n=1) if isinstance(name, str) else []
        hint = f" (did you mean '{close[0]}'?)" if close else ""
        raise CamJobError(f"{where}: unknown operation {shown(name)}{hint}; the operations are {', '.join(OPERATION_NAMES)}")
    return REGISTRY[name]


def get_operation(name: str, where: str = "op") -> "Operation":
    """An instance of the operation's class. A registered name whose module this cadgen does not have is refused in a
    sentence that names what is built."""
    entry = entry_for(name, where)
    if not available(name):
        raise CamJobError(f"{where}: '{name}' is planned but not in this cadgen yet; the operations built are "
                          f"{', '.join(built()) or 'none'}")
    module = importlib.import_module(entry.module)
    return getattr(module, entry.cls)()
