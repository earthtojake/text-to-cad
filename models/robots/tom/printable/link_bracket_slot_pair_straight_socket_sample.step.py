#!/usr/bin/env python3
"""Matching female dovetail half for the printable straight tongue shell."""

from __future__ import annotations

import sys
from pathlib import Path

PRINTABLE_DIR = Path(__file__).resolve().parent
if str(PRINTABLE_DIR) not in sys.path:
    sys.path.insert(0, str(PRINTABLE_DIR))

import sys as _sys
from pathlib import Path as _Path
_TOM_DIR = _Path(__file__).resolve().parents[2]
if str(_TOM_DIR) not in _sys.path:
    _sys.path.insert(0, str(_TOM_DIR))
from robot_common.step_entry import load_step_entry

connector_shell = load_step_entry("link_bracket_slot_pair_straight_sample")


PART_NAME = Path(__file__).stem


def build_step():
    shell = connector_shell.build_step(dovetail_role="female")
    shell.label = PART_NAME
    shell.color = connector_shell.PLASTIC_COLOR
    return shell


def gen_step() -> dict[str, object]:
    return {
        "shape": build_step(),
    }


if __name__ == "__main__":
    gen_step()
