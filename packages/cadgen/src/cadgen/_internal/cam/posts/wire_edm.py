"""``wire_edm``: a Fanuc-style 2-axis wire EDM with UV taper (``.nc``).

``%``, an ``O`` number (one more for each next setup), upper-case comments, decimal points. The program starts where the wire is threaded:
``G92 X Y`` makes the first cut's start hole the start point (everything the toolpath did before it, a rapid from the
setup's origin, is not posted; put the wire through the start hole by hand first). Z is never posted.

Offsets: by default the toolpath already is the wire-centre path (wire radius, spark gap and skim offsets applied by
cadgen), so the program says so and keeps compensation off (``G40``). ``machine.wire_comp: controller`` posts
``G41``/``G42 D1`` around each cut (from the beam event's ``offset_side``) with D1 holding only a wear or skim
adjustment on top of the applied offset.

Each cut: the thread code (``machine.wire_thread``, default ``M60``, Fanuc-format automatic wire threading) when the
wire was cut, the taper, the contour, then ``G40``/``G50``, and the cut-wire code (``machine.wire_cut``, default
``M50``) when another start hole follows. Both are machine keys: builders differ, check the control's manual.
Taper (the beam event's ``taper_deg``, plus leaning the wire's top to the left of travel): ``G51 A`` (left) or
``G52 A`` (right), cancelled by ``G50``; or, with ``machine.uv_words: true``, explicit ``U V`` words on every move:
the upper guide's offset from X Y at ``thickness_mm`` above the program plane, normal to the move (arcs posted as
short lines). That UV form is lite: at a sharp corner the wire's lean turns over the next move instead of at the
corner. The program ends ``M30``.
"""

from __future__ import annotations

import math
from dataclasses import replace

from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.posts._iso import CheckedPost
from cadgen._internal.cam.posts.base import Program, number
from cadgen._internal.cam.posts.fanuc import PROGRAM_NUMBER

__all__ = ["WireEdmPost", "linearize_arcs"]


def linearize_arcs(path, chord_mm: float):
    """``path`` with every arc replaced by feed moves within ``chord_mm`` (events moved with their moves)."""
    import numpy as np

    from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, FEED, Event, Toolpath

    rows, first = [], []
    for i in range(len(path.moves)):
        move = path.moves[i]
        first.append(len(rows))
        if int(move["kind"]) in (ARC_CW, ARC_CCW):
            for point in path.slice(i, i + 1).sample(chord_mm).points[1:]:
                row = move.copy()
                row["kind"], row["x"], row["y"], row["z"] = FEED, point[0], point[1], point[2]
                rows.append(row)
        else:
            rows.append(move.copy())
    first.append(len(rows))
    moves = np.array(rows, dtype=path.moves.dtype) if rows else path.moves[:0].copy()
    events = []
    for event in path.events:
        data = dict(event.data)
        if "end" in data:
            data["end"] = first[min(int(data["end"]), len(first) - 1)]
        events.append(Event(first[min(event.at, len(first) - 1)], event.kind, data))
    return Toolpath(moves, events, (), start=path.start, rotary=path.rotary, lathe=path.lathe)


