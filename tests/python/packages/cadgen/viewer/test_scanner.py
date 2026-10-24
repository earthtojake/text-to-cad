"""The catalog-row contract: what ``catalog_entry`` answers for one file, named by its absolute path.

What these pin is the behaviour of the row itself — the branches a particular file reaches,
and the JS/Python semantics that agree on well-formed input and part company on the edges. Every
format's row is its file's: a STEP's and an ``.xbf``'s too, which the cadgen engine draws.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from cadgen._internal.shared_read import open_shared_for_read
from cadgen.viewer import scanner
from cadgen.viewer.scanner import catalog_entry, is_served_cad_asset, source_format_for_path


def asset_query(url: str) -> dict:
    """The ``file`` and ``v`` an asset URL carries."""
    parsed = urlsplit(url)
    assert parsed.path == "/__cad/asset", url
    return {key: values[0] for key, values in parse_qs(parsed.query).items()}


class ScannerTestCase(unittest.TestCase):
    """A temp folder."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = os.path.join(self.tmp, "models")
        os.makedirs(self.root)

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

    def entry(self, rel: str) -> dict:
        found = catalog_entry(self.path(rel))
        self.assertIsNotNone(found, rel)
        return found


class OneRowPerNamedFile(ScannerTestCase):
    def test_artifacts_have_rows_and_a_script_has_none(self):
        self.write("drawing.dxf.py", "print(1)")
        self.write("model.py", "raise AssertionError('catalog must never execute a script')")
        self.write("outline.dxf", "0\nSECTION\n")
        self.assertIsNone(catalog_entry(self.path("drawing.dxf.py")))
        self.assertIsNone(catalog_entry(self.path("model.py")))
        self.assertIsNone(catalog_entry(f"{self.path('model.py')}::bare"))
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

    def test_only_the_cad_extensions_have_rows(self):
        for name in ("a.step", "b.stp", "c.stl", "d.3mf", "e.glb", "f.dxf", "g.urdf", "h.srdf", "i.sdf", "p.xbf"):
            self.write(name, "x")
            self.assertIsNotNone(catalog_entry(self.path(name)), name)
        for name in ("j.json", "k.js", "l.txt", "n", "o.stepx"):
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


class EngineDocumentRows(ScannerTestCase):
    """A STEP and an ``.xbf`` are drawn from what the cadgen engine serves of them: their rows are
    their files', which say only that the file is there and which bytes it has."""

    def test_a_step_row_is_its_files_and_its_version_moves_with_its_bytes(self):
        body = "ISO-10303-21;\nEND-ISO-10303-21;\n"
        self.write("part.step", body)
        entry = self.entry("part.step")
        self.assertEqual(list(entry), ["file", "kind", "url", "hash", "bytes"])
        self.assertEqual((entry["kind"], entry["bytes"]), ("step", len(body)))
        self.assertEqual(entry["hash"], hashlib.sha256(body.encode()).hexdigest())
        self.assertEqual(asset_query(entry["url"])["file"], self.path("part.step"))
        self.write("part.step", body + "\n")
        changed = self.entry("part.step")
        self.assertNotEqual((changed["hash"], changed["url"]), (entry["hash"], entry["url"]))

    def test_a_sidecar_beside_a_step_changes_nothing_of_its_row(self):
        self.write("part.step", "ISO-10303-21;\n")
        before = self.entry("part.step")
        self.write("part.step.json", '{"kinematics": {}, "animation": {}}')
        self.assertEqual(self.entry("part.step"), before)

    def test_an_xbf_and_an_stp_have_their_kinds(self):
        self.write("arm.xbf", "binary")
        self.write("vendor.STP", "ISO-10303-21;\n")
        self.assertEqual((self.entry("arm.xbf")["kind"], self.entry("vendor.STP")["kind"]), ("xbf", "stp"))


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

    def test_a_step_deleted_while_its_row_hashes_it_is_deleted(self):
        document = self.write("part.step", "ISO-10303-21;\nEND-ISO-10303-21;\n")
        with mock.patch.object(scanner, "open_shared_for_read", self.delete_while_open(document)):
            catalog_entry(document)
        self.assertEqual(self.deleted, [document])
        self.assertFalse(os.path.exists(document))


class ServedAssetGate(unittest.TestCase):
    def test_the_gate(self):
        self.assertFalse(is_served_cad_asset("/root/.secret.step"))
        # A sidecar is a .json like any other: nothing reads one, and none leaves.
        self.assertFalse(is_served_cad_asset("/root/part.step.json"))
        self.assertFalse(is_served_cad_asset("/root/PART.STEP.JSON"))
        self.assertFalse(is_served_cad_asset("/root/part.stp.json"))
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
