"""SpaceX Falcon Heavy — center-core cutaway (educational reconstruction).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Center core, second stage, and fairing sectioned 270 deg (opening +Y) with
schematic interiors: LOX/RP-1 tank volumes, transfer tube, domes, COPV-like
placeholders, octaweb frames, avionics/separation placeholders, payload
adapter + payload placeholder. All internals schematic and non-functional.
"""
from build123d import Compound
import falcon_common as fc

DISPLAY_NAME = "SpaceX Falcon Heavy cutaway (educational public-source reconstruction)"


def gen_step():
    groups = fc.build_vehicle(cutaway=True)
    return Compound(obj=groups, children=groups,
                    label="falcon_heavy_cutaway__educational_nonfunctional")
