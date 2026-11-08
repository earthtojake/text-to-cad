"""The installations' registry, the current one, and the ``cad`` command that runs it
(``cad_server._internal.installations``, ``cad_server._internal.proxy``).

Each test writes into temporary folders from fake environments; none touches ~/.local/bin or the
user's state folder, and no engine runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad_server._internal import installations, proxy  # noqa: E402
from cad_server.engine.registry import Folder, Registry  # noqa: E402
from cad_server._internal import engine_host  # noqa: E402
from cad_mcp import host  # noqa: E402

POSIX = unittest.skipIf(os.name == "nt", "the proxy is an sh script on POSIX")


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.state = Folder(self.root / "state")

    def environment(self, name: str) -> tuple[str, str, str]:
        """A fake environment's console script, python and prefix."""
        scripts = self.root / name / "bin"
        scripts.mkdir(parents=True)
        console, python = scripts / "cad", scripts / "python"
        for path in (console, python):
            path.write_text("", encoding="utf-8")
        return str(console), str(python), str(self.root / name)

    def registered(self, version: str) -> dict:
        installations.register(version, self.environment(f"env-{version}"), self.state)
        (record,) = [found for found in installations.records(self.state) if found["version"] == version]
        return record


class RegistryTests(Fixture):
    def test_a_record_names_the_installation_and_is_rewritten_only_when_it_moves(self) -> None:
        found = self.environment("env")
        path, status = installations.register("1.2.3", found, self.state)
        self.assertEqual((Path(path), status), (self.root / "state/installations/1.2.3.json", installations.REGISTERED))
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual({key: record[key] for key in ("version", "cad", "python", "prefix")},
                         {"version": "1.2.3", "cad": found[0], "python": found[1], "prefix": found[2]})
        self.assertIn("registered", record)
        self.assertEqual(installations.register("1.2.3", found, self.state)[1], installations.OK)
        moved = self.environment("moved")  # the same version installed again elsewhere (a purged uv cache)
        self.assertEqual(installations.register("1.2.3", moved, self.state)[1], installations.REGISTERED)
        self.assertEqual(installations.records(self.state)[0]["python"], moved[1])

    def test_0_8_s_records_are_read_where_0_8_left_them_and_no_record_of_this_release_s_is_one(self) -> None:
        installations.register("0.10.0", self.environment("env-0.10"), self.state)
        earlier = self.root / "cadgen" / "installations"
        earlier.mkdir(parents=True)
        zero_eight = {"version": "0.8.4", "python": "/e/bin/python", "cadgen": "/e/bin/cadgen", "prefix": "/e"}
        (earlier / "0.8.4.json").write_text(json.dumps(zero_eight), encoding="utf-8")
        (earlier / "0.8.3.json").write_text(json.dumps({**zero_eight, "version": "0.8.2"}), encoding="utf-8")
        (earlier / "0.8.1.json").write_text("{", encoding="utf-8")
        (earlier / "current").write_text("0.8.4", encoding="utf-8")
        self.assertEqual(installations.earlier(self.root / "cadgen"), [{**zero_eight, "path": str(earlier / "0.8.4.json")}])
        # Side by side in one folder (a state folder a test names), each release reads its own records alone.
        (self.root / "state" / "installations" / "0.8.4.json").write_text(json.dumps(zero_eight), encoding="utf-8")
        self.assertEqual([record["version"] for record in installations.records(self.state)], ["0.10.0"])
        self.assertEqual([record["version"] for record in installations.earlier(self.root / "state")], ["0.8.4"])

    def test_an_upgrade_in_place_takes_over_its_environment_s_record(self) -> None:
        found = self.environment("tool")
        installations.register("0.8.0", found, self.state)
        installations.register("0.8.1", found, self.state)  # the same environment, upgraded
        self.registered("0.7.0")
        self.assertEqual(sorted(record["version"] for record in installations.records(self.state)), ["0.7.0", "0.8.1"],
                         "0.8.0's code is gone from it: no record names it")

    def test_prune_removes_only_records_whose_interpreter_is_gone(self) -> None:
        gone, live = self.registered("1.0.0"), self.registered("2.0.0")
        os.unlink(gone["python"])
        self.assertEqual(installations.prune(self.state), [gone["path"]])
        self.assertEqual([record["version"] for record in installations.records(self.state)], ["2.0.0"])
        self.assertTrue(Path(live["path"]).is_file())

    def test_a_source_tree_registers_nothing_unless_named(self) -> None:
        # These tests import the server from the checkout: the release's version is not theirs to register.
        with mock.patch.dict("os.environ", {installations.NAME_ENV: "", "CAD_STATE_DIR": str(self.root / "state")}):
            self.assertIsNone(installations.own_version())
        with mock.patch.dict("os.environ", {installations.NAME_ENV: "1.2.3-dev.4"}):
            self.assertEqual(installations.own_version(), "1.2.3-dev.4")

    def test_an_environment_runs_as_the_version_it_is_registered_as(self) -> None:
        """``python model.py`` run directly in a registered development environment, no variable set:
        its client, engine and workers go by the record's version (one door with the dev MCP server's
        engine), never the bare release that would outrank it. Unregistered: the release. The variable
        still wins, and a record of another release (an upgrade in place since) is not this code's."""
        import sys

        from cad.engine import places, previous

        release = previous.version()
        dev = f"{release}-dev.20261025032333"
        here = (str(self.root / "c"), str(self.root / "p"), sys.prefix)
        with mock.patch.dict("os.environ", {"CAD_STATE_DIR": str(self.root / "state")}):
            os.environ.pop(installations.NAME_ENV, None)
            self.assertEqual(places.installation(), release, "unregistered: the release")
            installations.register("0.0.1-dev.1", here)  # another release's record of this environment
            self.assertEqual(places.installation(), release)
            installations.register(dev, here)
            self.assertEqual((places.installation(), installations.own_version()), (dev, dev))
            os.environ[installations.NAME_ENV] = "9.9.9"
            self.assertEqual((places.installation(), installations.own_version()), ("9.9.9", "9.9.9"))

    def test_only_the_cad_apps_server_and_doctor_write(self) -> None:
        from cad_server import cli

        found = self.environment("env")
        named = {installations.NAME_ENV: "1.2.3", installations.DIR_ENV: str(self.root / "bin"),
                 "CAD_STATE_DIR": str(self.root / "state")}
        with mock.patch.dict("os.environ", named), mock.patch.object(installations, "targets", return_value=found):
            with mock.patch.object(cli, "_run", return_value=0), mock.patch.object(cli, "_tell"):
                self.assertEqual(cli._main(["status"]), 0)
            self.assertFalse((self.root / "bin").exists())
            self.assertEqual(installations.records(), [])
            installations.startup()  # the transport's registration, on a device with none (``cad_mcp.engine.register``)
            self.assertEqual([record["version"] for record in installations.records()], ["1.2.3"])
            self.assertEqual(installations.current()["version"], "1.2.3")
            self.assertEqual(installations.proxy_status(), installations.OK)

    def test_a_cad_apps_server_of_another_release_registers_nothing_where_one_is_current(self) -> None:
        """An app that moved its plugin ahead runs a newer server: it attaches to the current
        installation's engine, writes the command, and moves nothing."""

        self.registered("1.0.0")
        installations.point("1.0.0", self.state)
        named = {installations.NAME_ENV: "2.0.0", installations.DIR_ENV: str(self.root / "bin"),
                 "CAD_STATE_DIR": str(self.root / "state")}
        with mock.patch.dict("os.environ", named), \
                mock.patch.object(installations, "targets", return_value=self.environment("newer")):
            installations.startup()
            self.assertEqual([record["version"] for record in installations.records()], ["1.0.0"])
            self.assertEqual(installations.current()["version"], "1.0.0")
            self.assertEqual(installations.proxy_status(), installations.OK)


