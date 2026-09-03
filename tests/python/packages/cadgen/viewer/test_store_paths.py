"""``cadgen.viewer.store_paths``: the server's string-typed view of cadgen's store layout.

There used to be a parity suite here, comparing a local stdlib copy of the store
layout against cadgen's over a matrix of environment states. The copy is gone --
the adapter delegates to ``cadgen.catalog`` and friends -- so what remains to
pin is the adapter's own contract: string results, per-call environment reads,
and the content-keying properties the routes depend on.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from cadgen import catalog
from cadgen._internal import cache_paths, source_sidecar
from cadgen.viewer import store_paths


class DelegatesToCadgen(unittest.TestCase):
    """Every helper is cadgen's answer, spelled as ``str``."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        previous = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = os.path.join(self.tmp.name, "cache")
        self.addCleanup(
            lambda: os.environ.__setitem__("CADGEN_CACHE_DIR", previous)
            if previous is not None
            else os.environ.pop("CADGEN_CACHE_DIR", None)
        )
        os.makedirs(os.path.join(self.tmp.name, "real", "sub"))
        Path(self.tmp.name, "real", "sub", "part.step").write_text("body\n", encoding="utf-8")
        os.symlink(os.path.join(self.tmp.name, "real"), os.path.join(self.tmp.name, "alias"))
        self.probes = [
            os.path.join(self.tmp.name, "real", "sub", "part.step"),
            os.path.join(self.tmp.name, "alias", "sub", "part.step"),
            os.path.join(self.tmp.name, "real", "sub", "gone.step"),
            os.path.join(self.tmp.name, "alias", "sub", "gone.step"),
        ]

    def test_the_tiers_are_cadgen_paths_as_strings(self) -> None:
        self.assertEqual(store_paths.cadgen_cache_root_dir(), str(cache_paths.cache_root()))
        self.assertEqual(store_paths.store_packages_dir(), str(cache_paths.packages_dir()))
        self.assertEqual(store_paths.store_locks_dir(), str(cache_paths.locks_dir()))
        self.assertEqual(store_paths.store_records_dir(), str(cache_paths.records_dir()))
        for value in (
            store_paths.cadgen_cache_root_dir(),
            store_paths.store_packages_dir(),
            store_paths.render_package_dir(self.probes[0]),
        ):
            self.assertIsInstance(value, str)

    def test_every_key_matches_cadgen_for_real_aliased_and_missing_paths(self) -> None:
        for probe in self.probes:
            with self.subTest(probe=probe):
                path = Path(probe)
                self.assertEqual(store_paths.artifact_path_key(probe), catalog.artifact_path_key(path))
                self.assertEqual(store_paths.render_package_dir(probe), str(catalog.render_package_dir(path)))
                self.assertEqual(store_paths.coordination_scope(probe), str(catalog.coordination_scope(path)))
                self.assertEqual(
                    store_paths.source_provenance_record_path(probe),
                    str(source_sidecar.provenance_record_path(path)),
                )
                self.assertEqual(
                    store_paths.source_sidecar_path(probe),
                    str(source_sidecar.source_sidecar_path(path)),
                )
                self.assertEqual(store_paths.artifact_file_hash(probe), catalog.artifact_file_hash(path))

    def test_the_constants_are_cadgens(self) -> None:
        from cadgen._internal.cache_schema import CACHE_SCHEMA_VERSION

        self.assertEqual(store_paths.CACHE_SCHEMA_VERSION, CACHE_SCHEMA_VERSION)
        self.assertEqual(store_paths.SOURCE_SIDECAR_SUFFIX, source_sidecar.SOURCE_SIDECAR_SUFFIX)
        self.assertEqual(
            store_paths.SOURCE_SIDECAR_SCHEMA_VERSION, source_sidecar.SOURCE_SIDECAR_SCHEMA_VERSION
        )
        self.assertEqual(
            store_paths.package_dir_for_hash("f" * 64), str(catalog.package_dir_for_hash("f" * 64))
        )


