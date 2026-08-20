"""Descriptor-level freshness primitives shared by BOTH freshness authorities.

A render package's currency is decided twice, by design: the viewer's validator
(``viewer/server_py/artifact.py``) decides what a status GET answers, and the producer's
per-kind ``is_current`` callable — re-evaluated under the generation lock — decides
whether a build no-ops. When the two disagree the failure is SILENT rather than loud: the
producer reports ``skipped``, the request settles ``ready``, and the stale package
renders. So a check added to one side must be added to the other.

These primitives live here, and not in either caller, because this module is stdlib-only:
the viewer's long-lived server process can import it without dragging OCP/build123d/ezdxf
into itself, exactly as it already imports ``cadgen._internal.source_hash``. Sharing the
code is what makes the two sides agree by construction instead of by review.

No tolerant reads. A descriptor either records what the current producer records, or the
package is stale and gets rebuilt (``__cadgen__/`` is a gitignored per-machine cache, so
invalidation costs one lazy rebuild per entry actually reopened).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

# One number per file type covers everything about how that type's package was produced:
# the descriptor's layout AND the bytes inside the payloads it references. Bumping it both
# makes the viewer's validator refuse existing packages and (for STEP, via the component cid
# salt in _internal.component_package) forces the payloads to be re-emitted rather than
# reused by geometry. Splitting those two into separate numbers is how a fix ships half
# applied: the descriptor advances while content-addressed payloads are reused unchanged.
#
# Deliberately per file type, not one number for all of them: a drawing rebuild is
# milliseconds and a large STEP assembly is tens of seconds, so a DXF change must not
# re-mesh every STEP model on next open.
#
# 3: the topology extractor's curveType/continuity names were corrupted by a memoization
#    collision between the numerically overlapping GeomAbs_* enum families (see
#    _internal.step_scene._enum_name), so every package built before that fix records
#    surface names on its edges.
STEP_PACKAGE_VERSION = 3

SCHEMA_VERSION_FIELD = "packageSchemaVersion"
BAKE_HASH_FIELD = "bakeHash"


def canonical_bake_hash(bake: Mapping[str, Any] | None) -> str | None:
    """sha256 over the canonicalized ``bake`` block, or None when a format bakes nothing.

    The bake block is the format-specific settings a build froze into its payload
    (toolpath widths, implicit resolution, DXF thickness). Those settings are invisible to
    every other freshness signal — the source is unchanged, the payload is present, the
    closure still hashes — so without this a settings change leaves stale artifacts
    rendering silently.

    Canonical means: JSON with sorted keys (recursively) and no insignificant whitespace.
    Array order is content, and is preserved. Non-JSON values raise rather than hashing to
    something that silently ignores them.
    """
    if bake is None:
        return None
    canonical = json.dumps(
        bake, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def descriptor_bake_hash(descriptor: Mapping[str, Any]) -> str | None:
    """The ``bakeHash`` a descriptor records, or None when it records none."""
    recorded = descriptor.get(BAKE_HASH_FIELD)
    if not isinstance(recorded, str):
        return None
    return recorded.strip() or None


def bake_hash_matches(descriptor: Mapping[str, Any], expected: str | None) -> bool:
    """True when the descriptor's recorded bake matches ``expected`` (both directions).

    ``expected`` is what :func:`canonical_bake_hash` returns for the format's CURRENT
    settings, so a settings change fails here. It is strict in both directions on purpose:
    a descriptor with no ``bakeHash`` for a format that bakes settings cannot be shown to
    be current, and a descriptor carrying one for a format that bakes nothing was written
    by a producer this build no longer is.
    """
    return descriptor_bake_hash(descriptor) == expected


def schema_version_matches(descriptor: Mapping[str, Any], expected: int) -> bool:
    """True when the descriptor records exactly ``expected`` as its schema version.

    Strict equality with no tolerance branch, mirroring
    ``cadgen.coordination.record``'s schema gate: a missing, non-integer, or older
    version is stale, not "probably fine".
    """
    recorded = descriptor.get(SCHEMA_VERSION_FIELD)
    if isinstance(recorded, bool) or not isinstance(recorded, int):
        return False
    return recorded == expected
