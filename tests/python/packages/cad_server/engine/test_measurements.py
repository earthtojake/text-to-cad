"""The manufacturing checks' measurements as the daemon keeps them (``measurements.Measurements``): an alias
from a version of a document to the content record it holds, a result by that record's key and its
measurement's, each in memory and on disk, bounded, served to whom it may be, removed where it does not read,
and a document's own going with it. No engine and no kernel: the store alone, on folders of the test's own."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

from tests.python.support.manufacturing_fixtures import record

BY = {"code": "c0de", "libraries": {"OCP": "8.0.1"}}


class MeasurementsTest(unittest.TestCase):
    def folder(self) -> Any:
        from cad_server.engine.registry import Folder

        folder = Folder(tempfile.mkdtemp(prefix="engine-dfm-kept-"))
        self.addCleanup(shutil.rmtree, folder.root, True)
        return folder

    def test_an_alias_says_what_a_version_holds_to_whom_its_describer_describes_for(self) -> None:
        """A model's by its id and revision, a file's by its bytes and its name wherever it lies; found again by
        a fresh store on the same folder; one of a build with no durable revision in memory alone; and one
        described by other code is none, replaced by the next."""
        from cad_server.engine.measurements import Measurements, build_token, file_token, model_token

        folder = self.folder()
        store = Measurements(lambda: folder)
        ident, plate = str(uuid.uuid4()), record()
        store.name(model_token(ident, "r1"), plate, BY)
        store.name(build_token(ident, "g7"), record(geometry="g2"), BY)
        here, there = Path(folder.root) / "a" / "part.step", Path(folder.root) / "b" / "part.step"
        self.assertEqual(file_token("d1", here), file_token("d1", there), "the same bytes under the same name")
        self.assertNotEqual(file_token("d1", here), file_token("d1", here.with_name("other.step")))
        self.assertNotEqual(file_token("d1", here), file_token("d1", here.with_suffix(".xbf")))
        store.name(file_token("d1", here), plate, BY)
        for held in (store, Measurements(lambda: folder)):
            with self.subTest(restarted=held is not store):
                self.assertEqual(held.content(model_token(ident, "r1")), plate)
                self.assertEqual(held.content(file_token("d1", there)), plate)
                self.assertIsNone(held.content(model_token(ident, "r2")))
                self.assertIsNone(held.content(file_token("d2", here)))
        self.assertEqual(store.content(build_token(ident, "g7"))["parts"][0]["key"], "g2")
        self.assertIsNone(Measurements(lambda: folder).content(build_token(ident, "g7")), "never written")
        self.assertEqual(len(folder.names(f"checks/models/{ident}")), 1)

        other = {**BY, "code": "other"}
        self.assertIsNone(store.content(model_token(ident, "r1"), lambda by: by == other))
        store.name(model_token(ident, "r1"), plate, other)
        self.assertEqual(Measurements(lambda: folder).content(model_token(ident, "r1"), lambda by: by == other), plate)
        self.assertEqual(len(folder.names(f"checks/models/{ident}")), 1, "in the old one's place")
        store.forget(model_token(ident, "r1"))
        store.forget(file_token("d1", here))
        self.assertEqual((store.content(model_token(ident, "r1")), store.content(file_token("d1", here))), (None, None))
        self.assertIsNone(Measurements().content(model_token(ident, "r1")), "no cache folder: memory alone")

    def test_a_result_is_one_measurement_of_one_record_served_to_whom_it_stands_for(self) -> None:
        from cad_server.engine.measurements import Measurements

        folder = self.folder()
        store = Measurements(lambda: folder)
        key, other = record()["key"], record(geometry="g2")["key"]
        store.keep(key, "cnc", {"report": {"x": 1}}, BY)
        store.keep(key, "sheet", {"report": {"x": 2}}, BY)
        self.assertEqual((store.get(key, "cnc"), store.get(other, "cnc")), ({"report": {"x": 1}}, None))
        self.assertEqual(len(folder.names(f"checks/results/{key[:2]}")), 2)
        restarted = Measurements(lambda: folder)
        self.assertEqual(restarted.get(key, "sheet"), {"report": {"x": 2}})
        self.assertEqual((restarted.status()["reused"], restarted.status()["restored"]), (1, 1))
        self.assertEqual(restarted.get(key, "sheet"), {"report": {"x": 2}}, "from memory then")
        self.assertEqual((restarted.status()["reused"], restarted.status()["restored"]), (2, 1))
        self.assertIsNone(restarted.get(key, "cnc", lambda by: by != BY), "measured by what stands for no such caller")
        restarted.keep(key, "cnc", {"report": {"x": 3}}, {**BY, "code": "newer"})
        self.assertEqual(Measurements(lambda: folder).get(key, "cnc", lambda by: by != BY), {"report": {"x": 3}})
        with self.assertRaises(ValueError):
            store.keep("../outside", "cnc", {"report": {}}, BY)

    def test_each_is_held_to_its_bounds_the_least_recently_used_going_first(self) -> None:
        from cad_server.engine.measurements import Measurements, file_token, model_token

        folder = self.folder()
        keys = [record(geometry=f"g{index}")["key"] for index in range(3)]
        # In memory, and on disk by a store that holds nothing in memory: each read makes its entry the latest.
        for store in (Measurements(results=2), Measurements(lambda: folder, results=0, disk_results=2)):
            with self.subTest(disk=store.folder is not None):
                for key in keys[:2]:
                    store.keep(key, "cnc", {"report": {"of": key}}, BY)
                self.assertIsNotNone(store.get(keys[0], "cnc"))
                store.keep(keys[2], "cnc", {"report": {"of": keys[2]}}, BY)
                self.assertEqual([store.get(key, "cnc") is not None for key in keys], [True, False, True])
        self.assertEqual((store.status()["held"], store.status()["disk"]),
                         (0, {"held": 2, "bytes": mock.ANY, "aliases": None}))
        self.assertEqual(sorted(folder.names("checks/results")), sorted({keys[0][:2], keys[2][:2]}),
                         "a folder left empty went with its last entry")
        small = Measurements(lambda: folder, budget=32, disk_budget=32)
        small.keep(keys[1], "sheet", {"report": {"big": "x" * 64}}, BY)
        self.assertEqual((small.status()["held"], small.get(keys[1], "sheet")), (0, None), "over the budget alone")

        store = Measurements(lambda: folder, aliases=2, file_aliases=2, revisions=2)
        ident = str(uuid.uuid4())
        for revision in ("r1", "r2", "r3"):
            store.name(model_token(ident, revision), record(geometry=revision), BY)
        fresh = Measurements(lambda: folder)
        self.assertEqual([fresh.content(model_token(ident, revision)) is not None for revision in ("r1", "r2", "r3")],
                         [False, True, True], "a model keeps its latest revisions")
        self.assertEqual(store.status()["aliases"], 2)
        path = Path(folder.root) / "part.step"
        for digest in ("d1", "d2", "d3"):
            store.name(file_token(digest, path), record(geometry=digest), BY)
        self.assertEqual(store.status()["disk"]["aliases"], 4, "two of the model's, two of the files'")
        self.assertIsNone(Measurements(lambda: folder).content(file_token("d1", path)))

        # The models' aliases together are bounded too, a model checked long ago going first, its folder with it;
        # and what a stopped engine left half written in a model's folder is swept as the models' are listed.
        models = [str(uuid.uuid4()) for _ in range(3)]
        folder.path(f"checks/models/{models[0]}").mkdir(parents=True)
        folder.path(f"checks/models/{models[0]}/x.json.1.ab.tmp").write_bytes(b"{")
        store = Measurements(lambda: folder, model_aliases=3)
        for model in models[:2]:
            store.name(model_token(model, "r1"), record(geometry=model), BY)
        self.assertEqual([name.endswith(".json") for name in folder.names(f"checks/models/{models[0]}")], [True],
                         "the half-written file went")
        self.assertEqual(store.status()["disk"]["aliases"], 3, "one of the model above went for the third")
        for model, ago in ((ident, 30.0), (models[0], 20.0), (models[1], 10.0)):  # each by its time on disk
            for name in folder.names(f"checks/models/{model}"):
                at = folder.path(f"checks/models/{model}/{name}").stat().st_mtime - ago
                os.utime(folder.path(f"checks/models/{model}/{name}"), (at, at))
        fresh = Measurements(lambda: folder, model_aliases=3)
        self.assertIsNotNone(fresh.content(model_token(models[0], "r1")))  # read: the most recently used
        fresh.name(model_token(models[2], "r1"), record(geometry=models[2]), BY)
        self.assertEqual(sorted(folder.names("checks/models")), sorted(models),
                         "the model above, least recently used, went, its folder with its last alias")
        self.assertEqual(fresh.status()["disk"]["aliases"], 3)

    def test_an_entry_that_does_not_read_as_what_its_name_says_is_removed_never_served(self) -> None:
        from cad_server.engine.measurements import Measurements, model_token

        folder = self.folder()
        store = Measurements(lambda: folder)
        plate, ident = record(), str(uuid.uuid4())
        key = plate["key"]
        tampered = {**plate, "name": "another"}  # a record changed since it was keyed
        whole = {"format": 1, "content": key, "measure": "cnc", "by": {}, "result": {"report": {}}}
        for said, wrong in (("not JSON", b"{not json"), ("another format", json.dumps({**whole, "format": 0})),
                            ("another measurement's", json.dumps({**whole, "measure": "sheet"})),
                            ("no report", json.dumps({**whole, "result": {}}))):
            with self.subTest(result=said):
                store.keep(key, "cnc", {"report": {"x": 1}}, BY)
                (name,) = folder.names(f"checks/results/{key[:2]}")
                folder.write(f"checks/results/{key[:2]}/{name}", wrong if isinstance(wrong, bytes) else wrong.encode())
                self.assertIsNone(Measurements(lambda: folder).get(key, "cnc"))
                self.assertEqual(folder.names("checks/results"), [], "removed, with its folder")
        whole = {"format": 1, "token": ["model", ident, "r1"], "content": plate, "by": {}}
        for said, wrong in (("another token's", {**whole, "token": ["model", ident, "r9"]}),
                            ("a record that is not its key's", {**whole, "content": tampered}),
                            ("no parts", {**whole, "content": {"key": key}})):
            with self.subTest(alias=said):
                store.name(model_token(ident, "r1"), plate, BY)
                (name,) = folder.names(f"checks/models/{ident}")
                folder.write(f"checks/models/{ident}/{name}", json.dumps(wrong).encode())
                self.assertIsNone(Measurements(lambda: folder).content(model_token(ident, "r1")))
                self.assertEqual(folder.names(f"checks/models/{ident}"), [])

    def test_a_folder_that_takes_no_write_keeps_nothing_and_what_a_stopped_engine_left_is_swept(self) -> None:
        from cad_server.engine.measurements import Measurements, file_token
        from cad_server.engine.registry import Folder

        sealed = {"on": True}

        class Sealed(Folder):
            def write(self, inside: str, data: bytes, mode: int | None = None) -> Path:
                if sealed["on"]:
                    raise PermissionError(inside)
                return super().write(inside, data, mode)

        folder = Sealed(tempfile.mkdtemp(prefix="engine-dfm-sealed-"))
        self.addCleanup(shutil.rmtree, folder.root, True)
        plate = record()
        token = file_token("d1", Path(folder.root) / "part.step")
        for inside in (f"checks/results/{plate['key'][:2]}", "checks/files/ab"):
            folder.path(inside).mkdir(parents=True)
            folder.path(f"{inside}/x.json.1.ab.tmp").write_bytes(b"{")
        store = Measurements(lambda: folder)
        store.keep(plate["key"], "cnc", {"report": {}}, BY)
        store.name(token, plate, BY)
        self.assertEqual((store.get(plate["key"], "cnc"), store.content(token)), ({"report": {}}, plate), "in memory")
        fresh = Measurements(lambda: folder)
        self.assertEqual((fresh.get(plate["key"], "cnc"), fresh.content(token)), (None, None), "no write taken")
        self.assertEqual(store.status()["disk"], {"held": 0, "bytes": 0, "aliases": 0})
        self.assertEqual([name for _folder, _folders, names in os.walk(folder.root) for name in names], [],
                         "the half-written files swept as each was listed")
        sealed["on"] = False
        store.keep(plate["key"], "cnc", {"report": {}}, BY)
        store.name(token, plate, BY)
        fresh = Measurements(lambda: folder)
        self.assertEqual((fresh.get(plate["key"], "cnc"), fresh.content(token)), ({"report": {}}, plate),
                         "kept as soon as it takes one")
        shutil.rmtree(folder.path("checks"))  # a person wiping the cache folder
        self.assertEqual((Measurements(lambda: folder).get(plate["key"], "cnc"), store.status()["disk"]["held"]),
                         (None, 1))
        store.results.drop((plate["key"], "cnc"))
        self.assertIsNone(store.get(plate["key"], "cnc"))
        self.assertEqual(store.status()["disk"]["held"], 0, "gone with its folder: out of the list as it is asked for")

    def test_a_deleted_document_takes_its_own_aliases_and_no_measurement(self) -> None:
        """Deleting a document removes the aliases of its versions with its folders, whether an engine runs or
        not -- the registry removes them itself (``Registry.delete``), as ``cad delete`` does with no server to
        ask -- so a model built again under the id, which may hold other parts at a revision it had, is read
        again. An engine that runs drops what it holds of them in memory, and a check of the document that
        began before names none. The results, which are no document's, stay."""
        from cad_server.engine import registry
        from cad_server.engine.measurements import Measurements, build_token, model_token
        from cad_server.engine.models import delete
        from cad_server.engine.registry import Registry

        root = Path(tempfile.mkdtemp(prefix="engine-dfm-deleted-"))
        self.addCleanup(shutil.rmtree, root, True)
        held = Registry(root / "state", cache=root / "cache")
        a, b, c, plate = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()), record()
        store = Measurements(lambda: held)
        for ident in (a, b, c):
            store.name(model_token(ident, "r1"), plate, BY)
        store.keep(plate["key"], "cnc", {"report": {"x": 1}}, BY)

        # No engine: the deletion is the command's own, and tells no one.
        self.assertEqual(registry.FORGOTTEN, [])
        delete(held, c)
        self.assertEqual(held.cache.names("checks/models"), sorted([a, b]))
        self.assertIsNone(Measurements(lambda: held).content(model_token(c, "r1")), "the engine started next finds none")

        registry.FORGOTTEN.append(store.deleted)
        self.addCleanup(registry.FORGOTTEN.remove, store.deleted)
        store.name(build_token(b, "g1"), plate, BY)
        since = store.epoch(b)
        held.delete(b)
        self.assertEqual((store.content(model_token(b, "r1")), held.cache.names("checks/models")), (None, [a]))
        self.assertIsNone(store.content(build_token(b, "g1")))
        store.name(model_token(b, "r1"), plate, BY, since=since)
        self.assertEqual((store.content(model_token(b, "r1")), held.cache.names("checks/models")), (None, [a]),
                         "a check that began before its deletion names nothing")
        store.name(model_token(b, "r1"), plate, BY, since=store.epoch(b))
        self.assertEqual(store.content(model_token(b, "r1")), plate, "built and checked again: named again")
        self.assertEqual((store.content(model_token(a, "r1")), Measurements(lambda: held).get(plate["key"], "cnc")),
                         (plate, {"report": {"x": 1}}), "another document's, and the measurement, as they were")

    def test_an_alias_read_as_its_document_is_deleted_is_neither_answered_nor_kept(self) -> None:
        """A check reads a model's alias from disk as the model is deleted: what it read is of a document gone,
        so it is not answered and does not come back into memory, where the next check of a model built again
        under the id would find it."""
        from cad_server.engine.measurements import Measurements, model_token

        folder = self.folder()
        ident, plate = str(uuid.uuid4()), record()
        Measurements(lambda: folder).name(model_token(ident, "r1"), plate, BY)
        store = Measurements(lambda: folder)
        read = store.models.read
        deleting = threading.Thread(target=lambda: (shutil.rmtree(folder.path(f"checks/models/{ident}")),
                                                     store.deleted(ident)), daemon=True)

        def deleted_as_it_is_read(*args: Any) -> Any:
            found = read(*args)
            deleting.start()  # as ``Registry.delete`` does: its folder removed, the store told
            deadline = time.monotonic() + 60.0
            while store.epoch(ident) == 0:  # the deletion is counted before the read goes on
                self.assertLess(time.monotonic(), deadline, "the deletion never ran")
                time.sleep(0.001)
            return found

        store.models.read = deleted_as_it_is_read
        self.assertIsNone(store.content(model_token(ident, "r1")))
        deleting.join(60.0)
        store.models.read = read
        self.assertEqual((store.status()["aliases"], store.content(model_token(ident, "r1"))), (0, None))
        store.name(model_token(ident, "r1"), plate, BY)
        self.assertEqual(Measurements(lambda: folder).content(model_token(ident, "r1")), plate, "read as ever, undeleted")


if __name__ == "__main__":
    unittest.main()
