"""``grbl``: GRBL 1.1 (hobby mills, routers, diode and CO2 lasers on GRBL boards).

GRBL has no tool changer, no tool-length table and no canned cycles. An ``M0`` tool change cannot work on it: in the
Hold state an ``M0`` leaves, GRBL will not jog or probe, so the new tool cannot be touched off, and with no table the
next, longer tool would rapid into the stock. So a mill or router setup that uses more than one tool is posted one
file per tool (``split_by_tool``, :meth:`~cadgen._internal.cam.posts.base.Post.render_tool_files`): each a complete
program that names its tool and says "file k of n: load T2, zero Z on the stock top, then run", carries the coolant
in effect, and starts safe (Z up to the clearance height, then X Y, then down). :meth:`GrblPost.render` refuses a
multi-tool setup in one file. Drilling cycles post as their expanded moves, except a tap: GRBL cannot keep the feed in
step with the spindle, so a ``tap`` cycle is refused (thread mill the hole, or use a post that taps), and so is a fine
bore that shifts its bar (GRBL cannot orient the spindle). Arcs are G2/G3 with I/J, helical with Z. Dwell ``G4 P`` is
in seconds. ``M3`` has no spindle-at-speed feedback on GRBL, so every spindle start from standstill is followed by
``G4 P<machine.spindle_spinup_s>`` (3 s when the job sets none) before the tool may cut. Coolant: flood is ``M8``;
stock GRBL builds have no ``M7`` (a compile-time option), so mist and air on a mill are a comment telling the
operator to switch them by hand, never another coolant's code. A laser's air assist is ``M8``: on a GRBL laser the
one coolant output drives the air pump.

Line length: GRBL holds a block of up to 80 characters (spaces and comments dropped) and a sender counts each line
into GRBL's 128-byte serial buffer, so every line's code stays within 79 characters and every whole line within 127
(:meth:`GrblPost.check_lines`; comments wrap at 70). A line past either is a cadgen bug, raised as one.

A laser's beam is ``M4`` (dynamic power: off while stationary and during rapids, scaled with speed) with ``S`` out of
GRBL's default ``$30=1000``. Because M4 fires nothing while the head is still, a pierce dwell is fired in ``M3``
(constant power, which in laser mode fires at once) and the cut switches back to ``M4``: ``M3 S.. / G4 P.. / M4 S..``.
A laser's tool events are beam settings, not tools: a laser program is never split.
"""

from __future__ import annotations

from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.posts.base import Post, Program

__all__ = ["GrblPost"]


class GrblPost(Post):
    name = "grbl"
    kinds = ("mill", "router", "laser")
    extension = ".nc"
    plain = "GRBL 1.1"
    accepts_arcs = True
    canned_cycles = frozenset()
    tool_changer = False
    split_by_tool = True
    options = {
        "spindle_spinup_s": {"type": "number", "default": 3.0,
                             "help": "seconds to dwell after the spindle starts, before the tool cuts (GRBL does not "
                                     "wait for the spindle to reach speed)"},
    }

    def render(self, program: Program) -> str:
        if program.machine.kind != "laser" and len(self.tool_programs(program)) > 1:
            raise CamJobError(f"setup {program.setup.id}: GRBL cannot change tools inside one program (no tool table, "
                              "and it cannot jog to touch off a tool after M0); post the setup one file per tool "
                              "(render_tool_files)")
        return self.check_lines(super().render(program))

    def tool_programs(self, program):
        pieces = super().tool_programs(program)
        return [(pieces[0][0], program)] if program.machine.kind == "laser" else pieces

    def preamble(self, program):
        return ["G90 G94 G17 G21"]

    def on_tool(self, data, program, first):
        tool = program.tools[data["tool"]]
        if program.machine.kind == "laser":
            return [self.comment(f"Beam: {self.tool_label(tool)}")]
        return [self.comment(f"Load {self.tool_label(tool)}")]

    def tool_change_height(self, program):
        # Every file starts with Z up at the clearance height in the work frame, before the spindle starts. Not
        # G53 (machine coordinates): they mean something only on a machine that homes ($22=1), and without homing
        # GRBL's machine zero is wherever it was switched on. The work Z was just zeroed on the setup's Z zero with
        # this tool, so the clearance height is above the stock and the clamps whatever the machine. A laser's
        # head goes up too before its first X Y move: it may sit at the focus height over the sheet.
        return float(program.clearance_z)

    def default_spinup_s(self, program):
        return float(self.option(program, "spindle_spinup_s"))

    def coolant_code(self, mode, program):
        # Stock GRBL 1.1 has no M7 (a compile-time option): flood only on a mill; a laser's air assist is the one
        # coolant output.
        if program.machine.kind == "laser":
            return {"flood": "M8", "air": "M8"}.get(mode)
        return {"flood": "M8"}.get(mode)

    def on_beam(self, data, program):
        if not data.get("on"):
            return ["M5"]
        power = self.num(round(1000 * float(data.get("power", 1.0))))
        if data.get("pierce_s"):
            # M4 fires nothing while the head is still: pierce at constant power, then cut in dynamic mode.
            return [f"M3 S{power}", f"G4 P{self.num(float(data['pierce_s']))}", f"M4 S{power}"]
        return [f"M4 S{power}"]

    def footer(self, program):
        return ["M5"] + self.coolant_stop(program) + ["M2"]

    def check_lines(self, text: str) -> str:
        """``text``, every line of it within what GRBL and a streaming sender take: its code (spaces and comments
        dropped) at most 79 characters, the whole line at most 127. A longer line is a bug: ValueError."""
        for k, line in enumerate(text.splitlines(), 1):
            code = "".join(line.split("(")[0].split())
            if len(code) > 79 or len(line) > 127:
                raise ValueError(f"grbl post: line {k} ({line[:40]!r}...) is {len(line)} characters, {len(code)} of "
                                 "them code; GRBL takes 79 characters of code and a sender 127 in all (a cadgen bug)")
        return text