class WireEdmPost(CheckedPost):
    name = "wire_edm"
    kinds = ("wire_edm",)
    extension = ".nc"
    plain = "Wire EDM (Fanuc-style)"
    accepts_arcs = True
    tool_changer = False
    canned_cycles = frozenset()
    linear_axes = "XY"
    upper_comments = True
    #: The program starts where the wire is threaded (G92): no approach move is added before the first cut.
    entry_moves = False
    options = {
        "wire_comp": {"type": "choice", "default": "applied", "choices": ("applied", "controller"),
                      "help": "applied: the path is the wire centre (G40); controller: G41/G42 D1 for wear only"},
        "uv_words": {"type": "bool", "default": False, "help": "taper as explicit U V words instead of G51/G52 A"},
        "wire_thread": {"type": "text", "default": "M60", "help": "the controller's thread-the-wire code (Fanuc "
                                                                   "AWT: M60)"},
        "wire_cut": {"type": "text", "default": "M50", "help": "the controller's cut-the-wire code (Fanuc AWT: M50)"},
        "program_number": PROGRAM_NUMBER,
    }

    def num(self, value: float, toward: int = 0) -> str:
        text = number(value, self.decimals, toward)
        return text if "." in text else text + "."

    def dwell_word(self, seconds: float) -> str:
        return f"P{int(round(seconds * 1000))}"

    def render(self, program: Program) -> str:
        self.check(program)
        path = program.toolpath
        self._uv = bool(self.option(program, "uv_words"))
        if self._uv:
            path = linearize_arcs(path, min(program.tolerance_mm, 0.01))
        self.fit_arcs_to_lines = not self._uv
        # Start where the wire is threaded: at the first beam-on, else before the first cutting move.
        ons = [e.at for e in path.events if e.kind == "beam" and e.data.get("on")]
        if ons:
            start = ons[0]
        else:
            from cadgen._internal.cam.ir import RAPID

            cutting = [i for i in range(len(path.moves)) if int(path.moves[i]["kind"]) != RAPID]
            start = cutting[0] if cutting else 0
        self._start = tuple(float(v) for v in path.positions()[start])
        if start:
            from cadgen._internal.cam.ir import Event, Toolpath

            kept = [Event(0, e.kind, e.data) for e in path.events if e.at < start and e.kind != "beam"]
            rest = path.slice(start, len(path.moves))
            path = Toolpath(rest.moves, kept + list(rest.events), (), start=rest.start, rotary=rest.rotary)
        # The wire is cut after a pass only when the table then travels to another start hole (skims stay threaded).
        from cadgen._internal.cam.ir import RAPID

        beams = [e for e in path.events if e.kind == "beam"]
        self._cuts = []
        positions = path.positions()
        for k, event in enumerate(beams):
            if event.data.get("on"):
                continue
            later = next((e.at for e in beams[k + 1:] if e.data.get("on")), None)
            moves = path.moves[event.at:later] if later is not None else path.moves[:0]
            self._cuts.append(later is not None and any(
                int(m["kind"]) == RAPID and (abs(m["x"] - positions[event.at + j][0]) > 1e-9
                                             or abs(m["y"] - positions[event.at + j][1]) > 1e-9)
                for j, m in enumerate(moves)))
        self._beam = False
        self._wire_cut = False
        self._comp = False
        self._taper = 0.0
        self._height = 0.0
        self._program = program
        text = super().render(replace(program, toolpath=path))
        number_ = int(self.option(program, "program_number")) + int(program.setup_index)   # one O number a setup
        if number_ > 9999:
            raise CamJobError("machine.program_number must be at most 9999 for a Fanuc-style O number (setup "
                              f"{program.setup_index + 1} of {program.setup_count} posts as O{number_})")
        title = self.comment_line(f"{program.job_name or program.part or 'part'} {program.setup.id}",
                                  self.comment_width - 6)
        return f"%\nO{number_:04d} {title}\n{text}%\n"

    def header(self, program: Program) -> list[str]:
        lines = super().header(program)
        comp = self.option(program, "wire_comp")
        lines.append(self.comment("The path is the wire centre: wire radius, spark gap and skims are applied, keep "
                                  "compensation off (G40)." if comp == "applied" else
                                  "The path is the wire centre: D1 holds only a wear or skim adjustment."))
        lines.append(self.comment(f"Thread the wire at the start hole X{number(self._start[0])} "
                                  f"Y{number(self._start[1])} before cycle start."))
        return lines

    def preamble(self, program: Program) -> list[str]:
        return ["G21", "G90 G40 G50", f"G92 X{self.num(self._start[0])} Y{self.num(self._start[1])}"]

    def footer(self, program: Program) -> list[str]:
        return (self._off_lines() if self._beam else []) + ["M30"]

    def on_setup(self, data: dict, program: Program) -> list[str]:
        return []

    def safety_lines(self, program: Program) -> list[str]:
        return ["Verify the start hole, the wire and the guide heights first."]

    def on_tool(self, data: dict, program: Program, first: bool) -> list[str]:
        return [self.comment(f"Wire: {self.tool_label(program.tools[data['tool']])}")]

    def on_spindle(self, data: dict, program: Program) -> list[str]:
        return []

    def on_coolant(self, data: dict, program: Program) -> list[str]:
        return []

    def on_beam(self, data: dict, program: Program) -> list[str]:
        if not data.get("on"):
            if not self._beam:
                return []
            self._beam = False
            lines = self._off_lines()
            if self._cuts and self._cuts.pop(0):
                lines += [self.comment("Cut the wire for the next start hole"), self.option(program, "wire_cut")]
                self._wire_cut = True
            return lines
        # A new pass without an off between (a skim, the rest after a hold): close the last pass's taper and offset.
        lines = self._off_lines(reset_uv=False) if self._beam else []
        self._beam = True
        if self._wire_cut:
            lines += [self.comment("Thread the wire"), self.option(program, "wire_thread")]
            self._wire_cut = False
        self._taper = float(data.get("taper_deg", 0.0) or 0.0)
        self._height = float(data.get("thickness_mm", 0.0) or 0.0)
        if self._taper and not self._uv:
            lines.append(f"{'G51' if self._taper > 0 else 'G52'} A{self.num(abs(self._taper))}")
        if self._taper and self._uv and self._height <= 0:
            raise CamJobError(f"setup {program.setup.id}: a tapered wire cut posted as U V words needs the cut's "
                              "thickness_mm (program plane to the top guide); set machine.uv_words false to post "
                              "G51/G52 instead")
        if self.option(program, "wire_comp") == "controller":
            side = data.get("offset_side")
            if side not in ("left", "right"):
                raise CamJobError(f"setup {program.setup.id}: machine.wire_comp controller needs to know which side "
                                  "of the contour the wire runs, and this cut does not say; use wire_comp applied")
            lines.append(f"{'G41' if side == 'left' else 'G42'} D1")
            self._comp = True
        return lines

    def _off_lines(self, reset_uv: bool = True) -> list[str]:
        lines = []
        if self._comp:
            lines.append("G40")
            self._comp = False
        if self._taper:
            if not self._uv:
                lines.append("G50")
            elif reset_uv:
                lines.append("G1 U0. V0.")
            self._taper = 0.0
        return lines

    def extra_words(self, start, end, code: str) -> list[str]:
        if not (self._uv and self._taper and code == "G1"):
            return []
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return []
        lean = self._height * math.tan(math.radians(self._taper))
        return [f"U{self.num(-dy / length * lean)}", f"V{self.num(dx / length * lean)}"]
