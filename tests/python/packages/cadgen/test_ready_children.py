"""Ordered forcing, bounded private preparation, and execution-local ownership."""
from contextlib import nullcontext
import contextlib
import threading
import gc
import importlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest import mock
import weakref

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

import build123d as bd
from cadgen.authoring import building, current_frame
from cadgen.store.build import build_tree_from_compound
from cadgen.store.lazy import LazyCompound, ChildBuildError
from cadgen.store.objects import object_path, put_object
from cadgen.store.trees import get_tree
from cadgen.store import _ready_children as candidate

lazy_module = importlib.import_module('cadgen.store.lazy')


class Job:
    def __init__(self, tree, callback=None, ready=False, failure=None):
        self.tree, self.callback, self.failure = tree, callback, failure
        self.result_ready = ready
        self.calls = 0
    def wait_result(self):
        self.calls += 1
        if self.callback:
            self.callback()
        if self.failure:
            raise RuntimeError(self.failure)
        return self.tree


class ReadyChildren(unittest.TestCase):
    def setUp(self):
        self.temp = generated_cad_directory(prefix='ready-children-')
        self.addCleanup(self.temp.cleanup)
        self.env = mock.patch.dict(os.environ, {'CADGEN_CACHE_DIR': self.temp.name,
                                                'CADGEN_COMPONENT_WORKERS': '1', 'CADGEN_DAEMON': '0'})
        self.env.start()
        self.addCleanup(self.env.stop)
        # This suite exercises the ordinary-construction preparation fallback;
        # exact unexposed references have their own stronger, separate coverage.
        from cadgen.store import _references
        reference_patch = mock.patch.object(_references, "_ENABLED", False)
        reference_patch.start()
        self.addCleanup(reference_patch.stop)
        from cadgen.store.materialize import reset_memo
        reset_memo()
        self.addCleanup(reset_memo)
        self.tree = build_tree_from_compound(bd.Box(4, 3, 2), root_name='cube')[0]
        self.other = build_tree_from_compound(bd.Sphere(2), root_name='curved')[0]
        self.yielded = False
        class Yield:
            def __enter__(inner):
                self.yielded = True
            def __exit__(inner,*args):
                self.yielded = False
        patch = mock.patch('cadgen.daemon.broker.yielded', return_value=Yield())
        patch.start()
        self.addCleanup(patch.stop)
        self.yield_patch = patch
        self.execution = building(None)
        self.frame = self.execution.__enter__()
        self.addCleanup(self.leave_execution)
        self.stats = dict(scopes=0, attempts=0, prepared=0, consumed=0, failed=0,
                          discarded=0, revalidationFallbacks=0, maxPreparedCount=0,
                          maxPreparedBrepBytes=0, maxPreparedSurfBytes=0)
        self.constructions = []
        original_construction = candidate._Construction
        original_budget = candidate._budget
        original_snapshot = candidate._materialize_snapshot
        original_prepare = candidate.prepare_for
        original_take = candidate.take_prepared

        def construction(*args):
            value = original_construction(*args)
            self.constructions.append(value)
            self.stats['scopes'] += 1
            return value

        def budget(tree):
            self.stats['attempts'] += 1
            try:
                return original_budget(tree)
            except Exception:
                self.stats['failed'] += 1
                raise

        def snapshot(*args):
            value = original_snapshot(*args)
            self.stats['prepared'] += 1
            self.stats['discarded'] += 1
            return value

        def prepare(owner):
            original_prepare(owner)
            value = candidate._active_construction()
            if value is not None:
                for key, observed in (('maxPreparedCount', len(value.prepared)),
                                      ('maxPreparedBrepBytes', value.brep_bytes),
                                      ('maxPreparedSurfBytes', value.surf_bytes)):
                    self.stats[key] = max(self.stats[key], observed)

        def take(owner, tree, label):
            active = candidate._active_construction()
            had_prepared = active is not None and id(owner) in active.prepared
            value = original_take(owner, tree, label)
            if value is not None:
                self.stats['consumed'] += 1
                self.stats['discarded'] -= 1
            elif had_prepared:
                self.stats['revalidationFallbacks'] += 1
            return value

        for name, observer in (('_Construction', construction), ('_budget', budget),
                               ('_materialize_snapshot', snapshot), ('prepare_for', prepare),
                               ('take_prepared', take)):
            patch = mock.patch.object(candidate, name, side_effect=observer)
            patch.start()
            self.addCleanup(patch.stop)

    def leave_execution(self):
        if self.execution is not None:
            self.execution.__exit__(None, None, None)
            self.execution = None

    def child(self, name, *, tree=None, job=None):
        return LazyCompound(f'{self.temp.name}/{name}.py::{name}', job,
                            frame=self.frame, label=name, tree=tree)

    def test_ready_geometry_prepares_without_force_or_author_callbacks(self):
        events = []
        late = self.child('late', tree=self.tree)
        late = late.moved(bd.Location((3, 4, 5), (0, 0, 15)))
        class Label(str):
            def __bool__(self):
                events.append('authored-label')
                return True
        late.label = Label('late')
        original = candidate._materialize_snapshot
        prepared_refs = []
        def materialize(tree, label, snapshot):
            self.assertFalse(self.yielded, 'native preparation while job slot yielded')
            value = original(tree, label, snapshot)
            if label == 'late':
                events.append('private-geometry')
                prepared_refs.append(weakref.ref(value))
            return value
        def wait():
            events.append('wait-first')
            self.assertFalse(late._forced)
            self.assertEqual(events, ['private-geometry', 'wait-first'])
            self.assertEqual(self.stats['prepared'], 1)
        first = self.child('first', job=Job(self.other, wait))
        with mock.patch.object(candidate, '_materialize_snapshot', side_effect=materialize), nullcontext():
            result = bd.Compound(obj=[first, late], children=[first, late])
            self.assertEqual([child.label for child in result.children], ['first', 'late'])
            self.assertEqual(self.stats['consumed'], 1)
            self.assertIsNone(candidate._STATE.construction)
        self.assertEqual(events, ['private-geometry', 'wait-first', 'authored-label'])
        self.assertAlmostEqual(sum(s.volume for s in late.solids()), 24)
        gc.collect()
        self.assertTrue(all(ref() is None for ref in prepared_refs))

    def test_each_prepared_consumer_owns_native_geometry(self):
        left, right = self.child('left', tree=self.tree), self.child('right', tree=self.tree)
        first = self.child('first', job=Job(self.other))
        with nullcontext():
            bd.Compound(obj=[first, left, right], children=[first, left, right])
        self.assertEqual(self.stats['prepared'], 2)
        self.assertEqual(self.stats['consumed'], 2)
        self.assertFalse(left.wrapped.IsPartner(right.wrapped))
        left_shape, right_shape = left.solids()[0], right.solids()[0]
        self.assertFalse(left_shape.wrapped.IsPartner(right_shape.wrapped))
        from OCP.BRep import BRep_Builder
        from OCP.gp import gp_Pnt
        vertex = left_shape.vertices()[0]
        before = tuple(right_shape.vertices()[0].center())
        BRep_Builder().UpdateVertex(vertex.wrapped, gp_Pnt(123, 456, 789), 1e-7)
        self.assertEqual(tuple(right_shape.vertices()[0].center()), before)

    def test_later_job_result_does_not_change_first_pin_order(self):
        events = []
        a_job = Job(self.tree, lambda: events.append('first'))
        b_job = Job(self.other, lambda: events.append('second'), ready=True)
        first = self.child('same', job=a_job)
        later = self.child('same', job=b_job)
        with nullcontext():
            bd.Compound(obj=[first, later], children=[first, later])
        self.assertEqual(events, ['first', 'second'])
        self.assertEqual(self.stats['prepared'], 0)
        self.assertEqual(first.tree_hash(), later.tree_hash())
        self.assertAlmostEqual(sum(s.volume for s in later.solids()), 24)

    def test_first_failure_wins_and_unused_private_geometry_releases(self):
        late = self.child('late', tree=self.tree)
        first = self.child('first', job=Job(self.other, failure='first-job-error'))
        refs = []
        original = candidate._materialize_snapshot
        def observe(tree, label, snapshot):
            value = original(tree, label, snapshot)
            refs.append(weakref.ref(value))
            return value
        with mock.patch.object(candidate, '_materialize_snapshot', side_effect=observe), nullcontext():
            with self.assertRaisesRegex(ChildBuildError, 'first-job-error'):
                bd.Compound(obj=[first, late], children=[first, late])
            self.assertFalse(late._forced)
            self.assertIsNone(candidate._STATE.construction)
        gc.collect()
        self.assertTrue(refs and all(ref() is None for ref in refs))
        self.assertEqual(self.stats['discarded'], 1)

    def test_deleted_object_after_preparation_fails_on_exact_pin(self):
        late = self.child('late', tree=self.tree)
        surf = next(iter(get_tree(self.tree)['components'].values()))['brep']
        first = self.child('first', job=Job(self.other, lambda: object_path(surf).unlink()))
        with nullcontext(), mock.patch('cadgen.store.records.read_record', side_effect=AssertionError('latest record')):
            with self.assertRaisesRegex(ChildBuildError, 'disappeared'):
                bd.Compound(obj=[first, late], children=[first, late])
        self.assertEqual(self.stats['prepared'], 1)
        self.assertEqual(self.stats['consumed'], 0)

    def test_corruption_after_preparation_is_not_hidden_by_private_value(self):
        late = self.child('late', tree=self.tree)
        surf = next(iter(get_tree(self.tree)['components'].values()))['brep']
        first = self.child('first', job=Job(self.other, lambda: object_path(surf).write_bytes(b'corrupt')))
        with nullcontext():
            with self.assertRaisesRegex(ChildBuildError, 'disappeared'):
                bd.Compound(obj=[first, late], children=[first, late])
        self.assertEqual(self.stats['prepared'], 1)
        self.assertEqual(self.stats['consumed'], 0)

    def test_failed_preparation_can_retry_same_repaired_object_in_order(self):
        late = self.child('late', tree=self.tree)
        surf = next(iter(get_tree(self.tree)['components'].values()))['brep']
        payload = object_path(surf).read_bytes()
        object_path(surf).write_bytes(b'corrupt')
        first = self.child('first', job=Job(self.other, lambda: put_object(payload, repair=True)))
        with nullcontext():
            bd.Compound(obj=[first, late], children=[first, late])
        self.assertEqual(self.stats['failed'], 1)
        self.assertEqual(self.stats['consumed'], 0)
        self.assertAlmostEqual(sum(s.volume for s in late.solids()), 24)

    def test_byte_budget_skips_preparation_and_discarded_child(self):
        late, discarded = self.child('late', tree=self.tree), self.child('discarded', tree=self.tree)
        first = self.child('first', job=Job(self.other))
        with mock.patch.object(candidate, '_MAX_BREP_BYTES', 1), nullcontext():
            bd.Compound(obj=[first, late], children=[first, late])
        self.assertEqual(self.stats['prepared'], 0)
        self.assertFalse(discarded._forced)
        self.assertEqual(discarded._lazy_tree, self.tree)

    def test_generator_preserves_original_iteration_and_force_order(self):
        late = self.child('late', tree=self.tree)
        events = []
        first = self.child('first', job=Job(self.other, lambda: events.append('wait-first')))
        def items():
            events.append('yield-first')
            yield first
            self.assertTrue(first._forced)
            events.append('yield-late')
            yield late
        with nullcontext():
            bd.Compound(obj=items())
        self.assertEqual(events, ['yield-first', 'wait-first', 'yield-late'])
        self.assertEqual(self.stats['scopes'], 0)
        self.assertEqual(self.stats['prepared'], 0)


    def test_nested_constructor_cannot_expand_ancestor_preparation_budget(self):
        ready = [self.child(f'outer{i}', tree=self.tree) for i in range(8)]
        inner_ready = [self.child(f'inner{i}', tree=self.tree) for i in range(8)]
        nested = []
        def inner_wait():
            self.assertEqual(self.stats['prepared'], 8)
            self.assertIs(candidate._STATE.construction, self.constructions[0])
            self.assertEqual(len(candidate._STATE.construction.prepared), 8)
        inner_first = self.child('inner_first', job=Job(self.other, inner_wait))
        class Label(str):
            def __bool__(label):
                if not nested:
                    nested.append(bd.Compound(obj=[inner_first, *inner_ready], children=[inner_first, *inner_ready]))
                return True
        first = self.child('first', job=Job(self.other))
        first.label = Label('first')
        with nullcontext():
            bd.Compound(obj=[first, *ready], children=[first, *ready])
        self.assertEqual(self.stats['scopes'], 1)
        self.assertEqual(self.stats['prepared'], 8)
        self.assertEqual(self.stats['maxPreparedCount'], 8)
        self.assertTrue(all(child._forced for child in inner_ready))

    def test_reentrant_force_errors_before_any_preparation(self):
        first = self.child('first', job=Job(self.other))
        late = self.child('late', tree=self.tree)
        with nullcontext():
            scope = candidate._Construction((first, late), self.frame)
            candidate._STATE.construction = scope
            first._lazy_forcing = True
            try:
                with self.assertRaisesRegex(RuntimeError, 're-entrantly'):
                    first._force()
                self.assertEqual(self.stats['attempts'], 0)
                self.assertEqual(self.stats['prepared'], 0)
            finally:
                first._lazy_forcing = False
                self.assertIs(candidate._STATE.construction, scope)
                candidate._STATE.construction = None
        self.assertFalse(late._forced)

    def test_verified_tree_snapshot_survives_swap_then_repair(self):
        # T1=cube is valid when admission reads it. The object path then holds
        # T2=sphere during preparation and is repaired to T1 before consumption.
        # Rechecking T1 at consumption alone cannot catch wrong geometry built
        # from an intervening unverified read: the snapshot must be the input.
        late = self.child('late', tree=self.tree)
        root_path = object_path(self.tree)
        canonical = root_path.read_bytes()
        replacement = object_path(self.other).read_bytes()
        cube_entry = next(iter(get_tree(self.tree)['components'].values()))
        cube_brep = cube_entry['brep']
        bound = object_path(cube_brep).stat().st_size
        first = self.child('first', job=Job(self.tree, lambda: put_object(canonical, repair=True)))
        original_budget = candidate._budget
        original_snapshot = candidate._materialize_snapshot
        prepared_refs = []
        def admit_then_swap(tree):
            budget = original_budget(tree)
            root_path.write_bytes(replacement)
            return budget
        def capture(tree, label, snapshot):
            self.assertEqual({entry['brep'] for entry in snapshot['components'].values()}, {cube_brep})
            value = original_snapshot(tree, label, snapshot)
            prepared_refs.append(weakref.ref(value))
            self.assertAlmostEqual(sum(s.volume for s in value.solids()), 24)
            return value
        with mock.patch.object(candidate, '_budget', side_effect=admit_then_swap), \
             mock.patch.object(candidate, '_materialize_snapshot', side_effect=capture), \
             mock.patch.object(candidate, '_MAX_BREP_BYTES', bound), nullcontext():
            bd.Compound(obj=[first, late], children=[first, late])
        self.assertEqual(self.stats['prepared'], 1)
        self.assertEqual(self.stats['consumed'], 1)
        self.assertLessEqual(self.stats['maxPreparedBrepBytes'], bound)
        self.assertEqual(late.tree_hash(), self.tree)
        self.assertAlmostEqual(sum(s.volume for s in late.solids()), 24)
        gc.collect()
        self.assertTrue(all(ref() is None for ref in prepared_refs))



    def test_warm_brep_memo_cannot_bypass_actual_admission_size(self):
        materializer = importlib.import_module('cadgen.store.materialize')
        entry = next(iter(get_tree(self.tree)['components'].values()))
        brep = entry['brep']
        payload = materializer._bytes_for_object(brep)
        self.assertGreater(len(payload), 1)
        object_path(brep).write_bytes(b'x')
        late = self.child('late', tree=self.tree)
        first = self.child('first', job=Job(self.other, lambda: put_object(payload, repair=True)))
        with mock.patch.object(candidate, '_MAX_BREP_BYTES', len(payload)-1), nullcontext():
            bd.Compound(obj=[first, late], children=[first, late])
        self.assertEqual(self.stats['prepared'], 0)
        self.assertEqual(self.stats['maxPreparedBrepBytes'], 0)
        self.assertAlmostEqual(sum(s.volume for s in late.solids()), 24)

    def test_brep_repaired_after_short_stat_still_obeys_actual_size_limit(self):
        entry = next(iter(get_tree(self.tree)['components'].values()))
        surf = entry['brep']
        path = object_path(surf)
        payload = path.read_bytes()
        path.write_bytes(b'x')
        late = self.child('late', tree=self.tree)
        first = self.child('first', job=Job(self.other))
        original_stat = Path.stat
        armed = True
        def stat_then_repair(target, *args, **kwargs):
            nonlocal armed
            value = original_stat(target, *args, **kwargs)
            if target == path and armed:
                armed = False
                put_object(payload, repair=True)
            return value
        with mock.patch.object(Path, 'stat', stat_then_repair), \
             mock.patch.object(candidate, '_MAX_BREP_BYTES', len(payload)-1), nullcontext():
            bd.Compound(obj=[first, late], children=[first, late])
        self.assertFalse(armed)
        self.assertEqual(self.stats['prepared'], 0)
        self.assertEqual(self.stats['maxPreparedBrepBytes'], 0)
        self.assertAlmostEqual(sum(s.volume for s in late.solids()), 24)

    def test_install_is_permanent_idempotent_and_inactive_outside_execution(self):
        constructor = bd.Compound.__init__
        self.assertFalse(candidate.install())
        self.assertIs(bd.Compound.__init__, constructor)
        self.leave_execution()
        late = self.child('late', tree=self.tree)
        first = self.child('first', job=Job(self.other, lambda: self.assertFalse(late._forced)))
        bd.Compound(obj=[first, late], children=[first, late])
        self.assertEqual(self.stats['prepared'], 0)
        self.assertEqual(self.stats['scopes'], 0)
        self.assertIsNone(current_frame())
        self.assertIs(bd.Compound.__init__, constructor)

    def test_nested_build_frame_cannot_consume_or_expand_ancestor_preparation(self):
        late = self.child('late', tree=self.tree)
        observed = []

        def nested():
            outer = candidate._STATE.construction
            self.assertEqual(len(outer.prepared), 1)
            with building(None) as inner:
                self.assertIsNone(candidate._active_construction())
                self.assertIsNone(candidate.take_prepared(late, self.tree, 'late'))
                a = LazyCompound('nested-a.py', Job(self.other), frame=inner, label='a')
                b = LazyCompound('nested-b.py', None, frame=inner, label='b', tree=self.tree)
                bd.Compound(obj=[a, b])
                observed.append((a._forced, b._forced))
            self.assertIs(candidate._active_construction(), outer)
            self.assertEqual(len(outer.prepared), 1)

        first = self.child('first', job=Job(self.other, nested))
        bd.Compound(obj=[first, late])
        self.assertEqual(observed, [(True, True)])
        self.assertEqual(self.stats['prepared'], 1)
        self.assertEqual(self.stats['consumed'], 1)
        self.assertIsNone(candidate._STATE.construction)

    def test_children_preparation_preserves_attachment_and_metadata_order(self):
        late = self.child('late', tree=self.tree).moved(bd.Location((5, 6, 7), (11, 19, 23)))
        events = []

        class Label(str):
            def __bool__(label):
                events.append('late-label')
                return True

        late.label = Label('authored')

        def wait():
            events.append('first-wait')
            parent = first.parent
            self.assertIsNotNone(parent)
            self.assertEqual(parent.children, (first,))
            self.assertIsNone(late.parent)
            self.assertFalse(late._forced)
            self.assertEqual(self.stats['prepared'], 1)
            self.assertEqual(events, ['first-wait'])

        first = self.child('first', job=Job(self.other, wait))
        result = bd.Compound(children=(first, late), label='parent')
        self.assertEqual(result.children, (first, late))
        self.assertTrue(first.parent is result and late.parent is result)
        self.assertEqual(events, ['first-wait', 'late-label'])
        self.assertEqual(self.stats['consumed'], 1)
        self.assertAlmostEqual(late.bounding_box().center().X, 5., places=7)
        self.assertIsNone(candidate._STATE.construction)

    def test_children_duplicate_validation_remains_before_preparation(self):
        from anytree import TreeError

        first = self.child('first', job=Job(self.other))
        late = self.child('late', tree=self.tree)
        with self.assertRaises(TreeError):
            bd.Compound(children=[first, late, first])
        self.assertIsNone(first.parent)
        self.assertIsNone(late.parent)
        self.assertEqual(self.stats['prepared'], 0)
        self.assertEqual(self.stats['scopes'], 0)
        self.assertEqual(first._lazy_job.calls, 0)

    def test_children_reparenting_parent_argument_and_generators_use_ordinary_path(self):
        existing = bd.Compound(children=[bd.Box(1, 1, 1)], label='existing')
        already = self.child('already', tree=self.tree)
        already.parent = existing
        first = self.child('first', job=Job(self.other))
        moved = bd.Compound(children=[first, already])
        self.assertEqual(moved.children, (first, already))
        self.assertIs(already.parent, moved)
        self.assertEqual(self.stats['scopes'], 0)
        a = self.child('a', job=Job(self.other))
        b = self.child('b', tree=self.tree)
        # build123d attaches the new, still-empty root before initializing its
        # children; its existing assertion remains authoritative on this path.
        with self.assertRaises(AssertionError):
            bd.Compound(None, 'attached', None, '', None, existing, [a, b])
        self.assertFalse(a._forced or b._forced)
        self.assertEqual(self.stats['scopes'], 0)
        c = self.child('c', job=Job(self.other))
        d = self.child('d', tree=self.tree)
        generated = bd.Compound(children=(child for child in (c, d)))
        self.assertEqual(generated.children, (c, d))
        self.assertEqual(self.stats['prepared'], 0)
        self.assertEqual(self.stats['scopes'], 0)

    def test_children_failure_keeps_anytree_rollback_and_releases_preparation(self):
        def attempt(enabled):
            suffix = 'prepared' if enabled else 'ordinary'
            first = self.child(f'first_{suffix}', tree=self.tree)
            second = self.child(f'second_{suffix}', job=Job(self.other, failure='second-failed'))
            late = self.child(f'late_{suffix}', tree=self.tree)
            children = (first, second, late)
            for child, label in zip(children, ('first', 'second', 'late')):
                child.label = label
            with (nullcontext() if enabled else mock.patch.object(candidate, '_budget', return_value=None)):
                with self.assertRaises(ChildBuildError) as error:
                    bd.Compound(children=children)
            self.assertIsNone(candidate._STATE.construction)
            return (str(error.exception).split('):\n')[-1], second._lazy_job.calls,
                    [(child.label, child._forced, child.parent is None,
                      tuple(item.label for item in child.parent.children) if child.parent is not None else ())
                     for child in children])

        self.assertEqual(attempt(False), attempt(True))
        self.assertEqual(self.stats['prepared'], 1)
        self.assertEqual(self.stats['consumed'], 0)
        self.assertTrue(all(not value.prepared for value in self.constructions))

    def test_nested_children_constructor_cannot_expand_preparation(self):
        ready = self.child('outer_ready', tree=self.tree)
        inner_ready = self.child('inner_ready', tree=self.tree)
        inner_first = self.child('inner_first', job=Job(self.other))
        nested = []

        def wait():
            active = candidate._STATE.construction
            nested.append(bd.Compound(children=[inner_first, inner_ready]))
            self.assertIs(candidate._STATE.construction, active)
            self.assertEqual(self.stats['prepared'], 1)

        first = self.child('first', job=Job(self.other, wait))
        result = bd.Compound(children=[first, ready])
        self.assertEqual(self.stats['scopes'], 1)
        self.assertEqual(self.stats['consumed'], 1)
        self.assertTrue(first.parent is result and ready.parent is result)
        self.assertTrue(inner_first.parent is nested[0] and inner_ready.parent is nested[0])

    def test_one_slot_decorated_parent_with_a_current_sibling_completes(self):
        from cadgen.cli._run_model import run_model_argv

        self.leave_execution()
        self.yield_patch.stop()
        root = Path(self.temp.name)
        for name, shape in (('current', 'bd.Box(4, 3, 2)'), ('changed', 'bd.Cylinder(2, 5)')):
            (root / f'{name}.py').write_text(
                f'from cadgen import step, build123d as bd\n@step\ndef {name}():\n'
                f'    return {shape}\n', encoding='utf-8')
        (root / 'parent.py').write_text(
            'from cadgen import step, build123d as bd\n'
            'from changed import changed\nfrom current import current\n'
            '@step\ndef parent():\n'
            '    return bd.Compound(children=[changed(), current()])\n', encoding='utf-8')
        stats = root / 'slots.json'
        output = io.StringIO()
        with mock.patch.dict(os.environ, {'CADGEN_JOBS': '1', 'CADGEN_BROKER_STATS': str(stats)}), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(run_model_argv([str(root / 'current.py'), '--json']), 0, output.getvalue())
            current_bytes = (root / 'current.step').read_bytes()
            current_stamp = (root / 'current.step').stat().st_mtime_ns
            before = self.stats['consumed']
            self.assertEqual(run_model_argv([str(root / 'parent.py'), '--json']), 0, output.getvalue())
        self.assertEqual(self.stats['consumed'], before + 1)
        self.assertEqual((root / 'current.step').read_bytes(), current_bytes)
        self.assertEqual((root / 'current.step').stat().st_mtime_ns, current_stamp)
        self.assertTrue((root / 'changed.step').is_file())
        self.assertTrue((root / 'parent.step').is_file())
        self.assertEqual(json.loads(stats.read_text(encoding='utf-8'))['peakRunning'], 1)
        self.assertIsNone(current_frame())
        self.assertIsNone(candidate._STATE.construction)

    def test_constructor_failure_restores_context_for_next_construction(self):
        first = self.child('failed', job=Job(self.other, failure='failed-first'))
        late = self.child('unused', tree=self.tree)
        with self.assertRaisesRegex(ChildBuildError, 'failed-first'):
            bd.Compound(obj=[first, late])
        self.assertIsNone(candidate._STATE.construction)
        again = self.child('again', job=Job(self.other))
        bd.Compound(obj=[again, late])
        self.assertEqual(self.stats['prepared'], 2)
        self.assertEqual(self.stats['consumed'], 1)
        self.assertTrue(again._forced and late._forced)
        self.assertIsNone(candidate._STATE.construction)

    def test_concurrent_model_threads_keep_independent_contexts_and_native_owners(self):
        barrier = threading.Barrier(2)
        results, failures, active_ids = [], [], []
        constructor = bd.Compound.__init__

        def run(index):
            try:
                with building(None) as frame:
                    late = LazyCompound(f'thread-{index}-late.py', None, frame=frame,
                                        label='late', tree=self.tree)

                    def wait():
                        active = candidate._active_construction()
                        self.assertIs(active.frame, frame)
                        self.assertEqual(len(active.prepared), 1)
                        self.assertFalse(late._forced)
                        active_ids.append(id(active))
                        barrier.wait(timeout=10)
                        self.assertIs(candidate._active_construction(), active)

                    first = LazyCompound(f'thread-{index}-first.py', Job(self.other, wait),
                                         frame=frame, label='first')
                    bd.Compound(obj=[first, late])
                    results.append(late)
                    self.assertIsNone(candidate._STATE.construction)
                self.assertIsNone(current_frame())
            except BaseException as exc:
                failures.append(exc)
                barrier.abort()

        threads = [threading.Thread(target=run, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        if failures:
            raise failures[0]
        self.assertEqual(len(set(active_ids)), 2)
        self.assertEqual(len(results), 2)
        self.assertFalse(results[0].wrapped.IsPartner(results[1].wrapped))
        self.assertFalse(results[0].solids()[0].wrapped.IsPartner(results[1].solids()[0].wrapped))
        self.assertIs(current_frame(), self.frame)
        self.assertIsNone(getattr(candidate._STATE, 'construction', None))
        self.assertIs(bd.Compound.__init__, constructor)

    def test_prepared_cache_paths_preserve_bytes_appearance_and_private_ownership(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.gp import gp_Vec
        from cadgen._internal.op_memo import _write_brep
        from cadgen.step_export import export_build123d_step_file
        from cadgen.store.build import _tagged_intact
        from cadgen.store.materialize import _native_children, reset_memo

        curved = bd.Solid.make_cylinder(2, 5)
        curved.label, curved.color = 'curved', bd.Color('red')
        curved.cad_face_ordinal_colors = {1: (0., 1., 0., 1.)}
        moved = bd.Solid.make_box(1, 2, 3).mirror(bd.Plane.YZ).moved(
            bd.Location((7, -2, 3), (13, 19, 31)))
        moved.label, moved.color = 'mirrored', bd.Color('blue')
        nested = bd.Compound(children=[curved, moved], label='nested')
        source = bd.Compound(children=[nested], label='source')
        tree = build_tree_from_compound(source, root_name='source')[0]
        previous, consumers = None, []
        reset_memo()
        cases = (
            ('obj-cold-prepared', 'obj', True, False),
            ('obj-ram-prepared', 'obj', True, False),
            ('obj-disk-prepared', 'obj', True, True),
            ('obj-ram-ordinary', 'obj', False, False),
            ('children-ram-prepared', 'children', True, False),
        )
        for mode, constructor, prepared, reset_ram in cases:
            if reset_ram:
                reset_memo()
            with self.subTest(mode=mode):
                ready = self.child(f'{mode}_ready', tree=tree).moved(
                    bd.Location((3, 4, 5), (7, 11, 23)))
                # An identical authored label keeps serialized outputs comparable.
                ready.label = 'ready'
                first = self.child(f'{mode}_first', job=Job(self.other))
                count = self.stats['consumed']
                with (mock.patch.object(candidate, '_budget', return_value=None)
                      if not prepared else nullcontext()):
                    if constructor == 'children':
                        bd.Compound(children=[first, ready])
                    else:
                        bd.Compound(obj=[first, ready])
                self.assertEqual(self.stats['consumed'], count + prepared)
                self.assertEqual(_tagged_intact(ready), tree)
                prepared_brep = _write_brep(ready.wrapped)
                path = Path(self.temp.name) / f'{mode}.step'
                export_build123d_step_file(ready, path)
                authored = (prepared_brep, path.read_bytes(),
                            [(child.label, tuple(child.color) if child.color else None,
                              child.__dict__.get('cad_face_ordinal_colors'))
                             for child in ready.children[0].children])
                if previous is not None:
                    self.assertEqual(authored, previous)
                previous = authored
                consumers.append(ready)
        for index, left in enumerate(consumers):
            for right in consumers[index + 1:]:
                self.assertFalse(left.wrapped.IsPartner(right.wrapped))
                self.assertFalse(left.solids()[0].wrapped.IsPartner(right.solids()[0].wrapped))
        unchanged = [_write_brep(child.wrapped) for child in consumers[1:]]
        first = consumers[0]
        curve = next(curve for edge in first.edges()
                     if (curve := BRep_Tool.Curve_s(edge.wrapped, 0., 0.)) is not None)
        curve.Translate(gp_Vec(1, 2, 3))
        BRep_Tool.Surface_s(first.faces()[0].wrapped).Translate(gp_Vec(2, 3, 4))
        first.wrapped.Free(True)
        BRep_Builder().Remove(first.wrapped, _native_children(first.wrapped)[0])
        first.children[0].children[0].cad_face_ordinal_colors[1] = (0., 0., 0., 1.)
        self.assertIsNone(_tagged_intact(first))
        self.assertEqual([_write_brep(child.wrapped) for child in consumers[1:]], unchanged)
        self.assertTrue(all(
            child.children[0].children[0].cad_face_ordinal_colors[1] == (0., 1., 0., 1.)
            for child in consumers[1:]
        ))


if __name__ == '__main__':
    unittest.main()
