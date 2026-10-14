"""``marlin``: a diode laser on a Marlin printer frame (``.gcode``, Marlin 2.x built with LASER_FEATURE).

``G21 G90``; each cut ``M3 S`` (``machine.laser_mode``: ``constant`` M3, or ``dynamic`` M4 where the firmware has it)
with the power on Marlin's scale (``machine.laser_scale``: 255, the PWM default, or 1000), ``G4 P`` (milliseconds)
for a pierce dwell, G1/G2/G3 with I/J, then ``M5``. ``machine.inline_power: true`` uses Marlin's inline mode
(``M3 I``): the power rides on every cutting move as ``S`` and the first rapid after a cut carries ``S0``. Air assist
is ``M8``/``M9`` (coolant ``air``). No Z unless ``machine.z_words`` is true. No work offsets: the setup posts
``G92 X0 Y0`` (``Z0`` too with ``z_words``), so the origin is where the head is when the job starts; jog it to the
setup's origin first. The program ends ``M5``: Marlin's ``M30`` deletes a file.
"""

from __future__ import annotations

from cadgen._internal.cam.posts._cutting import CuttingPost
from cadgen._internal.cam.posts.base import Program

__all__ = ["MarlinPost"]


class MarlinPost(CuttingPost):
    name = "marlin"
    kinds = ("laser",)
    extension = ".gcode"
    plain = "Marlin laser"
    comment_open, comment_close = "; ", ""
    options = {
        "laser_scale": {"type": "choice", "default": 255, "choices": (255, 1000),
                        "help": "the S value of full power: 255 (Marlin's PWM default) or 1000"},
        "laser_mode": {"type": "choice", "default": "constant", "choices": ("constant", "dynamic"),
                       "help": "M3 constant power, or M4 power scaled with speed (Marlin 2.1+)"},
        "inline_power": {"type": "bool", "default": False, "help": "Marlin's inline laser power (M3 I)"},
        "z_words": {"type": "bool", "default": False, "help": "post the toolpath's Z (a frame with a Z axis)"},
    }

    def render(self, program: Program) -> str:
        self._power = 0
        self._written = None
        # Inline power rides on each motion line, so no run of lines is folded into a fitted arc without its S.
        self.fit_arcs_to_lines = not self.option(program, "inline_power")
        return super().render(program)

    def preamble(self, program: Program) -> list[str]:
        return ["G21", "G90"] + (["M3 I S0"] if self.option(program, "inline_power") else [])

    def footer(self, program: Program) -> list[str]:
        self._beam = False
        return ["M5 I" if self.option(program, "inline_power") else "M5"]

    def on_setup(self, data: dict, program: Program) -> list[str]:
        axes = "X0 Y0 Z0" if "Z" in self.linear_axes else "X0 Y0"
        return [self.comment(f"Setup {data.get('id', program.setup.id)}: the origin is where the head starts"),
                f"G92 {axes}"]

    def safety_lines(self, program: Program) -> list[str]:
        return ["The origin is where the head starts: G92 sets it there.",
                "Jog the head to the setup's origin and check the focus before cutting."]

    #: Air assist on M8 (coolant ``air``), M7 where the firmware has a mist output; flood has no code on a laser.
    coolant_codes = {"air": "M8", "mist": "M7"}

    def dwell_word(self, seconds: float) -> str:
        return f"P{int(round(seconds * 1000))}"

    def scaled(self, power: float, program: Program) -> int:
        return int(round(max(0.0, min(1.0, power)) * int(self.option(program, "laser_scale"))))

    def beam_on(self, data: dict, program: Program) -> list[str]:
        self._power = self.scaled(float(data.get("power", 1.0)), program)
        lines = []
        if not self.option(program, "inline_power"):
            lines.append(f"{'M4' if self.option(program, 'laser_mode') == 'dynamic' else 'M3'} S{self._power}")
        if data.get("pierce_s"):
            lines.append(f"G4 {self.dwell_word(float(data['pierce_s']))}")
        return lines

    def beam_off(self, data: dict, program: Program) -> list[str]:
        self._power = 0
        return [] if self.option(program, "inline_power") else ["M5"]

    def modal_reset(self, kind: str) -> tuple[str, ...]:
        return ()

    def extra_words(self, start, end, code: str) -> list[str]:
        if not self.option(self._program, "inline_power"):
            return []
        power = 0 if code == "G0" else self._power
        if power == self._written:
            return []
        self._written = power
        return [f"S{power}"]
