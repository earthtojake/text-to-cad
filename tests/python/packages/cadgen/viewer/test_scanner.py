"""The catalog-row contract: what ``catalog_entry`` answers for one file, named by its absolute path.

What these pin is the behaviour of the row itself — the branches a particular file reaches,
and the JS/Python semantics that agree on well-formed input and part company on the edges.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from cadgen import catalog
from cadgen._internal.shared_read import open_shared_for_read
from cadgen._internal.source_sidecar import SOURCE_SIDECAR_SCHEMA_VERSION
from cadgen.viewer import scanner
from cadgen.viewer.scanner import catalog_entry, is_served_cad_asset, source_format_for_path
from cadgen.viewer.store_paths import result_snapshot, result_tree

from tests.python.support.store_fixtures import seed_result


def asset_query(url: str) -> dict:
    """The ``file`` and ``v`` an asset URL carries."""
    parsed = urlsplit(url)
    assert parsed.path == "/__cad/asset", url
    return {key: values[0] for key, values in parse_qs(parsed.query).items()}


class ScannerTestCase(unittest.TestCase):
    """A temp folder plus a temp cadgen store, with the env pointed at it."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = os.path.join(self.tmp, "models")
        os.makedirs(self.root)
        cache = os.path.join(self.tmp, "cache")
        os.makedirs(cache)
        # The cache root is read from the environment on every call, never memoised at import.
        previous = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = cache
        self.addCleanup(self._restore_cache_dir, previous)

    @staticmethod
    def _restore_cache_dir(previous) -> None:
        if previous is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = previous

    # --- helpers ----------------------------------------------------------

    def path(self, rel: str) -> str:
        return os.path.join(self.root, rel)

    def write(self, rel: str, text: str) -> str:
        path = self.path(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Bytes, not text mode: tests assert byte counts exactly, and text mode
        # would write \r\n on Windows.
        Path(path).write_bytes(text.encode("utf-8"))
        return path

    def package(self, rel: str, descriptor) -> str:
        """Seed ``root/<rel>``'s result in the store; returns the tree hash."""
        return seed_result(Path(self.path(rel)), descriptor)

    def sidecar(self, rel: str, payload: dict) -> str:
        document = Path(self.path(rel))
        body = dict(payload)
        body["schemaVersion"] = SOURCE_SIDECAR_SCHEMA_VERSION
        body["documentHash"] = hashlib.sha256(document.read_bytes()).hexdigest()
        return self.write(f"{rel}.json", json.dumps(body))

    def entry(self, rel: str) -> dict:
        found = catalog_entry(self.path(rel))
        self.assertIsNotNone(found, rel)
        return found


class OneRowPerNamedFile(ScannerTestCase):
    def test_the_written_artifact_has_a_row_and_a_model_script_none(self):
        self.write("drawing.dxf.py", "print(1)")
        self.write("model.py", "print(1)")
        self.write("outline.dxf", "0\nSECTION\n")
        self.assertIsNone(catalog_entry(self.path("drawing.dxf.py")))
        self.assertIsNone(catalog_entry(self.path("model.py")))
        self.assertEqual(self.entry("outline.dxf")["file"], self.path("outline.dxf").replace(os.sep, "/"))

    def test_a_file_under_a_hidden_folder_has_its_row_and_a_hidden_file_none(self):
        # Named, never found: a hidden FOLDER on the way is no reason to refuse it.
        self.write(".worktree/part.stl", "x")
        self.write(".hidden.stl", "x")
        os.makedirs(self.path("folder.step"))
        self.assertEqual(self.entry(".worktree/part.stl")["kind"], "stl")
        for rel in (".hidden.stl", "folder.step", "gone.stl"):
            with self.subTest(rel=rel):
                self.assertIsNone(catalog_entry(self.path(rel)))

    def test_only_the_source_extensions_have_rows(self):
        for name in ("a.step", "b.stp", "c.stl", "d.3mf", "e.glb", "f.dxf", "g.urdf", "h.srdf", "i.sdf"):
            self.write(name, "x")
            self.assertIsNotNone(catalog_entry(self.path(name)), name)
        for name in ("j.json", "k.js", "l.txt", "m.py", "n", "o.stepx"):
            self.write(name, "x")
            self.assertIsNone(catalog_entry(self.path(name)), name)


class EntryShape(ScannerTestCase):
    def test_a_single_asset_entry_and_its_key_order(self):
        self.write("outline.dxf", "0\nSECTION\n")
        entry = self.entry("outline.dxf")
        self.assertEqual(list(entry), ["file", "kind", "url", "hash", "bytes"])
        self.assertEqual(entry["kind"], "dxf")
        self.assertEqual(len(entry["hash"]), 64)
        self.assertEqual(entry["bytes"], 10)
        self.assertNotIn("relations", entry)

    @unittest.skipIf(os.name == "nt", "'*' is not a legal NTFS filename character")
    def test_the_url_names_the_file_by_its_absolute_path_and_its_version(self):
        path = self.write("sub dir/a b(c)*d~e.stl", "x")
        stat_result = os.stat(path)
        query = asset_query(self.entry("sub dir/a b(c)*d~e.stl")["url"])
        self.assertEqual(query["file"], path)
        # The ?v= token: base36(size)-base36(mtime_ns), from one stat.
        self.assertEqual(query["v"], scanner.file_version(stat_result.st_size, stat_result.st_mtime_ns))

    def test_kind_comes_from_the_lowercased_extension(self):
        for name, kind in (("a.STL", "stl"), ("b.3MF", "3mf"), ("c.GLB", "glb"), ("d.SDF", "sdf")):
            self.write(name, "x")
            self.assertEqual(self.entry(name)["kind"], kind)
        self.assertEqual(source_format_for_path("x.STP", ".STP"), "stp")

    def test_a_named_link_is_its_targets_bytes_and_a_dangling_one_has_no_row(self):
        real = self.write("real.stl", "same")
        os.symlink(real, self.path("link.stl"))
        os.symlink(self.path("nowhere.stl"), self.path("dangling.stl"))
        self.assertEqual(self.entry("link.stl")["hash"], self.entry("real.stl")["hash"])
        self.assertEqual(self.entry("link.stl")["file"], self.path("link.stl").replace(os.sep, "/"))
        self.assertIsNone(catalog_entry(self.path("dangling.stl")))


class StoreResults(ScannerTestCase):
    def test_unchanged_step_entry_reuses_immutable_tree_metadata(self):
        self.write("cached.step", "same bytes\n")
        self.package("cached.step", {"kind": "assembly-package", "components": {"c0": {}}})
        with mock.patch.object(scanner, "result_descriptor", wraps=scanner.result_descriptor) as descriptor:
            first = self.entry("cached.step")
            second = self.entry("cached.step")
        self.assertEqual(first, second)
        descriptor.assert_called_once()

    def test_sidecar_change_invalidates_the_step_entry(self):
        self.write("finish.step", "same bytes\n")
        self.package("finish.step", {
            "kind": "assembly-package",
            "components": {"cid": {}},
            "occurrences": [{"id": "o1.1", "name": "part", "component": "cid", "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}],
        })
        self.sidecar("finish.step", {"appearance": {"materials": {"finish": {"name": "Finish", "roughness": 0.2}}, "assignments": {"o1.1": "finish"}}})
        first = self.entry("finish.step")
        self.sidecar("finish.step", {"appearance": {"materials": {"finish": {"name": "Finish", "roughness": 0.9}}, "assignments": {"o1.1": "finish"}}})
        second = self.entry("finish.step")
        self.assertNotEqual(first["appearanceHash"], second["appearanceHash"])
        self.assertEqual(second["display"]["o1.1"]["material"]["roughness"], 0.9)

    def test_same_bytes_share_one_tree_and_each_document_has_its_own_record(self):
        self.write("a.step", "same bytes\n")
        self.write("sub/b.step", "same bytes\n")
        self.write("c.step", "other bytes\n")
        a = self.package("a.step", {"kind": "assembly-package", "components": {"c0": {}}})
        b = self.package("sub/b.step", {"kind": "assembly-package", "components": {"c0": {}}})
        c = self.package("c.step", {"kind": "assembly-package", "components": {"c0": {}}})
        self.assertEqual(a, b, "one tree for one result")
        self.assertEqual(a, c, "different document bytes may describe the same geometry")
        self.assertEqual(result_tree(self.path("c.step")), c)
        self.assertEqual(result_tree(self.path("a.step")), a)
        self.assertEqual(result_tree(self.path("sub/b.step")), b)
        self.assertIsNone(result_tree(self.path("gone.step")))

    def test_a_step_with_no_result_has_no_hash_and_no_bytes(self):
        self.write("bare.step", "ISO-10303-21;\n")
        entry = self.entry("bare.step")
        self.assertTrue(entry["url"].startswith("/__cad/store?file=unbuilt-"))
        self.assertNotIn("&v=", entry["url"])
        self.assertEqual((entry["hash"], entry["bytes"], entry["kind"]), ("", 0, "part"))

    def test_the_store_url_names_the_tree_and_its_bytes_describe_the_flattened_tree(self):
        from cadgen.viewer.store_paths import result_descriptor

        self.write("p.step", "a much longer step body than the descriptor\n")
        tree = self.package("p.step", {"kind": "assembly-package", "components": {"c0": {}}})
        entry = self.entry("p.step")
        self.assertEqual(entry["url"], f"/__cad/store?file={tree}&documentHash={entry['documentHash']}")
        self.assertEqual(entry["hash"], tree)
        self.assertEqual(entry["bytes"], len(json.dumps(result_descriptor(tree)).encode("utf-8")))


class UnreadableTree(ScannerTestCase):
    """A document whose tree the store can no longer read whole lists as unbuilt, until the
    store is repaired: the repair (a compile publishing the document again) restores the lost
    object at its own hash, so nothing in the row's key moves, and a row kept from before the
    repair listed the document as unbuilt for as long as the server ran."""

    def test_a_lost_component_lists_the_document_unbuilt_until_the_store_is_repaired(self):
        from cadgen.store.objects import object_path, put_object

        self.write("pair.step", "pair\n")
        tree = self.package("pair.step", {"components": {"left": {}, "right": {}}})
        brep = next(iter(json.loads(object_path(tree).read_bytes())["components"].values()))["brep"]
        payload = object_path(brep).read_bytes()
        object_path(brep).unlink()

        lost = self.entry("pair.step")
        # Nothing in it says it can be loaded: no tree hash, and no URL naming the tree.
        self.assertEqual((lost["hash"], lost["bytes"]), ("", 0))
        self.assertNotIn(tree, lost["url"])

        self.assertEqual(put_object(payload, repair=True), brep)  # the same bytes, at their hash
        repaired = self.entry("pair.step")
        self.assertEqual((repaired["kind"], repaired["hash"]), ("assembly", tree))
        self.assertEqual(repaired["documentHash"], lost["documentHash"])


class StepKind(ScannerTestCase):
    def _kind(self, descriptor) -> str:
        self.write("k.step", "x\n")
        self.package("k.step", descriptor)
        return self.entry("k.step")["kind"]

    def test_the_tree_decides_kind_not_the_entry_kind_text(self):
        # One occurrence is a part whatever the seeded descriptor claimed: the
        # flattened tree's entryKind comes from store.trees.tree_kind.
        self.assertEqual(self._kind({"kind": "assembly-package", "entryKind": "  ASSEMBLY  "}), "part")

    def test_two_occurrences_make_an_assembly(self):
        self.assertEqual(
            self._kind({"kind": "assembly-package", "occurrences": [{'id': 'o1.1', 'name': 'a', 'component': 'c0', 'transform': [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}, {'id': 'o1.2', 'name': 'b', 'component': 'c0', 'transform': [1, 0, 0, 10, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}]}), "assembly"
        )

    def test_a_root_object_alone_does_not_make_an_assembly(self):
        self.assertEqual(self._kind({"kind": "assembly-package", "assembly": {"root": {}}}), "part")

    def test_no_package_is_a_part(self):
        self.write("k.step", "x\n")
        self.assertEqual(self.entry("k.step")["kind"], "part")


HINGE = {"mates": [{"name": "hinge", "kind": "revolute", "parent": "#base", "child": "#arm",
                    "parentId": "o1.1", "childId": "o1.2",
                    "axis": {"origin": [10, 0, 0], "dir": [0, 0, 1]}, "limits": {"value": [0, 90]}}],
         "poses": {"open": {"hinge": 90}}}
HINGE_PACKAGE = {
    "kind": "assembly-package", "components": {"c0": {}},
    "occurrences": [{"id": "o1.1", "name": "base", "component": "c0", "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]},
                    {"id": "o1.2", "name": "arm", "component": "c0", "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}],
}


class DescriptorGate(ScannerTestCase):
    """``{}`` from ``read_step_catalog_metadata`` suppresses sourceUrl/poseUrl."""

    def test_a_valid_package_publishes_the_articulation_and_both_urls(self):
        self.write("g.step", "x\n")
        self.sidecar("g.step", {"kinematics": HINGE})
        self.package("g.step", HINGE_PACKAGE)
        entry = self.entry("g.step")
        self.assertEqual(asset_query(entry["sourceUrl"])["file"], self.path("g.step.json"))
        self.assertEqual(entry["poseUrl"], entry["sourceUrl"])
        # What the page plays: cadgen's articulation of the mates, inline, over the tree's occurrences.
        self.assertEqual([control["id"] for control in entry["articulation"]["controls"]], ["hinge"])
        self.assertEqual(entry["articulation"]["carries"], {"hinge": ["o1.2"]})
        self.assertEqual(entry["articulation"]["poses"], {"open": {"hinge": 90.0}})

    def test_no_package_suppresses_both(self):
        self.write("g.step", "x\n")
        self.sidecar("g.step", {"kinematics": HINGE})
        entry = self.entry("g.step")
        self.assertNotIn("sourceUrl", entry)
        self.assertNotIn("poseUrl", entry)
        self.assertNotIn("articulation", entry)


class SidecarSections(ScannerTestCase):
    """A row carries what each section MEANS, resolved: nothing for a section that declares nothing."""

    def _entry(self, sidecar_text: str | None) -> dict:
        self.write("s.step", "x\n")
        if sidecar_text is not None:
            self.sidecar("s.step", json.loads(sidecar_text))
        self.package("s.step", {"kind": "assembly-package", "components": {"c0": {}}})
        return self.entry("s.step")

    def test_a_kinematics_block_with_no_mates_poses_nothing(self):
        entry = self._entry(json.dumps({"kinematics": {}}))
        self.assertIn("sourceUrl", entry)
        self.assertNotIn("poseUrl", entry)
        self.assertNotIn("articulation", entry)

    def test_a_kinematics_block_this_cadgen_cannot_read_is_dropped_quietly(self):
        entry = self._entry(json.dumps({"kinematics": {"mates": [{"name": "x", "kind": "twist", "child": "#a", "parent": "#b"}]}}))
        for absent in ("annotationError", "sourceUrl", "poseUrl", "articulation"):
            self.assertNotIn(absent, entry)

    def test_explicit_nulls_yield_no_pose_url(self):
        entry = self._entry(json.dumps({"kinematics": None, "animation": None}))
        self.assertIn("sourceUrl", entry)
        self.assertNotIn("poseUrl", entry)
        self.assertNotIn("animation", entry)

    def test_appearance_has_a_scene_identity_without_changing_the_tree_identity(self):
        self.write("finish.step", "x\n")
        self.sidecar("finish.step", {
            "appearance": {"materials": {"finish": {"name": "Finish", "roughness": 0.25}}, "assignments": {"o1.1": "finish"}}
        })
        self.package("finish.step", {
            "kind": "assembly-package",
            "components": {"cid": {}},
            "occurrences": [{"id": "o1.1", "name": "part", "component": "cid", "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}],
        })
        entry = self.entry("finish.step")
        self.assertEqual(len(entry["appearanceHash"]), 64)
        # What the appearance resolves to for the page to draw, per assigned occurrence: the
        # material with every channel, and the opacity cadgen folded.
        self.assertEqual(entry["display"], {"o1.1": {
            "materialId": "finish", "materialName": "Finish", "opacity": 1.0,
            "material": {"roughness": 0.25, "metalness": 0.03, "clearcoat": 0.0, "clearcoatRoughness": 0.26, "opacity": 1.0},
        }})
        self.assertEqual(asset_query(entry["sourceUrl"])["file"], self.path("finish.step.json"))
        self.assertEqual(entry["hash"], result_tree(Path(self.path("finish.step"))))
        self.assertNotIn("poseUrl", entry)

    def test_catalog_binds_inline_sidecar_and_scene_hash_to_one_read(self):
        from cadgen._internal.source_sidecar import appearance_digest

        self.write("race.step", "x\n")
        first = {"materials": {"finish": {"name": "Finish", "roughness": 0.2}}, "assignments": {"o1.1": "finish"}}
        second = {"materials": {"finish": {"name": "Finish", "roughness": 0.9}}, "assignments": {"o1.1": "finish"}}
        self.sidecar("race.step", {"appearance": first})
        self.package("race.step", {
            "kind": "assembly-package",
            "components": {"cid": {}},
            "occurrences": [{"id": "o1.1", "name": "part", "component": "cid", "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}],
        })
        original_asset_for_path = scanner.asset_for_path

        def mutate_after_version_read(file_path):
            asset = original_asset_for_path(file_path)
            self.sidecar("race.step", {"appearance": second})
            return asset

        with mock.patch.object(scanner, "asset_for_path", mutate_after_version_read):
            entry = self.entry("race.step")

        self.assertEqual(entry["display"]["o1.1"]["material"]["roughness"], 0.2)
        self.assertEqual(entry["appearanceHash"], appearance_digest(first))
        self.assertNotEqual(entry["appearanceHash"], appearance_digest(second))

    def test_catalog_keeps_tree_and_document_hash_from_one_snapshot(self):
        path = Path(self.write("document-race.step", "first\n"))
        tree = self.package("document-race.step", {"kind": "assembly-package", "components": {"cid": {}}})
        selected = result_snapshot(path)
        self.assertEqual(selected, (hashlib.sha256(b"first\n").hexdigest(), tree))

        def replace_after_selection(_path):
            path.write_bytes(b"second\n")
            return selected

        with mock.patch.object(scanner, "result_snapshot", replace_after_selection):
            entry = self.entry("document-race.step")

        self.assertEqual(entry["hash"], tree)
        self.assertEqual(entry["documentHash"], hashlib.sha256(b"first\n").hexdigest())
        self.assertNotEqual(entry["documentHash"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_baked_animation_is_pinned_to_the_catalog_snapshot(self):
        animation = {"clips": [
            {"id": "swing", "label": "Swing", "duration": 2, "loop": True,
             "tracks": [{"targets": ["o1"], "times": [0, 2], "opacity": [1, 0.5]}]},
            {"id": "blink", "label": "blink", "duration": 1, "loop": False,
             "tracks": [{"targets": ["o1"], "times": [0, 0.5], "visible": [True, False]}]},
        ]}
        entry = self._entry(json.dumps({"animation": animation}))
        # The keyframes as read, clips in their declared order: the first is the one a viewer opens on.
        self.assertEqual(entry["animation"], animation)
        self.assertEqual(len(entry["animationHash"]), 64)

    def test_no_animation_no_hash(self):
        self.assertNotIn("animationHash", self._entry(None))

    def test_an_animation_that_bends_a_tube_names_where_its_skins_are(self):
        line = {"normal": [0, 0, 1], "segments": [{"kind": "line", "start": [0, 0, 0], "end": [10, 0, 0]}]}
        bend = {"clips": [{"id": "bend", "label": "Bend", "duration": 1, "loop": False, "tracks": [
            {"targets": ["o1"], "times": [0], "rest": line, "maxSegmentLength": 1.0, "tube": [None]}]}]}
        entry = self._entry(json.dumps({"animation": bend}))
        self.assertTrue(entry["tubeSkinsUrl"].startswith("/__cad/tube-skins?file="))
        self.assertTrue(entry["tubeSkinsUrl"].endswith(f"&documentHash={entry['documentHash']}"))
        fade = {"clips": [{"id": "fade", "label": "Fade", "duration": 1, "loop": False, "tracks": [
            {"targets": ["o1"], "times": [0], "opacity": [0.5]}]}]}
        self.assertNotIn("tubeSkinsUrl", self._entry(json.dumps({"animation": fade})))

    def test_an_unreadable_animation_section_is_no_sidecar_not_a_failed_entry(self):
        entry = self._entry(json.dumps({"animation": {"clips": "not clips"}}))
        self.assertNotIn("animation", entry)
        self.assertNotIn("animationHash", entry)

    def test_the_catalog_publishes_no_provenance(self):
        entry = self._entry(json.dumps({"sourceKind": "step"}))
        for forbidden in ("sourceKind", "source", "poseHatchUrl", "moduleUrl", "legacyParamsSidecar", "renderModuleUrl", "sourceSidecar"):
            self.assertNotIn(forbidden, entry)

    def test_the_sidecar_suffix_is_appended_to_the_whole_name(self):
        self.write("u.STP", "x\n")
        self.sidecar("u.STP", {"kinematics": {}})
        self.package("u.STP", {"kind": "assembly-package", "components": {"c0": {}}})
        self.assertEqual(asset_query(self.entry("u.STP")["sourceUrl"])["file"], self.path("u.STP.json"))

    # A sidecar this build cannot read is no sidecar: the document renders, with
    # no kinematics, no materials and no routine, and the entry says nothing
    # about it. The migration is announced by the build and by the cad skill.
    def test_a_sidecar_for_different_step_bytes_is_dropped_quietly(self):
        self.write("stale.step", "old\n")
        self.sidecar("stale.step", {"kinematics": {}})
        self.write("stale.step", "new\n")
        self.package("stale.step", {"kind": "assembly-package", "components": {"c0": {}}})

        entry = self.entry("stale.step")
        for absent in ("annotationError", "sourceUrl", "poseUrl"):
            self.assertNotIn(absent, entry)
        self.assertTrue(entry["url"].startswith("/__cad/store?file="))
        self.assertEqual(entry["documentHash"], hashlib.sha256(b"new\n").hexdigest())

    def test_a_schema_six_sidecar_is_a_hard_cutover_and_is_dropped_quietly(self):
        self.write("old.step", "x\n")
        self.write("old.step.json", json.dumps({"schemaVersion": 6, "kinematics": {}}))
        self.package("old.step", {"kind": "assembly-package", "components": {"c0": {}}})
        entry = self.entry("old.step")
        for absent in ("annotationError", "sourceUrl", "poseUrl"):
            self.assertNotIn(absent, entry)

    def test_invalid_appearance_drops_the_sidecar_without_an_entry_field(self):
        self.write("bad-finish.step", "x\n")
        self.sidecar("bad-finish.step", {
            "appearance": {"materials": {"finish": {"name": "Finish", "roughness": "glossy"}}, "assignments": {"o1.1": "finish"}}
        })
        self.package("bad-finish.step", {"kind": "assembly-package", "components": {"c0": {}}})
        entry = self.entry("bad-finish.step")
        for absent in ("annotationError", "sourceUrl", "appearanceHash"):
            self.assertNotIn(absent, entry)


class SrdfPairing(ScannerTestCase):
    def test_an_srdf_pairs_with_the_matching_same_directory_urdf(self):
        self.write("arm.urdf", '<?xml version="1.0"?><robot name="arm"><link name="l"/></robot>')
        self.write("other.urdf", '<robot name="other"/>')
        self.write("arm.srdf", '<robot name="arm"/>')
        relation = self.entry("arm.srdf")["relations"]["urdf"]
        self.assertEqual(list(relation), ["file", "url", "hash", "bytes"])
        self.assertEqual(relation["file"], self.path("arm.urdf").replace(os.sep, "/"))
        self.assertEqual(asset_query(relation["url"])["file"], self.path("arm.urdf"))

    def test_a_prolog_of_declaration_comment_and_doctype_is_skipped(self):
        self.write("z.urdf", '<robot name="z"/>')
        self.write("z.srdf", '<?xml version="1.0"?><!-- c --><!DOCTYPE robot><robot name="z"/>')
        self.assertEqual(self.entry("z.srdf")["relations"]["urdf"]["file"], self.path("z.urdf").replace(os.sep, "/"))

    def test_ambiguity_a_nameless_robot_and_another_directory_never_pair(self):
        self.write("one.urdf", '<robot name="dup"/>')
        self.write("two.urdf", '<robot name="dup"/>')
        self.write("dup.srdf", '<robot name="dup"/>')
        self.write("n.urdf", "<robot/>")
        self.write("n.srdf", "<robot/>")
        self.write("deep/far.urdf", '<robot name="far"/>')
        self.write("far.srdf", '<robot name="far"/>')
        for rel in ("dup.srdf", "n.srdf", "far.srdf"):
            with self.subTest(rel=rel):
                self.assertNotIn("relations", self.entry(rel))


class ReadsNeverBlockDeletion(ScannerTestCase):
    """A catalog read that has a model open must not stop the user deleting it.

    POSIX never lets a reader's handle refuse an unlink; Windows does, unless the reader asked
    for delete sharing, and a plain ``open()`` does not. On Windows these fail with
    ``WinError 32`` the moment a hash goes back to a plain ``open``; off Windows they pin the
    row's tolerance of a file that vanishes mid-read.
    """

    def delete_while_open(self, target, *, before_open: bool = False):
        """An opener that deletes ``target`` while (or just before) it is read."""
        self.deleted = []

        def opener(path):
            if os.path.realpath(path) != os.path.realpath(target):
                return open_shared_for_read(path)
            if before_open:
                os.unlink(path)
                return open_shared_for_read(path)
            handle = open_shared_for_read(path)
            os.unlink(path)
            self.deleted.append(path)
            return handle

        return opener

    def test_a_model_deleted_while_its_row_hashes_it_is_deleted(self):
        model = self.write("probe.stl", "solid probe\nendsolid probe\n")
        with mock.patch.object(scanner, "open_shared_for_read", self.delete_while_open(model)):
            catalog_entry(model)
        self.assertEqual(self.deleted, [model])
        self.assertIsNone(catalog_entry(model))

    def test_a_model_gone_before_its_row_opens_it_leaves_the_row_standing(self):
        model = self.write("probe.stl", "solid probe\nendsolid probe\n")
        with mock.patch.object(scanner, "open_shared_for_read", self.delete_while_open(model, before_open=True)):
            self.assertEqual(catalog_entry(model)["hash"], "")
        self.assertIsNone(catalog_entry(model))

    def test_a_step_deleted_while_its_digest_is_read_is_deleted(self):
        document = self.write("part.step", "ISO-10303-21;\nEND-ISO-10303-21;\n")
        with mock.patch.object(catalog, "open_shared_for_read", self.delete_while_open(document)):
            catalog.artifact_file_hash(Path(document))
        self.assertEqual(len(self.deleted), 1)
        self.assertFalse(os.path.exists(document))


class ServedAssetGate(unittest.TestCase):
    def test_the_gate(self):
        self.assertFalse(is_served_cad_asset("/root/.secret.step"))
        self.assertTrue(is_served_cad_asset("/root/part.step.json"))
        self.assertTrue(is_served_cad_asset("/root/PART.STEP.JSON"))
        self.assertTrue(is_served_cad_asset("/root/part.stp.json"))
        self.assertFalse(is_served_cad_asset("/root/random.js"))
        self.assertFalse(is_served_cad_asset("/root/part.anim.js"))
        self.assertFalse(is_served_cad_asset("/root/part.step.js"))
        self.assertFalse(is_served_cad_asset("/root/PART.STP.JS"))
        self.assertFalse(is_served_cad_asset("/root/.hidden.step.js"))
        self.assertFalse(is_served_cad_asset("/root/secrets.json"))
        self.assertTrue(is_served_cad_asset("/root/part.step"))
        self.assertTrue(is_served_cad_asset("/root/part.SDF"))
        self.assertFalse(is_served_cad_asset("/root/notes.txt"))

    def test_the_hidden_check_is_on_the_basename_only(self):
        # A hidden folder on the way is no reason to refuse a file that is named.
        self.assertTrue(is_served_cad_asset("/home/u/.models/part.step"))


if __name__ == "__main__":
    unittest.main()
