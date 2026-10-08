from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.cad_test_roots import IsolatedCadRoots
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from build123d import Box, Compound, Location  # noqa: E402

from cadgen.step_export import build_build123d_step_scene  # noqa: E402
from cadgen._internal.step_scene_loader import _normalize_label_name  # noqa: E402


class UnnamedLabelSceneTests(unittest.TestCase):
    """A shape whose XCAF labels are not all named must still build a scene.

    This is a SEGFAULT regression, not a wrong-answer one, so there is nothing to assert
    against on failure -- the process dies with SIGSEGV and no traceback, and the test run
    reports a crashed worker. TDF_Label.FindAttribute does not return false for an absent
    attribute in this OCP build; it dereferences null. _label_name now asks IsAttribute first.

    A plain ``Compound(children=[...])`` is the shape that produces unnamed labels: XCAF makes
    a child label per solid, and nothing names them unless the model was authored through
    AssemblyHelper. Both spellings are covered here because only the unnamed one ever crashed,
    and a fix that quietly stopped reading real names would pass the unnamed case alone.
    """

    def _build(self, shape):
        with tempfile.TemporaryDirectory() as directory:
            return build_build123d_step_scene(shape, Path(directory) / "scene.step")

    def _grid(self, count: int):
        return [Location((index * 30.0, 0.0, 0.0)) * Box(20, 20, 10) for index in range(count)]

    def test_compound_of_unnamed_solids_builds(self) -> None:
        scene = self._build(Compound(children=self._grid(3)))
        self.assertIsNotNone(scene)

    def test_named_labels_still_resolve(self) -> None:
        children = self._grid(2)
        for index, child in enumerate(children):
            child.label = f"block_{index}"
        scene = self._build(Compound(children=children))
        self.assertIsNotNone(scene)

    def test_single_unnamed_solid_builds(self) -> None:
        scene = self._build(Box(20, 20, 10))
        self.assertIsNotNone(scene)

    def test_vendor_unicode_label_spellings_normalize_to_authored_text(self) -> None:
        escaped = r"\X2\51F853F0\X0\-\X2\62C94F38\X0\4_1_2_3_4"
        mojibake = "å\x9c\x86è§\x922_1_2"
        self.assertEqual(_normalize_label_name(escaped), "凸台-拉伸4_1_2_3_4")
        self.assertEqual(_normalize_label_name(mojibake), "圆角2_1_2")
        self.assertEqual(_normalize_label_name(r"\X4\0001F680\X0\ mount"), "🚀 mount")
        self.assertEqual(_normalize_label_name("café Ã©"), "café Ã©")
        self.assertEqual(_normalize_label_name("bracket"), "bracket")


class XcafLabelEntryTests(unittest.TestCase):
    """Where a STEP gave a product or a usage no name, OCCT writes its label's address there.

    cadgen reads that as no name, in one place (``_normalize_label_name``), so every reader of
    the document -- its tree and view, ``read_scene``, the rows ``--mode list`` prints -- names
    the part by what the STEP does call it, else by its occurrence id, never by the address.
    """

    def test_an_entry_is_no_name_and_a_name_holding_one_is_a_name(self) -> None:
        for entry in ("0:1:1:2", "[0:1:1:2]", "=>[0:1:1:2]", "=> [ 0:1:1:12 ]", " =>[0:1:1:2] ", "0:1"):
            self.assertIsNone(_normalize_label_name(entry), entry)
        for name in ("bracket 0:1:1:2", "0:1:1:2 spare", "=>[0:1:1:2] cover", "gear 3:1", "M3:0.5"):
            self.assertEqual(_normalize_label_name(name), name)

    def test_a_single_part_document_reads_its_part_name_not_the_entry(self) -> None:
        import json

        from cadgen import read_scene
        from cadgen._internal.doors import document_snapshot
        from cadgen.assembly_lookup import assembly_occurrence_rows
        from cadgen.step_export import export_build123d_step_file
        from cadgen.store.index import write_entry
        from cadgen.store.trees import get_tree, put_tree
        from cadgen.store.view import view_dir_for

        roots = IsolatedCadRoots(self, prefix="xcaf-label-entry-")
        # A placed single part, as cadgen saves one: OCCT wraps it in a root product it names
        # `=>[0:1:1:2]` and names the usage the same; the part's own product is `l_bracket`.
        part = Location((1.0, 2.0, 3.0)) * Box(10, 8, 4)
        part.label = "l_bracket"
        path = roots.cad_root / "l_bracket.step"
        export_build123d_step_file(part, path)
        self.assertIn("PRODUCT('=>[0:1:1:2]'", path.read_text(encoding="utf-8"))
        document, tree = document_snapshot(path)

        # What a cadgen from before the entry rule left for these bytes -- a tree naming the root
        # and the part `=>[0:1:1:2]` -- is a miss, never served: the bytes compile again.
        stale = get_tree(tree)
        stale["label"] = stale["assembly"]["root"]["name"] = "=>[0:1:1:2]"
        stale["assembly"]["root"]["children"][0]["name"] = stale["occurrences"][0]["name"] = "=>[0:1:1:2]"
        write_entry("document", document, {"schemaVersion": 4, "tree": put_tree(stale), "kind": "step"})
        self.assertEqual((document, tree), document_snapshot(path))

        view = view_dir_for(tree, document_hash=document)
        descriptor = json.loads((view / "assembly.json").read_text(encoding="utf-8"))
        root = descriptor["assembly"]["root"]
        self.assertEqual([("o1", "o1"), ("o1.1", "l_bracket")],
                         [(node["id"], node["name"]) for node in (root, *root["children"])])
        self.assertEqual([("o1.1", "l_bracket")], [(row["id"], row["name"]) for row in descriptor["occurrences"]])
        self.assertEqual([("o1.1", "l_bracket")],
                         [(row["id"], row["name"]) for row in assembly_occurrence_rows(descriptor, None)])
        scene = read_scene(path)
        self.assertEqual("o1", scene.roots[0].label)
        self.assertEqual(["l_bracket"], [leaf.label for leaf in scene.leaves()])


if __name__ == "__main__":
    unittest.main()
