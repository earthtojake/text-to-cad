"""MuJoCo Studio, from the server: ``cad run mujoco-studio`` adds the mujoco integration as ``--with cad[mujoco]``
would and runs ``cad.mujoco._command`` in its environment, and Open in offers Studio for an MJCF where the
installation runs it with nothing fetched (``studio.find``), starting ``cad run mujoco-studio --model FILE``
detached and opening the URL Studio prints (``studio.start``), one Studio per file, stopped where its URL
never appears and when the server exits (``studio.stop``). Nothing is made or launched: the environments
are files in a temporary folder, the process a recorder."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import signal
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources

add_sources()

from cad_server._internal import apps, extras, studio  # noqa: E402

BANNER = ("cad run: MuJoCo Studio's web viewer listens on every network interface\n"
          "+------+\n|   Local:   \x1b]8;;http://localhost:8081/\x1b\\http://localhost:8081/\x1b]8;;\x1b\\  |\n")


class Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="mujoco-studio-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.folder)

    def touch(self, name: str) -> Path:
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path


class RunTest(Folder):
    def test_the_bare_command_adds_the_mujoco_integration_and_runs_through_its_module(self) -> None:
        from cad_server.cli import run

        def spec(*argv: str) -> extras.Spec:
            found = run.prepare(run.parse(list(argv)), "0.11.1").spec
            assert isinstance(found, extras.Spec)
            return found

        self.assertEqual(spec("mujoco-studio", "--help").integrations, ("mujoco",))
        self.assertEqual(spec("mujoco-studio.exe", "--model", "scene.xml").integrations, ("mujoco",))
        self.assertEqual(spec("--with", "cad[trimesh]", "mujoco-studio").integrations, ("mujoco", "trimesh"))
        self.assertEqual(spec("./mujoco-studio").integrations, (), "a path is no declared command")
        python = str(self.touch("env/bin/python"))
        self.assertEqual(run._command(run.parse(["mujoco-studio", "--model", "scene.xml"]), python),
                         [python, "-P", "-m", "cad.mujoco._command", "mujoco-studio", "--model", "scene.xml"])


class FindTest(Folder):
    def test_studio_where_its_environment_is_here_and_holds_the_script(self) -> None:
        carried = self.touch("own/bin/python")
        made = self.folder / "made"
        made_python = self.touch("made/Scripts/python.exe" if os.name == "nt" else "made/bin/python")

        def found(state: str):
            return lambda integration: (state, str(made), "0.11.1")

        self.assertIsNone(studio.find(found("carried"), str(carried)), "no script beside it, no Studio")
        self.assertIsNone(studio.find(found("made"), str(carried)))
        own = self.touch("own/bin/mujoco-studio")
        script = self.touch(str((made_python.parent / "mujoco-studio").relative_to(self.folder)))
        self.assertEqual(studio.find(found("carried"), str(carried)), studio.Studio(str(own)))
        self.assertEqual(studio.find(found("made"), str(carried)), studio.Studio(str(script)))
        self.assertIsNone(studio.find(found("not made"), str(carried)), "never one fetched for a menu")

    def test_the_look_adds_studio_to_the_desktop_apps(self) -> None:
        found = studio.Studio("/env/bin/mujoco-studio")
        with mock.patch.object(apps, "detect", return_value={"vscode": "/v"}), \
                mock.patch.object(studio, "find", return_value=found):
            self.assertEqual(apps.found_here("linux", commands=False), {"vscode": "/v", "mujoco-studio": found})
        with mock.patch.object(apps, "detect", return_value={}), mock.patch.object(studio, "find", return_value=None):
            self.assertEqual(apps.found_here("linux"), {})
        self.assertEqual(apps.apps_for("mjcf", {"mujoco-studio": found}), [{"id": "mujoco-studio", "name": "MuJoCo Studio"}])


class StartTest(Folder):
    def setUp(self) -> None:
        super().setUp()
        patch = mock.patch.dict(studio._RUNNING, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        registered = mock.patch.object(studio, "_REGISTERED", True)  # no exit handler in the test process
        registered.start()
        self.addCleanup(registered.stop)
        self.said: list[str] = []
        self.ended: list = []

    def start(self, printed: str | None, exited: int | None = None, child: mock.Mock | None = None):
        opened: list[str] = []
        calls: list = []

        def spawn(argv, **options):
            calls.append((argv, options))
            if printed is not None:
                options["stdout"].write(printed.encode())
                options["stdout"].flush()
            return child or mock.Mock(**{"poll.return_value": exited})

        times = iter(range(1000))
        with mock.patch.object(tempfile, "tempdir", str(self.folder)):
            studio.start(str(self.folder / "scene.xml"), spawn=spawn, opener=opened.append, platform="linux",
                         seconds=5, clock=lambda: float(next(times)), sleep=lambda _s: None, wait=True,
                         say=self.said.append, end=self.ended.append)
        return calls, opened

    def test_cad_run_starts_detached_and_its_printed_url_is_opened(self) -> None:
        calls, opened = self.start(BANNER)
        [(argv, options)] = calls
        self.assertEqual(argv, [sys.executable, "-P", "-m", "cad_server.cli", "run", "mujoco-studio", "--model",
                                str(self.folder / "scene.xml")])
        self.assertEqual((options["stdin"], options["stderr"], options["start_new_session"]),
                         (subprocess.DEVNULL, subprocess.STDOUT, True), "detached, never through a shell")
        self.assertNotIn("shell", options)
        self.assertEqual(opened, ["http://localhost:8081/"])
        [said] = self.said
        self.assertIn("listens on every network interface with no authentication", said, "the server says so too")
        self.assertIn(str(self.folder / "scene.xml"), said)
        if os.name != "nt":
            self.assertEqual(list(self.folder.glob("cad-mujoco-studio-*.log")), [], "its log is removed once read")

    def test_the_studio_running_on_a_file_has_its_page_opened_again_and_one_that_exited_is_started_again(self) -> None:
        child = mock.Mock(**{"poll.return_value": None})
        self.assertEqual(len(self.start(BANNER, child=child)[0]), 1)
        calls, opened = self.start(BANNER, child=child)
        self.assertEqual((calls, opened), ([], ["http://localhost:8081/"]), "no second Studio on the same file")
        child.poll.return_value = 0
        self.assertEqual(len(self.start(BANNER, child=child)[0]), 1, "the one that exited is started again")

    def test_nothing_is_opened_when_studio_exits_or_prints_no_url_in_time(self) -> None:
        self.assertEqual(self.start("cad run: cad[mujoco] could not be made\n", exited=1)[1], [])
        self.assertEqual((studio._RUNNING, self.ended), ({}, []), "one that exited is forgotten, nothing to stop")
        child = mock.Mock(**{"poll.return_value": None})
        self.assertEqual(self.start("loading\n", child=child)[1], [])
        self.assertEqual(self.ended, [child], "one still running with no URL in time is stopped")
        self.assertEqual(studio._RUNNING, {}, "and forgotten: the next Open in starts afresh")
        self.assertEqual(list(self.folder.glob("cad-mujoco-studio-*.log")), [], "its log is removed on every platform")
        self.assertEqual(len(self.start(BANNER, child=mock.Mock(**{"poll.return_value": None}))[0]), 1)

    def test_a_second_open_while_studio_starts_awaits_its_page_rather_than_starting_another(self) -> None:
        path = str(self.folder / "scene.xml")
        opened: list[str] = []
        spawned: list = []
        printed = threading.Event()

        def spawn(argv, **options):
            spawned.append(argv)
            return mock.Mock(**{"poll.return_value": None})

        def sleep(_seconds: float) -> None:  # the banner appears once the second request is in
            printed.wait()
            [log] = self.folder.glob("cad-mujoco-studio-*.log")
            log.write_text(BANNER, encoding="utf-8")

        times = iter(range(1000))
        with mock.patch.object(tempfile, "tempdir", str(self.folder)):
            first = studio.start(path, spawn=spawn, opener=opened.append, platform="linux", seconds=50,
                                 clock=lambda: float(next(times)), sleep=sleep, say=self.said.append,
                                 end=self.ended.append)
            second = studio.start(path, spawn=spawn, opener=opened.append, platform="linux", seconds=50,
                                  say=self.said.append, end=self.ended.append)
        printed.set()
        first.join()
        second.join()
        self.assertEqual(len(spawned), 1, "one Studio for the file, recorded at its spawn")
        self.assertEqual(opened, ["http://localhost:8081/"] * 2, "the second request opens the first's page")
        self.assertEqual((len(self.said), self.ended), (1, []))

    def test_the_studios_this_process_started_are_stopped_as_it_exits(self) -> None:
        children = [mock.Mock(**{"poll.return_value": None}) for _ in range(2)]
        for index, child in enumerate(children):
            studio._RUNNING[f"scene{index}.xml"] = studio._Run(child, self.touch(f"scene{index}.log"))
        stopped: list = []
        studio.stop(end=stopped.append)
        self.assertEqual((stopped, studio._RUNNING), (children, {}))
        self.assertEqual(list(self.folder.glob("*.log")), [], "their logs go with them")
        with mock.patch.object(studio, "_REGISTERED", False), mock.patch.object(studio.atexit, "register") as register:
            studio._stopped_at_exit()
            studio._stopped_at_exit()
        register.assert_called_once_with(studio.stop)

    def test_a_studio_is_stopped_with_its_process_group_or_tree(self) -> None:
        child = mock.Mock(pid=4321, **{"poll.return_value": None})
        sent: list = []
        studio._end(child, platform="linux", killpg=lambda pid, number: sent.append((pid, number)))
        self.assertEqual(sent, [(4321, signal.SIGTERM)])
        child.wait.side_effect = subprocess.TimeoutExpired("studio", 5)
        studio._end(child, platform="darwin", killpg=lambda pid, number: sent.append((pid, number)))
        self.assertEqual(sent[1:], [(4321, signal.SIGTERM), (4321, signal.SIGKILL)], "killed when it does not go")
        ran: list = []
        child.wait.side_effect = None
        studio._end(child, platform="win32", taskkill=lambda argv, **_o: ran.append(argv))
        self.assertEqual(ran, [["taskkill", "/T", "/F", "/PID", "4321"]])

    def test_the_url_as_the_banner_prints_it(self) -> None:
        self.assertEqual(studio.url_of(BANNER), "http://localhost:8081/")
        self.assertIsNone(studio.url_of("MuJoCo Web Viewer starting\n"))


if __name__ == "__main__":
    unittest.main()
