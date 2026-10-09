"""Disk management (STORE.md §8): the old operation cache retired, a size cap
with least-recently-written eviction, the three ways an earlier version of it
broke -- a hit that wrote, a reused object swept under a fresh record, and a
full pass rerun while records alone overfilled the cap -- a store a newer
cadgen shares, and the surfaces and meshes an older extractor or mesher left.
Tiny stores in fresh temporary directories; no kernel."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

HOUR = 3600.0
DAY = 24 * HOUR


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
        """A record, its document entry, its tree, a component and its surface;
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

    def op_entry(self, key: str, payload: dict, age: float = 3 * HOUR) -> None:
        """An entry of the operation cache cadgen 0.7.4 and earlier wrote."""
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
        from cadgen.store import bounds, drawings, meshes, surfaces
        from cadgen.store.gate import stale
        from cadgen.store.records import tree_for_document_hash
        from cadgen.store.trees import capture_tree, get_tree
        from tests.python.support.store_fixtures import FIXTURE_SURFACE_PRODUCER
        from tests.python.support.tessellation import tessellation_fixture

        tree, _brep = self.seed_document()
        component = next(iter(get_tree(tree)["components"].values()))
        mesh = tessellation_fixture()
        meshes.write(mesh["key"], base64.b64decode(mesh["bytes"]))
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
        self.assertIsNotNone(surfaces.lookup(component, FIXTURE_SURFACE_PRODUCER))
        self.assertIsNotNone(meshes.probe(mesh["key"]))
        self.assertIsNotNone(meshes.read(mesh["key"]))
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
        for kind in ("model", "document", "surface"):
            for key, _ in list(iter_entries(kind)):
                remove_entry(kind, key)  # the child moved on: nothing reaches its old tree
        parent = put_tree({"label": "parent", "units": "mm", "entryKind": "assembly", "components": {},
                           "occurrences": [], "links": [{"id": "o1.1", "name": "child", "tree": child, "transform": IDENTITY_16}],
                           "assembly": {"root": {"id": "o1", "nodeType": "assembly",
                                                 "children": [{"id": "o1.1", "nodeType": "link", "children": []}]}}})
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




