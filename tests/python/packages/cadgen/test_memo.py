"""Closed intermediate factories skip builders without skipping dependencies."""

from __future__ import annotations

import contextlib
import hashlib
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from cadgen import build123d as bd
from cadgen import memo
from cadgen import memoization
from cadgen.authoring import building
from cadgen.store.closure import ExecutionHashes

WIDTH = 30.0
OPTIONAL = None
_MODULE = bd


def _scaled_width(value):
    return value * WIDTH


@memo
def _plate(width=30.0, *, holes=3):
    with bd.BuildPart() as plate:
        bd.Box(width, 20, 6)
        for index in range(holes):
            with bd.Locations((-width / 2 + 5 + index * (width - 10) / (holes - 1), 0, 0)):
                bd.Cylinder(1.5, 10, mode=bd.Mode.SUBTRACT)
    return plate.part


@memo()
def _helper_plate(scale=1.0):
    return bd.Solid.make_box(_scaled_width(scale), 20, 6)


@memo
def _optional_plate():
    if OPTIONAL is None:
        return bd.Solid.make_box(2, 3, 4)
    return bd.Solid.make_box(OPTIONAL, 3, 4)


@memo
def _module_plate():
    return _MODULE.Box(2, 3, 4)


@memo
def _builder_effect():
    bd.Box(2, 3, 4)
    return bd.Solid.make_box(2, 3, 4)


@memo
def _mutable_input(values):
    values.append(3)
    return bd.Box(len(values), 2, 3)


@memo
def _read_file(path):
    from cadgen import declare_input
    return bd.Box(float(declare_input(path).read_text(encoding="utf-8")), 2, 3)


@memo
def _global_list():
    return bd.Box(_VALUES.pop(), 2, 3)


_VALUES = []


def _digest(shape):
    from cadgen._internal.op_memo import _write_brep
    return hashlib.sha256(_write_brep(shape.wrapped)).hexdigest()


class MemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen._internal import determinism, op_memo
        op_memo.install()
        determinism.install()
        memoization.install(trusted_worker=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cadgen-memo-")
        self.env = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": self.temp.name,
            "CADGEN_MEMO_CACHE": "1",
            "CADGEN_OP_MEMO": "1",
            "CADGEN_OP_MEMO_DISK": "1",
        })
        self.env.start()
        trust = mock.patch.object(memoization, "_reuse_trusted", True)
        trust.start()
        self.addCleanup(trust.stop)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.env.stop)
        for name in memoization._stats:
            memoization._stats[name] = 0

    @contextlib.contextmanager
    def _build(self, *paths):
        with ExecutionHashes() as hashes, building(Path(__file__), "test"):
            hashes.note(Path(__file__))
            for path in paths:
                hashes.note(Path(path))
            yield hashes

    def test_kernel_free_public_import(self):
        command = """
import importlib.util
import sys
import cadgen
from cadgen import memo
from cadgen import memo as again
from cadgen.daemon.client import FORWARDED_ENV_VARS
assert callable(memo) and memo is again and memo.__name__ == 'memo'
assert 'memo' in cadgen.__all__ and 'feature' not in cadgen.__all__
assert not hasattr(cadgen, 'feature')
assert importlib.util.find_spec('cadgen.features') is None
assert 'CADGEN_MEMO_CACHE' in FORWARDED_ENV_VARS
assert 'CADGEN_FEATURE_CACHE' not in FORWARDED_ENV_VARS
assert 'build123d' not in sys.modules and 'OCP' not in sys.modules
"""
        subprocess.run([sys.executable, "-c", command], check=True,
                       env={**os.environ, "PYTHONPATH": str(Path(memoization.__file__).parents[1])}, timeout=20)

    def test_cold_warm_disabled_and_fresh_process_recipe_are_identical(self):
        with self._build():
            first = _plate()
            warm = _plate(width=30.0, holes=3)
            with mock.patch.dict(os.environ, {"CADGEN_MEMO_CACHE": "0"}):
                disabled = _plate(30.0)
            memoization._code_cache.clear()
            memoization._code_bytes = 0
            disk = _plate()
        self.assertEqual(2, memoization._stats["hits"])
        self.assertEqual(2, memoization._stats["misses"])
        self.assertEqual({_digest(first)}, {_digest(warm), _digest(disabled), _digest(disk)})
        self.assertTrue(first.is_valid)

    def test_untrusted_embedding_runs_body_without_reusing_or_writing(self):
        with self._build():
            first = _plate()
            with mock.patch.object(memoization, "_reuse_trusted", False):
                self.assertFalse(memoization.install(trusted_worker=True))
                second = _plate()
                third = _plate()
                self.assertFalse(memoization._reuse_trusted)
        self.assertEqual(_digest(first), _digest(second))
        self.assertEqual(_digest(first), _digest(third))
        self.assertEqual(0, memoization._stats["hits"])
        self.assertEqual(3, memoization._stats["misses"])

    def test_initial_embedding_patch_is_not_a_reuse_witness(self):
        program = Path(self.temp.name) / "embedding.py"
        program.write_text("""\
from pathlib import Path
from cadgen import memoization, memo, build123d as bd
import build123d as real
from cadgen.authoring import building
from cadgen.store.closure import ExecutionHashes
from cadgen.store.index import iter_entries, read_entry
WIDTH = 2
def patched(*args):
    return real.Solid.make_box(WIDTH, 1, 1)
real.Box = patched
bd.Box = patched
memoization.install()
@memo
def geometry():
    return bd.Box(9, 1, 1)
with ExecutionHashes() as hashes, building(Path(__file__), 'embedding'):
    hashes.note(Path(__file__))
    first = geometry()
    WIDTH = 3
    assert not memoization.install(trusted_worker=True)
    second = geometry()
assert not memoization._reuse_trusted
assert memoization._stats['hits'] == 0
assert abs(first.volume - 2) < 1e-8
assert abs(second.volume - 3) < 1e-8
assert not any(read_entry('op', key).get('memoScheme') for key, _ in iter_entries('op'))
""", encoding="utf-8")
        completed = subprocess.run([sys.executable, str(program)], capture_output=True,
                                   text=True, timeout=20,
                                   env={**os.environ, "PYTHONPATH": str(Path(memoization.__file__).parents[1])})
        self.assertEqual(0, completed.returncode, completed.stderr[-3000:])

    def test_argument_and_keyword_default_changes_invalidate(self):
        with self._build():
            first = _plate()
            wide = _plate(40.0)
            more = _plate(30.0, holes=4)
            again = _plate(30.0, holes=3)
        self.assertEqual(3, memoization._stats["misses"])
        self.assertEqual(1, memoization._stats["hits"])
        self.assertEqual(_digest(first), _digest(again))
        self.assertNotEqual(_digest(first), _digest(wide))
        self.assertNotEqual(_digest(first), _digest(more))

    def test_changed_function_default_and_captured_module_hash_invalidate(self):
        original = _helper_plate.__wrapped__.__defaults__
        with self._build() as hashes:
            first = _helper_plate()
            try:
                _helper_plate.__wrapped__.__defaults__ = (2.0,)
                wider = _helper_plate()
            finally:
                _helper_plate.__wrapped__.__defaults__ = original
            hashes.hashes[str(Path(__file__).resolve())] = "ast1:changed"
            changed_source = _helper_plate()
        self.assertEqual(3, memoization._stats["misses"])
        self.assertAlmostEqual(first.volume * 2, wider.volume)
        self.assertEqual(_digest(first), _digest(changed_source))

    def test_global_helper_value_and_code_are_actual_inputs(self):
        with self._build():
            first = _helper_plate()
            with mock.patch.dict(globals(), {"WIDTH": 40.0}):
                changed_global = _helper_plate()
            original = _scaled_width.__code__
            replacement = compile("def helper(value):\n    return value * 45.0\n", __file__, "exec").co_consts[0]
            try:
                _scaled_width.__code__ = replacement
                changed_helper = _helper_plate()
            finally:
                _scaled_width.__code__ = original
            again = _helper_plate()
        self.assertEqual(3, memoization._stats["misses"])
        self.assertEqual(1, memoization._stats["hits"])
        self.assertAlmostEqual(3600, first.volume)
        self.assertAlmostEqual(4800, changed_global.volume)
        self.assertAlmostEqual(5400, changed_helper.volume)
        self.assertEqual(_digest(first), _digest(again))

    def test_result_mutation_cannot_escape_to_another_consumer(self):
        with self._build():
            first = _plate()
            original = _digest(first)
            first.label = "changed"
            first.color = bd.Color("red")
            first.wrapped.Reverse()
            second = _plate()
        self.assertEqual(original, _digest(second))
        self.assertNotEqual(first.label, second.label)
        self.assertNotEqual(first.color, second.color)
        self.assertFalse(first.wrapped.IsPartner(second.wrapped))

    def test_missing_or_corrupt_required_object_recomputes_and_repairs(self):
        from cadgen.store.index import iter_entries, read_entry
        from cadgen.store.objects import object_path, read_verified_object
        with self._build():
            first = _plate()
            entries = [read_entry("op", key) for key, _path in iter_entries("op")]
            entries = [entry for entry in entries if entry.get("memoScheme")]
            self.assertEqual(1, len(entries))
            digest = entries[0]["object"]
            object_path(digest).unlink()
            missing = _plate()
            object_path(digest).write_bytes(b"corrupt")
            repaired = _plate()
            read_verified_object(digest)
        self.assertEqual(0, memoization._stats["hits"])
        self.assertEqual(3, memoization._stats["misses"])
        self.assertEqual(_digest(first), _digest(missing))
        self.assertEqual(_digest(first), _digest(repaired))

    def test_mutable_inputs_globals_and_dynamic_io_execute_normally(self):
        from cadgen._internal.source_hash import record_discovered_inputs
        path = Path(self.temp.name) / "size.txt"
        path.write_text("4", encoding="utf-8")
        values = []
        with self._build(), record_discovered_inputs() as inputs:
            _mutable_input(values)
            _mutable_input(values)
            with mock.patch.dict(globals(), {"_VALUES": [6, 5]}):
                five = _global_list()
                six = _global_list()
            four = _read_file(str(path))
            path.write_text("7", encoding="utf-8")
            seven = _read_file(str(path))
        self.assertEqual([3, 3], values)
        self.assertAlmostEqual(30, five.volume)
        self.assertAlmostEqual(36, six.volume)
        self.assertAlmostEqual(24, four.volume)
        self.assertAlmostEqual(42, seven.volume)
        self.assertIn(path.resolve(), inputs)
        self.assertEqual(6, memoization._stats["declined"])

    def test_external_builders_and_locations_keep_their_side_effects(self):
        with self._build():
            _builder_effect()
            for _ in range(2):
                with bd.BuildPart() as parent:
                    _builder_effect()
                self.assertAlmostEqual(24, parent.part.volume)
                self.assertEqual(1, memoization._stats["misses"])
            with bd.BuildPart() as moved:
                with bd.Locations((50, 0, 0)):
                    _builder_effect()
            with bd.BuildSketch(bd.Plane.XY.offset(10)):
                with self.assertRaises(RuntimeError):
                    _builder_effect()
        self.assertGreaterEqual(memoization._stats["declined"], 4)
        self.assertAlmostEqual(50, moved.part.bounding_box().center().X)

    def test_replaced_export_or_protocol_is_never_blessed_by_reinstall(self):
        import build123d
        with self._build():
            first = _plate()
            original = build123d.Box
            def other_box(*args, **kwargs):
                return original(60, 20, 6)
            with mock.patch.object(bd, "Box", other_box):
                changed = _plate()
            with mock.patch.object(build123d.Shape, "__bool__", lambda self: True):
                self.assertFalse(memoization.install())
                _plate()
            again = _plate()
        self.assertNotEqual(_digest(first), _digest(changed))
        self.assertEqual(_digest(first), _digest(again))
        self.assertEqual(2, memoization._stats["declined"])
        self.assertEqual(1, memoization._stats["hits"])

    def test_missing_global_cannot_alias_a_cached_none(self):
        with self._build():
            _optional_plate()
            saved = globals().pop("OPTIONAL")
            try:
                with self.assertRaises(NameError):
                    _optional_plate()
            finally:
                globals()["OPTIONAL"] = saved

    def test_fake_proxy_module_keeps_ordinary_getattr_side_effect(self):
        calls = []
        fake = types.ModuleType("cadgen.build123d")
        def get_attr(name):
            calls.append(name)
            return getattr(bd, name)
        fake.__getattr__ = get_attr
        with self._build():
            _module_plate()
            with mock.patch.dict(globals(), {"_MODULE": fake}):
                first = _module_plate()
                second = _module_plate()
        self.assertEqual(["Box", "Box"], calls)
        self.assertEqual(_digest(first), _digest(second))
        self.assertEqual(2, memoization._stats["declined"])

    def test_nested_decorated_child_calls_are_not_skipped(self):
        from cadgen import step
        from cadgen import authoring
        @step
        def child():
            return bd.Box(2, 3, 4)
        @memo
        def parent():
            return child()
        with self._build(), mock.patch.object(authoring, "_compose_child", side_effect=lambda _defn: bd.Box(2, 3, 4)) as compose:
            parent()
            parent()
        self.assertEqual(2, compose.call_count)
        self.assertEqual(2, memoization._stats["declined"])

    def test_implicit_protocol_in_place_code_patch_declines(self):
        import build123d
        fn = build123d.Shape.__bool__
        original = fn.__code__
        replacement = compile("def truth(self):\n    return True\n", __file__, "exec").co_consts[0]
        with self._build():
            _plate()
            try:
                fn.__code__ = replacement
                _plate()
            finally:
                fn.__code__ = original
        self.assertEqual(1, memoization._stats["declined"])

    def test_primitive_subclass_keeps_its_constructor_attributes(self):
        # Existing op result recipes reconstruct Part/Solid wrappers. A Box
        # requires dimensional constructor arguments, so it remains ordinary.
        with self._build():
            first = _module_plate()
            second = _module_plate()
        self.assertIs(type(first), bd.Box)
        self.assertIs(type(second), bd.Box)
        self.assertEqual(2, second.length)
        self.assertEqual(2, memoization._stats["unstorable"])

    def test_identity_sensitive_arguments_and_nonfinite_values_do_not_alias(self):
        @memo
        def identity(first, second):
            return bd.Solid.make_box(1 if first is second else 2, 1, 1)
        @memo
        def comparison(first, second):
            return bd.Solid.make_box(1 if first == second else 2, 1, 1)
        left = tuple([1, 2])
        right = tuple([1, 2])
        nan = float("nan")
        with self._build():
            one = identity(left, left)
            two = identity(left, right)
            same_nan = comparison((nan,), (nan,))
            other_nan = comparison((nan,), (float("nan"),))
        self.assertAlmostEqual(1, one.volume)
        self.assertAlmostEqual(2, two.volume)
        self.assertAlmostEqual(1, same_nan.volume)
        self.assertAlmostEqual(2, other_nan.volume)
        self.assertEqual(4, memoization._stats["declined"])

    def test_replaced_bounding_box_intermediary_declines(self):
        from build123d import Solid
        from build123d.geometry import BoundBox, Vector
        # A helper defined via exec has no closure containing a class, so this
        # also exercises direct-import globals rather than a module alias.
        namespace = {"Solid": Solid}
        exec(compile("def measured():\n    width = Solid.make_box(2,3,4).bounding_box().center().X\n    return Solid.make_box(width,1,1)\n", __file__, "exec"), namespace)
        measured = memo(namespace["measured"])
        with self._build():
            first = measured()
            with mock.patch.object(BoundBox, "center", lambda self: Vector(7, 0, 0)):
                second = measured()
        self.assertAlmostEqual(1, first.volume)
        self.assertAlmostEqual(7, second.volume)
        self.assertEqual(1, memoization._stats["declined"])

    def test_mutable_native_default_is_compared_by_value(self):
        from OCP.gp import gp_Pnt
        axis = next(value for value, _key in memoization._trusted[-1] if type(value) is bd.Axis)
        before = axis.wrapped.Location()
        try:
            axis.wrapped.SetLocation(gp_Pnt(before.X() + 5, before.Y(), before.Z()))
            self.assertFalse(memoization._runtime_eligible())
        finally:
            axis.wrapped.SetLocation(before)
        self.assertTrue(memoization._runtime_eligible())

    def test_unsupported_result_attributes_preserve_original_values(self):
        # Attribute assignment is deliberately outside the certified subset.
        @memo
        def colored():
            result = bd.Box(2, 3, 4)
            result.label = "label"
            return result
        with self._build():
            self.assertEqual("label", colored().label)
            self.assertEqual("label", colored().label)
        self.assertEqual(2, memoization._stats["declined"])


if __name__ == "__main__":
    unittest.main()
