"""A board's ``.kicad_pro``: its design rules and net classes.

The project file is KiCad's JSON settings for the project. cadgen writes the
part of it the board's checks depend on: the constraints (``rules=``), the net
classes and which nets are in them, and the severities it changes from
KiCad's. Everything else KiCad fills with its defaults when it reads the file.

Changed severities: the library-table checks are off. A generated board embeds
every symbol and footprint from the library at build time, so "this footprint
differs from the library" cannot happen to it, and "the library is not in your
library table" depends on the machine that opens it rather than on the board.
"""

from __future__ import annotations

import json

from cadgen.kicad.design import Board, kicad_net_name

__all__ = ["project_document"]

_IGNORED_DRC = ("lib_footprint_issues", "lib_footprint_mismatch")
_IGNORED_ERC = ("footprint_link_issues", "lib_symbol_issues", "lib_symbol_mismatch")


def _netclass(name: str, *, track_width: float, clearance: float, via_diameter: float, via_drill: float, priority: int) -> dict:
    return {
        "bus_width": 12,
        "clearance": clearance,
        "diff_pair_gap": clearance,
        "diff_pair_via_gap": clearance,
        "diff_pair_width": track_width,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "name": name,
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "priority": priority,
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": track_width,
        "via_diameter": via_diameter,
        "via_drill": via_drill,
        "wire_width": 6,
    }


def project_document(board: Board, *, project: str, root_uuid: str) -> str:
    """The ``.kicad_pro`` text."""
    rules = board.rules
    classes = [
        _netclass(
            "Default",
            track_width=rules.track_width,
            clearance=rules.clearance,
            via_diameter=rules.via_diameter,
            via_drill=rules.via_drill,
            priority=2147483647,
        )
    ]
    for priority, netclass in enumerate(board.netclasses):
        classes.append(
            _netclass(
                netclass.name,
                track_width=netclass.track_width,
                clearance=netclass.clearance,
                via_diameter=netclass.via_diameter,
                via_drill=netclass.via_drill,
                priority=priority,
            )
        )
    patterns = [
        {"netclass": net.netclass, "pattern": kicad_net_name(net.name)}
        for net in sorted(board.nets, key=lambda net: net.name)
        if net.netclass is not None
    ]
    document = {
        "board": {
            "design_settings": {
                "rule_severities": {name: "ignore" for name in _IGNORED_DRC},
                "rules": {
                    "min_clearance": rules.min_clearance,
                    "min_connection": 0.0,
                    "min_copper_edge_clearance": rules.min_copper_edge_clearance,
                    "min_hole_clearance": rules.min_hole_clearance,
                    "min_hole_to_hole": rules.min_hole_to_hole,
                    "min_silk_clearance": rules.min_silk_clearance,
                    "min_text_height": rules.min_text_height,
                    "min_text_thickness": rules.min_text_thickness,
                    "min_through_hole_diameter": rules.min_through_hole_diameter,
                    "min_track_width": rules.min_track_width,
                    "min_via_annular_width": rules.min_via_annular_width,
                    "min_via_diameter": rules.min_via_diameter,
                },
            },
        },
        "erc": {"rule_severities": {name: "ignore" for name in _IGNORED_ERC}},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{project}.kicad_pro", "version": 3},
        "net_settings": {
            "classes": classes,
            "meta": {"version": 5},
            "netclass_assignments": None,
            "netclass_patterns": patterns,
        },
        "sheets": [[root_uuid, "Root"]],
        "text_variables": {},
    }
    return json.dumps(document, indent=2, sort_keys=True) + "\n"
