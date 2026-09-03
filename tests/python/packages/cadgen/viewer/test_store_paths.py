"""``cadgen.viewer.store_paths``: the server's string-typed view of cadgen's store.

The adapter delegates to ``cadgen.catalog`` and ``cadgen.store``; what is pinned
here is its own contract: string results, per-call environment reads, and the
document -> record resolution the routes depend on.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from cadgen import catalog
from cadgen._internal import source_sidecar
from cadgen.viewer import store_paths

from tests.python.support.store_fixtures import seed_result


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

    def test_the_roots_are_cadgen_paths_as_strings(self) -> None:
        from cadgen.store.paths import locks_dir, store_root

        self.assertEqual(store_paths.cadgen_cache_root_dir(), str(store_root()))
        self.assertEqual(store_paths.store_locks_dir(), str(locks_dir()))
        self.assertIsInstance(store_paths.coordination_scope(self.probes[0]), str)

    def test_every_key_matches_cadgen_for_real_aliased_and_missing_paths(self) -> None:
        for probe in self.probes:
            with self.subTest(probe=probe):
                path = Path(probe)
                self.assertEqual(store_paths.artifact_file_hash(probe), catalog.artifact_file_hash(path))
                self.assertEqual(store_paths.artifact_path_key(probe), catalog.artifact_path_key(path))
                self.assertEqual(store_paths.coordination_scope(probe), str(catalog.coordination_scope(path)))
                self.assertEqual(
                    store_paths.source_sidecar_path(probe),
                    str(source_sidecar.source_sidecar_path(Path(os.path.abspath(probe)))),
                )

    def test_an_unbuilt_document_has_no_tree_and_no_record(self) -> None:
        self.assertIsNone(store_paths.result_tree(self.probes[0]))
        self.assertIsNone(store_paths.record_for(self.probes[0]))
        self.assertIsNone(store_paths.result_descriptor("f" * 64))

    def test_a_seeded_document_resolves_to_its_tree_through_the_alias_too(self) -> None:
        tree = seed_result(self.probes[0])
        for probe in self.probes[:2]:
            with self.subTest(probe=probe):
                self.assertEqual(store_paths.result_tree(probe), tree)
                descriptor = store_paths.result_descriptor(tree)
                self.assertEqual(descriptor["kind"], "assembly-package")
                (component,) = descriptor["components"].values()
                self.assertTrue(component["surf"].startswith("components/"))
                self.assertTrue(store_paths.component_object_present(component["surfObject"]))

    def test_the_virtual_store_asset_serves_the_tree_and_its_components(self) -> None:
        tree = seed_result(self.probes[0], surf=b"SURF\x00\x01")
        body, content_type = store_paths.virtual_store_asset(f"{tree}/assembly.json")
        self.assertEqual(content_type, "application/json")
        self.assertIn(b'"kind": "assembly-package"', body)
        descriptor = store_paths.result_descriptor(tree)
        (component,) = descriptor["components"].values()
        payload, content_type = store_paths.virtual_store_asset(f"{tree}/{component['surf']}")
        self.assertEqual(Path(payload).read_bytes(), b"SURF\x00\x01")
        self.assertEqual(content_type, "application/octet-stream")
        for bad in ("", "/etc/hosts", f"{tree}/../x", f"{tree}/components/nope.surf", "zz/assembly.json"):
            with self.subTest(bad=bad):
                self.assertEqual(store_paths.virtual_store_asset(bad), (None, ""))


class ReadPerCall(unittest.TestCase):
    """Never memoised: the suites flip ``CADGEN_CACHE_DIR`` after import."""

    def test_the_root_follows_the_environment_on_every_call(self) -> None:
        previous = os.environ.get("CADGEN_CACHE_DIR")
        try:
            os.environ["CADGEN_CACHE_DIR"] = "/tmp/first"
            self.assertEqual(store_paths.cadgen_cache_root_dir(), "/tmp/first")
            os.environ["CADGEN_CACHE_DIR"] = "/tmp/second"
            self.assertEqual(store_paths.cadgen_cache_root_dir(), "/tmp/second")
        finally:
            if previous is None:
                os.environ.pop("CADGEN_CACHE_DIR", None)
            else:
                os.environ["CADGEN_CACHE_DIR"] = previous


if __name__ == "__main__":
    unittest.main()
