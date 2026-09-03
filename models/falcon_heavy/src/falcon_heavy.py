"""SpaceX Falcon Heavy — full-stack exterior (educational reconstruction).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Three cores with 27 linked Merlin 1D instances (octaweb 8+1 per core, reduced
decorative detail), MVac-derivative second stage, interstage, fairing, grid
fins, landing legs, raceways, attach hardware. See RESEARCH.md/PROVENANCE.md.
"""
from __future__ import annotations
from cadgen import step
from cadgen import build123d as bd
from lib import falcon_common as fc


@step(out="../STEP/falcon_heavy.step")
def falcon_heavy():
    groups = fc.build_vehicle()
    return bd.Compound(obj=groups, children=groups,
                    label="falcon_heavy__educational_public_source_reconstruction")


if __name__ == "__main__":
    falcon_heavy()
