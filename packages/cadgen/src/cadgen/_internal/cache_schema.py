"""The ONE cache-scheme number.

``CACHE_SCHEMA_VERSION`` is the store generation: it salts every render
package's directory key (``<sha256(document)>-v<N>``, ``cadgen.catalog``)
and the component cids inside packages. Bumping it is the whole migration
story — old-generation artifacts simply stop resolving (orphaned BY NAME,
swept by ``cadgen cache gc``) and everything regenerates on demand at the
new key. Nothing is ever migrated in place, and no artifact records a
version inside itself: a tree that resolves at all IS current-scheme by
construction.

Bump it whenever anything about a tree's meaning or payloads changes:
the assembly.json shape, the ``.surf`` container (``SURF_VERSION``), the
embedded topology tables, component serialization — one number, one
signal, one regeneration.

Stdlib-only on purpose: the viewer's mirror is ``CACHE_SCHEMA_VERSION``
in ``apps/viewer/server/store_paths.py``, pinned against this literal by
``tests/python/global/test_render_contract_sync.py`` so a one-sided bump
cannot ship.
"""

# 17: the assembly.json's ``mesh`` section is gone. A tree stores
# surfaces, not triangles, so the deflection numbers it recorded described a
# mesher this package no longer contains, and the adaptive ``resolution``
# beside them was the input to a decision the assembly.json already records the
# output of (``edgeRendering.visibilityClasses``).

# 18: periodic spline surfaces are extracted over their ACTIVE parameter
# domain. ``SetNotPeriodic`` retains extension knots outside it, and the
# extractor read the first stored knot as the domain start, translating such a
# surface a whole period out of the face's frame (PR #370 bug record 034). The geometry a
# component hashes to is unchanged, so only the store generation can retire the
# ``.surf`` files — and the tessellation-cache entries keyed on their cid — that
# were written with the shifted knots. It retires the ``.surf`` files written by
# the other extractor fix in the same batch too, whose face and edge bboxes
# bounded a spline's CONTROL POLYGON instead of the surface (PR #370 bug record 004).

# 19: a model's own components are the geometry of the STEP it WROTE, re-read
# from that file, not the shapes the script returned. OCCT's STEP translation
# is lossy for some geometry (a trimmed rational surface can reload as its
# complementary cap: PR #370 bug records 028-030), so a tree serialized from the in-memory
# shapes described a solid the artifact did not contain, and a warm
# ``read_step`` disagreed with a cold parse of the same bytes. Every cid moves
# (the bytes are now the re-parsed BREP), and trees built from build-side
# shapes must stop resolving.
CACHE_SCHEMA_VERSION = 19
