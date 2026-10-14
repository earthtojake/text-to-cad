"""What the cutting posts share (``plasma``, ``waterjet``, ``marlin``, and ``mach3`` on a plasma table).

:class:`CuttingPost` writes X and Y only (``machine.z_words`` adds Z where a post offers it), turns a tool change
into a comment naming the beam, refuses a spindle or coolant its machine does not have (``_iso.CheckedPost``), and
posts any drilling cycle as its expansion. A ``beam`` event is the process's own on/off (:meth:`CuttingPost.beam_on`,
:meth:`CuttingPost.beam_off`).

The torch sequence (``plasma`` and ``mach3``), with every height and code a machine key; after the work offset the
torch first goes up to ``G0 Z<safe_height_mm>`` (where it starts is unknown)::

    G0 Z<pierce_height_mm>     (torch_z)
    M3                         torch on
    G4 P<pierce>               the beam event's pierce_s, else machine.pierce_delay_s
    G1 Z<cut_height_mm> F<z_feed_mm_min>   (torch_z)
    <thc_on>                   (thc)
    ... the cut ...
    <thc_off>                  (thc)
    M5
    G0 Z<safe_height_mm>       (torch_z)
"""

from __future__ import annotations

from cadgen._internal.cam.posts._iso import CheckedPost
from cadgen._internal.cam.posts.base import Program, number

__all__ = ["CuttingPost", "TORCH_OPTIONS", "torch_off", "torch_on", "torch_safe"]

DWELL_MS = {"type": "bool", "default": False, "help": "dwell P words in milliseconds instead of seconds"}


def torch_options(thc: bool) -> dict:
    return {
        "torch_z": {"type": "bool", "default": True, "help": "write the pierce, cut and safe heights as Z moves"},
        "pierce_height_mm": {"type": "number", "default": 3.8, "help": "torch height while piercing"},
        "cut_height_mm": {"type": "number", "default": 1.5, "help": "torch height while cutting"},
        "safe_height_mm": {"type": "number", "default": 10.0, "help": "torch height for rapids"},
        "z_feed_mm_min": {"type": "number", "default": 1000.0, "minimum": 1.0,
                          "help": "feed from pierce height down to cut height"},
        "pierce_delay_s": {"type": "number", "default": 0.5,
                           "help": "pierce dwell when the operation gives none"},
        "thc": {"type": "bool", "default": thc, "help": "switch the torch height control on and off around each cut"},
        "thc_on": {"type": "text", "default": "M101", "help": "the controller's THC-on code"},
        "thc_off": {"type": "text", "default": "M102", "help": "the controller's THC-off code"},
        "dwell_ms": DWELL_MS,
    }


TORCH_OPTIONS = torch_options(True)


def torch_on(post, data: dict, program: Program) -> list[str]:
    z = post.option(program, "torch_z")
    pierce = float(data.get("pierce_s") or post.option(program, "pierce_delay_s"))
    lines = [f"G0 Z{post.num(post.option(program, 'pierce_height_mm'))}"] if z else []
    lines.append("M3")
    if pierce > 0:
        lines.append(f"G4 {post.dwell_word(pierce)}")
    if z:
        lines.append(f"G1 Z{post.num(post.option(program, 'cut_height_mm'))} "
                     f"F{post.num(post.option(program, 'z_feed_mm_min'))}")
    if post.option(program, "thc"):
        lines.append(post.option(program, "thc_on"))
    return lines


def torch_safe(post, program: Program) -> list[str]:
    """The torch up to its safe height before the first move (where it starts is unknown: it may sit at the cut
    height over the sheet, and an X Y rapid there drags it through tipped-up parts)."""
    return [f"G0 Z{post.num(post.option(program, 'safe_height_mm'))}"] if post.option(program, "torch_z") else []


def torch_off(post, program: Program) -> list[str]:
    lines = [post.option(program, "thc_off")] if post.option(program, "thc") else []
    lines.append("M5")
    if post.option(program, "torch_z"):
        lines.append(f"G0 Z{post.num(post.option(program, 'safe_height_mm'))}")
    return lines


class CuttingPost(CheckedPost):
    """X/Y cutting: the beam is the process; the IR's Z is not posted (unless ``machine.z_words``)."""

    accepts_arcs = True
    tool_changer = False
    canned_cycles = frozenset()
    linear_axes = "XY"

    def render(self, program: Program) -> str:
        self._program = program
        self._beam = False
        self.linear_axes = "XYZ" if self.options.get("z_words") and self.option(program, "z_words") else "XY"
        self.check(program)
        return super().render(program)

    def preamble(self, program: Program) -> list[str]:
        return ["G21", "G90 G94 G17 G40"]

    def tool_change_height(self, program: Program) -> float | None:
        # Where Z words are posted, the head goes up to the clearance height before its first X Y move.
        return float(program.clearance_z) if "Z" in self.linear_axes else None

    def footer(self, program: Program) -> list[str]:
        return (self.beam_off({}, program) if self._beam else []) + ["M30"]

    def on_tool(self, data: dict, program: Program, first: bool) -> list[str]:
        return [self.comment(f"Beam: {self.tool_label(program.tools[data['tool']])}")]

    def on_spindle(self, data: dict, program: Program) -> list[str]:
        return []                  # only "off" reaches here (check() refuses a spindle start)

    def dwell_word(self, seconds: float) -> str:
        if self.options.get("dwell_ms") and self.option(self._program, "dwell_ms"):
            return f"P{int(round(seconds * 1000))}"
        return f"P{number(seconds, 3)}"

    def modal_reset(self, kind: str) -> tuple[str, ...]:
        return ("motion", "f", "z") if kind == "beam" else ()

    def on_beam(self, data: dict, program: Program) -> list[str]:
        if data.get("on"):
            self._beam = True
            return self.beam_on(data, program)
        if not self._beam:
            return []
        self._beam = False
        return self.beam_off(data, program)

    def beam_on(self, data: dict, program: Program) -> list[str]:
        raise NotImplementedError

    def beam_off(self, data: dict, program: Program) -> list[str]:
        raise NotImplementedError
