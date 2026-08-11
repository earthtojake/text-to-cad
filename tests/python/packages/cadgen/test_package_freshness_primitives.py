"""``cadgen._internal.package_freshness`` — the primitives BOTH freshness authorities share.

The viewer's validator and the producer's ``is_current`` callables must answer the same
question the same way, so the comparisons themselves live in one stdlib-only module. Two
properties are pinned here: the semantics (strict, no tolerant reads) and the import
purity that lets the viewer's long-lived server process use it at all.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.package_freshness import (  # noqa: E402
    ASSEMBLY_PACKAGE_SCHEMA_VERSION,
    bake_hash_matches,
    canonical_bake_hash,
    descriptor_bake_hash,
    schema_version_matches,
)

_CADGEN_SRC = str(Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src")


class CanonicalBakeHashTests(unittest.TestCase):
    def test_no_settings_hashes_to_none(self):
        # A format that bakes nothing (STEP today) has no bake to compare.
        self.assertIsNone(canonical_bake_hash(None))

    def test_key_order_is_not_content(self):
        self.assertEqual(
            canonical_bake_hash({"a": 1, "nested": {"x": 1, "y": 2}}),
            canonical_bake_hash({"nested": {"y": 2, "x": 1}, "a": 1}),
        )

    def test_every_value_change_changes_the_hash(self):
        base = {"detailMode": "full", "showTravel": True, "extrusionWidthMm": 0.42}
        for key, changed in (
            ("detailMode", "coarse"),
            ("showTravel", False),
            ("extrusionWidthMm", 0.43),
        ):
            with self.subTest(key=key):
                self.assertNotEqual(
                    canonical_bake_hash(base), canonical_bake_hash({**base, key: changed})
                )
        # An added or removed setting counts too.
        self.assertNotEqual(canonical_bake_hash(base), canonical_bake_hash({**base, "zBias": 8}))

    def test_array_order_is_content(self):
        self.assertNotEqual(
            canonical_bake_hash({"layers": [1, 2]}), canonical_bake_hash({"layers": [2, 1]})
        )

    def test_digest_is_pinned(self):
        # Changing the canonicalization silently invalidates every package on every
        # machine. It may change -- but not by accident.
        self.assertEqual(
            "62ecee723bd4f0a64c1aab6f001f2b135a454ce643777e114a684b293bb3bffc",
            canonical_bake_hash(
                {"detailMode": "full", "showTravel": True, "extrusionWidthMm": 0.42}
            ),
        )

    def test_unserializable_settings_raise_rather_than_hash_around_them(self):
        with self.assertRaises(ValueError):
            canonical_bake_hash({"tolerance": float("nan")})
        with self.assertRaises(TypeError):
            canonical_bake_hash({"path": Path("/tmp/x")})


class BakeHashMatchTests(unittest.TestCase):
    def test_recorded_hash_is_read_strictly(self):
        self.assertIsNone(descriptor_bake_hash({}))
        self.assertIsNone(descriptor_bake_hash({"bakeHash": "  "}))
        self.assertIsNone(descriptor_bake_hash({"bakeHash": 5}))
        self.assertEqual("abc", descriptor_bake_hash({"bakeHash": " abc "}))

    def test_settings_change_invalidates_a_recorded_bake(self):
        recorded = {"bakeHash": canonical_bake_hash({"widthMm": 0.42})}
        self.assertTrue(bake_hash_matches(recorded, canonical_bake_hash({"widthMm": 0.42})))
        self.assertFalse(bake_hash_matches(recorded, canonical_bake_hash({"widthMm": 0.43})))

    def test_it_is_strict_in_both_directions(self):
        # A format that bakes settings must not accept a descriptor without a bake...
        self.assertFalse(bake_hash_matches({}, canonical_bake_hash({"widthMm": 0.42})))
        # ...and a format that bakes nothing must not accept one that carries a bake.
        self.assertFalse(bake_hash_matches({"bakeHash": "abc"}, None))
        self.assertTrue(bake_hash_matches({}, None))


class SchemaVersionGateTests(unittest.TestCase):
    def test_exact_int_equality_only(self):
        current = ASSEMBLY_PACKAGE_SCHEMA_VERSION
        self.assertTrue(schema_version_matches({"packageSchemaVersion": current}, current))
        for recorded in (
            None,
            current - 1,
            current + 1,
            str(current),
            float(current),
            True,
        ):
            with self.subTest(recorded=recorded):
                self.assertFalse(
                    schema_version_matches({"packageSchemaVersion": recorded}, current)
                )

    def test_a_descriptor_that_records_nothing_is_not_current(self):
        self.assertFalse(schema_version_matches({}, ASSEMBLY_PACKAGE_SCHEMA_VERSION))

    def test_the_emitter_stamps_the_shared_constant(self):
        # component_package writes the descriptor; the viewer cannot import it (CAD
        # runtime). One constant, or the two sides drift by exactly one bump.
        from cadgen._internal.component_package import PACKAGE_SCHEMA_VERSION

        self.assertEqual(ASSEMBLY_PACKAGE_SCHEMA_VERSION, PACKAGE_SCHEMA_VERSION)


_PROBE = """
import json, sys
sys.path.insert(0, {src!r})
import cadgen._internal.package_freshness  # noqa: F401
print(json.dumps(sorted(m for m in ("OCP", "build123d", "ezdxf") if m in sys.modules)))
"""


class ImportPurityTest(unittest.TestCase):
    """The viewer's server imports this module. If it ever drags in a CAD runtime, the
    long-lived process pays for OCP on startup -- the invariant that made sharing the
    producer's code with the viewer safe in the first place. Fresh interpreter: asserting
    on sys.modules in this one would just measure what the rest of the suite imported."""

    def test_import_pulls_in_no_cad_runtime(self):
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE.format(src=_CADGEN_SRC)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual([], json.loads(proc.stdout.strip().splitlines()[-1]))


if __name__ == "__main__":
    unittest.main()
