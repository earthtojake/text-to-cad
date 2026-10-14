"""``waterjet``: a generic abrasive or pure waterjet (``.nc``): X/Y cutting, ``M3`` jet on, ``M5`` jet off.

Each cut: ``M3`` (jet on, abrasive with it where the machine feeds it), ``G4 P`` pierce dwell (the operation's
``pierce_s``, else ``machine.pierce_s``), the cut, ``M5``. Lead-ins and the kerf are already in the toolpath
(compensation off, ``G40``). No Z unless ``machine.z_words`` is true (a programmable nozzle height). Dwell ``P`` in
seconds unless ``machine.dwell_ms`` is true. The program ends ``M30``.
"""

from __future__ import annotations

from cadgen._internal.cam.posts._cutting import DWELL_MS, CuttingPost
from cadgen._internal.cam.posts.base import Program

__all__ = ["WaterjetPost"]


class WaterjetPost(CuttingPost):
    name = "waterjet"
    kinds = ("waterjet",)
    extension = ".nc"
    plain = "Waterjet"
    options = {
        "pierce_s": {"type": "number", "default": 1.0, "help": "pierce dwell when the operation gives none"},
        "z_words": {"type": "bool", "default": False, "help": "post the toolpath's Z (a programmable nozzle height)"},
        "dwell_ms": DWELL_MS,
    }

    def beam_on(self, data: dict, program: Program) -> list[str]:
        pierce = float(data.get("pierce_s") or self.option(program, "pierce_s"))
        return ["M3"] + ([f"G4 {self.dwell_word(pierce)}"] if pierce > 0 else [])

    def beam_off(self, data: dict, program: Program) -> list[str]:
        return ["M5"]
