"""A pinned command, ``cad +<version>[@<name>] ...``: the ``cad`` command that reads the pin first (the sh and the
Windows main, ``cad_server._internal.installations``), the version that reads it then (``pins``, ``cli``), and what
a version's command says after its output (the update notice, ``cli._notice``) and records (its use).

The command runs for real against a device in a temporary folder whose versions are stubs: a version's code
marker names a ``python`` that runs what it is given and a ``cad`` that says which version it is, the name it was
told and its arguments. uv is a stub on a PATH of the test's own, which records any run: the command never runs it.
The Windows main is run by this Python on any system.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

import cad_server  # noqa: E402
from cad.engine import places  # noqa: E402
from cad_server import cli, updates  # noqa: E402
from cad_server._internal import extras, imports, installations, pins, proxy, versions  # noqa: E402
from cad_server._internal.cli_errors import REASONS, Failure  # noqa: E402

STUBS = unittest.skipIf(os.name == "nt", "the stub programs are sh scripts")
X, OLDER, NEWER, DEV = "0.12.0", "0.11.20", "0.13.0", "0.12.0-dev.20261113000000"


class Device(unittest.TestCase):
    """A device: its state folder (with a space in its path, as macOS's has), a home, and the cad command."""

    def setUp(self) -> None:
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="cad-pins-")))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state = self.root / "Application Support" / "cad"
        self.state.mkdir(parents=True)
        self.bin = self.root / "bin"  # the test's PATH: the uvx stub, when there is one
        self.bin.mkdir()
        self.uvx_log = self.root / "uvx.log"
        sh = self.root / "cad"
        sh.write_text(installations.script(windows=False), encoding="utf-8")
        sh.chmod(0o755)
        main = self.root / "main.py"
        main.write_text(installations.script(windows=True), encoding="utf-8")
        self.commands = {"sh": [str(sh)], "windows": [sys.executable, "-I", str(main)]}

    # --- the device ----------------------------------------------------------------------------------------

    def version(self, name: str, where: Path | None = None) -> None:
        """Version ``name`` installed (in the versions' folder ``where`` names, by default the device's)."""
        code = (where or self.state / "versions") / name / "code"
        scripts = code / "server" / "bin"
        scripts.mkdir(parents=True)
        python, cad = scripts / "python", scripts / "cad"
        # The sh runs ``python cad ARGS``; the Windows main runs ``cad ARGS``.
        python.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
        cad.write_text(f'#!/bin/sh\necho "{name} ${{CAD_INSTALLATION_VERSION-unset}} $*"\n', encoding="utf-8")
        python.chmod(0o755)
        cad.chmod(0o755)
        final = self.state / "versions" / name / "code" / "server" / "bin"
        record = {"schema": places.VERSION_SCHEMA, "version": name, "python": str(final / "python"),
                  "cad": str(final / "cad"), "prefix": str(final.parent)}
        # As ``versions.make_present`` writes it: a key a line, its paths as they are.
        (code / places.VERSION_MARKER).write_text(json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False)
                                                  + "\n", encoding="utf-8")

    def uvx(self, *, installs: str | None = None, fails: str | None = None) -> None:
        """uv's stub: it records how it was run (and the name it was told), then installs version ``installs`` --
        staged, copied in as ``cad setup`` would make it -- or fails saying ``fails``. The ``cad`` command never runs
        it: it is here to prove so."""
        staged = self.root / "staged"
        lines = ["#!/bin/sh", f'echo "${{CAD_INSTALLATION_VERSION-unset}} $*" >> "{self.uvx_log}"']
        if installs is not None:
            self.version(installs, staged)
            lines += ['echo "Installed 40 packages in 300ms" >&2', f'mkdir -p "$CAD_STATE_DIR/versions"',
                      f'cp -R "{staged / installs}" "$CAD_STATE_DIR/versions/"']
        if fails is not None:
            lines += [f'echo "{fails}" >&2', "", "exit 2"]
        (self.bin / "uvx").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (self.bin / "uvx").chmod(0o755)

    def cad(self, how: str, *args: str, **environment: str) -> subprocess.CompletedProcess:
        """The cad command (``how``: ``sh`` or ``windows``) run with ``args`` on this device."""
        env = {"PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(self.root),
               "CAD_STATE_DIR": str(self.state), **environment}
        return subprocess.run([*self.commands[how], *args], capture_output=True, text=True, env=env, cwd=self.root)

    def uv_runs(self) -> list[str]:
        return self.uvx_log.read_text(encoding="utf-8").splitlines() if self.uvx_log.exists() else []

    def both(self, check) -> None:
        """``check(how)`` for the sh and the Windows main, each on a fresh device."""
        for how in ("sh", "windows"):
            with self.subTest(how=how):
                self.setUp()
                check(how)


