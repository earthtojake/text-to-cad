"""The two sides of the store — a law (packages/cadgen/STORE.md §2).

``objects/`` and ``index/document`` are the ARTIFACT side; ``index/model`` and
``index/output`` are the CODE side. Three properties, one test each, over a
real link trio (a pin, an arm placing the pin twice, a robot placing the arm
twice and the pin once) built through the real pipeline:

1. no object references source;
2. no reader consults a record — the doors, the viewer (catalog, render
   path AND status), and the mesh ledger find a tree through ``index/document``
   alone; the viewer has no exception;
3. records are deletable — ``rm -rf index/model index/output`` loses no
   artifact, and the rebuild re-creates the records without a new object.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

REPO = Path(__file__).resolve().parents[4]

PIN = '''
from cadgen import step
from cadgen import build123d as bd

RADIUS = 2.0


@step(out="pin.step")
def pin():
    return bd.Cylinder(RADIUS, 14)


if __name__ == "__main__":
    pin()
'''

ARM = '''
from cadgen import label_shape, step
from cadgen import build123d as bd
from pin import RADIUS, pin


@step(out="arm.step", kind="assembly")
def arm():
    bar = label_shape(bd.Box(40, 4 * RADIUS, 4), "bar")
    left = bd.Pos(-15, 0, 2) * pin()
    left.label = "pin_left"
    right = bd.Pos(15, 0, 2) * pin()
    right.label = "pin_right"
    return bd.Compound(children=[bar, left, right])


if __name__ == "__main__":
    arm()
'''

ROBOT = '''
from cadgen import label_shape, step
from cadgen import build123d as bd
from arm import arm
from pin import pin


@step(out="robot.step", kind="assembly")
def robot():
    base = label_shape(bd.Box(60, 60, 3), "base")
    front = bd.Pos(0, 20, 5) * arm()
    front.label = "arm_front"
    back = bd.Pos(0, -20, 5) * arm()
    back.label = "arm_back"
    post = bd.Pos(0, 0, 10) * pin()
    post.label = "post"
    return bd.Compound(children=[base, front, back, post])


if __name__ == "__main__":
    robot()
'''

SCRIPTS = {"pin.py": PIN, "arm.py": ARM, "robot.py": ROBOT}


@contextlib.contextmanager
def forbid_record_reads():
    """Fail the moment anything reads ``index/model`` or ``index/output``."""
    import cadgen.store.index as index
    import cadgen.store.records as records

    real = index.read_entry

    def guarded(kind: str, key: str):
        if kind in ("model", "output"):
            raise AssertionError(f"a reader consulted index/{kind} (STORE.md §2, the law)")
        return real(kind, key)

    with mock.patch.object(index, "read_entry", guarded), mock.patch.object(records, "read_entry", guarded):
        yield


def _cli(*argv: str, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in [str(REPO / "packages" / "cadgen" / "src"), env.get("PYTHONPATH", "")] if p
    )
    return subprocess.run(
        [sys.executable, "-m", "cadgen.cli", *argv],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=600,
    )


class TwoSidesLaw(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = temporary_directory(prefix="two-sides-")
        cls.root = Path(cls._tmp.name) / "workspace"
        cls.root.mkdir()
        cls.cache = Path(cls._tmp.name) / "cadgen-cache"
        cls.cache.mkdir()
        cls._previous_cache = os.environ.get("CADGEN_CACHE_DIR")
        cls._previous_cwd = Path.cwd()
        os.environ["CADGEN_CACHE_DIR"] = str(cls.cache)
        os.chdir(cls.root)
        for name, text in SCRIPTS.items():
            (cls.root / name).write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
        cls._build_all()
        cls.robot_step = cls.root / "robot.step"
        assert cls.robot_step.is_file(), "the fixture build wrote no robot.step"

    @classmethod
    def tearDownClass(cls) -> None:
        os.chdir(cls._previous_cwd)
        if cls._previous_cache is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = cls._previous_cache
        cls._tmp.cleanup()

    @classmethod
    def _build_all(cls) -> None:
        from cadgen.generation import generate_step_targets

        for name in ("pin.py", "arm.py", "robot.py"):
            assert generate_step_targets([str(cls.root / name)]) == 0, f"building {name} failed"

    # --- helpers ------------------------------------------------------------------

    def _objects(self) -> set[str]:
        return {p.name for p in (self.cache / "objects").rglob("*") if p.is_file()}

    def _trees(self) -> dict[str, dict]:
        trees: dict[str, dict] = {}
        for path in (self.cache / "objects").rglob("*"):
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_bytes())
            except (UnicodeDecodeError, ValueError):
                continue
            if isinstance(payload, dict) and "occurrences" in payload:
                trees[path.name] = payload
        return trees

    def _document_trees(self) -> dict[str, str]:
        from cadgen.catalog import result_tree_for

        return {name: result_tree_for(self.root / f"{name}.step") for name in ("pin", "arm", "robot")}

    # --- property 1: no object references source ------------------------------------

    def test_property_1_no_object_references_source(self) -> None:
        from cadgen.store.index import model_key
        from cadgen.store.records import read_record

        trees = self._trees()
        self.assertGreaterEqual(len(trees), 3, "expected a tree per model")
        forbidden = {str(self.root), str(self.root.resolve()), ".py"}
        for name in SCRIPTS:
            script = self.root / name
            forbidden.add(model_key(script))
            record = read_record(script) or {}
            forbidden.add(str((record.get("closure") or {}).get("hash") or "") or "<none>")
            for module, names in (record.get("constants") or {}).items():
                forbidden.update(names.values())
        for tree_hash, tree in trees.items():
            text = json.dumps(tree)
            for needle in forbidden:
                self.assertNotIn(needle, text, f"tree {tree_hash[:12]} references source: {needle!r}")
            for key in ("closure", "sourceHash", "sourcePath", "sourceClosureHash", "script", "model", "record"):
                self.assertNotIn(key, tree, f"tree {tree_hash[:12]} carries {key!r}")

    # --- property 2: a reader never consults a record -------------------------------

    def test_property_2_readers_never_consult_records(self) -> None:
        from cadgen import catalog
        from cadgen._internal import doors
        from cadgen.step_artifact_cli import build_step_artifact
        from cadgen.step_export_target import export_cad_target
        from cadgen.viewer import artifact_status, scanner, store_paths

        expected = self._document_trees()
        self.assertTrue(all(expected.values()), expected)
        out = self.root / "exports" / "robot.stl"
        with forbid_record_reads():
            for name, tree in expected.items():
                document = self.root / f"{name}.step"
                self.assertEqual(tree, catalog.result_tree_for(document))
                self.assertEqual(tree, doors.document_tree(document))
                self.assertEqual(tree, store_paths.result_tree(document))
                self.assertTrue((catalog.result_view_dir(document) / "assembly.json").is_file())
                self.assertIsInstance(store_paths.result_descriptor(tree), dict)
            listed = scanner.scan_cad_directory(str(self.root))
            self.assertIn("robot.step", json.dumps(listed))
            # The viewer's status — the badge included — is artifact-side only.
            verdict = artifact_status.resolve_artifact_verdict(str(self.robot_step), str(self.root))
            self.assertTrue(verdict.get("ok"), verdict)
            self.assertNotIn("generated", verdict)
            self.assertEqual("ready", artifact_status.artifact_status(str(self.robot_step), str(self.root))["state"])
            payload = export_cad_target(self.robot_step, [("stl", out)], repo_root=self.root)
            self.assertTrue(out.is_file(), payload)
            # A second export at the same variant is satisfied by the ARTIFACT-side ledger.
            before = out.stat().st_mtime_ns
            export_cad_target(self.robot_step, [("stl", out)], repo_root=self.root)
            self.assertEqual(before, out.stat().st_mtime_ns, "the mesh ledger did not satisfy the re-export")
            result = build_step_artifact(repo_root=self.root, step=self.robot_step)
            self.assertTrue(result.get("ok"), result)
            self.assertTrue(result.get("skipped"), "a document with a tree for its bytes is current at `step compile`")

    # --- property 3: records are deletable ------------------------------------------

    def test_property_3_records_are_deletable(self) -> None:
        from cadgen._internal import doors
        from cadgen.store.records import read_record
        from cadgen.viewer import scanner, store_paths

        expected = self._document_trees()
        trees = set(self._trees())
        shutil.rmtree(self.cache / "index" / "model")
        shutil.rmtree(self.cache / "index" / "output", ignore_errors=True)
        try:
            with mock.patch("cadgen.daemon.executors.submit_compile", side_effect=AssertionError("a compile was submitted for a document whose tree exists")):
                for name, tree in expected.items():
                    document = self.root / f"{name}.step"
                    self.assertEqual(tree, doors.document_tree(document))
                    self.assertEqual(tree, store_paths.result_tree(document))
                self.assertIn("robot.step", json.dumps(scanner.scan_cad_directory(str(self.root))))
            stl = _cli("stl", "build", "robot.step", "exports/robot_no_records.stl", cwd=self.root)
            self.assertEqual(0, stl.returncode, stl.stderr)
            self.assertTrue((self.root / "exports" / "robot_no_records.stl").is_file())
            inspect = _cli("step", "inspect", "refs", "robot.step", "#o1", cwd=self.root)
            self.assertEqual(0, inspect.returncode, inspect.stderr)
            if shutil.which("node"):
                snapshot = _cli("step", "snapshot", "robot.step", "exports/robot.png", cwd=self.root)
                self.assertEqual(0, snapshot.returncode, snapshot.stderr)
                self.assertTrue((self.root / "exports" / "robot.png").is_file())
            # Readers may cache what they derive (tessellations); they build no tree.
            self.assertEqual(trees, set(self._trees()), "a reader wrote a tree")
            objects = self._objects()
        finally:
            # The rebuild: records come back; no tree is rebuilt whose objects exist.
            self._build_all()
        for name in SCRIPTS:
            self.assertIsNotNone(read_record(self.root / name), f"{name} has no record after the rebuild")
        self.assertEqual(expected, self._document_trees(), "the rebuild changed a tree hash")
        self.assertEqual(objects, self._objects(), "the rebuild wrote new objects")


if __name__ == "__main__":
    unittest.main()
