"""A build says where it is: the engine's stages and each body it runs, by name, one frame each, over the worker's pipe and through the daemon -- to the build's caller, to ``cadgen
status`` from another shell, to a page waiting on a served document, and, last, in each report."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock
from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cadgen.engine import progress  # noqa: E402


def await_(condition, what: str, seconds: float = 120.0):
    deadline = time.monotonic() + seconds
    while True:
        found = condition()
        if found:
            return found
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.02)


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class BodiesTest(unittest.TestCase):
    """The bodies a model's body runs (``Progress.entering``, ``leaving``): what each frame says."""

    def frames(self, body) -> list[dict]:
        sent: list[dict] = []
        with progress.building(progress.Progress(sent.append)) as current:
            current.stage("body", model="hand.py::hand", outputs=["/x/XBF/hand.xbf"])
            body(current)
        return sent

    def test_a_body_is_named_while_it_runs_and_counted_when_it_ends(self) -> None:
        def body(current) -> None:
            for name in ("thumb", "index"):
                current.entering(name)
                current.leaving(name)

        self.enterContext(mock.patch.object(progress, "INTERVAL", 0))  # every frame sent: none held
        said = [(frame["detail"], frame["done"]) for frame in self.frames(body)]
        self.assertEqual(said, [("", 0), ("thumb", 0), ("", 1), ("index", 1), ("", 2)])

    def test_a_body_inside_another_hands_the_detail_back_when_it_ends(self) -> None:
        def body(current) -> None:
            current.entering("finger")
            current.entering("tip")
            current.leaving("tip")
            current.leaving("finger")

        self.enterContext(mock.patch.object(progress, "INTERVAL", 0))
        said = [(frame["detail"], frame["done"], frame["determinate"]) for frame in self.frames(body)]
        self.assertEqual(said, [("", 0, False), ("finger", 0, False), ("tip", 0, False), ("finger", 1, False),
                                ("", 2, False)])

    def test_frames_come_at_most_one_an_interval(self) -> None:
        def body(current) -> None:
            for n in range(200):
                current.entering(f"loft{n}")
                current.leaving(f"loft{n}")

        sent = self.frames(body)
        self.assertLess(len(sent), 20, "two hundred bodies in a moment are a few frames")
        self.assertEqual((sent[-1]["detail"], sent[-1]["done"]), ("", 200),
                         "the last state is the last frame, sent as the build ends")
        held = sent[:-1]  # the phase's own frame, then the bodies', each an interval after the last
        gaps = [b["elapsedMs"] - a["elapsedMs"] for a, b in zip(held, held[1:])]
        self.assertTrue(all(gap >= progress.INTERVAL * 1000 - 5 for gap in gaps), gaps)

    def test_a_held_frame_is_sent_when_its_interval_is_up(self) -> None:
        sent: list[dict] = []
        with progress.building(progress.Progress(sent.append)) as current:
            current.stage("body", model="m.py::m")
            current.entering("first")  # held: the stage's frame was sent a moment ago
            await_(lambda: any(frame["detail"] == "first" for frame in sent), "the held frame", 5)

    def test_the_last_frame_of_each_model_is_its_report_s(self) -> None:
        current = progress.Progress(lambda frame: None)
        with progress.building(current):
            current.stage("body", model="a.py::a")
            current.entering("one")
            current.leaving("one")
            current.stage("write", model="a.py::a", detail="a.xbf")
            current.stage("body", model="a.py::b")
            current.entering("raised_here")
        reports = [{"model": "a.py::a", "ok": True}, {"model": "a.py::b", "ok": False}, {"model": "a.py"}]
        current.attach(reports)
        self.assertEqual(reports[0]["progress"]["phase"], "write")
        self.assertEqual((reports[1]["progress"]["phase"], reports[1]["progress"]["detail"]), ("body", "raised_here"))
        self.assertEqual(reports[2]["progress"]["model"], "a.py::b", "no frame of its own: the build's last")

    def test_a_build_names_each_memo_call_and_child_model_its_body_runs(self) -> None:
        from cadgen.engine import api

        folder = Path(tempfile.mkdtemp(prefix="engine-bodies-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        (folder / "hand.py").write_text(textwrap.dedent("""
            import build123d as bd
            from cadgen.engine import memo, model, xbf

            @memo
            def finger(at):
                return bd.Pos(at * 3, 0, 0) * bd.Box(2, 2, 6)

            @model
            def palm():
                return bd.Box(12, 8, 2)

            @xbf("XBF/hand.xbf")
            def hand():
                return bd.Compound(children=[palm().shape, finger(0), finger(1)], label="hand")
        """), encoding="utf-8")
        here = Path.cwd()
        os.chdir(folder)
        self.addCleanup(os.chdir, here)
        frames: list[dict] = []
        self.enterContext(mock.patch.object(progress, "INTERVAL", 0))  # in this process: every frame sent
        api.build_script(folder / "hand.py", ["hand"], daemon=False, progress=frames.append)
        said = [(frame["detail"], frame["done"]) for frame in frames
                if frame["phase"] == "body" and frame["model"] == "hand.py::hand"]
        self.assertEqual(said, [("", 0), ("palm", 0), ("", 1), ("finger", 1), ("", 2), ("finger", 2), ("", 3)])


class StagesTest(unittest.TestCase):
    """The engine's stages, said where a build reaches them (``build.py``): a model's body, its names,
    its document and each file it writes, a child's files after its target's."""

    def test_a_build_says_each_stage_of_each_model_it_writes(self) -> None:
        from cadgen.engine import api

        folder = Path(tempfile.mkdtemp(prefix="engine-stages-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        (folder / "kit.py").write_text(textwrap.dedent("""
            import build123d as bd
            from cadgen.engine import step, xbf

            @xbf("XBF/peg.xbf")
            def peg():
                return bd.Cylinder(1, 4)

            @xbf("XBF/kit.xbf")
            @step("kit.step")
            def kit():
                return bd.Compound(children=[bd.Box(4, 4, 1), bd.Pos(0, 0, 2) * peg().shape], label="kit")
        """), encoding="utf-8")
        here = Path.cwd()
        os.chdir(folder)
        self.addCleanup(os.chdir, here)
        frames: list[dict] = []
        api.build_script(folder / "kit.py", ["kit"], daemon=False, progress=frames.append)
        # Each stage's own frame: the child's body, named in the target's (``BodiesTest``), aside.
        said = [(frame["phase"], frame["model"], frame["detail"], frame["done"], frame["total"],
                 [Path(path).name for path in frame["outputs"]]) for frame in frames
                if frame["phase"] != "body" or (frame["detail"], frame["done"]) == ("", 0)]
        self.assertEqual(said, [
            ("load", "kit.py", "", 0, None, []),
            ("body", "kit.py::kit", "", 0, None, ["kit.xbf", "kit.step"]),
            ("names", "kit.py::kit", "", 0, None, ["kit.xbf", "kit.step"]),
            ("document", "kit.py::kit", "", 0, None, ["kit.xbf", "kit.step"]),
            ("write", "kit.py::kit", "kit.xbf", 0, 2, ["kit.xbf", "kit.step"]),
            ("write", "kit.py::kit", "kit.step", 1, 2, ["kit.xbf", "kit.step"]),
            ("names", "kit.py::peg", "", 0, None, ["peg.xbf"]),
            ("document", "kit.py::peg", "", 0, None, ["peg.xbf"]),
            ("write", "kit.py::peg", "peg.xbf", 0, 1, ["peg.xbf"])])


class BarTest(unittest.TestCase):
    FRAMES = [{"model": "hand.py", "phase": "load", "label": "Loading the script", "detail": "", "done": 0,
               "total": None, "determinate": False},
              {"model": "hand.py::hand", "phase": "body", "label": "Building geometry", "detail": "middle", "done": 2,
               "total": 5, "determinate": True},
              {"model": "hand.py::hand", "phase": "write", "label": "Writing files", "detail": "hand.xbf", "done": 0,
               "total": 1, "determinate": True}]

    def test_no_bar_is_drawn_on_a_stream_that_is_no_terminal(self) -> None:
        stream = io.StringIO()
        bar = progress.Bar(stream)
        printed = []
        log = bar.around(printed.append)
        for frame in self.FRAMES:
            bar.frame(frame)
            log("wrote hand.xbf")
        bar.close()
        self.assertEqual(stream.getvalue(), "")
        self.assertEqual(printed, ["wrote hand.xbf"] * 3, "the log's lines pass through untouched")

    def test_a_terminal_shows_each_finished_phase_and_the_one_in_flight(self) -> None:
        stream = Terminal()
        bar = progress.Bar(stream)
        for frame in self.FRAMES:
            bar.frame(frame)
        live = stream.getvalue().rsplit("\r", 1)[-1]
        self.assertIn("writing files", live)
        self.assertIn("0/1  hand.xbf", live)
        bar.close()
        lines = [line.split("\r")[-1].rstrip() for line in stream.getvalue().split("\n")]
        self.assertTrue(lines[0].startswith("  ✓ loading the script"), lines)
        self.assertEqual(lines[1], "hand.py::hand")
        self.assertTrue(lines[2].startswith("  ✓ building geometry"), lines)
        self.assertTrue(lines[3].startswith("  ✓ writing files"), lines)
        self.assertEqual(lines[4].strip(), "", "the live line is gone")


SLOW = """
import pathlib, time
import build123d as bd
from cadgen.engine import memo, xbf

FOLDER = pathlib.Path(__file__).parent


def gated(name, at, size):
    gate = FOLDER / f"{{name}}.go"
    while not gate.exists():
        time.sleep(0.01)
    return bd.Pos(at * 3, 0, 0) * bd.Box(2, 2, size)


@memo
def one(size):
    return gated("one", 0, size)


@memo
def two(size):
    return gated("two", 1, size)


@memo
def three(size):
    return gated("three", 2, size)


@memo
def {last}(size):
    if {fail}:
        raise RuntimeError("no")
    return bd.Pos(9, 0, 0) * bd.Box(1, 1, size)


@xbf("XBF/slow.xbf")
def slow():
    parts = [one({size}), two({size}), three({size}), {last}({size})]
    return bd.Compound(children=parts, label="slow")

if __name__ == "__main__":
    slow()
"""


class DaemonProgressTest(unittest.TestCase):
    """Frames from a slow build in a worker, as each reader takes them."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-progress-")).resolve()
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(self.state),
                                          "CADGEN_ENGINE_IDLE": "120", "CADGEN_ENGINE_MESH": "inline"}, self.addCleanup)
        # This process asks the test's daemon what it holds (``busy``), never starting one.
        self.enterContext(mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.state)}))
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        self.cli("stop")
        shutil.rmtree(self.folder, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cadgen.engine", *args], cwd=self.folder, env=self.env)

    def write(self, size: int = 2, last: str = "lid", fail: bool = False) -> None:
        """The slow model: three bodies, each waiting on its gate file, and a fourth named ``last``."""
        for gate in self.folder.glob("*.go"):
            gate.unlink()
        (self.folder / "slow.py").write_text(textwrap.dedent(SLOW.format(size=size, last=last, fail=fail)),
                                             encoding="utf-8")

    def start(self, *command: str) -> subprocess.Popen:
        """A build of the model, by ``Model.build()``: its report printed as JSON (or ``command``)."""
        command = command or ("-c", "import json, slow; print(json.dumps(slow.slow.build().models[0]))")
        process = subprocess.Popen([sys.executable, *command], cwd=self.folder, env=self.env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.addCleanup(self._reap, process)
        return process

    @staticmethod
    def _reap(process: subprocess.Popen) -> None:
        if process.poll() is None:
            process.kill()
        engine_daemon.reap(process)

    def busy(self) -> dict | None:
        """The busy worker's last frame, as ``cadgen status`` has it."""
        from cadgen.engine.client import request

        status = request({"op": "status"}, start=False) or {}
        return next((worker.get("progress") for worker in status.get("workers", []) if worker.get("busy")), None)

    def test_a_slow_build_s_frames_reach_status_in_order_and_its_report_holds_the_last(self) -> None:
        self.write()
        building = self.start()
        seen = []
        for name, done in (("one", 0), ("two", 1), ("three", 2)):
            frame = await_(lambda: (lambda f: f if f and f["detail"] == name else None)(self.busy()),
                           f"the frame naming {name}")
            seen.append((frame["phase"], frame["done"], frame["total"], frame["detail"]))
            if name == "two":
                text = self.cli("status").stdout
                self.assertIn("building slow.py::slow · Building geometry · two", text)
            (self.folder / f"{name}.go").touch()
        self.assertEqual(seen, [("body", 0, None, "one"), ("body", 1, None, "two"), ("body", 2, None, "three")])
        out, err = engine_daemon.communicate(building, self.env)
        self.assertEqual(building.returncode, 0, err)
        report = json.loads(out.strip().splitlines()[-1])
        last = report["progress"]
        self.assertEqual((last["model"], last["phase"], last["detail"]), ("slow.py::slow", "write", "slow.xbf"))
        self.assertEqual(last["outputs"], [str(self.folder / "XBF" / "slow.xbf")])
        self.assertIsNone(self.busy(), "the build is over: no worker is busy")

        # A body that raises: its report says where the build was.
        self.write(size=3, last="seal", fail=True)
        for name in ("one", "two", "three"):
            (self.folder / f"{name}.go").touch()
        failed = self.start()
        out, _err = engine_daemon.communicate(failed, self.env)
        report = json.loads(out.strip().splitlines()[-1])
        self.assertFalse(report["ok"])
        self.assertEqual((report["progress"]["phase"], report["progress"]["detail"]), ("body", "seal"))

    def test_the_caller_takes_every_frame_in_order_and_no_bar_is_drawn_off_a_terminal(self) -> None:
        self.write()
        for name in ("one", "two", "three"):
            (self.folder / f"{name}.go").touch()
        probe = textwrap.dedent("""
            import json, os
            from pathlib import Path
            from cadgen.engine.client import request
            frames = []
            answer = request({"op": "build", "script": str(Path("slow.py").resolve()), "cwd": os.getcwd(),
                              "env": dict(os.environ)}, on_progress=frames.append)
            print(json.dumps({"ok": all(report["ok"] for report in answer["done"]), "frames": frames}))
        """)
        done = engine_daemon.run([sys.executable, "-c", probe], cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertTrue(found["ok"])
        frames = found["frames"]
        phases = [frame["phase"] for frame in frames]
        self.assertEqual(phases[0], "load")
        order = list(progress.PHASES)
        self.assertEqual(sorted(set(phases), key=order.index), order, "every stage, each once its turn came")
        self.assertEqual(phases, sorted(phases, key=order.index), "each phase after the one before it")
        counts = [frame["done"] for frame in frames if frame["phase"] == "body"]
        self.assertEqual(counts, sorted(counts), "the count only goes up")
        elapsed = [frame["elapsedMs"] for frame in frames]
        self.assertEqual(elapsed, sorted(elapsed))
        self.assertEqual(frames[-1]["detail"], "slow.xbf")
        # ``python slow.py`` with its stderr no terminal: the build's log, and no bar.
        self.write(size=3)
        for name in ("one", "two", "three"):
            (self.folder / f"{name}.go").touch()
        running = self.start("slow.py")
        _out, err = engine_daemon.communicate(running, self.env)
        self.assertEqual(running.returncode, 0, err)
        self.assertIn("wrote XBF/slow.xbf", err)
        self.assertFalse({"\r", "▕", "✓"} & set(err), err)

    def test_a_page_waiting_on_a_served_document_is_woken_by_its_build_s_progress(self) -> None:
        self.write()
        for name in ("one", "two", "three"):
            (self.folder / f"{name}.go").touch()
        first = self.start("slow.py")
        engine_daemon.communicate(first, self.env)
        self.assertEqual(first.returncode, 0)
        served = self.cli("serve", "XBF/slow.xbf")
        self.assertEqual(served.returncode, 0, served.stderr)
        from urllib.parse import urlsplit, parse_qs
        page = urlsplit(served.stdout.strip())
        query = parse_qs(page.query)
        base, ident, token = f"{page.scheme}://{page.netloc}", page.path.strip("/"), query["token"][0]
        route = f"{base}/api/doc/{ident}/version"

        def get(query: str) -> dict:
            with urllib.request.urlopen(urllib.request.Request(f"{route}?{query}",
                        headers={"Authorization": "Bearer " + token}), timeout=120) as response:
                return json.loads(response.read())

        idle = get("")
        self.assertEqual((idle["building"], idle["failed"]), (None, None))
        version, mark = idle["version"], idle["progress"]
        self.write(size=4)
        building = self.start("slow.py")
        seen = []
        while not seen or seen[-1]["detail"] != "one":
            answer = get(f"after={version}&progress={mark}&wait=60")
            self.assertEqual(answer["version"], version, "the version moves only when the xbf does")
            mark = answer["progress"]
            if answer["building"]:
                seen.append(answer["building"])
        self.assertEqual(seen[-1]["model"], "slow.py::slow")
        self.assertIn(str(self.folder / "XBF" / "slow.xbf"), seen[-1]["outputs"])
        for name in ("one", "two", "three"):
            (self.folder / f"{name}.go").touch()
        moved = False
        while not (moved and answer["building"] is None):
            answer = get(f"after={version}&progress={mark}&wait=60")
            mark = answer["progress"]
            if answer["version"] != version:
                moved, version = True, answer["version"]
        self.assertIsNone(answer["failed"])
        engine_daemon.communicate(building, self.env)
        self.assertEqual(building.returncode, 0)
        # A build that fails says so to the page, and where it was.
        self.write(size=5, last="seal", fail=True)
        for name in ("one", "two", "three"):
            (self.folder / f"{name}.go").touch()
        failed = self.start("slow.py")
        while not answer["failed"]:
            answer = get(f"after={version}&progress={mark}&wait=60")
            mark = answer["progress"]
        self.assertIsNone(answer["building"])
        self.assertEqual(answer["failed"]["model"], "slow.py::slow")
        self.assertIn("RuntimeError: no", answer["failed"]["error"])
        self.assertEqual(answer["failed"]["progress"]["detail"], "seal")
        engine_daemon.communicate(failed, self.env)
        self.assertEqual(failed.returncode, 1)


if __name__ == "__main__":
    unittest.main()
