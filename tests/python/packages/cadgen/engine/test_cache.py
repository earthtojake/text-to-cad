"""The engine's document cache: a model document idle a moment is saved once per revision in the
cache folder (its record, in the state folder, says so), so a restarted engine answers every verb
of it -- page, export, snapshot, inspect, cad_show -- with nothing run; a document whose code
changed since says so and reruns nothing; the cache is bounded, least recently used first, and
touches nothing in its folder but ``documents/``; and an engine whose cache folder is read-only
behaves as one with no cache at all."""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cadgen.engine.ids import file_id, model_id  # noqa: E402
from cadgen.engine.registry import Registry  # noqa: E402

IDLE = 0.3  # the cache's idle seam (``CADGEN_ENGINE_CACHE_IDLE``), in seconds

SCRIPT = """
import pathlib
import build123d as bd
from cadgen.engine import model

pathlib.Path(__file__).with_suffix(".ran").write_text("ran", encoding="utf-8")
WIDTH = {width}


@model
def {name}():
    return bd.Box(WIDTH, 2, 1)


if __name__ == "__main__":
    {name}()
"""

DECLARED = """
import build123d as bd
from cadgen.engine import xbf


@xbf("XBF/plate.xbf")
def plate():
    return bd.Box(4, 3, 1)


if __name__ == "__main__":
    plate()
"""


def await_(condition, what: str, seconds: float = 60.0):
    deadline = time.monotonic() + seconds
    while True:
        found = condition()
        if found:
            return found
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.02)


def get(url: str, token: str) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


