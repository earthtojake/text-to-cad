"""Parse and validate a CAM job: a closed vocabulary (law 9), frozen dataclasses, one-sentence teaching errors.

The job (spec section 3) is JSON: a file path, inline JSON text, or a dict from a library caller. :func:`parse_job`
returns a :class:`Job`::

    Job(machine: Machine, material: Material, stock: StockSpec, tools: tuple[Tool, ...],
        setups: tuple[Setup, ...], tolerance_mm: float, coolant: str, name: str)

Each :class:`Setup` carries its operations as :class:`OpSpec`: the keys every operation shares, parsed here, and the
operation's own keys left in ``extra`` for the operation's ``parse`` (``operations/base.py``) to validate against
its own closed set. What needs the part (that a face exists, that it is flat) is checked later, against the part.

Every refusal is a :class:`~cadgen._internal.cam.job_errors.CamJobError` naming the path into the job
(``setups[0].operations[2].tool``), what is wrong and the allowed set. The machine may name its ``model``
(``machines.py``): the model's published numbers stand in for the keys the job leaves out, and the job's own keys win.
What neither states takes the kind's generic value (``machines.GENERIC``: a post, a spindle limit, the cycle-time
rates, the controller's own tapping cycle, not homed), and every such value is listed in :attr:`Job.assumed` (``{"key", "value",
"why"}``), never taken silently; so are the tool lengths a used tool leaves to the catalogue defaults. ``tools`` is a
list, a tool library file (``"tools": "my-tools.json"``), or a list mixing tools and ``{"library": path, "only":
[ids]}``: a library's tools are kept when an operation uses them or ``only`` picks them. The stock must be one the
machine starts from (:data:`STOCK_FOR_KIND`). A dict job is copied through JSON, so it reads exactly as the same job
in a file would (tuples become lists, NaN is refused) and nothing parsed shares the caller's lists. Stdlib only.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from cadgen._internal.cam import machines
from cadgen._internal.cam import posts as post_registry
from cadgen._internal.cam.job_errors import CamJobError, check_keys, choice, is_number, number_list, read_number, shown
from cadgen._internal.cam.operations import available as operation_built
from cadgen._internal.cam.operations import entry_for as operation_entry
from cadgen._internal.cam.operations import get_operation
from cadgen._internal.cam.operations.drill import DEFAULT_CYCLE
from cadgen._internal.cam.tools import Tool, parse_tool

__all__ = ["CamJobError", "Fixture", "Holding", "Job", "Machine", "Material", "OpSpec", "Setup", "StockSpec",
           "load_job", "parse_job", "FIXTURE_KEYS", "MACHINE_KINDS", "ORIENTATIONS", "ORIGINS", "COOLANTS"]

MACHINE_KINDS = ("mill", "mill4", "mill5", "lathe", "laser", "plasma", "waterjet", "router", "wire_edm")
#: mill5 kinematics: an A+C trunnion table, or a B+C head over a C table.
KINEMATICS = ("ac_trunnion", "bc_head")
ORIENTATIONS = ("+Z", "-Z", "+X", "-X", "+Y", "-Y")
#: The machines a setup may be turned onto a face of the part (``"orientation": "#o1.f4"``): the tool looks down the
#: face's outward normal (``wcs.with_face_orientations``).
FACE_ORIENTATION_KINDS = ("mill", "mill4", "mill5", "router")
#: A setup's fixture: a keep-out box in part coordinates (no ``type``, or ``"box"``), or a fixture modelled around the
#: stock in the setup's frame and compiled to boxes where the stock and the WCS are known (``workholding.py``). The
#: keys each takes; a size it leaves out is a default, said in an ``assumed_fixture`` finding.
FIXTURE_KEYS = {
    "box": ("type", "name", "min_mm", "max_mm"),
    "vise": ("type", "name", "jaws_along", "jaw_height_mm", "grip_mm", "parallels_mm", "jaw_width_mm",
             "jaw_thickness_mm", "parallel_width_mm", "floor_thickness_mm"),
    "plate": ("type", "name", "thickness_mm", "border_mm"),
}
#: The machines a vise or a plate holds work on.
HOLDING_KINDS = ("mill", "mill4", "mill5", "router")
#: How closely a vise's stated ``grip_mm`` must agree with ``jaw_height_mm - parallels_mm``, mm.
VISE_AGREE_MM = 0.01
#: Where a setup's WCS zero sits: the stock's or the part's box, at its top, middle or bottom, at the centre of that
#: face or its corner (min X, min Y, in the setup's WCS); or a part point ``{"xyz": [x, y, z]}`` (``[x, y, z]``).
ORIGINS = ("stock-top-center", "stock-top-corner", "stock-center", "stock-bottom-center", "stock-bottom-corner",
           "part-top-center", "part-top-corner", "part-center", "part-bottom-center", "part-bottom-corner")
COOLANTS = ("off", "flood", "mist", "air")
STOCK_KINDS = ("box", "cylinder", "sheet", "from_step")
#: The stock each machine kind starts from, and how a refusal says it: a lathe turns bar, a beam or a jet cuts
#: through a sheet (its thickness is the cut's), a wire EDM through a plate or block.
STOCK_FOR_KIND = {"mill": STOCK_KINDS, "mill4": STOCK_KINDS, "mill5": STOCK_KINDS, "router": STOCK_KINDS,
                  "lathe": ("cylinder",), "laser": ("sheet",), "plasma": ("sheet",), "waterjet": ("sheet",),
                  "wire_edm": ("sheet", "box")}
_STOCK_WORDS = {"lathe": "a lathe turns bar stock", "laser": "a laser cuts from a sheet",
                "plasma": "a plasma cuts from a sheet", "waterjet": "a waterjet cuts from a sheet",
                "wire_edm": "a wire EDM cuts through a sheet or a block"}
#: The largest stock (and step) a job names, in mm: ten metres, past any machine bed; beyond it a number is a units
#: slip, and the stock grid and the paths over it stop fitting in memory.
MAX_STOCK_MM = 10_000.0
WORK_OFFSETS = ("G54", "G55", "G56", "G57", "G58", "G59")

JOB_KEYS = ("name", "machine", "material", "stock", "tools", "setups", "tolerance_mm", "coolant")
MACHINE_KEYS = ("model", "kind", "post", "name", "travel_mm", "min_rpm", "max_rpm", "max_feed_mm_min", "rapid_mm_min",
                "tool_change_s", "rigid_tap", "kinematics", "rotary_limits_deg", "diameter_mode", "power_w",
                "laser_source", "amps", "abrasive", "spindle_spinup_s", "assumed")
#: The machine keys a job may mark as its own guesses (``"assumed": ["kind"]``): listed in the plan's ``assumed``.
GUESSABLE_KEYS = tuple(key for key in MACHINE_KEYS if key not in ("model", "assumed"))
#: How many travel numbers each kind takes: a lathe [x, z], a mill [x, y, z], a cutting machine [x, y] or [x, y, z].
_TRAVEL = {"lathe": ((2,), "[x, z]"), "mill": ((3,), "[x, y, z]"), "mill4": ((3,), "[x, y, z]"),
           "mill5": ((3,), "[x, y, z]"), "router": ((3,), "[x, y, z]")}
#: The cutting machines' own keys and the kind each belongs to (their cutting speeds scale with them: feeds.cut_feeds).
CUTTING_MACHINE_KEYS = {"power_w": ("laser",), "laser_source": ("laser",), "amps": ("plasma",),
                        "abrasive": ("waterjet",)}
LASER_SOURCES = ("fiber", "co2", "diode")
MATERIAL_KEYS = ("name", "surface_m_min", "sfm", "chipload_mm", "drill_mm_per_rev", "stepdown_fraction")
SETUP_KEYS = ("id", "name", "orientation", "origin", "fixture", "operations", "wcs", "clearance_mm", "retract_mm")
#: Keys every operation takes; an operation adds its own (its reference page), validated by its ``parse``.
#: ``clearance_mm``/``retract_mm`` override the setup's for this operation; ``plunge_mm_min`` its plunge feed.
OP_COMMON_KEYS = ("op", "tool", "faces", "region", "feed", "speed", "plunge_mm_min", "stepdown_mm", "stepover",
                  "stepover_mm", "stock_to_leave_mm", "coolant", "name", "clearance_mm", "retract_mm")



@dataclass(frozen=True)
class Machine:
    kind: str
    post: str
    name: str = ""
    #: Axis travel in mm: [x, y, z] (a lathe: [x, z]); ``None`` when the job names none (no travel check).
    travel_mm: tuple[float, ...] | None = None
    max_rpm: float | None = None
    max_feed_mm_min: float | None = None
    rapid_mm_min: float = 5000.0
    tool_change_s: float = 10.0
    kinematics: str | None = None
    rotary_limits_deg: dict = field(default_factory=dict)
    #: The post's own machine keys as the job set them (``machine.cycles``, ...): ``posts/base.py`` Post.options.
    post_options: dict = field(default_factory=dict)
    #: A lathe's X words are diameters (true) or radii.
    diameter_mode: bool = True
    #: Cutting machines: a laser's power (W) and source (fiber, co2, diode), a plasma's current (A), whether a
    #: waterjet adds abrasive. ``None`` takes the cutting table's reference machine (feeds.cut_feeds).
    power_w: float | None = None
    laser_source: str | None = None
    amps: float | None = None
    abrasive: bool = True
    #: Seconds to wait after the spindle starts before cutting; ``None``: the post's own default (3 s on grbl, which
    #: does not wait for the spindle to reach speed; none on the controllers that do).
    spindle_spinup_s: float | None = None
    #: The catalog model the job names (``machines.MODELS`` id), or ``None``.
    model: str | None = None
    #: The slowest the spindle turns: a slower speed is raised to it (feeds.for_op).
    min_rpm: float | None = None
    #: Whether the controller taps rigidly; ``None``: not known, so a tap that does not say keeps the controller's own
    #: tapping cycle (operations/drill.py), and the plan lists that as assumed.
    rigid_tap: bool | None = None

    @property
    def axes(self) -> str:
        """The axes the machine has: ``XYZ``, ``XYZA``, ``XYZAC``/``XYZBC``, ``XZ`` (lathe), ``XY`` (cutting),
        ``XYUV`` (wire EDM)."""
        return {"mill": "XYZ", "router": "XYZ", "mill4": "XYZA", "lathe": "XZ", "laser": "XY", "plasma": "XY",
                "waterjet": "XY", "wire_edm": "XYUV"}.get(self.kind) or (
            "XYZBC" if self.kinematics == "bc_head" else "XYZAC")

    def as_dict(self) -> dict:
        out = {"kind": self.kind, "post": self.post, "axes": self.axes, "rapid_mm_min": self.rapid_mm_min,
               "tool_change_s": self.tool_change_s}
        for key in ("model", "name", "travel_mm", "min_rpm", "max_rpm", "max_feed_mm_min", "kinematics", "rigid_tap"):
            value = getattr(self, key)
            if value not in (None, ""):
                out[key] = list(value) if isinstance(value, tuple) else value
        # The model's tool changer (none, manual, atc) and its pockets, for the record.
        model = machines.MODELS.get(self.model) if self.model else None
        for key in ("tool_changer", "tool_capacity"):
            if model is not None and getattr(model, key) is not None:
                out[key] = getattr(model, key)
        if self.rotary_limits_deg:
            out["rotary_limits_deg"] = {k: list(v) for k, v in self.rotary_limits_deg.items()}
        out.update(self.post_options)
        if self.kind == "lathe":
            out["diameter_mode"] = self.diameter_mode
        for key in ("power_w", "laser_source", "amps", "spindle_spinup_s"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        if self.kind == "waterjet":
            out["abrasive"] = self.abrasive
        return out


@dataclass(frozen=True)
class Material:
    """A feeds-table material (``table`` true; ``name`` its canonical row, an alias resolved), its numbers the
    table's unless the job overrides one; or the job's own numbers (``table`` false)."""

    name: str
    plain: str
    table: bool
    surface_m_min: float | None = None
    #: One chip load (mm a tooth) for every tool, or ``((tool diameter mm, chip load), ...)``, smallest first.
    chipload_mm: float | tuple[tuple[float, float], ...] | None = None
    drill_mm_per_rev: float | None = None
    stepdown_fraction: float | None = None


@dataclass(frozen=True)
class StockSpec:
    kind: str
    #: Box/sheet: added on each side, ``(x-, x+, y-, y+, z-, z+)`` in mm. A box's z margin goes on top only unless
    #: six numbers are given. Cylinder: ``(radial, axial)``; one number is both. The radial margin goes all round
    #: (none with a stated ``diameter_mm``); the axial margin at each end (none with a stated ``length_mm``), except on
    #: a lathe, where the +axis end is ``face_stock_mm`` and the axial margin goes at the chuck end only.
    margin_mm: tuple[float, ...] = (0.0,) * 6
    size_mm: tuple[float, float, float] | None = None
    diameter_mm: float | None = None
    length_mm: float | None = None
    axis: str = "z"
    thickness_mm: float | None = None
    path: str | None = None
    #: A lathe's bar: how far it stands proud of the part's +axis end (the face to be faced off); with it the bar is
    #: centred on the part's own turning axis and runs ``length_mm`` back from there (the rest is held in the chuck).
    face_stock_mm: float | None = None

    def as_dict(self) -> dict:
        out = {"kind": self.kind}
        for key in ("margin_mm", "size_mm", "diameter_mm", "length_mm", "thickness_mm", "path", "face_stock_mm"):
            value = getattr(self, key)
            if value is not None:
                out[key] = list(value) if isinstance(value, tuple) else value
        if self.kind == "cylinder":
            out["axis"] = self.axis
        return out


@dataclass(frozen=True)
class Fixture:
    """A box keep-out in part coordinates (mm): nothing may move into it."""

    min_mm: tuple[float, float, float]
    max_mm: tuple[float, float, float]
    name: str = ""


@dataclass(frozen=True)
class Holding:
    """A vise or a plate as the job wrote it: ``stated`` holds the keys it gave (sizes in mm, a vise's ``jaws_along``
    ``"x"``/``"y"``); the rest are defaults taken where the stock and the setup's frame are known
    (:func:`~cadgen._internal.cam.workholding.holding_boxes`), which compiles it to :class:`Fixture` boxes."""

    type: str
    stated: dict
    name: str = ""
    where: str = ""


@dataclass(frozen=True)
class OpSpec:
    """One operation as the job wrote it: the shared keys parsed, the operation's own keys in ``extra``."""

    op: str
    where: str                    # "setups[0].operations[2]", for the operation's own teaching errors
    index: int                    # its position in the setup
    tool: str | None = None
    faces: tuple[str, ...] = ()
    region: object = None         # the raw value; the operation parses it
    feed: float | None = None     # mm/min override
    speed: float | None = None    # rpm override
    stepdown_mm: float | None = None
    stepover: float | None = None       # a fraction of the tool diameter
    stepover_mm: float | None = None
    stock_to_leave_mm: float = 0.0
    coolant: str | None = None
    name: str = ""
    extra: dict = field(default_factory=dict)
    #: The plunge feed override (mm/min), and the heights above the stock top this operation moves at instead of its
    #: setup's (``None``: the setup's); retract is at or under clearance.
    plunge_mm_min: float | None = None
    clearance_mm: float | None = None
    retract_mm: float | None = None
    #: The shared keys the job wrote (a default is not a key written): an operation refuses one it does not read.
    given: frozenset = frozenset()


