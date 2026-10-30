"""Tools: the closed tool vocabulary a job's ``tools`` list is read in (:func:`parse_tool`).

A tool is one of FreeCAD's built-in tool bit shapes (``freecad_job.SHAPES``): ``flat``, ``ball``, ``bull`` or ``drill``.
Nothing about a tool is guessed (law 10): the T number the program loads it by, its diameter, its flute length (every
cut is held to it) and its stickout (FreeCAD's model of the tool); a milling tool's flutes (its feed is worked out from
them) and shank diameter (FreeCAD's model again); a bull nose's corner radius and a drill's point angle (how far past
a through hole's bottom it drills) are required, and a tool without one is refused. A key that means nothing for a
tool's type is no key of it.

Stdlib only.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from cadgen._internal.cam.job_errors import CamJobError, check_keys, choice, read_number, shown

__all__ = ["TOOL_KEYS", "TOOL_TYPES", "Tool", "parse_tool"]

#: Each tool type: the keys only it takes, every one required, and its plain name. A drill is fed per revolution and
#: FreeCAD models it with no shank of its own: it takes no flutes and no shank diameter.
TOOL_TYPES: dict[str, dict] = {
    "flat": {"keys": ("flutes", "shank_diameter_mm"), "plain": "flat"},
    "ball": {"keys": ("flutes", "shank_diameter_mm"), "plain": "ball"},
    "bull": {"keys": ("flutes", "shank_diameter_mm", "corner_radius_mm"), "plain": "bull nose"},
    "drill": {"keys": ("point_angle",), "plain": "drill"},
}
#: The keys every tool takes. ``number`` is the T number posted.
TOOL_KEYS = ("id", "type", "number", "name", "diameter_mm", "flute_length_mm", "stickout_mm")
#: Past these a length is a units slip (mm); the highest T number a controller takes.
MIN_TOOL_MM = 0.01
MAX_TOOL_MM = 1000.0
MAX_TOOL_NUMBER = 9999
#: A tool as a job gives one, for the refusals.
EXAMPLE = ('{"id": "T1", "type": "flat", "number": 1, "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20, '
           '"stickout_mm": 30, "shank_diameter_mm": 6}')
#: What every tool must state, beyond its type's own keys.
_REQUIRED = ("number", "diameter_mm", "flute_length_mm", "stickout_mm")
#: What each required key is for, in the refusal of a tool without it.
_WHY = {
    "number": "the T number the program loads it by, as the machine's tool table has it",
    "diameter_mm": "its cutting diameter",
    "flute_length_mm": "how long its cutting edge is, which every cut's depth is held to",
    "stickout_mm": "how far it stands out of its holder, flutes included, as FreeCAD models the tool",
    "shank_diameter_mm": "the diameter of its shank, as FreeCAD models the tool",
    "flutes": "how many cutting edges it has, which its feed is worked out from",
    "corner_radius_mm": "its corner radius, which its cut's profile is",
    "point_angle": "its point's included angle, which sets how far past a through hole's bottom it drills",
}


@dataclass(frozen=True)
class Tool:
    id: str
    type: str
    number: int
    diameter_mm: float
    #: None for a drill, which is fed per revolution.
    flutes: int | None
    flute_length_mm: float
    stickout_mm: float
    #: A milling tool's; None for a drill.
    shank_diameter_mm: float | None
    name: str = ""
    #: A bull nose's; 0 for any other.
    corner_radius_mm: float = 0.0
    #: A drill's; None for any other.
    point_angle: float | None = None

    @property
    def radius(self) -> float:
        return self.diameter_mm / 2.0

    @property
    def plain(self) -> str:
        """The viewer's words for it: ``6 mm flat``, ``6 mm R1 bull nose``."""
        if self.type == "bull":
            return f"{self.diameter_mm:g} mm R{self.corner_radius_mm:g} bull nose"
        return f"{self.diameter_mm:g} mm {TOOL_TYPES[self.type]['plain']}"

    @property
    def tip_length_mm(self) -> float:
        """How far a drill's point reaches past its full diameter."""
        if self.point_angle is None:            # no drill
            return 0.0
        return self.radius / math.tan(math.radians(self.point_angle / 2.0))

    def as_dict(self) -> dict:
        """The tool as the GLB's extras and the Results carry it, with ``plain``."""
        out = asdict(self)
        out["plain"] = self.plain
        return out


