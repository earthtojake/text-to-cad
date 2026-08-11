"""SpaceX Raptor Vacuum (RVac) — derived exterior reconstruction (educational).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Derived variant of the Raptor 2 sea-level model: identical simplified
powerhead, nozzle extended to a vacuum expansion ratio of ~80 (Musk statement,
MEDIUM confidence; exit radius and bell length are schematic Rao-approximation
derivations, LOW confidence). The real RVac is fixed-mounted; the mount block
here is the same simplified placeholder as the sea-level model. Coordinates:
centerline = Z, vacuum nozzle exit plane = Z=0, engine extends +Z
(~4.39 m tall). See RESEARCH.md and PROVENANCE.md.
"""

from build123d import Compound

import raptor2_common as rc

DISPLAY_NAME = "SpaceX Raptor Vacuum (educational public-source reconstruction, derived variant)"


def gen_step():
    groups = rc.build_vacuum_exterior()
    return Compound(
        obj=groups,
        children=groups,
        label="raptor_vacuum_exterior__educational_public_source_reconstruction",
    )
