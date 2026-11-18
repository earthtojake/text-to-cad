"""The bridge (``cad_server.cli.setup``): what carries a computer a release of 0.10.0 to 0.11.11 updated onto this one.

``--engine-update`` is what those updaters run of a newer release, from the folder they made: it writes the record their
switch starts its server by, owes install mode (``test_handover`` runs it) and leaves ``current`` and the ``cad`` command
to them; on Windows 0.10.0, whose switch cannot start it, it takes over. Plain ``cad setup`` is the install command in
the foreground. A server of the uv tool points the records old clients read at itself (``follow``), and a server that
runs from a shipped updater's folder hands over to the uv tool's once install mode installed it (``move``,
``Tending``). The helper the move starts is ``test_auto_update``'s; a real 0.11.10 handing over is the update
rehearsal's.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import client, places
from cad_server._internal import arrival, auto_update, install_script, installations, tool_install
from cad_server.cli import setup
from cad_server.engine.registry import Folder

OLD, Y = "0.11.10", "0.12.1"
REFUSED = ("the install command online is not yet this release's, so nothing was installed: run the install command "
           "again in a few minutes")
INSTALLING = "this cad runs from an earlier release's folder: installing cad with uv"


class Computer(unittest.TestCase):
    """A state folder of the test's own, and this environment as the release that runs ``--engine-update`` (its
    console script and Python, ``installations.targets``)."""

    def setUp(self) -> None:
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="cad-bridge-")))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state = self.root / "state"
        self.home = self.root / "home"
        self.home.mkdir()
        self.this = (str(self.root / "releases" / Y / "bin" / "cad"), sys.executable, str(self.root / "releases" / Y))
        Path(self.this[0]).parent.mkdir(parents=True)
        Path(self.this[0]).write_text("", encoding="utf-8")
        for patch in (mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state), "HOME": str(self.home),
                                                   "USERPROFILE": str(self.home), places.INSTALLATION_ENV: Y,
                                                   "CAD_UPDATE_CHECK": "0"}),
                      mock.patch.object(installations, "targets", return_value=self.this),
                      mock.patch.object(arrival, "setup_ended")):
            patch.start()
            self.addCleanup(patch.stop)
        self.ended = arrival.setup_ended
        self.state.mkdir()
        (self.state / "install-receipt.json").write_text("{}", encoding="utf-8")  # our setup ran here once

    def main(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = setup.main(argv)
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()

    def record(self, version: str, folder: Path | None = None) -> dict:
        return json.loads((folder or self.state) .joinpath("installations", f"{version}.json").read_text(encoding="utf-8"))


class EngineUpdate(Computer):
    """What an updater of 0.11.10 runs of a newer release Y, and what its switch then reads."""

    def test_prepare_does_nothing_and_the_whole_run_writes_the_record_and_owes_install_mode(self) -> None:
        installations.point(OLD)
        with mock.patch.dict(os.environ, {setup.PREPARE_ENV: "1"}):
            self.assertEqual(self.main(["--engine-update"]), (0, "", ""))
        self.assertEqual(sorted(os.listdir(self.state)), ["install-receipt.json", "installations"],
                         "the prepare run writes nothing")
        code, out, err = self.main(["--engine-update"])
        self.assertEqual((code, out, err), (0, "", ""))
        record = self.record(Y)
        self.assertEqual((record["cad"], record["python"], record["prefix"]), self.this,
                         "the record the switch starts this release's server by: this environment")
        self.assertEqual(installations.current_version(), OLD, "current is the switch's: it reads it as the way back")
        owed = install_script.read()
        self.assertEqual((owed["mode"], owed["version"], owed["state"], owed["attempts"]), ("install", Y, "owed", 0))
        self.assertEqual({key: arrival.read(Y)[key] for key in ("route", "from")}, {"route": "updater", "from": OLD})
        self.ended.assert_called_once_with(Y, "updater", OLD, "ok", None, first=True)
        self.assertFalse(Path(installations.proxy_path()).exists(), "no cad command written")
        self.assertEqual(self.main(["--engine-update"])[0], 0, "an updater's second run")
        self.assertEqual(self.ended.call_args.kwargs, {"first": False})
        self.assertNotIn("--engine-update", setup.build_parser().format_help(), "hidden")

    def test_a_run_that_cannot_write_its_record_fails_and_owes_nothing(self) -> None:
        with mock.patch.object(installations, "register", side_effect=OSError("read-only")):
            code, out, err = self.main(["--engine-update"])
        self.assertEqual(code, 1)
        self.assertEqual(err, f"cad: cad {Y} could not take over: read-only\n")
        self.assertIsNone(install_script.read())
        self.ended.assert_called_once_with(Y, "updater", None, "failed", "other", first=False)


class Plain(Computer):
    """``cad update`` typed on 0.10.x and 0.11.x runs the new release's plain ``cad setup``: the install command."""

    def test_it_runs_the_install_command_in_install_mode_and_exits_as_it_does(self) -> None:
        noted = self.root / "noted"
        stand_in = self.root / "install.py"
        stand_in.write_text("import os, sys\nopen(sys.argv[1], 'w').write(repr(os.environ.get('CAD_INSTALL_UPDATE')))"
                            "\nsys.exit(int(sys.argv[2]))\n", encoding="utf-8")
        for code in (0, 4):
            with self.subTest(code=code), mock.patch.dict(os.environ, {
                    install_script.INSTALLER_ENV: f'"{sys.executable}" "{stand_in}" "{noted}" {code}',
                    install_script.UPDATE_ENV: "1"}):
                self.assertEqual(self.main([])[0], code)
                self.assertEqual(noted.read_text(encoding="utf-8"), "None", "install mode")
        self.assertEqual([call.args[3] for call in self.ended.call_args_list], ["ok", "failed"])

    def test_run_by_an_install_command_cad_started_it_runs_nothing(self) -> None:
        # That command is an earlier release's script (the site not yet redeployed), which runs `cad setup` again.
        ran = self.root / "ran"
        with mock.patch.dict(os.environ, {install_script.BY_CAD_ENV: "1", install_script.INSTALLER_ENV:
                                          f'"{sys.executable}" -c "open(r\'{ran}\', \'w\')"'}):
            self.assertEqual(self.main([]), (1, "", f"cad: {REFUSED}\n"))
        self.assertFalse(ran.exists(), "the install command never ran")
        self.ended.assert_called_once_with(Y, "setup", None, "failed", "other", first=False)

    def test_an_earlier_release_s_script_that_runs_cad_setup_again_ends_after_one_refusal(self) -> None:
        # The way the hosted script of 0.10.0 to 0.11.11 ends: `cad setup` of the feed's newest, this release. The
        # stand-in stops itself on its fourth run, so a loop fails here rather than hangs.
        runs, stand_in = self.root / "runs", self.root / "old-install.py"
        stand_in.write_text(
            "import os, subprocess, sys\n"
            "with open(sys.argv[1], 'a', encoding='utf-8') as runs:\n"
            "    runs.write('ran\\n')\n"
            "if len(open(sys.argv[1], encoding='utf-8').read().split()) > 3:\n"
            "    sys.exit(2)\n"
            "sys.exit(subprocess.call([sys.executable, '-m', 'cad_server.cli', 'setup'], stdin=subprocess.DEVNULL,\n"
            "                         env={**os.environ, 'PYTHONPATH': sys.argv[2]}))\n", encoding="utf-8")
        source = str(Path(setup.__file__).resolve().parents[2])
        env = {**os.environ, "CAD_ENGINE_DIR": str(self.root / "engine"), "CAD_CACHE_DIR": str(self.root / "cache"),
               "CAD_TELEMETRY": "0", "DO_NOT_TRACK": "1", "CAD_API_URL": "http://127.0.0.1:9", "PYTHONPATH": source,
               install_script.INSTALLER_ENV: f'"{sys.executable}" "{stand_in}" "{runs}" "{source}"'}
        done = subprocess.run([sys.executable, "-m", "cad_server.cli", "setup"], env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(runs.read_text(encoding="utf-8"), "ran\n", "the earlier script ran once")
        self.assertEqual(done.stderr.count(REFUSED), 1, done.stderr)


class NothingOurs(Computer):
    """Plain ``cad setup`` where our setup never ran: cad alone moves only on a computer that arrives from a shipped
    release (0.10.0 to 0.11.11, a store's copy alone). Anywhere else only an install script reaches it -- a copy of an
    old one kept, or the hosted one before the site is redeployed --, and the install command runs."""

    def setUp(self) -> None:
        super().setUp()
        (self.state / "install-receipt.json").unlink()
        self.runs = self.root / "runs"

    def installer(self, code: int = 0) -> dict[str, str]:
        stand_in = self.root / "install.py"
        stand_in.write_text("import sys\nopen(sys.argv[1], 'a').write('ran\\n')\nsys.exit(int(sys.argv[2]))\n",
                            encoding="utf-8")
        return {install_script.INSTALLER_ENV: f'"{sys.executable}" "{stand_in}" "{self.runs}" {code}'}

    def test_with_no_earlier_release_the_install_command_runs_and_its_exit_status_is_the_command_s(self) -> None:
        for code in (0, 4):
            with self.subTest(code=code), mock.patch.dict(os.environ, self.installer(code)):
                self.runs.unlink(missing_ok=True)
                self.assertEqual(self.main([]), (code, "", ""))
                self.assertEqual(self.runs.read_text(encoding="utf-8"), "ran\n", "the install command ran once")
        self.assertIsNone(installations.current_version(), "current left to the install command")
        self.assertEqual([call.args[2:4] for call in self.ended.call_args_list], [(None, "ok"), (None, "failed")])

    def test_cad_alone_moves_only_where_it_arrives_from_a_shipped_release(self) -> None:
        for came, alone in ((None, False), ("0.10.0", True), (OLD, True), ("0.11.11", True), ("0.11.12", False),
                            ("0.12.0", False), ("0.11.10-dev.1", False)):
            with self.subTest(came=came), mock.patch.dict(os.environ, self.installer()):
                self.runs.unlink(missing_ok=True)
                current = self.state / "installations" / "current"
                current.unlink(missing_ok=True)
                if came is not None:
                    installations.point(came)
                code, out, err = self.main([])
                self.assertEqual(code, 0, err)
                self.assertEqual(self.runs.exists(), not alone)
                self.assertEqual(installations.current_version(), Y if alone else came)
                self.assertEqual(err, f"cad: cad {Y} runs from the next start of the cad server\n" if alone else "")

    def test_run_by_an_install_command_cad_started_it_still_runs_nothing(self) -> None:
        with mock.patch.dict(os.environ, {**self.installer(), install_script.BY_CAD_ENV: "1"}):
            self.assertEqual(self.main([]), (1, "", f"cad: {REFUSED}\n"))
        self.assertFalse(self.runs.exists(), "the install command never ran")

    def test_an_earlier_release_s_script_kept_and_run_on_an_empty_computer_installs(self) -> None:
        # A copy of the script 0.10.0 to 0.11.11 offered, which ends in `cad setup` of the feed's newest, this release.
        old = self.root / "old-install.py"
        old.write_text("import subprocess, sys\n"
                       "sys.exit(subprocess.call([sys.executable, '-m', 'cad_server.cli', 'setup'], "
                       "stdin=subprocess.DEVNULL))\n", encoding="utf-8")
        source = str(Path(setup.__file__).resolve().parents[2])
        env = {**os.environ, "CAD_ENGINE_DIR": str(self.root / "engine"), "CAD_CACHE_DIR": str(self.root / "cache"),
               "CAD_TELEMETRY": "0", "DO_NOT_TRACK": "1", "CAD_API_URL": "http://127.0.0.1:9", "PYTHONPATH": source,
               **self.installer()}
        self.assertEqual(os.listdir(self.state), [], "an empty state folder")
        done = subprocess.run([sys.executable, str(old)], env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.runs.read_text(encoding="utf-8"), "ran\n", "the install command ran")


class StoreOnly(Computer):
    """A computer whose agent apps got text-to-cad from a store alone: no receipt and no plugin folder of our setup's.
    Its old release still runs ``--engine-update`` (an automatic update of a server a ``cad`` command started) and a
    typed ``cad update`` runs plain ``cad setup``: cad alone moves, and the install command never runs there."""

    def setUp(self) -> None:
        super().setUp()
        (self.state / "install-receipt.json").unlink()

    def test_cad_alone_moves_and_nothing_installs_a_plugin(self) -> None:
        self.assertFalse(setup.ours())
        installations.point(OLD)
        self.assertEqual(self.main(["--engine-update"])[0], 0)
        self.assertEqual(self.record(Y)["prefix"], self.this[2], "the switch starts this release all the same")
        self.assertIsNone(install_script.read(), "install mode never owed")
        ran = self.root / "ran"
        with mock.patch.dict(os.environ, {install_script.INSTALLER_ENV: f'"{sys.executable}" -c "open(r\'{ran}\', \'w\')"'}):
            code, out, err = self.main([])
        self.assertEqual(code, 0, err)
        self.assertFalse(ran.exists(), "the install command never ran")
        self.assertEqual(installations.current_version(), Y, "cad update typed: this release runs from the next start")
        self.assertEqual(err, f"cad: cad {Y} runs from the next start of the cad server\n")
        for mark in ("install-receipt.json", "plugin"):  # what our setup leaves: ours, either
            path = self.state / mark
            path.mkdir() if mark == "plugin" else path.write_text("{}", encoding="utf-8")
            self.assertTrue(setup.ours(), mark)
            path.rmdir() if mark == "plugin" else path.unlink()


@unittest.skipIf(os.name == "nt", "0.10.0's stand-in stop is a POSIX script")
class TakeOver(Computer):
    """``--engine-update`` run by 0.10.0's updater on Windows (its state in the local application data, here a folder of
    the test's): its switch could only go back, so the run takes the computer over."""

    def setUp(self) -> None:
        super().setUp()
        self.appdata = self.root / "AppData" / "Local" / "cad-state"
        (self.appdata / "installations").mkdir(parents=True)
        self.stopped = self.root / "stopped"
        console = self.root / "ten" / "bin" / "cad"
        console.parent.mkdir(parents=True)
        console.write_text(f"#!/bin/sh\necho \"$*\" >> '{self.stopped}'\n"
                           "echo '{\"ok\": true, \"stopped\": [\"engine\"]}'\nexit ${TEN_EXIT:-0}\n", encoding="utf-8")
        console.chmod(0o755)
        (self.appdata / "installations" / "0.10.0.json").write_text(json.dumps(
            {"version": "0.10.0", "python": sys.executable, "cad": str(console), "prefix": str(console.parent.parent)}),
            encoding="utf-8")
        (self.appdata / "installations" / "current").write_text("0.10.0", encoding="utf-8")
        self.served = mock.Mock()
        for patch in (mock.patch.object(places, "appdata_state_dir", return_value=self.appdata),
                      mock.patch.object(setup, "_alone", return_value=True),
                      mock.patch.object(setup, "_serve", self.served)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_0_10_0_stops_first_or_nothing_changes_then_both_folders_name_this_release(self) -> None:
        with mock.patch.dict(os.environ, {"TEN_EXIT": "1"}), mock.patch.object(setup, "_appdata_serving",
                                                                               return_value=None):
            code, out, err = self.main(["--engine-update"])
        self.assertEqual(code, 1, out + err)
        self.assertIn("the server of cad-server 0.10.0 did not stop, and keeps what it has", err)
        self.assertIsNone(install_script.read())
        self.assertFalse((self.state / "installations").exists(), "nothing taken over")
        with mock.patch.object(setup, "_appdata_serving", return_value=str(self.root / "ten")):
            code, out, err = self.main(["--engine-update"])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.stopped.read_text(encoding="utf-8"), "stop --json\nstop --json\n")
        for folder in (self.state, self.appdata):
            self.assertEqual(installations.current_version(Folder(folder)), Y)
            self.assertEqual(self.record(Y, folder)["prefix"], self.this[2], "0.10.0's clients start this release")
        self.assertEqual(install_script.read()["mode"], "install")
        self.assertEqual(arrival.read(Y)["from"], "0.10.0")
        self.served.assert_called_once_with(Y)

    def test_its_typed_cad_update_takes_its_data_over_before_the_install_command_runs(self) -> None:
        # What 0.10.0's typed `cad update` runs of the new release: plain `cad setup`, from 0.10.0's own folder.
        seen, adopted = self.root / "seen", self.state / "adopted"
        stand_in = self.root / "install.py"
        stand_in.write_text("import os, sys\nopen(sys.argv[1], 'a').write(f'{os.path.exists(sys.argv[2])} '"
                            " + open(sys.argv[3]).read().strip() + '\\n')\n", encoding="utf-8")
        current = self.appdata / "installations" / "current"
        installer = {install_script.INSTALLER_ENV: f'"{sys.executable}" "{stand_in}" "{seen}" "{adopted}" "{current}"'}
        adopt = mock.Mock(side_effect=lambda: adopted.write_text("", encoding="utf-8"))
        with mock.patch.dict(os.environ, {**installer, "TEN_EXIT": "1"}), \
                mock.patch.object(places, "adopt_earlier", adopt), \
                mock.patch.object(setup, "_appdata_serving", return_value=str(self.root / "ten")):
            code, out, err = self.main([])
            self.assertEqual(code, 0, err)
            self.assertIn(f"cad {Y} left the data of cad-server 0.10.0 where it is: its server did not stop", err)
            self.assertEqual(seen.read_text(encoding="utf-8"), "False 0.10.0\n", "nothing moved; the command ran")
            adopt.assert_not_called()
            os.environ.pop("TEN_EXIT")
            code, out, err = self.main([])
        self.assertEqual(code, 0, err)
        self.assertEqual(seen.read_text(encoding="utf-8").splitlines()[1], f"True {Y}",
                         "adopted, and 0.10.0's records name this release, before the command ran")
        self.assertEqual(self.stopped.read_text(encoding="utf-8"), "stop --json\nstop --json\n")
        for folder in (self.state, self.appdata):
            self.assertEqual(installations.current_version(Folder(folder)), Y)
        self.served.assert_not_called()

    def test_0_10_0_s_stop_runs_only_against_0_10_0_s_own_server(self) -> None:
        # Its `cad stop` stops whatever answers at its port file, where later servers write a copy of their own.
        for answering, runs in ((self.this[2], False), (str(self.root / "ten"), True), (None, True)):
            with self.subTest(answering=answering):
                self.stopped.unlink(missing_ok=True)
                with mock.patch.object(setup, "_appdata_serving", return_value=answering):
                    self.assertTrue(setup.stop_appdata(lambda line: None), "held: nothing of 0.10.0's, or it stopped")
                self.assertEqual(self.stopped.exists(), runs)

    def test_it_is_told_by_where_0_10_0_made_its_folder(self) -> None:
        mock.patch.stopall()
        with mock.patch.object(places, "appdata_state_dir", return_value=self.appdata):
            with mock.patch.object(sys, "prefix", str(self.appdata / "releases" / Y)):
                self.assertTrue(setup._alone())
            self.assertFalse(setup._alone(), "a folder of 0.11.10's layout: its switch starts this release")
        with mock.patch.object(places, "appdata_state_dir", return_value=None):
            self.assertFalse(setup._alone(), "not Windows, or a state folder named")


class Serving(Computer):
    """The server a take-over starts (``_serve``) gets this process's environment, without what only this run goes
    by, and leaves ``os.environ`` as it was. Measured on Windows: computed from an emptied one, it started no server."""

    def test_the_server_gets_this_process_s_environment_less_the_run_s_own_and_it_is_put_back(self) -> None:
        kept = {"CAD_ENGINE_DIR": str(self.root / "engine"), "CAD_BRIDGE_MARK": "kept"}
        dropped = {"PYTHONPATH": str(self.root / "src"), setup.PREPARE_ENV: "1", "UV_NO_MODIFY_PATH": "1",
                   install_script.BY_CAD_ENV: "1"}
        with mock.patch.dict(os.environ, {**kept, **dropped}):
            before = dict(os.environ)
            for failing in (False, True):
                with self.subTest(failing=failing):
                    seen: list[dict[str, str]] = []

                    def start() -> str:
                        seen.append(dict(os.environ))
                        if failing:
                            raise ConnectionError("the engine server did not start")
                        return "started"

                    err = io.StringIO()
                    with mock.patch.object(client, "start", side_effect=start), \
                            mock.patch.object(client, "request", side_effect=lambda *_a, **_k: seen.append(
                                dict(os.environ))), contextlib.redirect_stderr(err):
                        setup._serve(Y)
                    self.assertEqual(len(seen), 1 if failing else 2)
                    for environment in seen:
                        self.assertEqual({key: environment.get(key) for key in kept}, kept)
                        self.assertEqual({key: environment.get(key) for key in (*dropped, places.INSTALLATION_ENV)},
                                         dict.fromkeys((*dropped, places.INSTALLATION_ENV)))
                        self.assertEqual((environment["CAD_STATE_DIR"], environment["HOME"]),
                                         (str(self.state), str(self.home)))
                        self.assertIn("PATH", environment)
                    self.assertEqual(dict(os.environ), before)
                    self.assertEqual("cad: cad 0.12.1's server is not running: the engine server did not start\n"
                                     if failing else "", err.getvalue())


class AppdataServing(unittest.TestCase):
    """Where the guard on 0.10.0's own stop asks what answers: where that stop reaches."""

    def test_the_flat_door_s_port_file_under_a_named_engine_folder_else_the_temporary_folder_s(self) -> None:
        asked: list[Path] = []
        with tempfile.TemporaryDirectory() as folder:
            root = Path(os.path.realpath(folder))
            named = {"CAD_ENGINE_DIR": str(root / "engines"), "CAD_STATE_DIR": str(root / "state"),
                     "CAD_CACHE_DIR": str(root / "cache")}
            with mock.patch.object(client, "_connect", side_effect=lambda door: asked.append(door)), \
                    mock.patch.dict(os.environ, named):
                with mock.patch.object(places, "WINDOWS", True):
                    self.assertIsNone(setup._appdata_serving(), "none answers")
                with mock.patch.object(places, "WINDOWS", False):
                    self.assertIsNone(setup._appdata_serving(), "no 0.10.0 of Windows' to guard")
                with mock.patch.object(places, "appdata_engine_dir", return_value=root / "cad-engine"):
                    setup._appdata_serving()
        self.assertEqual(asked, [root / "engines" / "engine.port", root / "cad-engine" / "engine.port"])


class Tool(Computer):
    """A uv tool ``cad`` of release ``release``, found the way ``uv tool dir`` names it: a stand-in ``uv`` on PATH."""

    def tool(self, release: str) -> Path:
        tools = self.root / "uv-tools"
        environment = tools / "cad"
        site = environment / "lib" / "python3.14" / "site-packages" / f"cad-{release}.dist-info"
        site.mkdir(parents=True, exist_ok=True)
        (environment / "uv-receipt.toml").write_text('[tool]\nrequirements = [{ name = "cad" }]\n', encoding="utf-8")
        for name in ("cad", "python"):
            (environment / "bin").mkdir(exist_ok=True)
            (environment / "bin" / name).write_text("", encoding="utf-8")
        bin_ = self.root / "bin"
        bin_.mkdir(exist_ok=True)
        uv = bin_ / "uv"
        uv.write_text(f"#!/bin/sh\n[ \"$1 $2\" = 'tool dir' ] && echo '{tools}'\n", encoding="utf-8")
        uv.chmod(0o755)
        return environment


@unittest.skipIf(os.name == "nt", "the stand-in uv is a POSIX script")
class Handing(Tool):
    """A server that runs from a shipped updater's folder, handing over: the helper it starts recorded, never run; no
    pipx found but where a test gives one; uv's tools in the test's folder."""

    def setUp(self) -> None:
        super().setUp()
        self.started: list = []
        self.envs: list[dict[str, str]] = []
        # The Python a server's environment was made from, outside it, as a uv tool's or a shipped updater's
        # environment has: the suite's own may be a system Python, with nothing outside it (CI's Linux jobs).
        for patch in (mock.patch.object(sys, "_base_executable", str(self.root / "python3"), create=True),
                      mock.patch.dict(os.environ, {"PATH": str(self.root / "bin"),
                                                   "UV_TOOL_DIR": str(self.root / "uv-tools")}),
                      mock.patch.object(setup, "_start", side_effect=lambda *a, **k: (
                          self.started.append(a), self.envs.append(k["env"]))),
                      mock.patch.object(auto_update, "find_pipx", return_value=None),
                      mock.patch.object(auto_update, "uv_tool", side_effect=lambda prefix=None: Path(prefix)
                                        if prefix and Path(prefix, "uv-receipt.toml").exists() else None)):
            patch.start()
            self.addCleanup(patch.stop)

    def tending(self, tending: setup.Tending, *, quiet: bool = True) -> list[str]:
        said: list[str] = []
        tending.tend(Y, said.append, quiet=quiet)
        return said


class Moving(Handing):
    """Step 5: a server that runs from a shipped updater's folder hands over to the global cad's once install mode
    installed cad, and nothing is in flight; never to an older one."""

    def test_once_installed_and_quiet_the_records_name_the_tool_and_the_helper_starts(self) -> None:
        environment = self.tool("0.12.2")
        installations.register(Y, self.this)
        installations.point(Y)
        install_script.owe(Y)
        tending = setup.Tending()
        self.assertEqual(self.tending(tending), [], "install mode has not run: nothing")
        install_script._write({**install_script.read(), "attempts": 1, "outcome": "app", "installed": True})
        self.assertEqual(self.tending(tending, quiet=False), [], "work in flight: not yet")
        self.assertEqual(self.tending(tending), ["handing over to the global cad 0.12.2: this server stops, and "
                                                 "that cad starts the next"])
        [(command,)] = self.started
        told = json.loads(command[-1])
        self.assertEqual((told["cad"], told["target"], told["from"], told["prefix"]),
                         (str(environment / "bin" / "cad"), "0.12.2", Y, str(environment)))
        self.assertEqual(Path(told["record"]).name, setup.MOVE_RECORD)
        self.assertNotIn("auto-update.json", told["record"], "never cad's own update's record")
        current = installations.current()
        self.assertEqual((current["version"], current["prefix"]), ("0.12.2", str(environment)),
                         "a client of 0.11.10 that finds no server starts the uv tool's")
        self.assertEqual(self.record(Y)["prefix"], self.this[2], "the shipped updater's record stays")
        self.assertEqual(self.tending(tending), [], "once a server")

    def test_never_to_an_older_cad_nor_where_there_is_none(self) -> None:
        install_script._write({**install_script._new("install", Y, 0.0), "attempts": 1, "outcome": "done",
                               "state": "done", "installed": True})
        self.assertEqual(self.tending(setup.Tending()), ["no global cad was found: this server runs on"])
        self.tool("0.12.0")
        self.assertEqual(self.tending(setup.Tending()),
                         [f"the global cad 0.12.0 is older than this cad {Y}: this server runs on"])
        self.assertEqual(self.started, [])
        self.assertIsNone(installations.current_version())

    def test_a_pipx_global_cad_gets_a_helper_with_pipx_s_commands(self) -> None:
        environment = self.root / "pipx" / "venvs" / "cad"
        (environment / "lib" / "python3.14" / "site-packages" / "cad-0.12.2.dist-info").mkdir(parents=True)
        (environment / "bin").mkdir()
        for name in ("cad", "python"):
            (environment / "bin" / name).write_text("", encoding="utf-8")
        (environment / "pipx_metadata.json").write_text(json.dumps({"main_package": {"package": "cad"}}),
                                                        encoding="utf-8")
        install_script._write({**install_script._new("install", Y, 0.0), "attempts": 1, "outcome": "done",
                               "state": "done", "installed": True})
        with mock.patch.object(auto_update, "installed_tool", return_value=environment), \
                mock.patch.object(auto_update, "find_pipx", return_value=["/opt/pipx"]):
            self.assertEqual(self.tending(setup.Tending()), ["handing over to the global cad 0.12.2: this server "
                                                             "stops, and that cad starts the next"])
        [(command,)] = self.started
        told = json.loads(command[-1])
        self.assertEqual((told["cad"], told["target"], told["prefix"]),
                         (str(environment / "bin" / "cad"), "0.12.2", str(environment)))
        # pipx's upgrade inside this release's major, which the helper runs only where the global cad holds less than
        # the release it hands over to (here it holds it: nothing runs).
        self.assertEqual((told["upgrade"], told["launchers"]),
                         (["/opt/pipx", "upgrade", "cad", f"--pip-args=cad>={Y},<1"],
                          ["/opt/pipx", "environment", "--value", "PIPX_BIN_DIR"]))
        self.assertEqual(self.envs[0]["PIPX_HOME"], str(self.root / "pipx"), "pipx acts on this cad's folder")
        self.assertEqual(installations.current()["prefix"], str(environment))


class Carrying(Handing):
    """Step 4b: a server that runs from a shipped updater's folder, where nothing is owed or install mode's attempt
    installed nothing, installs cad globally on a thread, then hands over at the next quiet tending."""

    def setUp(self) -> None:
        super().setUp()
        self.installs: list[float] = []
        for patch in (mock.patch.object(sys, "prefix", str(self.state / "releases" / Y)),
                      mock.patch.dict(os.environ, {install_script.FIRST_ENV: "0"}),
                      mock.patch.object(tool_install, "install", side_effect=self.install)):
            patch.start()
            self.addCleanup(patch.stop)
        installations.register(Y, self.this)
        installations.point(Y)  # what the shipped switch does

    def install(self, *, timeout: float) -> list[str]:
        """uv's install, a stand-in: the uv tool cad 0.12.2 made."""
        self.installs.append(timeout)
        self.tool("0.12.2")
        return ["Installed 1 executable: cad"]

    def carried(self, tending: setup.Tending) -> list[str]:
        """One quiet tending, and the install it began waited for: what both said."""
        said = self.tending(tending)
        if tending.carrying is not None:
            tending.carrying.join(30)
        return said

    def test_it_installs_on_a_thread_then_hands_over_at_the_next_quiet_tending(self) -> None:
        tending = setup.Tending()
        self.assertEqual(self.carried(tending), [INSTALLING, "uv: Installed 1 executable: cad"])
        self.assertEqual(self.installs, [setup.CARRY_SECONDS])
        self.assertEqual(self.tending(tending, quiet=False), [], "work in flight: not yet")
        self.assertEqual(self.tending(tending), ["handing over to the global cad 0.12.2: this server stops, and that "
                                                 "cad starts the next"])
        self.assertEqual(json.loads(self.started[0][0][-1])["prefix"], str(self.root / "uv-tools" / "cad"))
        self.assertEqual(installations.current()["prefix"], str(self.root / "uv-tools" / "cad"))
        self.assertEqual((self.tending(tending), self.installs), ([], [setup.CARRY_SECONDS]), "once a server")
        self.assertIsNone(install_script.read(), "nothing owed: the install command never runs")

    def test_a_global_cad_already_there_is_moved_to_with_no_install(self) -> None:
        self.tool("0.12.2")
        tending = setup.Tending()
        self.assertEqual(self.carried(tending), [])
        self.assertIn("handing over to the global cad 0.12.2", self.tending(tending)[0])
        self.assertEqual(self.installs, [])

    def test_never_from_a_project_s_python_or_a_checkout(self) -> None:
        for prefix in (self.root / "project" / ".venv", self.root / "checkout" / ".venv", self.this[2]):
            with self.subTest(prefix=prefix), mock.patch.object(sys, "prefix", str(prefix)):
                tending = setup.Tending()
                self.assertEqual(self.carried(tending), [])
                self.assertIsNone(tending.carrying)
        installations.point(OLD)
        self.assertEqual(self.carried(setup.Tending()), [], "current names another release: the switch's to decide")
        self.assertEqual(self.installs, [])

    def test_not_while_install_mode_is_owed_and_after_an_attempt_that_installed_nothing(self) -> None:
        install_script.owe(Y)
        self.assertEqual(self.carried(setup.Tending()), [], "owed: install mode's to run")
        for outcome in (install_script.RUNNING, "no_report"):
            install_script._write({**install_script.read(), "attempts": 1, "outcome": outcome, "installed": False})
            tending = setup.Tending()
            self.carried(tending)
            self.assertEqual(self.installs, [] if outcome == install_script.RUNNING else [setup.CARRY_SECONDS], outcome)
        self.assertIn("handing over to the global cad 0.12.2", self.tending(tending)[0])
        self.assertEqual(install_script.read()["state"], "owed", "install mode still owed: the next server runs it")

    def test_where_nothing_moved_it_tries_again_a_day_later_and_at_each_start(self) -> None:
        def refused(*, timeout: float) -> list[str]:
            self.installs.append(timeout)
            raise tool_install.Failed("error: Executable already exists: cad")

        tending = setup.Tending()
        with mock.patch.object(tool_install, "install", side_effect=refused):
            self.assertEqual(self.carried(tending), [
                INSTALLING, "could not install cad with uv: error: Executable already exists: cad"])
        self.assertEqual(self.tending(tending), ["no global cad was found: this server runs on"])
        self.assertGreater(tending.next, time.monotonic() + install_script.DAY_SECONDS - 60)
        self.assertEqual((self.carried(tending), len(self.installs)), ([], 1), "not again within the day")
        self.assertEqual(self.carried(setup.Tending()), [INSTALLING, "uv: Installed 1 executable: cad"],
                         "a server's start: again")
        self.assertEqual(len(self.installs), 2)


class Once(Computer):
    """Step 7: a global install's server on a computer where our setup ran (``ours``), whose switch was never set, turns
    it on, then runs the install command once, detached."""

    def setUp(self) -> None:
        super().setUp()
        self.runs = self.root / "runs"
        stand_in = self.root / "install.py"
        # What the switch said when the command began, a line per run.
        stand_in.write_text("import json, sys\nkept = json.load(open(sys.argv[1], encoding='utf-8'))\n"
                            "open(sys.argv[2], 'a', encoding='utf-8').write(json.dumps(kept.get('plugin')) + '\\n')\n"
                            "print('installed')\n", encoding="utf-8")
        settings = self.state / "settings.json"
        for patch in (mock.patch.dict(os.environ, {install_script.INSTALLER_ENV:
                                                   f'"{sys.executable}" "{stand_in}" "{settings}" "{self.runs}"'}),
                      mock.patch.object(auto_update, "uv_tool", return_value=Path(self.this[2]))):  # a global install
            patch.start()
            self.addCleanup(patch.stop)

    def test_it_runs_once_with_the_switch_on_first(self) -> None:
        said: list[str] = []
        first, second = setup.Tending(), setup.Tending()  # a server, and the next
        for tending in (first, second):
            for _ in range(2):
                tending.tend(Y, said.append, quiet=True)
        self.assertIsNone(second.command)
        self.assertEqual(first.command.wait(60), 0)
        self.assertEqual(self.runs.read_text(encoding="utf-8").splitlines(), ['{"auto_update": true}'],
                         "once, the switch on before it began")
        self.assertTrue(auto_update.plugin_switch())
        self.assertIn("the install command set up this computer before: it runs once now, in the background", said)
        self.assertEqual((self.state / auto_update.INSTALL_LOG).read_text(encoding="utf-8"), "installed\n")

    def test_nothing_runs_where_the_switch_was_set_on_a_computer_not_ours_while_owed_or_not_global(self) -> None:
        for kept in (False, True):
            (self.state / "settings.json").write_text(json.dumps({"plugin": {"auto_update": kept}}), encoding="utf-8")
            self.assertFalse(setup.once(lambda line: None), kept)
            self.assertIs(auto_update.plugin_switch(), kept, "the person's switch left as it is")
        (self.state / "settings.json").unlink()
        install_script.owe(Y)
        self.assertFalse(setup.once(lambda line: None), "install mode owed: the Carrier's")
        (self.state / install_script.RECORD).unlink()
        with mock.patch.object(auto_update, "uv_tool", return_value=None):
            self.assertFalse(setup.once(lambda line: None), "not a global install")
        (self.state / "install-receipt.json").unlink()
        self.assertFalse(setup.once(lambda line: None), "not ours: a store's copy alone")
        self.assertFalse((self.state / "settings.json").exists(), "no switch written")
        self.assertFalse(self.runs.exists(), "the install command never ran")


class Following(Tool):
    """Step 6: a server of the uv tool points ``current`` and its record at itself, for the clients of 0.11.11 and
    earlier."""

    def test_it_points_them_where_they_name_another_and_never_past_a_later_release(self) -> None:
        said: list[str] = []
        with mock.patch.object(auto_update, "uv_tool", return_value=None):
            self.assertFalse(setup.follow(said.append), "no uv tool: nothing")
        with mock.patch.object(auto_update, "uv_tool", return_value=Path(self.this[2])):
            installations.point(OLD)
            self.assertTrue(setup.follow(said.append))
            self.assertEqual((installations.current_version(), self.record(Y)["prefix"]), (Y, self.this[2]))
            self.assertFalse(setup.follow(said.append), "named already")
            installations.register("0.13.0", (self.this[0], sys.executable, str(self.root / "later")))
            installations.point("0.13.0")
            self.assertFalse(setup.follow(said.append), "a later release's, alive: left")
            installations.point("0.13.1")
            self.assertTrue(setup.follow(said.append), "one that is gone: this one's")
            # 0.10.0's own folder, pointed at a release of ours by a take-over: followed too; 0.10.0's own, never.
            appdata = self.root / "cad-state"
            for named, followed in (("0.10.0", False), ("0.12.0", True)):
                Folder(appdata).write("installations/current", named.encode())
                installations.point(OLD)
                with mock.patch.object(places, "appdata_state_dir", return_value=appdata):
                    self.assertTrue(setup.follow(said.append))
                self.assertEqual(installations.current_version(Folder(appdata)), Y if followed else named)
        self.assertEqual(said[0], f"the clients of 0.11.11 and earlier start this cad {Y} where none runs")

    def test_a_server_of_pipx_s_cad_is_followed_too(self) -> None:
        installations.point(OLD)
        with mock.patch.object(auto_update, "uv_tool", return_value=None), \
                mock.patch.object(auto_update, "pipx_tool", return_value=Path(self.this[2])), \
                mock.patch.object(auto_update, "find_pipx", return_value=None):
            self.assertTrue(setup.follow(lambda line: None))
        self.assertEqual((installations.current_version(), self.record(Y)["prefix"]), (Y, self.this[2]))


class Arriving(unittest.TestCase):
    """``arrival``: how a release arrived, kept once by ``--engine-update``, where it came from, and each run of setup
    counted (``analytics.arrival``, as ``test_arrival`` shows the counting itself)."""

    def setUp(self) -> None:
        from cad_server._internal import telemetry_send
        from tests.python.packages.cad_server import test_arrival

        root = Path(os.path.realpath(tempfile.mkdtemp(prefix="cad-arrival-")))
        self.addCleanup(shutil.rmtree, root, True)
        for patch in (mock.patch.dict(os.environ, {**test_arrival.QUIET, "CAD_STATE_DIR": str(root / "state")}),
                      mock.patch.object(telemetry_send, "_spawn", lambda settings: None)):
            patch.start()
            self.addCleanup(patch.stop)
        self.settings = places.state_dir() / "settings.json"
        test_arrival.ArrivalTest.tell(self)
        self.kept = lambda: test_arrival.ArrivalTest.kept(self)

    def test_kept_once_where_it_came_from_and_counted(self) -> None:
        self.assertTrue(arrival.keep(Y, arrival.UPDATER, OLD, now=5.0))
        self.assertFalse(arrival.keep(Y, arrival.UPDATER, None, now=6.0), "an updater's second run keeps the first")
        self.assertEqual({key: arrival.read(Y)[key] for key in ("route", "from", "at")},
                         {"route": "updater", "from": OLD, "at": 5.0})
        self.assertIsNone(arrival.read("0.12.0"), "another release's")
        self.assertIsNone(arrival.came_from(Y), "nothing older on this computer")
        installations.point(OLD)
        self.assertEqual(arrival.came_from(Y), OLD, "the release current names")
        arrival.setup_ended(Y, "updater", OLD, "failed", "other")
        arrival.setup_ended(Y, "updater", OLD, "ok")  # not the run that kept its arrival: counted by that one
        arrival.setup_ended(Y, "updater", OLD, "ok", first=True)
        arrival.setup_ended(Y, "setup", OLD, "ok")  # `cad update` typed: each run
        self.assertEqual(self.kept(), [
            {"step": "setup", "route": "updater", "from": OLD, "outcome": "failed", "reason": "other"},
            {"step": "setup", "route": "updater", "from": OLD, "outcome": "ok"},
            {"step": "setup", "route": "setup", "from": OLD, "outcome": "ok"},
        ])


if __name__ == "__main__":
    unittest.main()
