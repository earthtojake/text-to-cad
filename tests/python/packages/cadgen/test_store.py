"""The store (packages/cadgen/STORE.md): gate truth table, closure boundary
rule, hash-at-execution, publish rule, tree flattening, GC reachability, the
link/component decision and children-by-result."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PYTHON = sys.executable

IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

MODEL_TEXT = textwrap.dedent(
    """
    from cadgen import step
    from cadgen import build123d as bd

    SIZE = {size}


    @step
    def {name}():
        return bd.Box(SIZE, SIZE, SIZE)


    if __name__ == "__main__":
        {name}()
    """
)


class StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.previous = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = str(self.root / "store")

        def restore() -> None:
            if self.previous is None:
                os.environ.pop("CADGEN_CACHE_DIR", None)
            else:
                os.environ["CADGEN_CACHE_DIR"] = self.previous

        self.addCleanup(restore)
        from cadgen.store.closure import forget_model_files

        forget_model_files()
        self.addCleanup(forget_model_files)

    # --- fixtures -------------------------------------------------------------

    def model(self, name: str, size: float = 10.0, folder: Path | None = None) -> Path:
        path = (folder or self.root) / f"{name}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MODEL_TEXT.format(name=name, size=size), encoding="utf-8")
        return path

    def tree_for(self, label: str, payload: bytes = b"SURF\x00") -> str:
        from cadgen.store.objects import put_object
        from cadgen.store.trees import put_tree

        digest = put_object(payload)
        return put_tree(
            {
                "label": label,
                "entryKind": "part",
                "units": "mm",
                "components": {"c0": {"surf": digest, "brep": digest, "contentHash": "c0"}},
                "occurrences": [{"id": "o1", "name": f"{label}_body", "component": "c0", "transform": IDENTITY}],
                "links": [],
                "assembly": {"root": {"id": "o1", "name": label, "nodeType": "part", "leafPartIds": ["o1"], "children": []}},
                "stats": {"occurrenceCount": 1, "linkCount": 0},
            }
        )

    def record(self, script: Path, *, tree: str, children=(), output: Path | None = None) -> dict:
        from cadgen.store.closure import current_closure_hash
        from cadgen.store.records import note_output, write_record

        files = [str(script)]
        outputs = {}
        if output is not None:
            outputs[str(output.resolve())] = {"sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
        record = {
            "entryKind": "part",
            "sourceKind": "python",
            "tree": tree,
            "closure": {"hash": current_closure_hash(script, files), "files": files, "static": False},
            "children": [{"model": str(child), "tree": child_tree} for child, child_tree in children],
            "outputs": outputs,
        }
        write_record(script, record)
        if output is not None:
            note_output(output, script)
        return record

    def stale_clause(self, script: Path):
        from cadgen.store.gate import stale

        verdict = stale(script)
        if not verdict.stale:
            return None
        return next(c["clause"] for c in verdict.clauses if c.get("stale"))


class GateTruthTable(StoreCase):
    def test_clause_1_no_record(self) -> None:
        script = self.model("plate")
        self.assertEqual(self.stale_clause(script), 1)

    def test_a_complete_record_is_current(self) -> None:
        script = self.model("plate")
        out = self.root / "plate.step"
        out.write_bytes(b"ISO-10303-21;\n")
        self.record(script, tree=self.tree_for("plate"), output=out)
        self.assertIsNone(self.stale_clause(script))

    def test_clause_2_a_semantic_edit_is_stale_but_a_comment_is_not(self) -> None:
        script = self.model("plate")
        self.record(script, tree=self.tree_for("plate"))
        script.write_text(script.read_text(encoding="utf-8") + "\n# a trailing comment\n", encoding="utf-8")
        self.assertIsNone(self.stale_clause(script), "comments and formatting are not inputs")
        script.write_text(script.read_text(encoding="utf-8").replace("SIZE = 10.0", "SIZE = 11.0"), encoding="utf-8")
        self.assertEqual(self.stale_clause(script), 2)

    def test_clause_3_a_child_whose_result_moved_or_is_itself_stale(self) -> None:
        child = self.model("pin")
        parent = self.model("arm")
        child_tree = self.tree_for("pin")
        self.record(child, tree=child_tree)
        self.record(parent, tree=self.tree_for("arm"), children=[(child, child_tree)])
        self.assertIsNone(self.stale_clause(parent))

        # The child's result changed under the parent's pin.
        self.record(child, tree=self.tree_for("pin", payload=b"SURF\x01"))
        self.assertEqual(self.stale_clause(parent), 3)

        # The pin matches again but the child itself is stale (its source moved on).
        self.record(child, tree=child_tree)
        self.assertIsNone(self.stale_clause(parent))
        child.write_text(child.read_text(encoding="utf-8").replace("SIZE = 10.0", "SIZE = 12.0"), encoding="utf-8")
        self.assertEqual(self.stale_clause(parent), 3)

    def test_clause_3_an_identical_result_after_a_child_edit_leaves_the_parent_current(self) -> None:
        child = self.model("pin")
        parent = self.model("arm")
        child_tree = self.tree_for("pin")
        self.record(parent, tree=self.tree_for("arm"), children=[(child, child_tree)])
        # The child was edited and rebuilt, and produced the SAME tree.
        child.write_text(child.read_text(encoding="utf-8").replace("SIZE = 10.0", "SIZE = 10.0 * 1"), encoding="utf-8")
        self.record(child, tree=child_tree)
        self.assertIsNone(self.stale_clause(parent), "a parent depends on its children by result")

    def test_clause_4_a_missing_component_object(self) -> None:
        from cadgen.store.objects import object_path

        script = self.model("plate")
        tree = self.tree_for("plate", payload=b"SURF\x02")
        self.record(script, tree=tree)
        self.assertIsNone(self.stale_clause(script))
        object_path(hashlib.sha256(b"SURF\x02").hexdigest()).unlink()
        self.assertEqual(self.stale_clause(script), 4)

    def test_clause_5_an_output_that_changed_on_disk(self) -> None:
        script = self.model("plate")
        out = self.root / "plate.step"
        out.write_bytes(b"ISO-10303-21;\n")
        self.record(script, tree=self.tree_for("plate"), output=out)
        out.write_bytes(b"ISO-10303-21; edited\n")
        self.assertEqual(self.stale_clause(script), 5)
        out.unlink()
        self.assertEqual(self.stale_clause(script), 5)


class ClosureBoundaryRule(StoreCase):
    def test_a_model_taken_through_its_function_is_a_child_anything_else_is_source(self) -> None:
        from cadgen.store.closure import static_closure

        self.model("arm")
        self.model("plate")
        lib = self.root / "lib"
        lib.mkdir()
        (lib / "__init__.py").write_text("", encoding="utf-8")
        (lib / "frame.py").write_text("WIDTH = 4\n", encoding="utf-8")
        robot = self.root / "robot.py"
        robot.write_text(
            textwrap.dedent(
                """
                from cadgen import step
                from arm import arm            # only the model function: a result edge
                from plate import SIZE         # a literal from a model file: a value edge
                from lib import frame          # a plain module: a source edge


                @step
                def robot():
                    return arm()
                """
            ),
            encoding="utf-8",
        )
        closure = static_closure(robot)
        children = {p.name for p in closure.child_models}
        sources = {p.name for p in closure.source_files}
        self.assertEqual(children, {"arm.py", "plate.py"})
        self.assertNotIn("plate.py", sources)
        self.assertIn("frame.py", sources)
        self.assertNotIn("arm.py", sources)
        # Constants by value: the literal is tracked by its value hash, not the file.
        self.assertEqual({"plate.py": {"SIZE"}}, {Path(k).name: set(v) for k, v in closure.constants.items()})

    # --- constants by value, functions by file, models by result ----------------

    def _mirror_over(self, handlebar_text: str, mirror_import: str = "from handlebar import MIRROR_MOUNT_LEFT") -> Path:
        (self.root / "handlebar.py").write_text(textwrap.dedent(handlebar_text), encoding="utf-8")
        mirror = self.root / "mirror.py"
        mirror.write_text(
            textwrap.dedent(
                f"""
                from cadgen import step
                from cadgen import build123d as bd
                {mirror_import}


                @step
                def mirror():
                    return bd.Box(1, 1, 1)
                """
            ),
            encoding="utf-8",
        )
        return mirror

    HANDLEBAR = """
        from cadgen import step
        from cadgen import build123d as bd

        _TOP = (-104.0, 0.0, 9.0)                          # computed, not a literal: by VALUE
        MIRROR_MOUNT_LEFT = (_TOP[0] - 16.0, 40.0, _TOP[2] + 6.0)


        @step
        def handlebar():
            return bd.Box(2, 2, 2)
        """

    def _record_with_constants(self, script: Path) -> None:
        from cadgen.store.closure import build_closure
        from cadgen.store.records import write_record

        closure = build_closure(script, executed={})
        write_record(
            script,
            {
                "entryKind": "part",
                "sourceKind": "python",
                "tree": self.tree_for("mirror"),
                "closure": {"hash": closure.hash, "files": list(closure.files), "static": False},
                "constants": closure.constants,
                "children": [],
                "outputs": {},
            },
        )
        self.assertEqual({"handlebar.py": {"MIRROR_MOUNT_LEFT"}}, {k: set(v) for k, v in closure.constants.items()})
        self.assertNotIn("handlebar.py", closure.files)

    def test_a_comment_edit_to_the_constants_module_leaves_the_importer_current(self) -> None:
        mirror = self._mirror_over(self.HANDLEBAR)
        self._record_with_constants(mirror)
        self.assertIsNone(self.stale_clause(mirror))
        handlebar = self.root / "handlebar.py"
        handlebar.write_text(handlebar.read_text(encoding="utf-8") + "\n# a comment, and a new helper the importer never took\n", encoding="utf-8")
        handlebar.write_text(handlebar.read_text(encoding="utf-8").replace("return bd.Box(2, 2, 2)", "return bd.Box(3, 3, 3)"), encoding="utf-8")
        self.assertIsNone(self.stale_clause(mirror), "handlebar's own body is not mirror's source")

    def test_changing_the_constant_value_makes_the_importer_stale(self) -> None:
        from cadgen.store.gate import stale

        mirror = self._mirror_over(self.HANDLEBAR)
        self._record_with_constants(mirror)
        handlebar = self.root / "handlebar.py"
        handlebar.write_text(handlebar.read_text(encoding="utf-8").replace("_TOP[0] - 16.0", "_TOP[0] - 21.0"), encoding="utf-8")
        self.assertEqual(2, self.stale_clause(mirror))
        self.assertIn("constant changed: MIRROR_MOUNT_LEFT in handlebar.py", stale(mirror).reason())

    def test_an_unhashable_constant_is_a_source_edge(self) -> None:
        from cadgen.store.closure import static_closure

        mirror = self._mirror_over(self.HANDLEBAR.replace("(_TOP[0] - 16.0, 40.0, _TOP[2] + 6.0)", "bd.Pos(-120.0, 40.0, 15.0)"))
        closure = static_closure(mirror)
        self.assertIn("handlebar.py", {p.name for p in closure.source_files})
        self.assertEqual({}, closure.constants)

    def test_a_helper_function_import_is_a_source_edge(self) -> None:
        from cadgen.store.closure import static_closure

        mirror = self._mirror_over(
            self.HANDLEBAR + "\n\ndef mount_offset(side):\n    return MIRROR_MOUNT_LEFT\n",
            mirror_import="from handlebar import MIRROR_MOUNT_LEFT, mount_offset",
        )
        closure = static_closure(mirror)
        self.assertIn("handlebar.py", {p.name for p in closure.source_files})
        self.assertEqual({}, closure.constants)

    def test_the_record_carries_the_constants_block(self) -> None:
        from cadgen.store.records import read_record

        mirror = self._mirror_over(self.HANDLEBAR)
        self._record_with_constants(mirror)
        record = read_record(mirror) or {}
        self.assertEqual(["MIRROR_MOUNT_LEFT"], list(record["constants"]["handlebar.py"]))
        self.assertRegex(record["constants"]["handlebar.py"]["MIRROR_MOUNT_LEFT"], r"^[0-9a-f]{64}$")

    def test_relative_imports_inside_a_lib_package_are_in_the_closure(self) -> None:
        # lyra's `lib/digits.py` reaches `lib/chain.py` with `from .chain import ...`;
        # a tracer that only follows absolute imports leaves chain.py out of the
        # closure, and an edit to it never rebuilds the finger.
        from cadgen.store.closure import static_closure

        lib = self.root / "lib"
        lib.mkdir()
        (lib / "__init__.py").write_text("", encoding="utf-8")
        (lib / "chain.py").write_text("LENGTH = 40\n", encoding="utf-8")
        (lib / "common.py").write_text("def attach(a, b):\n    return a\n", encoding="utf-8")
        (lib / "palette.py").write_text("PEARL = (1, 1, 1)\n", encoding="utf-8")
        (lib / "digits.py").write_text(
            textwrap.dedent(
                """
                from .chain import LENGTH
                from . import common
                from .palette import *


                def build_finger():
                    return common.attach(LENGTH, PEARL)
                """
            ),
            encoding="utf-8",
        )
        finger = self.root / "finger.py"
        finger.write_text(
            textwrap.dedent(
                """
                from cadgen import step
                from lib.digits import build_finger


                @step
                def finger():
                    return build_finger()
                """
            ),
            encoding="utf-8",
        )
        sources = {p.name for p in static_closure(finger).source_files}
        self.assertEqual(sources, {"digits.py", "chain.py", "common.py", "palette.py"})


class HashAtExecution(StoreCase):
    def test_a_file_is_hashed_with_the_bytes_that_ran(self) -> None:
        from cadgen.store.closure import ExecutionHashes

        module = self.root / "helper.py"
        module.write_text("VALUE = 1\n", encoding="utf-8")
        with ExecutionHashes() as executed:
            exec(compile(module.read_bytes(), str(module), "exec"), {})  # noqa: S102
            module.write_text("VALUE = 2\n", encoding="utf-8")  # edited mid-build
        recorded = executed.hashes[str(module.resolve())]
        with ExecutionHashes() as again:
            exec(compile(module.read_bytes(), str(module), "exec"), {})  # noqa: S102
        self.assertNotEqual(recorded, again.hashes[str(module.resolve())])
        module.write_text("VALUE = 1\n", encoding="utf-8")
        with ExecutionHashes() as original:
            exec(compile(module.read_bytes(), str(module), "exec"), {})  # noqa: S102
        self.assertEqual(recorded, original.hashes[str(module.resolve())])


class PublishRule(StoreCase):
    def test_a_build_against_older_sources_never_replaces_a_current_record(self) -> None:
        from cadgen.store.closure import current_closure_hash
        from cadgen.store.publish import decide

        script = self.model("plate")
        now = current_closure_hash(script, [str(script)])
        self.assertTrue(decide(script, ran_closure_hash=now, ran_files=[str(script)]).publish_outputs)
        # A record that already matches the sources as they are now wins over
        # a build that ran against something older.
        self.record(script, tree=self.tree_for("plate"))
        self.assertFalse(decide(script, ran_closure_hash="0" * 64, ran_files=[str(script)]).publish_outputs)
        # With nothing current on disk, an older build still publishes (better than nothing).
        script.write_text(script.read_text(encoding="utf-8").replace("SIZE = 10.0", "SIZE = 13.0"), encoding="utf-8")
        self.assertTrue(decide(script, ran_closure_hash="0" * 64, ran_files=[str(script)]).publish_outputs)


class TreeFlattening(StoreCase):
    def test_links_expand_with_rebased_ids_composed_placements_and_the_link_name(self) -> None:
        from cadgen.store.trees import flatten, put_tree

        pin = self.tree_for("pin")
        arm = put_tree(
            {
                "label": "arm",
                "entryKind": "assembly",
                "units": "mm",
                "components": {},
                "occurrences": [],
                "links": [
                    {"id": "o1.1", "name": "pin_left", "tree": pin, "transform": [1, 0, 0, -15, 0, 1, 0, 0, 0, 0, 1, 2, 0, 0, 0, 1]},
                    {"id": "o1.2", "name": "pin_right", "tree": pin, "transform": [1, 0, 0, 15, 0, 1, 0, 0, 0, 0, 1, 2, 0, 0, 0, 1]},
                ],
                "assembly": {"root": {"id": "o1", "name": "arm", "nodeType": "assembly", "children": [
                    {"id": "o1.1", "name": "pin_left", "nodeType": "link", "tree": pin, "children": []},
                    {"id": "o1.2", "name": "pin_right", "nodeType": "link", "tree": pin, "children": []},
                ]}},
                "stats": {"occurrenceCount": 0, "linkCount": 2},
            }
        )
        robot = put_tree(
            {
                "label": "robot",
                "entryKind": "assembly",
                "units": "mm",
                "components": {},
                "occurrences": [],
                "links": [{"id": "o1.1", "name": "arm_front", "tree": arm, "transform": [1, 0, 0, 0, 0, 1, 0, 10, 0, 0, 1, 5, 0, 0, 0, 1]}],
                "assembly": {"root": {"id": "o1", "name": "robot", "nodeType": "assembly", "children": [
                    {"id": "o1.1", "name": "arm_front", "nodeType": "link", "tree": arm, "children": []},
                ]}},
                "stats": {"occurrenceCount": 0, "linkCount": 1},
            }
        )
        flat = flatten(robot)
        by_id = {o["id"]: o for o in flat["occurrences"]}
        self.assertEqual(sorted(by_id), ["o1.1.1", "o1.1.2"])
        self.assertEqual(by_id["o1.1.1"]["name"], "pin_left")
        self.assertEqual(by_id["o1.1.2"]["name"], "pin_right")
        self.assertEqual(by_id["o1.1.1"]["transform"][3::4][:3], [-15, 10, 7])
        self.assertEqual(by_id["o1.1.2"]["transform"][3::4][:3], [15, 10, 7])
        self.assertEqual(list(flat["components"]), ["c0"], "one shared component, stored once")
        self.assertEqual(flat["assembly"]["root"]["children"][0]["nodeType"], "subassembly")


class GcReachability(StoreCase):
    def test_reachable_through_links_kept_orphans_swept_after_grace(self) -> None:
        from cadgen.store.gc import collect
        from cadgen.store.objects import has_object, object_path, put_object
        from cadgen.store.trees import put_tree

        pin = self.tree_for("pin")
        arm = put_tree(
            {
                "label": "arm", "entryKind": "assembly", "units": "mm", "components": {}, "occurrences": [],
                "links": [{"id": "o1.1", "name": "pin", "tree": pin, "transform": IDENTITY}],
                "stats": {"occurrenceCount": 0, "linkCount": 1},
            }
        )
        self.record(self.model("arm"), tree=arm)
        old_orphan = put_object(b"orphan-old")
        fresh_orphan = put_object(b"orphan-fresh")
        stale_time = time.time() - 7200
        os.utime(object_path(old_orphan), (stale_time, stale_time))

        report = collect(grace_seconds=3600, dry_run=False)
        self.assertEqual(report.removed, 1)
        self.assertFalse(has_object(old_orphan))
        self.assertTrue(has_object(fresh_orphan), "within the grace window a build may still pin it")
        self.assertTrue(has_object(pin) and has_object(arm))
        self.assertTrue(has_object(hashlib.sha256(b"SURF\x00").hexdigest()), "reachable through the link")


class LinkOrComponent(StoreCase):
    """Kernel-backed: a materialized child placed unmodified is a link; a
    modified one is the parent's own components."""

    def test_placed_children_link_and_modified_children_become_components(self) -> None:
        from build123d import Box, Compound, Location, Plane

        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.materialize import materialize, reset_memo

        pin_tree, _tree, _stats = build_tree_from_compound(
            Box(4, 4, 12), root_name="pin", entry_kind="part", single_component=True
        )
        reset_memo()
        pin = materialize(pin_tree, label="pin")
        left = pin.moved(Location((-15, 0, 2)))
        left.label = "pin_left"
        right = Location((15, 0, 2)) * pin
        right.label = "pin_right"
        mirrored = pin.mirror(Plane.XZ)
        mirrored.label = "pin_mirrored"
        cut = pin - Box(1, 1, 1)
        cut.label = "pin_cut"
        # located() deep-copies the geometry (BRepBuilderAPI_Copy): new bytes,
        # a new cid, and therefore the parent's own component — as it always was.
        relocated = pin.located(Location((0, 20, 2)))
        relocated.label = "pin_relocated"
        bar = Box(40, 8, 4)
        bar.label = "bar"
        arm_tree, arm, _stats = build_tree_from_compound(
            Compound(children=[bar, left, right, mirrored, cut, relocated], label="arm"),
            root_name="arm",
            entry_kind="assembly",
        )
        self.assertEqual({l["name"] for l in arm["links"]}, {"pin_left", "pin_right"})
        self.assertEqual({l["tree"] for l in arm["links"]}, {pin_tree})
        self.assertEqual({o["name"] for o in arm["occurrences"]}, {"bar", "pin_mirrored", "pin_cut", "pin_relocated"})

        # The materialize contract: the parent got the child's geometry and labels.
        reset_memo()
        again = materialize(arm_tree, label="arm")
        self.assertEqual(
            sorted(c.label for c in again.children),
            sorted(["bar", "pin_left", "pin_right", "pin_mirrored", "pin_cut", "pin_relocated"]),
        )