class CacheTest(unittest.TestCase):
    """Through a real daemon, in an engine, a state and a cache folder of the test's own."""

    def setUp(self) -> None:
        self.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-cache-")))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.project = self.folder / "project"
        self.project.mkdir()
        self.use(self.folder / "state", self.folder / "cache")

    def use(self, state: Path, cache: Path, **extra: str) -> None:
        """The engine the test talks to from now on: a folder of its own, and ``state`` and ``cache``."""
        self.state, self.cache = state, cache
        self.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, self.engine, True)
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(self.engine),
                                          "CADGEN_STATE_DIR": str(state), "CADGEN_CACHE_DIR": str(cache),
                                          "CADGEN_ENGINE_IDLE": "120", "CADGEN_ENGINE_MESH": "inline",
                                          "CADGEN_ENGINE_CACHE_IDLE": str(IDLE), **extra}, self.addCleanup)
        self.addCleanup(self.cli, "stop", env=dict(self.env))

    def cli(self, *args: str, env: dict | None = None):
        return engine_daemon.run([sys.executable, "-m", "cadgen.engine", *args], cwd=self.project, env=env or self.env)

    def run_script(self, name: str):
        done = engine_daemon.run([sys.executable, f"{name}.py"], cwd=self.project, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    def write(self, name: str, width: float = 3.0, text: str = SCRIPT) -> str:
        (self.project / f"{name}.py").write_text(textwrap.dedent(text.format(name=name, width=width)), encoding="utf-8")
        return model_id(self.project / f"{name}.py", name)

    def ask(self, message: dict) -> dict:
        from cadgen.engine.client import request

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.engine)}):
            return request(message, start=False) or {}

    def record(self, ident: str) -> dict:
        return Registry(self.state).get(ident) or {}

    def file(self, ident: str) -> Path:
        return self.cache / "documents" / ident / "document.xbf"

    def cached(self, ident: str, revision: str | None = None) -> dict:
        """The record's ``cache`` field, once its file is there (at ``revision``, when given)."""
        def found():
            meta = self.record(ident).get("cache")
            ok = meta and self.file(ident).is_file() and (revision is None or meta["revision"] == revision)
            return meta if ok else None

        return await_(found, f"{ident}'s cache file")

    def page(self, ident: str) -> tuple[int, dict]:
        serving = self.ask({"op": "status"})["serving"]
        return get(f"{serving['url']}/api/doc/{ident}", self.ask({"op": "http"}).get("token", ""))

    def ran(self, name: str) -> bool:
        return (self.project / f"{name}.ran").exists()

    # --- the tests ----------------------------------------------------------------------

    def test_an_idle_build_is_saved_once_and_an_unchanged_run_rewrites_nothing(self) -> None:
        ident = self.write("cube")
        self.run_script("cube")
        meta = self.cached(ident)
        record = self.record(ident)
        self.assertEqual((meta["revision"], meta["bytes"]), (record["revision"], self.file(ident).stat().st_size))
        self.assertEqual(sorted(row[1] for row in meta["read"]), ["cube.py"], "what the build read, by digest")
        self.assertEqual(sorted(os.listdir(self.state / "documents" / ident)), ["document.json"],
                         "the bytes are the cache folder's, never the state folder's")
        stamps = (self.file(ident).stat().st_mtime_ns, (self.state / "documents" / ident / "document.json").stat().st_mtime_ns)
        self.run_script("cube")
        time.sleep(IDLE * 4)  # its idle window passed again
        self.assertEqual((self.file(ident).stat().st_mtime_ns,
                          (self.state / "documents" / ident / "document.json").stat().st_mtime_ns), stamps,
                         "an unchanged document is never rewritten")
        self.assertEqual(self.ask({"op": "status"})["cache"]["written"], 1)
        # Removed from the home, its cache file goes with its record.
        from cadgen.viewer.recents import RecentStore

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.cache)}):
            RecentStore(self.state).remove(ident)
        self.assertFalse(self.file(ident).parent.exists())

    def test_a_restart_answers_every_verb_from_the_cache_and_an_edit_is_said_never_rerun(self) -> None:
        ident = self.write("cube")
        self.run_script("cube")
        live = {kind: self.folder / f"live.{kind}" for kind in ("xbf", "glb")}
        self.assertEqual(self.cli("export", ident, *map(str, live.values())).returncode, 0)
        self.cached(ident)
        self.assertEqual(self.cli("stop").returncode, 0)
        (self.project / "cube.ran").unlink()

        inspected = self.cli("inspect", ident)  # starts the engine afresh
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["source"]["function"], "cube")
        self.assertNotIn("stale", json.loads(inspected.stdout))
        cold = {kind: self.folder / f"cold.{kind}" for kind in ("xbf", "glb")}
        exported = self.cli("export", ident, *map(str, cold.values()))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        for kind in cold:
            self.assertEqual(cold[kind].read_bytes(), live[kind].read_bytes(), f"the {kind} is the live export's")
        snapped = self.cli("snapshot", ident, str(self.folder / "cold.png"))
        self.assertEqual(snapped.returncode, 0, snapped.stderr)
        self.assertGreater((self.folder / "cold.png").stat().st_size, 0)
        status, structure = self.page(ident)
        self.assertEqual((status, structure.get("stale")), (200, None))
        self.assertEqual(structure["closure"]["source"]["function"], "cube")
        listed = self.ask({"op": "status"})
        (row,) = [row for row in listed["models"] if row["id"] == ident]
        self.assertEqual((row["state"], row["held"]), ("held", "memory and disk"))
        self.assertEqual([Path(worker["script"]).name for worker in listed["workers"]], ["documents"])
        from cadgen.mcp.server import _say_not_held

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.engine)}):
            self.assertIsNone(_say_not_held(ident), "cad_show shows it, with nothing to add")
        self.assertFalse(self.ran("cube"), "nothing ran the script")

        # The code changes: the page and inspect say so, with the command; nothing reruns.
        self.write("cube", width=5.0)
        (self.project / "cube.ran").unlink(missing_ok=True)
        command = f"python {self.project / 'cube.py'}"
        status, structure = self.page(ident)
        self.assertEqual(status, 200)
        self.assertEqual((structure["stale"]["changes"], structure["stale"]["rebuild"]), (["cube.py changed"], command))
        self.assertIn("the code changed since this was built", structure["stale"]["text"])
        inspected = self.cli("inspect", ident)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertIn(f"the code changed since this was built (cube.py changed); run `{command}`", inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["stale"]["rebuild"], command)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.engine)}):
            self.assertIn("the code changed since this was built", _say_not_held(ident))
        self.assertFalse(self.ran("cube"), "nothing reran it")

    def test_a_rebuild_replaces_the_cache_at_its_new_revision(self) -> None:
        ident = self.write("cube")
        self.run_script("cube")
        first = self.cached(ident)["revision"]
        before = self.file(ident).read_bytes()
        self.write("cube", width=6.0)
        self.run_script("cube")
        revision = self.record(ident)["revision"]
        self.assertNotEqual(revision, first)
        self.assertEqual(self.cached(ident, revision)["revision"], revision)
        self.assertNotEqual(self.file(ident).read_bytes(), before, "the new build's document")

    def test_a_build_arriving_during_a_save_waits_for_it_and_succeeds(self) -> None:
        from cadgen.engine import daemon, document

        ident = self.write("cube")
        script = str(self.project / "cube.py")
        saved: list[tuple[dict, bytes]] = []
        worker = daemon.Worker(script, {**os.environ, "PYTHONPATH": str(SRC)},
                               on_saved=lambda _worker, header, payload: saved.append((header, payload)))
        self.addCleanup(worker.stop)
        order = {"id": 1, "op": "build", "script": script, "functions": None, "cwd": str(self.project)}
        self.assertIn("done", worker.build(order, lambda _message: None))
        worker.save(ident, script, "cube", "g1")
        answer = worker.build({**order, "id": 2}, lambda _message: None)  # queued behind the save
        self.assertTrue(all(report["ok"] for report in answer["done"]), answer)
        (header, payload), = await_(lambda: saved, "the save's answer")
        self.assertEqual((header["ident"], header["generation"], header.get("error")), (ident, "g1", None))
        self.assertTrue(document.read_bytes(payload), "the whole document's bytes")

    def test_a_stop_saves_a_document_built_in_its_last_idle_window(self) -> None:
        self.use(self.state, self.cache, CADGEN_ENGINE_CACHE_IDLE="600")
        ident = self.write("cube")
        self.run_script("cube")
        self.assertFalse(self.file(ident).exists(), "not idle yet")
        self.assertEqual(self.cli("stop").returncode, 0)
        self.assertEqual(self.record(ident)["cache"]["revision"], self.record(ident)["revision"])
        self.assertTrue(self.file(ident).is_file())
        # The next engine's viewer opens it by its id, as it held it.
        launched = engine_daemon.run([sys.executable, "-m", "cadgen.viewer", "--json", "--api-only", ident],
                                     cwd=self.project, env=self.env)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertEqual([row["id"] for row in json.loads(launched.stdout)["documents"]], [ident])

    def test_past_its_cap_the_least_recently_used_goes_and_nothing_else_in_the_folder_is_touched(self) -> None:
        foreign = self.cache / "objects" / "ab" / "0.7-object"
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(b"a 0.7 store object")
        beside = self.cache / "index.db"
        beside.write_bytes(b"0.7")
        stamps = {path: path.stat().st_mtime_ns for path in (foreign, beside)}
        first = self.write("first")
        self.run_script("first")
        size = self.cached(first)["bytes"]
        self.assertEqual(self.cli("stop").returncode, 0)
        # Room for two and a half documents, and a second engine bound by it: its workers go when idle.
        self.use(self.state, self.cache, CADGEN_ENGINE_CACHE_GB=str(2.6 * size / 2**30), CADGEN_ENGINE_WORKER_IDLE="1")
        second = self.write("second")
        self.run_script("second")
        self.cached(second)
        await_(lambda: self.ask({"op": "status"})["workers"] == [], "second's worker to retire")
        self.assertEqual(self.cli("export", first, str(self.folder / "first.step")).returncode, 0)  # read: recent
        third = self.write("third")
        self.run_script("third")
        self.cached(third)
        await_(lambda: not self.file(second).exists(), "the least recently used to go")
        self.assertTrue(self.file(first).is_file() and self.file(third).is_file())
        self.assertNotIn("cache", self.record(second), "its record stays, saying it is not cached")
        cache = self.ask({"op": "status"})["cache"]
        self.assertEqual((cache["documents"], cache["evictions"], cache["root"]), (2, 1, str(self.cache)))
        self.assertIn(f"cache {self.cache}: 2 documents", self.cli("status").stdout)
        self.assertEqual({path: path.stat().st_mtime_ns for path in stamps}, stamps, "the rest of the folder is not ours")
        self.assertEqual(foreign.read_bytes(), b"a 0.7 store object")

    def test_a_declared_xbf_model_is_cached_its_file_untouched_and_a_file_document_gets_none(self) -> None:
        (self.project / "plate.py").write_text(textwrap.dedent(DECLARED), encoding="utf-8")
        self.run_script("plate")
        declared = self.project / "XBF" / "plate.xbf"
        written = (declared.read_bytes(), declared.stat().st_mtime_ns)
        ident = model_id(self.project / "plate.py", "plate")
        meta = self.cached(ident)
        self.assertNotIn(str(declared), json.dumps(self.record(ident)), "the cache never points at the author's file")
        served = self.ask({"op": "serve", "path": str(declared)})
        self.assertEqual(served.get("doc"), file_id(declared))
        time.sleep(IDLE * 4)
        self.assertEqual((declared.read_bytes(), declared.stat().st_mtime_ns), written, "the declared file is the author's")
        self.assertEqual(sorted(os.listdir(self.cache / "documents")), [ident], "a file's document is its own file")
        self.assertEqual(meta["bytes"], self.file(ident).stat().st_size)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "a read-only folder is POSIX's, and refuses no one running as root")
    def test_with_its_cache_folder_read_only_the_engine_behaves_as_one_with_no_cache(self) -> None:
        def scenario(tag: str, **extra: str) -> dict:
            self.use(self.folder / f"state-{tag}", self.folder / f"cache-{tag}", **extra)
            self.cache.mkdir()
            if tag == "read-only":
                self.cache.chmod(stat.S_IRUSR | stat.S_IXUSR)
                self.addCleanup(self.cache.chmod, stat.S_IRWXU)
            ident = self.write("cube")
            seen: dict = {"build": [line for line in self.run_script("cube").stdout.splitlines() if "id:" in line]}
            time.sleep(IDLE * 4)  # idle: a save is tried
            status, structure = self.page(ident)
            seen["page"] = (status, sorted(structure), structure.get("stale"))
            seen["state"] = self.ask({"op": "state", "id": ident})
            out = self.folder / f"{tag}.xbf"
            seen["export"] = (self.cli("export", ident, str(out)).returncode, out.read_bytes())
            seen["inspect"] = self.cli("inspect", ident).stdout
            listed = self.ask({"op": "status"})
            seen["models"] = [(row["state"], row.get("held")) for row in listed["models"]]
            failures = listed["cache"]["failures"]
            self.assertEqual(self.cli("stop").returncode, 0)
            (self.project / "cube.ran").unlink()
            again = self.cli("inspect", ident)
            seen["restart"] = (again.returncode, again.stderr)
            seen["restart state"] = self.ask({"op": "state", "id": ident})
            seen["restart page"] = self.page(ident)
            seen["ran"] = self.ran("cube")
            self.assertEqual(self.cli("stop").returncode, 0)
            seen = json.loads(json.dumps(seen, default=lambda value: value.hex()).replace(str(self.state), "STATE"))
            return seen, failures, list(self.cache.iterdir())

        read_only, failures, left = scenario("read-only")
        self.assertTrue(failures, "the failed save is listed")
        self.assertEqual(left, [], "and nothing is cached")
        uncached, _failures, _left = scenario("off", CADGEN_ENGINE_CACHE_GB="0")
        self.assertEqual(read_only, uncached, "every verb, every state, every message as with no cache")
        self.assertEqual(read_only["restart"][0], 2, "after a restart it is not held: its command is said")


if __name__ == "__main__":
    unittest.main()
