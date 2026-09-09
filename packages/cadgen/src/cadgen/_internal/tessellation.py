"""The tessellator's own default tolerances, mirrored from the JS source of truth.

There is exactly ONE tessellator in this repo and it is JavaScript: every render
mesh and every exported mesh comes out of ``tessellateComponent`` in
``packages/core/src/lib/surf/tessellate.js``. Its ``DEFAULT_OPTIONS`` are
the real defaults; the values below are a Python-side MIRROR, and what they
document is what an OMITTED tolerance means: a mesh export with no
``--mesh-tolerance`` (``MeshExportJob.mesh_tolerance is None``) is meshed at
exactly these numbers. Nothing on the Python side substitutes them — the
tessellator applies its own — so this module is a pinned statement of fact
rather than a source of values.

Both are RELATIVE — a fraction of the component's bounding diagonal, not
millimetres. The absolute OCCT "deflection" constants that used to sit in
``cadgen.metadata`` described a mesher this package no longer contains.

``tests/python/global/test_cache_root_sync.py`` pins these against
``DEFAULT_OPTIONS`` in tessellate.js, the same way it pins the tessellator
version salt. Change one side and that test fails before the drift can ship.
"""

from __future__ import annotations


# Max 3D distance between the surface and a triangle edge midpoint, relative to
# the component diagonal (tessellate.js DEFAULT_OPTIONS.chordTolerance).
TESSELLATOR_CHORD_TOLERANCE = 1.5e-3

# Max normal spread across one triangle edge, in radians
# (tessellate.js DEFAULT_OPTIONS.angleTolerance).
TESSELLATOR_ANGLE_TOLERANCE = 0.35
