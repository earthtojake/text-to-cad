"""Identity beyond the id's formula: a model's id is its ``.xbf``'s, and a record from before -- its id its script's
and function's, or its folder's and explicit name's -- is carried to that id, what a person did with its card with
it, its old id kept as an alias that still answers; a run re-attaches a moved script's record by its name and bytes in
one pass of the registry, a copy never; a move stopped part way is finished; two models that write one file share its
id, nothing refused; and the startup migration moves a ``key::`` record and a record that names its ``.xbf``, fills
what is missing, skips what does not read and is quiet when there is nothing to do. The run's own paths through a
real daemon in private engine, state and cache folders: a moved script is taken warm from its moved ``.xbf``."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cad.engine.identity import carry, fingerprint, former, migrate, reattach, repoint
from cad.engine.ids import NAMESPACE, canonical, derived_id, file_id
from tests.python.support.ids import model_id
from cad_server.engine.registry import Folder, Registry
from tests.python.support import engine_daemon

SCRIPT = '''import build123d as bd
from cad import model
@model{options}
def part():
    return bd.Box(2, 3, 4)
if __name__ == "__main__":
    part()
'''


class Fixture(unittest.TestCase):
    def setUp(self):
        self.folder = Path(canonical(tempfile.mkdtemp(prefix="identity-")))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.registry = Registry(self.folder / "state", self.folder / "cache")

    def script(self, relative: str, text: str) -> Path:
        path = self.folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def record(self, script: Path, entry: str = "part", name: str | None = None, **extra) -> str:
        ident = model_id(script, entry, name)
        self.registry.put({"id": ident, "kind": "model", "root": str(script.parent), "home": script.name,
                           "entry": entry, "namespace": str(script.parent), "name": name or entry, "built": 1,
                           "saved": f"{name or entry}.xbf", **extra})
        return ident


class FormerTest(Fixture):
    def test_the_id_before_is_the_formula_over_a_script_and_its_function_or_a_folder_and_its_name(self):
        script = self.folder / "parts.py"
        self.assertEqual(former({"script": str(script), "name": "cube"}),
                         str(uuid.uuid5(NAMESPACE, canonical(script) + "::cube")))
        self.assertEqual(former({"script": str(script), "name": "cube", "explicit_name": "arm"}),
                         derived_id(self.folder, "arm"))
        self.assertEqual(former({"kind": "shape", "script": str(self.folder), "name": "crate"}),
                         derived_id(self.folder, "crate"))
        self.assertNotEqual(former({"script": str(script), "name": "cube"}), model_id(script, "cube"))

    def test_carry_keeps_the_first_creation_the_last_opening_a_pin_a_picture_and_every_id_as_an_alias(self):
        found = carry({"id": "n", "created": 5, "opened": 1},
                      {"id": "11111111-1111-5111-8111-111111111111", "created": 2, "opened": 9, "pinned": True,
                       "preview": {"thumbnail": "kept.png"}, "aliases": ["22222222-2222-5222-8222-222222222222"]}, None)
        self.assertEqual(found, {"id": "n", "created": 2, "opened": 9, "pinned": True, "preview": {"thumbnail": "kept.png"},
                                 "aliases": ["22222222-2222-5222-8222-222222222222",
                                             "11111111-1111-5111-8111-111111111111"]})


class ReattachmentTest(Fixture):
    def test_two_missing_candidates_choose_the_latest_and_keep_the_other(self):
        source = self.script("new/part.py", SCRIPT.format(options=""))
        for at, built in enumerate((2, 7)):
            script = self.folder / f"gone{at}" / "part.py"
            self.record(script, fingerprint=fingerprint(source), built=built, created=1,
                        preview={"thumbnail": "kept.png"})
        new = model_id(source, "part")
        lines = []
        moved = reattach(self.registry, [{"script": str(source), "name": "part", "fingerprint": fingerprint(source),
                                          "xbf": str(source.parent / "part.xbf")}], log=lines.append)
        old = model_id(self.folder / "gone1" / "part.py", "part")
        self.assertEqual(moved, [(old, new)])
        self.assertIn("most recently built of 2 candidates", lines[0])
        self.assertEqual(len(self.registry.list()), 2)
        self.assertEqual(self.registry.get(new)["preview"], {"thumbnail": "kept.png"})
        self.assertEqual(self.registry.get(new)["created"], 1)
        self.assertEqual((self.registry.get(new)["saved"], self.registry.get(new)["aliases"]), ("part.xbf", [old]))
        self.assertEqual(self.registry.resolve(old), new, "its old id answers as the document it moved to")

    def test_one_pass_of_the_registry_serves_every_model_and_parses_no_record_it_cannot_adopt(self):
        for at in range(40):
            self.record(self.folder / f"gone{at}" / "part.py", fingerprint=f"{at:064x}")
        sources = [{"script": str(self.folder / "new" / f"m{at}.py"), "name": "part", "fingerprint": "f" * 64,
                    "xbf": str(self.folder / "new" / f"m{at}.xbf")} for at in range(3)]
        with mock.patch.object(Folder, "names", autospec=True, side_effect=Folder.names) as listed, \
                mock.patch.object(Registry, "get", autospec=True, side_effect=Registry.get) as parsed:
            self.assertEqual(reattach(self.registry, sources), [])
        self.assertEqual(listed.call_count, 1, "one pass for all of them")
        self.assertEqual(parsed.call_count, 3, "each model's own id, and no record of the pass")

    def test_a_record_of_the_same_script_under_its_id_before_is_carried_and_a_copy_never(self):
        real = self.script("real/part.py", SCRIPT.format(options=""))
        source = {"script": str(real), "name": "part", "fingerprint": fingerprint(real),
                  "xbf": str(real.parent / "part.xbf")}
        before = former(source)
        self.registry.put({"id": before, "kind": "model", "root": str(real.parent), "home": "part.py", "entry": "part",
                           "name": "part", "built": 1, "fingerprint": source["fingerprint"], "pinned": True})
        self.assertEqual(reattach(self.registry, [source]), [(before, model_id(real, "part"))])
        self.assertIsNone(self.registry.get(before))
        self.assertEqual(self.registry.get(model_id(real, "part"))["pinned"], True)
        copy = self.script("copy/part.py", SCRIPT.format(options=""))
        kept = self.registry.get(model_id(real, "part"))
        self.assertEqual(reattach(self.registry, [{**source, "script": str(copy), "xbf": str(copy.parent / "part.xbf")}]),
                         [], "the original is there")
        self.assertEqual(self.registry.get(model_id(real, "part")), kept)

    def test_a_move_carries_what_the_file_s_record_held_and_one_stopped_part_way_is_finished(self):
        script = self.script("part.py", SCRIPT.format(options=""))
        old = self.record(self.folder / "gone" / "part.py", fingerprint="a" * 64, created=1)
        record = self.registry.get(old)
        new = model_id(script, "part")
        # A page opened its .xbf before: the file's record, its opening and its picture.
        self.registry.put({"id": new, "kind": "file", "root": str(self.folder), "home": "part.xbf", "opened": 7,
                           "created": 4, "preview": {"thumbnail": "file.png"}})
        found = {**record, "id": new, "root": str(self.folder), "home": "part.py"}
        repoint(self.registry, record, found)
        self.assertIsNone(self.registry.get(old))
        moved = self.registry.get(new)
        self.assertEqual((moved["kind"], moved["created"], moved["opened"], moved["preview"], moved["aliases"]),
                         ("model", 1, 7, {"thumbnail": "file.png"}, [old]))
        # Stopped after the new record landed: the old one is still there, and the move is finished.
        self.registry.put(record)
        repoint(self.registry, record, found)
        self.assertIsNone(self.registry.get(old))
        self.assertEqual(self.registry.get(new)["aliases"], [old])


class BuildAsksTest(Fixture):
    def test_a_build_asks_once_and_only_for_models_with_nothing_to_take_up(self):
        from cad.engine import build

        script = self.folder / "parts.py"
        moved_away = self.folder / "before.py"

        def model(name, written=False):
            found = SimpleNamespace(script=script, name=name, explicit_name=None, id=model_id(script, name),
                                    xbf=script.parent / f"{name}.xbf", source={"script": str(script), "name": name})
            if written:
                self.addCleanup(build._WRITTEN.pop, f"{script}::{name}", None)
                build._WRITTEN[f"{script}::{name}"] = object()
            return found

        held = model("held", written=True)
        own = model("own")
        self.registry.put({"id": own.id, "kind": "model", "root": str(self.folder), "home": "parts.py", "entry": "own"})
        new = model("new")
        away = model("away")
        self.registry.put({"id": away.id, "kind": "model", "root": str(self.folder), "home": moved_away.name, "entry": "away"})
        with mock.patch("cad.engine.records.current", return_value=self.registry), \
                mock.patch("cad.engine.client.request", return_value={"ok": True, "lines": []}) as asked:
            build._reattach([held, own, new, away])
        [((message,), options)] = [(call.args, call.kwargs) for call in asked.call_args_list]
        self.assertEqual([row["name"] for row in message["models"]], ["new", "away"])
        self.assertEqual((message["op"], message["pid"], options), ("reattach", os.getpid(), {"start": False}))
        with mock.patch("cad.engine.records.current", return_value=self.registry), \
                mock.patch("cad.engine.client.request") as asked:
            build._reattach([held, own])
        asked.assert_not_called()


class ReattachmentDaemonTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(canonical(tempfile.mkdtemp(prefix="identity-")))
        self.addCleanup(shutil.rmtree, self.folder, True)
        engine = tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
        self.addCleanup(shutil.rmtree, engine, True)
        self.env = {**os.environ, "CAD_ENGINE_DIR": engine, "CAD_STATE_DIR": str(self.folder / "state"),
                    "CAD_CACHE_DIR": str(self.folder / "cache"), "CAD_LAUNCHER_DIR": str(self.folder / "bin"),
                    "CAD_ENGINE_PORT": "0", "CAD_ENGINE_STANDBY": "0", "DO_NOT_TRACK": "1"}
        engine_daemon.register(self.env["CAD_STATE_DIR"])
        engine_daemon.start(self.env)
        self.addCleanup(self.stop)
        self.registry = Registry(self.env["CAD_STATE_DIR"], self.env["CAD_CACHE_DIR"])

    def stop(self):
        engine_daemon.run([sys.executable, "-m", "cad_server.engine", "stop"], env=self.env)

    def run_script(self, script, warm=False):
        engine_daemon.start(self.env)  # again after a stop: a restart
        done = engine_daemon.run([sys.executable, str(script)], env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        if warm:
            self.assertIn("nothing ran", done.stdout, done.stdout + done.stderr)
        return done

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_moves_are_warm_copies_and_function_renames_are_new(self):
        project = self.folder / "project"
        project.mkdir()
        script = project / "part.py"
        script.write_text(SCRIPT.format(options=""), encoding="utf-8")
        self.run_script(script)
        self.stop()
        first = model_id(script, "part")
        digest = self.digest(project / "part.xbf")
        self.registry.update(first, lambda row: {**row, "preview": {"thumbnail": "kept.png"}, "opened": 3})
        created = self.registry.get(first)["created"]
        # Its folder moved, its .xbf with it: the record follows, and the run takes it from the moved file.
        moved = self.folder / "moved"
        project.rename(moved)
        script = moved / "part.py"
        self.run_script(script, warm=True)
        second = model_id(script, "part")
        self.assertIsNone(self.registry.get(first))
        self.assertEqual(self.digest(moved / "part.xbf"), digest)
        self.assertEqual(self.registry.get(second)["created"], created)
        self.assertEqual(self.registry.get(second)["preview"], {"thumbnail": "kept.png"})
        self.assertEqual(self.registry.get(second)["opened"], 3)
        self.assertEqual(self.registry.get(second)["aliases"], [first])
        # The script moved alone: its record follows; its .xbf is not there, so it builds and writes it.
        single = self.folder / "single"
        single.mkdir()
        script.rename(single / "renamed.py")
        script = single / "renamed.py"
        self.run_script(script)
        third = model_id(script, "part")
        self.assertIsNone(self.registry.get(second))
        self.assertTrue((single / "part.xbf").is_file(), "the same model, written where it is now")
        self.stop()
        self.run_script(script, warm=True)
        before = self.registry.get(third)
        copy = self.folder / "copy"
        shutil.copytree(single, copy)
        self.run_script(copy / "renamed.py")
        self.assertEqual(self.registry.get(third), before, "copy leaves the extant original untouched")
        copied = model_id(copy / "renamed.py", "part")
        self.assertIsNotNone(self.registry.get(copied))
        script.write_text(script.read_text(encoding="utf-8").replace("part()", "different()"), encoding="utf-8")
        self.run_script(script)
        self.assertIsNotNone(self.registry.get(model_id(script, "different")))
        self.assertEqual(self.registry.get(third), before, "a renamed function leaves its prior document")

    def test_a_name_keeps_its_file_and_its_id_and_two_declarations_of_it_share_them(self):
        script = self.folder / "named.py"
        script.write_text(SCRIPT.format(options='(name="named")'), encoding="utf-8")
        self.run_script(script)
        self.stop()
        ident = model_id(script, "part", "named")
        self.assertEqual(ident, file_id(self.folder / "named.xbf"))
        digest = self.digest(self.folder / "named.xbf")
        script.rename(self.folder / "elsewhere.py")
        script = self.folder / "elsewhere.py"
        self.run_script(script, warm=True)
        self.assertEqual(self.digest(self.folder / "named.xbf"), digest)
        self.assertEqual(self.registry.get(ident)["home"], "elsewhere.py")
        renamed = SCRIPT.format(options='(name="named")').replace("part", "piece")
        script.write_text(renamed, encoding="utf-8")
        self.run_script(script)  # its function renamed: the same file, the same id
        self.assertEqual(self.registry.get(ident)["entry"], "piece")
        # A second file of the folder declaring the name writes the same file: one id, the last build wins, and
        # nothing is refused.
        split = self.folder / "split.py"
        split.write_text(renamed.replace("Box(2, 3, 4)", "Box(5, 3, 4)"), encoding="utf-8")
        self.run_script(split)
        self.assertEqual(self.registry.get(ident)["home"], "split.py")
        self.run_script(script)
        self.assertEqual(self.registry.get(ident)["home"], "elsewhere.py")

    def test_a_record_from_before_ids_were_the_xbf_s_is_carried_and_its_old_id_still_answers(self):
        project = self.folder / "project"
        project.mkdir()
        script = project / "part.py"
        script.write_text(SCRIPT.format(options=""), encoding="utf-8")
        old = former({"script": str(script), "name": "part"})
        # A record an earlier release wrote: the model's under its script's id, naming no .xbf.
        self.registry.put({"id": old, "kind": "model", "root": str(project), "home": "part.py", "entry": "part",
                           "namespace": str(project), "name": "part", "revision": "r0", "built": 1, "created": 1,
                           "opened": 2, "pinned": True, "preview": {"thumbnail": "kept.png"},
                           "fingerprint": "0" * 64})
        self.run_script(script)  # its first build under its .xbf's id
        new = model_id(script, "part")
        self.assertIsNone(self.registry.get(old))
        found = self.registry.get(new)
        self.assertEqual({key: found[key] for key in ("created", "opened", "pinned", "preview", "aliases")},
                         {"created": 1, "opened": 2, "pinned": True, "preview": {"thumbnail": "kept.png"}, "aliases": [old]})
        # The old id answers as the model: a command, and a page.
        inspected = engine_daemon.run([sys.executable, "-m", "cad_server.engine", "inspect", old, "--json"],
                                      env=self.env)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["summary"]["id"], new)
        served = engine_daemon.run([sys.executable, "-m", "cad_server.engine", "serve", old], env=self.env)
        self.assertEqual(served.returncode, 0, served.stderr)
        page = urllib.parse.urlsplit(served.stdout.strip())
        self.assertEqual(page.path, f"/{new}")
        token = urllib.parse.parse_qs(page.query)["token"][0]
        request = urllib.request.Request(f"{page.scheme}://{page.netloc}/api/v1/documents/{old}",
                                         headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            self.assertEqual(json.loads(response.read())["id"], new)
        # The listing has one row of it, its .xbf's.
        request = urllib.request.Request(f"{page.scheme}://{page.netloc}/api/v1/documents",
                                         headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            rows = json.loads(response.read())["documents"]
        self.assertEqual([(row["id"], row["record"], row["file"]) for row in rows],
                         [(new, "model", (project / "part.xbf").as_posix())])


class IdentityMigrationTest(unittest.TestCase):
    def test_json_migration_moves_a_legacy_key_and_skips_malformed_records_idempotently(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(canonical(temporary))
            held = Registry(folder / "state", folder / "cache")
            script = folder / "part.py"
            script.write_text(SCRIPT.format(options=""), encoding="utf-8")
            old = str(uuid.uuid5(NAMESPACE, "key::arm"))
            plain = model_id(script, "part")
            for ident, extra in ((old, {"key": "arm"}), (plain, {})):
                held.put({"id": ident, "kind": "model", "root": str(folder), "home": "part.py", "entry": "part",
                          "created": 1, "built": 2, "preview": {"thumbnail": "kept.png"}, **extra})
                held.cache.write(f"documents/{ident}/document.xbf", b"opaque xbf bytes: never parsed")
            bad = model_id(folder / "bad.py", "bad")
            held.state.write(f"documents/{bad}/document.json", b"{bad json")
            # A well-formed JSON record with invalid fields is equally unreadable for this pass.
            wrong = model_id(folder / "wrong.py", "wrong")
            held.put({"id": wrong, "kind": "model", "root": 42, "home": "wrong.py", "entry": "broken"})
            (held.state.root / "documents" / ".DS_Store").write_bytes(b"no record's")
            logs = []
            result = migrate(held, log=logs.append)
            self.assertEqual((result["filled"], result["moved"], len(result["skipped"])), (1, 1, 2))
            self.assertEqual(len(logs), 1)
            self.assertIn(bad, logs[0])
            self.assertIn(wrong, logs[0])
            self.assertNotIn(".DS_Store", logs[0])
            new = derived_id(folder, "arm")
            self.assertIsNone(held.get(old))
            self.assertEqual((held.get(new)["namespace"], held.get(new)["name"]), (str(folder), "arm"))
            self.assertEqual((held.get(new)["fingerprint"], held.get(new)["aliases"]), (fingerprint(script), [old]))
            self.assertEqual(held.get(plain)["name"], "part")
            self.assertIsNone(held.cache.read(f"documents/{old}/document.xbf"), "what the cache kept of it went with it")
            self.assertEqual(held.state.read(f"documents/{bad}/document.json"), b"{bad json")
            before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for root in (held.state.root, held.cache.root)
                      for p in root.rglob("*") if p.is_file()}
            second = migrate(held, log=logs.append)
            self.assertEqual((second["filled"], second["moved"]), (0, 0))
            self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                                     for root in (held.state.root, held.cache.root)
                                     for p in root.rglob("*") if p.is_file()})
            for ident in (bad, wrong):
                held.state.remove(f"documents/{ident}")
            quiet = []
            self.assertEqual(migrate(held, log=quiet.append), {"filled": 0, "moved": 0, "skipped": []})
            self.assertEqual(quiet, [], "a pass with nothing to do says nothing")

    def test_a_record_that_names_its_xbf_moves_to_the_file_s_id_with_the_file_s_record_carried(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(canonical(temporary))
            held = Registry(folder / "state", folder / "cache")
            script = folder / "part.py"
            script.write_text(SCRIPT.format(options=""), encoding="utf-8")
            (folder / "part.xbf").write_bytes(b"the model's file")
            old = former({"script": str(script), "name": "part"})
            new = file_id(folder / "part.xbf")
            held.put({"id": old, "kind": "model", "root": str(folder), "home": "part.py", "entry": "part",
                      "namespace": str(folder), "name": "part", "fingerprint": fingerprint(script), "revision": "r1",
                      "built": 2, "created": 3, "saved": "part.xbf", "cache": {"revision": "r1", "bytes": 1},
                      "line": 3, "declares": []})
            # The fold's record of its file: opened on a page, pictured, and the version the engine wrote.
            held.put({"id": new, "kind": "file", "root": str(folder), "home": "part.xbf", "namespace": str(folder),
                      "name": "part.xbf", "opened": 9, "created": 1, "preview": {"thumbnail": "file.png"},
                      "of": {"id": old, "version": "123-16", "revision": "r1"}})
            self.assertEqual(migrate(held, log=lambda _line: None)["moved"], 1)
            self.assertIsNone(held.get(old))
            found = held.get(new)
            self.assertEqual({key: found.get(key) for key in ("kind", "created", "opened", "preview", "aliases",
                                                                "version", "cache", "line", "of")},
                             {"kind": "model", "created": 1, "opened": 9, "preview": {"thumbnail": "file.png"},
                              "aliases": [old], "version": "123-16", "cache": None, "line": None, "of": None})
            self.assertEqual(held.resolve(old), new)
            self.assertEqual(held.resolve(new), new)
            self.assertEqual(migrate(held, log=lambda _line: None)["moved"], 0, "a second pass moves nothing")

    def test_cadgen_status_says_what_the_pass_did_since_a_started_engine_s_stderr_is_no_one_s(self):
        from cad_server.engine.cli import status_text

        said = status_text({"pid": 1, "up": 5, "workers": [], "identity": {
            "filled": 2, "moved": 1, "skipped": ["documents/a/document.json: missing root/home", "documents/b"]}})
        self.assertIn("identity migration at start: filled 2, moved 1, skipped 2 "
                      "(documents/a/document.json: missing root/home, ...)", said)
        self.assertNotIn("identity", status_text({"pid": 1, "up": 5, "workers": [], "identity": None}))


def setUpModule():
    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
