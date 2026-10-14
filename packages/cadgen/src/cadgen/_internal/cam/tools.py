"""Tools: the closed tool vocabulary, each tool's cutter profile, and its holder.

A tool is a frozen :class:`Tool` parsed from one entry of the job's ``tools`` list (:func:`parse_tool`). Its
geometry is a cutter profile about the tool axis, measured from the tip:

* :meth:`Tool.radius_at` ``(h)``: the cutting radius at height ``h`` mm above the tip (flutes only).
* :meth:`Tool.height_at` ``(d)``: the height of the cutter's lower surface at radial distance ``d`` from the axis
  (``inf`` beyond the radius), vectorised over numpy arrays. Drop-cutter and the stock simulators stamp with it.
* :attr:`Tool.holder`: the shank and holder above the flutes, for the reach and collision checks.

Families: ``mill`` (flat, face_mill, ball, bull, vee, chamfer, drill, spot, tap, reamer, boring, counterbore,
thread_mill, slot, engraver), ``lathe`` (turn, groove, thread, partoff) and ``cutting`` (beam, wire). A lathe tool's
profile is its nose radius (for the radial simulator); a beam's or a wire's is half its kerf or diameter. Each family
takes only the keys its tools are read by (:data:`FAMILY_KEYS`): a beam has no flutes, a lathe insert no holder.

What a job leaves out is filled in here, and only here:

* ``flute_length_mm``: a catalogue tool's (an end mill's three diameters, a drill's ten, a face mill's quarter
  diameter, a counterbore's pilot plus two diameters), cut back to a stated ``stickout_mm``: a stated stickout always
  wins over a defaulted flute length (a 10 mm cutter stated 25 mm out of its holder has 25 mm of flutes, not 30).
* ``stickout_mm``: the flutes and a quarter more (at least 5 mm more).
* ``shank_diameter_mm``: the diameter; 3 mm for a flat, ball, bull, thread mill or engraver under 3 mm (small
  cutters sit on a bigger shank, and a check that assumed a 1 mm shank would pass tools that cannot fit).
* a holder only when the job states both ``holder_diameter_mm`` and ``holder_length_mm`` (one alone is refused:
  a holder of a guessed length is a collision check of a guessed holder).
* a counterbore's pilot (``pilot_diameter_mm``) is as long as it is wide.

Stdlib at import; numpy inside :meth:`Tool.height_at` when it is handed an array.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from cadgen._internal.cam.job_errors import CamJobError, check_keys, choice, read_number, shown

__all__ = ["FAMILY_KEYS", "Holder", "TOOL_TYPES", "Tool", "parse_tool"]

#: Every tool type: its family and the keys only it takes (beyond :data:`COMMON_KEYS`). A required key is listed in
#: ``required``; the rest have defaults (:func:`parse_tool`).
TOOL_TYPES: dict[str, dict] = {
    "flat": {"family": "mill", "keys": (), "required": ("diameter_mm",), "plain": "flat"},
    "face_mill": {"family": "mill", "keys": (), "required": ("diameter_mm",), "plain": "face mill"},
    "ball": {"family": "mill", "keys": (), "required": ("diameter_mm",), "plain": "ball"},
    "bull": {"family": "mill", "keys": ("corner_radius_mm",), "required": ("diameter_mm", "corner_radius_mm"),
             "plain": "bull nose"},
    "vee": {"family": "mill", "keys": ("angle_deg", "tip_diameter_mm"), "required": ("diameter_mm", "angle_deg"),
            "plain": "vee"},
    "chamfer": {"family": "mill", "keys": ("angle_deg", "tip_diameter_mm"), "required": ("diameter_mm",),
                "plain": "chamfer mill"},
    "drill": {"family": "mill", "keys": ("point_angle",), "required": ("diameter_mm",), "plain": "drill"},
    "spot": {"family": "mill", "keys": ("angle_deg",), "required": ("diameter_mm",), "plain": "spot drill"},
    "tap": {"family": "mill", "keys": ("pitch_mm", "hand"), "required": ("diameter_mm", "pitch_mm"), "plain": "tap"},
    "reamer": {"family": "mill", "keys": (), "required": ("diameter_mm",), "plain": "reamer"},
    "boring": {"family": "mill", "keys": (), "required": ("diameter_mm",), "plain": "boring bar"},
    "counterbore": {"family": "mill", "keys": ("pilot_diameter_mm",), "required": ("diameter_mm",),
                    "plain": "counterbore"},
    "thread_mill": {"family": "mill", "keys": ("pitch_mm",), "required": ("diameter_mm", "pitch_mm"),
                    "plain": "thread mill"},
    "slot": {"family": "mill", "keys": ("width_mm",), "required": ("diameter_mm", "width_mm"), "plain": "slot cutter"},
    "engraver": {"family": "mill", "keys": ("angle_deg", "tip_diameter_mm"), "required": ("diameter_mm",),
                 "plain": "engraver"},
    "turn": {"family": "lathe", "keys": ("insert", "nose_radius_mm", "side"), "required": (), "plain": "turning tool"},
    "groove": {"family": "lathe", "keys": ("width_mm", "nose_radius_mm", "side"), "required": ("width_mm",),
               "plain": "grooving tool"},
    "thread": {"family": "lathe", "keys": ("pitch_mm", "side"), "required": ("pitch_mm",), "plain": "threading tool"},
    "partoff": {"family": "lathe", "keys": ("width_mm",), "required": ("width_mm",), "plain": "part-off blade"},
    "beam": {"family": "cutting", "keys": ("kerf_mm",), "required": ("kerf_mm",), "plain": "beam"},
    "wire": {"family": "cutting", "keys": ("diameter_mm",), "required": ("diameter_mm",), "plain": "wire"},
}

#: The keys every tool of a family may carry, beyond its type's own. ``number`` is the T number posted (default: the
#: digits of ``id``, else its position). A milling tool has flutes, a shank and a holder; a lathe tool has its tool
#: material (HSS turns slower) and a bar's diameter (a boring bar's reach); a beam or a wire has neither.
FAMILY_KEYS = {
    "mill": ("id", "type", "number", "name", "diameter_mm", "flutes", "flute_length_mm", "stickout_mm",
             "holder_diameter_mm", "holder_length_mm", "shank_diameter_mm", "material"),
    "lathe": ("id", "type", "number", "name", "diameter_mm", "material"),
    "cutting": ("id", "type", "number", "name"),
}
#: Every key any tool takes.
COMMON_KEYS = FAMILY_KEYS["mill"]
TOOL_MATERIALS = ("carbide", "hss")
#: A cutter under this diameter sits on a shank this wide unless the job states one (mm), for these types.
SMALL_SHANK_MM = 3.0
SMALL_SHANK_TYPES = ("flat", "ball", "bull", "thread_mill", "engraver")
#: A tool's lengths are refused past these (mm): beyond them a number is a units slip, and a 0.000001 mm cutter would
#: plan millions of passes. The highest T number a controller takes.
MIN_TOOL_MM = 0.01
MAX_TOOL_MM = 1000.0
MAX_TOOL_NUMBER = 9999
TOOL_LENGTHS = ("diameter_mm", "flute_length_mm", "stickout_mm", "holder_diameter_mm", "holder_length_mm",
                "shank_diameter_mm", "corner_radius_mm", "tip_diameter_mm", "pitch_mm", "width_mm", "nose_radius_mm",
                "kerf_mm", "pilot_diameter_mm")
INSERTS = ("C", "D", "V", "W")
SIDES = ("left", "right", "neutral")


@dataclass(frozen=True)
class Holder:
    """The non-cutting part above the flutes: a shank to ``stickout_mm`` above the tip, then a holder cylinder."""

    shank_diameter_mm: float
    stickout_mm: float
    holder_diameter_mm: float | None
    holder_length_mm: float


@dataclass(frozen=True)
class Tool:
    id: str
    type: str
    number: int
    diameter_mm: float = 0.0
    flutes: int = 2
    flute_length_mm: float = 0.0
    stickout_mm: float = 0.0
    holder_diameter_mm: float | None = None
    holder_length_mm: float = 40.0
    shank_diameter_mm: float = 0.0
    material: str = "carbide"
    name: str = ""
    corner_radius_mm: float = 0.0
    #: Included angle of a vee, chamfer, spot or engraver (degrees).
    angle_deg: float = 0.0
    tip_diameter_mm: float = 0.0
    point_angle: float = 118.0
    pitch_mm: float = 0.0
    width_mm: float = 0.0
    insert: str = ""
    nose_radius_mm: float = 0.0
    side: str = ""
    kerf_mm: float = 0.0
    #: A tap's hand: ``right`` (the default, posted G84) or ``left`` (G74, spindle reversed).
    hand: str = ""
    #: A counterbore's pilot (0: none, a flat-bottomed counterbore); the pilot is as long as it is wide.
    pilot_diameter_mm: float = 0.0
    #: What the job left to the defaults above that a plan rests on: the lengths (``flute_length_mm``,
    #: ``stickout_mm``, and ``shank_diameter_mm`` where it differs from the diameter), a milling cutter's ``flutes``
    #: and a hole maker's ``material``. The plan lists each as assumed, and ``reach`` and ``holder_collision`` do not
    #: judge a cut past an assumed length (they say ``not_judged``).
    assumed: tuple[str, ...] = ()

    @property
    def family(self) -> str:
        return TOOL_TYPES[self.type]["family"]

    @property
    def radius(self) -> float:
        """The cutting radius (half the kerf for a beam)."""
        if self.type == "beam":
            return self.kerf_mm / 2.0
        return self.diameter_mm / 2.0

    @property
    def plain(self) -> str:
        """The viewer's words for it: ``6 mm flat``, ``90° vee``, ``M6x1 tap``, ``0.2 mm beam``."""
        word = TOOL_TYPES[self.type]["plain"]
        if self.type in ("vee", "engraver") and self.angle_deg:
            return f"{_num(self.angle_deg)}° {word}"
        if self.type == "tap":
            return f"M{_num(self.diameter_mm)}x{_num(self.pitch_mm)}{' LH' if self.hand == 'left' else ''} tap"
        if self.type == "beam":
            return f"{_num(self.kerf_mm)} mm kerf beam"
        if self.type in ("groove", "partoff"):
            return f"{_num(self.width_mm)} mm {word}"
        if self.family == "lathe":
            return word if not self.insert else f"{self.insert} insert {word}"
        if self.type == "bull":
            return f"{_num(self.diameter_mm)} mm R{_num(self.corner_radius_mm)} bull nose"
        return f"{_num(self.diameter_mm)} mm {word}"

    @property
    def holder(self) -> Holder:
        return Holder(self.shank_diameter_mm or self.diameter_mm, self.stickout_mm, self.holder_diameter_mm,
                      self.holder_length_mm)

    def _half_angle(self) -> float:
        angle = self.angle_deg or (self.point_angle if self.type == "drill" else 90.0)
        return math.radians(angle / 2.0)

    def radius_at(self, h: float) -> float:
        """The cutting radius ``h`` mm above the tip; 0 below the tip, the full radius above the profile's top."""
        r = self.radius
        if h < 0:
            return 0.0
        kind = self.type
        if kind == "ball":
            return math.sqrt(max(0.0, r * r - (r - h) ** 2)) if h < r else r
        if kind == "bull":
            rc = min(self.corner_radius_mm, r)
            return (r - rc) + (math.sqrt(max(0.0, rc * rc - (rc - h) ** 2)) if h < rc else rc)
        if kind in ("vee", "chamfer", "engraver", "spot", "drill"):
            tip = self.tip_diameter_mm / 2.0
            return min(r, tip + h * math.tan(self._half_angle()))
        if kind == "counterbore" and h < self.pilot_diameter_mm:
            return self.pilot_diameter_mm / 2.0
        return r

    def height_at(self, d):
        """The lower surface's height above the tip at radial distance ``d`` (a float or a numpy array); ``inf``
        beyond the radius. Flat: 0. Ball: ``r - sqrt(r² - d²)``. Bull: flat to ``r - rc``, then the corner arc.
        Cone (vee, chamfer, engraver, spot, drill): ``(d - tip) / tan(half angle)``. Counterbore: 0 over the pilot,
        the pilot's length beyond it."""
        if not hasattr(d, "shape"):
            import numpy as np

            return float(self.height_at(np.asarray([d], dtype=float))[0])
        import numpy as np

        d = np.abs(np.asarray(d, dtype=float))
        r = self.radius
        kind = self.type
        out = np.full(d.shape, np.inf)
        inside = d <= r + 1e-12
        di = np.minimum(d[inside], r)
        if kind == "ball":
            out[inside] = r - np.sqrt(np.maximum(0.0, r * r - di * di))
        elif kind == "bull":
            rc = min(self.corner_radius_mm, r)
            flat = r - rc
            dd = np.maximum(0.0, di - flat)
            out[inside] = rc - np.sqrt(np.maximum(0.0, rc * rc - dd * dd))
        elif kind in ("vee", "chamfer", "engraver", "spot", "drill"):
            tip = self.tip_diameter_mm / 2.0
            out[inside] = np.maximum(0.0, di - tip) / math.tan(self._half_angle())
        elif kind == "counterbore" and self.pilot_diameter_mm > 0:
            out[inside] = np.where(di <= self.pilot_diameter_mm / 2.0 + 1e-12, 0.0, self.pilot_diameter_mm)
        else:
            out[inside] = 0.0
        return out

    def as_dict(self) -> dict:
        """The tool as the GLB's extras and the Results carry it: every set field, plus ``plain``."""
        out = {key: value for key, value in asdict(self).items() if value not in (0.0, "", None) and key != "assumed"}
        out.update({"id": self.id, "type": self.type, "number": self.number, "plain": self.plain,
                    "diameter_mm": self.diameter_mm})
        return out


