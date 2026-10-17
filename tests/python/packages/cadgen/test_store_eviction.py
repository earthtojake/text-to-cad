"""Disk management (STORE.md §8): the old operation cache retired, a size cap
with least-recently-written eviction, the three ways an earlier version of it
broke -- a hit that wrote, a reused object swept under a fresh record, and a
full pass rerun while records alone overfilled the cap -- a store a newer
cadgen shares, and the display data an older cadgen left: the surface, selector
and mesh entries before parts, and parts an older derivation wrote.
Tiny stores in fresh temporary directories; no kernel."""

from __future__ import annotations

import hashlib
import json
import os
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tree_ids import tokenized
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

HOUR = 3600.0
DAY = 24 * HOUR
WEEK = 7 * DAY


class StoreSweepCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = generated_cad_directory(prefix="store-evict-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "store"
        patch = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)})
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("CADGEN_STORE_MAX", None)

    # --- fixtures -------------------------------------------------------------

    def seed_document(self) -> tuple[str, str]:
        """A record, its document entry, its tree, a component and its part;
        returns (tree, the component's brep object)."""
        from cadgen.store.trees import get_tree
        from tests.python.support.store_fixtures import seed_result

        document = self.root / "part.step"
        document.write_bytes(b"fixture document")
        tree = seed_result(document)
        return tree, next(iter(get_tree(tree)["components"].values()))["brep"]

    def old(self, path: Path, age: float = 3 * HOUR) -> None:
        then = time.time() - age
        os.utime(path, (then, then))

    def old_object(self, payload: bytes, age: float = 3 * HOUR) -> str:
        from cadgen.store.objects import object_path, put_object

        digest = put_object(payload)
        self.old(object_path(digest), age)
        return digest

    def drawing_entry(self, key: str, payload: bytes, age: float) -> str:
        """A derived entry and the object only it names, last written ``age`` ago."""
        from cadgen.store.drawings import DRAWING_ENTRY_SCHEMA_VERSION
        from cadgen.store.index import entry_path, write_entry

        digest = self.old_object(payload, age)
        write_entry("drawing", key, {"schemaVersion": DRAWING_ENTRY_SCHEMA_VERSION, "object": digest})
        self.old(entry_path("drawing", key), age)
        return digest

    def raw_entry(self, kind: str, key: str, payload: dict, age: float = 3 * HOUR) -> Path:
        """A file under index/<kind>/, written as some other cadgen would."""
        folder = self.store / "index" / kind
        folder.mkdir(parents=True, exist_ok=True)
        (folder / key).write_text(json.dumps(payload), encoding="utf-8")
        self.old(folder / key, age)
        return folder / key

    def op_entry(self, key: str, payload: dict, age: float = WEEK + 3 * HOUR) -> None:
        """An entry of the operation cache cadgen 0.7.4 and earlier wrote, long ago."""
        self.raw_entry("op", key, payload, age)

    def snapshot(self) -> dict[str, tuple[int, int]]:
        found = {}
        for folder, _dirs, files in os.walk(self.store):
            for name in files:
                stat = os.stat(os.path.join(folder, name))
                found[os.path.relpath(os.path.join(folder, name), self.store)] = (stat.st_size, stat.st_mtime_ns)
        return found


class HitsNeverWrite(StoreSweepCase):
    """Bug 1: last-use stamps refreshed on a hit made every hit a write, and a
    store this user cannot write failed the build that hit it."""

    def test_every_cache_hit_is_a_pure_read(self) -> None:
        from cadgen.store import bounds, drawings, parts
        from cadgen.store.gate import stale
        from cadgen.store.records import tree_for_document_hash
        from cadgen.store.trees import capture_tree, get_tree
        from tests.python.support.store_fixtures import FIXTURE_PRODUCER

        tree, _brep = self.seed_document()
        part = parts.part_key(next(iter(get_tree(tree)["components"].values())), FIXTURE_PRODUCER)
        drawings.write("d" * 64, b"drawing payload")
        versions = ("0.11.1", "7.9.3.1", "7.9.3.1.1")
        with mock.patch.object(bounds, "kernel_versions", return_value=versions):
            bounds.cached_box("test-box", ("brep", 1), lambda: [0.0, 0.0, 0.0, 1.0, 2.0, 3.0])
        bounds.clear()
        before = self.snapshot()

        def never_measured():
            raise AssertionError("a hit measures nothing and writes nothing")

        with mock.patch.object(bounds, "kernel_versions", return_value=versions):
            self.assertEqual(bounds.cached_box("test-box", ("brep", 1), never_measured), [0.0, 0.0, 0.0, 1.0, 2.0, 3.0])
        self.assertFalse(stale(self.root / "part.step").stale)
        self.assertEqual(tree_for_document_hash(hashlib.sha256(b"fixture document").hexdigest()), tree)
        self.assertIsNotNone(capture_tree(tree, retain_payloads=False))
        self.assertIsNone(parts.request_display(tree, producer=FIXTURE_PRODUCER), "every part is stored: no job")
        self.assertIsNotNone(parts.probe(part))
        self.assertIsNotNone(parts.read(part, "glb"))
        self.assertIsNotNone(parts.read(part, "selectors"))
        self.assertEqual(drawings.read("d" * 64), b"drawing payload")
        self.assertEqual(self.snapshot(), before, "nothing under the store changed")


