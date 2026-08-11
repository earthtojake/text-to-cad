# Prompt: Laser-cut profile DXF for the clamp plate, projected from the
# clamp_plate_profile.py topology.

from __future__ import annotations

from pathlib import Path

from cadgen.sources import load_source_module

_step = load_source_module(Path(__file__).with_name("clamp_plate_profile.py"))


def gen_dxf():
    return {"document": _step.build_dxf()}


if __name__ == "__main__":
    gen_dxf()