@dataclass(frozen=True)
class Setup:
    id: str
    plain: str
    #: ``+Z`` .. ``-Y``, a 3+2 tilt ``{"a_deg": .., "c_deg": ..}`` (a dict), or a planar face's selector (``#o1.f4``,
    #: a str), which the plan resolves against the part to a :class:`~cadgen._internal.cam.wcs.FaceOrientation`.
    orientation: object
    #: One of :data:`ORIGINS`, or ``{"xyz": (x, y, z)}`` in part mm (a bare ``[x, y, z]`` in the job).
    origin: object
    operations: tuple[OpSpec, ...]
    wcs: str = "G54"
    clearance_mm: float = 5.0
    retract_mm: float = 2.0
    #: Keep-out boxes in part coordinates: the job's own, then (once planned) each :class:`Holding`'s compiled.
    fixtures: tuple[Fixture, ...] = ()
    index: int = 0
    #: The vises and plates the job names, in its order; ``plan_setups`` adds their boxes to ``fixtures``.
    holding: tuple[Holding, ...] = ()

    @property
    def tilted(self) -> bool:
        return isinstance(self.orientation, dict)


@dataclass(frozen=True)
class Job:
    machine: Machine
    material: Material
    stock: StockSpec
    tools: tuple[Tool, ...]
    setups: tuple[Setup, ...]
    tolerance_mm: float = 0.01
    coolant: str = "off"
    name: str = ""
    #: The folder relative paths in the job (``stock.path``) resolve against.
    base_dir: Path | None = None
    #: Every value the plan takes that neither the job nor its machine model states: ``{"key", "value", "why"}``,
    #: ``key`` the job path it stands in for (``machine.post``, ``tools.T1.flute_length_mm``).
    assumed: tuple[dict, ...] = ()

    def tool(self, tool_id: str) -> Tool:
        for tool in self.tools:
            if tool.id == tool_id:
                return tool
        raise CamJobError(f"no tool '{tool_id}'; the tools are {', '.join(t.id for t in self.tools)}")