class CurrentTests(Fixture):
    def test_current_is_a_live_registered_installation_and_point_moves_it(self) -> None:
        self.registered("1.0.0")
        later = self.registered("2.0.0")
        self.assertIsNone(installations.current(self.state))
        installations.point("1.0.0", self.state)
        self.assertEqual(installations.current(self.state)["version"], "1.0.0")
        self.assertEqual((self.root / "state/installations/current").read_text(encoding="utf-8"), "1.0.0",
                         "the version alone, which cmd's set /p and sh's sed read as it is")
        installations.point("2.0.0", self.state)
        self.assertEqual(installations.current(self.state)["prefix"], later["prefix"])
        os.unlink(later["cad"])
        self.assertIsNone(installations.current(self.state), "an installation that is gone is no current one")
        self.assertEqual(installations.current_version(self.state), "2.0.0")
        with self.assertRaises(ValueError):
            installations.point("2.0.0; rm -rf /", self.state)

    def test_the_first_installation_becomes_current_once_and_a_development_install_on_purpose(self) -> None:
        self.registered("1.0.0")
        self.registered("2.0.0")
        self.assertTrue(installations.bootstrap("1.0.0", self.state))
        self.assertFalse(installations.bootstrap("2.0.0", self.state), "one is current: nothing moves it but a switch")
        self.assertEqual(installations.current(self.state)["version"], "1.0.0")
        with mock.patch.dict("os.environ", {"CAD_STATE_DIR": str(self.root / "state"),
                                            installations.DIR_ENV: str(self.root / "bin")}), \
                mock.patch.object(installations, "targets", return_value=self.environment("dev")):
            installations.setup("3.0.0-dev.1", make_current=True)  # a development install of a checkout
            self.assertEqual(installations.current()["version"], "3.0.0-dev.1")

    def test_the_current_release_writes_the_plugin_folder_as_it_registers_and_nothing_else_does(self) -> None:
        from cad_server._internal import plugin

        state = {"CAD_STATE_DIR": str(self.root / "state"), installations.DIR_ENV: str(self.root / "bin"),
                 installations.NAME_ENV: ""}
        with mock.patch.dict("os.environ", state), mock.patch.object(plugin, "write") as write, \
                mock.patch.object(installations, "editable", return_value=False), \
                mock.patch.object(installations, "targets", return_value=self.environment("release")):
            installations.setup("1.0.0")  # the device's first: current, a release's, so the folder is written
            self.assertEqual(installations.current()["version"], "1.0.0")
            write.assert_called_once_with()
            with mock.patch.object(installations, "targets", return_value=self.environment("other")):
                installations.setup("2.0.0")  # registered, not current: the folder stays the current one's
            self.assertEqual(write.call_count, 1)
            with mock.patch.object(installations, "editable", return_value=True):
                self.assertFalse(installations.write_plugin(), "a source tree writes it only when asked")
            with mock.patch.dict("os.environ", {installations.NAME_ENV: "1.0.0-dev.1"}):
                self.assertFalse(installations.write_plugin(), "a development install writes it only when asked")
            write.side_effect = plugin.Missing("no plugin")
            self.assertFalse(installations.write_plugin(), "never a failure of the registration it rides on")

    def test_a_folder_it_cannot_write_is_skipped_silently(self) -> None:

        blocked = self.root / "a-file"
        blocked.write_text("", encoding="utf-8")
        path, status, error = installations.write_proxy(str(blocked / "bin"))
        self.assertTrue(error)
        named = {installations.NAME_ENV: "1.2.3", installations.DIR_ENV: str(blocked / "bin"),
                 "CAD_STATE_DIR": str(blocked / "state")}
        with mock.patch.dict("os.environ", named), mock.patch.object(installations, "targets",
                                                                     return_value=self.environment("env")):
            installations.startup()  # it says nothing and raises nothing
            (_, _, unregistered), (_, _, unwritten) = installations.setup("1.2.3")
        self.assertTrue(unregistered and unwritten)