class ReadPerCall(unittest.TestCase):
    def test_the_cache_root_is_never_memoised(self):
        # The suites set CADGEN_CACHE_DIR after the app is constructed and
        # expect the very next call to observe it. A module-level constant
        # would pass every other test in this file and fail this one.
        previous = os.environ.get("CADGEN_CACHE_DIR")
        try:
            os.environ["CADGEN_CACHE_DIR"] = "/tmp/first"
            self.assertEqual(store_paths.store_packages_dir(), os.path.join("/tmp/first", "packages"))
            os.environ["CADGEN_CACHE_DIR"] = "/tmp/second"
            self.assertEqual(store_paths.store_packages_dir(), os.path.join("/tmp/second", "packages"))
        finally:
            if previous is None:
                os.environ.pop("CADGEN_CACHE_DIR", None)
            else:
                os.environ["CADGEN_CACHE_DIR"] = previous


class ContentKeying(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        previous = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = os.path.join(self.tmp.name, "cache")
        self.addCleanup(
            lambda: os.environ.__setitem__("CADGEN_CACHE_DIR", previous)
            if previous is not None
            else os.environ.pop("CADGEN_CACHE_DIR", None)
        )

    def test_the_hash_memo_notices_a_content_change(self):
        # The memo is keyed on (mtime_ns, size): a stale hit would need an edit
        # preserving BOTH. Back-to-back same-size writes DO preserve both on
        # Windows, whose file times advance in ~15ms ticks, so the edit is
        # stamped forward explicitly -- the memo must honour mtime, not just size.
        path = os.path.join(self.tmp.name, "a.step")
        Path(path).write_bytes(b"one\n")
        first = store_paths.artifact_file_hash(path)
        stat = os.stat(path)
        later = (stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000)
        Path(path).write_bytes(b"two\n")
        os.utime(path, ns=later)
        second = store_paths.artifact_file_hash(path)
        self.assertNotEqual(second, first)
        # And a size change at an UNCHANGED mtime is noticed too.
        Path(path).write_bytes(b"three\n")
        os.utime(path, ns=later)
        self.assertNotEqual(store_paths.artifact_file_hash(path), second)

    def test_a_missing_file_hashes_to_none_rather_than_raising(self):
        self.assertIsNone(store_paths.artifact_file_hash(os.path.join(self.tmp.name, "gone.step")))

    def test_a_directory_named_like_a_step_hashes_to_none(self):
        directory = os.path.join(self.tmp.name, "dir.step")
        os.makedirs(directory)
        self.assertIsNone(store_paths.artifact_file_hash(directory))

    def test_a_path_that_cannot_be_resolved_still_keys_rather_than_raising(self):
        # A request can name anything. An embedded NUL cannot be resolved by the
        # filesystem; the server must answer "no package", not 500.
        odd = os.path.join(self.tmp.name, "nul\x00.step")
        key = store_paths.artifact_path_key(odd)
        self.assertEqual(len(key), 24)
        self.assertIsNone(store_paths.artifact_file_hash(odd))
        self.assertTrue(os.path.basename(store_paths.render_package_dir(odd)).startswith("unbuilt-"))

    def test_the_unbuilt_path_is_deterministic_and_never_created(self):
        missing = os.path.join(self.tmp.name, "gone.step")
        unbuilt = store_paths.render_package_dir(missing)
        self.assertEqual(unbuilt, store_paths.render_package_dir(missing))
        self.assertTrue(os.path.basename(unbuilt).startswith("unbuilt-"))
        self.assertFalse(os.path.exists(unbuilt))

    def test_the_path_key_is_24_hex_characters(self):
        key = store_paths.artifact_path_key(os.path.join(self.tmp.name, "x.step"))
        self.assertEqual(len(key), 24)
        self.assertTrue(all(c in "0123456789abcdef" for c in key))


if __name__ == "__main__":
    unittest.main()