@STUBS
class TheCommand(Device):
    def ran(self, done: subprocess.CompletedProcess, line: str) -> None:
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, line + "\n", ""))

    def refused(self, done: subprocess.CompletedProcess, code: int, words: str) -> None:
        self.assertEqual((done.returncode, done.stdout, done.stderr), (code, "", f"cad: {words}\n"))

    def test_a_pinned_version_installed_runs_exactly_it_whatever_else_is_installed(self) -> None:
        def check(how: str) -> None:
            self.uvx(installs=X)
            for name in (OLDER, X, NEWER):
                self.version(name)
            # Older or newer than the others, with a name or without: that version's own cad reads the pin.
            for word in (f"+{X}", f"+{X}@store", f"+{X}@default", f"+{OLDER}@codex"):
                name = word[1:].split("@")[0]
                self.ran(self.cad(how, word, "status", "a b", "$HOME"), f"{name} unset {word} status a b $HOME")
            # A release is told no name, whatever this shell inherited (a daemon's children carry one).
            self.ran(self.cad(how, f"+{X}", "run", CAD_INSTALLATION_VERSION="0.9.0"), f"{X} unset +{X} run")
            self.assertEqual(self.uv_runs(), [])

        self.both(check)

    def test_a_pin_not_installed_says_so_and_installs_nothing_names_no_command_and_uses_no_network(self) -> None:
        def check(how: str) -> None:
            self.uvx(installs=X)  # uv there and able: never run
            self.version(NEWER)
            for word in (f"+{X}", f"+{X}@store", f"+{DEV}"):
                done = self.cad(how, word, "status")
                self.refused(done, 3, pins.not_installed(word[1:].split("@")[0]))
                self.assertEqual(done.stderr, f"cad: cad {word[1:].split('@')[0]} is not installed on this "
                                              "computer.\n")
            self.assertEqual(self.uv_runs(), [], "nothing installed")
            self.assertFalse((self.state / "versions" / X).exists())

        self.both(check)

    def test_a_development_version_runs_by_its_record_told_its_name(self) -> None:
        def check(how: str) -> None:
            self.version(DEV)
            self.ran(self.cad(how, f"+{DEV}", "status"), f"{DEV} {DEV} +{DEV} status")

        self.both(check)

    def test_a_word_that_is_no_pin_or_names_no_channel_is_refused(self) -> None:
        def check(how: str) -> None:
            self.version(X)
            for word in ("+", "+abc", "+.1", "+0.12.0;rm", "+@store"):
                self.refused(self.cad(how, word, "status"), REASONS["bad_pin"], pins.bad_pin(word))
            for word in (f"+{X}@", f"+{X}@Store", f"+{X}@-x", f"+{X}@a@b", f"+{X}@{'a' * 33}"):
                self.refused(self.cad(how, word, "status"), REASONS["bad_pin"], pins.bad_channel(word))
            self.ran(self.cad(how, f"+{X}@{'a' * 32}", "status"), f"{X} unset +{X}@{'a' * 32} status")

        self.both(check)

    def test_no_pin_runs_the_newest_installed_and_a_later_release_by_the_same_rules(self) -> None:
        def check(how: str) -> None:
            done = self.cad(how, "status")
            self.refused(done, 3, pins.none_installed())
            self.assertEqual(done.stderr, "cad: cad is not installed on this computer.\n")
            self.version("0.9.0")
            self.version(X)
            self.ran(self.cad(how, "status"), f"{X} unset status")  # the newest installed, by its numbers
            (self.state / "versions" / "0.99.0" / "code").mkdir(parents=True)  # an install cut short: not installed
            self.ran(self.cad(how, "status", "x"), f"{X} unset status x")
            self.version(DEV)  # a development build of X: newer than X
            self.ran(self.cad(how, "status"), f"{DEV} {DEV} status")
            # A release made after this command was written, laid out as every version is: run by the same rules.
            self.version(NEWER)
            self.ran(self.cad(how, "status"), f"{NEWER} unset status")
            self.ran(self.cad(how, f"+{NEWER}", "status"), f"{NEWER} unset +{NEWER} status")
            self.assertEqual(self.uv_runs(), [])

        self.both(check)

    def test_both_order_versions_as_the_versions_do(self) -> None:
        # A10: the sh, the Windows main and ``versions.order`` agree on every name a release or a development build
        # has (``X.Y.Z``, ``X.Y.Z-dev.<stamp>``), a development build after its own release and before the next.
        names = ["0.9.0", "0.11.10", "0.11.11", "0.12", "0.12.0", "0.12.1", "1.0.0", "10.0.0", "0.99.99",
                 "0.12.0-dev.20261113000000", "0.12.0-dev.20261114000000", "0.12.1-dev.20261101000000"]
        main: dict = {}  # the Windows main's functions, its last line (which runs it) left out
        exec(compile(installations.script(windows=True).replace("sys.exit(main())", ""), "main", "exec"), main)
        body = installations.script(windows=False).split("\nolder() {\n", 1)[1].split("\n}\n", 1)[0]
        program = f'older() {{\n{body}\n}}\nolder "$1" "$2"'  # the sh's function alone
        shells = [shell for shell in ("sh", "dash") if shutil.which(shell)]
        for one in names:
            for other in names:
                expected = versions.older(one, other)
                with self.subTest(one=one, other=other):
                    self.assertEqual(main["older"](one, other), expected)
                    for shell in shells:
                        done = subprocess.run([shell, "-c", program, shell, one, other])
                        self.assertEqual(done.returncode == 0, expected, shell)

    def test_a_state_folder_with_quotes_and_backslashes_in_its_path_runs(self) -> None:
        # A release is run from where every release puts its Python and cad, no path parsed; a development version's
        # read with JSON's escapes undone.
        self.state = self.root / 'odd "quoted" \\ back' / "cad"
        self.state.mkdir(parents=True)
        self.version(X)
        self.ran(self.cad("sh", f"+{X}", "status"), f"{X} unset +{X} status")
        self.ran(self.cad("sh", "status"), f"{X} unset status")
        self.version(DEV)
        self.ran(self.cad("sh", f"+{DEV}", "status"), f"{DEV} {DEV} +{DEV} status")

    def test_the_command_of_0_11_10_s_layout_says_this_command_s_words(self) -> None:
        self.assertEqual(proxy.NONE_INSTALLED, f"cad: {pins.none_installed()}")


