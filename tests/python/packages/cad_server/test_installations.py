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

    def test_the_windows_proxy_is_a_cmd_with_the_same_marker(self) -> None:
        text = installations.script(True)
        self.assertIn(f"rem {installations.MARK}{installations.REVISION}\r\n", text)
        self.assertIn("-P -m cad_server._internal.proxy %*", text)
        installations.write_proxy(str(self.root / "bin"), windows=True)
        self.assertTrue((self.root / "bin" / "cad.cmd").is_file())

    def test_the_cmd_takes_the_python_from_its_record_line(self) -> None:
        # No Windows here to run it: for /f's split is simulated. With delims=" a run of quotes is
        # one delimiter and none starts the line, so the line's leading space is token 1.
        import re

        python = "C:\\Users\\a b\\AppData\\Local\\uv\\env\\Scripts\\python.exe"
        path, _status = installations.register("1.2.3", (python[:-10] + "cad.exe", python, "C:\\env"), self.state)
        text = installations.script(True)
        tokens, delimiter, needle = re.search(r'tokens\^=(\d+)\^ delims\^=\^(.) %%p in \(`findstr /c:"((?:\\"|[^"])*)" ',
                                              text).groups()
        needle = needle.replace('\\"', '"')  # findstr's escaped quote
        (line,) = [line for line in Path(path).read_text(encoding="utf-8").splitlines() if needle in line]
        fields = [field for field in line.split(delimiter) if field]
        found = fields[int(tokens) - 1]
        self.assertEqual(found.replace("\\\\", "\\"), python, "the cmd's !python:\\\\=\\! unescapes JSON's backslashes")
        self.assertIn("!python:\\\\=\\!", text)

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
        self.assertEqual(str(refused.exception), "text-to-cad is not installed: run `uvx --no-config --managed-python "
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

    def test_the_windows_proxy_reads_the_python_and_the_console_script_a_record_names(self) -> None:
        # No Windows runner executes the cmd: each for /f is checked against the record's own line, the
        # current installation's and then each registered one's. With delims set to a quote alone, cmd
        # skips empty pieces and keeps the indent as one.
        import re

        record = self.registered("1.0.0")
        lines = Path(record["path"]).read_text(encoding="utf-8").splitlines()
        text = installations.script(True)
        for named in ("!current!.json", "%%n"):
            reads = re.findall(r'tokens\^=(\d+)\^ delims\^=\^" %%(\w) in \(`findstr /c:"\\"(\w+)\\":" '
                               r'"!state!\\installations\\' + re.escape(named) + r'"`\) do set "(\w+)=%%\2"', text)
            self.assertEqual(sorted((key, name) for _taken, _letter, key, name in reads),
                             [("cad", "console"), ("python", "python")], named)
            for taken, _letter, key, _name in reads:
                (line,) = [row for row in lines if f'"{key}":' in row]
                pieces = [piece for piece in line.split('"') if piece]
                self.assertEqual(pieces[int(taken) - 1].replace("\\\\", "\\"), record[key])
        self.assertIn('set /p current=<"!state!\\installations\\current"', text)
        # Alive as alive() says it, as the sh does: an uninstalled server leaves its python.
        self.assertEqual(text.count('if exist "!python!" if exist "!console!" goto run'), 2)

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
