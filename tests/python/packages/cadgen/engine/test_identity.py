"""Identity beyond the id's formula: an explicit name stays its declaration's through a function
renamed and a file moved in its folder, and is refused only while another file still declares it,
naming both; a run re-attaches a moved script's record by its name and bytes in one pass of the
registry, a copy never; a move stopped part way is finished; a shape handed over never takes a
declared model's id; and the startup migration moves a ``key::`` record, fills what is missing,
skips what does not read and is quiet when there is nothing to do. The run's own paths through a
real daemon in private engine, state and cache folders: a moved script is taken warm."""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cadgen.engine import model as declaring
from cadgen.engine.identity import claimed, claims, fingerprint, handed, migrate, reattach, released, repoint
from cadgen.engine.ids import NAMESPACE, canonical, derived_id, model_id
from cadgen.engine.registry import Folder, Registry
from tests.python.support import engine_daemon

SCRIPT = '''import build123d as bd
from cadgen import model
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
                           **extra})
        return ident


class ClaimTest(Fixture):
    def test_a_name_is_its_declaration_s_until_its_file_s_run_declares_it_no_more(self):
        one, two = self.folder / "one.py", self.folder / "two.py"
        for path in (one, two):
            path.write_text("# a script\n", encoding="utf-8")
        ident = self.record(one, "first", "arm", line=5, declares=["arm"])
        claimed(self.registry, {"script": str(one), "name": "second", "line": 9}, "arm")  # renamed: its own
        with self.assertRaises(ValueError) as refused:
            claimed(self.registry, {"script": str(two), "name": "first", "line": 4}, "arm")
        self.assertIn(f"claimed by {one}:5 and {two}:4", str(refused.exception))
        self.assertIn("or once one.py no longer declares it, run `cadgen run one.py`", str(refused.exception))
        claimed(self.registry, {"script": str(self.folder / "other" / "two.py"), "name": "first", "line": 4},
                "arm")  # another folder is another namespace
        self.assertEqual(released(self.registry, two, ["arm"]), [], "only its own script gives a name up")
        self.assertEqual(released(self.registry, one, ["arm"]), [ident])
        self.assertNotIn("line", self.registry.get(ident))
        self.assertEqual(self.registry.get(ident)["home"], "one.py", "its document is kept")
        claimed(self.registry, {"script": str(two), "name": "first", "line": 4}, "arm")  # given up
        self.record(one, "first", "arm", line=5)
        one.unlink()
        claimed(self.registry, {"script": str(two), "name": "first", "line": 4}, "arm")  # its file is gone

    def test_the_claims_of_a_script_are_read_from_the_records_that_point_at_it(self):
        one = self.script("one.py", "# a script\n")
        self.record(one, "first", "arm", line=5)
        self.record(one, "second", "leg", line=9)
        self.record(one, "plain")
        self.record(self.folder / "two.py", "third", "hand", line=2)
        self.assertEqual(claims(self.registry, one), {"arm", "leg"})

    def test_one_process_refuses_a_second_function_and_keeps_a_declaration_made_again(self):
        self.addCleanup(declaring._NAMES.clear)
        declaring.claim("/p", "arm", "/p/a.py", "left", 3)
        declaring.claim("/p", "arm", "/p/a.py", "left", 9)  # loaded again, its line moved
        with self.assertRaisesRegex(ValueError, "claimed by /p/a.py:9 and /p/a.py:12"):
            declaring.claim("/p", "arm", "/p/a.py", "right", 12)
        declaring.claim("/q", "arm", "/q/a.py", "right", 12)


class HandOverTest(Fixture):
    def test_a_shape_never_takes_the_id_a_named_model_holds(self):
        named = self.script("named.py", "# a script\n")
        ident = self.record(named, "part", "bracket", line=3)
        self.assertEqual(ident, derived_id(self.folder, "bracket"), "a REPL's hand-over in the folder names it")
        with self.assertRaises(ValueError) as refused:
            handed(self.registry, ident, str(self.folder), "bracket")
        self.assertIn(f"declared at {named}:3; hand it over under another name", str(refused.exception))
        released(self.registry, named, ["bracket"])
        handed(self.registry, ident, str(self.folder), "bracket")  # its script declares it no more
        self.record(named, "part", "bracket", line=3)
        named.unlink()
        handed(self.registry, ident, str(self.folder), "bracket")  # its script is gone


class ReattachmentTest(Fixture):
    def test_two_missing_candidates_choose_the_latest_and_keep_the_other(self):
        source = self.script("new/part.py", SCRIPT.format(options=""))
        for at, built in enumerate((2, 7)):
            script = self.folder / f"gone{at}" / "part.py"
            ident = self.record(script, fingerprint=fingerprint(source), built=built, created=1,
                                preview={"thumbnail": "kept.png"})
            self.registry.cache.write(f"documents/{ident}/document.xbf", f"cache{at}".encode())
        new = model_id(source, "part")
        lines = []
        moved = reattach(self.registry, [{"script": str(source), "name": "part", "fingerprint": fingerprint(source)}],
                         log=lines.append)
        self.assertEqual(moved, [(model_id(self.folder / "gone1" / "part.py", "part"), new)])
        self.assertIn("most recently built of 2 candidates", lines[0])
        self.assertEqual(len(self.registry.list()), 2)
        self.assertEqual(self.registry.cache.read(f"documents/{new}/document.xbf"), b"cache1")
        self.assertEqual(self.registry.get(new)["preview"], {"thumbnail": "kept.png"})
        self.assertEqual(self.registry.get(new)["created"], 1)

    def test_one_pass_of_the_registry_serves_every_model_and_parses_no_record_it_cannot_adopt(self):
        for at in range(40):
            self.record(self.folder / f"gone{at}" / "part.py", fingerprint=f"{at:064x}")
        sources = [{"script": str(self.folder / "new" / f"m{at}.py"), "name": "part", "fingerprint": "f" * 64}
                   for at in range(3)]
        with mock.patch.object(Folder, "names", autospec=True, side_effect=Folder.names) as listed, \
                mock.patch.object(Registry, "get", autospec=True, side_effect=Registry.get) as parsed:
            self.assertEqual(reattach(self.registry, sources), [])
        self.assertEqual(listed.call_count, 1, "one pass for all of them")
        self.assertEqual(parsed.call_count, 3, "each model's own id, and no record of the pass")

    def test_the_same_script_under_another_spelling_is_a_move_and_another_file_a_copy(self):
        real = self.script("real/part.py", SCRIPT.format(options=""))
        try:
            (self.folder / "link").symlink_to(real.parent, target_is_directory=True)
        except OSError as error:  # Windows without the symlink privilege
            self.skipTest(f"no symlinks here: {error}")
        source = {"script": str(real), "name": "part", "fingerprint": fingerprint(real)}
        spelled = self.folder / "link" / "part.py"  # the record's spelling: there still, this very file
        old = self.registry.put({"id": model_id(spelled, "part"), "kind": "model", "root": str(spelled.parent),
                                 "home": "part.py", "entry": "part", "name": "part", "built": 1,
                                 "fingerprint": source["fingerprint"]})
        self.assertTrue(old)
        self.assertEqual(reattach(self.registry, [source]), [(model_id(spelled, "part"), model_id(real, "part"))])
        copy = self.script("copy/part.py", SCRIPT.format(options=""))
        before = self.registry.get(model_id(real, "part"))
        self.assertEqual(reattach(self.registry, [{**source, "script": str(copy)}]), [], "the original is there")
        self.assertEqual(self.registry.get(model_id(real, "part")), before)

    def test_a_move_stopped_part_way_is_finished_and_another_record_is_never_replaced(self):
        script = self.script("part.py", SCRIPT.format(options=""))
        old = self.record(self.folder / "gone" / "part.py", fingerprint="a" * 64)
        self.registry.cache.write(f"documents/{old}/document.xbf", b"its bytes")
        record = self.registry.get(old)
        found = {**record, "id": model_id(script, "part"), "root": str(self.folder), "home": "part.py"}
        # Stopped after the cache file landed: a file at the new id no record names.
        self.registry.cache.write(f"documents/{found['id']}/document.xbf", b"a half move's")
        repoint(self.registry, record, found)
        self.assertIsNone(self.registry.get(old))
        self.assertEqual(self.registry.cache.read(f"documents/{found['id']}/document.xbf"), b"its bytes")
        # Stopped after the new record landed: the old one is still there.
        self.registry.put(record)
        repoint(self.registry, record, found)
        self.assertIsNone(self.registry.get(old))
        other = {**found, "entry": "another"}
        self.registry.put(record)
        with self.assertRaisesRegex(ValueError, "another record holds that id"):
            repoint(self.registry, record, other)
        self.assertIsNotNone(self.registry.get(old), "nothing moved")


class BuildAsksTest(Fixture):
    def test_a_build_asks_once_and_only_for_models_with_nothing_to_take_up(self):
        from cadgen.engine import build

        cache = self.folder / "cache" / "documents"
        script = self.folder / "parts.py"
        moved_away = self.folder / "before.py"

        def model(name, explicit=None, cached=False, written=False):
            found = SimpleNamespace(script=script, name=name, explicit_name=explicit,
                                    id=model_id(script, name, explicit), source={"script": str(script), "name": name})
            if cached:
                self.registry.cache.write(f"documents/{found.id}/document.xbf", b"x")
            if written:
                self.addCleanup(build._WRITTEN.pop, f"{script}::{name}", None)
                build._WRITTEN[f"{script}::{name}"] = object()
            return found

        held = model("held", written=True)
        cached = model("cached", cached=True)
        new = model("new")
        here = model("here", "here", cached=True)
        self.registry.put({"id": here.id, "kind": "model", "root": str(self.folder), "home": "parts.py", "entry": "here"})
        away = model("away", "away", cached=True)
        self.registry.put({"id": away.id, "kind": "model", "root": str(self.folder), "home": moved_away.name, "entry": "away"})
        with mock.patch("cadgen.engine.registry.current", return_value=self.registry), \
                mock.patch("cadgen.engine.client.request", return_value={"ok": True, "lines": []}) as asked:
            build._reattach([held, cached, new, here, away], cache)
        [((message,), options)] = [(call.args, call.kwargs) for call in asked.call_args_list]
        self.assertEqual([row["name"] for row in message["models"]], ["new", "away"])
        self.assertEqual((message["op"], message["pid"], options), ("reattach", os.getpid(), {"start": False}))
        with mock.patch("cadgen.engine.registry.current", return_value=self.registry), \
                mock.patch("cadgen.engine.client.request") as asked:
            build._reattach([held, cached, here], cache)
        asked.assert_not_called()


class ReattachmentDaemonTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(canonical(tempfile.mkdtemp(prefix="identity-")))
        self.addCleanup(shutil.rmtree, self.folder, True)
        engine = tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
        self.addCleanup(shutil.rmtree, engine, True)
        self.env = {**os.environ, "CADGEN_ENGINE_DIR": engine, "CADGEN_STATE_DIR": str(self.folder / "state"),
                    "CADGEN_CACHE_DIR": str(self.folder / "cache"), "CADGEN_LAUNCHER_DIR": str(self.folder / "bin"),
                    "CADGEN_ENGINE_PORT": "0", "CADGEN_ENGINE_STANDBY": "0", "DO_NOT_TRACK": "1"}
        self.addCleanup(self.stop)
        self.registry = Registry(self.env["CADGEN_STATE_DIR"], self.env["CADGEN_CACHE_DIR"])

    def stop(self):
        engine_daemon.run([sys.executable, "-m", "cadgen.engine", "stop"], env=self.env)

    def run_script(self, script, warm=False):
        done = engine_daemon.run([sys.executable, str(script)], env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        if warm:
            self.assertIn("nothing ran", done.stdout, done.stdout + done.stderr)
        return done

    def cached(self, ident):
        return hashlib.sha256(self.registry.cache.read(f"documents/{ident}/document.xbf")).hexdigest()

    def test_moves_are_warm_copies_and_function_renames_are_new(self):
        project = self.folder / "project"
        project.mkdir()
        script = project / "part.py"
        script.write_text(SCRIPT.format(options=""), encoding="utf-8")
        self.run_script(script)
        self.stop()
        first = model_id(script, "part")
        digest = self.cached(first)
        self.registry.update(first, lambda row: {**row, "preview": {"thumbnail": "kept.png"}, "opened": 3})
        created = self.registry.get(first)["created"]
        moved = self.folder / "moved"
        project.rename(moved)
        script = moved / "part.py"
        self.run_script(script, warm=True)
        second = model_id(script, "part")
        self.assertIsNone(self.registry.get(first))
        self.assertEqual(self.cached(second), digest)
        self.assertEqual(self.registry.get(second)["created"], created)
        self.assertEqual(self.registry.get(second)["preview"], {"thumbnail": "kept.png"})
        self.assertEqual(self.registry.get(second)["opened"], 3)
        # A second move, with the same daemon and the original cache's paths still in its bytes.
        single = self.folder / "single"
        single.mkdir()
        script.rename(single / "renamed.py")
        script = single / "renamed.py"
        self.run_script(script, warm=True)
        third = model_id(script, "part")
        self.assertIsNone(self.registry.get(second))
        self.assertEqual(self.cached(third), digest)
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

    def test_an_explicit_name_keeps_its_id_through_a_move_a_rename_and_a_split(self):
        script = self.folder / "named.py"
        script.write_text(SCRIPT.format(options='(name="named")'), encoding="utf-8")
        self.run_script(script)
        self.stop()
        ident = model_id(script, "part", "named")
        digest = self.cached(ident)
        script.rename(self.folder / "elsewhere.py")
        script = self.folder / "elsewhere.py"
        self.run_script(script, warm=True)
        self.assertEqual(self.cached(ident), digest)
        self.assertEqual(self.registry.get(ident)["home"], "elsewhere.py")
        renamed = SCRIPT.format(options='(name="named")').replace("part", "piece")
        script.write_text(renamed, encoding="utf-8")
        self.run_script(script)  # its function renamed: its own declaration still
        self.assertEqual(self.registry.get(ident)["entry"], "piece")
        # Moved into a file of its own while the file it left stays, with a model of its own: the
        # engine knows what that file declares from its last run, so it is refused until that file
        # runs again and gives the name up.
        split = self.folder / "split.py"
        split.write_text(renamed, encoding="utf-8")
        script.write_text(SCRIPT.format(options="").replace("part", "other"), encoding="utf-8")
        refused = engine_daemon.run([sys.executable, str(split)], env=self.env)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn(f"claimed by {script}:3 and {split}:3", refused.stderr)
        self.run_script(script)
        self.assertIsNotNone(self.registry.get(model_id(script, "other")))
        self.run_script(split)
        self.assertEqual((self.registry.get(ident)["home"], self.registry.get(ident)["line"]), ("split.py", 3))


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
            bad = model_id(folder / "bad.py", "broken")
            held.state.write(f"documents/{bad}/document.json", b"{bad json")
            # A well-formed JSON record with invalid fields is equally unreadable for this pass.
            wrong = model_id(folder / "wrong.py", "broken")
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
            self.assertEqual((held.get(new)["fingerprint"], held.get(new)["line"]), (fingerprint(script), 3))
            self.assertEqual(held.get(plain)["name"], "part")
            self.assertEqual(held.cache.read(f"documents/{new}/document.xbf"), b"opaque xbf bytes: never parsed")
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

    def test_cadgen_status_says_what_the_pass_did_since_a_started_engine_s_stderr_is_no_one_s(self):
        from cadgen.engine.cli import status_text

        said = status_text({"pid": 1, "up": 5, "workers": [], "identity": {
            "filled": 2, "moved": 1, "skipped": ["documents/a/document.json: missing root/home", "documents/b"]}})
        self.assertIn("identity migration at start: filled 2, moved 1, skipped 2 "
                      "(documents/a/document.json: missing root/home, ...)", said)
        self.assertNotIn("identity", status_text({"pid": 1, "up": 5, "workers": [], "identity": None}))


def setUpModule():
    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
