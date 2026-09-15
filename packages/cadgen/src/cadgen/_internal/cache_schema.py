"""Compatibility identity for component extraction inputs.

``CACHE_SCHEMA_VERSION`` participates in a component's input hash together
with its exact BREP bytes and normalized face colors. Changing the extraction
scheme prevents reuse through an older component input key. Immutable object
addresses remain hashes of their bytes, and document keys remain hashes of
the actual saved file. There are no version-salted package directories.

This is not a universal store-reset switch. Model/document index payloads,
operation keys, SURF containers and tessellation payloads validate their own
compatibility contracts. A component scheme change alone does not invalidate
an otherwise accepted saved-document mapping. Persistent deletion remains the
explicit ``cadgen store gc`` operation.

Keep this module free of kernel imports. The historical notes below describe
the extraction cutovers when introduced; current builds distinguish authored
result trees from canonical trees derived from saved STEP bytes.
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
# 20: STEP writing preserves different whole-part colours on occurrences that
# share one native TShape. STEPCAF otherwise merges their definitions and
# writes only the last colour. Component identities move, and the accompanying
# model-record schema cutover makes the next ordinary source run regenerate the
# formerly wrong STEP bytes with the corrected writer. Saved documents remain
# documents: compiling one reparses its existing bytes and never guesses at
# source colors that those bytes lost.
CACHE_SCHEMA_VERSION = 20
