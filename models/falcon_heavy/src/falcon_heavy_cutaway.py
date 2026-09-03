"""SpaceX Falcon Heavy — center-core cutaway (educational reconstruction).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Center core, second stage, and fairing sectioned 270 deg (opening +Y) with
schematic interiors: LOX/RP-1 tank volumes, transfer tube, domes, COPV-like
placeholders, octaweb frames, avionics/separation placeholders, payload
adapter + payload placeholder. All internals schematic and non-functional.
"""
from __future__ import annotations
from cadgen import step
from cadgen import build123d as bd
from lib import falcon_common as fc


@step(out="../STEP/falcon_heavy_cutaway.step")
def falcon_heavy_cutaway():
    groups = fc.build_vehicle(cutaway=True)
    return bd.Compound(obj=groups, children=groups,
                    label="falcon_heavy_cutaway__educational_nonfunctional")


if __name__ == "__main__":
    falcon_heavy_cutaway()