def parse_tool(raw: object, position: int) -> Tool:
    """One entry of ``tools``: closed keys per type, what the tool is required, defaults filled in for the rest,
    teaching errors naming the allowed set."""
    where = f"tools[{position}]"
    if not isinstance(raw, dict):
        raise CamJobError(f"{where} must be an object like {EXAMPLE}")
    kind = choice(raw.get("type"), tuple(TOOL_TYPES), f"{where}.type")
    check_keys(raw, (*TOOL_KEYS, *TOOL_TYPES[kind]["keys"]), where, hint=f"a {kind} tool")
    tool_id = raw.get("id")
    if (not isinstance(tool_id, str) or not tool_id or len(tool_id) > 40
            or not all(c.isalnum() or c in "-_" for c in tool_id)):
        raise CamJobError(f"{where} needs an \"id\": a short name of letters, digits, - and _ the operations use, "
                          f"like \"T1\" (it names a posted file when a post takes one tool a program), not {shown(tool_id)}")
    for key in (*_REQUIRED, *TOOL_TYPES[kind]["keys"]):
        if key not in raw:
            raise CamJobError(f"{where} ({tool_id}, a {kind} tool) needs \"{key}\": {_WHY[key]}. It is never "
                              "assumed, so ask what the tool is")
    number = raw["number"]
    if isinstance(number, bool) or not isinstance(number, int) or not 0 <= number <= MAX_TOOL_NUMBER:
        raise CamJobError(f"{where}.number must be a whole number from 0 to {MAX_TOOL_NUMBER} (the T number posted)")
    diameter = read_number(raw, "diameter_mm", where, minimum=MIN_TOOL_MM)
    flutes = raw.get("flutes")
    if kind != "drill" and (isinstance(flutes, bool) or not isinstance(flutes, int) or not 1 <= flutes <= 100):
        raise CamJobError(f"{where}.flutes must be a whole number from 1 to 100")
    stickout = read_number(raw, "stickout_mm", where, minimum=MIN_TOOL_MM)
    flute_length = read_number(raw, "flute_length_mm", where, minimum=MIN_TOOL_MM)
    if stickout < flute_length:
        raise CamJobError(f"{where}: stickout_mm ({stickout:g}) is shorter than flute_length_mm ({flute_length:g}); "
                          "the stickout is the length out of the holder, flutes included")
    point_angle = read_number(raw, "point_angle", where)
    if point_angle is not None and not 60 <= point_angle <= 180:
        raise CamJobError(f"{where}.point_angle must be between 60 and 180 degrees")
    tool = Tool(
        id=tool_id, type=kind, number=number, diameter_mm=diameter, flutes=flutes, flute_length_mm=flute_length,
        stickout_mm=stickout, shank_diameter_mm=read_number(raw, "shank_diameter_mm", where, minimum=MIN_TOOL_MM),
        name=str(raw.get("name", "")),
        corner_radius_mm=read_number(raw, "corner_radius_mm", where, default=0.0, minimum=0.0),
        point_angle=point_angle,
    )
    for key in ("diameter_mm", "flute_length_mm", "stickout_mm", "shank_diameter_mm"):
        if (getattr(tool, key) or 0.0) > MAX_TOOL_MM:
            raise CamJobError(f"{where}.{key} is {getattr(tool, key):g} mm; no cutter is over {MAX_TOOL_MM:g} mm: "
                              "check the units (every length in a job is mm)")
    if kind == "bull" and not 0 < tool.corner_radius_mm <= tool.radius:
        raise CamJobError(f"{where}: a bull nose needs corner_radius_mm, more than 0 and at most its radius")
    return tool
