"""``plasma``: a generic plasma table (``.nc``): X/Y cutting with torch heights, pierce delay and THC codes.

After the work offset the torch goes up to ``G0 Z`` safe height (where it starts is unknown). Each cut: ``G0 Z``
pierce height, ``M3`` torch on, ``G4 P`` pierce delay (the operation's, else ``machine.pierce_delay_s``), ``G1 Z``
cut height, the THC-on code; after it the THC-off code, ``M5`` and ``G0 Z`` safe height. Every height and both THC
codes are machine keys (``_cutting.py``); the default THC codes ``M101`` and ``M102`` are placeholders that must
match the controller (set ``machine.thc: false`` when it has no THC). Kerf and lead-ins are already in the toolpath,
so compensation stays off (``G40``). Dwell ``P`` in seconds unless ``machine.dwell_ms`` is true. The program ends ``M30``.
"""

from __future__ import annotations

from cadgen._internal.cam.posts._cutting import TORCH_OPTIONS, CuttingPost, torch_off, torch_on, torch_safe
from cadgen._internal.cam.posts.base import Program

__all__ = ["PlasmaPost"]


class PlasmaPost(CuttingPost):
    name = "plasma"
    kinds = ("plasma",)
    extension = ".nc"
    plain = "Plasma (THC)"
    options = dict(TORCH_OPTIONS)

    def on_setup(self, data: dict, program: Program) -> list[str]:
        return super().on_setup(data, program) + torch_safe(self, program)

    def beam_on(self, data: dict, program: Program) -> list[str]:
        return torch_on(self, data, program)

    def beam_off(self, data: dict, program: Program) -> list[str]:
        return torch_off(self, program)
