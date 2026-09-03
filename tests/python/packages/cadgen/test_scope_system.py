"""W1–W3 of design/production-architecture.md: scope capture, the frozen
value contract (gated by byte-identity through the REAL packager), and the
compose seams."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from build123d import Color, Compound, Location, Pos  # noqa: E402
from build123d.topology import Solid  # noqa: E402

from cadgen import compose  # noqa: E402
from cadgen._internal import scope_capture, scope_store  # noqa: E402
from cadgen._internal.component_package import build_package_from_compound  # noqa: E402
from cadgen.coordination.lock import exclusive  # noqa: E402
from cadgen.coordination.paths import write_lock_path  # noqa: E402


def _demo_compound() -> Compound:
    from build123d import Cylinder

    box_a = Pos(0, 0, 0) * Solid.make_box(10, 10, 10)
    box_a.label = "widget_a"
    box_a.cad_material = {"roughness": 0.4, "metalness": 0.9}
    # An OBJECT-class leaf (constructor takes dimensions, not TopoDS): thaw
    # must reconstruct by ShapeType, never by the recorded Python class.
    pin = Pos(0, -30, 0) * Cylinder(4, 12)
    pin.label = "pin"
    box_b = Pos(40, 0, 0) * Solid.make_box(8, 8, 20)
    box_b.label = "widget_b"
    box_b._color = Color(0.2, 0.3, 0.4, 1.0)
    inner = Compound(children=[box_b], label="subassembly")
    inner.location = Location((0, 25, 0))
    root = Compound(children=[box_a, pin, inner], label="demo")
    root._color = Color(0.8, 0.1, 0.1, 1.0)
    root.assembly_mates = [{"id": "m1", "type": "revolute",
                            "fixed": "#widget_a.f1", "moving": "#widget_b.f2"}]
    return root


def _package(compound: Compound, package_dir: Path) -> dict:
    with exclusive(write_lock_path(package_dir)):
        build_package_from_compound(
            compound, package_dir=package_dir, root_name="demo")
    descriptor = json.loads((package_dir / "assembly.json").read_text())
    return {
        "cids": sorted((descriptor.get("components") or {}).keys()),
        "occurrences": [
            {k: occ.get(k) for k in ("id", "name", "component", "transform")}
            for occ in descriptor.get("occurrences") or []
        ],
        # Mates ride the source sidecar; the descriptor is STEP-pure.
        "assemblyMates": (
            json.loads((package_dir / "source.json").read_text()).get("assemblyMates")
            if (package_dir / "source.json").is_file()
            else None
        ),
        "componentBytes": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((package_dir / "components").glob("*.surf"))
        },
    }


class StoreIsolatedTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["CADGEN_CACHE_DIR"] = str(Path(self._tmp.name) / "store")
        with compose._lock:
            for key in compose._stats:
                compose._stats[key] = 0

    def tearDown(self) -> None:
        os.environ.pop("CADGEN_CACHE_DIR", None)
        self._tmp.cleanup()

    def _dir(self, name: str) -> Path:
        path = Path(self._tmp.name) / name
        path.mkdir(parents=True, exist_ok=True)
        return path


class FreezeThawPackagerGate(StoreIsolatedTest):
    """The W2 gate: fresh and thawed compounds must package byte-identically."""

    def test_labeled_colored_mated_compound(self) -> None:
        fresh_fp = _package(_demo_compound(), self._dir("fresh"))
        frozen = scope_store.freeze_value(_demo_compound())
        thawed = scope_store.thaw_value(frozen)
        thawed_fp = _package(thawed, self._dir("thawed"))
        self.assertEqual(fresh_fp, thawed_fp)

    def test_occurrence_tree_compound(self) -> None:
        from cadgen.instances import compound_from_instances

        proto = Solid.make_box(6, 6, 6)
        proto.label = "block"

        def build():
            return compound_from_instances(
                "grid",
                [(proto, Location((float(i * 10), 0, 0)), f"block_{i}")
                 for i in range(3)],
            )

        fresh_fp = _package(build(), self._dir("fresh_tree"))
        thawed = scope_store.thaw_value(scope_store.freeze_value(build()))
        thawed_fp = _package(thawed, self._dir("thawed_tree"))
        self.assertEqual(fresh_fp, thawed_fp)

    def test_envelope_round_trip(self) -> None:
        frozen = scope_store.freeze_value(
            {"shape": _demo_compound(), "params": "demo.params.js"})
        thawed = scope_store.thaw_value(frozen)
        self.assertEqual(thawed["params"], "demo.params.js")
        self.assertEqual(thawed["shape"].label, "demo")

    def test_unfreezable_envelope_extra(self) -> None:
        with self.assertRaises(scope_store.Unfreezable):
            scope_store.freeze_value({"shape": _demo_compound(),
                                      "callback": lambda: None})


class ScopeCaptureTest(StoreIsolatedTest):
    def _write_model(self, root: Path) -> Path:
        (root / "_spec.py").write_text("SIZE = 5.0\n")
        (root / "_helper.py").write_text(
            "import _spec\n\ndef size():\n    return _spec.SIZE\n")
        entry = root / "part.py"
        entry.write_text(textwrap.dedent("""\
            import _helper

            from cadgen import step
            @step
            def model():
                from build123d.topology import Solid
                s = _helper.size()
                box = Solid.make_box(s, s, s)
                box.label = "part"
                return box


            if __name__ == "__main__":
                model()
            """))
        return entry

    def test_static_closure_reaches_transitive_imports(self) -> None:
        root = self._dir("model")
        entry = self._write_model(root)
        closure = scope_capture.static_import_closure(entry, root)
        names = {p.name for p in closure}
        self.assertIn("_helper.py", names)
        self.assertIn("_spec.py", names)

    def test_comment_edit_keeps_closure_valid(self) -> None:
        from cadgen._internal.source_hash import closure_hash_matches

        root = self._dir("model2")
        entry = self._write_model(root)
        with scope_capture.scoped_recording(entry, root) as rec:
            pass
        closure = scope_capture.scope_closure(entry, rec)
        spec = root / "_spec.py"
        spec.write_text("# a comment\nSIZE = 5.0\n")
        self.assertTrue(closure_hash_matches(
            closure.closure_hash, closure.files, base=root))
        spec.write_text("SIZE = 6.0\n")
        self.assertFalse(closure_hash_matches(
            closure.closure_hash, closure.files, base=root))

    def test_data_reads_are_inputs(self) -> None:
        from cadgen._internal.source_hash import closure_hash_matches

        root = self._dir("model3")
        entry = self._write_model(root)
        data = root / "profile.json"
        data.write_text('{"teeth": 12}')
        with scope_capture.scoped_recording(entry, root) as rec:
            json.loads(data.read_text())
        closure = scope_capture.scope_closure(entry, rec)
        self.assertIn("profile.json", set(closure.files))
        data.write_text('{"teeth": 13}')
        self.assertFalse(closure_hash_matches(
            closure.closure_hash, closure.files, base=root))

    def test_child_reads_propagate_to_parent_scope(self) -> None:
        root = self._dir("model4")
        entry = self._write_model(root)
        data = root / "d.json"
        data.write_text("{}")
        with scope_capture.scoped_recording(entry, root) as outer:
            with scope_capture.scoped_recording(entry, root):
                scope_capture.note_scope_read(data)
        self.assertIn(data.resolve(), outer.reads)


class ComposeSeamTest(StoreIsolatedTest):
    """These tests stand in for a PARENT's body composing a child: outside a
    build, calling a decorated name would build it, so each test runs inside
    ``building()`` — the state a real parent's call site is always in."""

    def setUp(self) -> None:
        super().setUp()
        from cadgen.authoring import building

        active = building()
        active.__enter__()
        self.addCleanup(active.__exit__, None, None, None)

    def _write_model(self) -> Path:
        root = self._dir("modelc")
        (root / "_spec.py").write_text("SIZE = 5.0\n")
        (root / "_other.py").write_text("UNRELATED = 1\n")
        child = root / "child.py"
        child.write_text(textwrap.dedent("""\
            import _spec

            from cadgen import step
            @step
            def model():
                from build123d.topology import Solid
                box = Solid.make_box(_spec.SIZE, _spec.SIZE, _spec.SIZE)
                box.label = "child"
                return box


            if __name__ == "__main__":
                model()
            """))
        return child

    def _digest(self, shape) -> str:
        import io

        from OCP.BinTools import BinTools, BinTools_FormatVersion

        stream = io.BytesIO()
        BinTools.Write_s(shape.wrapped, stream, False, False,
                         BinTools_FormatVersion.BinTools_FormatVersion_CURRENT)
        return hashlib.sha256(stream.getvalue()).hexdigest()

    def _fresh_model(self, child: Path):
        """Import the child fresh and wrap its entry function with memo — the
        new-model composition pattern (`from part import gen_part;
        memo(gen_part)`), with the fresh import modeling what every real run
        does (workers evict and re-import edited first-party modules; memo's
        freshness contract is per RUN, like any import's)."""
        import importlib.util
        import shutil

        root = child.parent.resolve()
        # A same-size edit within one mtime second leaves a validly-stamped
        # stale .pyc; the runner purges pycache around scope re-execution, so
        # the fresh-import helper does too.
        for pycache in root.rglob("__pycache__"):
            shutil.rmtree(pycache, ignore_errors=True)
        for name, module in list(sys.modules.items()):
            file_name = getattr(module, "__file__", None)
            if file_name and Path(file_name).resolve().is_relative_to(root):
                sys.modules.pop(name, None)
        sys.path.insert(0, str(root))
        try:
            spec = importlib.util.spec_from_file_location(child.stem, child)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(root))
        return compose.memo(module.model)

    def test_miss_then_hit_and_canonical_return(self) -> None:
        child = self._write_model()
        first = self._fresh_model(child)()
        self.assertEqual(compose.stats()["misses"], 1)
        # A separate wrapper of a separately-imported module still HITS: the
        # scope key is the child's file + closure + args, never the function
        # object's identity.
        second = self._fresh_model(child)()
        self.assertEqual(compose.stats()["hits"], 1)
        self.assertEqual(self._digest(first), self._digest(second))
        self.assertEqual(second.label, "child")

    def test_closure_edit_misses_unrelated_edit_hits(self) -> None:
        child = self._write_model()
        self._fresh_model(child)()
        (child.parent / "_other.py").write_text("UNRELATED = 2\n")
        self._fresh_model(child)()
        self.assertEqual(compose.stats()["hits"], 1)
        (child.parent / "_spec.py").write_text("SIZE = 7.0\n")
        bigger = self._fresh_model(child)()
        self.assertEqual(compose.stats()["misses"], 2)
        self.assertAlmostEqual(bigger.volume, 343.0, places=6)

    def test_kill_switch(self) -> None:
        child = self._write_model()
        os.environ["CADGEN_SCOPE_CACHE"] = "0"
        try:
            self._fresh_model(child)()
            self._fresh_model(child)()
            self.assertEqual(compose.stats()["hits"], 0)
        finally:
            os.environ.pop("CADGEN_SCOPE_CACHE", None)

    def test_compose_exposes_only_the_function_seam(self) -> None:
        self.assertFalse(hasattr(compose, "child_entry"))

    def test_memo_function(self) -> None:
        calls = {"n": 0}

        @compose.memo
        def build_block(size: float):
            calls["n"] += 1
            block = Solid.make_box(size, size, size)
            block.label = "block"
            return block

        a = build_block(4.0)
        b = build_block(4.0)
        build_block(5.0)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(self._digest(a), self._digest(b))


if __name__ == "__main__":
    unittest.main()