class StoreCli(StoreCase):
    def run_cli(self, argv):
        import io
        from contextlib import redirect_stdout

        from cadgen.cli import store as store_cli

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = store_cli.main(argv)
        return code, buffer.getvalue()

    def test_info_counts_objects_and_entries(self) -> None:
        import json

        script = self.model("plate")
        self.record(script, tree=self.tree_for("plate"))
        code, out = self.run_cli(["info", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["root"], os.environ["CADGEN_CACHE_DIR"])
        self.assertEqual(payload["objects"]["count"], 2, "one component object and one tree")
        self.assertEqual(payload["index"]["model"], 1)

    def test_why_reports_the_clause_and_exits_nonzero_when_stale(self) -> None:
        import json

        script = self.model("plate")
        code, out = self.run_cli(["why", str(script), "--json"])
        self.assertEqual(code, 1)
        self.assertTrue(json.loads(out)["stale"])
        self.record(script, tree=self.tree_for("plate"))
        code, out = self.run_cli(["why", str(script)])
        self.assertEqual(code, 0)
        self.assertIn("verdict current", out)
        self.assertIn("[ok] 2 closure", out)

    def test_gc_dry_run_removes_nothing(self) -> None:
        from cadgen.store.objects import has_object, put_object

        orphan = put_object(b"orphan")
        code, out = self.run_cli(["gc", "--dry-run", "--grace-hours", "0"])
        self.assertEqual(code, 0)
        self.assertIn("would remove 1 objects", out)
        self.assertTrue(has_object(orphan))


class ChildrenByResult(StoreCase):
    """End to end over real model runs: a child edit with identical geometry
    leaves the parent current; a geometry change rebuilds it."""

    def run_model(self, script: Path) -> str:
        env = dict(os.environ)
        env.update({"CADGEN_DAEMON": "0", "PYTHONPATH": str(REPO / "packages/cadgen/src")})
        completed = subprocess.run(
            [PYTHON, script.name], cwd=str(script.parent), env=env, capture_output=True, text=True, timeout=600
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        return completed.stdout.strip().splitlines()[-1].split(" ", 1)[0]

    def test_a_parent_pins_its_children_by_result(self) -> None:
        src = self.root / "src"
        src.mkdir()
        for name in ("link_pin.py", "link_arm.py"):
            shutil.copyfile(REPO / "models/examples/src" / name, src / name)
        (self.root / "STEP").mkdir()
        pin, arm = src / "link_pin.py", src / "link_arm.py"

        self.assertEqual(self.run_model(arm), "built")
        self.assertEqual(self.run_model(arm), "current")
        self.assertEqual(self.run_model(pin), "current", "the child was built inline and recorded")

        pin.write_text(pin.read_text(encoding="utf-8").replace("height=12.0", "height=12.0 * 1.0"), encoding="utf-8")
        self.assertEqual(self.run_model(pin), "built", "a semantic edit rebuilds the child")
        self.assertEqual(self.run_model(arm), "current", "identical geometry: the parent's pin still holds")

        pin.write_text(pin.read_text(encoding="utf-8").replace("radius=2.0", "radius=2.5"), encoding="utf-8")
        self.assertEqual(self.run_model(arm), "built", "a geometry change reaches the parent")

        from cadgen.store.records import read_record

        record = read_record(arm)
        self.assertEqual([Path(c["model"]).name for c in record["children"]], ["link_pin.py"])
        self.assertEqual(record["children"][0]["tree"], read_record(pin)["tree"])


if __name__ == "__main__":
    unittest.main()
