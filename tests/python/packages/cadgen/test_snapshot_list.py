"""`cadgen step snapshot --mode list`: cadgen's facts, through the real door.

These run the verb on a tiny assembly built here -- a 20 x 10 x 5 plate at the origin and a
radius-5 pin standing at x = 30 -- and read what was answered:

* `--mode list` is answered from the tree and the store, with no browser: the refs every
  selector resolves, the parts' exact boxes, and the stored meshes' counts;
* a view of a model with no surfaces -- only curves and points, or nothing -- warns so.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from tests.python.support.cad_test_roots import ClassCadRoots
from tests.python.support.paths import add_repo_path
from tests.python.support.tree_ids import leaf_id, node_id, tokenized

add_repo_path("packages/cadgen/src")

PIN = (30.0, 0.0, 5.0)  # centre x, centre y, radius


def write_assembly(path) -> None:
    from build123d import Compound, Location, Solid
    from cadgen.step_export import export_build123d_step_file

    plate = Solid.make_box(20, 10, 5)
    plate.label = "plate"
    pin = Solid.make_cylinder(PIN[2], 20).moved(Location((PIN[0], PIN[1], 0)))
    pin.label = "pin"
    export_build123d_step_file(Compound(children=[plate, pin], label="asm"), path)


def browser_refused(*_args, **_kwargs):
    raise AssertionError("a browser was started")


class SnapshotListTests(unittest.TestCase):
    """`--mode list` on a STEP model is cadgen's answer from the tree and the store: no browser."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._roots = ClassCadRoots(prefix="snapshot-list-")
        cls.workspace = cls._roots.cad_root
        write_assembly(cls.workspace / "asm.step")
        import cadgen.step as step_door
        from cadgen import snapshot_core

        cls.step = step_door
        with mock.patch.object(snapshot_core.BatchSnapshotRenderer, "start", browser_refused):
            cls.listing = step_door.snapshot(cls.workspace / "asm.step", mode="list")
            cls.focused = step_door.snapshot(cls.workspace / "asm.step", mode="list", focus=("#pin",))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._roots.cleanup()

    def test_each_part_is_listed_with_its_exact_box_and_its_mesh_counts(self) -> None:
        self.assertTrue(self.listing.ok)
        self.assertEqual((), self.listing.files)
        from cadgen._internal.tree_tokens import is_occurrence_token

        rows = {row["name"]: row for row in self.listing.parts}
        self.assertEqual(["plate", "pin"], list(rows))
        self.assertEqual({"ref", "name", "triangleCount", "vertexCount", "bounds"}, set(rows["plate"]))
        # Each ref is the occurrence's token, the ref every selector takes.
        self.assertTrue(all(row["ref"].startswith("#") and is_occurrence_token(row["ref"][1:]) for row in rows.values()))
        self.assertEqual({"min": [0, 0, 0], "max": [20, 10, 5]}, rows["plate"]["bounds"])
        # The pin's exact box, from its BREP, placed at x = 30: not a tessellation's.
        self.assertEqual({"min": [25, -5, 0], "max": [35, 5, 20]}, rows["pin"]["bounds"])
        # A box is two triangles a face, each face its own four vertices.
        self.assertEqual((12, 24), (rows["plate"]["triangleCount"], rows["plate"]["vertexCount"]))
        self.assertGreater(rows["pin"]["triangleCount"], 12)

    def test_a_listed_ref_is_one_every_selector_resolves(self) -> None:
        from cadgen._internal.doors import document_snapshot
        from cadgen.assembly_lookup import assembly_occurrence_rows
        from cadgen.store.view import view_dir_for

        document, tree = document_snapshot(self.workspace / "asm.step")
        package = view_dir_for(tree, document_hash=document)
        descriptor = json.loads((package / "assembly.json").read_text(encoding="utf-8"))
        rows = assembly_occurrence_rows(descriptor, package)
        self.assertEqual([(f"#{row['id']}", row["name"]) for row in rows],
                         [(row["ref"], row["name"]) for row in self.listing.parts])

    def test_focus_lists_only_what_it_keeps(self) -> None:
        self.assertEqual(["pin"], [row["name"] for row in self.focused.parts])

    def test_listing_a_stored_model_loads_no_kernel(self) -> None:
        # The rows are read from the tree and its parts' records: a process that lists
        # (the snapshot CLI) never pays for OCCT. Run where nothing else has loaded it.
        import os
        import subprocess
        import sys

        from tests.python.support.paths import repo_path

        source = str(repo_path("packages/cadgen/src"))
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [source, os.environ.get("PYTHONPATH")]))}
        script = (
            "import json, sys\n"
            "from pathlib import Path\n"
            "from cadgen._internal.doors import document_snapshot\n"
            "from cadgen.store.view import view_dir_for\n"
            "from cadgen.snapshot_parts import list_rows\n"
            "document, tree = document_snapshot(Path(sys.argv[1]))\n"
            "package = view_dir_for(tree, document_hash=document)\n"
            "descriptor = json.loads((package / 'assembly.json').read_text())\n"
            "rows = list_rows(descriptor, package, selection=None)\n"
            "print(json.dumps([len(rows), sorted(name for name in sys.modules if name.split('.')[0] in ('OCP', 'build123d'))]))\n"
        )
        done = subprocess.run([sys.executable, "-c", script, str(self.workspace / "asm.step")],
                              capture_output=True, text=True, check=True, cwd=self.workspace, env=env)
        self.assertEqual([2, []], json.loads(done.stdout.strip().splitlines()[-1]), done.stderr)


