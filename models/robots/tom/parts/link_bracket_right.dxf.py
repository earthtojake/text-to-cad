"""Flat-pattern DXF drawing for link_bracket_right; geometry reused from link_bracket_right.step.py."""

from __future__ import annotations

from pathlib import Path

from cadgen.sources import load_source_module

_step = load_source_module(Path(__file__).with_name("link_bracket_right.step.py"))


def gen_dxf() -> dict[str, object]:
    return {
        "document": _step.build_dxf(),
    }


if __name__ == "__main__":
    gen_dxf()
