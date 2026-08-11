"""Python port of the CAD Viewer backend.

This package reproduces the Node viewer backend (viewer/src/server) so the
unchanged React/Three.js client can talk to a Python server byte-for-byte.

Fidelity is the hard part of this migration, not capability: a handful of
encoders (base36 cache tokens, ``encodeURIComponent``-equivalents,
``URLSearchParams`` form encoding, RFC5987 Content-Disposition, the two
hand-written content-type maps, and ``localeCompare`` natural sort) must match
the JS output exactly or the client silently breaks (cache busts, 404s on
sub-assets, reordered trees). Those primitives live in ``encoding.py``,
``content_types.py`` and ``natural_sort.py`` and are pinned against
Node-generated golden fixtures (see ``tests/gen_golden.mjs``).
"""