class NoSurfacesTests(unittest.TestCase):
    """A view of a model with no faces says so: the image alone is blank, with exit 0."""

    @classmethod
    def setUpClass(cls) -> None:
        from build123d import Compound, Edge, Solid, Vertex
        from cadgen.step_export import export_build123d_step_file

        cls._roots = ClassCadRoots(prefix="snapshot-no-surfaces-")
        cls.workspace = cls._roots.cad_root
        # Not the other classes' assembly: the same bytes in another store share this
        # process's view of them.
        export_build123d_step_file(Solid.make_box(3, 2, 1), cls.workspace / "block.step")
        wire = Compound(children=[Edge.make_line((0, 0, 0), (10, 0, 0)), Edge.make_circle(5), Vertex(1, 2, 3)])
        export_build123d_step_file(wire, cls.workspace / "wire.step")
        export_build123d_step_file(Compound([]), cls.workspace / "empty.step")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._roots.cleanup()

    def warnings(self, name: str) -> list:
        from cadgen.snapshot_cli import resolve_step_render_job

        job = resolve_step_render_job({"input": name, "mode": "view", "outputs": []}, kind="step",
                                      input_path=self.workspace / name, root_path=self.workspace,
                                      reference_root=self.workspace)
        return job["resolved"].get("warnings") or []

    def test_curves_and_points_or_nothing_are_named_as_no_surfaces(self) -> None:
        for name in ("wire.step", "empty.step"):
            with self.subTest(name):
                self.assertEqual(["this model has no surfaces to draw: it is empty, or only curves and points"],
                                 self.warnings(name))
        self.assertEqual([], self.warnings("block.step"))


class FilterOccurrencesTests(unittest.TestCase):
    # A plate beside a `hardware` group of a pin and a nut; the rows are the leaves, the
    # groups come from the tree (``assembly_group_members``), and every id is a token.
    DESCRIPTOR, _ = tokenized({
        "occurrences": [{"id": "o1.1", "name": "plate"}, {"id": "o1.2.1", "name": "pin"}, {"id": "o1.2.2", "name": "nut"}],
        "assembly": {"root": {"id": "o1", "name": "asm", "children": [
            {"id": "o1.1", "name": "plate", "children": []},
            {"id": "o1.2", "name": "hardware", "children": [
                {"id": "o1.2.1", "name": "pin", "children": []},
                {"id": "o1.2.2", "name": "nut", "children": []},
            ]},
        ]}},
    })
    ROWS = DESCRIPTOR["occurrences"]

    def keep(self, **selection):
        from cadgen.assembly_lookup import assembly_group_members
        from cadgen.snapshot_parts import filter_occurrences

        groups = assembly_group_members(self.DESCRIPTOR)
        return [row["name"] for row in filter_occurrences(self.ROWS, selection, groups=groups)]

    def test_a_ref_matches_its_id_its_group_or_its_name(self) -> None:
        self.assertEqual(["plate", "pin", "nut"], self.keep())
        self.assertEqual(["pin", "nut"], self.keep(focus=[f"#{node_id(self.DESCRIPTOR, 'hardware')}"]))
        self.assertEqual(["nut"], self.keep(focus=["nut"]))
        self.assertEqual(["plate", "nut"], self.keep(hide=f"#{leaf_id(self.DESCRIPTOR, 'pin')}"))
        with self.assertRaisesRegex(ValueError, "No renderable parts remain"):
            self.keep(focus=["#o:" + "9" * 12])


if __name__ == "__main__":
    unittest.main()
