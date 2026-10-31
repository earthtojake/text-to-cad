"""Parse and validate a CAM job: a closed vocabulary (law 16), frozen dataclasses, one-sentence teaching errors.

The job is JSON: a file path, inline JSON text, or a dict from a library caller. :func:`parse_job` returns a
:class:`Job`::

    Job(name, machine: Machine, material: Material, stock: Stock, tools: dict[str, Tool], setups: tuple[Setup, ...],
        tolerance_mm, coolant)

What needs the part (that a face exists, faces up and can be reached) is checked later, against the part
(``run.py``). Every refusal is a :class:`~cadgen._internal.cam.job_errors.CamJobError` naming the path into the job
(``setups[0].operations[2].tool``), what is wrong and the allowed set. A dict job is copied through JSON, so it reads
exactly as the same job in a file would. Stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cadgen._internal.cam.feeds import MATERIAL_ALIASES, MATERIALS
from cadgen._internal.cam.job_errors import CamJobError, check_keys, choice, is_number, number_list, read_number, shown
from cadgen._internal.cam.tools import EXAMPLE, Tool, parse_tool

__all__ = ["COOLANTS", "OPERATIONS", "ORIENTATIONS", "ORIGINS", "POSTS", "CamJobError", "Job", "Machine", "Material",
           "Operation", "Setup", "Stock", "load_job", "parse_job"]

#: Each post: FreeCAD's post processor, the posted file's extension, the options it is run with, and whether the
#: controller changes tools itself. GRBL cannot (its post comments ``M6`` out), so a setup with several tools posts one
#: file per tool, each run after the operator changes the tool and sets its length.
POSTS: dict[str, dict] = {
    "grbl": {"freecad": "grbl", "ext": ".nc", "args": "--no-show-editor --precision 3", "tool_change": False},
    "linuxcnc": {"freecad": "linuxcnc", "ext": ".ngc", "args": "--no-show-editor --precision 3", "tool_change": True},
    "mach3": {"freecad": "mach3_mach4", "ext": ".tap", "args": "--no-show-editor --precision 3", "tool_change": True},
    "fanuc": {"freecad": "fanuc", "ext": ".nc", "args": "--no-show-editor --precision 3", "tool_change": True},
    "centroid": {"freecad": "centroid", "ext": ".nc", "args": "--no-show-editor", "tool_change": True},
    "uccnc": {"freecad": "uccnc", "ext": ".nc", "args": "--no-show-editor --precision 3", "tool_change": True},
    "smoothie": {"freecad": "smoothie", "ext": ".gcode", "args": "--no-show-editor --precision 3",
                 "tool_change": False},
}
ORIENTATIONS = ("+Z", "-Z")
ORIGINS = ("stock-top-center", "stock-top-corner", "stock-bottom-center", "stock-bottom-corner")
COOLANTS = ("off", "flood", "mist")
WORK_OFFSETS = ("G54", "G55", "G56", "G57", "G58", "G59")
#: Each operation: its own keys (beyond :data:`OP_COMMON_KEYS`), whether it must name faces, and the feeds kind.
OPERATIONS: dict[str, dict] = {
    "face": {"keys": ("stepdown_mm", "stepover"), "faces": False, "feeds": "face", "plain": "Face"},
    "profile": {"keys": ("stepdown_mm", "side", "through_mm", "leave_mm"), "faces": False, "feeds": "finish",
                "plain": "Profile"},
    "pocket": {"keys": ("stepdown_mm", "stepover", "leave_mm"), "faces": True, "feeds": "rough", "plain": "Pocket"},
    "adaptive": {"keys": ("stepdown_mm", "stepover", "leave_mm"), "faces": True, "feeds": "rough",
                 "plain": "Adaptive clear"},
    "drill": {"keys": ("peck_mm", "through_mm"), "faces": True, "feeds": "drill", "plain": "Drill"},
}
OP_COMMON_KEYS = ("op", "tool", "faces", "feed", "speed", "plunge_mm_min", "coolant", "name")
#: Milling tools each operation takes: a drill drills, and nothing else does.
_TOOLS_FOR = {"drill": ("drill",)}
_MILLING = ("flat", "ball", "bull")

JOB_KEYS = ("name", "machine", "material", "stock", "tools", "setups", "tolerance_mm", "coolant")
MACHINE_KEYS = ("post", "name", "travel_mm", "min_rpm", "max_rpm", "max_feed_mm_min", "rapid_mm_min",
                "work_offset")
MATERIAL_KEYS = ("name", "surface_m_min", "chipload_mm", "drill_mm_per_rev", "stepdown_fraction")
STOCK_KEYS = ("margin_mm",)
SETUP_KEYS = ("id", "orientation", "origin", "operations", "clearance_mm", "retract_mm")
#: The rapid rate a job that names none is timed at (mm/min), listed as assumed.
RAPID_MM_MIN = 3000.0
MAX_STOCK_MM = 10_000.0


@dataclass(frozen=True)
class Machine:
    post: str
    name: str = ""
    travel_mm: tuple[float, float, float] | None = None
    min_rpm: float | None = None
    max_rpm: float | None = None
    max_feed_mm_min: float | None = None
    rapid_mm_min: float = RAPID_MM_MIN
    work_offset: str = "G54"


@dataclass(frozen=True)
class Material:
    name: str
    plain: str
    #: Whether ``name`` is a row of the feeds table (its numbers stand unless overridden below).
    table: bool
    surface_m_min: float | None = None
    chipload_mm: float | None = None
    drill_mm_per_rev: float | None = None
    stepdown_fraction: float | None = None


@dataclass(frozen=True)
class Stock:
    """A box around the part: the part's bounding box grown by ``margin_mm`` (x and y each side, and over the top);
    its bottom is the part's, where the part sits on the table."""

    margin_mm: tuple[float, float, float]