class AnOlderReleaseNeverRewritesIt(unittest.TestCase):
    def test_a_writer_of_an_earlier_revision_finds_this_one_newer_and_leaves_it(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for windows in (False, True):
                path = Path(installations.proxy_path(folder, windows=windows))
                data = installations.script(False).encode() if not windows else _exe(installations.script(True))
                path.write_bytes(data)
                with mock.patch.object(installations, "REVISION", installations.REVISION - 1):  # 0.11.11's writer
                    self.assertEqual(installations.proxy_status(str(path), windows=windows), installations.NEWER)
                    self.assertEqual(installations.write_proxy(folder, windows=windows)[1], installations.NEWER)
                self.assertEqual(path.read_bytes(), data)


def _exe(main: str) -> bytes:
    import zipfile

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("__main__.py", main)
    return b"MZ launcher\n" + stream.getvalue()


# --- the version that reads the pin -------------------------------------------------------------------------


class Reading(unittest.TestCase):
    def test_parse_and_take(self) -> None:
        self.assertEqual(pins.parse(f"+{X}"), pins.Pin(X, None, f"+{X}"))
        self.assertEqual(pins.parse(f"+{X}@default").channel, None)
        self.assertEqual(pins.parse(f"+{DEV}@store").channel, "store")
        self.assertEqual(pins.take([f"+{X}@store", "status", "+x"]), (pins.Pin(X, "store", f"+{X}@store"),
                                                                      ["status", "+x"]))
        self.assertEqual(pins.take(["status"]), (None, ["status"]))
        for word, words in (("+abc", pins.bad_pin("+abc")), (f"+{X}@", pins.bad_channel(f"+{X}@"))):
            with self.assertRaises(Failure) as refused:
                pins.take([word, "status"])
            self.assertEqual((str(refused.exception), refused.exception.status), (words, 2))


class TheParser(unittest.TestCase):
    """The real ``cad`` reading a pin: its own version's accepted, another's refused."""

    def setUp(self) -> None:
        folder = tempfile.mkdtemp(prefix="cad-pins-")
        self.addCleanup(shutil.rmtree, folder, True)
        for patch in (mock.patch.dict(os.environ, {"CAD_STATE_DIR": folder, places.INSTALLATION_ENV: DEV}),
                      mock.patch.object(places, "_channel", None)):
            patch.start()
            self.addCleanup(patch.stop)
        places._versioned.cache_clear()
        self.addCleanup(places._versioned.cache_clear)

    def main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_its_own_version_s_pin_is_read_and_its_channel_is_the_command_s(self) -> None:
        self.assertEqual(self.main(f"+{DEV}@store", "--version"), (0, f"cad {DEV}\n", ""))
        self.assertEqual(places.channel(), "store")

    def test_another_version_s_pin_is_refused_in_one_line(self) -> None:
        self.assertEqual(self.main(f"+{X}", "status"), (5, "", f"cad: {pins.other_version(DEV, X)}\n"))
        code, out, _ = self.main(f"+{X}@store", "status", "--json")
        self.assertEqual((code, json.loads(out)["reason"]), (5, "other_version"))
        self.assertEqual(self.main("+0.12.0@Bad", "status")[0], 2)
        self.assertEqual(places.channel(), "default", "a refused pin names no channel")


class ACommandOfAVersion(unittest.TestCase):
    """What a version's own ``cad`` does around a command: its use recorded, its data copied in first where it is not
    there yet, and, after the command's output, the update notice."""

    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp(prefix="cad-pins-"))
        self.addCleanup(shutil.rmtree, self.state, True)
        for patch in (mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state), places.INSTALLATION_ENV: DEV,
                                                   "CAD_UPDATE_CHECK": "", "CI": ""}),
                      mock.patch.object(places, "_channel", None), mock.patch.object(places, "HOME", None)):
            patch.start()
            self.addCleanup(patch.stop)
        places._versioned.cache_clear()
        self.addCleanup(places._versioned.cache_clear)

    def main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def installed(self, name: str) -> Path:
        """Version ``name``'s code marker, as ``versions.make_present`` writes it (its environment this Python's)."""
        code = self.state / "versions" / name / "code"
        code.mkdir(parents=True)
        record = {"schema": places.VERSION_SCHEMA, "version": name, "python": sys.executable, "cad": sys.executable,
                  "prefix": sys.prefix}
        (code / places.VERSION_MARKER).write_text(json.dumps(record), encoding="utf-8")
        places._versioned.cache_clear()
        return self.state / "versions" / name

    def test_its_own_version_s_pin_is_read_and_its_name_is_the_command_s_channel(self) -> None:
        self.assertEqual(self.main(f"+{DEV}@store", "--version"), (0, f"cad {DEV}\n", ""))
        self.assertEqual(places.channel(), "store")

    def test_another_version_s_pin_is_refused_in_one_line(self) -> None:
        self.assertEqual(self.main(f"+{X}", "status"), (5, "", f"cad: {pins.other_version(DEV, X)}\n"))
        code, out, _ = self.main(f"+{X}@store", "status", "--json")
        self.assertEqual((code, json.loads(out)["reason"]), (5, "other_version"))
        self.assertEqual(self.main("+0.12.0@Bad", "status")[0], 2)
        self.assertEqual(places.channel(), "default", "a refused pin names no channel")

    def test_a_command_records_its_version_s_use_and_copies_its_data_in_first(self) -> None:
        folder = self.installed(DEV)
        code, _out, _err = self.main(f"+{DEV}", "requirement")
        self.assertEqual(code, 0)
        self.assertTrue((folder / versions.USED).is_file(), "a use recorded")
        self.assertTrue(imports.imported(DEV), "its settings and store, once, before anything else")
        os.utime(folder / versions.USED, (1.0, 1.0))
        self.main("--version")
        self.assertGreater((folder / versions.USED).stat().st_mtime, 1.0, "an agent's check at a session's start too")

    def test_only_a_command_on_the_default_channel_marks_its_version_used_there(self) -> None:
        self.installed(DEV)
        self.main(f"+{DEV}@store", "requirement")
        self.main(f"+{DEV}@store", "--version")
        self.assertFalse(versions.on_default_channel(DEV), "a store's commands: never")
        self.main(f"+{DEV}", "--version")
        self.assertTrue(versions.on_default_channel(DEV), "a pin that names no store: the default channel")

    def notice(self, latest: str | None = "99.0.0") -> None:
        """The feed as the last check read it, for this process (its data folder), and this process told."""
        cache = places.data_dir() / updates.FILE
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"checked": time.time(), **({"feed": {"latest": latest}} if latest else {})}),
                         encoding="utf-8")
        for patch in (mock.patch.object(updates, "told", return_value=True),
                      mock.patch.object(pins, "own", return_value=cad_server.__version__)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_notice_follows_the_output_on_stderr_once_a_day_and_never_with_a_name(self) -> None:
        self.notice()
        mine = cad_server.__version__
        lines = f"A new version of cad is available: {mine} -> 99.0.0\n"
        with mock.patch.dict(os.environ, {"CAD_UPDATE_CHECK": "0"}):
            quiet = self.main("requirement")
        self.assertEqual(quiet[2], "", "the check turned off: nothing")
        code, out, err = self.main("requirement")
        self.assertEqual((code, out), quiet[:2], "stdout as it was")
        self.assertTrue(err.endswith(lines), err)
        self.assertNotIn("new version", self.main("requirement")[2], "once a day per computer")
        stamp = self.state / cli.NOTICE
        os.utime(stamp, (time.time() - cli.NOTICE_SECONDS, time.time() - cli.NOTICE_SECONDS))
        code, out, err = self.main(f"+{mine}@claude", "requirement")
        self.assertEqual((code, out, err), (*quiet[:2], ""), "a name: whoever delivered that copy updates it")
        self.assertIn("new version", self.main("requirement")[2], "a day later")

    def test_version_says_it_every_time_and_nothing_when_the_check_is_off_or_none_is_newer(self) -> None:
        self.notice()
        mine = cad_server.__version__
        for _ in range(2):
            code, out, err = self.main("--version")
            self.assertEqual((code, out), (0, f"cad {mine}\n"))
            self.assertIn(f"{mine} -> 99.0.0", err)
        self.assertFalse((self.state / cli.NOTICE).exists(), "no daily stamp for --version")
        self.assertEqual(self.main(f"+{mine}@codex", "--version"), (0, f"cad {mine}\n", ""))
        with mock.patch.dict(os.environ, {"CAD_UPDATE_CHECK": "0"}):
            self.assertEqual(self.main("--version"), (0, f"cad {mine}\n", ""))
        self.notice(latest=mine)
        self.assertEqual(self.main("--version"), (0, f"cad {mine}\n", ""), "the newest already")

    def test_a_version_with_a_newer_one_installed_beside_it_says_nothing(self) -> None:
        self.installed(DEV)
        self.notice()  # in DEV's own data folder
        mine = cad_server.__version__
        self.assertIn("new version", self.main("--version")[2], "the newest installed: told")
        self.installed(NEWER)
        self.assertEqual(self.main("--version"), (0, f"cad {mine}\n", ""))
        code, _out, err = self.main("requirement")
        self.assertEqual((code, err), (0, ""), "nor after a command, though no notice was said today")
        self.assertFalse((self.state / cli.NOTICE).exists())

    def test_the_notice_comes_after_the_output_where_both_streams_share_one_pipe(self) -> None:
        # `2>&1`: stdout block-buffered on a pipe, stderr on the same pipe; the output is flushed before the line.
        self.notice()
        mine = cad_server.__version__
        read, write = os.pipe()
        with open(read, "rb") as reader:
            # newline="\n": the writers keep each line's end as written, on Windows too, where text files write \r\n.
            with (open(write, "w", encoding="utf-8", newline="\n") as out,
                  open(os.dup(write), "w", encoding="utf-8", newline="\n") as err):
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(cli.main(["--version"]), 0)
            self.assertEqual(reader.read().decode("utf-8"),
                             f"cad {mine}\nA new version of cad is available: {mine} -> 99.0.0\n")


class TheChannel(unittest.TestCase):
    def setUp(self) -> None:
        for patch in (mock.patch.object(places, "_channel", None), mock.patch.dict(os.environ, clear=False)):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop(places.RUN_WITH, None)

    def test_default_unless_a_pin_names_one(self) -> None:
        self.assertEqual(places.channel(), "default")
        extras.tell([])
        self.assertNotIn(places.RUN_WITH, os.environ)
        places.set_channel("store")
        self.assertEqual(places.channel(), "store")
        extras.tell([])  # cad run hands its program no channel: there is none in the cad command
        self.assertNotIn(places.RUN_WITH, os.environ)
        places.set_channel(None)
        self.assertEqual(places.channel(), "default")
        with self.assertRaises(ValueError):
            places.set_channel("Bad")


if __name__ == "__main__":
    unittest.main()
