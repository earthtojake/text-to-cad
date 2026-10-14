"""``linuxcnc``: LinuxCNC 2.8/2.9 (``.ngc``) for mills, 4th/5th-axis mills and lathes.

Mill: ``G21 G90 G94 G17``, ``G91.1`` (incremental arc centres, whatever the config left), ``G64 P`` path blending
at the job's tolerance, ``M5 M9``, ``G49`` and ``G53 G0 Z0`` (the tool length off first, since a G53 move still
applies it; Z to the machine's top: LinuxCNC's M6 does not retract) then ``T M6``, ``G0 X Y`` over the first point and
``G43 H`` at a clearance Z, G2/G3 with incremental I/J, the drilling cycles G81 G82 G83 G73 G85 G86 G89 natively, a
tap as rigid ``G33.1`` per hole (LinuxCNC's G84 does not follow the spindle), or, when the tap cycle says ``rigid:
false`` (a floating, tension-compression holder), as LinuxCNC's ``G84`` (``G74`` left hand), a fine bore and a back
bore as their moves (LinuxCNC's G76 is a lathe thread, and it has no G87) with ``M19 R0 Q10`` (orient, and wait for
it) before the bar shifts, dwell ``G4 P`` in seconds,
mist ``M7``, flood ``M8`` (air: a comment to switch it by hand), ``G49``, ``G53 G0 Z0`` and the table to rotary zero
(``G53 G0 A0 C0``) then ``M2`` at the end. A 3+2 setup turns the table (``G0 A.. C..``) after each tool change, with Z at the top, and
then posts 3-axis: set the work offset on the turned part.
Simultaneous 4/5-axis posts the rotary words on every move with ``G43.4`` tool centre point control, which stock
LinuxCNC does not have: the machine's TCP kinematics must provide it (a switchkins config with G43.4 remapped).

Lathe: ``G18``, ``G7`` diameter mode (``G8`` with ``machine.diameter_mode: false``), ``G91.1``, arcs with I as a
radius, ``G30`` (the turret's safe index position, set on the machine with ``G30.1``) before ``T M6`` and ``G43`` and
at the end, ``G96 D S`` constant surface speed with its clamp, ``G95`` feed per revolution where the spindle event
asks, threads as LinuxCNC's one-line ``G76`` (its I, J and K are diameters in G7; tapered threads post expanded).
Roughing always posts expanded: LinuxCNC's G71 needs the profile as an O-word subroutine and is fragile.
"""

from __future__ import annotations

from cadgen._internal.cam.posts._iso import CYCLES_OPTION, IsoPost
from cadgen._internal.cam.posts.base import Program, number

__all__ = ["LinuxCncPost"]


class LinuxCncPost(IsoPost):
    name = "linuxcnc"
    kinds = ("mill", "mill4", "mill5", "lathe")
    extension = ".ngc"
    plain = "LinuxCNC"
    tilt_style = "rotate"
    tcp_code = "G43.4"
    drill_codes = {"drill": "G81", "spot": "G82", "peck": "G83", "chipbreak": "G73", "tap": "G33.1", "bore": "G85",
                   "ream": "G85", "bore_stop": "G86", "bore_dwell": "G89"}
    left_tap_code = "G33.1"
    lathe_feed_codes = ("G94", "G95")
    native_rough = False
    mill_tool_home = ("G53 G0 Z0",)
    mill_end_home = ("G53 G0 Z0",)
    index_home_lines = ("G53 G0 Z0",)
    rotary_home_style = "g53"
    lathe_home = ("G30",)
    end_code = "M2"
    length_cancel_before_home = True
    orient_lines = ("M19 R0 Q10",)
    options = {"cycles": CYCLES_OPTION}

    def preamble(self, program: Program) -> list[str]:
        if self._lathe:
            return ["G21 G90 G94 G18 G40 G49 G80", "G91.1", "G7" if self.diameter() else "G8"]
        return ["G21 G90 G94 G17 G40 G49 G80", "G91.1", f"G64 P{number(max(program.tolerance_mm, 0.001), 4)}"]

    def tcp_notes(self, program: Program) -> list[str]:
        return ["Stock LinuxCNC has no G43.4: this program needs a TCP kinematics config, a switchkins machine "
                "with G43.4 remapped. Without it, it will not run."]

    def header(self, program: Program) -> list[str]:
        lines = super().header(program)
        if self._lathe:
            lines.append(self.comment("G30 is the turret's safe index position: set it on the machine with G30.1 "
                                      "before running."))
        return lines

    def lathe_tool_words(self, n: int) -> list[str]:
        return [f"T{n} M6", f"G43 H{n}"]

    def css_words(self, css: float, clamp: int, m: str) -> list[str]:
        return [f"G96 D{clamp} S{number(css, 1)} {m}"]

    def can_thread(self, data: dict) -> bool:
        return super().can_thread(data) and abs(float(data.get("taper_mm", 0.0))) < 1e-9

    def tap_code(self, data: dict) -> str:
        """G33.1 (rigid, synchronised to the spindle), or G84/G74 for a floating holder (``rigid: false``)."""
        if data.get("rigid") is False:
            return "G74" if self.left_hand(data) else "G84"
        return "G33.1"

    def drill_lines(self, data: dict) -> list[str]:
        if data["cycle"] != "tap" or data.get("rigid") is False:
            return super().drill_lines(data)
        # Rigid tapping: G33.1 feeds in synchronised with the spindle, reverses and comes back to where it started.
        pitch = float(data.get("pitch_mm") or (float(data["feed"]) / self._rpm if self._rpm else 0.0))
        holes = data["holes"]
        r_plane = float(data["r_plane"])
        back = float(data.get("initial_z", r_plane)) if data.get("retract", "r") == "initial" else r_plane
        lines = [self.comment(f"rigid tap, {len(holes)} hole{'s' if len(holes) != 1 else ''}, pitch "
                              f"{number(pitch)} mm")]
        for hole in holes:
            lines += [f"G0 X{self.num(hole[0])} Y{self.num(hole[1])}", f"G0 Z{self.num(r_plane)}",
                      f"G33.1 Z{self.num(float(data['z_bottom']))} K{number(pitch, 4)}"]
            if abs(back - r_plane) > 1e-9:
                lines.append(f"G0 Z{self.num(back)}")
        return lines

    def thread_lines(self, data: dict) -> list[str]:
        """LinuxCNC's G76: the drive line is the X it starts at; I (crest from the drive line), J (first depth) and K
        (thread depth) are diameters in G7."""
        scale = 2.0 if self.diameter() else 1.0
        depth = float(data["depth_mm"])
        first = float(data.get("first_depth_mm") or max(depth / 3.0, 0.05))
        peak = (float(data["x_crest"]) - float(data["x_clear"])) * scale
        words = [f"G76 P{number(float(data['pitch_mm']), 4)}", f"Z{self.num(float(data['z_end']))}",
                 f"I{self.num(peak)}", f"J{self.num(first * scale)}", f"K{self.num(depth * scale)}", "R2",
                 f"Q{number(float(data.get('infeed_deg', 29.5)), 2)}", f"H{int(data.get('spring_passes', 1))}"]
        return [self.comment(f"thread, pitch {number(float(data['pitch_mm']))} mm"), " ".join(words)]
