"""A model's store is its ``.xbf``: a build adds the file to the library, and writes no record and no copy of
the document anywhere; a restarted engine answers every verb of a model from its ``.xbf`` -- page, export, snapshot,
inspect -- with nothing run, and finds an id's file from the library or a project's folder alone; an unchanged run
after a restart is taken from the file's own key, whoever wrote the file last, and one that does not read is built
and written again; a function with a file decorator alone writes that file alone, is no document, and says each run that a restart builds it again. On a
class engine of the file's own (``store_fixtures.StoreCase``), with an engine, a state and a cache folder of its own
(``CAD_ENGINE_DIR``, ``CAD_STATE_DIR``, ``CAD_CACHE_DIR``)."""

from __future__ import annotations

import json
import sys
import shutil
import textwrap
import unittest
import urllib.error
import urllib.request

from tests.python.support import engine_daemon, opengl, store_fixtures
from tests.python.support.store_fixtures import get

from cad.engine.ids import derived_id, file_id

# A function declaring a STEP and no xbf, whose body says on stderr that it ran.
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


class XbfStoreTest(store_fixtures.StoreCase):
    def assert_taken(self, name: str = "cube") -> None:
        """A run of ``<name>.py`` a fresh worker took from its ``.xbf``: no body ran."""
        done = self.run_script(name)
        self.assertIn(f"took {name}.py::{name} cold in", done.stdout)
        self.assertIn("its .xbf holds the model's key, 1 body loaded, nothing ran", done.stdout)
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

    def test_a_build_adds_its_xbf_to_the_library_and_writes_no_record_and_no_copy(self) -> None:
        ident = self.write("cube")
        self.assertEqual(ident, file_id(self.xbf("cube")), "a model's id is its .xbf's")
        done = self.run_script("cube")
        self.assertIn(f"id: {ident}", done.stdout)
        entry = self.entry(ident)
        self.assertEqual((set(entry), entry["path"]), ({"path", "created"}, str(self.xbf("cube"))))
        self.run_script("cube")
        self.assertEqual(self.entry(ident), entry, "known once: a later run writes nothing")
        self.assertFalse((self.state / "documents").exists(), "no record of a document")
        self.assertEqual(self.copies(), [], "the store is the file: no copy in the cache folder")
        compiled = [path for path in (self.cache / "pycache").glob("*/**/build123d/__init__.*.pyc")  # the prefix mirrors its path
                    if path.parent.parent.name != "cad"]  # build123d's own, not the library's integration of it
        self.assertEqual(len(compiled), 1, "the worker's libraries' bytecode, in the engine's folder")
        self.assertEqual(list(self.project.rglob("*.pyc")), [], "none beside the model")
        self.assertNotIn("cache", self.ask({"op": "status"}), "no document cache to say")

    def test_a_restart_answers_every_verb_from_the_xbf_and_an_unchanged_run_is_taken_from_it(self) -> None:
        ident = self.said()
        self.assertIn("the body ran", self.run_script("cube").stderr)
        live = {kind: self.folder / f"live.{kind}" for kind in ("xbf", "glb")}
        self.assertEqual(self.cli("export", ident, *map(str, live.values())).returncode, 0)
        self.assertEqual(self.cli("stop").returncode, 0)

        self.start()  # the engine afresh: no worker holds it, its .xbf is the document
        inspected = self.cli("inspect", ident, "--json")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["closure"]["source"]["function"], "cube")
        self.assertEqual(json.loads(inspected.stdout)["summary"]["state"],
                         {"state": "file", "path": str(self.xbf("cube"))})
        cold = {kind: self.folder / f"cold.{kind}" for kind in ("xbf", "glb")}
        exported = self.cli("export", ident, *map(str, cold.values()))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        for kind in cold:
            self.assertEqual(cold[kind].read_bytes(), live[kind].read_bytes(), f"the {kind} is the live export's")
        from cad.engine.render import context

        if opengl.draws(context.available(), "the cold snapshot is drawn by OCCT"):
            snapped = self.cli("snapshot", ident, str(self.folder / "cold.png"))
            self.assertEqual(snapped.returncode, 0, snapped.stderr)
            self.assertGreater((self.folder / "cold.png").stat().st_size, 0)
        status, structure = self.page(ident)
        self.assertEqual(status, 200, structure)
        self.assertEqual(structure["closure"]["source"]["function"], "cube")
        self.assertEqual(self.ask({"op": "state", "id": ident}), {"ok": True, "state": "held"})
        # An unchanged run is taken from the file's own key, and writes nothing.
        before = (self.xbf("cube").read_bytes(), self.xbf("cube").stat().st_mtime_ns, self.entry(ident))
        self.assert_taken()
        self.assertEqual((self.xbf("cube").read_bytes(), self.xbf("cube").stat().st_mtime_ns, self.entry(ident)), before)
        self.assertEqual(self.copies(), [])

    def test_an_xbf_that_does_not_read_is_built_again_and_one_whose_key_holds_is_taken(self) -> None:
        ident = self.said()
        self.run_script("cube")
        built = self.xbf("cube").read_bytes()
        self.assertEqual(self.cli("stop").returncode, 0)
        self.start()
        # Broken in place: its head shows the model's key, but its bytes no longer read as the document; the run
        # builds it, and writes it whole.
        broken = bytearray(built)
        broken[-1024:] = bytes(1024)
        self.xbf("cube").write_bytes(bytes(broken))
        self.assertIn("the body ran", self.run_script("cube").stderr)
        self.assertEqual(self.xbf("cube").read_bytes(), built, "written again from the build")
        # Written by another hand, its key the model's still: the file is the model, taken, and left as it is.
        self.assertEqual(self.cli("stop").returncode, 0)
        self.start()
        with self.xbf("cube").open("ab") as edited:
            edited.write(b"by hand")
        self.assert_taken()
        self.assertEqual(self.xbf("cube").read_bytes(), built + b"by hand")
        # Gone: its id names nothing, and its run writes it again.
        self.assertEqual(self.cli("stop").returncode, 0)
        self.start()
        self.xbf("cube").unlink()
        self.assertEqual(self.ask({"op": "state", "id": ident}),
                         {"ok": True, "state": None, "error": f"no document {ident} is held"})
        self.assertIn("the body ran", self.run_script("cube").stderr)
        self.assertTrue(self.xbf("cube").is_file())

    def test_an_id_answers_after_a_restart_from_the_library_or_a_project_folder_alone(self) -> None:
        # Folders of its own: this test's project is the only one, and its Recents hold what it built.
        self.use(self.folder / "state", self.folder / "cache")
        self.start()
        built = self.said()
        self.run_script("cube")
        work = self.folder / "work" / "parts"
        work.mkdir(parents=True)
        dropped = work / "dropped.xbf"
        shutil.copyfile(self.xbf("cube"), dropped)  # a file another program drops in a project: nobody opens it
        launched = engine_daemon.run([sys.executable, "-m", "cad_server.viewer", "--json", "--api-only",
                                      str(work.parent)], cwd=self.project, env=self.env)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertEqual(self.cli("stop").returncode, 0)
        self.start()

        def envelope(ident: str) -> tuple[int, dict]:
            served = self.ask({"op": "http"})
            return get(f"{served['url']}/api/v1/documents/{ident}", served["token"])

        # A project's file nobody opened: its folder knows it, for a verb before anything is served as for a page.
        # A model outside every project: the library knows its .xbf.
        dropped_id = file_id(self.folder / "work" / "parts" / "dropped.xbf")
        self.assertEqual(self.cli("inspect", dropped_id).returncode, 0)
        self.assertEqual(self.cli("inspect", built).returncode, 0)
        status, found = envelope(built)
        self.assertEqual((status, found["source"]["path"], found["entry"]["project"]), (200, self.xbf("cube").as_posix(), None))
        status, found = envelope(dropped_id)
        self.assertEqual((status, found["source"]["path"], found["entry"]["project"]["folder"]), (200, dropped.as_posix(), "parts"))
        self.assertEqual(self.entry(dropped_id), None, "found, with no entry made for it")
        self.assertFalse((self.state / "documents").exists(), "and no record of either")
        # An unchanged run after the restart is taken from its file by its key.
        self.assert_taken()
        # A file that is gone names nothing: a 404, with no state and no command.
        dropped.unlink()
        status, gone = envelope(file_id(dropped))
        self.assertEqual((status, gone), (404, {
            "error": f"no document {file_id(dropped)} is held",
            "hint": "run the model's script again, or open the file from where it is now"}))
        refused = self.cli("inspect", file_id(dropped))
        self.assertEqual((refused.returncode, f"no document {file_id(dropped)} is held" in refused.stderr), (2, True))
        self.assertEqual(envelope(derived_id(self.project / "cube.py", "cube"))[0], 404,
                         "an id of an earlier release's formula names nothing")

    def test_a_live_model_whose_xbf_is_gone_names_nothing_until_its_script_runs_again(self) -> None:
        ident = self.write("cube")
        self.run_script("cube")
        self.assertEqual(self.ask({"op": "state", "id": ident}), {"ok": True, "state": "live"})
        served = self.ask({"op": "http"})

        def answer(method: str, route: str, body: dict | None = None) -> tuple[int, dict]:
            request = urllib.request.Request(f"{served['url']}{route}", method=method,
                                             data=json.dumps(body).encode() if body is not None else None,
                                             headers={"Authorization": "Bearer " + served["token"],
                                                      "x-cad-viewer": "1", "content-type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read())

        missing = f"no document {ident} is held"
        # Its worker holds its build still; its file is gone, so it is gone: the version first, which no read before
        # it has looked at the file by.
        self.xbf("cube").unlink()
        self.assertEqual(answer("GET", f"/api/v1/documents/{ident}/version"),
                         (404, {"error": missing, "hint": "check the path or id"}))
        self.assertEqual(answer("GET", f"/api/v1/documents/{ident}"), (404, {
            "error": missing, "hint": "run the model's script again, or open the file from where it is now"}))
        self.assertEqual(self.page(ident)[0], 404)
        self.assertEqual(answer("PATCH", "/api/v1/documents", {"action": "open", "path": ident}),
                         (400, {"error": missing, "hint": "fix the request as the error says"}))
        refused = self.cli("inspect", ident)
        self.assertEqual((refused.returncode, missing in refused.stderr), (2, True))
        self.assertEqual(self.ask({"op": "state", "id": ident}), {"ok": True, "state": None, "error": missing})
        self.assertNotIn(ident, [row["id"] for row in self.ask({"op": "status"}).get("models") or []])
        # Its script's next run writes the file again, and the document is back.
        self.run_script("cube")
        self.assertTrue(self.xbf("cube").is_file())
        self.assertEqual(self.ask({"op": "state", "id": ident}), {"ok": True, "state": "live"})
        self.assertEqual(answer("GET", f"/api/v1/documents/{ident}/version")[0], 200)
        self.assertEqual(answer("GET", f"/api/v1/documents/{ident}")[0], 200)
        self.assertEqual(self.page(ident)[0], 200)
        self.assertEqual(answer("PATCH", "/api/v1/documents", {"action": "open", "path": ident})[0], 200)
        self.assertEqual(self.cli("inspect", ident).returncode, 0)

    def test_a_live_model_whose_xbf_another_process_rewrote_is_that_file_until_its_script_runs_again(self) -> None:
        ident = self.write("cube")
        ran = self.run_script("cube")
        self.write("wide", width=7.0)
        self.run_script("wide")
        generation = self.generation(ran.stdout)

        def inspected(*options: str, source: str = str(self.xbf("cube"))) -> dict:
            done = self.cli("inspect", source, *options, "--json")
            self.assertEqual(done.returncode, 0, done.stderr)
            return json.loads(done.stdout)

        def answered() -> tuple[str, list, list]:
            """Its state and size by its path, and the size of what an export by its id writes."""
            summary = inspected()["summary"]
            done = self.cli("export", ident, "exported.step")
            self.assertEqual(done.returncode, 0, done.stderr)
            exported = inspected(source=str(self.project / "exported.step"))["summary"]
            return summary["state"]["state"], summary["bounds"]["size"], exported["bounds"]["size"]

        self.assertEqual(answered(), ("live", [3.0, 2.0, 1.0], [3.0, 2.0, 1.0]))
        # Another model's .xbf copied over it in place, as git, a sync folder or cp writes it: the file is the
        # document at once, for every verb, by its path and by its id, and a page on it follows to the file.
        shutil.copyfile(self.xbf("wide"), self.xbf("cube"))
        self.assertNotEqual(self.generation(ran.stdout, after=generation), generation)
        self.assertEqual(answered(), ("file", [7.0, 2.0, 1.0], [7.0, 2.0, 1.0]))
        self.assertEqual(self.ask({"op": "state", "id": ident}), {"ok": True, "state": "held"})
        self.assertEqual(self.page(ident)[1]["prototypes"][0]["key"], inspected("wide/face 1")["key"])
        # Its script's next run writes the file again, and holds it.
        self.run_script("cube")
        self.assertEqual(answered(), ("live", [3.0, 2.0, 1.0], [3.0, 2.0, 1.0]))

    def test_an_xbf_that_is_no_document_cad_wrote_is_refused_in_one_line_by_every_verb(self) -> None:
        self.write("cube")
        self.run_script("cube")
        whole = self.xbf("cube").read_bytes()
        for name, data, why in (("garbage", b"garbage", "another file"), ("cut", whole[:len(whole) // 2], "cut short")):
            path = self.project / f"{name}.xbf"
            path.write_bytes(data)
            said = f"{path} is no .xbf cad wrote: it is {why}"
            for verb, *rest in (("inspect",), ("export", "out.step"), ("snapshot", "out.png")):
                with self.subTest(name=name, verb=verb):
                    refused = self.cli(verb, str(path), *rest)
                    lines = refused.stderr.strip().splitlines()
                    self.assertEqual((refused.returncode, len(lines), lines[-1].endswith(f" {verb}: {said}")),
                                     (2, 1, True), refused.stderr)
            refused = self.cli("export", str(path), "out.step", "--json")
            self.assertEqual((refused.returncode, json.loads(refused.stdout)),
                             (2, {"ok": False, "error": said, "reason": "invalid_argument"}))
            self.assertEqual(self.cli("inspect", str(self.xbf("cube"))).returncode, 0, "the engine reads on")

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

    def test_failed_revisions_before_a_restart_leave_the_xbf_to_take(self) -> None:
        self.said()
        self.run_script("cube")
        for broken in ("    return bd.Box(WIDTH, 2, 1", "    assert WIDTH < 0, 'too wide'\n    return bd.Box(WIDTH, 2, 1)",
                       "    return bd.fillet(bd.Box(WIDTH, 2, 1).edges(), radius=50)"):
            self.said(broken)
            failed = engine_daemon.run([sys.executable, "cube.py"], cwd=self.project, env=self.env)
            self.assertNotEqual(failed.returncode, 0, broken)
        self.said()
        self.run_script("cube")
        self.assertEqual(self.cli("stop").returncode, 0)
        self.start()
        self.assert_taken()

    def test_a_step_alone_writes_its_file_alone_says_so_and_builds_again_after_a_restart(self) -> None:
        (self.project / "plate.py").write_text(textwrap.dedent(STEPPED.format(width=4)), encoding="utf-8")
        declared = self.project / "plate.step"
        warning = ("warning: plate saves no .xbf (no @xbf): once the CAD server restarts, its next run builds it again "
                   "from scratch; add @xbf to save it")
        done = self.run_script("plate")
        self.assertIn("the body ran", done.stderr)
        self.assertIn(warning, done.stdout)
        ident = file_id(declared)
        self.assertIn(f"id: {ident}", done.stdout, "its id is its file's")
        self.assertIn(f"/{ident}?", done.stdout, "its page is its file's")
        self.assertEqual(sorted(path.name for path in self.project.iterdir()), ["plate.py", "plate.step"], "no .xbf")
        self.assertIsNone(self.entry(ident), "no document: nothing of it in the library")
        # Warm: taken from the worker's memory, nothing ran, and said again.
        warm = self.run_script("plate")
        self.assertIn("took plate.py::plate warm in", warm.stdout)
        self.assertIn(warning, warm.stdout)
        # After a restart, built from nothing: no .xbf to take it from.
        self.assertEqual(self.cli("stop").returncode, 0)
        self.start()
        cold = self.run_script("plate")
        self.assertIn("the body ran", cold.stderr)
        self.assertIn(warning, cold.stdout)
        # With @xbf, no warning.
        self.write("cube")
        self.assertNotIn("warning:", self.run_script("cube").stdout)


if __name__ == "__main__":
    unittest.main()