class ReusedObjectsSurvive(StoreSweepCase):
    """Bug 2: a write that found its bytes already present left their mtime
    alone, so the grace window never covered an object a just-published record
    reused, and a running sweep deleted it."""

    def test_an_object_reused_after_a_sweep_began_is_kept(self) -> None:
        from cadgen.store import gc
        from cadgen.store.objects import has_object, put_object

        reused = b"component bytes no record reaches at the sweep's mark"
        digest = self.old_object(reused)
        garbage = self.old_object(b"bytes nobody reuses")
        mark = gc.protected_objects

        def mark_then_publish(found, **kwargs):
            protected = mark(found, **kwargs)
            put_object(reused)  # a build publishes the same bytes while the sweep runs
            return protected

        with mock.patch.object(gc, "protected_objects", side_effect=mark_then_publish):
            report = gc.collect()
        self.assertTrue(has_object(digest))
        self.assertFalse(has_object(garbage))
        self.assertEqual(report.removed, 1)

    def test_a_claim_between_the_sweeps_check_and_its_delete_is_not_lost(self) -> None:
        from cadgen.store import objects
        from cadgen.store.objects import object_path, read_verified_object

        payload = b"claimed in the instant after the sweep checked it"
        digest = self.old_object(payload)
        path = object_path(digest)
        real_stat = type(path).stat
        checked = []

        def claimed_after_check(self_path, *args, **kwargs):
            result = real_stat(self_path, *args, **kwargs)
            if self_path == path and not checked:
                checked.append(result)
                os.utime(path)  # a publish claims it right after the sweep's check
            return result

        with mock.patch.object(type(path), "stat", claimed_after_check):
            self.assertEqual(objects.delete_unclaimed(path, time.time() - HOUR), 0)
        self.assertTrue(checked, "the sweep checked the object")
        self.assertEqual(read_verified_object(digest), payload)
        self.assertEqual([p.name for p in path.parent.iterdir()], [path.name], "no tombstone left")

    def test_a_publish_claims_a_pinned_childs_whole_closure(self) -> None:
        from cadgen.store import gc, trees
        from cadgen.store.index import iter_entries, remove_entry
        from cadgen.store.objects import has_object, object_path, read_verified_object
        from cadgen.store.trees import IDENTITY_16, get_tree, put_tree

        child, brep = self.seed_document()
        for kind in ("model", "document"):
            for key, _ in list(iter_entries(kind)):
                remove_entry(kind, key)  # the child moved on: nothing reaches its old tree
        parent = put_tree(tokenized({"label": "parent", "units": "mm", "entryKind": "assembly", "components": {},
                                     "occurrences": [], "links": [{"id": "o1.1", "name": "child", "tree": child, "transform": IDENTITY_16}],
                                     "assembly": {"root": {"id": "o1", "nodeType": "assembly",
                                                           "children": [{"id": "o1.1", "nodeType": "link", "children": []}]}}})[0])
        for digest in (parent, child, brep):
            self.old(object_path(digest))
        brep_bytes = read_verified_object(brep)
        claim = trees.claim_object

        def swept_after_verifying(digest):
            if digest == brep:
                object_path(brep).unlink()  # a sweep took it after the publish read it
            return claim(digest)

        mark = gc.protected_objects

        def mark_then_claim(found, **kwargs):
            protected = mark(found, **kwargs)
            with mock.patch.object(trees, "claim_object", side_effect=swept_after_verifying):
                self.assertTrue(trees.claim_tree(parent))
            return protected

        with mock.patch.object(gc, "protected_objects", side_effect=mark_then_claim):
            gc.collect()
        self.assertTrue(all(has_object(d) for d in (parent, child, brep)))
        self.assertEqual(read_verified_object(brep), brep_bytes)
        self.assertEqual(get_tree(parent)["links"][0]["tree"], child)


    def test_a_pass_that_died_holding_a_claimed_object_puts_it_back(self) -> None:
        from cadgen._internal.atomic_replace import temp_suffix
        from cadgen.store import gc
        from cadgen.store.objects import SWEPT, object_path

        held = {}
        for name, claimed in (("claimed", True), ("unclaimed", False)):
            payload = f"held when its pass died: {name}".encode()
            path = object_path(self.old_object(payload))
            held[name] = (path, path.with_name(f".{path.name}{SWEPT}{temp_suffix()}"), payload)
            os.replace(path, held[name][1])  # renamed out of reach; the recheck never ran
            if claimed:
                os.utime(held[name][1])  # a publish had claimed it just before the rename
        report = gc.collect(should_stop=lambda: True)
        self.assertTrue(report.stopped, "a pass asked to stop ends at its first step")
        self.assertTrue(held["claimed"][1].exists() and held["unclaimed"][1].exists(), "and touches nothing")

        gc.collect()
        path, _, payload = held["claimed"]
        self.assertEqual(path.read_bytes(), payload, "a claimed object goes back to its address")
        self.assertFalse(held["unclaimed"][0].exists() or held["unclaimed"][1].exists())
        self.assertEqual([p.name for p in self.store.joinpath("objects").rglob(f"*{SWEPT}*")], [])


