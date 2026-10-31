"""What the engine's verbs say of what they read, on tiny models in an engine of the test's own: a
document whose last run failed is said once on stderr by every verb that reads it, and by ``status``
in a word, and the verbs go on; one whose code changed since is read as its last run, with nothing
said, since when to run the code again is the agent's call; a failed run's traceback
is printed once; a STEP holds no closure because the format carries none; a part ref answers where
the part stands; and a mesh file answers what it holds, or what to do."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import engine_daemon, opengl
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

# Two models in one script, so one worker builds both: ``box``, a part placed off the origin, and
# ``bad``, which fails once the script says so. cadgen is imported first, so its lazy kernel binds
# ``build123d`` (an editable install has no ``.pth`` to do it sooner).
SCRIPT = """
from cad import model

import build123d as bd

FAIL = {fail}


@model
def box():
    link = bd.Pos(30, 5, 0) * bd.Rot(0, 0, 90) * bd.Box(4, 8, 2)
    link.label = "link"
    return bd.Compound(children=[link], label="box")


@model
def bad():
    assert not FAIL, "blade count must be positive"
    return bd.Box(1, 1, 1)


if __name__ == "__main__":
    box()
    bad()
"""


class VerbsTest(unittest.TestCase):
    """One engine and one script for the class. ``bad`` is built, opened (so the engine follows its
    builds), then fails; the script is then edited, after ``box`` was built by that run."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-cli-truth-")))
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.addClassCleanup(shutil.rmtree, engine, True)
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(engine),
                                         "CAD_STATE_DIR": str(cls.folder / "state"),
                                         "CAD_CACHE_DIR": str(cls.folder / "cache"),
                                         "CAD_ENGINE_MESH": "inline"},
                                        cls.addClassCleanup)
        cls.addClassCleanup(cls.run_, "-m", "cad_server.engine", "stop")
        script = cls.folder / "parts.py"
        script.write_text(textwrap.dedent(SCRIPT.format(fail=False)), encoding="utf-8")
        built = cls.run_("parts.py")
        assert built.returncode == 0, built.stderr
        cls.box, cls.bad = [line.split()[1] for line in built.stdout.splitlines() if line.strip().startswith("id:")]
        assert cls.run_("-m", "cad_server.engine", "inspect", cls.bad).returncode == 0
        script.write_text(textwrap.dedent(SCRIPT.format(fail=True)), encoding="utf-8")
        cls.failed = cls.run_("parts.py")
        with script.open("a", encoding="utf-8") as handle:
            handle.write("# an edit\n")
        cls.command = f"cad run {script}"

    @classmethod
    def run_(cls, *args: str):
        return engine_daemon.run([sys.executable, *args], cwd=cls.folder, env=cls.env)

    def cli(self, *args: str):
        return self.run_("-m", "cad_server.engine", *args)

    def status_line(self, ident: str) -> str:
        return next(line for line in self.cli("status").stdout.splitlines() if ident in line)

    def said(self, ident: str, ref: str, words: str | None) -> None:
        """Every verb reading ``ident`` succeeds and says ``words`` (its verb's -ing form in place of
        ``{doing}``) once on stderr; nothing at all on stderr where ``words`` is None."""
        from cad.engine.render import context

        verbs = [("export", [str(self.folder / f"{ident}.glb")]), ("inspect", []), ("inspect", [ref])]
        if opengl.draws(context.available(), "the snapshot verb is drawn by OCCT"):
            verbs.append(("snapshot", [str(self.folder / f"{ident}.png"), "--width", "64", "--height", "48"]))
        for verb, args in verbs:
            done = self.cli(verb, ident, *args)
            self.assertEqual(done.returncode, 0, done.stderr)
            if words is None:
                self.assertEqual(done.stderr, "", f"{verb} {args}")
                continue
            doing = {"export": "exporting", "snapshot": "drawing"}.get(verb, "inspecting")
            self.assertEqual(done.stderr.count(words.format(doing=doing) + "\n"), 1, f"{verb} {args}: {done.stderr}")

    def test_a_document_whose_code_changed_is_read_as_its_last_run_with_nothing_said(self) -> None:
        self.said(self.box, "box/link", None)
        self.assertRegex(self.status_line(self.box), rf"^  live +box +{self.box}$")

    def test_a_document_whose_last_run_failed_is_said_to_be_its_previous_good_build(self) -> None:
        self.said(self.bad, "bad", f"the last run of bad failed; {{doing}} its previous good build; "
                                   f"fix it and run `{self.command}` to update it")
        self.assertTrue(self.status_line(self.bad).endswith("serving its previous good build"))

    def test_a_failed_run_prints_the_models_frames_once_then_the_line_naming_it(self) -> None:
        self.assertEqual(self.failed.returncode, 1)
        lines = self.failed.stderr.splitlines()
        self.assertEqual(lines[0], "Traceback (the model's frames):")
        # Its previous good build is still served, and the program stopped there: the line after says so.
        self.assertEqual(lines[-3:], ["AssertionError: blade count must be positive",
                                      "failed parts.py::bad; serving its previous good build",
                                      "the run stopped at bad"])  # its last call: nothing after it goes unbuilt
        self.assertEqual(self.failed.stderr.count("Traceback"), 1, self.failed.stderr)

    def test_a_refused_pose_leaves_the_document_as_it_was(self) -> None:
        """A snapshot refused before it draws -- a pose the document cannot take -- is the
        request's refusal, never its document's build failure: status, export and inspect say
        what they said before, and nothing says the last run failed."""
        before = self.status_line(self.box)
        self.assertNotIn("failed", before)
        refused = self.cli("snapshot", self.box, str(self.folder / "posed.png"), "--pose", '{"ja": 45}')
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn("no joints to pose", refused.stderr)
        self.assertEqual(self.status_line(self.box), before)
        for verb, args in (("export", [str(self.folder / "after.stl")]), ("inspect", [])):
            done = self.cli(verb, self.box, *args)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("failed", done.stderr)

    def test_a_wrote_line_names_each_path_as_it_was_given(self) -> None:
        """An absolute path outside the working folder stays absolute, unresolved (macOS's /var is
        /private/var), and a relative one stays relative, for export and, where OCCT can draw,
        snapshot alike."""
        from cad.engine.render import context

        elsewhere = Path(tempfile.mkdtemp(prefix="engine-wrote-"))
        self.addCleanup(shutil.rmtree, elsewhere, True)
        small = ["--width", "64", "--height", "48"]
        verbs = [("export", str(elsewhere / "box.stl"), []), ("export", "box.stl", [])]
        if opengl.draws(context.available(), "the snapshot verb is drawn by OCCT"):
            verbs += [("snapshot", str(elsewhere / "box.png"), small), ("snapshot", "box.png", small)]
        for verb, out, extra in verbs:
            done = self.cli(verb, self.box, out, *extra)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(done.stdout.startswith(f"wrote {out} ("), f"{verb} {out}: {done.stdout}")
            if verb == "export":  # a small file's size in KB (or bytes), never "0.0 MB"
                self.assertRegex(done.stdout, r"\((\d+ B|\d+\.\d KB)\) in ", done.stdout)
            else:  # a model's picture says its display as a file's does
                self.assertRegex(done.stdout, r"\(64x48, solid\) in ", done.stdout)

    def test_a_step_cadgen_exported_holds_no_closure_because_the_format_carries_none(self) -> None:
        self.assertEqual(self.cli("export", self.box, str(self.folder / "box.step")).returncode, 0)
        closure = self.cli("inspect", "box.step", "--query", "closure")
        self.assertEqual(closure.returncode, 1)
        self.assertEqual(closure.stderr, "python -m cad_server.engine inspect: box.step holds no build closure: a STEP file "
                                         "carries none, only an .xbf does; inspect the model's document by its id for "
                                         "its closure, or name a ref in the file (cad inspect box.step REF)\n")
        summary = self.cli("inspect", "box.step")
        self.assertEqual(summary.returncode, 0, summary.stderr)
        self.assertEqual(summary.stdout.splitlines()[-1], "closure     none: a STEP file carries none, only an .xbf "
                                                          "does (a model's document, inspected by its id, has one)")

    def test_a_part_ref_answers_where_the_part_stands_and_its_world_bounds(self) -> None:
        shown = self.cli("inspect", self.box, "box/link")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        found = json.loads(shown.stdout)
        self.assertEqual(found["placement"], {"origin": [30.0, 5.0, 0.0], "x": [0.0, 1.0, 0.0], "y": [-1.0, 0.0, 0.0],
                                              "z": [0.0, 0.0, 1.0]})
        self.assertEqual(found["bounds"], {"min": [26.0, 3.0, -1.0], "max": [34.0, 7.0, 1.0], "size": [8.0, 4.0, 2.0]})


