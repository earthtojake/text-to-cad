"""The engine's document cache: a model document idle a moment is saved once per revision in the
cache folder (its record, in the state folder, says so), so a restarted engine answers every verb
of it -- page, export, snapshot, inspect, cad_show -- with nothing run; a document whose code
changed since is answered as its last run, and nothing reruns; the cache keeps every document until a person deletes it,
with no cap and nothing evicted, and touches nothing in its folder but ``documents/``; and an engine
whose cache folder is read-only, or not writable at all, saves nothing and does everything else as
ever."""

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

from tests.python.support import engine_daemon, opengl

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

# A model whose body says on stderr that it ran: the worker's output reaches the run's stderr.
SAID = """
import sys
import build123d as bd
from cadgen.engine import model

WIDTH = {width}


@model
def {name}():
{body}


if __name__ == "__main__":
    {name}()
"""
GOOD = '    print("the body ran", file=sys.stderr)\n    return bd.Box(WIDTH, 2, 1)'

# A model declaring a STEP and no xbf, whose body says on stderr that it ran.
STEPPED = """
import sys
import build123d as bd
from cadgen.engine import step


@step("plate.step")
def plate():
    print("the body ran", file=sys.stderr)
    return bd.Box({width}, 3, 1)


if __name__ == "__main__":
    plate()
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
    """Through a real daemon. The class shares one engine, with a state and a cache folder of its
    own (so its workers' bytecode is compiled once), and each test starts with nothing recorded in
    it; a test whose engine needs another environment, or folders of its own, starts that engine
    (``use``), which reads the class's bytecode."""

    @classmethod
    def setUpClass(cls) -> None:
        from cadgen.engine import daemon

        cls.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-cache-")))
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        cls.shared = cls.root / "state", cls.root / "cache"
        cls.engine_env = cls.environment(*cls.shared, cls.addClassCleanup)
        cls.bytecode = str(cls.shared[1] / daemon.PYCACHE / daemon._tag())  # the class engine's own

    @classmethod
    def environment(cls, state: Path, cache: Path, cleanup, **extra: str) -> dict:
        """An engine's environment: a folder of its own, ``state`` and ``cache``; stopped at ``cleanup``."""
        engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cleanup(shutil.rmtree, engine, True)
        # The class engine keeps its bytecode where the engine does (the first test reads it there),
        # whatever folder a test run shares.
        given = {name: value for name, value in os.environ.items() if name != "PYTHONPYCACHEPREFIX"}
        env = engine_daemon.started({**given, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(engine),
                                     "CADGEN_STATE_DIR": str(state), "CADGEN_CACHE_DIR": str(cache),
                                     "CADGEN_ENGINE_MESH": "inline", "CADGEN_ENGINE_CACHE_IDLE": str(IDLE),
                                     **extra}, cleanup)
        cleanup(lambda: engine_daemon.run([sys.executable, "-m", "cadgen.engine", "stop"], env=dict(env)))
        return env

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="test-", dir=self.root))
        self.project = self.folder / "project"
        self.project.mkdir()
        (self.state, self.cache), self.env = self.shared, self.engine_env
        self.engine = Path(self.env["CADGEN_ENGINE_DIR"])
        engine_daemon.bootstrap(self.env)
        self.reset()

    def reset(self) -> None:
        """Nothing recorded in the class's engine: every document an earlier test left, deleted."""
        from cadgen.engine import api

        with mock.patch.dict(os.environ, self.env, clear=True):
            left = [row["id"] for row in Registry(self.state).list()]
            if left:
                api.delete(left)

    def use(self, state: Path, cache: Path, **extra: str) -> None:
        """The engine the test talks to from now on: one of its own, on ``state`` and ``cache``."""
        self.state, self.cache = state, cache
        self.env = self.environment(state, cache, self.addCleanup, PYTHONPYCACHEPREFIX=self.bytecode, **extra)
        self.engine = Path(self.env["CADGEN_ENGINE_DIR"])

    @property
    def document_state(self) -> Path:
        return Registry(self.state).state.root

    @property
    def document_cache(self) -> Path:
        return Registry(self.state, self.cache).cache.root

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

        with mock.patch.dict(os.environ, self.env, clear=True):
            return request(message, start=False) or {}

    def record(self, ident: str) -> dict:
        return Registry(self.state).get(ident) or {}

    def file(self, ident: str) -> Path:
        return self.document_cache / "documents" / ident / "document.xbf"

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

    def test_an_idle_build_is_saved_in_the_cache_folder_with_its_record_saying_so(self) -> None:
        ident = self.write("cube")
        written = (self.ask({"op": "status"}).get("cache") or {}).get("written", 0)
        self.run_script("cube")
        meta = self.cached(ident)
        record = self.record(ident)
        self.assertEqual(set(record), {"schema", "id", "kind", "root", "home", "entry", "revision", "built", "created", "facts",
                                       "cache", "namespace", "name", "fingerprint", "module", "declares"},
                         "a build's record, once its document is cached")
        self.assertEqual(set(meta), {"revision", "bytes"})
        self.assertEqual((meta["revision"], meta["bytes"]), (record["revision"], self.file(ident).stat().st_size))
        self.assertEqual(sorted(os.listdir(self.document_state / "documents" / ident)), ["document.json"],
                         "the bytes are the cache folder's, never the state folder's")
        compiled = list((self.cache / "pycache").glob("*/**/build123d/__init__.*.pyc"))  # the prefix mirrors its path
        self.assertTrue(compiled, "each execution environment caches its libraries under the engine cache")
        self.assertEqual(list(self.project.rglob("*.pyc")), [], "none beside the model")
        self.assertEqual(self.ask({"op": "status"})["cache"]["written"], written + 1)

    def home(self, action: str, path: str) -> tuple[int, dict]:
        """A change to the home's library, as the engine's page posts it (``/__cad/recents``)."""
        serving = self.ask({"op": "status"})["serving"]
        request = urllib.request.Request(f"{serving['url']}/__cad/recents", method="POST",
                                         data=json.dumps({"action": action, "path": path}).encode(),
                                         headers={"Authorization": "Bearer " + self.ask({"op": "http"})["token"],
                                                  "x-cadgen-viewer": "1", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    def test_delete_is_one_function_from_the_shell_and_from_the_home(self) -> None:
        cube, other = self.write("cube"), self.write("other")
        for name, ident in (("cube", cube), ("other", other)):
            self.run_script(name)
            self.cached(ident)
        # The shell refuses a document it cannot name, before anything is deleted.
        refused = self.cli("delete", cube, str(self.project / "nothing.py"))
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn(f"no document is recorded for {self.project / 'nothing.py'}", refused.stderr)
        self.assertTrue(self.record(cube) and self.file(cube).is_file(), "nothing was deleted")
        # Several at once, an id and a model's script: a line each; the record, the cached document and
        # the engine's copy go; the script stays.
        done = self.cli("delete", cube, str(self.project / "other.py"))
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, f"deleted cube {cube}\ndeleted other {other}\n", ""))
        for ident in (cube, other):
            self.assertEqual(self.record(ident), {})
            self.assertFalse(self.file(ident).parent.exists())
        self.assertEqual([row["id"] for row in self.ask({"op": "status"})["models"]], [])
        self.assertEqual(self.page(cube)[0], 404, "the engine holds it no more")
        self.assertTrue((self.project / "cube.py").is_file(), "never a file of the person's")
        # The next run registers it again, and the cache keeps it again.
        self.run_script("cube")
        self.cached(cube)
        # The home's Delete is the same deletion; Remove is a file's alone.
        self.assertEqual(self.home("remove", cube)[0], 400, "a model's row is deleted, never removed")
        status, body = self.home("delete", cube)
        self.assertEqual(status, 200, body)
        self.assertNotIn(cube, [row.get("id") for row in body["recents"]])
        self.assertEqual(self.record(cube), {})
        self.assertFalse(self.file(cube).parent.exists())
        self.assertEqual(self.page(cube)[0], 404)
        # With no engine running, the shell deletes the record and its file, and starts none.
        self.run_script("other")
        self.cached(other)
        self.assertEqual(self.cli("stop").returncode, 0)
        done = self.cli("delete", other, "--json")
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(json.loads(done.stdout), {"ok": True, "deleted": [{"id": other, "name": "other", "kind": "model"}]})
        self.assertEqual((self.record(other), self.file(other).parent.exists()), ({}, False))
        self.assertIn("no engine server is running", self.cli("status").stdout)

    def test_a_restart_answers_every_verb_from_the_cache_and_an_edit_reruns_nothing(self) -> None:
        ident = self.write("cube")
        self.run_script("cube")
        live = {kind: self.folder / f"live.{kind}" for kind in ("xbf", "glb")}
        self.assertEqual(self.cli("export", ident, *map(str, live.values())).returncode, 0)
        self.cached(ident)
        self.assertEqual(self.cli("stop").returncode, 0)
        engine_daemon.bootstrap(self.env)
        (self.project / "cube.ran").unlink()

        inspected = self.cli("inspect", ident, "--json")  # reads the explicitly restarted engine
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["closure"]["source"]["function"], "cube")
        self.assertEqual(json.loads(inspected.stdout)["summary"]["state"]["state"], "held")
        cold = {kind: self.folder / f"cold.{kind}" for kind in ("xbf", "glb")}
        exported = self.cli("export", ident, *map(str, cold.values()))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        for kind in cold:
            self.assertEqual(cold[kind].read_bytes(), live[kind].read_bytes(), f"the {kind} is the live export's")
        from cadgen.engine.render import context

        if opengl.draws(context.available(), "the cold snapshot is drawn by OCCT"):
            snapped = self.cli("snapshot", ident, str(self.folder / "cold.png"))
            self.assertEqual(snapped.returncode, 0, snapped.stderr)
            self.assertGreater((self.folder / "cold.png").stat().st_size, 0)
        # Inspection no longer prefetches meshes. The first page does, and their status
        # fields appear asynchronously: wait for those before comparing two page reads.
        def meshed_page():
            status, structure = self.page(ident)
            return (status, structure) if status == 200 and all(
                "unmeshed" in part for part in structure["prototypes"]) else None

        status, structure = await_(meshed_page, "the page's prefetched meshes")
        self.assertEqual(status, 200)
        self.assertEqual(structure["closure"]["source"]["function"], "cube")
        listed = self.ask({"op": "status"})
        (row,) = [row for row in listed["models"] if row["id"] == ident]
        self.assertEqual((row["state"], row["held"]), ("held", "memory and disk"))
        self.assertEqual([Path(worker["script"]).name for worker in listed["workers"]], ["documents"])
        from cadgen.mcp.server import _say_not_held

        with mock.patch.dict(os.environ, self.env, clear=True):
            self.assertIsNone(_say_not_held(ident), "cad_show shows it, with nothing to add")
        self.assertFalse(self.ran("cube"), "nothing ran the script")

        # The code changes: every surface answers the document of its last run, as it did, and says
        # nothing of the edit -- when to run the code again is the agent's call; nothing reruns.
        self.write("cube", width=5.0)
        (self.project / "cube.ran").unlink(missing_ok=True)
        self.assertEqual(self.page(ident), (status, structure), "the page reads the last run, as before")
        inspected = self.cli("inspect", ident)
        self.assertEqual((inspected.returncode, inspected.stderr), (0, ""))
        self.assertTrue(inspected.stdout.splitlines()[1].startswith("state       held (in memory and disk), cached, "
                                                                    "built "), inspected.stdout)
        with mock.patch.dict(os.environ, self.env, clear=True):
            self.assertIsNone(_say_not_held(ident))
        self.assertFalse(self.ran("cube"), "nothing reran it")

    def test_running_engines_share_saved_models_and_a_stale_shutdown_preserves_the_newer_save(self) -> None:
        self.use(self.folder / "state", self.folder / "cache", CADGEN_ENGINE_CACHE_IDLE="600")
        first = self.env
        second = self.environment(self.state, self.cache, self.addCleanup, PYTHONPYCACHEPREFIX=self.bytecode)
        self.assertNotEqual(first["CADGEN_PORT"], second["CADGEN_PORT"])
        self.env = second
        self.assertEqual(self.ask({"op": "status"})["cache"]["documents"], 0)

        self.env = first
        ident = self.write("cube")
        script = self.project / "cube.py"
        self.run_script("cube")
        self.assertEqual(self.cli("stop").returncode, 0)  # flush without an idle-window race
        original_cache = self.cached(ident)
        script.unlink()
        (self.project / "cube.ran").unlink()

        # The other engine was already running with an empty cache index. Its shared home
        # discovers the saved model, and opening it needs neither its source nor a model worker.
        self.env = second
        listed = self.ask({"op": "status"})
        self.assertIn(ident, [row["id"] for row in listed["models"]])
        serving = listed["serving"]
        status, home = get(f"{serving['url']}/__cad/recents", self.ask({"op": "http"})["token"])
        self.assertEqual(status, 200, home)
        self.assertIn(ident, [entry.get("id") for entry in home["recents"]])
        opened = self.cli("inspect", ident, "--json")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.assertEqual(json.loads(opened.stdout)["summary"]["bounds"]["size"], [3.0, 2.0, 1.0])
        self.assertFalse(self.ran("cube"), "opening saved bytes did not run the missing script")
        self.assertNotIn(str(script), [worker["script"] for worker in self.ask({"op": "status"})["workers"]])

        # Keep an unsaved older build live in the first engine while the second saves a
        # newer build of the same model. Live workers remain local to their engine.
        self.env = first
        engine_daemon.bootstrap(first)
        self.write("cube", width=4.0)
        self.run_script("cube")
        stale_revision = self.record(ident)["revision"]
        self.assertNotEqual(stale_revision, original_cache["revision"])
        self.assertEqual(self.record(ident)["cache"], original_cache, "the long idle window leaves this build unsaved")
        (first_worker,) = [worker for worker in self.ask({"op": "status"})["workers"] if worker["script"] == str(script)]
        self.env = second
        self.write("cube", width=5.0)
        self.run_script("cube")
        (second_worker,) = [worker for worker in self.ask({"op": "status"})["workers"] if worker["script"] == str(script)]
        self.assertNotEqual(first_worker["pid"], second_worker["pid"])
        revision = self.record(ident)["revision"]
        self.assertNotEqual(revision, stale_revision)
        self.cached(ident, revision)
        newest_record, newest_bytes = self.record(ident), self.file(ident).read_bytes()

        self.assertEqual(self.cli("stop", env=first).returncode, 0)
        self.assertEqual(self.record(ident), newest_record, "the stale engine cannot replace the newer record")
        self.assertEqual(self.file(ident).read_bytes(), newest_bytes, "the stale shutdown cannot replace the newer bytes")
        script.unlink()
        (self.project / "cube.ran").unlink()
        saved = self.cli("inspect", str(self.file(ident)), "--json")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        summary = json.loads(saved.stdout)["summary"]
        self.assertEqual(summary["bounds"]["size"], [5.0, 2.0, 1.0])
        self.assertAlmostEqual(summary["volume"], 10.0)
        self.assertFalse(self.ran("cube"), "reading the newer saved bytes did not rebuild")

    def said(self, body: str = GOOD, width: float = 3.0) -> str:
        """``cube.py``, its model's body ``body``: the model's id."""
        (self.project / "cube.py").write_text(SAID.format(name="cube", width=width, body=body), encoding="utf-8")
        return model_id(self.project / "cube.py", "cube")

    def assert_taken(self) -> None:
        """A run of ``cube.py`` that took its document from the engine's cache: no body ran."""
        done = self.run_script("cube")
        self.assertIn("took cube.py::cube cold in", done.stdout)
        self.assertIn("the engine's cache holds the model's key, 1 body loaded, nothing ran", done.stdout)
        self.assertNotIn("the body ran", done.stderr)

    def generation(self, stdout: str, after: str | None = None) -> str:
        """The generation a page reads of the document a run printed (its `view:` page's version); with
        ``after``, what a page waiting a moment on that generation is answered."""
        import urllib.parse
        import urllib.request

        view = urllib.parse.urlsplit(next(line.split()[1] for line in stdout.splitlines() if line.strip().startswith("view:")))
        link = urllib.parse.parse_qs(view.query)["token"][0]
        wait = f"?after={after}&wait=1" if after else ""
        request = urllib.request.Request(f"{view.scheme}://{view.netloc}/__cad/api/doc{view.path}/version{wait}",
                                         headers={"Authorization": f"Bearer {link}"})
        with urllib.request.urlopen(request, timeout=30) as answer:
            return json.loads(answer.read())["version"]


    def test_two_unchanged_runs_leave_one_generation_and_the_page_idle(self) -> None:
        # A document is what its last run made: nothing ran, nothing changed, so a page has nothing to fetch.
        self.said()
        self.assertIn("the body ran", self.run_script("cube").stderr)
        first = self.run_script("cube")
        self.assertIn("nothing ran", first.stdout)
        version = self.generation(first.stdout)
        second = self.run_script("cube")
        self.assertIn("nothing ran", second.stdout)
        self.assertEqual(self.generation(second.stdout), version)
        self.assertEqual(self.generation(second.stdout, after=version), version, "a waiting page is not woken")
        self.said(width=5.0)
        edited = self.run_script("cube")
        self.assertIn("the body ran", edited.stderr)
        self.assertNotEqual(self.generation(edited.stdout), version, "an edit is a new generation")

    def corrupt(self, ident: str) -> None:
        """The document's cache file broken where its bytes are read, its size and its head (the writer
        and the closure a build compares) as they were: what an earlier test of this left behind."""
        path = self.file(ident)
        data = bytearray(path.read_bytes())
        from cadgen.engine import previous

        kept = data.find(previous._PREFIX)
        kept = data.find(b"\x00", kept) if kept >= 0 else 0
        self.assertLess(kept + 64, len(data) - 1024, "room past the head to break")
        data[-1024:] = bytes(1024)
        path.write_bytes(bytes(data))

    def test_an_unreadable_saved_document_is_preserved_until_an_explicit_rebuild(self) -> None:
        ident = self.said()
        self.assertIn("the body ran", self.run_script("cube").stderr)
        meta = self.cached(ident)
        whole = self.file(ident).read_bytes()
        self.assertEqual(self.cli("stop").returncode, 0)
        self.corrupt(ident)
        broken, record = self.file(ident).read_bytes(), self.record(ident)
        out = self.folder / "cube.step"
        for _ in range(2):
            engine_daemon.bootstrap(self.env)
            exported = self.cli("export", ident, str(out))
            self.assertEqual(exported.returncode, 2, exported.stderr)
            self.assertIn("cannot read saved", exported.stderr)
            self.assertIn("original document is preserved", exported.stderr)
            self.assertIn("explicitly rebuild", exported.stderr)
            self.assertFalse(out.exists())
            self.assertEqual(self.file(ident).read_bytes(), broken)
            self.assertEqual(self.record(ident), record)
            self.assertEqual(self.cli("stop").returncode, 0)
        engine_daemon.bootstrap(self.env)
        self.assertIn("the body ran", self.run_script("cube").stderr)
        await_(lambda: self.file(ident).read_bytes() == whole, "the successful rebuild's atomic cache replacement")
        self.assertEqual(self.cached(ident, meta["revision"])["bytes"], len(whole))
        self.assertEqual(self.cli("stop").returncode, 0)
        engine_daemon.bootstrap(self.env)
        self.assertEqual(self.cli("export", ident, str(out)).returncode, 0, "the next restart reads the rebuilt file")
        self.assertGreater(out.stat().st_size, 0)

    def legacy_cache(self, data: bytes) -> tuple[str, dict]:
        """Install historical bytes in a real registered model's cache, with its source gone."""
        ident = self.write("cube")
        self.run_script("cube")
        self.cached(ident)
        self.assertEqual(self.cli("stop").returncode, 0)
        self.file(ident).write_bytes(data)
        Registry(self.state).update(ident, lambda record: {
            **record, "cache": {**record["cache"], "bytes": len(data)},
        })
        (self.project / "cube.py").unlink()
        (self.project / "cube.ran").unlink()
        return ident, self.record(ident)

    def test_legacy_cached_snapshot_opens_after_restart_without_source_or_rewriting_cache(self) -> None:
        from cadgen.engine import document, document_migrations, previous

        fixture = Path(__file__).with_name("fixtures") / "xbf8_materials.xbf"
        original = fixture.read_bytes()
        ident, record = self.legacy_cache(original)
        engine_daemon.bootstrap(self.env)
        original_closure = previous.read_record(document.read_bytes(original))[1]
        partial = self.folder / "must-not-write.step"
        refused = self.cli("export", ident, str(partial), str(self.file(ident)))
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn("cached document is preserved", refused.stderr)
        self.assertFalse(partial.exists())
        self.assertEqual(self.file(ident).read_bytes(), original)
        self.assertEqual(self.record(ident), record)
        for suffix in ("step", "glb", "xbf"):
            out = self.folder / f"migrated.{suffix}"
            exported = self.cli("export", ident, str(out))
            self.assertEqual(exported.returncode, 0, exported.stderr)
            self.assertGreater(out.stat().st_size, 0)
        loaded = document.Loaded(self.folder / "migrated.xbf")
        self.assertEqual(document.written_format(loaded.writer), previous.FORMAT)
        self.assertEqual(previous.read_record(loaded.doc)[1], original_closure)
        self.assertEqual(document_migrations.provenance(loaded.doc)["origin"], {
            "kind": "document", "id": ident, "script": str(self.project / "cube.py"), "closure_base": None,
        })
        launched = engine_daemon.run([sys.executable, "-m", "cadgen.viewer", "--json", "--api-only", ident],
                                     cwd=self.project, env=self.env)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertEqual([row["id"] for row in json.loads(launched.stdout)["documents"]], [ident])
        status, shown = self.page(ident)
        self.assertEqual(status, 200, shown)
        self.assertEqual(self.cli("stop").returncode, 0)
        # The next daemon still opens the original snapshot; no migration cache/revision churn.
        engine_daemon.bootstrap(self.env)
        out = self.folder / "again.step"
        exported = self.cli("export", ident, str(out))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertEqual(self.file(ident).read_bytes(), original)
        self.assertEqual(self.record(ident), record)
        self.assertFalse(self.ran("cube"))

    def test_unsupported_or_failed_migration_keeps_cached_bytes_across_restarts(self) -> None:
        from OCP.Standard import Standard_GUID
        from OCP.TDataStd import TDataStd_AsciiString, TDataStd_NamedData
        from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        from OCP.collections import Sequence_TDF_Label
        from cadgen.engine import document

        fixture = Path(__file__).with_name("fixtures") / "xbf8_materials.xbf"
        for failure in ("unsupported", "migration"):
            with self.subTest(failure=failure):
                engine_daemon.bootstrap(self.env)
                doc = document.read_bytes(fixture.read_bytes())
                if failure == "unsupported":
                    TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(document.WRITER_GUID),
                                             TCollection_AsciiString("cadgen.engine xbf/99 (cadgen 99.0.0)"))
                    message = "unsupported document format xbf/99"
                else:
                    labels = Sequence_TDF_Label()
                    XCAFDoc_DocumentTool.MaterialTool_s(doc.Main()).GetMaterialLabels(labels)
                    TDataStd_NamedData.Set_s(labels.Value(1)).SetReal(
                        TCollection_ExtendedString("young_modulus"), float("nan"))
                    message = "young_modulus is not finite"
                original = document.to_bytes(doc)
                ident, record = self.legacy_cache(original)
                out = self.folder / "unsupported.step"
                for _ in range(2):
                    engine_daemon.bootstrap(self.env)
                    exported = self.cli("export", ident, str(out))
                    self.assertEqual(exported.returncode, 2, exported.stderr)
                    self.assertIn(message, exported.stderr)
                    self.assertFalse(out.exists())
                    self.assertEqual(self.file(ident).read_bytes(), original)
                    self.assertEqual(self.record(ident), record)
                    self.assertEqual(self.cli("stop").returncode, 0)
                self.assertFalse(self.ran("cube"))

    def test_a_genuine_old_cached_shape_opens_and_transfers_without_its_program(self) -> None:
        from cadgen.engine import api, export

        fixture = Path(__file__).with_name("fixtures") / "xbf8_materials.xbf"
        original = fixture.read_bytes()
        expected_volume = export.Source.read(fixture).shape().volume
        missing = self.project / "missing-hand-over.py"
        ident = model_id(missing, "legacy-shape")
        self.assertEqual(self.cli("stop").returncode, 0)
        held = Registry(self.state, self.cache)
        held.put({"id": ident, "kind": "shape", "root": str(self.project), "home": missing.name,
                  "program": missing.name, "entry": "legacy-shape", "namespace": str(self.project),
                  "name": "legacy-shape", "revision": "old-shape", "built": 1.0,
                  "cache": {"revision": "old-shape", "bytes": len(original)}})
        held.cache.write(f"documents/{ident}/document.xbf", original)
        record = self.record(ident)
        for _ in range(2):
            engine_daemon.bootstrap(self.env)
            with mock.patch.dict(os.environ, self.env, clear=True):
                handle = api.Document("legacy-shape", missing, {"id": ident}, self.project)
                self.assertAlmostEqual(handle.shape.volume, expected_volume, places=7)
            out = self.folder / "legacy-shape.step"
            exported = self.cli("export", ident, str(out))
            self.assertEqual(exported.returncode, 0, exported.stderr)
            self.assertGreater(out.stat().st_size, 0)
            self.assertEqual(self.page(ident)[0], 200)
            self.assertEqual(self.file(ident).read_bytes(), original)
            self.assertEqual(self.record(ident), record)
            self.assertFalse(missing.exists())
            self.assertEqual(self.cli("stop").returncode, 0)

    def test_failed_revisions_before_a_restart_leave_the_cache_to_take(self) -> None:
        self.use(self.folder / "state", self.folder / "cache", CADGEN_ENGINE_CACHE_IDLE="600")  # saved at the stop, as a person's is
        self.said()
        self.run_script("cube")
        self.run_script("cube")
        for broken in ("    return bd.Box(WIDTH, 2, 1", "    assert WIDTH < 0, 'too wide'\n    return bd.Box(WIDTH, 2, 1)",
                       "    return bd.fillet(bd.Box(WIDTH, 2, 1).edges(), radius=50)"):
            self.said(broken)
            failed = engine_daemon.run([sys.executable, "cube.py"], cwd=self.project, env=self.env)
            self.assertNotEqual(failed.returncode, 0, broken)
        self.said()
        self.run_script("cube")
        self.assertEqual(self.cli("stop").returncode, 0)
        engine_daemon.bootstrap(self.env)
        self.assert_taken()

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
        worker = daemon.Worker(script, {**os.environ, "PYTHONPATH": str(SRC), "PYTHONPYCACHEPREFIX": self.bytecode},
                               on_saved=lambda _worker, header, payload: saved.append((header, payload)))
        self.addCleanup(worker.stop)
        order = {"id": 1, "op": "build", "script": script, "functions": None, "cwd": str(self.project), "execution": worker.execution}
        self.assertIn("done", worker.build(order, lambda _message: None))
        worker.save(ident, script, "cube", "g1")
        answer = worker.build({**order, "id": 2}, lambda _message: None)  # queued behind the save
        self.assertTrue(all(report["ok"] for report in answer["done"]), answer)
        (header, payload), = await_(lambda: saved, "the save's answer")
        self.assertEqual((header["ident"], header["generation"], header.get("error")), (ident, "g1", None))
        self.assertTrue(document.read_bytes(payload), "the whole document's bytes")

    def test_a_stop_saves_a_document_built_in_its_last_idle_window(self) -> None:
        self.use(self.folder / "state", self.folder / "cache", CADGEN_ENGINE_CACHE_IDLE="600")
        ident = self.write("cube")
        self.run_script("cube")
        self.assertFalse(self.file(ident).exists(), "not idle yet")
        self.assertEqual(self.cli("stop").returncode, 0)
        engine_daemon.bootstrap(self.env)
        self.assertEqual(self.record(ident)["cache"]["revision"], self.record(ident)["revision"])
        self.assertTrue(self.file(ident).is_file())
        # The next engine's viewer opens it by its id, as it held it.
        launched = engine_daemon.run([sys.executable, "-m", "cadgen.viewer", "--json", "--api-only", ident],
                                     cwd=self.project, env=self.env)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertEqual([row["id"] for row in json.loads(launched.stdout)["documents"]], [ident])

    def test_every_document_stays_until_deleted_and_nothing_else_in_the_folder_is_touched(self) -> None:
        # Its workers go after each build, over a memory cap of 1 MB, and its memory budget is past at
        # once: every document leaves memory, and the cache keeps them all.
        self.use(self.folder / "state", self.folder / "cache", CADGEN_ENGINE_WORKER_RSS_MB="1",
                 CADGEN_ENGINE_MEMORY_MB="0.001")
        foreign = self.cache / "objects" / "ab" / "0.7-object"
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(b"a 0.7 store object")
        beside = self.cache / "index.db"
        beside.write_bytes(b"0.7")
        stamps = {path: path.stat().st_mtime_ns for path in (foreign, beside)}
        idents = [self.write(name) for name in ("first", "second", "third")]
        for name, ident in zip(("first", "second", "third"), idents):
            self.run_script(name)
            self.cached(ident)
        # Out of memory, each read again from the cache: its worker gone and the server's copy trimmed.
        held = lambda: [(row["state"], row.get("held")) for row in self.ask({"op": "status"})["models"]]  # noqa: E731
        await_(lambda: self.ask({"op": "status"})["workers"] == [] and held() == [("held", "disk")] * 3,
               "every document out of memory and held on disk alone")
        self.assertTrue(all(self.file(ident).is_file() for ident in idents), "nothing evicts a document")
        cache = self.ask({"op": "status"})["cache"]
        self.assertEqual(sorted(cache), ["bytes", "documents", "enabled", "failures", "idleSeconds", "root",
                                         "written"], "no cap, no evictions")
        self.assertEqual((cache["documents"], cache["root"]), (3, str(self.document_cache)))
        total = sum(self.file(ident).stat().st_size for ident in idents)
        from cadgen.engine.cli import _bytes

        self.assertIn(f"cache {self.document_cache}: 3 documents · {_bytes(total)}, kept until deleted\n", self.cli("status").stdout)
        exported = self.cli("export", idents[0], str(self.folder / "first.step"))
        self.assertEqual(exported.returncode, 0, exported.stderr)
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
        self.assertEqual((declared.read_bytes(), declared.stat().st_mtime_ns), written, "the declared file is the author's")
        self.assertEqual(sorted(os.listdir(self.document_cache / "documents")), [ident], "a file's document is its own file")
        self.assertEqual(meta["bytes"], self.file(ident).stat().st_size)

    def test_a_model_declaring_a_step_is_taken_by_its_key_after_a_restart_and_its_file_written_from_it(self) -> None:
        (self.project / "plate.py").write_text(textwrap.dedent(STEPPED.format(width=4)), encoding="utf-8")
        ident = model_id(self.project / "plate.py", "plate")
        self.assertIn("the body ran", self.run_script("plate").stderr)
        declared = self.project / "plate.step"
        first = declared.read_bytes()
        self.cached(ident)
        self.assertNotIn("files", self.record(ident), "nothing records which files a model wrote")
        self.assertEqual(self.cli("stop").returncode, 0)
        engine_daemon.bootstrap(self.env)
        # Unchanged after a restart: taken by its key, nothing run; its STEP is the document's export, as
        # `cadgen export` writes it of the document taken (OCCT's xbf read gives a -0. back for a 0.:
        # the first run after a restart may write it once, the same geometry).
        done = self.run_script("plate")
        self.assertIn("took plate.py::plate cold in", done.stdout)
        self.assertIn("the engine's cache holds the model's key", done.stdout)
        self.assertNotIn("the body ran", done.stderr)
        exported = self.folder / "exported.step"
        self.assertEqual(self.cli("export", ident, str(exported)).returncode, 0)
        taken = declared.read_bytes()
        self.assertEqual(taken, exported.read_bytes(), "exactly an export of the document")
        # Unchanged, it is compared and left as it is: its bytes and its time.
        stamp = declared.stat().st_mtime_ns
        done = self.run_script("plate")
        self.assertIn("took plate.py::plate warm in", done.stdout)
        self.assertEqual((declared.read_bytes(), declared.stat().st_mtime_ns), (taken, stamp))
        # Deleted: the next run writes it again from the document, and still runs nothing.
        declared.unlink()
        done = self.run_script("plate")
        self.assertIn("took plate.py::plate warm in", done.stdout)
        self.assertNotIn("the body ran", done.stderr)
        self.assertEqual(declared.read_bytes(), taken)
        # A key change runs the body.
        (self.project / "plate.py").write_text(textwrap.dedent(STEPPED.format(width=5)), encoding="utf-8")
        done = self.run_script("plate")
        self.assertIn("the body ran", done.stderr)
        self.assertNotEqual(declared.read_bytes(), first)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "a read-only folder is POSIX's, and refuses no one running as root")
    def test_with_its_cache_folder_read_only_the_engine_saves_nothing_and_does_everything_else(self) -> None:
        def scenario(tag: str, **extra: str) -> dict:
            if tag == "read-only":
                cache = self.folder / f"cache-{tag}"
                cache.mkdir()
                cache.chmod(stat.S_IRUSR | stat.S_IXUSR)
                self.addCleanup(cache.chmod, stat.S_IRWXU)
                self.use(self.folder / f"state-{tag}", cache, **extra)
            else:  # no folder can be made there at all: a file is in its place
                self.use(self.folder / f"state-{tag}", Path(engine_daemon.unwritable(self.folder / tag)), **extra)
            ident = self.write("cube")
            seen: dict = {"build": [line for line in self.run_script("cube").stdout.splitlines() if "id:" in line]}
            await_(lambda: self.ask({"op": "status"})["cache"]["failures"], "the idle save tried and failed")
            status, structure = self.page(ident)
            seen["page"] = (status, sorted(structure))
            seen["state"] = self.ask({"op": "state", "id": ident})
            out = self.folder / f"{tag}.xbf"
            seen["export"] = (self.cli("export", ident, str(out)).returncode, out.read_bytes())
            seen["inspect"] = self.cli("inspect", ident, "--query", "closure").stdout
            listed = self.ask({"op": "status"})
            seen["models"] = [(row["state"], row.get("held")) for row in listed["models"]]
            failures = listed["cache"]["failures"]
            self.assertEqual(self.cli("stop").returncode, 0)
            engine_daemon.bootstrap(self.env)
            (self.project / "cube.ran").unlink()
            again = self.cli("inspect", ident)
            seen["restart"] = (again.returncode, again.stderr)
            seen["restart state"] = self.ask({"op": "state", "id": ident})
            seen["restart page"] = self.page(ident)
            seen["ran"] = self.ran("cube")
            self.assertEqual(self.cli("stop").returncode, 0)
            engine_daemon.bootstrap(self.env)
            seen = json.loads(json.dumps(seen, default=lambda value: value.hex()).replace(str(self.state), "STATE"))
            return seen, failures, list(self.cache.iterdir()) if self.cache.is_dir() else []

        read_only, failures, left = scenario("read-only")
        self.assertTrue(failures, "the failed save is listed")
        self.assertEqual(left, [], "and nothing is cached")
        unwritable, failures, _left = scenario("unwritable")
        self.assertTrue(failures, "the failed save is listed there too")
        self.assertEqual(read_only, unwritable, "every verb, every state, every message alike: nothing saved")
        self.assertEqual(read_only["restart"][0], 2, "after a restart it is not held: its command is said")