def load_job(job: str | dict | None) -> tuple[dict, Path | None]:
    """The job as a dict, and the folder a job file sits in: a dict (copied through JSON: NaN, infinity and anything
    that is not plain JSON refused), inline JSON text, or a path. JSON's NaN and Infinity are refused too."""
    if job is None:
        raise CamJobError("a plan needs a job: pass --job job.cam.json, or inline JSON like "
                          "'{\"machine\": {\"kind\": \"mill\"}, \"material\": \"aluminum-6061\", ...}'")
    base = None
    if isinstance(job, dict):
        # Through JSON, so a library dict reads exactly as the same job in a file would and shares nothing with the
        # caller (what is parsed keeps its own lists).
        try:
            text = json.dumps(job, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise CamJobError(f"the job is not plain JSON: {exc}") from None
        except RecursionError:
            raise CamJobError("the job is not a job: it nests too deeply to read") from None
    elif not isinstance(job, str):
        raise CamJobError(f"the job must be JSON text, a path to a JSON file, or a dict, not {type(job).__name__}")
    else:
        text = job.strip()
    if not text.startswith("{"):
        path = Path(text).expanduser()
        if not path.is_file():
            what = "a folder" if path.is_dir() else "no job file"
            raise CamJobError(f"{what} at {path}; pass a JSON file path or inline JSON")
        text, base = _read_text(path, "the job file"), path.resolve().parent
    raw = _parse_json(text, "the job")
    if not isinstance(raw, dict):
        raise CamJobError("the job must be a JSON object with machine, material, stock, tools and setups")
    return raw, base


class _NotANumber(ValueError):
    pass


def _read_text(path: Path, what: str) -> str:
    """A UTF-8 file's text, or the teaching refusal naming ``what`` (``the job file``, ``the tool library``)."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise CamJobError(f"{what} {path.name} is not UTF-8 text; save it as UTF-8 JSON") from None
    except OSError as exc:
        raise CamJobError(f"{what} {path.name} cannot be read ({exc.strerror or exc})") from None


def _parse_json(text: str, what: str):
    """The JSON value in ``text``, or the teaching refusal naming ``what``: NaN and Infinity are not numbers here."""
    try:
        return json.loads(text, parse_constant=_refuse_constant)
    except _NotANumber as exc:
        raise CamJobError(f"{what} is not valid JSON: {exc}") from None
    except json.JSONDecodeError as exc:
        raise CamJobError(f"{what} is not valid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}") from None
    except RecursionError:
        raise CamJobError(f"{what} is not valid JSON: it nests too deeply to read") from None
    except ValueError as exc:   # an integer longer than Python reads (sys.get_int_max_str_digits)
        raise CamJobError(f"{what} is not valid JSON: {exc}") from None


def _refuse_constant(name: str):
    raise _NotANumber(f"{name} is not a number a job can hold")


def parse_job(job: str | dict | None, *, post: str | None = None, part_dir: Path | None = None) -> Job:
    """The job, typed and checked. ``post`` (``cadgen cam plan --post``) stands in for ``machine.post``, under the
    same checks: the same job written for another controller without editing it. ``part_dir`` is the part's folder,
    where a relative tool library path is looked for when it is not beside the job file."""
    raw, base = load_job(job)
    if post is not None and isinstance(raw, dict) and isinstance(raw.get("machine"), dict):
        raw = {**raw, "machine": {**raw["machine"], "post": post}}
    check_keys(raw, JOB_KEYS, "job")
    for key in ("machine", "material", "stock", "tools", "setups"):
        if key not in raw:
            raise CamJobError(f"the job needs \"{key}\"; a job names {', '.join(JOB_KEYS[1:6])}")
    machine, assumed = _machine(raw["machine"])
    material = _material(raw["material"])
    stock = _stock(raw["stock"], machine.kind)
    entries = _tool_entries(raw["tools"], base, part_dir)
    seen: dict[str, str] = {}
    for tool, where, _ in entries:
        if tool.id in seen:
            raise CamJobError(f"two tools are called '{tool.id}' ({seen[tool.id]} and {where}); every tool id must be "
                              "different, across the job and its libraries")
        seen[tool.id] = where
    coolant = choice(raw.get("coolant", "off"), COOLANTS, "coolant")
    setups_raw = raw["setups"]
    if not isinstance(setups_raw, list) or not setups_raw:
        raise CamJobError("setups must be a non-empty list, like [{\"id\": \"top\", \"orientation\": \"+Z\", "
                          "\"operations\": [...]}]")
    available = {tool.id: tool for tool, _, _ in entries}
    setups = tuple(_setup(entry, i, machine, available) for i, entry in enumerate(setups_raw))
    ids = [s.id for s in setups]
    if len(set(ids)) != len(ids):
        raise CamJobError(f"setup ids must be different (they name the posted files); got {', '.join(ids)}")
    # A library's tools are the user's rack: only those an operation uses (or "only" picks) are the job's.
    used = {spec.tool for setup in setups for spec in setup.operations if spec.tool}
    tools = tuple(tool for tool, _, keep in entries if keep or tool.id in used)
    numbers: dict[int, str] = {}
    for tool in tools:
        if tool.number in numbers:
            raise CamJobError(f"tools '{numbers[tool.number]}' and '{tool.id}' both post as T{tool.number}; "
                              "give one a different \"number\"")
        numbers[tool.number] = tool.id
    tolerance = read_number(raw, "tolerance_mm", "job", default=0.01, minimum=0.001, maximum=1.0)
    name = raw.get("name", "")
    if not isinstance(name, str):
        raise CamJobError("job.name must be text")
    assumed += _tap_assumed(machine, setups, available)
    assumed += _tool_assumed([tool for tool in tools if tool.id in used])
    return Job(machine=machine, material=material, stock=stock, tools=tools, setups=setups, tolerance_mm=tolerance,
               coolant=coolant, name=name, base_dir=base, assumed=tuple(assumed))


def _assumed(key: str, value: object, why: str) -> dict:
    if isinstance(value, float):
        value = round(value, 4)
    return {"key": key, "value": list(value) if isinstance(value, tuple) else value, "why": why}


def _machine(raw: object) -> tuple[Machine, list[dict]]:
    """The machine and what it assumes. A ``model`` fills in what the job leaves out (the job's keys win); what
    neither states takes the kind's generic value (``machines.GENERIC``), each listed as assumed."""
    if not isinstance(raw, dict):
        raise CamJobError("machine must be an object like {\"kind\": \"mill\"} or {\"model\": \"haas-vf-2\"}")
    model, kind, stated, machine_raw = _merged_machine(raw)
    assumed = _fill_generic(machine_raw, kind, model, stated)
    post = machine_raw["post"]
    assumed = _job_guesses(raw, stated) + assumed
    machine = _machine_keys(machine_raw, kind, post, model)
    return replace(machine, post_options=post_registry.parse_options(post, machine_raw)), assumed


def _merged_machine(raw: dict):
    """``(model, kind, the job's own keys, the keys to check)``: the model's numbers under the job's own."""
    model = machines.lookup(raw["model"]) if "model" in raw else None
    if "kind" not in raw and model is None:
        raise CamJobError("machine needs a model (like \"tormach-1100mx\") or a kind (" + ", ".join(MACHINE_KINDS) +
                          "): ask the user which machine runs the job; if they do not know, write "
                          "{\"kind\": \"mill\", \"assumed\": [\"kind\"]} and the plan lists it as assumed")
    kind = choice(raw.get("kind", model.kind if model else None), MACHINE_KINDS, "machine.kind")
    fourth_axis = model is not None and model.kind == "mill" and "a" in model.rotary
    if model is not None and kind != model.kind and not (kind == "mill4" and fourth_axis):
        extra = " (or mill4 with its 4th axis)" if fourth_axis else ""
        raise CamJobError(f"machine.kind is {kind!r}, but the {model.plain} is a {model.kind}; remove kind, or give "
                          f"{model.kind!r}{extra}")
    stated = {key: value for key, value in raw.items() if key not in ("model", "assumed")}
    machine_raw = {**(model.machine_keys() if model else {}), **stated, "kind": kind}
    if model is not None and kind == "mill4" and "rotary_limits_deg" not in stated:
        machine_raw.pop("rotary_limits_deg", None)
    return model, kind, stated, machine_raw


def _fill_generic(machine_raw: dict, kind: str, model, stated: dict) -> list[dict]:
    """Fill what neither the job nor its model states with the kind's generic value, in place, and say each. A
    generic value yields to the limits that are stated: a rapid no faster than the maximum feed, no spindle limit
    under the slowest speed."""
    assumed: list[dict] = []
    generic = machines.GENERIC[kind]
    whose = f"the {model.plain}'s maker publishes none" if model else "no machine model given"
    if "post" not in machine_raw:
        machine_raw["post"] = generic["post"][0]
        assumed.append(_assumed("machine.post", generic["post"][0], f"no machine model or post given: "
                                                                     f"{generic['post'][1]}"))
    post = machine_raw["post"]
    try:
        post_registry.entry_for(post, kind)
    except CamJobError:
        if model is not None and "post" not in stated:
            raise CamJobError(f"the {model.plain} runs {model.post}, which does not serve a {kind}; name machine.post "
                              "for this kind") from None
        raise
    options = post_registry.option_keys(machine_raw)
    check_keys(stated, MACHINE_KEYS + options, "machine")
    # A post whose tapping cycle does not follow the spindle (Mach3's G84) says the machine taps floating: a fact of
    # the post, not a guess.
    post_class = post_registry._post_class(post)
    if "rigid_tap" not in machine_raw and post_class is not None and not getattr(post_class, "rigid_tap", True):
        machine_raw["rigid_tap"] = False
    if "homed" in options and "homed" not in machine_raw:
        if model is not None and model.homed is not None:
            machine_raw["homed"] = model.homed
        else:
            assumed.append(_assumed("machine.homed", False, machines.GENERIC_HOMED_WHY))
    if model is not None and model.spindle and not {"min_rpm", "max_rpm"} & set(stated):
        assumed.append(_assumed("machine.spindle", model.spindle[0], model.spindle[1]))
    max_feed, min_rpm = machine_raw.get("max_feed_mm_min"), machine_raw.get("min_rpm")
    for key in ("max_rpm", "rapid_mm_min", "tool_change_s"):
        if key in machine_raw or key not in generic:
            continue
        value, why = generic[key]
        if key == "rapid_mm_min" and is_number(max_feed) and max_feed < value:
            # A rapid runs no faster than the machine's top speed (GRBL rapids at its maximum rates).
            value, why = float(max_feed), "the machine's maximum feed: a rapid runs no faster; it only shapes the cycle time"
        if key == "max_rpm" and is_number(min_rpm) and min_rpm > value:
            continue    # a generic limit under the stated slowest speed is no limit at all: none is assumed
        machine_raw[key] = value
        if value:
            assumed.append(_assumed(f"machine.{key}", value, f"{whose}: {why}"))
    if "spindle_spinup_s" not in machine_raw and kind not in ("laser", "plasma", "waterjet", "wire_edm"):
        default = post_registry.option_default(post, "spindle_spinup_s")
        if default:
            assumed.append(_assumed("machine.spindle_spinup_s", default,
                                    f"{whose}: the {post} post dwells this long after each spindle start, as the "
                                    "controller does not wait for the spindle to reach speed"))
    return assumed


def _job_guesses(raw: dict, stated: dict) -> list[dict]:
    """The machine keys the job marks as its own guesses (``"assumed": ["kind"]``), each listed first."""
    guesses = raw.get("assumed", [])
    if not isinstance(guesses, list) or not all(isinstance(key, str) for key in guesses):
        raise CamJobError("machine.assumed lists the machine keys the job guessed, like [\"kind\"]")
    out = []
    for key in guesses:
        choice(key, GUESSABLE_KEYS, "machine.assumed[]")
        if key not in stated:
            raise CamJobError(f"machine.assumed names {key!r}, which the machine does not give; give it, or take it "
                              "out of assumed")
        out.append(_assumed(f"machine.{key}", stated[key], "the job marks it as a guess: the user did not know"))
    return out


def _machine_keys(raw: dict, kind: str, post: str, model) -> Machine:
    """The machine's keys (the job's over its model's over the kind's generic ones), checked."""
    travel = None
    if "travel_mm" in raw:
        counts, words = _TRAVEL.get(kind, ((2, 3), "[x, y] or [x, y, z]"))
        if not isinstance(raw["travel_mm"], (list, tuple)) or len(raw["travel_mm"]) not in counts:
            raise CamJobError(f"machine.travel_mm: a {kind}'s travel_mm is {words} in mm, not "
                              f"{shown(raw['travel_mm'])}")
        travel = number_list(raw["travel_mm"], "machine.travel_mm", length=counts, positive=True)
    kinematics = None
    if "kinematics" in raw:
        if kind != "mill5":
            raise CamJobError("machine.kinematics is for a mill5 (a five-axis mill); remove it for a " + kind)
        kinematics = choice(raw["kinematics"], KINEMATICS, "machine.kinematics")
    elif kind == "mill5":
        kinematics = "ac_trunnion"
    limits = {}
    if "rotary_limits_deg" in raw:
        value = raw["rotary_limits_deg"]
        if not isinstance(value, dict):
            raise CamJobError("machine.rotary_limits_deg must be an object like {\"a\": [-120, 120]}")
        check_keys(value, ("a", "b", "c"), "machine.rotary_limits_deg")
        limits = {axis: number_list(v, f"machine.rotary_limits_deg.{axis}", length=2) for axis, v in value.items()}
        for axis, (low, high) in limits.items():
            if high <= low:
                raise CamJobError(f"machine.rotary_limits_deg.{axis} must be [low, high] with high more than low")
    diameter_mode = raw.get("diameter_mode", True)
    if not isinstance(diameter_mode, bool):
        raise CamJobError("machine.diameter_mode must be true or false")
    rigid_tap = raw.get("rigid_tap")
    if rigid_tap is not None and not isinstance(rigid_tap, bool):
        raise CamJobError("machine.rigid_tap is true (the controller taps with the feed synchronised to the spindle) "
                          "or false (taps run in a floating holder)")
    name = raw.get("name", "")
    if not isinstance(name, str):
        raise CamJobError("machine.name must be text")
    cutting = _cutting_keys(raw, kind)
    # A spindle or a feed slower than 1 a minute posts as S0 or F0: a spindle that never turns, an axis that never
    # moves.
    max_rpm = read_number(raw, "max_rpm", "machine", minimum=1.0)
    min_rpm = read_number(raw, "min_rpm", "machine", minimum=1.0)
    if min_rpm is not None and max_rpm is not None and min_rpm > max_rpm:
        raise CamJobError(f"machine.min_rpm ({min_rpm:g}) is more than machine.max_rpm ({max_rpm:g}); the spindle "
                          "turns between them")
    return Machine(**cutting,
        kind=kind, post=post, name=name, travel_mm=travel, max_rpm=max_rpm, min_rpm=min_rpm,
        max_feed_mm_min=read_number(raw, "max_feed_mm_min", "machine", minimum=1.0),
        rapid_mm_min=read_number(raw, "rapid_mm_min", "machine", minimum=1.0),
        tool_change_s=read_number(raw, "tool_change_s", "machine", minimum=0.0),
        kinematics=kinematics, rotary_limits_deg=limits, diameter_mode=diameter_mode,
        # A minute is longer than any spindle takes to reach speed; past it the number is a units slip.
        spindle_spinup_s=read_number(raw, "spindle_spinup_s", "machine", minimum=0.0, maximum=60.0),
        rigid_tap=rigid_tap, model=model.id if model else None,
    )


def _tap_assumed(machine: Machine, setups, tools: dict[str, Tool]) -> list[dict]:
    """A tap that does not say whether it is rigid, on a machine that does not say whether it taps rigidly: posted
    with the controller's own tapping cycle (operations/drill.py), said here."""
    if machine.rigid_tap is not None:
        return []
    for setup in setups:
        for spec in setup.operations:
            tool = tools.get(spec.tool) if spec.tool else None
            cycle = spec.extra.get("cycle") or (DEFAULT_CYCLE.get(tool.type) if tool is not None else None)
            if spec.op == "drill" and cycle == "tap" and "rigid" not in spec.extra:
                return [_assumed("machine.rigid_tap", True, machines.GENERIC_RIGID_TAP_WHY)]
    return []


#: What a used milling tool's unstated length stands for, and what reads it.
_TOOL_WHY = {
    "flute_length_mm": "no flute_length_mm given: a catalogue {plain}'s; the stepdown is held to it, and reach does "
                       "not judge a cut deeper than it",
    "stickout_mm": "no stickout_mm given: the flutes and a quarter more (at least 5 mm more); reach does not judge "
                   "a cut deeper than it",
    "shank_diameter_mm": "no shank_diameter_mm given: a cutter under 3 mm sits on a 3 mm shank; holder_collision "
                         "judges that shank",
    "material": "no material given: carbide, the speeds' table; an HSS {plain} wants about a third of that speed, so "
                "state \"material\": \"hss\" if it is one",
    "flutes": "no flutes given: {plain}'s usual count; the feed is per tooth, so a tool with fewer flutes would be "
              "fed too hard",
}


def _tool_assumed(tools) -> list[dict]:
    return [_assumed(f"tools.{tool.id}.{key}", getattr(tool, key), _TOOL_WHY[key].format(plain=tool.plain))
            for tool in tools for key in tool.assumed]


def _tool_entries(value: object, base: Path | None, part_dir: Path | None) -> list[tuple[Tool, str, bool]]:
    """Every tool the job can name: ``(tool, where, kept)``, ``kept`` true for a tool the job lists itself or a
    library's ``only`` picks (a library's other tools are kept only when an operation uses them)."""
    if isinstance(value, str):
        value = [{"library": value}]
    if not isinstance(value, list) or not value:
        raise CamJobError("tools must be a non-empty list, like [{\"id\": \"T1\", \"type\": \"flat\", "
                          "\"diameter_mm\": 6}], or a tool library file, like \"my-tools.json\"")
    out: list[tuple[Tool, str, bool]] = []
    for i, entry in enumerate(value):
        if isinstance(entry, dict) and "library" in entry:
            out += _library(entry, f"tools[{i}]", base, part_dir)
        else:
            out.append((parse_tool(entry, i), f"tools[{i}]", True))
    return out


#: The keys a tool library file's object may carry (a bare list of tools is a library too).
LIBRARY_KEYS = ("name", "tools")


def _library(entry: dict, where: str, base: Path | None, part_dir: Path | None) -> list[tuple[Tool, str, bool]]:
    """A ``{"library": path, "only": [ids]}`` entry: the file's tools, each parsed as an inline one, ``only`` (when
    given) the ids kept whether or not an operation uses them."""
    check_keys(entry, ("library", "only"), where, hint="a tool library entry")
    path = entry["library"]
    if not isinstance(path, str) or not path.strip():
        raise CamJobError(f"{where}.library names a tool library file (JSON), relative to the job file or the part")
    found = _find_library(path, base, part_dir, where)
    label = found.name
    data = _parse_json(_read_text(found, "the tool library"), f"the tool library {label}")
    if isinstance(data, dict):
        check_keys(data, LIBRARY_KEYS, label, hint="a tool library")
        data = data.get("tools")
    if not isinstance(data, list) or not data:
        raise CamJobError(f"the tool library {label} must be a non-empty JSON list of tools, or {{\"tools\": [...]}}, "
                          "each tool as a job writes one")
    tools = [(parse_tool(raw, k, where=f"{label} tools[{k}]"), f"{label} tools[{k}]") for k, raw in enumerate(data)]
    only = entry.get("only")
    if only is None:
        return [(tool, at, False) for tool, at in tools]
    if not isinstance(only, list) or not only or not all(isinstance(tool_id, str) for tool_id in only):
        raise CamJobError(f"{where}.only lists tool ids from {label}, like [\"T1\", \"T4\"]")
    ids = tuple(tool.id for tool, _ in tools)
    for tool_id in only:
        choice(tool_id, ids, f"{where}.only[] (a tool of {label})")
    return [(tool, at, tool.id in only) for tool, at in tools]


def _find_library(path: str, base: Path | None, part_dir: Path | None, where: str) -> Path:
    """The library file: an absolute path, else beside the job file, else beside the part (else, with neither
    known, from the working folder)."""
    named = Path(path).expanduser()
    if named.is_absolute():
        places = [named]
    else:
        places = [folder / named for folder in (base, part_dir) if folder is not None] or [named]
    for place in places:
        if place.is_file():
            return place
    looked = " or ".join(str(place) for place in places)
    raise CamJobError(f"{where}.library: no tool library at {looked}; give its path relative to the job file or the "
                      "part, or an absolute one")


def _cutting_keys(raw: dict, kind: str) -> dict:
    """A cutting machine's own keys (:data:`CUTTING_MACHINE_KEYS`), each refused on a machine it does not fit."""
    out: dict = {}
    for key, kinds in CUTTING_MACHINE_KEYS.items():
        if key not in raw:
            continue
        if kind not in kinds:
            raise CamJobError(f"machine.{key} is a {' or '.join(kinds)}'s setting; remove it for a {kind}")
    if "power_w" in raw:
        out["power_w"] = read_number(raw, "power_w", "machine", maximum=100000.0)
    if "laser_source" in raw:
        out["laser_source"] = choice(raw["laser_source"], LASER_SOURCES, "machine.laser_source")
    if "amps" in raw:
        out["amps"] = read_number(raw, "amps", "machine", minimum=10.0, maximum=400.0)
    if "abrasive" in raw:
        if not isinstance(raw["abrasive"], bool):
            raise CamJobError("machine.abrasive must be true (an abrasive jet, for metal and stone) or false (pure "
                              "water, for foam, rubber and soft plastics)")
        out["abrasive"] = raw["abrasive"]
    return out


def _material(raw: object) -> Material:
    """A table name (or an alias of one); a table name with some of its numbers overridden, like
    ``{"name": "aluminum-6061", "surface_m_min": 300}`` (the rest of the row stands); or a material of the job's
    own, which states its surface speed and chip load. The chip load is a 6 mm tool's, scaled with the diameter as the
    table's is, or one per tool diameter, ``{"3": 0.02, "6": 0.04}``, interpolated by the tool's diameter
    (``feeds.chipload_at``)."""
    from cadgen._internal.cam.feeds import MATERIAL_ALIASES, MATERIALS

    names = (*MATERIALS, *MATERIAL_ALIASES)
    if isinstance(raw, str):
        name = MATERIAL_ALIASES.get(raw, raw)
        if name not in MATERIALS:
            choice(raw, names, "material")
        return Material(name=name, plain=MATERIALS[name]["plain"], table=True)
    if not isinstance(raw, dict):
        raise CamJobError(f"material must be a name ({', '.join(names)}) or an object with surface_m_min (or sfm) "
                          "and chipload_mm")
    check_keys(raw, MATERIAL_KEYS, "material")
    name = raw.get("name", "custom")
    if not isinstance(name, str):
        raise CamJobError("material.name must be text")
    name = MATERIAL_ALIASES.get(name, name)
    table = name in MATERIALS
    if "surface_m_min" in raw and "sfm" in raw:
        raise CamJobError("material: give one surface speed, surface_m_min (metres a minute) or sfm (feet a minute), "
                          "not both")
    if not table and "surface_m_min" not in raw and "sfm" not in raw:
        raise CamJobError(f"material needs one surface speed: surface_m_min (metres a minute) or sfm (feet a minute); "
                          f"{shown(name)} is not in the table ({', '.join(names)}), whose rows need none")
    if not table and "chipload_mm" not in raw:
        raise CamJobError("material needs chipload_mm, the chip load per tooth for a 6 mm tool (scaled with the "
                          "diameter), or one per tool diameter, like {\"3\": 0.02, \"6\": 0.04}")
    # Bounded well past any real material (the fastest carbide on aluminium runs ~1500 m/min, ~0.3 mm a tooth), so a
    # typo is refused rather than posted as a feed no machine has.
    speed = None
    if "surface_m_min" in raw:
        speed = read_number(raw, "surface_m_min", "material", maximum=10000.0)
    elif "sfm" in raw:
        speed = read_number(raw, "sfm", "material", maximum=33000.0) * 0.3048
    return Material(name=name, plain=MATERIALS[name]["plain"] if table else name, table=table, surface_m_min=speed,
                    chipload_mm=_chipload(raw["chipload_mm"]) if "chipload_mm" in raw else None,
                    drill_mm_per_rev=read_number(raw, "drill_mm_per_rev", "material", maximum=5.0),
                    stepdown_fraction=read_number(raw, "stepdown_fraction", "material", minimum=0.001, maximum=4.0))


def _chipload(value: object) -> float | tuple[tuple[float, float], ...]:
    """One chip load (mm a tooth), or ``{"<tool diameter mm>": chip load}``: each key a diameter over 0, once."""
    if not isinstance(value, dict):
        return read_number({"chipload_mm": value}, "chipload_mm", "material", maximum=5.0)
    if not value:
        raise CamJobError("material.chipload_mm: give a chip load, or one per tool diameter like {\"3\": 0.02, "
                          "\"6\": 0.04}")
    bands: dict[float, float] = {}
    for key, load in value.items():
        try:
            diameter = float(key)
        except ValueError:
            diameter = math.nan
        if not (math.isfinite(diameter) and 0 < diameter <= MAX_STOCK_MM):
            raise CamJobError(f"material.chipload_mm: {shown(key)} is not a tool diameter in mm; key each chip load "
                              "by the diameter it is for, like {\"3\": 0.02, \"6\": 0.04}")
        if diameter in bands:
            raise CamJobError(f"material.chipload_mm: the {diameter:g} mm tool diameter is listed twice "
                              f"({shown(key)}); give each diameter once")
        bands[diameter] = read_number({key: load}, key, "material.chipload_mm", maximum=5.0)
    return tuple(sorted(bands.items()))


def _margins(value: object, where: str, *, box: bool) -> tuple[float, ...]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        m = read_number({"margin_mm": value}, "margin_mm", where.rsplit(".", 1)[0], minimum=0.0, maximum=MAX_STOCK_MM)
        return (m, m, m, m, 0.0 if box else m, m) if box else (m, m, m, m, 0.0, 0.0)
    numbers = number_list(value, where, length=(2, 3, 6))
    if any(v < 0 for v in numbers):
        raise CamJobError(f"{where} must not be negative")
    if any(v > MAX_STOCK_MM for v in numbers):
        raise CamJobError(f"{where} must be at most {MAX_STOCK_MM:,.0f} mm a side (check the units: a job is in mm)")
    if len(numbers) == 6:
        return numbers
    if len(numbers) == 2:
        x, y = numbers
        return (x, x, y, y, 0.0, 0.0)
    x, y, z = numbers
    return (x, x, y, y, 0.0, z)


def _stock(raw: object, kind: str) -> StockSpec:
    if not isinstance(raw, dict):
        raise CamJobError("stock must be an object like {\"kind\": \"box\", \"margin_mm\": [2, 2, 1]}")
    stock_kind = choice(raw.get("kind"), STOCK_KINDS, "stock.kind")
    allowed_kinds = STOCK_FOR_KIND[kind]
    if stock_kind not in allowed_kinds:
        words = _STOCK_WORDS.get(kind, f"a {kind} starts from {', '.join(allowed_kinds)}")
        raise CamJobError(f"stock.kind is {stock_kind!r}: {words}; use {' or '.join(allowed_kinds)}")
    allowed = {"box": ("kind", "margin_mm", "size_mm"),
               "cylinder": ("kind", "diameter_mm", "length_mm", "axis", "margin_mm", "face_stock_mm"),
               "sheet": ("kind", "thickness_mm", "margin_mm"),
               "from_step": ("kind", "path")}[stock_kind]
    check_keys(raw, allowed, "stock", hint=f"{stock_kind} stock")
    if stock_kind == "box":
        if "margin_mm" in raw and "size_mm" in raw:
            raise CamJobError("stock: give margin_mm or size_mm, not both")
        size = number_list(raw["size_mm"], "stock.size_mm", length=3, positive=True) if "size_mm" in raw else None
        if size is not None and max(size) > MAX_STOCK_MM:
            raise CamJobError(f"stock.size_mm must be at most {MAX_STOCK_MM:,.0f} mm on every axis (check the units: a "
                              "job is in mm)")
        margins = _margins(raw.get("margin_mm", 0.0), "stock.margin_mm", box=True)
        return StockSpec(kind="box", margin_mm=margins, size_mm=size)
    if stock_kind == "cylinder":
        margin = raw.get("margin_mm", 0.0)
        if isinstance(margin, (list, tuple)):
            radial, axial = number_list(margin, "stock.margin_mm", length=2)
            if min(radial, axial) < 0 or max(radial, axial) > MAX_STOCK_MM:
                raise CamJobError(f"stock.margin_mm is [radial, axial] in mm, each 0 to {MAX_STOCK_MM:,.0f}, not "
                                  f"{shown(margin)}")
        else:
            radial = axial = read_number(raw, "margin_mm", "stock", default=0.0, minimum=0.0, maximum=MAX_STOCK_MM)
        if "diameter_mm" in raw and radial > 0:
            raise CamJobError(f"stock: a bar of a stated diameter_mm takes no radial margin (margin_mm gives "
                              f"{radial:g} mm all round); give diameter_mm or a radial margin_mm, not both (margin_mm "
                              "[0, axial] keeps an axial one)")
        if "length_mm" in raw and axial > 0:
            raise CamJobError(f"stock: a bar of a stated length_mm takes no axial margin (margin_mm gives {axial:g} mm "
                              "at the ends); give length_mm or an axial margin_mm, not both (margin_mm [radial, 0] "
                              "keeps a radial one)")
        return StockSpec(kind="cylinder", margin_mm=(radial, axial),
                         diameter_mm=read_number(raw, "diameter_mm", "stock", maximum=MAX_STOCK_MM),
                         length_mm=read_number(raw, "length_mm", "stock", maximum=MAX_STOCK_MM),
                         axis=choice(raw.get("axis", "z"), ("x", "y", "z"), "stock.axis"),
                         face_stock_mm=read_number(raw, "face_stock_mm", "stock", minimum=0.0, maximum=MAX_STOCK_MM,
                                                   default=1.0 if kind == "lathe" else None))
    if stock_kind == "sheet":
        margins = _margins(raw.get("margin_mm", 0.0), "stock.margin_mm", box=False)
        return StockSpec(kind="sheet", margin_mm=margins,
                         thickness_mm=read_number(raw, "thickness_mm", "stock", maximum=MAX_STOCK_MM))
    path = raw.get("path")
    if not isinstance(path, str) or not path.strip():
        raise CamJobError("stock.path names the stock's STEP (a casting, a blank), relative to the job file or the part")
    # An absolute path is checked now; a relative one is found beside the job file or, failing that, the part
    # (stock.build_stock), which is not known until the part is read.
    where = Path(path).expanduser()
    if where.is_absolute() and not where.is_file():
        raise CamJobError(f"stock.path: no STEP at {where}")
    return StockSpec(kind="from_step", path=path)


_REF = re.compile(r"^(?:[^#\s]*)#o[\w.]+\.f\d+$|^#f\d+$")


def _setup(raw: object, index: int, machine: Machine, tools: dict[str, Tool]) -> Setup:
    where = f"setups[{index}]"
    if not isinstance(raw, dict):
        raise CamJobError(f"{where} must be an object with an id, an orientation and operations")
    check_keys(raw, SETUP_KEYS, where)
    setup_id = raw.get("id", f"setup{index + 1}")
    if not isinstance(setup_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", setup_id):
        raise CamJobError(f"{where}.id must be a short name of letters, digits, - or _ (it names the posted file), "
                          f"not {shown(setup_id)}")
    orientation = raw.get("orientation", "+Z")
    if isinstance(orientation, dict):
        check_keys(orientation, ("a_deg", "b_deg", "c_deg"), f"{where}.orientation")
        if machine.kind not in ("mill4", "mill5"):
            raise CamJobError(f"{where}.orientation tilts the part (3+2), which needs a mill4 or mill5; this machine is "
                              f"a {machine.kind}. Use +Z, -Z, +X, -X, +Y or -Y and refixture by hand")
        for axis in ("a_deg", "b_deg", "c_deg"):
            read_number(orientation, axis, f"{where}.orientation", default=0.0, minimum=-360.0, maximum=360.0)
        if "b_deg" in orientation and machine.kinematics != "bc_head":
            raise CamJobError(f"{where}.orientation: b_deg needs a mill5 with kinematics bc_head; use a_deg and c_deg")
        orientation = {k: float(v) for k, v in orientation.items()}
        from cadgen._internal.cam.multiaxis import check_orientation

        # What the machine's rotary axes (and machine.rotary_limits_deg) can reach; every axis it has, named.
        orientation = check_orientation(orientation, machine, f"{where}.orientation")
    elif isinstance(orientation, str) and "#" in orientation:
        orientation = _face_orientation(orientation, f"{where}.orientation", machine)
    else:
        orientation = choice(orientation, ORIENTATIONS, f"{where}.orientation")
    origin = _origin(raw.get("origin", "stock-top-center"), f"{where}.origin", machine)
    wcs = choice(raw.get("wcs", WORK_OFFSETS[min(index, 5)]), WORK_OFFSETS, f"{where}.wcs")
    fixtures, holding = _fixtures(raw.get("fixture", []), f"{where}.fixture", machine)
    clearance, retract = _heights(raw, where, 5.0, 2.0)
    ops_raw = raw.get("operations")
    if not isinstance(ops_raw, list) or not ops_raw:
        raise CamJobError(f"{where}.operations must be a non-empty list, like [{{\"op\": \"face\", \"tool\": \"T1\"}}]")
    operations = tuple(_operation(op, f"{where}.operations[{i}]", i, machine, tools, (clearance, retract))
                       for i, op in enumerate(ops_raw))
    plain = raw.get("name") or _plain_orientation(orientation)
    if not isinstance(plain, str):
        raise CamJobError(f"{where}.name must be text")
    return Setup(
        id=setup_id, plain=plain, orientation=orientation, origin=origin, operations=operations, wcs=wcs,
        clearance_mm=clearance, retract_mm=retract, fixtures=tuple(fixtures), index=index, holding=tuple(holding),
    )


def _face_orientation(value: str, where: str, machine: Machine) -> str:
    """A setup turned onto a face (``#o1.f4``): a planar face's selector, kept as written; the plan reads the face's
    outward normal from the part (``wcs.with_face_orientations``), and refuses one that is not planar."""
    if machine.kind not in FACE_ORIENTATION_KINDS:
        held = ("a lathe's setup is its spindle axis" if machine.kind == "lathe"
                else f"a {machine.kind} cuts through the sheet lying flat")
        raise CamJobError(f"{where} is {shown(value)}, a face: {held}, so it cannot be turned onto a face; "
                          "remove orientation (or use +Z)")
    if re.search(r"\.[ev]\d+$", value):
        what = "an edge" if re.search(r"\.e\d+$", value) else "a vertex"
        raise CamJobError(f"{where} is {shown(value)}, {what}: a setup looks down a flat face's outward normal, so "
                          "name a planar face (#o1.f4; cadgen cam features lists them)")
    if not _REF.match(value):
        raise CamJobError(f"{where} is {shown(value)}; use one of {', '.join(ORIENTATIONS)}, a planar face's "
                          "selector like \"#o1.f4\", or a tilt {\"a_deg\": .., \"c_deg\": ..} on a mill4 or mill5")
    return value


def _fixtures(value: object, where: str, machine: Machine) -> tuple[list[Fixture], list[Holding]]:
    """A setup's ``fixture``: one entry or a list. A box (no ``type``, or ``"box"``) in part coordinates, or a
    ``vise`` or ``plate`` (:class:`Holding`, compiled to boxes by the plan)."""
    entries = [value] if isinstance(value, dict) else value
    if not isinstance(entries, list):
        raise CamJobError(f"{where} must be a box {{\"min_mm\": [x, y, z], \"max_mm\": [x, y, z]}}, a vise "
                          "{\"type\": \"vise\"}, a plate {\"type\": \"plate\"}, or a list of them")
    boxes, holding = [], []
    for i, entry in enumerate(entries):
        at = f"{where}[{i}]"
        if not isinstance(entry, dict):
            raise CamJobError(f"{at} must be a box {{\"min_mm\": [x, y, z], \"max_mm\": [x, y, z]}} in part "
                              "coordinates, or a vise or plate {\"type\": \"vise\"}")
        kind = entry.get("type", "box")
        if kind in ("chuck", "collet"):
            raise CamJobError(f"{at}.type is {kind!r}: cadgen does not model a {kind} (a lathe's bar behind the part, "
                              "where it is held, is already kept from every tool); on a mill give its jaws as boxes "
                              "{\"min_mm\", \"max_mm\"} in part coordinates")
        kind = choice(kind, tuple(FIXTURE_KEYS), f"{at}.type")
        check_keys(entry, FIXTURE_KEYS[kind], at, hint=f"a {kind}")
        name = entry.get("name", "")
        if not isinstance(name, str):
            raise CamJobError(f"{at}.name must be text")
        if kind == "box":
            low = number_list(entry.get("min_mm"), f"{at}.min_mm", length=3)
            high = number_list(entry.get("max_mm"), f"{at}.max_mm", length=3)
            if any(h <= lo for lo, h in zip(low, high)):
                raise CamJobError(f"{at}: max_mm must be more than min_mm on every axis")
            boxes.append(Fixture(low, high, name))
            continue
        if machine.kind not in HOLDING_KINDS:
            held = ("a lathe holds its bar in the chuck, and the bar behind the part is already kept from every tool"
                    if machine.kind == "lathe" else f"a {machine.kind} cuts a sheet lying flat on its bed")
            raise CamJobError(f"{at}: {held}; a {kind} is a mill's or a router's, so remove it (a box "
                              "{\"min_mm\", \"max_mm\"} marks anything else the tool must keep out of)")
        holding.append(Holding(kind, _holding_sizes(entry, kind, at), name, at))
    return boxes, holding


def _holding_sizes(entry: dict, kind: str, at: str) -> dict:
    """The sizes a vise or plate states, checked (mm, each over 0; a vise's parallels may be 0). A vise's
    ``grip_mm`` (how far its jaws reach up the stock's sides) is ``jaw_height_mm - parallels_mm``: any two give the
    third, three must agree within :data:`VISE_AGREE_MM`, and a grip of 0 or less holds nothing."""
    stated: dict = {}
    for key in FIXTURE_KEYS[kind]:
        if key in ("type", "name") or key not in entry:
            continue
        if key == "jaws_along":
            stated[key] = choice(entry[key], ("x", "y"), f"{at}.jaws_along")
        elif key == "parallels_mm":
            stated[key] = read_number(entry, key, at, minimum=0.0, maximum=MAX_STOCK_MM)
        elif key == "grip_mm":
            stated[key] = read_number(entry, key, at, inclusive=True, maximum=MAX_STOCK_MM)
        else:
            stated[key] = read_number(entry, key, at, maximum=MAX_STOCK_MM)
    if kind != "vise":
        return stated
    height, grip, parallels = (stated.get(k) for k in ("jaw_height_mm", "grip_mm", "parallels_mm"))
    if grip is not None and grip <= 0:
        raise CamJobError(f"{at}.grip_mm is {grip:g}: the jaws would hold none of the stock; grip_mm is how far "
                          "they reach up its sides, more than 0")
    if height is not None and parallels is not None:
        if grip is None and height - parallels <= 0:
            raise CamJobError(f"{at}: the jaws ({height:g} mm) are no taller than the parallels ({parallels:g} mm), "
                              "so they hold none of the stock; raise jaw_height_mm or lower parallels_mm")
        if grip is not None and abs(height - parallels - grip) > VISE_AGREE_MM:
            raise CamJobError(f"{at}: grip_mm ({grip:g}) must be jaw_height_mm ({height:g}) less parallels_mm "
                              f"({parallels:g}), {height - parallels:g}: the jaws' top stands that far over the "
                              "stock's bottom; state two of the three")
    elif height is not None and grip is not None and grip > height:
        raise CamJobError(f"{at}: grip_mm ({grip:g}) is more than jaw_height_mm ({height:g}): the stock rests on the "
                          "vise's floor at the lowest, so the jaws reach at most their own height up it")
    return stated


def _heights(raw: dict, where: str, clearance: float, retract: float) -> tuple[float, float]:
    """``clearance_mm`` and ``retract_mm`` (heights above the stock top, each defaulting to the one given): both over
    0, the retract at or under the clearance (the tool lifts to the retract between passes and to the clearance
    between features)."""
    clearance = read_number(raw, "clearance_mm", where, default=clearance, maximum=1000.0)
    retract = read_number(raw, "retract_mm", where, default=retract, maximum=1000.0)
    if retract > clearance:
        raise CamJobError(f"{where}.retract_mm ({retract:g} mm) must be at or under {where}.clearance_mm "
                          f"({clearance:g} mm): the tool lifts to the retract between passes and to the clearance "
                          "between features; lower retract_mm or raise clearance_mm")
    return clearance, retract


def _origin(value: object, where: str, machine: Machine) -> object:
    """One of :data:`ORIGINS`, ``{"xyz": [x, y, z]}`` or a bare ``[x, y, z]`` (both kept as ``{"xyz": (...)}``)."""
    if isinstance(value, list):
        return {"xyz": number_list(value, where, length=3)}
    if isinstance(value, dict):
        check_keys(value, ("xyz",), where)
        return {"xyz": number_list(value.get("xyz"), f"{where}.xyz", length=3)}
    if isinstance(value, str) and value not in ORIGINS:
        # Another spelling of one of ours (stock_top_center, part_bbox_bottom_corner) is named outright; difflib's
        # nearest word could be the wrong corner.
        ours = value.lower().replace("_", "-").replace("bbox-", "").replace("centre", "center")
        if ours in ORIGINS:
            raise CamJobError(f"{where} is {shown(value)} (did you mean '{ours}'?); use one of {', '.join(ORIGINS)}, "
                              "or a part point [x, y, z]")
    origin = choice(value, ORIGINS, where)
    if machine.kind == "lathe" and origin.endswith("corner"):
        raise CamJobError(f"{where}: a lathe's work zero sits on the spindle axis; {origin} is off it: use "
                          "stock-top-center (or part-top-center on a round part)")
    return origin


def _plain_orientation(orientation: object) -> str:
    if isinstance(orientation, dict):
        return "Tilted " + " ".join(f"{k[0].upper()}{v:g}°" for k, v in orientation.items() if v)
    if "#" in orientation:
        return f"Face {orientation} up"
    return {"+Z": "Top", "-Z": "Bottom", "+X": "Right", "-X": "Left", "+Y": "Back", "-Y": "Front"}[orientation]


def _operation(raw: object, where: str, index: int, machine: Machine, tools: dict[str, Tool],
               heights: tuple[float, float] = (5.0, 2.0)) -> OpSpec:
    if not isinstance(raw, dict):
        raise CamJobError(f"{where} must be an object like {{\"op\": \"pocket\", \"tool\": \"T1\", \"faces\": [\"#o1.f12\"]}}")
    if "op" not in raw:
        raise CamJobError(f"{where} needs \"op\", the operation's name")
    entry = operation_entry(raw["op"], f"{where}.op")
    # A shared key the operation also has as its own (a drill's chip-break retract_mm) is the operation's.
    own = set(get_operation(entry.name).keys) if operation_built(entry.name) else set()
    common = tuple(key for key in OP_COMMON_KEYS if key not in own)
    if machine.kind not in entry.machines:
        raise CamJobError(f"{where}: a {machine.kind} cannot {entry.plain.lower()} ('{entry.name}' runs on "
                          f"{', '.join(entry.machines)}); change the machine or the operation")
    tool = raw.get("tool")
    if tool is not None:
        if not isinstance(tool, str) or tool not in tools:
            raise CamJobError(f"{where}.tool is {shown(tool)}, which is not in tools; the tools are {', '.join(tools)}")
    faces = raw.get("faces", [])
    if isinstance(faces, str):
        faces = [faces]
    if not isinstance(faces, list) or not all(isinstance(face, str) and _REF.match(face) for face in faces):
        raise CamJobError(f"{where}.faces must be a list of face refs like \"#o1.f12\" (cadgen cam features lists "
                          f"them), not {shown(raw.get('faces'))}")
    for i, face in enumerate(faces):
        if face in faces[:i]:
            raise CamJobError(f"{where}.faces: {face!r} is listed twice; name each face once")
    # A thousandth of a millimetre is finer than any machine steps; below it a number is a units slip.
    stepover = read_number(raw, "stepover", where, minimum=0.001, maximum=1.0)
    stepover_mm = read_number(raw, "stepover_mm", where, minimum=0.001, maximum=MAX_STOCK_MM)
    if stepover is not None and stepover_mm is not None:
        raise CamJobError(f"{where}: give stepover (a fraction of the tool diameter) or stepover_mm, not both")
    name = raw.get("name", "")
    if not isinstance(name, str):
        raise CamJobError(f"{where}.name must be text")
    clearance, retract = _heights({key: raw[key] for key in ("clearance_mm", "retract_mm") if key in common and key in raw},
                                  where, *heights)
    return OpSpec(
        op=entry.name, where=where, index=index, tool=tool, faces=tuple(faces), region=raw.get("region"),
        feed=read_number(raw, "feed", where), speed=read_number(raw, "speed", where, minimum=1.0),
        stepdown_mm=read_number(raw, "stepdown_mm", where, minimum=0.001, maximum=MAX_STOCK_MM), stepover=stepover,
        stepover_mm=stepover_mm,
        stock_to_leave_mm=read_number(raw, "stock_to_leave_mm", where, default=0.0, minimum=0.0),
        coolant=choice(raw["coolant"], COOLANTS, f"{where}.coolant") if "coolant" in raw else None,
        name=name, extra={key: value for key, value in raw.items() if key not in common},
        given=frozenset(key for key in raw if key in common),
        plunge_mm_min=read_number(raw, "plunge_mm_min", where) if "plunge_mm_min" in common else None,
        clearance_mm=clearance if "clearance_mm" in raw and "clearance_mm" in common else None,
        retract_mm=retract if "retract_mm" in raw and "retract_mm" in common else None,
    )