class Obsolete(StoreSweepCase):
    """An upgrade that moves the extractor or the mesher leaves the surfaces and
    meshes the older one wrote, which no reader of this cadgen asks for again: a
    pass retires them once a week old, with the objects only they named, and
    keeps a newer cadgen's. An older cadgen still sharing the store may read
    them, and a read never writes, so a younger one stays."""

    def surface_entry(self, key: str, producer: dict | None, digest: str, age: float = 8 * DAY) -> None:
        self.raw_entry("surface", key, {
            "schemaVersion": 1, "surfaceInput": key, "component": "c" * 64, "brep": "b" * 64,
            "codec": "bintools-v4", "faceColors": {}, "producer": producer, "object": digest}, age)

    def mesh_entry(self, surface_input: str, mesher: int, payload: int, digest: str, age: float = 8 * DAY) -> str:
        key = f"{surface_input}-t{mesher}-p{payload}-l{'0' * 16}-a{'0' * 16}"
        self.raw_entry("mesh", key, {"schemaVersion": 1, "object": digest}, age)
        return key

    def selector_entry(self, surface_input: str, scheme: int, digest: str, age: float = 8 * DAY) -> str:
        key = f"{surface_input}-s{scheme}"
        self.raw_entry("selector", key, {"schemaVersion": 1, "object": digest}, age)
        return key

    @staticmethod
    def older_producer() -> dict:
        from cadgen.store import surfaces

        return {"scheme": surfaces.EXTRACTION_SCHEME - 1, "surfFormat": surfaces.SURF_FORMAT - 1,
                "build123d": "0.11.1", "ocp": "7.9.3.1", "cadqueryOcp": "7.9.3.1.1"}

    def seed_versions(self) -> dict[str, str]:
        """Surfaces and meshes of this cadgen's versions, an older one's and a newer
        one's; returns the objects by what wrote them."""
        from cadgen.store import meshes, selectors, surfaces

        now = {"scheme": surfaces.EXTRACTION_SCHEME, "surfFormat": surfaces.SURF_FORMAT,
               "build123d": "0.11.1", "ocp": "7.9.3.1", "cadqueryOcp": "7.9.3.1.1"}
        mesher, payload = meshes.TESSELLATOR_VERSION, meshes.PAYLOAD_VERSION
        objects = {name: self.old_object(name.encode()) for name in (
            "older surface", "current surface", "newer surface", "pinned surface",
            "older mesher's mesh", "older surface's mesh", "current mesh", "newer mesher's mesh",
            "older scheme's table", "older surface's table", "current table", "newer scheme's table")}
        self.selector_entry("2" * 64, selectors.SELECTOR_SCHEME - 1, objects["older scheme's table"])
        self.selector_entry("1" * 64, selectors.SELECTOR_SCHEME, objects["older surface's table"])
        self.selector_entry("2" * 64, selectors.SELECTOR_SCHEME, objects["current table"])
        self.selector_entry("2" * 64, selectors.SELECTOR_SCHEME + 1, objects["newer scheme's table"])
        self.surface_entry("1" * 64, {**now, "scheme": now["scheme"] - 1, "surfFormat": now["surfFormat"] - 1},
                           objects["older surface"])
        self.surface_entry("2" * 64, now, objects["current surface"])
        self.surface_entry("3" * 64, {**now, "scheme": now["scheme"] + 1}, objects["newer surface"])
        # An eager-only component's surface names no producer: its key carries the SURF format.
        pinned = objects["pinned surface"]
        self.surface_entry(surfaces._pinned_surface_input(pinned, surfaces.SURF_FORMAT - 1), None, pinned)
        self.surface_entry(surfaces._pinned_surface_input(pinned, surfaces.SURF_FORMAT), None, pinned)
        self.mesh_entry("2" * 64, mesher - 1, payload - 1, objects["older mesher's mesh"])
        self.mesh_entry("1" * 64, mesher, payload, objects["older surface's mesh"])
        self.mesh_entry("2" * 64, mesher, payload, objects["current mesh"])
        self.mesh_entry("2" * 64, mesher + 1, payload, objects["newer mesher's mesh"])
        return objects

    def test_a_pass_retires_what_an_older_extractor_or_mesher_wrote_and_keeps_the_rest(self) -> None:
        from cadgen.store import gc
        from cadgen.store.objects import has_object

        tree, brep = self.seed_document()
        objects = self.seed_versions()
        before = self.snapshot()
        dry = gc.collect(retired_only=True, dry_run=True)
        self.assertEqual(dry.obsolete, {"surface": 2, "selector": 2, "mesh": 2})
        self.assertEqual(self.snapshot(), before, "a dry run removes nothing")

        report = gc.collect(retired_only=True)
        self.assertEqual(report.obsolete, {"surface": 2, "selector": 2, "mesh": 2})
        gone = {"older surface", "older mesher's mesh", "older surface's mesh",
                "older scheme's table", "older surface's table"}
        self.assertEqual({name for name, digest in objects.items() if not has_object(digest)}, gone,
                         "a pinned surface a current entry names stays, and so does a newer cadgen's work")
        self.assertTrue(has_object(tree) and has_object(brep))
        self.assertEqual(gc.collect(retired_only=True).obsolete, {}, "nothing is obsolete twice")

    def test_an_obsolete_entry_goes_only_once_a_week_old(self) -> None:
        from cadgen.store import gc, meshes, selectors
        from cadgen.store.objects import has_object

        tree, brep = self.seed_document()
        week = gc.OBSOLETE_RETIRE_AFTER_SECONDS
        mesher, payload = meshes.TESSELLATOR_VERSION, meshes.PAYLOAD_VERSION
        objects = {name: self.old_object(name.encode()) for name in (
            "old surface", "young surface", "young surface's old mesh",
            "old surface with a young mesh", "that young mesh", "old surface with a young table", "that young table")}
        old, young = week + HOUR, week - DAY
        self.surface_entry("1" * 64, self.older_producer(), objects["old surface"], age=old)
        self.surface_entry("2" * 64, self.older_producer(), objects["young surface"], age=young)
        self.mesh_entry("2" * 64, mesher - 1, payload - 1, objects["young surface's old mesh"], age=old)
        # This cadgen's mesher and format, keyed by an obsolete surface: known obsolete only by that surface.
        self.surface_entry("3" * 64, self.older_producer(), objects["old surface with a young mesh"], age=old)
        self.mesh_entry("3" * 64, mesher, payload, objects["that young mesh"], age=young)
        # And this cadgen's selector table scheme, keyed the same way.
        self.surface_entry("4" * 64, self.older_producer(), objects["old surface with a young table"], age=old)
        self.selector_entry("4" * 64, selectors.SELECTOR_SCHEME, objects["that young table"], age=young)

        # A full pass -- what `cadgen store gc` runs -- holds to the same week as the daemon's.
        report = gc.collect()
        self.assertEqual(report.obsolete, {"surface": 1, "mesh": 1})
        self.assertEqual({name for name, digest in objects.items() if not has_object(digest)},
                         {"old surface", "young surface's old mesh"},
                         "a younger obsolete entry keeps its objects, and an obsolete surface stays with its younger mesh or table")
        self.assertTrue(has_object(tree) and has_object(brep))

        for kind in ("surface", "selector", "mesh"):
            for path in (self.store / "index" / kind).iterdir():
                self.old(path, old)
        self.assertEqual(gc.collect(retired_only=True).obsolete, {"surface": 3, "selector": 1, "mesh": 1},
                         "a week later they go")
        self.assertFalse(any(has_object(digest) for digest in objects.values()))

    def test_an_obsolete_entry_written_again_during_the_pass_stays(self) -> None:
        from cadgen.store import gc
        from cadgen.store.index import entry_path
        from cadgen.store.objects import has_object, put_object

        self.seed_document()
        payload = b"a surface an older cadgen sharing the store still reads"
        digest = self.old_object(payload)
        self.surface_entry("1" * 64, self.older_producer(), digest)
        retire = gc._retire

        def derived_again_then_retire(*args, **kwargs):
            # The older cadgen derives it again after the sweep: object first, then its entry.
            put_object(payload)
            os.utime(entry_path("surface", "1" * 64))
            return retire(*args, **kwargs)

        with mock.patch.object(gc, "_retire", side_effect=derived_again_then_retire):
            report = gc.collect(retired_only=True)
        self.assertEqual(report.obsolete, {})
        self.assertTrue(entry_path("surface", "1" * 64).is_file(), "an entry written since the scan stays")
        self.assertTrue(has_object(digest), "and the object it names is there")

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
        self.assertIn("retired obsolete mesh entries (2), selector entries (2), surface entries (2)", line)
        self.assertFalse(has_object(objects["older surface"]))
        self.assertIsNone(housekeeper.look(str(self.store), cap), "not once per idle moment")
        self.assertIsNone(daemon().look(str(self.store), cap), "nor once per daemon start")
        moved = {"surface": [99, 9], "mesh": [99, 9]}
        with mock.patch("cadgen.store.gc.producer_versions", return_value=moved):
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
