"""SpaceX Falcon Heavy — full-stack exterior (educational reconstruction).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Three cores with 27 linked Merlin 1D instances (octaweb 8+1 per core, reduced
decorative detail), MVac-derivative second stage, interstage, fairing, grid
fins, landing legs, raceways, attach hardware. See RESEARCH.md/PROVENANCE.md.
"""
from build123d import Compound
import falcon_common as fc

DISPLAY_NAME = fc.DISPLAY_NAME


def gen_step():
    groups = fc.build_vehicle()
    return Compound(obj=groups, children=groups,
                    label="falcon_heavy__educational_public_source_reconstruction")