class ProxyFileTests(Fixture):
    def test_the_proxy_is_written_once_and_a_file_not_ours_is_left_alone(self) -> None:
        where = str(self.root / "bin")
        self.assertEqual(installations.write_proxy(where, windows=False)[1:], (installations.MISSING, None))
        path = installations.proxy_path(where, windows=False)
        self.assertEqual(Path(path).read_text(encoding="utf-8"), installations.script(False))
        self.assertTrue(os.access(path, os.X_OK))
        self.assertEqual(installations.write_proxy(where, windows=False)[1], installations.OK)
        Path(path).write_text(installations.script(False).replace("exit 1", "exit 2"), encoding="utf-8")
        self.assertEqual(installations.write_proxy(where, windows=False)[1], installations.STALE)
        later = installations.script(False).replace(f"{installations.MARK}{installations.REVISION}",
                                                    f"{installations.MARK}{installations.REVISION + 1}")
        Path(path).write_text(later, encoding="utf-8")
        self.assertEqual(installations.write_proxy(where, windows=False)[1], installations.NEWER)
        self.assertEqual(Path(path).read_text(encoding="utf-8"), later)
        Path(path).write_text("#!/bin/sh\nexec uv-tool-cadgen\n", encoding="utf-8")  # a person's own
        self.assertEqual(installations.write_proxy(where, windows=False)[1], installations.FOREIGN)
        self.assertEqual(Path(path).read_text(encoding="utf-8"), "#!/bin/sh\nexec uv-tool-cadgen\n")

    @POSIX
    def test_the_sh_runs_the_current_installation_else_the_one_registered_last(self) -> None:
        where = str(self.root / "bin")
        installations.write_proxy(where, windows=False)
        proxy_file = installations.proxy_path(where, windows=False)
        environment = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.root), "CAD_STATE_DIR": str(self.root / "state")}
        # None installed: the sh and the proxy say it in one wording, the command that installs it.
        none = subprocess.run([proxy_file, "status"], capture_output=True, text=True, env=environment)
        self.assertEqual((none.returncode, none.stderr.strip()), (1, proxy.NONE_INSTALLED))
        with self.assertRaises(proxy.Refused) as refused:
            proxy.choose(None, [])
        self.assertEqual(str(refused.exception), "cad-server is not installed: run `uvx --no-config --managed-python "
                                                 "--python 3.14 --from cad-server cad doctor` once, outside any "
                                                 "sandbox or with its permission")
        for version in ("1.0.0", "2.0.0"):
            record = self.registered(version)
            Path(record["python"]).write_text(f'#!/bin/sh\necho "{version}" "$@"\n', encoding="utf-8")
            os.chmod(record["python"], 0o755)
        os.utime(self.root / "state/installations/2.0.0.json", (1, 1))  # 1.0.0 registered last
        ran = subprocess.run([proxy_file, "export", "a b"], capture_output=True, text=True, env=environment,
                             cwd=self.root)
        self.assertEqual(ran.stdout, "1.0.0 -P -m cad_server._internal.proxy export a b\n", "no current: the last registered")
        installations.point("2.0.0", self.state)
        ran = subprocess.run([proxy_file, "status"], capture_output=True, text=True, env=environment, cwd=self.root)
        self.assertEqual(ran.stdout, "2.0.0 -P -m cad_server._internal.proxy status\n", "the current one")
        (self.root / "state/installations/current").write_text("2.0.0; echo planted", encoding="utf-8")
        ran = subprocess.run([proxy_file, "status"], capture_output=True, text=True, env=environment, cwd=self.root)
        self.assertEqual(ran.stdout, "1.0.0 -P -m cad_server._internal.proxy status\n", "a current that is no version is none")

    @POSIX
    def test_the_sh_passes_over_an_installation_whose_console_script_is_gone(self) -> None:
        where = str(self.root / "bin")
        installations.write_proxy(where, windows=False)
        environment = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.root), "CAD_STATE_DIR": str(self.root / "state")}
        for version in ("1.0.0", "2.0.0"):
            record = self.registered(version)
            Path(record["python"]).write_text(f'#!/bin/sh\necho "{version}"\n', encoding="utf-8")
            os.chmod(record["python"], 0o755)
        os.utime(self.root / "state/installations/1.0.0.json", (1, 1))  # 2.0.0 registered last...
        os.remove(record["cad"])  # ...and uninstalled from its environment: its python stays
        ran = subprocess.run([installations.proxy_path(where, windows=False), "status"], capture_output=True,
                             text=True, env=environment, cwd=self.root)
        self.assertEqual(ran.stdout, "1.0.0\n", ran.stderr)