class KeptTest(unittest.TestCase):
    """The cache on its own: it has no cap, and keeps every file it writes, a shape handed over's as a
    model's; a document whose file is gone says to hand it over again."""

    def test_no_cap_every_file_written_stays(self) -> None:
        from cadgen.engine import cache as engine_cache

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-kept-")))
        self.addCleanup(shutil.rmtree, folder, True)
        held = Registry(folder / "state", folder / "cache")

        class Models:
            def registry(self) -> Registry:
                return held

            def row(self, _ident: str) -> None:
                return None

        names = ["a_shape", "a_model", "b_shape", "b_model"]
        idents = {name: model_id(folder / f"{name}.py", name) for name in names}
        for name, ident in idents.items():
            held.put({"id": ident, "kind": "shape" if name.endswith("shape") else "model",
                      "root": str(folder), "home": f"{name}.py", "entry": name, "revision": "r1"})
        self.assertFalse(hasattr(engine_cache, "cap") or hasattr(engine_cache, "CACHE_GB"), "no cap to set")
        first, second = engine_cache.Cache(Models()), engine_cache.Cache(Models())
        for name in names[:3]:
            first._write(idents[name], "r1", b"x" * 1000)
        second._write(idents["b_model"], "r1", b"x" * 1000)  # an engine started after the first three
        kept = {name for name, ident in idents.items() if (folder / "cache" / "documents" / ident / "document.xbf").is_file()}
        self.assertEqual(kept, set(names), "every file stays")
        self.assertTrue(all(held.get(ident)["cache"]["bytes"] == 1000 for ident in idents.values()))
        status = second.status()
        self.assertEqual((status["documents"], status["bytes"]), (4, 4000))
        self.assertNotIn("capBytes", status)
        self.assertNotIn("evictions", status)

    def test_rebuilding_unreadable_bytes_preserves_them_until_a_successful_replacement(self) -> None:
        from cadgen.engine.cache import Cache

        with tempfile.TemporaryDirectory(prefix="engine-replace-") as folder:
            root = Path(folder)
            held = Registry(root / "state", root / "cache")
            ident = model_id(root / "cube.py", "cube")
            held.put({"id": ident, "kind": "model", "root": str(root), "home": "cube.py",
                      "entry": "cube", "revision": "same-key"})
            kept = Cache(mock.Mock(registry=lambda: held))
            kept._write(ident, "same-key", b"recoverable original bytes")
            original = held.cache.read(kept.inside(ident)), held.get(ident)
            kept.refresh(ident)
            with mock.patch.object(held.cache, "write", side_effect=OSError("disk unavailable")):
                with self.assertRaisesRegex(OSError, "disk unavailable"):
                    kept._write(ident, "same-key", b"rebuilt complete document")
            self.assertEqual((held.cache.read(kept.inside(ident)), held.get(ident)), original)
            self.assertFalse(kept.current(ident, "same-key"))
            kept._write(ident, "same-key", b"rebuilt complete document")
            self.assertEqual(held.cache.read(kept.inside(ident)), b"rebuilt complete document")
            self.assertTrue(kept.current(ident, "same-key"))

    def test_a_document_at_the_cache_s_revision_is_never_written_again(self) -> None:
        from cadgen.engine import cache as engine_cache

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-once-")))
        self.addCleanup(shutil.rmtree, folder, True)
        held = Registry(folder / "state", folder / "cache")
        ident = model_id(folder / "cube.py", "cube")
        held.put({"id": ident, "kind": "model", "root": str(folder), "home": "cube.py", "entry": "cube", "revision": "r1"})

        class Models:
            def registry(self) -> Registry:
                return held

            def row(self, _ident: str) -> dict:
                return {"revision": "r1", "worker": None, "version": "g2"}

            def held_bytes(self, _ident: str, _version: str) -> bytes:
                raise AssertionError("an unchanged document's bytes are never taken")

        kept = engine_cache.Cache(Models())
        kept._write(ident, "r1", b"x" * 1000)
        path = folder / "cache" / "documents" / ident / "document.xbf"
        stamps = (path.stat().st_mtime_ns, held.get(ident))
        kept._due(ident)  # idle again, unchanged
        kept.keep(ident, "r1", b"y" * 10)  # the drain's bytes, unchanged
        self.assertEqual((list(kept.writes), kept.written), ([], 1))
        self.assertEqual((path.stat().st_mtime_ns, held.get(ident)), stamps, "the file and its record as they were")

    def test_a_shape_taken_up_after_a_restart_and_unsaved_names_the_program_that_handed_it_over(self) -> None:
        from cadgen.engine import registry as registering
        from cadgen.engine.models import Models as Book

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-shape-")))
        self.addCleanup(shutil.rmtree, folder, True)
        held = Registry(folder / "state", folder / "cache")
        ident = model_id(folder / "hand.py", "crate")
        words = Book.shown(str(folder / "hand.py"))
        held.put({"id": ident, "kind": "shape", "root": str(folder), "home": "hand.py", "program": "hand.py",
                  "entry": "crate", "revision": "h1", "built": 1.0})
        held.cache.write(f"documents/{ident}/document.xbf", b"x" * 10)
        held.update(ident, lambda found: {**found, "cache": {"revision": "h1", "bytes": 10}})
        daemon = mock.Mock(server=None)
        with mock.patch.object(registering, "FACTORY", lambda: held):
            book = Book(daemon)
            book.adopt(ident)  # a restart: taken up from its record, its cache file at its revision
            self.assertEqual(book.state(ident), "held")
            held.cache.remove(f"documents/{ident}")  # deleted by hand outside the engine
            self.assertIsNone(book.cache.read(ident))  # the next read observes the missing file
            found = book.rebuild(ident)
        self.assertEqual((found["state"], found["rebuild"]), ("unsaved", None))
        self.assertIn(words, found["error"], "the words of the program its record names, not a Python session's")


if __name__ == "__main__":
    unittest.main()