@dataclass(frozen=True)
class Operation:
    #: The operation's place in the whole job, from 0: the index findings and the viewer use.
    index: int
    op: str
    tool: str
    faces: tuple[str, ...]
    params: dict
    where: str

    @property
    def plain(self) -> str:
        return OPERATIONS[self.op]["plain"]


@dataclass(frozen=True)
class Setup:
    id: str
    orientation: str
    origin: str
    operations: tuple[Operation, ...]
    clearance_mm: float
    retract_mm: float


@dataclass(frozen=True)
class Job:
    name: str
    machine: Machine
    material: Material
    stock: Stock
    tools: dict[str, Tool]
    setups: tuple[Setup, ...]
    tolerance_mm: float
    coolant: str
    #: What the plan took that the job does not state: ``{"key", "value", "why"}``.
    assumed: tuple[dict, ...] = ()


def load_job(job: str | dict | None) -> tuple[dict, Path | None]:
    """The job as a fresh dict (a JSON round trip), and the file it came from (None for inline JSON or a dict)."""
    if job is None:
        raise CamJobError("a plan needs a job: --job job.json, or the job as inline JSON")
    if isinstance(job, dict):
        try:
            return json.loads(json.dumps(job, allow_nan=False)), None
        except (TypeError, ValueError) as exc:
            raise CamJobError(f"the job must be plain JSON data (numbers, text, lists and objects): {exc}") from None
    text = str(job).strip()
    path = None
    if not text.startswith("{"):
        path = Path(text)
        if not path.is_file():
            raise CamJobError(f"no job file at {text}; pass a JSON file or the job as inline JSON")
        text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text, parse_constant=_refuse_constant)
    except ValueError as exc:
        raise CamJobError(f"the job is not JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise CamJobError("the job must be a JSON object: {\"machine\": ..., \"material\": ..., ...}")
    return raw, path


def _refuse_constant(name: str):
    raise ValueError(f"{name} is not a number")


def parse_job(job: str | dict | None) -> Job:
    raw, path = load_job(job)
    check_keys(raw, JOB_KEYS, "the job")
    for key in ("machine", "material", "stock", "tools", "setups"):
        if key not in raw:
            raise CamJobError(f"the job needs \"{key}\"; its keys are {', '.join(JOB_KEYS)}")
    machine, assumed = _machine(raw["machine"])
    material = _material(raw["material"])
    if not isinstance(raw["tools"], list) or not raw["tools"]:
        raise CamJobError(f"tools must be a list of at least one tool, like [{EXAMPLE}]")
    tools: dict[str, Tool] = {}
    for position, entry in enumerate(raw["tools"]):
        tool = parse_tool(entry, position)
        if tool.id in tools:
            raise CamJobError(f"tools[{position}]: a second tool is called {shown(tool.id)}; each id names one tool")
        tools[tool.id] = tool
    numbers: dict[int, str] = {}
    for tool in tools.values():
        if tool.number in numbers:
            raise CamJobError(f"tools: {numbers[tool.number]} and {tool.id} are both T{tool.number}, so a tool change "
                              "loads one for the other; give one a \"number\" of its own")
        numbers[tool.number] = tool.id
    coolant = choice(raw.get("coolant", "off"), COOLANTS, "coolant")
    if not isinstance(raw["setups"], list) or not raw["setups"]:
        raise CamJobError("setups must be a list of at least one setup, like [{\"id\": \"top\", \"operations\": "
                          "[...]}]")
    setups, index = [], 0
    for position, entry in enumerate(raw["setups"]):
        setup = _setup(entry, position, tools, coolant, index)
        if any(s.id == setup.id for s in setups):
            raise CamJobError(f"setups[{position}]: a second setup is called {shown(setup.id)}; each id names one")
        setups.append(setup)
        index += len(setup.operations)
    name = raw.get("name", path.stem if path else "job")
    if not isinstance(name, str) or not name.strip():
        raise CamJobError("name must be text: the job's name, for the posted files' headers")
    return Job(name=name.strip(), machine=machine, material=material, stock=_stock(raw["stock"]), tools=tools,
               setups=tuple(setups), tolerance_mm=read_number(raw, "tolerance_mm", "the job", default=0.01,
                                                              minimum=0.01, maximum=1.0),
               coolant=coolant, assumed=tuple(assumed))


def _machine(raw: object) -> tuple[Machine, list[dict]]:
    if not isinstance(raw, dict):
        raise CamJobError("machine must be an object like {\"post\": \"grbl\", \"max_rpm\": 24000}")
    check_keys(raw, MACHINE_KEYS, "machine")
    if "post" not in raw:
        raise CamJobError("machine.post is required: the controller's dialect (one of " + ", ".join(POSTS) + "). A "
                          "dialect read by the wrong controller moves the machine wrongly, so ask which controller "
                          "runs the machine")
    post = choice(raw["post"], tuple(POSTS), "machine.post")
    if "max_rpm" not in raw:
        raise CamJobError("machine.max_rpm is required: the spindle's top speed, which every operation's speed is "
                          "held to. A small cutter's table speed is past most spindles', so ask what this one turns")
    travel = raw.get("travel_mm")
    machine = Machine(
        post=post, name=str(raw.get("name", "")),
        travel_mm=None if travel is None else number_list(travel, "machine.travel_mm", length=3, positive=True),
        min_rpm=read_number(raw, "min_rpm", "machine"), max_rpm=read_number(raw, "max_rpm", "machine"),
        max_feed_mm_min=read_number(raw, "max_feed_mm_min", "machine"),
        rapid_mm_min=read_number(raw, "rapid_mm_min", "machine", default=RAPID_MM_MIN),
        work_offset=choice(raw.get("work_offset", "G54"), WORK_OFFSETS, "machine.work_offset"))
    if machine.min_rpm is not None and machine.max_rpm is not None and machine.min_rpm > machine.max_rpm:
        raise CamJobError("machine.min_rpm is more than machine.max_rpm")
    assumed = [] if "rapid_mm_min" in raw else [
        {"key": "machine.rapid_mm_min", "value": RAPID_MM_MIN, "why": "for the cycle time only"}]
    return machine, assumed


def _material(raw: object) -> Material:
    if isinstance(raw, str):
        raw = {"name": raw}
    if not isinstance(raw, dict):
        raise CamJobError("material must be a feeds-table name (" + ", ".join(MATERIALS) + ") or an object")
    check_keys(raw, MATERIAL_KEYS, "material")
    name = raw.get("name")
    if name is not None and not isinstance(name, str):
        raise CamJobError("material.name must be text")
    name = MATERIAL_ALIASES.get(name, name) if name else None
    table = name in MATERIALS
    if name is not None and not table and not ("surface_m_min" in raw and "chipload_mm" in raw):
        raise CamJobError(f"material {shown(name)} is not in the feeds table ({', '.join(MATERIALS)}); name one, "
                          "or give its surface_m_min and chipload_mm from the tool maker's chart")
    if name is None and not ("surface_m_min" in raw and "chipload_mm" in raw):
        raise CamJobError("material needs a name from the feeds table, or surface_m_min and chipload_mm")
    numbers = {key: read_number(raw, key, "material") for key in MATERIAL_KEYS[1:]}
    plain = MATERIALS[name]["plain"] if table else (name or "the job's material")
    return Material(name=name or "custom", plain=plain, table=table, **numbers)


def _stock(raw: object) -> Stock:
    if not isinstance(raw, dict):
        raise CamJobError("stock must be an object like {\"margin_mm\": [2, 2, 1]}: the part's box grown by x and y "
                          "each side and by the third over the top")
    check_keys(raw, STOCK_KEYS, "stock")
    margin = raw.get("margin_mm", 0.0)
    if is_number(margin):
        margin = [margin] * 3
    values = number_list(margin, "stock.margin_mm", length=3)
    if any(v < 0 or v > MAX_STOCK_MM for v in values):
        raise CamJobError(f"stock.margin_mm must hold numbers from 0 to {MAX_STOCK_MM:g}, not {shown(margin)}")
    return Stock(margin_mm=values)


def _setup(raw: object, position: int, tools: dict[str, Tool], coolant: str, start: int) -> Setup:
    where = f"setups[{position}]"
    if not isinstance(raw, dict):
        raise CamJobError(f"{where} must be an object like {{\"id\": \"top\", \"operations\": [...]}}")
    check_keys(raw, SETUP_KEYS, where)
    setup_id = raw.get("id", f"setup{position + 1}")
    if not isinstance(setup_id, str) or not setup_id.strip() or not all(c.isalnum() or c in "-_" for c in setup_id):
        raise CamJobError(f"{where}.id must be a short name of letters, digits, - and _ (it names the posted file), "
                          f"not {shown(setup_id)}")
    operations = raw.get("operations")
    if not isinstance(operations, list) or not operations:
        raise CamJobError(f"{where} needs \"operations\": a list of at least one, like [{{\"op\": \"face\", "
                          "\"tool\": \"T1\"}]")
    clearance = read_number(raw, "clearance_mm", where, default=5.0)
    retract = read_number(raw, "retract_mm", where, default=2.0)
    if retract > clearance:
        raise CamJobError(f"{where}: retract_mm ({retract:g}) must not be more than clearance_mm ({clearance:g})")
    return Setup(id=setup_id, orientation=choice(raw.get("orientation", "+Z"), ORIENTATIONS, f"{where}.orientation"),
                 origin=choice(raw.get("origin", "stock-top-center"), ORIGINS, f"{where}.origin"),
                 operations=tuple(_operation(entry, f"{where}.operations[{k}]", tools, coolant, start + k)
                                  for k, entry in enumerate(operations)),
                 clearance_mm=clearance, retract_mm=retract)


def _operation(raw: object, where: str, tools: dict[str, Tool], coolant: str, index: int) -> Operation:
    if not isinstance(raw, dict):
        raise CamJobError(f"{where} must be an object like {{\"op\": \"pocket\", \"tool\": \"T1\", \"faces\": "
                          "[\"part/face 9\"]}")
    kind = choice(raw.get("op"), tuple(OPERATIONS), f"{where}.op")
    spec = OPERATIONS[kind]
    check_keys(raw, (*OP_COMMON_KEYS, *spec["keys"]), where, hint=f"a {kind} operation")
    tool_id = raw.get("tool")
    if tool_id not in tools:
        raise CamJobError(f"{where}.tool is {shown(tool_id)}; name one of the job's tools: {', '.join(tools)}")
    allowed = _TOOLS_FOR.get(kind, _MILLING)
    if tools[tool_id].type not in allowed:
        raise CamJobError(f"{where}: {kind} takes a {' or '.join(allowed)} tool, and {tool_id} is a "
                          f"{tools[tool_id].type}")
    faces = raw.get("faces", [])
    if not isinstance(faces, list) or not all(isinstance(f, str) and f.strip() for f in faces):
        raise CamJobError(f"{where}.faces must be a list of face references as cadgen cam features lists them, like "
                          "[\"part/face 9\"]")
    if spec["faces"] and not faces:
        raise CamJobError(f"{where}: {kind} needs \"faces\": " + (
            "the hole walls to drill" if kind == "drill" else "the floors to clear down to") + " (cadgen cam features "
                          "lists them)")
    tool = tools[tool_id]
    params: dict = {
        "feed": read_number(raw, "feed", where), "speed": read_number(raw, "speed", where),
        "plunge_mm_min": read_number(raw, "plunge_mm_min", where),
        "coolant": choice(raw.get("coolant", coolant), COOLANTS, f"{where}.coolant"),
    }
    if "leave_mm" in spec["keys"]:
        params["leave_mm"] = read_number(raw, "leave_mm", where, default=0.0, minimum=0.0, maximum=tool.diameter_mm)
    if kind != "drill":
        params["stepdown_mm"] = read_number(raw, "stepdown_mm", where, maximum=tool.flute_length_mm)
    if "stepover" in spec["keys"]:
        params["stepover"] = read_number(raw, "stepover", where, default=0.4, maximum=1.0)
        if kind == "adaptive" and "stepover" not in raw:
            params["stepover"] = 0.15
    if kind == "profile":
        params["side"] = choice(raw.get("side", "outside"), ("outside", "inside"), f"{where}.side")
    if kind in ("profile", "drill"):
        params["through_mm"] = read_number(raw, "through_mm", where, default=1.0 if kind == "drill" else 0.0,
                                           minimum=0.0, maximum=tool.diameter_mm * 2)
    if kind == "drill":
        params["peck_mm"] = read_number(raw, "peck_mm", where)
    name = raw.get("name")
    if name is not None and not isinstance(name, str):
        raise CamJobError(f"{where}.name must be text")
    params["name"] = name
    return Operation(index=index, op=kind, tool=tool_id, faces=tuple(f.strip() for f in faces), params=params,
                     where=where)