class CapPasses(StoreSweepCase):
    """Bug 3: an idle daemon reran a full pass every few minutes while records
    and documents alone held more than the cap, though no pass could help."""

    def test_records_alone_over_the_cap_cost_one_pass_per_fifth_of_the_cap(self) -> None:
        from cadgen.daemon.housekeeping import Housekeeper
        from cadgen.store import gc

        tree, brep = self.seed_document()
        derived = self.drawing_entry("a" * 64, b"x" * 4000, age=5 * HOUR)
        newest = self.drawing_entry("b" * 64, b"n" * 200, age=2 * HOUR)
        found = gc.scan()
        cap = 2000  # below what the record and document alone keep
        self.assertGreater(sum(found.objects[d][0] for d in gc.protected_objects(found)), cap)
        housekeeper = Housekeeper(active=lambda: False, state_dir=lambda: self.root / "daemon")
        real_pass = Housekeeper._pass

        with mock.patch.object(Housekeeper, "_pass", autospec=True, side_effect=real_pass) as passes:
            housekeeper.look(str(self.store), cap)
            self.assertEqual(passes.call_count, 1)
            self.assertFalse((self.store / "objects" / derived[:2] / derived[2:]).exists(), "evicted")
            self.assertTrue((self.store / "objects" / brep[:2] / brep[2:]).exists(), "a record's geometry is never evicted")
            self.assertTrue((self.store / "objects" / newest[:2] / newest[2:]).exists(),
                            "the most recent derived entries keep a fifth of the cap")
            housekeeper.look(str(self.store), cap)
            Housekeeper(active=lambda: False, state_dir=lambda: self.root / "daemon").look(str(self.store), cap)
            self.assertEqual(passes.call_count, 1, "no pass while nothing a pass could free has grown, across daemons")

            self.drawing_entry("c" * 64, b"y" * (cap // 5 + 1000), age=1.5 * HOUR)
            housekeeper.look(str(self.store), cap)
            self.assertEqual(passes.call_count, 2, "a fifth of the cap of growth earns the next pass")


class Retirement(StoreSweepCase):
    def test_retiring_the_operation_cache_takes_only_what_it_alone_named(self) -> None:
        from cadgen.store import gc
        from cadgen.store.objects import has_object, put_object

        tree, brep = self.seed_document()
        only_op = self.old_object(b"an op-memo shape")
        reused = b"an op-memo shape a build publishes during the retirement"
        reused_digest = self.old_object(reused)
        fresh = put_object(b"an op-memo shape from the last hour")
        garbage = self.old_object(b"unreachable, but not the retired kinds' to take")
        recipe = {"op": "fillet", "args": ["x" * 64]}
        self.op_entry("1" * 64, {"object": only_op, "cls": "build123d.topology.Solid", "recipe": recipe})
        self.op_entry("2" * 64, {"object": brep, "cls": "build123d.topology.Solid", "recipe": recipe})
        self.op_entry("3" * 64, {"object": reused_digest, "cls": "build123d.topology.Solid", "recipe": recipe})
        self.op_entry("4" * 64, {"object": fresh, "cls": "build123d.topology.Solid", "recipe": recipe})
        self.op_entry("5" * 64, {"value": 42.0})
        mark = gc.protected_objects

        def mark_then_publish(found, **kwargs):
            protected = mark(found, **kwargs)
            put_object(reused)
            return protected

        with mock.patch.object(gc, "protected_objects", side_effect=mark_then_publish):
            gc.collect(retired_only=True)
        self.assertFalse(has_object(only_op))
        self.assertTrue(has_object(brep), "shared with a current tree")
        self.assertTrue(has_object(reused_digest), "claimed by a publish while retiring")
        self.assertTrue(has_object(fresh), "inside the grace window")
        self.assertTrue(has_object(garbage), "retiring sweeps only what the retired entries named")
        self.assertEqual(sorted(p.name for p in (self.store / "index" / "op").iterdir()),
                         sorted(["3" * 64, "4" * 64]), "entries naming objects the grace window kept wait for the next pass")

        for digest in (reused_digest, fresh):
            self.old(self.store / "objects" / digest[:2] / digest[2:])
        gc.collect(retired_only=True)
        self.assertFalse(has_object(fresh))
        self.assertFalse(has_object(reused_digest))
        self.assertFalse((self.store / "index" / "op").exists())
        self.assertTrue(has_object(garbage))
        gc.collect()
        self.assertFalse(has_object(garbage))
        self.assertTrue(has_object(tree) and has_object(brep))


    def test_the_daemon_retires_a_retired_kind_on_its_own_under_the_cap(self) -> None:
        from cadgen.daemon.housekeeping import Housekeeper
        from cadgen.store.objects import has_object

        tree, brep = self.seed_document()
        shapes = [self.old_object(f"op-memo shape {i}".encode()) for i in range(3)]
        for i, digest in enumerate(shapes):
            self.op_entry(f"{i:064x}", {"object": digest, "cls": "build123d.topology.Solid", "recipe": {}})
        housekeeper = Housekeeper(active=lambda: False, state_dir=lambda: self.root / "daemon")
        line = housekeeper.look(str(self.store), 20 * 1024**3)
        self.assertIn("retired index/op (3 entries)", line)
        self.assertFalse((self.store / "index" / "op").exists())
        self.assertFalse(any(has_object(d) for d in shapes))
        self.assertTrue(has_object(tree) and has_object(brep))
        self.assertIsNone(housekeeper.look(str(self.store), 20 * 1024**3), "nothing left to do")


class NewerCadgen(StoreSweepCase):
    """A store two cadgens share. The older one cannot read what the newer one
    still needs, so while the newer one writes, the older one removes nothing;
    and a folder under index/ it does not know, it never touches at all."""

    def store_with_garbage(self) -> tuple[str, str, str]:
        """A current document, an op entry and an unreachable object, all old:
        a pass that runs takes the op entry, its shape and the garbage."""
        tree, _brep = self.seed_document()
        garbage = self.old_object(b"nothing reaches me")
        shape = self.old_object(b"an op-memo shape")
        self.op_entry("1" * 64, {"object": shape, "cls": "build123d.topology.Solid", "recipe": {}})
        return tree, garbage, shape

    def test_while_a_newer_cadgen_writes_to_the_store_a_pass_removes_nothing(self) -> None:
        import shutil

        from cadgen.daemon.housekeeping import Housekeeper
        from cadgen.store import gc
        from cadgen.store.index import write_entry
        from cadgen.store.objects import put_object
        from cadgen.store.records import DOCUMENT_SCHEMA_VERSION, RECORD_SCHEMA_VERSION
        from cadgen.store.trees import TREE_KIND, TREE_SCHEMA

        newer_tree = json.dumps({"kind": TREE_KIND, "schemaVersion": TREE_SCHEMA + 1, "components": {}, "links": []})
        evidence = {
            "a record in a newer format": lambda: write_entry(
                "model", "a" * 64, {"schemaVersion": RECORD_SCHEMA_VERSION + 1, "tree": "b" * 64}),
            "a document entry in a newer format": lambda: write_entry(
                "document", "c" * 64, {"schemaVersion": DOCUMENT_SCHEMA_VERSION + 1, "tree": "d" * 64}),
            "a tree in a newer format": lambda: write_entry(
                "model", "e" * 64, {"schemaVersion": RECORD_SCHEMA_VERSION, "tree": put_object(newer_tree.encode())}),
            "an index folder it does not know": lambda: self.raw_entry("next", "f" * 64, {"schemaVersion": 1}, age=HOUR),
        }
        for what, write in evidence.items():
            with self.subTest(what):
                shutil.rmtree(self.store, ignore_errors=True)
                self.store_with_garbage()
                write()
                before = self.snapshot()
                report = gc.collect(max_bytes=1)
                self.assertIsNotNone(report.deferred)
                self.assertEqual(self.snapshot(), before, "the pass removed something")
        line = Housekeeper(active=lambda: False, state_dir=lambda: self.root / "daemon").look(str(self.store), 1)
        self.assertIn("left alone: a newer cadgen writes to this store", line)
        self.assertEqual(self.snapshot(), before)

    def test_a_newer_cadgen_gone_a_month_is_collected_and_a_folder_it_does_not_know_never_is(self) -> None:
        from cadgen.store import gc
        from cadgen.store.index import entry_path, write_entry
        from cadgen.store.objects import has_object
        from cadgen.store.records import RECORD_SCHEMA_VERSION

        tree, garbage, shape = self.store_with_garbage()
        month = gc.NEWER_CADGEN_SECONDS + HOUR
        write_entry("model", "a" * 64, {"schemaVersion": RECORD_SCHEMA_VERSION + 1, "tree": "b" * 64})
        self.old(entry_path("model", "a" * 64), month)
        foreign = [self.raw_entry("notes", "todo.txt", {"mine": True}, age=month)]
        for path in (self.store / "objects" / "zz" / ".draft.tmp", self.store / "objects" / "ab" / "README"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not cadgen's", encoding="utf-8")
            self.old(path, month)
            foreign.append(path)

        report = gc.collect(max_bytes=1)
        self.assertIsNone(report.deferred)
        self.assertFalse(has_object(garbage) or has_object(shape))
        self.assertFalse((self.store / "index" / "op").exists())
        self.assertTrue(has_object(tree))
        self.assertTrue(all(path.is_file() for path in foreign), "files that are not cadgen's are never touched")


class AnotherSchemaVersion(StoreSweepCase):
    """A record or document entry at a key this cadgen does not own is another
    cadgen version's: one sharing the store may still use it, and a read never
    writes, so a pass keeps it and what its tree reaches until it was last
    written a week ago, then retires it like an obsolete entry."""

    def test_another_versions_entries_keep_their_trees_for_a_week_then_go(self) -> None:
        from cadgen.store import gc
        from cadgen.store.index import model_key
        from cadgen.store.objects import has_object
        from cadgen.store.records import RECORD_SCHEMA_VERSION, document_key, record_key
        from cadgen.store.trees import get_tree
        from tests.python.support.store_fixtures import seed_result

        tree, brep = self.seed_document()
        other = self.root / "other.step"
        other.write_bytes(b"a document another cadgen compiled")
        other_tree = seed_result(other, components=("a", "b"))
        only_other = {other_tree} | {c["brep"] for c in get_tree(other_tree)["components"].values()} - {brep}
        # That cadgen stored no result of this one's by key: only its own entries name the tree.
        from cadgen.store.index import remove_entry
        from cadgen.store.results import results_of

        for key in results_of(other):
            remove_entry("result", key)
        # Its entries, as the other versions wrote them: cadgen 0.7.19's document
        # entry (schema 4, at the unversioned key), and an older record schema's record.
        index = self.store / "index"
        digest = hashlib.sha256(other.read_bytes()).hexdigest()
        theirs = []
        for ours_at, theirs_at, schema in (
                (index / "document" / document_key(digest), index / "document" / digest, 4),
                (index / "model" / record_key(other), index / "model" / f"{model_key(other)}-v{RECORD_SCHEMA_VERSION - 1}",
                 RECORD_SCHEMA_VERSION - 1)):
            theirs_at.write_text(json.dumps({**json.loads(ours_at.read_text(encoding="utf-8")), "schemaVersion": schema}),
                                 encoding="utf-8")
            ours_at.unlink()
            theirs.append(theirs_at)
        week = gc.OBSOLETE_RETIRE_AFTER_SECONDS
        for path in theirs:
            self.old(path, week - DAY)
        for shard in (self.store / "objects").iterdir():
            for path in shard.iterdir():
                self.old(path)
        garbage = self.old_object(b"nothing reaches me")
        ours = [index / "document" / document_key(hashlib.sha256(b"fixture document").hexdigest()),
                index / "model" / record_key(self.root / "part.step")]
        before = {path: path.read_bytes() for path in ours + theirs}

        report = gc.collect()
        self.assertFalse(has_object(garbage), "the pass swept")
        self.assertEqual(report.obsolete, {})
        self.assertTrue(all(has_object(digest) for digest in only_other), "a younger one's tree stays reachable")
        self.assertEqual({path: path.read_bytes() for path in ours + theirs}, before)

        for path in theirs:
            self.old(path, week + HOUR)
        self.assertEqual(gc.collect(retired_only=True).obsolete, {"document": 1, "model": 1},
                         "a week after its last write it goes, by the daemon's retiring pass too")
        self.assertFalse(any(path.exists() for path in theirs))
        gc.collect()
        self.assertFalse(any(has_object(digest) for digest in only_other), "and its tree with it")
        self.assertTrue(has_object(tree) and has_object(brep))
        self.assertEqual({path: path.read_bytes() for path in ours}, {path: before[path] for path in ours})

    def test_another_versions_tree_in_a_format_this_cadgen_cannot_read_is_kept_whole(self) -> None:
        from unittest import mock

        from cadgen.store import gc, trees
        from cadgen.store.objects import has_object
        from cadgen.store.records import document_key
        from tests.python.support.store_fixtures import seed_result

        other = self.root / "other.step"
        other.write_bytes(b"a document another cadgen compiled")
        other_tree = seed_result(other, components=("a", "b"))
        named = {other_tree} | {c["brep"] for c in trees.get_tree(other_tree)["components"].values()}
        index = self.store / "index"
        digest = hashlib.sha256(other.read_bytes()).hexdigest()
        ours_at = index / "document" / document_key(digest)
        (index / "document" / digest).write_text(
            json.dumps({**json.loads(ours_at.read_text(encoding="utf-8")), "schemaVersion": 4}), encoding="utf-8")
        ours_at.unlink()
        for shard in (self.store / "objects").iterdir():
            for path in shard.iterdir():
                self.old(path)
        real = trees.get_tree
        # Its tree as one in another tree format: this cadgen's reader cannot read it.
        with mock.patch.object(trees, "get_tree", lambda d: None if d == other_tree else real(d)):
            gc.collect()
        self.assertTrue(all(has_object(d) for d in named), "the young entry's tree and its parts stay")


class LeastRecentlyWritten(StoreSweepCase):
    def test_eviction_takes_the_oldest_derived_entries_and_never_a_record_or_document(self) -> None:
        from cadgen.store import gc
        from cadgen.store.index import iter_entries
        from cadgen.store.objects import has_object

        tree, brep = self.seed_document()
        ages = {"a": 5, "b": 4, "c": 3, "d": 2}
        objects = {name: self.drawing_entry(name * 64, name.encode() * 20000, age=hours * HOUR)
                   for name, hours in ages.items()}
        recent = self.drawing_entry("e" * 64, b"e" * 20000, age=600)
        found = gc.scan()
        weight = {name: found.entries["drawing"][name * 64][0] + found.objects[digest][0] for name, digest in objects.items()}
        after_two = found.total - weight["a"] - weight["b"]
        cap = int(after_two / gc.LOW_WATERMARK) + 1

        report = gc.collect(max_bytes=cap)
        self.assertEqual(report.evicted, {"drawing": 2})
        self.assertEqual({name for name, digest in objects.items() if not has_object(digest)}, {"a", "b"})

        report = gc.collect(max_bytes=1)
        self.assertEqual(report.evicted, {"drawing": 2})
        self.assertTrue(has_object(recent), "an entry written inside the grace window is leased")
        self.assertEqual(len(list(iter_entries("model"))), 1)
        self.assertEqual(len(list(iter_entries("document"))), 1)
        self.assertTrue(has_object(tree) and has_object(brep))

    def test_an_entry_written_again_after_the_scan_stays(self) -> None:
        from cadgen.store import gc
        from cadgen.store.index import entry_path
        from cadgen.store.objects import has_object, put_object

        payload = b"z" * 20000
        digest = self.drawing_entry("f" * 64, payload, age=5 * HOUR)
        real_scan = gc.scan

        def scan_then_rewrite():
            found = real_scan()
            put_object(payload)
            os.utime(entry_path("drawing", "f" * 64))  # a derivation writes it again
            return found

        with mock.patch.object(gc, "scan", side_effect=scan_then_rewrite):
            report = gc.collect(max_bytes=1)
        self.assertEqual(report.evicted, {})
        self.assertTrue(entry_path("drawing", "f" * 64).is_file())
        self.assertTrue(has_object(digest))




class RetiredDisplayData(StoreSweepCase):
    """A part's display data was three entries before ``index/part`` named its two objects in
    one: the surface, selector and mesh kinds are retired, and a pass removes them with the
    objects only they named. A part an older cadgen's derivation wrote (an older
    ``-v<PART_VERSION>``) no reader of this cadgen asks for again: a pass retires it once a
    week old, with the objects only it named, and keeps a newer cadgen's. An older cadgen
    still sharing the store may read it, and a read never writes, so a younger one stays."""

    def part_entry(self, version: int, digest: str, objects: tuple[str, str], age: float = 8 * DAY) -> str:
        key = f"{digest * 64}-v{version}"
        self.raw_entry("part", key, {"glb": {"object": objects[0]}, "selectors": {"object": objects[1]}}, age)
        return key

    def seed_versions(self) -> dict[str, str]:
        """The display kinds before parts, and an older and a newer cadgen's parts; returns
        the objects by what wrote them."""
        from cadgen.store.parts import PART_VERSION

        objects = {name: self.old_object(name.encode()) for name in (
            "surface", "selector table", "mesh", "older part's mesh", "older part's table",
            "newer part's mesh", "newer part's table")}
        for kind, name in (("surface", "surface"), ("selector", "selector table"), ("mesh", "mesh")):
            self.raw_entry(kind, "1" * 64, {"schemaVersion": 1, "object": objects[name]}, age=WEEK + HOUR)
        self.part_entry(PART_VERSION - 1, "1", (objects["older part's mesh"], objects["older part's table"]))
        self.part_entry(PART_VERSION + 1, "2", (objects["newer part's mesh"], objects["newer part's table"]))
        return objects

    def test_a_pass_retires_the_kinds_before_parts_and_an_older_cadgens_parts_and_keeps_the_rest(self) -> None:
        from cadgen.store import gc, parts
        from cadgen.store.index import iter_entries
        from cadgen.store.objects import has_object

        tree, brep = self.seed_document()
        [(current, _)] = iter_entries("part")
        objects = self.seed_versions()
        before = self.snapshot()
        dry = gc.collect(retired_only=True, dry_run=True)
        self.assertEqual((dry.retired, dry.obsolete), ({"surface": 1, "selector": 1, "mesh": 1}, {"part": 1}))
        self.assertEqual(self.snapshot(), before, "a dry run removes nothing")

        report = gc.collect(retired_only=True)
        self.assertEqual((report.retired, report.obsolete), ({"surface": 1, "selector": 1, "mesh": 1}, {"part": 1}))
        self.assertEqual({name for name, digest in objects.items() if not has_object(digest)},
                         {"surface", "selector table", "mesh", "older part's mesh", "older part's table"},
                         "a newer cadgen's part stays")
        self.assertFalse(any((self.store / "index" / kind).exists() for kind in ("surface", "selector", "mesh")))
        self.assertTrue(has_object(tree) and has_object(brep))
        self.assertIsNotNone(parts.probe(current), "this cadgen's part stays whole")
        again = gc.collect(retired_only=True)
        self.assertEqual((again.retired, again.obsolete), ({}, {}), "nothing is retired twice")

    def test_an_obsolete_part_goes_only_once_a_week_old(self) -> None:
        from cadgen.store import gc
        from cadgen.store.objects import has_object
        from cadgen.store.parts import PART_VERSION

        tree, brep = self.seed_document()
        week = gc.OBSOLETE_RETIRE_AFTER_SECONDS
        objects = {name: self.old_object(name.encode()) for name in (
            "old part's mesh", "old part's table", "young part's mesh", "young part's table")}
        old, young = week + HOUR, week - DAY
        self.part_entry(PART_VERSION - 1, "1", (objects["old part's mesh"], objects["old part's table"]), age=old)
        self.part_entry(PART_VERSION - 1, "2", (objects["young part's mesh"], objects["young part's table"]), age=young)

        # A full pass -- what `cadgen store gc` runs -- holds to the same week as the daemon's.
        report = gc.collect()
        self.assertEqual(report.obsolete, {"part": 1})
        self.assertEqual({name for name, digest in objects.items() if not has_object(digest)},
                         {"old part's mesh", "old part's table"}, "a younger obsolete part keeps its objects")
        self.assertTrue(has_object(tree) and has_object(brep))

        for path in (self.store / "index" / "part").iterdir():
            self.old(path, old)
        self.assertEqual(gc.collect(retired_only=True).obsolete, {"part": 1}, "a week later it goes")
        self.assertFalse(any(has_object(digest) for digest in objects.values()))
        self.assertTrue(has_object(tree) and has_object(brep))

    def test_a_retired_kind_goes_a_week_after_its_last_write(self) -> None:
        """The release before parts still reads index/surface, index/selector and
        index/mesh: a pass keeps what it wrote in the last week, with the objects
        it names, so a cadgen of that release sharing the store derives each again
        at most once a week; once a week old it goes like an obsolete part."""
        from cadgen.store import gc
        from cadgen.store.objects import has_object

        tree, brep = self.seed_document()
        kinds = ("surface", "selector", "mesh")
        young = {kind: self.old_object(f"young {kind}".encode()) for kind in kinds}
        aged = {kind: self.old_object(f"aged {kind}".encode(), age=WEEK + HOUR) for kind in kinds}
        for kind in kinds:
            self.raw_entry(kind, "1" * 64, {"schemaVersion": 1, "object": young[kind]}, age=3 * HOUR)
            self.raw_entry(kind, "2" * 64, {"schemaVersion": 1, "object": aged[kind]}, age=WEEK + HOUR)

        # A full pass -- what `cadgen store gc` runs -- holds to the same week as the daemon's.
        report = gc.collect()
        self.assertEqual(report.retired, {kind: 1 for kind in kinds})
        self.assertTrue(all(has_object(digest) for digest in young.values()), "a young entry keeps its objects")
        self.assertFalse(any(has_object(digest) for digest in aged.values()))
        self.assertTrue(all((self.store / "index" / kind / ("1" * 64)).is_file() for kind in kinds))
        self.assertTrue(has_object(tree) and has_object(brep))

        for kind in kinds:
            self.old(self.store / "index" / kind / ("1" * 64), WEEK + HOUR)
        self.assertEqual(gc.collect(retired_only=True).retired, {kind: 1 for kind in kinds}, "a week later it goes")
        self.assertFalse(any(has_object(digest) for digest in young.values()))
        self.assertFalse(any((self.store / "index" / kind).exists() for kind in kinds))
        self.assertTrue(has_object(tree) and has_object(brep))

    def test_under_a_cap_a_young_retired_entry_is_evicted_like_a_derived_one(self) -> None:
        from cadgen.store import gc
        from cadgen.store.objects import has_object

        tree, brep = self.seed_document()
        mesh = self.old_object(b"m" * 5000, age=5 * HOUR)
        self.raw_entry("mesh", "1" * 64, {"schemaVersion": 1, "object": mesh}, age=5 * HOUR)
        report = gc.collect(max_bytes=4000)
        self.assertEqual(report.evicted, {"mesh": 1})
        self.assertEqual(report.retired, {})
        self.assertFalse(has_object(mesh))
        self.assertFalse((self.store / "index" / "mesh" / ("1" * 64)).exists())
        self.assertTrue(has_object(tree) and has_object(brep))

    def test_an_obsolete_part_written_again_during_the_pass_stays(self) -> None:
        from cadgen.store import gc
        from cadgen.store.index import entry_path
        from cadgen.store.objects import has_object, put_object
        from cadgen.store.parts import PART_VERSION

        self.seed_document()
        payload = b"a part an older cadgen sharing the store still reads"
        digest = self.old_object(payload)
        key = self.part_entry(PART_VERSION - 1, "1", (digest, digest))
        retire = gc._retire

        def derived_again_then_retire(*args, **kwargs):
            # The older cadgen derives it again after the sweep: object first, then its entry.
            put_object(payload)
            os.utime(entry_path("part", key))
            return retire(*args, **kwargs)

        with mock.patch.object(gc, "_retire", side_effect=derived_again_then_retire):
            report = gc.collect(retired_only=True)
        self.assertEqual(report.obsolete, {})
        self.assertTrue(entry_path("part", key).is_file(), "an entry written since the scan stays")
        self.assertTrue(has_object(digest), "and the object it names is there")

    def test_a_store_holding_an_older_cadgens_parts_alone_earns_the_daemons_pass(self) -> None:
        from cadgen.daemon.housekeeping import Housekeeper
        from cadgen.store.objects import has_object
        from cadgen.store.parts import PART_VERSION

        objects = (self.old_object(b"an older part's mesh"), self.old_object(b"an older part's table"))
        self.part_entry(PART_VERSION - 1, "1", objects)
        line = Housekeeper(active=lambda: False, state_dir=lambda: self.root / "daemon").look(str(self.store), 20 * 1024**3)
        self.assertIn("retired obsolete part entries (1)", line or "")
        self.assertFalse(any(has_object(digest) for digest in objects))

    def test_the_daemon_retires_obsolete_entries_once_per_upgrade_then_daily(self) -> None:
        from cadgen.daemon.housekeeping import RETIRE_INTERVAL_SECONDS, Housekeeper
        from cadgen.store.objects import has_object

        self.seed_document()
        objects = self.seed_versions()
        state, cap, now = self.root / "daemon", 20 * 1024**3, [time.time()]

        def daemon() -> Housekeeper:
            return Housekeeper(active=lambda: False, state_dir=lambda: state, wall_clock=lambda: now[0])

        housekeeper = daemon()
        line = housekeeper.look(str(self.store), cap)
        self.assertIn("retired index/mesh (1 entries), index/selector (1 entries), index/surface (1 entries)", line)
        self.assertIn("retired obsolete part entries (1)", line)
        self.assertFalse(has_object(objects["older part's mesh"]))
        self.assertIsNone(housekeeper.look(str(self.store), cap), "not once per idle moment")
        self.assertIsNone(daemon().look(str(self.store), cap), "nor once per daemon start")
        with mock.patch("cadgen.store.gc.producer_versions", return_value={"part": [99]}):
            self.assertIsNotNone(housekeeper.look(str(self.store), cap), "an upgrade earns one more pass")
            self.assertIsNone(housekeeper.look(str(self.store), cap))
        # Two releases sharing the store keep a note each: neither moves the other's.
        self.assertIsNone(daemon().look(str(self.store), cap), "the first versions' note still stands")
        # Nor does an older cadgen, which writes the store's other note with no versions in it.
        housekeeper._note_path(str(self.store)).write_text(
            json.dumps({"root": str(self.store), "cap": cap, "after": 1, "at": now[0]}), encoding="utf-8")
        self.assertIsNone(daemon().look(str(self.store), cap), "an older cadgen's note re-arms nothing")
        # A day on, a pass looks again: it retires what the last kept for being younger than a week.
        now[0] += RETIRE_INTERVAL_SECONDS + 1
        self.assertIsNotNone(daemon().look(str(self.store), cap))
        self.assertIsNone(daemon().look(str(self.store), cap))

if __name__ == "__main__":
    unittest.main()
