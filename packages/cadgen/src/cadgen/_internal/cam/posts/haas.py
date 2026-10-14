"""``haas``: Haas NGC/classic controls (``.nc``) for mills (VF, UMC) and lathes (ST, DS): Fanuc-like with Haas's own.

``%`` and a five-digit ``O`` number (``machine.program_number`` for the first setup, one more for each next one),
decimal points on every dimension word, ``N1 T M06``, ``N2``... (an N number on each tool change, so the operator can
restart at a tool; the Haas tool change retracts Z itself) then ``G43 H`` at a clearance Z, the canned cycles G81 G82
G83 G73 G84 (rigid, no M29, F the posted S times the pitch; G74 left hand; the same G84 for a floating holder) G85
G86 G89 G76 (its shift ``I J`` along the cycle's ``shift_xy``, else ``Q`` in setting 27's direction), the back bore
as Haas's ``G77`` (not G87, which is another cycle on a Haas; shift ``I J`` the same way; it takes no dwell, so a back
bore with one posts as its moves with ``M19``), dwell ``G4 P`` in milliseconds, air blast
``M83``/``M84``. The end cancels the tool length (``G49``) after Z goes home.
``machine.smoothing`` (``rough``, ``medium``, ``finish``) writes ``G187 P1``..``P3 E`` (the job's tolerance) and
resets it at the end. A 3+2 setup turns the table (``G0 A.. C..`` or ``B.. C..``) and switches on dynamic work
offsets (``G254``, off with ``G255``): G54.. is the setup's origin with the table at zero and the machine's rotary
centre settings must be right. Simultaneous moves post under ``G234`` tool centre point control (rotary axes first,
then ``G234 H``, then X Y, then Z; drilling posts expanded there). At the end Z goes home, then the table to rotary zero
(``G91 G28 A0. C0.``).

Lathe: diameter X, ``G28 U0. W0.``, ``T101``-style tool words, ``G50 S`` clamp, ``G96``/``G97``, ``G98``/``G99``,
the one-block Haas ``G76`` thread (``X Z K D F A``), and the one-block ``G71 P Q U W D F`` roughing with its profile
when ``machine.cycles`` is true. The program is inline (no ``M97`` local subprograms: nothing in it repeats).
"""

from __future__ import annotations

from cadgen._internal.cam.posts._iso import CYCLES_OPTION, IsoPost
from cadgen._internal.cam.posts.base import Program, number, shift_direction
from cadgen._internal.cam.posts.fanuc import PROGRAM_NUMBER

__all__ = ["HaasPost"]

_SMOOTHING = {"rough": 1, "medium": 2, "finish": 3}


class HaasPost(IsoPost):
    name = "haas"
    kinds = ("mill", "mill4", "mill5", "lathe")
    extension = ".nc"
    plain = "Haas"
    decimal_point = True
    program_wrap = True
    o_digits = 5
    mill_end_home = ("G91 G28 Z0.", "G90")
    index_home_lines = ("G91 G28 Z0.", "G90")
    lathe_home = ("G28 U0. W0.",)
    tilt_style = "dwo"
    tool_line_numbers = True
    q_shift = None
    orient_lines = ("M19",)
    drill_codes = {**IsoPost.drill_codes, "back_bore": "G77"}
    back_bore_dwell = False
    coolant_codes = {"flood": "M8", "mist": "M7", "air": "M83"}
    coolant_off_codes = {"air": "M84"}
    tcp_code = "G234"
    dwell_ms = True
    lathe_feed_codes = ("G98", "G99")
    native_rough = True
    options = {
        "cycles": CYCLES_OPTION, "program_number": PROGRAM_NUMBER,
        "smoothing": {"type": "choice", "default": "off", "choices": ("off", "rough", "medium", "finish"),
                      "help": "G187 smoothing: rough, medium or finish, at the job's tolerance"},
    }

    def preamble(self, program: Program) -> list[str]:
        if self._lathe:
            return ["G21", "G0 G18 G40 G80 G98"]
        lines = ["G21", "G0 G17 G40 G49 G80 G90 G94"]
        smoothing = self.option(program, "smoothing")
        if smoothing != "off":
            lines.append(f"G187 P{_SMOOTHING[smoothing]} E{self.num(max(program.tolerance_mm, 0.001))}")
        return lines

    def footer(self, program: Program) -> list[str]:
        lines = super().footer(program)
        if not self._lathe and self.option(program, "smoothing") != "off":
            lines.insert(-1, "G187")
        return lines

    def on_tool(self, data: dict, program: Program, first: bool) -> list[str]:
        lines = super().on_tool(data, program, first)
        return [line.replace(" M6", " M06") if line.startswith("N") else line for line in lines]

    def lathe_tool_words(self, n: int) -> list[str]:
        return [f"T{n}{n:02d}"]

    def shift_words(self, data: dict) -> list[str]:
        """G76's and G77's shift: I and J along the cycle's own direction (``shift_xy``), else Q (setting 27's
        direction)."""
        xy = shift_direction(data)
        if xy is None:
            return super().shift_words(data)
        shift = float(data.get("shift_mm", 0.1))
        return [f"I{self.num(shift * xy[0])}", f"J{self.num(shift * xy[1])}"]

    def thread_lines(self, data: dict) -> list[str]:
        """Haas's one-block G76: X root, Z end, K thread height (radius), D first pass depth, F lead, A tip angle."""
        depth = float(data["depth_mm"])
        first = float(data.get("first_depth_mm") or max(depth / 3.0, 0.05))
        words = [f"G76 X{self.num(self.axis_value('x', self.root_radius(data)))}", f"Z{self.num(float(data['z_end']))}",
                 f"K{self.num(depth)}", f"D{self.num(first)}", f"F{self.num(float(data['pitch_mm']))}",
                 f"A{self.thread_angle(data)}"]
        taper = -float(data.get("taper_mm", 0.0))
        if abs(taper) > 1e-9:
            words.insert(2, f"I{self.num(taper)}")
        return [self.comment(f"thread, pitch {number(float(data['pitch_mm']))} mm"), " ".join(words)]

    def rough_lines(self, data: dict) -> list[str]:
        ns, nf, profile = self.profile_blocks(data)
        u, w = self.allowances(data)
        return [self.comment("roughing cycle"),
                f"G71 P{ns} Q{nf} U{self.num(u)} W{self.num(w)} D{self.num(float(data['depth_mm']))} "
                f"F{self.feed_word(float(data['feed']))}"] + profile
