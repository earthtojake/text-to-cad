---
name: mesh-qa
description: Programmatic printability and geometry-health validation for generated mesh/STEP/STL parts using trimesh and slicer dry-run output. Use when a part produced by the CAD skill needs pre-print geometric verification, when writing pytest checks for watertightness, wall thickness, bounding-box dimensions, overhang or support requirements, or when turning slicer validation output into automated assertions.
---

# Mesh QA

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill after a part has been generated with the CAD skill and needs
programmatic printability or geometry-health validation before slicing or
printing. This skill is a tool guide: it documents what trimesh and the
gcode skill's validation output offer, not which checks you must run. You
decide which checks are meaningful for the part at hand, based on the
user's requirements and any design note for the task.

## Core Rules

1. You own the check selection. No file in this skill mandates a test for a
   part type. Read the part's requirements and design note, then choose the
   checks that actually verify them.
2. Threshold values in `references/printability-heuristics.md` are
   reference-only typical FDM ranges, never binding defaults. State the
   basis for every threshold you assert (user requirement, design note, or
   reference value you judged applicable).
3. Write part tests as pytest files under `tests/generated/<part-name>/`,
   one directory per part. Use the skeleton below as a starting shape, not
   as a fixed contract.
4. Assert against the design intent, not against whatever the current mesh
   happens to measure. A test that only mirrors measured values cannot
   catch regressions.
5. Keep generated CAD/robot artifacts under the workspace `models/` area or
   the owning project layout; keep test code under `tests/generated/`.
6. Prefer fixing the CAD source over weakening a failing assertion. When a
   threshold itself turns out wrong, say so and correct the test with a
   stated reason.

## Workflow

1. Load the generated artifact (STEP, STL, 3MF, or OBJ) with trimesh. STEP
   files need a prior export to a mesh format; use the CAD skill's export
   workflow if only STEP exists.
2. Pick the checks that matter for this part: structural sanity
   (watertight, winding-consistent, single connected component, positive
   volume), dimensional intent (bounding-box extents, feature-level
   measurements), printability (local wall thickness, overhang/support
   expectations from a slicer dry run). See `references/trimesh-api.md`.
3. When slicer-level evidence matters, run the gcode skill's slice/validate
   workflow and convert its output (support requirements, overhang
   warnings, out-of-bounds motion) into assertions.
4. Write the pytest file(s) under `tests/generated/<part-name>/` and run
   them with the project Python environment.
5. On failure, read the assertion output, fix the CAD source, regenerate
   the artifact, and rerun. Respect the iteration budget of the task's
   orchestration loop.

## Test Skeleton

Adapt this shape; delete or replace any assertion that does not serve the
part's actual requirements:

```python
import trimesh

import pytest


@pytest.fixture(scope="module")
def mesh():
    return trimesh.load("models/<part-name>/<part-name>.stl", force="mesh")


def test_structural_sanity(mesh):
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.volume > 0


def test_dimensions(mesh):
    extents = mesh.bounding_box.extents  # millimeters, XYZ
    assert extents[0] == pytest.approx(EXPECTED_X, abs=TOLERANCE)
```

## Tools

Install the skill dependencies into the project Python environment:

```bash
pip install -r requirements.txt
```

`trimesh` is the primary library; `numpy` backs its array API; `rtree`
enables spatial queries used by proximity and containment checks. See
`references/trimesh-api.md` for the API surface and copyable snippets, and
`references/printability-heuristics.md` for reference-only FDM value
ranges.

## CAD Viewer Handoff

Automated mesh QA is a separate layer from visual review. When the task
also needs a human-facing preview of the checked part, hand the artifact
path to `$cad-viewer`; do not treat a passing test suite as a substitute
for visual inspection, or vice versa.

## References

- trimesh API surface and code snippets: `references/trimesh-api.md`
- FDM printability reference values (non-binding):
  `references/printability-heuristics.md`
