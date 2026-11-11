"""A model script through the daemon: running it asks the daemon to build its models, each reported by
its id and served at one address; decorating a model declares it and ``__main__`` calls it; no verb
runs a script, an id is read as held, and inspection never builds; an element answers what made it
from the worker that built it."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import daemon_fixtures, engine_daemon
from tests.python.support.daemon_fixtures import BARE, MODEL, get_json


class DaemonModelTest(daemon_fixtures.DaemonCase):
    """A model script's builds through the daemon, and what each verb reads of them."""

    def test_inspection_never_builds_a_missing_or_edited_script_model(self):
        from cad.engine.ids import model_id

        # The registry alone, a cache folder nothing can write: a restart is refused with the command
        # (what the cache reopens is ``test_cache_restart``'s).
        self.own(CAD_CACHE_DIR=engine_daemon.unwritable(self.folder))

        marker = self.folder / "executed.txt"
        main = self.folder / "main.txt"
        self.script.write_text(textwrap.dedent(MODEL.format(size=3)).replace(
            'if __name__ == "__main__":',
            f'from pathlib import Path\nPath({str(marker)!r}).write_text("imported", encoding="utf-8")\n'
            f'if __name__ == "__main__":\n    Path({str(main)!r}).write_text("main", encoding="utf-8")'), encoding="utf-8")
        ident = model_id(self.script, "block")
        # An id nothing holds is refused, naming no build: the engine runs nothing.
        for options in ((), ("face 1",), ("--query", "build")):
            missing = self.cli("inspect", ident, *options)
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
            self.assertIn(f"no document {ident} is held", missing.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse((self.folder / "XBF/block.xbf").exists())
        self.built("block")
        self.assertTrue(marker.exists())
        self.assertFalse(main.exists(), "explicit decorated-model build does not execute __main__")
        saved = (self.folder / "XBF/block.xbf").read_bytes()
        marker.unlink()
        self.script.write_text('raise RuntimeError("inspection ran source")\n', encoding="utf-8")
        for options in ((), ("face 1",), ("--query", "build")):
            inspected = self.cli("inspect", ident, *options)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual((self.folder / "XBF/block.xbf").read_bytes(), saved)
        self.assertFalse(marker.exists())
        self._stop_daemon()
        # After a restart the registry knows it: refused with the command that builds it again, run by no one.
        missing = self.cli("inspect", ident, "face 1")
        self.assertEqual(missing.returncode, 2)
        self.assertIn(f"block ({ident}) is not saved: the engine's cache holds no file of its last build; run "
                      "`cad run ", missing.stderr)
        self.assertFalse(marker.exists())
        inspected = self.cli("inspect", str(self.folder / "XBF/block.xbf"), "--query", "build")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertIsNone(json.loads(inspected.stdout)["live"])

    def test_a_named_model_updates_one_address_and_after_a_restart_names_its_command(self) -> None:
        from urllib.parse import urlparse, parse_qs

        aside = Path(tempfile.mkdtemp(prefix="engine-daemon-cache-")).resolve()
        self.addCleanup(shutil.rmtree, aside, True)
        self.own(CAD_CACHE_DIR=engine_daemon.unwritable(aside))  # nothing kept: ``test_cache_saving``'s

        address = self._bare()
        first = self.built("bracket")
        self.assertEqual(first["files"], {})
        self.assertEqual(first["id"], address)
        self.assertNotIn("address", first, "a report names its document by its id alone")
        url = urlparse(first["url"])
        doc = url.path.strip("/")
        endpoint = f"{url.scheme}://{url.netloc}/api/v1/documents/model/{doc}/structure"
        token = parse_qs(url.query)["token"][0]
        before = get_json(endpoint, token)
        (self.folder / "bracket.py").write_text(textwrap.dedent(BARE.format(size=2)), encoding="utf-8")
        second = self.built("bracket")
        self.assertEqual(urlparse(second["url"])[:3], url[:3], "one address, each URL with a fresh link")
        from cad.engine.ids import model_id

        self.assertEqual((first["id"], second["id"], doc), (model_id(self.folder / "bracket.py", "bracket"),) * 3,
                         "two builds of one function are one document, served by its id")
        after = get_json(endpoint, token)
        self.assertNotEqual(before["version"], after["version"])
        measured = self.cli("inspect", f"{address}#face 1")
        self.assertEqual(measured.returncode, 0, measured.stderr)
        self.assertEqual(json.loads(measured.stdout)["kind"], "face")
        models = json.loads(self.cli("status", "--json").stdout)["models"]
        self.assertEqual([row["id"] for row in models], [address])
        self.assertEqual([path.name for path in self.folder.iterdir()], ["bracket.py"],
                         "no cache, document, or thumbnail on disk")
        self._stop_daemon()
        missing = self.cli("inspect", f"{address}#face 1")
        self.assertEqual(missing.returncode, 2)
        self.assertIn(f"bracket ({address}) is not saved: the engine's cache holds no file of its last build; "
                      "run `cad run ", missing.stderr)
        self.assertEqual(json.loads(self.cli("status", "--json").stdout)["models"], [],
                         "a restart holds nothing: status lists what this server built")

    def test_a_script_is_never_a_source_and_an_id_is_read_as_held(self) -> None:
        """No verb imports, runs or builds a script: ``x.py`` and ``x.py::f`` are refused as any file
        that is no document is. An id is the document the engine holds: exported after the script
        changed, it writes the same bytes, and nothing runs."""
        from cad.engine.ids import model_id

        marker = self.folder / "ran.txt"
        self.script.write_text(textwrap.dedent(MODEL.format(size=3)).replace(
            "def block():\n", f"def block():\n    open({str(marker)!r}, 'w', encoding='utf-8').write('ran')\n"),
            encoding="utf-8")
        for named in (str(self.script), f"{self.script}::block"):
            for verb, *rest in (("export", "refused.step"), ("serve",), ("inspect",), ("snapshot", "refused.png")):
                with self.subTest(verb=verb, source=named):
                    refused = self.cli(verb, named, *rest)
                    self.assertEqual(refused.returncode, 2, refused.stderr)
                    self.assertRegex(refused.stderr, "is no document|is neither a document")
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["block.py"], "nothing ran, nothing was written")
        ident = self.built("block")["id"]
        self.assertEqual(ident, model_id(self.script, "block"))
        marker.unlink()
        first = self.cli("export", ident, "first.step")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.script.write_text(textwrap.dedent(MODEL.format(size=9)), encoding="utf-8")
        again = self.cli("export", ident, "again.step")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual((self.folder / "again.step").read_bytes(), (self.folder / "first.step").read_bytes(),
                         "the held document, as it was built")
        self.assertFalse(marker.exists(), "an id is never built")

    def test_a_program_reports_every_model_its_calls_build_wherever_each_is_defined(self) -> None:
        from urllib.parse import urlsplit

        from cad.engine.ids import model_id

        (self.folder / "parts.py").write_text(textwrap.dedent(BARE.format(size=1)).replace("bracket", "cube"),
                                              encoding="utf-8")
        (self.folder / "caller.py").write_text("import parts\nparts.cube()\n", encoding="utf-8")
        done = self.run_script("caller.py")
        self.assertEqual(done.returncode, 0, done.stderr)
        ident = model_id(self.folder / "parts.py", "cube")
        self.assertIn(f"  id: {ident}", done.stdout)
        view = next(line for line in done.stdout.splitlines() if line.startswith("  view: "))
        self.assertEqual(urlsplit(view.removeprefix("  view: ")).path, f"/{ident}")

    def test_main_calls_bare_and_file_models_in_order_and_keeps_its_arguments(self) -> None:
        self.script.write_text("""import sys
from cad import model, step, xbf
import build123d as bd
@model
def bare(): return bd.Box(1, 2, 3)
@step('saved.step')
def saved(): return bd.Box(2, 2, 3)
@xbf("XBF/document.xbf")
def document(): return bd.Box(3, 2, 3)
if __name__ == '__main__':
    print('before', sys.argv[1:])
    value = bare()
    print('volume', round(value.shape.volume))
    saved()
    document()
    print('after')
""", encoding="utf-8")
        done = engine_daemon.run([sys.executable, str(self.script), '--mine'], cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("before ['--mine']", done.stdout)
        self.assertIn('volume 6', done.stdout)
        self.assertTrue(done.stdout.rstrip().endswith('after'))
        self.assertTrue((self.folder / 'saved.step').is_file())
        self.assertTrue((self.folder / 'XBF/document.xbf').is_file())
        self.assertFalse((self.folder / 'XBF/bare.xbf').exists())

    def where(self, ref: str, doc: str = "XBF/block.xbf") -> dict:
        from cad.engine.ids import is_id

        kind = "model" if is_id(doc) else "xbf"
        found = engine_daemon.run([sys.executable, "-m", "cad_server.cli", kind, "inspect", doc, ref], cwd=self.folder,
                                  env=self.env)
        self.assertEqual(found.returncode, 0, found.stderr)
        return json.loads(found.stdout)

    def test_an_element_answers_what_made_it_from_the_worker_that_built_it(self) -> None:
        ident = self.build(10)["id"]
        face = self.where("block/face 1", ident)
        made = face["made_by"]
        line = next(n for n, text in enumerate(self.script.read_text(encoding="utf-8").splitlines(), 1)
                    if "bd.fillet" in text)
        self.assertEqual((made["function"], made["file"], made["line"]), ("block", str(self.script), line))
        self.assertEqual(made["name"], face["name"])
        self.assertTrue(made["feature"].startswith("block.") and made["operation"])
        self.assertGreater(face["area"], 0)
        # By its element name, the same element.
        self.assertEqual(self.where(face["name"], ident)["ordinal"], 1)
        drop = ("made_by", "meshed")
        # The xbf the run wrote is a file: it names no model, so its element answers no ``made_by``,
        # the worker that wrote it live or not -- and every fact the kernel measures is the model's.
        declared = self.where("block/face 1")
        self.assertNotIn("made_by", declared)
        self.assertEqual({k: v for k, v in declared.items() if k not in drop},
                         {k: v for k, v in face.items() if k not in drop})
        # A daemon started again with no build serves the model from its cache cold: no worker
        # holds a trace of it, so ``made_by`` is null -- and every fact the kernel measures is
        # what it was. Nothing of the provenance was written anywhere.
        self._stop_daemon()
        cold = self.where("block/face 1", ident)
        self.assertIsNone(cold.pop("made_by"))
        self.assertEqual({k: v for k, v in cold.items() if k not in drop}, {k: v for k, v in face.items() if k not in drop})
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()),
                         ["XBF/block.xbf", "block.py"])

    def test_a_failing_body_answers_with_its_error(self) -> None:
        self.script.write_text("from cad.engine import xbf\n\n@xbf('XBF/block.xbf')\ndef block():\n    raise RuntimeError('no')\nif __name__ == '__main__':\n    block()\n", encoding="utf-8")
        done = self.run_script("block.py")
        self.assertEqual(done.returncode, 1)
        self.assertIn("RuntimeError: no", done.stderr)

    def test_running_a_model_script_asks_the_daemon_to_build_it(self) -> None:
        # A script runs like Python and takes no options (law 11): every model it defines writes
        # what it declares, whatever its argv holds.
        self.script.write_text(textwrap.dedent(MODEL.format(size=3)) + "\n\n@stl('peg.stl')\ndef peg():\n"
                               "    return bd.Cylinder(1, 3)\nif __name__ == '__main__':\n    peg()\n", encoding="utf-8")
        self.script.write_text(self.script.read_text(encoding="utf-8").replace("import xbf", "import stl, xbf"),
                               encoding="utf-8")
        done = self.run_script("block.py")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual([line.split(" in ")[0] for line in done.stdout.splitlines() if line.startswith("built")],
                         ["built block.py::block cold", "built block.py::peg warm"])
        self.assertEqual(sum(line.startswith("  view: http://127.0.0.1:") for line in done.stdout.splitlines()), 2,
                         "each model reports its viewer link, including file-output builds")
        from urllib.parse import parse_qs, urlparse

        from cad.engine.ids import model_id

        # Each model reports its id, the one the script's own process derives (ids.model_id), and
        # its page is that id's.
        expected = [model_id(self.script, "block"), model_id(self.script, "peg")]
        self.assertEqual([line.removeprefix("  id: ") for line in done.stdout.splitlines() if line.startswith("  id: ")],
                         expected)
        views = [line for line in done.stdout.splitlines() if line.startswith("  view: ")]
        self.assertEqual([urlparse(line.removeprefix("  view: ")).path.strip("/") for line in views], expected)
        workers = self.mine(json.loads(self.cli("status", "--json").stdout)["workers"])
        self.assertEqual([(Path(w["script"]).name, w["builds"]) for w in workers], [("block.py", 2)],
                         "the daemon's worker built it, not the script's own process")
        done = engine_daemon.run([sys.executable, "block.py", "--step", "b.step", "--json"], cwd=self.folder,
                                 env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()),
                         ["XBF/block.xbf", "block.py", "peg.stl"])

    def test_decoration_only_declares_and_main_calls_only_its_selected_model(self) -> None:
        self.own()  # no engine yet, so none an import started goes unseen
        self.script.write_text(textwrap.dedent("""
            from cad import model, xbf

            @model
            def unused():
                raise AssertionError("uncalled model ran")

            @xbf("XBF/block.xbf")
            def block():
                import build123d as bd
                return bd.Box(1, 2, 3)

            if __name__ == "__main__":
                import sys
                print("after definitions", "build123d" in sys.modules)
                if "call" in sys.argv:
                    block()
                    print("after call")
            """), encoding="utf-8")
        declared = self.run_script("block.py")
        self.assertEqual((declared.returncode, declared.stdout.strip()), (0, "after definitions False"), declared.stderr)
        self.assertFalse((self.folder / "XBF").exists())
        self.assertFalse(self.state.exists() and any(self.state.iterdir()), "importing starts no daemon")
        called = engine_daemon.run([sys.executable, "block.py", "call"], cwd=self.folder, env=self.env)
        self.assertEqual(called.returncode, 0, called.stderr)
        self.assertIn("after call", called.stdout)
        self.assertTrue((self.folder / "XBF/block.xbf").is_file())


if __name__ == "__main__":
    unittest.main()
