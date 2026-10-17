"""A part's display data (STORE.md §2): ONE record per part, keyed by what made the component
and the producer, naming its display mesh and selector table; derived once, read bound
to that record, and carried by a view for the CLI's readers; a part that fails to mesh is
named once the rest are stored. A tiny box in a fresh store."""

from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.inline_artifacts import inline_artifacts
from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen.store import meshes, parts  # noqa: E402
from cadgen.store.build import build_tree_from_compound  # noqa: E402
from cadgen.store.index import entry_path, remove_entry  # noqa: E402
from cadgen.store.objects import object_path  # noqa: E402
from cadgen.store.trees import capture_tree  # noqa: E402


class PartStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = generated_cad_directory(prefix="part-store-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store"), "CADGEN_DAEMON": "0"})
        env.start()
        self.addCleanup(env.stop)
        from build123d import Solid

        self.tree, _, _ = build_tree_from_compound(Solid.make_box(1, 2, 3), root_name="box")
        self.producer = parts.producer_identity()
        descriptor, _ = capture_tree(self.tree, retain_payloads=False)
        self.cid, self.entry = next(iter(descriptor["components"].items()))
        self.key = parts.part_key(self.entry, self.producer)

    def test_derive_stores_one_record_naming_both_objects_and_a_hit_is_a_read(self) -> None:
        record = parts.derive(self.tree)[self.cid]
        self.assertEqual(parts.probe(self.key), record)
        glb, table = parts.read(self.key, "glb"), parts.read(self.key, "selectors")
        self.assertEqual(meshes.body_facts(glb)["part"], self.key, "the mesh names its part")
        self.assertEqual(hashlib.sha256(table).hexdigest(), record["selectors"]["object"])
        self.assertEqual(json.loads(table)["stats"]["faceCount"], 6)
        self.assertEqual([record["selectors"][name] for name in ("faceCount", "edgeCount", "vertexCount")], [6, 12, 8])
        self.assertEqual([record["glb"][name] for name in ("faceCount", "edgeCount")], [6, 12],
                         "the mesh's faces and edges are the table's")
        written = entry_path("part", self.key).stat().st_mtime_ns
        self.assertEqual(parts.derive(self.tree), {self.cid: record})
        self.assertEqual(entry_path("part", self.key).stat().st_mtime_ns, written, "a second derive writes nothing")
        remove_entry("part", self.key)
        self.assertEqual(parts.derive(self.tree), {self.cid: record}, "the same inputs give the same part")

    def test_a_part_that_fails_to_mesh_is_named_once_the_rest_are_stored(self) -> None:
        from build123d import Box, Compound, Cylinder, Pos

        from cadgen._internal import tessellate

        tree, geometry, _ = build_tree_from_compound(
            Compound(children=[Box(4, 4, 4), Pos(10, 0, 0) * Cylinder(2, 4)]), root_name="pair")
        keys = [parts.part_key(entry, self.producer) for entry in geometry["components"].values()]
        real, failed = tessellate.mesh_component, []

        def mesher(topods, table, face_colors, *, part, **options):
            # Whatever fails, not only OCCT's own refusal: the first part meshed fails every
            # time, as a body its encoding refuses would.
            if failed in ([], [part]):
                failed[:] = [part]
                raise ValueError("invalid tessellation JSON length")
            return real(topods, table, face_colors, part=part, **options)

        def stored():
            return {key: parts.probe(key) is not None for key in keys}

        # A view's job names the component, after storing the other.
        named = r"^component [0-9a-f]{16}: ValueError: invalid tessellation JSON length$"
        with mock.patch.object(tessellate, "mesh_component", side_effect=mesher), \
                self.assertRaisesRegex(tessellate.MeshProductionError, named):
            parts.derive(tree)
        others = {key: key != failed[0] for key in keys}
        self.assertEqual(stored(), others, "the other part was stored before the failure was reported")
        # A build's job, asked for the part still missing, says the one failure as a line and
        # fails nothing (what the build then prints: test_build_derives_display).
        with inline_artifacts() as jobs, mock.patch.object(tessellate, "mesh_component", side_effect=mesher):
            [_failure] = parts.request_display(tree).wait()
        self.assertEqual([len(call.args[0]["cids"]) for call in jobs.call_args_list], [1], "one job, for the part missing")
        self.assertEqual(stored(), others)
        # An interrupt is not a part's failure.
        with inline_artifacts(), mock.patch.object(tessellate, "mesh_component", side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            parts.request_display(tree).wait()

    def test_a_large_batch_is_several_jobs_waited_for_as_one(self) -> None:
        """A batch of parts past ``_BATCH_BYTES`` goes to the daemon's pool as several jobs --
        a slot each, the caller's kept -- balanced by BREP size, and the build waits for them
        as one job; a small batch is one job, and so is any batch with no daemon, whose one
        process has no slots to spread it over."""
        from build123d import Box, Compound, Cylinder, Pos, Sphere

        bodies = [Box(4, 4, 4), Pos(10, 0, 0) * Cylinder(2, 4), Pos(20, 0, 0) * Sphere(3), Pos(30, 0, 0) * Box(1, 2, 3)]
        tree, geometry, _ = build_tree_from_compound(Compound(children=bodies), root_name="row")
        keys = {cid: parts.part_key(entry, self.producer) for cid, entry in geometry["components"].items()}

        def request(*, daemon: bool) -> list[list[str]]:
            for key in keys.values():
                remove_entry("part", key)
            with inline_artifacts() as jobs, mock.patch.object(parts, "_BATCH_BYTES", 1), \
                    mock.patch("cadgen.daemon.broker.job_limit", return_value=3), \
                    mock.patch("cadgen.daemon.executors.use_daemon", return_value=daemon):
                job = parts.request_display(tree)
                heard = []
                job.when_done(heard.append)
                self.assertEqual(job.wait(), [])
            self.assertEqual(heard, [job], "told once, when the last job is done")
            self.assertTrue(all(parts.probe(key) is not None for key in keys.values()))
            return [call.args[0]["cids"] for call in jobs.call_args_list]

        batches = request(daemon=True)
        self.assertEqual(len(batches), 2, "a slot each, but the caller's")
        self.assertEqual(sorted(cid for batch in batches for cid in batch), sorted(keys))
        self.assertEqual([sorted(batch) for batch in request(daemon=False)], [sorted(keys)],
                         "with no daemon, one job on one thread")
        for key in keys.values():
            remove_entry("part", key)
        with inline_artifacts() as jobs:
            self.assertEqual(parts.request_display(tree).wait(), [])
        self.assertEqual(len(jobs.call_args_list), 1, "four small parts are one job")

    def test_part_keys_carry_their_version_and_an_older_one_is_obsolete(self) -> None:
        digest = self.key.rsplit("-v", 1)[0]
        older, newer = f"{digest}-v{parts.PART_VERSION - 1}", f"{digest}-v{parts.PART_VERSION + 1}"
        self.assertTrue(parts.valid_key(self.key))
        self.assertTrue(parts.obsolete_key(older))
        self.assertFalse(parts.obsolete_key(self.key))
        self.assertFalse(parts.obsolete_key(newer), "a newer cadgen's part is not this one's to retire")
        self.assertFalse(parts.valid_key(older))
        self.assertIsNone(parts.probe(older))
        other = {**self.producer, "ocp": self.producer["ocp"] + ".1"}
        self.assertNotEqual(parts.part_key(self.entry, other), self.key, "another kernel derives another part")

    def test_a_read_is_bound_to_its_record_and_the_admitted_bytes(self) -> None:
        glb = parts.derive(self.tree)[self.cid]["glb"]
        self.assertIsNotNone(parts.read(self.key, "glb", expected_object=glb["object"], max_bytes=glb["byteLength"]))
        self.assertIsNone(parts.read(self.key, "glb", expected_object="f" * 64))
        self.assertIsNone(parts.read(self.key, "glb", max_bytes=glb["byteLength"] - 1))
        # Same-size damage: a probe stats objects only, a read checks what it serves.
        record = parts.probe(self.key)
        other = ("1" if self.key[0] == "0" else "0") + self.key[1:]
        body = object_path(glb["object"])
        body.write_bytes(body.read_bytes().replace(self.key.encode(), other.encode()))
        table = object_path(record["selectors"]["object"])
        damaged = bytearray(table.read_bytes())
        damaged[-1] ^= 1
        table.write_bytes(bytes(damaged))
        self.assertEqual(parts.probe(self.key), record)
        self.assertIsNone(parts.read(self.key, "glb"), "a body naming another part is not this part's")
        self.assertIsNone(parts.read(self.key, "selectors"), "a table that is not its address is no table")

    def test_a_view_carries_each_parts_selector_table_and_nothing_else(self) -> None:
        from cadgen.store.view import SELECTOR_TABLE_SUFFIX, export_view

        parts.derive(self.tree)
        view_dir = export_view(self.tree, self.root / "view")
        descriptor = json.loads((view_dir / "assembly.json").read_text(encoding="utf-8"))
        entry = descriptor["components"][self.cid]
        self.assertEqual(entry["part"], self.key)
        self.assertEqual(entry["selectors"], f"components/{self.cid}{SELECTOR_TABLE_SUFFIX}")
        self.assertEqual((view_dir / entry["selectors"]).read_bytes(), parts.read(self.key, "selectors"))
        self.assertEqual(sorted(path.name for path in (view_dir / "components").iterdir()),
                         sorted([f"{self.cid}.brep", f"{self.cid}{SELECTOR_TABLE_SUFFIX}"]))

    def test_the_cli_resolves_a_ref_to_the_row_the_table_names(self) -> None:
        from cadgen import assembly_lookup, lookup
        from cadgen.store.view import export_view

        parts.derive(self.tree)
        view_dir = export_view(self.tree, self.root / "view")
        descriptor = json.loads((view_dir / "assembly.json").read_text(encoding="utf-8"))
        occurrence = descriptor["occurrences"][0]["id"]
        flat = lookup.build_selector_index({"tables": {"occurrenceColumns": ["id"]}, "occurrences": [[occurrence]]})
        merged = assembly_lookup.merge_assembly_entities(
            assembly_lookup.merge_assembly_occurrences(flat, descriptor, view_dir), descriptor, view_dir)
        table = json.loads(parts.read(self.key, "selectors"))
        columns = table["tables"]["faceColumns"]
        for row in table["faces"]:
            face = dict(zip(columns, row))
            ref = f"{occurrence}/{face['name']}"
            found = lookup.find(ref, merged)
            self.assertEqual(found[0], "face")
            self.assertEqual(found[1]["ordinal"], face["ordinal"])
            self.assertEqual(found[1]["tangentGroup"], face["tangentGroup"])
            # The one leaf qualifies a bare element name.
            self.assertEqual(lookup.find(face["name"], merged), found)
        vertex_name = dict(zip(table["tables"]["vertexColumns"], table["vertices"][0]))["name"]
        vertex = lookup.find(f"{occurrence}/{vertex_name}", merged)
        self.assertEqual(vertex[0], "vertex")
        with self.assertRaises(ValueError, msg="the ordinal spelling is no ref"):
            lookup.find(f"{occurrence}.f1", merged)

    def test_a_part_is_what_made_it(self) -> None:
        """A part is keyed by what made its component (STORE.md §2): the construction key its
        model's run named it by, else its content -- this box was built outside any run --
        with the lineage that names its elements, its face colours and the producer. One
        construction is one part however its bytes fall; other names make another part."""
        from build123d import Solid, export_step, import_step

        self.assertNotIn("construction", self.entry, "no model run made this box")
        step = self.root / "box.step"
        export_step(Solid.make_box(1, 2, 3), str(step))
        tree, _, _ = build_tree_from_compound(import_step(str(step)), root_name="box")
        read = next(iter(capture_tree(tree, retain_payloads=False)[0]["components"].values()))
        self.assertNotEqual(read["contentHash"], self.entry["contentHash"])
        self.assertNotEqual(parts.part_key(read, self.producer), self.key, "other bytes, nothing made them: another part")

        def key(entry: dict, **fields) -> str:
            return parts.part_key({**entry, **fields}, self.producer)

        made, remade = key(self.entry, construction="a" * 64), key(read, construction="a" * 64)
        self.assertEqual(made, remade, "one construction is one part whatever its bytes")
        self.assertNotIn(made, (self.key, key(self.entry, construction="b" * 64)))
        self.assertNotEqual(key(self.entry, construction="a" * 64, lineage="c" * 64),
                            key(self.entry, construction="a" * 64, lineage="d" * 64), "other names: another part")
        self.assertNotEqual(key(self.entry, faceColors={"1": [1.0, 0.0, 0.0, 1.0]}), self.key)
        self.assertNotEqual(parts.part_key(self.entry, {**self.producer, "ocp": "0.0.0"}), self.key)

    def test_an_export_at_a_tolerance_meshes_the_bytes_it_decodes(self) -> None:
        """An export at another tolerance builds the table for the bytes it decodes and
        stores nothing (``mesh_at``): its mesh is the same whether the store holds the part
        or not. A sphere: its seam is drawn and its two pole edges are not."""
        from build123d import Solid

        from cadgen.store.meshes import EDGE_CLASSES, decode_payload

        tree, _, _ = build_tree_from_compound(Solid.make_sphere(3), root_name="sphere")
        entry = next(iter(capture_tree(tree, retain_payloads=False)[0]["components"].values()))
        key = parts.part_key(entry, self.producer)
        alone = parts.mesh_at(entry, key, 2e-3, 0.5)
        self.assertIsNone(parts.probe(key), "an export stores nothing")
        self.assertEqual([EDGE_CLASSES[int(row[3])] for row in decode_payload(alone).edges], ["seam"],
                         "the seam is drawn as the seam and the poles are not drawn")
        parts.derive(tree)
        self.assertIsNotNone(parts.probe(key))
        self.assertEqual(parts.mesh_at(entry, key, 2e-3, 0.5), alone, "the stored part changes nothing")


class PartRecordTest(unittest.TestCase):
    """A record a reader cannot trust is no record: to every reader the store lacks the part."""

    def setUp(self) -> None:
        from tests.python.support.tessellation import part_fixture, store_part

        self.tmp = generated_cad_directory(prefix="part-record-")
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(Path(self.tmp.name) / "store")})
        env.start()
        self.addCleanup(env.stop)
        self.key = part_fixture()["key"]
        self.record = store_part()

    def test_a_damaged_record_or_a_missing_object_is_a_miss(self) -> None:
        from cadgen.store.index import write_entry

        self.assertEqual(parts.probe(self.key), self.record)
        glb, table = self.record["glb"], self.record["selectors"]
        for label, damaged in (
            ("decoded size", {**self.record, "glb": {**glb, "decodedBytes": 1}}),
            ("byte length", {**self.record, "glb": {**glb, "byteLength": glb["byteLength"] + 4}}),
            ("edge points", {**self.record, "glb": {**glb, "edgePointCount": 1}}),
            ("no unmeshed face counted", {**self.record, "glb": {**glb, "unmeshedFaceCount": 0}}),
            ("unmeshed past the faces", {**self.record, "glb": {**glb, "unmeshedFaceCount": 2}}),
            ("unknown field", {**self.record, "glb": {**glb, "schemaVersion": 1}}),
            ("negative count", {**self.record, "selectors": {**table, "faceCount": -1}}),
            ("no table", {"glb": glb}),
            ("another field", {**self.record, "part": self.key}),
        ):
            with self.subTest(label=label):
                write_entry("part", self.key, damaged)
                self.assertIsNone(parts.probe(self.key))
        for raw in (b" " * (parts.MAX_INDEX_BYTES + 1), b"[" * 2000 + b"0" + b"]" * 2000):
            entry_path("part", self.key).write_bytes(raw)
            self.assertIsNone(parts.probe(self.key))
        write_entry("part", self.key, self.record)
        object_path(table["object"]).unlink()
        self.assertIsNone(parts.probe(self.key), "a record names objects the store holds")


if __name__ == "__main__":
    unittest.main()
