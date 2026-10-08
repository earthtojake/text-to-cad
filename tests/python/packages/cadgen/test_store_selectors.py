"""The selector index (STORE.md §2): a component's selector table, derived with its
surface, keyed by the surface input and the table scheme, and carried by a view
beside the ``.surf`` for the CLI's readers. A tiny box in a fresh store."""

from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen.store import selectors, surfaces  # noqa: E402
from cadgen.store.build import build_tree_from_compound  # noqa: E402
from cadgen.store.index import entry_path, remove_entry  # noqa: E402
from cadgen.store.objects import read_verified_object  # noqa: E402


class SelectorStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = generated_cad_directory(prefix="selector-store-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store"), "CADGEN_DAEMON": "0"})
        env.start()
        self.addCleanup(env.stop)
        from build123d import Solid

        self.tree, _, _ = build_tree_from_compound(Solid.make_box(1, 2, 3), root_name="box")
        self.producer = surfaces.producer_identity()
        view = surfaces.request_view(self.tree, producer=self.producer)
        self.cid, self.entry = next(iter(view["components"].items()))
        self.key = selectors.selector_key(self.entry["surfaceInput"])

    def test_derive_stores_the_table_beside_the_surface_and_a_hit_is_a_read(self) -> None:
        record = surfaces.derive(self.tree)[self.cid]
        table = selectors.probe(self.key)
        self.assertEqual(table["surfaceObject"], record["object"])
        self.assertEqual((table["faceCount"], table["edgeCount"], table["vertexCount"]), (6, 12, 8))
        payload = selectors.read(self.key)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), table["object"])
        self.assertEqual(json.loads(payload)["stats"]["faceCount"], 6)
        written = entry_path("selector", self.key).stat().st_mtime_ns
        surfaces.derive(self.tree)
        self.assertEqual(entry_path("selector", self.key).stat().st_mtime_ns, written, "a second derive writes nothing")

    def test_a_missing_table_is_derived_again_from_the_stored_surface(self) -> None:
        surfaces.derive(self.tree)
        first = selectors.probe(self.key)
        remove_entry("selector", self.key)
        self.assertIsNone(selectors.probe(self.key))
        surfaces.derive(self.tree)
        self.assertEqual(selectors.probe(self.key), first, "the same inputs give the same table")

    def test_keys_name_the_scheme_and_an_older_one_is_obsolete(self) -> None:
        self.assertEqual(selectors.parse_key(self.key), self.entry["surfaceInput"])
        self.assertIsNone(selectors.parse_key(self.entry["surfaceInput"]))
        older = f"{self.entry['surfaceInput']}-s{selectors.SELECTOR_SCHEME - 1}"
        self.assertTrue(selectors.obsolete_key(older))
        self.assertFalse(selectors.obsolete_key(self.key))
        self.assertFalse(selectors.obsolete_key(f"{self.entry['surfaceInput']}-s{selectors.SELECTOR_SCHEME + 1}"))
        self.assertIsNone(selectors.probe(older))
        with self.assertRaises(ValueError):
            selectors.selector_key("not a digest")

    def test_write_refuses_a_foreign_payload_and_a_conflicting_table(self) -> None:
        record = surfaces.derive(self.tree)[self.cid]
        with self.assertRaises(ValueError):
            selectors.write(self.key, record["object"], b"{}")
        payload = selectors.read(self.key)
        altered = json.loads(payload)
        altered["faces"][0][6] = 123.0  # another area for the same input
        with self.assertRaises(selectors.SelectorConflictError):
            selectors.write(self.key, record["object"], json.dumps(altered, separators=(",", ":")).encode())

    def test_a_view_carries_the_table_beside_the_surface(self) -> None:
        from cadgen.store.view import SELECTOR_TABLE_SUFFIX, component_object_for_ref, export_view

        view_dir = export_view(self.tree, self.root / "view")
        descriptor = json.loads((view_dir / "assembly.json").read_text(encoding="utf-8"))
        entry = descriptor["components"][self.cid]
        table = selectors.probe(self.key)
        self.assertEqual(entry["selectorObject"], table["object"])
        self.assertEqual(entry["selectors"], f"components/{self.cid}{SELECTOR_TABLE_SUFFIX}")
        written = (view_dir / entry["selectors"]).read_bytes()
        self.assertEqual(written, read_verified_object(table["object"]))
        self.assertEqual(component_object_for_ref(entry["selectors"], descriptor), (table["object"], "selectors"))
        self.assertEqual(component_object_for_ref(entry["surf"], descriptor), (entry["surfaceObject"], "surf"))

    def test_the_cli_resolves_a_ref_to_the_row_the_table_names(self) -> None:
        from cadgen import assembly_lookup, lookup
        from cadgen.store.view import export_view

        view_dir = export_view(self.tree, self.root / "view")
        descriptor = json.loads((view_dir / "assembly.json").read_text(encoding="utf-8"))
        flat = lookup.build_selector_index({"tables": {"occurrenceColumns": ["id"]}, "occurrences": [["o1"]]})
        merged = assembly_lookup.merge_assembly_entities(
            assembly_lookup.merge_assembly_occurrences(flat, descriptor, view_dir), descriptor, view_dir)
        occurrence = descriptor["occurrences"][0]["id"]
        table = json.loads(selectors.read(self.key))
        columns = table["tables"]["faceColumns"]
        for row in table["faces"]:
            face = dict(zip(columns, row))
            found = lookup.lookup_selector(f"{occurrence}.{face['localId']}", merged)
            self.assertIsNotNone(found, f"{occurrence}.{face['localId']} resolves")
            self.assertEqual(found[0], "face")
            self.assertEqual(found[1]["ordinal"], face["ordinal"])
            self.assertEqual(found[1]["tangentGroup"], face["tangentGroup"])
        vertex = lookup.lookup_selector(f"{occurrence}.v1", merged)
        self.assertEqual(vertex[0], "vertex")
        self.assertEqual(len(lookup.vertex_adjacent_edge_selectors(vertex[1], merged)), 3)


if __name__ == "__main__":
    unittest.main()