class MeshTest(unittest.TestCase):
    """``inspect`` of a mesh file, which needs no engine: a GLB's own facts, read from its JSON; an
    STL's, and a ref into any mesh, refused in words that say what to do."""

    def test_a_glb_tells_its_nodes_meshes_and_animations_and_an_stl_what_to_do(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="cli-truth-mesh-"))
        self.addCleanup(shutil.rmtree, folder, True)
        document = json.dumps({"asset": {"version": "2.0"}, "nodes": [{"mesh": 0}, {"children": [0]}],
                               "meshes": [{"primitives": []}],
                               "accessors": [{"count": 2, "componentType": 5126, "type": "SCALAR", "min": [0.0],
                                              "max": [2.5]}],
                               "animations": [{"name": "spin", "samplers": [{"input": 0, "output": 0}],
                                               "channels": []}]}).encode()
        document += b" " * (-len(document) % 4)
        (folder / "rotor.glb").write_bytes(struct.pack("<III", 0x46546C67, 2, 20 + len(document))
                                           + struct.pack("<II", len(document), 0x4E4F534A) + document)
        (folder / "rotor.stl").write_text("solid rotor\nendsolid rotor\n", encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(SRC)}

        def inspect(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, "-m", "cad_server.engine", "inspect", *args], cwd=folder, env=env,
                                  capture_output=True, text=True, timeout=120)

        shown = inspect("rotor.glb")
        self.assertEqual((shown.returncode, shown.stdout.splitlines()), (0, [
            "rotor.glb  a mesh (GLB)", "nodes       2", "meshes      1", "animations", "  spin  2.5 s",
            "closure     none: a mesh carries none, only an .xbf does"]))
        refused = inspect("rotor.stl")
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(refused.stderr, "python -m cad_server.engine inspect: rotor.stl is a mesh: it has no B-rep for a "
                                         "ref to name and no build closure (only an .xbf carries one); inspect reads "
                                         "nothing more of it: `cad viewer rotor.stl` shows it, and the document it "
                                         "was exported from, inspected, tells the rest\n")
        self.assertIn("`cad inspect rotor.glb` alone tells its nodes, meshes and animations",
                      inspect("rotor.glb", "rotor").stderr)


if __name__ == "__main__":
    unittest.main()
