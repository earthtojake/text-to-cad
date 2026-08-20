"""What an artifact kind has to supply to get coordination for free.

Adding a coordinated artifact format should be a constant here, not a fifth hand-placed
lock. Before this, four independent producers each decided for themselves whether to
lock -- and one of them did not, which is how a cold ``cad inspect`` build became invisible
to the viewer and raced a viewer-started build in the same directory.

A kind carries only what the coordination layer itself needs: a name for the status record
and the phase set its progress bar is weighted over. Freshness is deliberately NOT here --
``artifact_build`` takes ``is_current`` as a callable, so coordination calls freshness and
never decides what fresh means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from cadgen.coordination.phases import (
    PHASE_COMPONENTS,
    PHASE_FINALIZE,
    PHASE_GENERATE,
    PHASE_PACKAGE,
)


@dataclass(frozen=True)
class ArtifactKind:
    """One coordinated output format.

    ``name``   identifies the kind in status records.
    ``phases`` the phases this kind actually has, in order. The progress bar is weighted
               over exactly these, so a kind with no meshing stage does not reserve half
               its bar for one.
    ``labels`` human text for phases this kind introduces. PHASE_LABELS covers the shared
               ones; a kind with novel phases supplies its own here rather than growing
               that global dict, so an unrelated kind's vocabulary never leaks into
               another's bar. Merged OVER the shared labels, so a kind may also override.
    """

    name: str
    phases: tuple[str, ...] = (PHASE_GENERATE, PHASE_PACKAGE, PHASE_COMPONENTS, PHASE_FINALIZE)
    labels: Mapping[str, str] = field(default_factory=dict)


# A component-GLB render package: assembly.json + content-addressed components/<cid>.glb.
STEP_PACKAGE = ArtifactKind(name="step-package")

# Phases the JS builders introduce. None of the STEP phase names fit their work, so they
# declare their own here rather than growing the shared PHASE_LABELS dict.
PHASE_PARSE = "parse"
PHASE_MESH = "mesh"
PHASE_SAMPLE = "sample"
PHASE_POLYGONIZE = "polygonize"
PHASE_WELD = "weld"
PHASE_WRITE = "write"

# A DXF drawing package: drawing.json + drawing.dxf + preview.glb. The last three phases run
# in the NODE child (parse the drawing, mesh the flat pattern, write the GLB) while this
# process holds the lock, so they are declared here -- one run id and one status record span
# both runtimes, and the bar has to be weighted over the phases it will actually be told
# about.
DRAWING_PACKAGE = ArtifactKind(
    name="drawing-package",
    phases=(PHASE_GENERATE, PHASE_PARSE, PHASE_MESH, PHASE_WRITE, PHASE_FINALIZE),
    labels={
        PHASE_PARSE: "Reading drawing",
        PHASE_MESH: "Building preview",
        PHASE_WRITE: "Writing preview",
    },
)

# Implicit CAD: sampling an SDF over a grid, polygonizing it, welding, writing.

IMPLICIT_PACKAGE = ArtifactKind(
    name="implicit-package",
    phases=(PHASE_SAMPLE, PHASE_POLYGONIZE, PHASE_WELD, PHASE_WRITE),
    labels={
        PHASE_SAMPLE: "Sampling field",
        PHASE_POLYGONIZE: "Building surface",
        PHASE_WELD: "Welding vertices",
        PHASE_WRITE: "Writing package",
    },
)

# A snapshot render. Not a coordinated artifact -- it takes no lock and writes no status
# record, because it produces an image, not a package another process might read half-built.
# It is a kind anyway so its CLI reports through the same phase model as everything else;
# before this it had a second, unrelated progress implementation of its own.
#
# Note what is NOT a phase here: resolving the input. That step builds the STEP/drawing
# package when the model is cold, which is the slowest part of a whole snapshot -- and that
# build reports its OWN phases through artifact_build. Declaring a `resolve` phase here would
# put two painters on one terminal and replace the build's detail with the word "resolving".
PHASE_BROWSER = "browser"
PHASE_RENDER = "render"

SNAPSHOT = ArtifactKind(
    name="snapshot",
    phases=(PHASE_BROWSER, PHASE_RENDER),
    labels={PHASE_BROWSER: "Starting browser", PHASE_RENDER: "Rendering"},
)

# An export (STEP/STL/3MF/GLB/DXF) writes no package -- it occupies the model's GENERATOR
# and writes a file elsewhere -- so it is coordinated with generator_busy() against the
# model's own kind rather than being a kind of its own. Add one here when something needs
# to coordinate a directory these two do not cover.
