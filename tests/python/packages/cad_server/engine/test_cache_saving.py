"""The engine's document cache as it is written: a model document idle a moment is saved once per
revision in the cache folder (its record, in the state folder, says so), a stop saves one built in its
last idle window, and a build that arrives during a save waits for it; a run that changes nothing
takes the document, a model's declared files untouched or written from it, and failed revisions before
a restart leave it to take. On a class engine of the file's own (``cache_fixtures.CacheCase``), with an engine,
a state and a cache folder of its own (``CAD_ENGINE_DIR``, ``CAD_STATE_DIR``, ``CAD_CACHE_DIR``)."""

from __future__ import annotations

import json
import os
import sys
import textwrap
import unittest

from tests.python.support import cache_fixtures, engine_daemon
from tests.python.support.cache_fixtures import SRC, await_

from cad.engine.ids import file_id, model_id

# A model declaring a STEP and no xbf, whose body says on stderr that it ran.
STEPPED = """
import sys
import build123d as bd
from cad.engine import step


@step("plate.step")
def plate():
    print("the body ran", file=sys.stderr)
    return bd.Box({width}, 3, 1)


if __name__ == "__main__":
    plate()
"""

DECLARED = """
import build123d as bd
from cad.engine import xbf


@xbf("XBF/plate.xbf")
def plate():
    return bd.Box(4, 3, 1)


if __name__ == "__main__":
    plate()
"""


class CacheSavingTest(cache_fixtures.CacheCase):
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
        self.assertEqual(sorted(os.listdir(self.state / "documents" / ident)), ["document.json"],
                         "the bytes are the cache folder's, never the state folder's")
        compiled = [path for path in (self.cache / "pycache").glob("*/**/build123d/__init__.*.pyc")  # the prefix mirrors its path
                    if path.parent.parent.name != "cad"]  # build123d's own, not the library's integration of it
        self.assertEqual(len(compiled), 1, "the worker's libraries' bytecode, in the engine's folder")
        self.assertEqual(list(self.project.rglob("*.pyc")), [], "none beside the model")
        self.assertEqual(self.ask({"op": "status"})["cache"]["written"], written + 1)

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
        request = urllib.request.Request(f"{view.scheme}://{view.netloc}/api/v1/documents{view.path}/version{wait}",
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

    def test_failed_revisions_before_a_restart_leave_the_cache_to_take(self) -> None:
        self.use(self.folder / "state", self.folder / "cache", CAD_ENGINE_CACHE_IDLE="600")  # saved at the stop, as a person's is
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
        from cad_server.engine.services import WORKER
        from cad_server.engine.supervisor import Process
        from cad.engine import document

        ident = self.write("cube")
        script = str(self.project / "cube.py")
        saved: list[tuple[dict, bytes]] = []
        worker = Process.start(WORKER, script, script,
                               {**os.environ, "PYTHONPATH": str(SRC), "PYTHONPYCACHEPREFIX": self.bytecode},
                               on_event={"saved": lambda _worker, header, payload: saved.append((header, payload))})
        self.addCleanup(worker.stop)
        order = {"id": 1, "op": "build", "script": script, "functions": None, "cwd": str(self.project)}
        self.assertIn("done", worker.request(order, lambda _message: None))
        worker.tell({"op": "save", "ident": ident, "script": script, "name": "cube", "generation": "g1"})
        answer = worker.request({**order, "id": 2}, lambda _message: None)  # queued behind the save
        self.assertTrue(all(report["ok"] for report in answer["done"]), answer)
        (header, payload), = await_(lambda: saved, "the save's answer")
        self.assertEqual((header["ident"], header["generation"], header.get("error")), (ident, "g1", None))
        self.assertTrue(document.read_bytes(payload), "the whole document's bytes")

    def test_a_stop_saves_a_document_built_in_its_last_idle_window(self) -> None:
        self.use(self.folder / "state", self.folder / "cache", CAD_ENGINE_CACHE_IDLE="600")
        ident = self.write("cube")
        self.run_script("cube")
        self.assertFalse(self.file(ident).exists(), "not idle yet")
        self.assertEqual(self.cli("stop").returncode, 0)
        self.assertEqual(self.record(ident)["cache"]["revision"], self.record(ident)["revision"])
        self.assertTrue(self.file(ident).is_file())
        # The next engine's viewer opens it by its id, as it held it.
        launched = engine_daemon.run([sys.executable, "-m", "cad_server.viewer", "--json", "--api-only", ident],
                                     cwd=self.project, env=self.env)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertEqual([row["id"] for row in json.loads(launched.stdout)["documents"]], [ident])

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
        self.assertEqual(sorted(os.listdir(self.cache / "documents")), [ident], "a file's document is its own file")
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
        # Unchanged after a restart: taken by its key, nothing run; its STEP is the document's export, as
        # `cad <type> export` writes it of the document taken (OCCT's xbf read gives a -0. back for a 0.:
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


if __name__ == "__main__":
    unittest.main()