class WindowsCommandTests(Fixture):
    """``cad.exe``: distlib's launcher, a shebang naming the command's own Python beside it, and a zip whose
    ``__main__.py`` chooses the installation. Written on any system; run for real on Windows alone."""

    def setUp(self) -> None:
        super().setUp()
        self.bin = str(self.root / "bin")
        self.exe = Path(installations.proxy_path(self.bin, windows=True))
        self.making = mock.patch.object(installations, "_make_interpreter", side_effect=self.interpreter)
        self.made = self.making.start()
        self.addCleanup(self.making.stop)

    def interpreter(self, folder: str) -> None:
        """The command's Python as uv makes it, without uv: a venv's python.exe and the home it names."""
        home = self.root / "home"
        home.mkdir(exist_ok=True)
        (home / "python.exe").write_bytes(b"MZ")
        Path(folder, "Scripts").mkdir(parents=True, exist_ok=True)
        Path(folder, "Scripts", "python.exe").write_bytes(b"MZ")
        Path(folder, "pyvenv.cfg").write_text(f"home = {home}\nversion_info = 3.14.0\n", encoding="utf-8")

    @staticmethod
    def exe_of(main: str) -> bytes:
        """A cad.exe of a launcher's shape whose ``__main__.py`` is ``main``."""
        import io
        import zipfile

        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("__main__.py", main)
        return b"MZ launcher\n#!C:\\uv\\tools\\cad-server\\Scripts\\python.exe\n" + stream.getvalue()

    def write(self) -> str:
        path, status, error = installations.write_proxy(self.bin, windows=True)
        self.assertEqual((path, error), (str(self.exe), None))
        return status

    def test_cad_exe_is_distlib_s_launcher_a_shebang_to_its_own_python_and_the_zip(self) -> None:
        import zipfile
        from importlib.resources import files

        self.assertEqual(self.write(), installations.MISSING)
        data = self.exe.read_bytes()
        stub = files("distlib").joinpath("t64.exe").read_bytes()
        self.assertTrue(data.startswith(stub), "pip's console launcher, as it ships in distlib")
        # The launcher runs `<its folder>\cad-launcher\Scripts\python.exe -I cad.exe <arguments>`: no state
        # folder in it, so every release and every state folder writes these same bytes.
        self.assertTrue(data[len(stub):].startswith(b"#!<launcher_dir>\\cad-launcher\\Scripts\\python.exe -I\n"))
        with zipfile.ZipFile(self.exe) as archive:
            self.assertEqual(archive.namelist(), ["__main__.py"])
            main = archive.read("__main__.py").decode("utf-8")
        self.assertEqual(main, installations.script(True))
        self.assertTrue(main.startswith(f"# {installations.MARK}{installations.REVISION}\n"))
        compile(main, "__main__.py", "exec")
        self.made.assert_called_once_with(str(self.root / "bin" / "cad-launcher"))
        self.assertEqual(self.write(), installations.OK)
        self.assertEqual(self.made.call_count, 1, "a Python that starts is never made again")

    def test_a_cad_exe_not_ours_is_left_alone_a_later_one_too_and_a_stale_one_rewritten(self) -> None:
        exe = self.exe_of
        self.exe.parent.mkdir()
        theirs = exe("import sys\nfrom cad_server.cli import main\nsys.exit(main())\n")  # `uv tool install cad-server`
        self.exe.write_bytes(theirs)
        self.assertEqual(self.write(), installations.FOREIGN)
        self.assertEqual(self.exe.read_bytes(), theirs)
        self.exe.write_bytes(b"MZ not a zip")
        self.assertEqual(self.write(), installations.FOREIGN)
        later = exe(installations.script(True).replace(f"{installations.MARK}{installations.REVISION}",
                                                       f"{installations.MARK}{installations.REVISION + 1}"))
        self.exe.write_bytes(later)
        self.assertEqual(self.write(), installations.NEWER)
        self.assertEqual(self.exe.read_bytes(), later)
        self.exe.write_bytes(exe(installations.script(True) + "# changed\n"))
        self.assertEqual(self.write(), installations.STALE)
        self.assertEqual(self.write(), installations.OK)

    def test_a_stub_of_another_distlib_is_still_this_revision_s_command(self) -> None:
        self.write()
        data = self.exe.read_bytes()
        archive = data[data.index(b"#!<launcher_dir>"):]
        self.exe.write_bytes(b"MZ another distlib's t64.exe" + archive)
        self.assertEqual(self.write(), installations.OK, "releases of other distlibs do not rewrite it in turn")

    def test_a_python_that_no_longer_starts_is_made_again_and_the_exe_kept(self) -> None:
        self.write()
        before = self.exe.stat().st_mtime_ns
        (self.root / "home" / "python.exe").unlink()  # uv's Python it was made of, uninstalled
        self.assertEqual(installations.proxy_status(str(self.exe), windows=True), installations.STALE)
        self.assertEqual(self.write(), installations.STALE)
        self.assertEqual(self.made.call_count, 2)
        self.assertEqual(self.exe.stat().st_mtime_ns, before, "the same bytes: cad.exe is not written again")
        self.assertEqual(self.write(), installations.OK)

    def test_a_running_cad_exe_is_set_aside_replaced_and_swept_by_a_later_write(self) -> None:
        self.write()
        self.exe.write_bytes(self.exe_of(installations.script(True) + "# the one running\n"))  # stale, and running:
        replace, remove = os.replace, os.remove

        def held_replace(source, target):  # Windows: a running program is never replaced...
            if os.fspath(target) == str(self.exe) and self.exe.exists():
                raise PermissionError(13, "Access is denied", str(target))
            return replace(source, target)

        def held_remove(path):  # ...nor removed, but it can be renamed
            if os.fspath(path).endswith(installations.ASIDE):
                raise PermissionError(13, "Access is denied", str(path))
            return remove(path)

        from cad._internal import atomic_replace

        with mock.patch.object(atomic_replace.os, "replace", side_effect=held_replace), \
                mock.patch.object(atomic_replace.time, "sleep"), \
                mock.patch.object(installations.os, "remove", side_effect=held_remove):
            self.assertEqual(self.write(), installations.STALE)
        self.assertEqual(installations.proxy_status(str(self.exe), windows=True), installations.OK)
        (aside,) = [name for name in os.listdir(self.bin) if name.endswith(installations.ASIDE)]
        self.assertRegex(aside, r"^cad\.exe\.[0-9a-f]{8}\.old$")
        self.assertIn(b"# the one running", (self.root / "bin" / aside).read_bytes(), "the running one, set aside")
        self.assertEqual([name for name in os.listdir(self.bin) if name.endswith(".tmp")], [])
        self.assertEqual(self.write(), installations.OK)  # it ended: the next write removes it
        self.assertFalse((self.root / "bin" / aside).exists())

    def test_the_cad_cmd_before_goes_at_the_write_after_cad_exe_is_in_place(self) -> None:
        self.exe.parent.mkdir()
        earlier = self.exe.parent / "cad.cmd"
        earlier.write_text("@echo off\r\nrem cad proxy: 9\r\n", encoding="utf-8")
        self.assertEqual(installations.earlier_command(self.bin), str(earlier))
        self.assertEqual(self.write(), installations.MISSING)
        self.assertTrue(earlier.exists(), "a cad update through cad.cmd still has cmd reading it")
        self.assertEqual(self.write(), installations.OK)
        self.assertFalse(earlier.exists())
        earlier.write_text("@echo off\r\nrem a person's own\r\n", encoding="utf-8")
        self.write()
        self.assertTrue(earlier.exists(), "a cad.cmd not ours stays")
        self.assertIsNone(installations.earlier_command(self.bin))

    def test_an_uninstall_takes_cad_exe_its_python_and_the_cad_cmd_before(self) -> None:
        self.write()
        (self.exe.parent / "cad.cmd").write_text("@echo off\r\nrem cad proxy: 9\r\n", encoding="utf-8")
        remove = os.remove

        def held_remove(path):  # the cad.exe this uninstall runs through
            if os.path.basename(os.fspath(path)).startswith("cad.exe"):
                raise PermissionError(13, "Access is denied", str(path))
            return remove(path)

        with mock.patch.object(installations.os, "remove", side_effect=held_remove):
            removed, left = installations.remove_proxy(self.bin, windows=True)
        self.assertEqual(sorted(removed), sorted([str(self.exe), str(self.exe.parent / "cad.cmd"),
                                                  installations.interpreter_folder(self.bin)]))
        (aside,) = left
        self.assertRegex(os.path.basename(aside), r"^cad\.exe\.[0-9a-f]{8}\.old$")
        self.assertEqual(sorted(os.listdir(self.bin)), [os.path.basename(aside)], "no cad command is left")

    @POSIX
    def test_its_main_runs_the_current_installation_else_the_one_registered_last_with_the_arguments_as_given(self) -> None:
        import sys

        self.write()
        environment = {"PATH": os.environ.get("PATH", ""), "CAD_STATE_DIR": str(self.root / "state")}

        def run(*args: str) -> subprocess.CompletedProcess:
            # The launcher's own command line: its Python, -I, the exe itself, then the arguments (and -S:
            # the command's Python has nothing installed).
            return subprocess.run([sys.executable, "-I", "-S", str(self.exe), *args], capture_output=True, text=True,
                                  env=environment, cwd=self.root)

        none = run("status")
        self.assertEqual((none.returncode, none.stderr.strip()), (1, proxy.NONE_INSTALLED))
        for version in ("1.0.0", "2.0.0"):
            record = self.registered(version)
            Path(record["python"]).write_text(f'#!/bin/sh\nprintf "%s|" "{version}" "$@"\nexit 3\n', encoding="utf-8")
            os.chmod(record["python"], 0o755)
        os.utime(self.root / "state/installations/2.0.0.json", (1, 1))  # 1.0.0 registered last
        arguments = ["run", "--with", "pandas>=2", "a&b %PATH% ^!<c>|d.py", 'say "é"']
        ran = run(*arguments)
        self.assertEqual(ran.stdout, "|".join(["1.0.0", "-P", "-m", "cad_server._internal.proxy", *arguments]) + "|",
                         "no current: the last registered, each argument one, as given")
        self.assertEqual(ran.returncode, 3, "the installation's exit status")
        installations.point("2.0.0", self.state)
        self.assertTrue(run("status").stdout.startswith("2.0.0|"), "the current one")
        (self.root / "state/installations/current").write_text("2.0.0; echo planted", encoding="utf-8")
        self.assertTrue(run("status").stdout.startswith("1.0.0|"), "a current that is no version is none")
        installations.point("2.0.0", self.state)
        os.remove(record["cad"])  # 2.0.0 uninstalled from its environment: its python stays
        self.assertTrue(run("status").stdout.startswith("1.0.0|"))

    @unittest.skipUnless(os.name == "nt", "cad.exe runs on Windows")
    def test_on_windows_cad_exe_runs_this_installation_with_the_arguments_as_given(self) -> None:
        self.making.stop()  # the real one: uv makes the command's Python
        self.addCleanup(self.making.start)
        self.assertEqual(self.write(), installations.MISSING)
        python = os.path.join(self.bin, "cad-launcher", "Scripts", "python.exe")
        self.assertTrue(os.path.isfile(python))
        self.assertFalse((self.root / "home").exists(), "uv made it, not the test's stand-in")
        ran = subprocess.run([str(self.exe), "--version"], capture_output=True, text=True, encoding="utf-8")
        # The current installation of the runner's state folder: this interpreter, by the version it is
        # registered as, which the proxy tells it.
        current = installations.current()
        self.assertIsNotNone(current)
        self.assertEqual((ran.returncode, ran.stdout.strip()), (0, f"cad {current['version']}"), ran.stderr)
        # cmd parsed these: `>` and `|` redirected, `&` split the line, `^` and `!` went, `%PATH%` expanded.
        odd = 'a&b>c|d ^e !f! %PATH% "g"'
        ran = subprocess.run([str(self.exe), odd], capture_output=True, text=True, encoding="utf-8", cwd=self.root)
        self.assertEqual(ran.returncode, 2, ran.stderr)
        self.assertIn(f"cad: unknown command {odd!r}", ran.stderr)
        self.assertFalse((self.root / "c").exists(), "nothing was redirected")


