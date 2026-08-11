"""SpaceX Merlin 1D sea-level engine — exterior reconstruction (educational).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Exterior-only assembly: Rao-approximation bell, chamber envelope, injector
dome, thrust/gimbal structure, side-mounted turbopump + gas-generator
exterior placeholders, turbine exhaust duct, feed lines and valves, harness,
sensors, and dense decorative hardware (bolt rings, bands, bellows, clamps).
See RESEARCH.md and PROVENANCE.md for per-component source metadata.
"""

from build123d import Compound

import merlin_common as mc

DISPLAY_NAME = mc.DISPLAY_NAME


def gen_step():
    groups = mc.build_exterior()
    return Compound(
        obj=groups,
        children=groups,
        label="merlin1d_sea_level_exterior__educational_public_source_reconstruction",
    )
