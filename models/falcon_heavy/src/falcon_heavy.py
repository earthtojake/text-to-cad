"""SpaceX Falcon Heavy — educational public-source reconstruction.

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

The models of this script, each built from lib/falcon_common.py's vehicle
(`build_vehicle`) and the vendored Merlin 1D library (lib/merlin_common.py):

- `falcon_heavy`: the full-stack exterior. Three cores
  with 27 linked Merlin 1D instances (octaweb 8+1 per core, reduced decorative
  detail), MVac-derivative second stage, interstage, fairing, grid fins,
  landing legs, raceways, attach hardware.
- `falcon_heavy_cutaway`: center core, second
  stage and fairing sectioned 270 deg (opening +Y) with schematic interiors:
  LOX/RP-1 tank volumes, transfer tube, domes, COPV-like placeholders, octaweb
  frames, avionics/separation placeholders, payload adapter + payload
  placeholder. All internals schematic and non-functional.
- `falcon_heavy_exploded`: boosters translated
  outboard, second stage and fairing lifted, with translucent guide rods.
  Offsets presentational only.

The sources, confidence and estimates behind every number are the original
project's RESEARCH.md, PROVENANCE.md and DIMENSIONS.md (models/falcon_heavy).
"""

from __future__ import annotations

from cadgen import model

import build123d as bd

from lib import falcon_common as fc

OFFSETS = {
    "port_booster_group": (-5500.0, 0.0, 0.0),
    "starboard_booster_group": (5500.0, 0.0, 0.0),
    "second_stage_group": (0.0, 0.0, 9000.0),
    "payload_fairing_group": (0.0, 0.0, 18000.0),
}


@model
def falcon_heavy():
    groups = fc.build_vehicle()
    return bd.Compound(obj=groups, children=groups,
                       label="falcon_heavy__educational_public_source_reconstruction")


@model
def falcon_heavy_cutaway():
    groups = fc.build_vehicle(cutaway=True)
    return bd.Compound(obj=groups, children=groups,
                       label="falcon_heavy_cutaway__educational_nonfunctional")


@model
def falcon_heavy_exploded():
    groups = []
    for g in fc.build_vehicle():
        moved = g.moved(bd.Location(OFFSETS.get(g.label, (0.0, 0.0, 0.0))))
        moved.label = g.label
        groups.append(moved)
    rods = []
    for label, loc, ln, rot in (
        ("explode_guide_axis_z__annotation", (0, 0, 46000), 92000.0, (0, 0, 0)),
        ("explode_guide_axis_x__annotation", (0, 0, 21000), 18500.0, (0, 90, 0)),
    ):
        rod = bd.Cylinder(radius=60.0, height=ln, rotation=rot).locate(bd.Location(loc))
        rod.label = label
        rod.color = bd.Color("#c4c7ce73")
        rods.append(rod)
    groups.append(bd.Compound(obj=rods, children=rods, label="explode_guides_group"))
    return bd.Compound(obj=groups, children=groups,
                       label="falcon_heavy_exploded__educational_nonfunctional")


if __name__ == "__main__":
    falcon_heavy()
    falcon_heavy_cutaway()
    falcon_heavy_exploded()