def _num(value: float) -> str:
    return f"{value:g}"


#: The milling cutters whose feed rests on their flute count, and the hole makers whose speed rests on their material.
_FLUTED = ("flat", "ball", "bull", "face_mill")
_HOLE_MAKERS = ("drill", "spot", "reamer", "boring", "counterbore")


def _assumed_keys(raw: dict, kind: str, family: str, thinner_shank: bool) -> tuple[str, ...]:
    """What ``raw`` leaves to the defaults that a plan rests on (:attr:`Tool.assumed`)."""
    if family != "mill":
        return ()
    unstated = [key for key in ("flute_length_mm", "stickout_mm") if key not in raw]
    if thinner_shank and "shank_diameter_mm" not in raw:
        unstated.append("shank_diameter_mm")
    if kind in _FLUTED and "flutes" not in raw:
        unstated.append("flutes")
    if kind in _HOLE_MAKERS and "material" not in raw:
        unstated.append("material")
    return tuple(unstated)


def parse_tool(raw: object, position: int, *, where: str | None = None) -> Tool:
    """One entry of ``tools`` (or of a tool library, ``where`` naming it): closed keys per type, defaults filled in,
    teaching errors naming the allowed set."""
    where = where or f"tools[{position}]"
    if not isinstance(raw, dict):
        raise CamJobError(f"{where} must be an object like {{\"id\": \"T1\", \"type\": \"flat\", \"diameter_mm\": 6}}")
    kind = choice(raw.get("type"), tuple(TOOL_TYPES), f"{where}.type")
    spec = TOOL_TYPES[kind]
    family = spec["family"]
    check_keys(raw, tuple(dict.fromkeys((*FAMILY_KEYS[family], *spec["keys"]))), where,
               hint=f"a {kind} tool" + {"lathe": " (a lathe tool has no flutes, shank or holder)",
                                        "cutting": " (a beam or a wire has no flutes, holder or tool material)"}.get(
                   family, ""))
    tool_id = raw.get("id")
    if not isinstance(tool_id, str) or not tool_id.strip():
        raise CamJobError(f"{where} needs an \"id\" (a short name the operations use, like \"T1\")")
    if tool_id != tool_id.strip():
        raise CamJobError(f"{where}.id {shown(tool_id)} has space around it (the operations name it exactly); write "
                          f"{shown(tool_id.strip())}")
    if len(tool_id) > 40 or not tool_id.isprintable():
        raise CamJobError(f"{where}.id must be a short name (40 characters at most, no line breaks) like \"T1\", "
                          f"not {tool_id[:20]!r}...")
    for key in spec["required"]:
        if key not in raw:
            raise CamJobError(f"{where} ({tool_id}, a {kind} tool) needs \"{key}\"")
    digits = "".join(ch for ch in tool_id if ch.isdigit())
    t_number = raw.get("number")
    if t_number is None:
        t_number = int(digits) if digits else position + 1
    elif isinstance(t_number, bool) or not isinstance(t_number, int) or t_number < 0:
        raise CamJobError(f"{where}.number must be a whole number, 0 or more (the T number posted)")
    if t_number > MAX_TOOL_NUMBER:
        raise CamJobError(f"{where} posts as T{str(t_number)[:12]}{'...' if len(str(t_number)) > 12 else ''}; a "
                          f"controller's tool numbers stop at {MAX_TOOL_NUMBER}: give it a \"number\" up to "
                          f"{MAX_TOOL_NUMBER}")
    diameter = read_number(raw, "diameter_mm", where, default=0.0)
    if spec["family"] == "mill" and diameter <= 0:
        raise CamJobError(f"{where}.diameter_mm must be more than 0")
    flutes = raw.get("flutes", 1 if kind in ("vee", "engraver", "spot", "boring", "reamer") else
                     4 if kind == "face_mill" else 2)
    if isinstance(flutes, bool) or not isinstance(flutes, int) or not 1 <= flutes <= 100:
        raise CamJobError(f"{where}.flutes must be a whole number from 1 to 100")
    pilot = read_number(raw, "pilot_diameter_mm", where, default=0.0)
    if pilot and pilot >= diameter:
        raise CamJobError(f"{where}: pilot_diameter_mm must be less than diameter_mm (the pilot leads the "
                          f"{diameter:g} mm cutter into its hole)")
    # Defaults from catalogue tools: a jobber drill's flutes run about ten diameters, a reamer's six, a spot
    # drill's one, an inserted face mill's a quarter (its inserts' height); an end mill's about three. A
    # counterbore's flutes start above its pilot, which is as long as it is wide.
    flute_factor = {"drill": 10.0, "reamer": 6.0, "spot": 1.0, "tap": 3.0, "boring": 4.0, "face_mill": 0.25,
                    "counterbore": 2.0}.get(kind, 3.0)
    flute_default = max(flute_factor * diameter + pilot, 1.0)
    stated_stickout = read_number(raw, "stickout_mm", where)
    if stated_stickout is not None and "flute_length_mm" not in raw:
        if pilot and stated_stickout <= pilot:
            raise CamJobError(f"{where}.stickout_mm: {stated_stickout:g} mm out of the holder does not reach past its "
                              f"{pilot:g} mm pilot to the cutter; state a longer stickout")
        flute_default = min(flute_default, stated_stickout)   # a stated stickout wins over a defaulted flute length
    flute_length = read_number(raw, "flute_length_mm", where, default=flute_default)
    stickout = stated_stickout if stated_stickout is not None else max(flute_length * 1.25, flute_length + 5.0)
    if stickout < flute_length:
        raise CamJobError(f"{where}: stickout_mm ({stickout:g}) is shorter than flute_length_mm ({flute_length:g}); "
                          "the stickout is the length out of the holder, flutes included")
    holder_given = [key for key in ("holder_diameter_mm", "holder_length_mm") if key in raw]
    if len(holder_given) == 1:
        missing = "holder_length_mm" if holder_given[0] == "holder_diameter_mm" else "holder_diameter_mm"
        raise CamJobError(f"{where} ({tool_id}) states {holder_given[0]} and so needs \"{missing}\": the holder is "
                          "checked for collisions as a cylinder of both, and a guessed one is a guessed check")
    shank_default = SMALL_SHANK_MM if kind in SMALL_SHANK_TYPES and diameter < SMALL_SHANK_MM else diameter
    angle_default = {"chamfer": 90.0, "spot": 90.0, "engraver": 30.0}.get(kind, 0.0)
    tool = Tool(
        id=tool_id, type=kind, number=t_number, diameter_mm=diameter, flutes=flutes,
        flute_length_mm=flute_length, stickout_mm=stickout,
        holder_diameter_mm=read_number(raw, "holder_diameter_mm", where, default=None),
        holder_length_mm=read_number(raw, "holder_length_mm", where, default=40.0),
        shank_diameter_mm=read_number(raw, "shank_diameter_mm", where, default=shank_default),
        material=choice(raw.get("material", "carbide"), TOOL_MATERIALS, f"{where}.material"),
        name=str(raw.get("name", "")),
        corner_radius_mm=read_number(raw, "corner_radius_mm", where, default=0.0),
        angle_deg=read_number(raw, "angle_deg", where, default=angle_default),
        tip_diameter_mm=read_number(raw, "tip_diameter_mm", where, default=0.0, minimum=0.0),
        point_angle=read_number(raw, "point_angle", where, default=118.0),
        pitch_mm=read_number(raw, "pitch_mm", where, default=0.0),
        width_mm=read_number(raw, "width_mm", where, default=0.0),
        insert=choice(raw["insert"], INSERTS, f"{where}.insert") if "insert" in raw else "",
        nose_radius_mm=read_number(raw, "nose_radius_mm", where, default=0.4 if kind == "turn" else 0.0, minimum=0.0),
        side=choice(raw["side"], SIDES, f"{where}.side") if "side" in raw else "",
        kerf_mm=read_number(raw, "kerf_mm", where, default=0.0),
        hand=choice(raw["hand"], ("right", "left"), f"{where}.hand") if "hand" in raw else "",
        pilot_diameter_mm=pilot,
        assumed=_assumed_keys(raw, kind, family, shank_default != diameter),
    )
    for key in TOOL_LENGTHS:
        value = getattr(tool, key)
        if value is not None and value > MAX_TOOL_MM:
            raise CamJobError(f"{where}.{key} is {value:g} mm; no cutter is over {MAX_TOOL_MM:g} mm: check the units "
                              "(every length in a job is mm)")
    for key in ("diameter_mm", "kerf_mm", "width_mm", "pitch_mm", "pilot_diameter_mm"):
        value = getattr(tool, key)
        if 0 < value < MIN_TOOL_MM:
            raise CamJobError(f"{where}.{key} is {value:g} mm; no cutter is under {MIN_TOOL_MM:g} mm (the finest "
                              "micro tools and EDM wires are 0.02 mm): check the units (every length in a job is mm)")
    if kind == "bull" and tool.corner_radius_mm > tool.radius:
        raise CamJobError(f"{where}: corner_radius_mm ({tool.corner_radius_mm:g}) is more than the tool's radius")
    if kind in ("vee", "chamfer", "engraver", "spot") and not 0 < tool.angle_deg < 180:
        raise CamJobError(f"{where}.angle_deg is the included angle and must be between 0 and 180")
    if kind == "drill" and not 60 <= tool.point_angle <= 180:
        raise CamJobError(f"{where}.point_angle must be between 60 and 180 degrees (118 or 135 for most drills)")
    if tool.tip_diameter_mm >= max(tool.diameter_mm, 1e-9) and kind in ("vee", "chamfer", "engraver"):
        raise CamJobError(f"{where}: tip_diameter_mm must be less than diameter_mm")
    if pilot and tool.flute_length_mm <= pilot:
        raise CamJobError(f"{where}.flute_length_mm ({tool.flute_length_mm:g}) must reach past the {pilot:g} mm pilot "
                          "(it is measured from the tip, the pilot included)")
    return tool