class ResolutionTests(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.old, self.new, self.dev = self.registered("0.8.0"), self.registered("0.9.0"), self.registered("0.9.0-dev.20261024")
        self.records = installations.records(self.state)

    def test_the_current_installation_runs(self) -> None:
        installations.point("0.8.0", self.state)
        self.assertEqual(proxy.choose(installations.current(self.state), self.records)["version"], "0.8.0")

    def test_with_none_current_the_installation_registered_last_runs(self) -> None:
        stamped = [{**record, "registered": f"2026-10-0{index}"} for index, record in enumerate(self.records, 1)]
        self.assertEqual(proxy.choose(None, stamped)["version"], stamped[-1]["version"])
        os.unlink(stamped[-1]["python"])
        self.assertEqual(proxy.choose(None, stamped)["version"], stamped[-2]["version"],
                         "an installation that is gone is passed over")

    def test_a_shell_whose_folder_was_removed_still_resolves(self) -> None:
        with mock.patch("os.getcwd", side_effect=FileNotFoundError(2, "No such file or directory")), \
                mock.patch("cad_server._internal.installations.records", return_value=[]), \
                mock.patch("cad_server._internal.installations.current", return_value=None):
            self.assertEqual(proxy.main(["status"]), 1, "refused in its line, never a traceback")

    def test_every_verb_run_too_execs_the_current_installations_console_script(self) -> None:
        # ``cad run`` is the installation's verb: it runs the script in its CAD kernel environment.
        self.assertEqual(proxy.command(self.old, ["run", "model.py", "--force"]),
                         [self.old["cad"], "run", "model.py", "--force"])
        installations.point("0.8.0", self.state)
        run = [self.old["cad"], "run", "model.py", "a"]
        with mock.patch.dict("os.environ", {"CAD_STATE_DIR": str(self.root / "state")}), \
                mock.patch.object(proxy.os, "execve") as execve, \
                mock.patch("subprocess.call", return_value=3) as call:
            code = proxy.main(["run", "model.py", "a"])
        if os.name == "nt":  # no exec on Windows: the installation's cad is a child, its exit code the proxy's
            call.assert_called_once_with(run, env=mock.ANY)
            self.assertEqual((code, execve.call_count), (3, 0))
        else:
            execve.assert_called_once_with(self.old["cad"], run, mock.ANY)
            self.assertEqual(call.call_count, 0)

    def test_a_development_installation_is_told_its_version_and_a_release_is_not(self) -> None:
        """A dev or source registration reports its release's version: the proxy names it, in the
        environment of what it runs (and its children, the same installation). A release knows its
        own, and a name a dev installation's process passed down is taken off."""
        ran = {}

        def child(argv, env):  # Windows runs the installation as a child rather than exec
            ran.update({argv[0]: dict(env)})
            return 0

        with mock.patch.dict("os.environ", {"CAD_STATE_DIR": str(self.root / "state"),
                                            installations.NAME_ENV: "0.9.0-dev.1"}), \
                mock.patch.object(proxy.os, "execve", side_effect=lambda path, argv, env: ran.update({path: dict(env)})), \
                mock.patch("subprocess.call", side_effect=child):
            installations.point("0.9.0-dev.20261024")
            proxy.main(["doctor"])
            installations.point("0.8.0")
            proxy.main(["doctor"])
        self.assertEqual(ran[self.dev["cad"]][installations.NAME_ENV], "0.9.0-dev.20261024")
        self.assertNotIn(installations.NAME_ENV, ran[self.old["cad"]])
        self.assertEqual([installations.named(record) for record in (self.old, self.new, self.dev)],
                         [None, None, "0.9.0-dev.20261024"])

    def test_the_shell_names_its_host(self) -> None:
        self.assertEqual(engine_host.shell({"CODEX_THREAD_ID": "t", "CLAUDECODE": "1"}), "codex")
        self.assertEqual(engine_host.shell({"CLAUDECODE": "1"}), "claude code")
        self.assertIsNone(engine_host.shell({}))
        self.assertEqual(host.family({"host": "codex app-server"}), "codex")
        self.assertEqual(host.family({"host": "claude code"}), "claude code")
        self.assertIsNone(host.family(None))


class TokenTests(unittest.TestCase):
    def test_the_page_token_is_one_file_the_users_alone(self) -> None:
        import re

        with TemporaryDirectory() as scratch:
            held = Registry(scratch)
            self.assertIsNone(held.token())
            held.put_token("t" * 43)
            self.assertEqual(held.token(), "t" * 43)
            path = Path(scratch) / "engines" / "token"
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_bytes(b"short\n")
            with self.assertRaisesRegex(ValueError, rf"^the page token {re.escape(str(path))} holds no token "
                                                    r"\(6 bytes\): remove it to make a new one"):
                held.token()  # a token too short to guard anything is refused, never taken for none
            path.write_text("t" * 40 + "\r\nSet-Cookie: x=y\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, rf"^the page token {re.escape(str(path))} holds no token"):
                held.token()  # only a token's characters: it goes into a cookie
            held.put_token("u" * 43)
            if os.name != "nt":
                os.chmod(path, 0o644)  # readable by others, as in a state folder others share
                with self.assertRaisesRegex(ValueError, rf"^the page token {re.escape(str(path))} is not this "
                                                        r"user's alone \(mode 0644\)"):
                    held.token()  # a token others can read guards nothing, and is never served
                os.chmod(path, 0o600)
                with mock.patch("os.getuid", return_value=os.getuid() + 1):
                    with self.assertRaisesRegex(ValueError, r"is not this user's alone \(mode 0600, owned by uid"):
                        held.token()  # another user's token file is not this user's token
            self.assertEqual(held.token(), "u" * 43)
            self.assertEqual(path.read_text(encoding="utf-8"), "u" * 43 + "\n", "refused, never replaced")

    def test_the_first_engine_makes_the_token_and_another_starting_with_it_serves_that_one(self) -> None:
        from cad_server.engine import daemon

        with TemporaryDirectory() as scratch:
            held = Registry(scratch)
            self.assertTrue(held.make_token("a" * 43))
            self.assertFalse(held.make_token("b" * 43), "never made over one that is there")
            self.assertEqual(held.token(), "a" * 43)
            if os.name != "nt":
                self.assertEqual((Path(scratch) / "engines" / "token").stat().st_mode & 0o777, 0o600)
            # An engine that found none, then lost the making to this one: it serves this one's.
            self.assertEqual(daemon._new_token(held), "a" * 43)
            self.assertEqual(held.token(), "a" * 43)
            self.assertEqual(os.listdir(Path(scratch) / "engines"), ["token"], "nothing of its own left beside it")

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "a file's mode is POSIX's, and refuses no one running as root")
    def test_a_token_that_cannot_be_read_is_refused_by_name_and_never_replaced(self) -> None:
        import re

        from cad_server.engine import daemon

        with TemporaryDirectory() as scratch:
            held = Registry(scratch)
            held.put_token("a" * 43)
            path = Path(scratch) / "engines" / "token"
            path.chmod(0)
            try:
                for call in (held.token, lambda: daemon._new_token(held)):
                    with self.assertRaisesRegex(ValueError, rf"^the page token {re.escape(str(path))} cannot be read "
                                                            r"\(Permission denied, mode 0000\): make it this user's"):
                        call()
            finally:
                path.chmod(0o600)
            self.assertEqual(path.read_text(encoding="utf-8"), "a" * 43 + "\n", "left as it was: every link still works")


if __name__ == "__main__":
    unittest.main()
