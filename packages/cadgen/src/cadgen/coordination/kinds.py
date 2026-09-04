"""What an artifact kind has to supply to get coordination for free.

Adding a reported artifact format should be a constant here, not a fifth hand-placed
progress implementation.

A kind carries only what progress reporting itself needs: a name for the status record
and the phase set its progress bar is weighted over. Freshness is deliberately NOT here --
``artifact_build`` takes ``is_current`` as a callable, so reporting calls freshness and
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
PHASE_WRITE = "write"

# A generated drawing: the product is the `.dxf` file itself (design/
# standalone-viewer.md Phase A — the viewer parses it directly; no package, no
# Node child). The phases are just the Python generator run and the file write.
DRAWING_PACKAGE = ArtifactKind(
    name="drawing-package",
    phases=(PHASE_GENERATE, PHASE_WRITE, PHASE_FINALIZE),
    labels={
        PHASE_WRITE: "Writing DXF",
    },
)

# A snapshot render. Not a reported artifact -- it writes no status record, because it
# produces an image, not an output another process might read half-built.
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
# and writes a file elsewhere -- so it is reported with generator_busy() against the
# model's own kind rather than being a kind of its own.

# `inspect validate`. Not a reported artifact either -- it writes no package -- but a
# check over a 2,500-occurrence assembly runs for many minutes,
# and it reports through the same phase model so the terminal line reads like a
# build's. Resolving the input is deliberately not a phase here for the same reason
# as SNAPSHOT: a stale document's rebuild paints its own line first.
PHASE_COLLECT = "collect"
PHASE_CHECK = "check"

VALIDATION = ArtifactKind(
    name="validation",
    phases=(PHASE_COLLECT, PHASE_CHECK),
    labels={PHASE_COLLECT: "Collecting parts", PHASE_CHECK: "Checking parts"},
)
