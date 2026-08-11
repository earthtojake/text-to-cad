"""Flat-pattern DXF drawing for servo_end_mount; geometry reused from servo_end_mount.step.py."""

from __future__ import annotations

from pathlib import Path

from cadgen.sources import load_source_module

_step = load_source_module(Path(__file__).with_name("servo_end_mount.step.py"))


def gen_dxf() -> dict[str, object]:
    return {
        "document": _step.build_dxf(),
    }


if __name__ == "__main__":
    gen_dxf()
