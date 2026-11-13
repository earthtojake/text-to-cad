"""A pinned command, ``cad +<version>[@<channel>] ...``: the ``cad`` command that reads the pin first (the sh and
the Windows main, ``cad_server._internal.installations``), and the version that reads it then (``pins``, ``cli``).

The command runs for real against a device in a temporary folder whose versions are stubs: a version's code
marker names a ``python`` that runs what it is given and a ``cad`` that says which version it is, the name it was
told and its arguments. uv is a stub too (``uvx`` on a PATH of the test's own), which records how it was run and
installs a version by copying a staged one in, or fails. The Windows main is run by this Python on any system.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.engine import client, places  # noqa: E402
from cad_server import cli  # noqa: E402
from cad_server._internal import extras, installations, pins, pointers, proxy, versions  # noqa: E402
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
        # The sh runs ``python cad ARGS``; the Windows main runs ``cad ARGS``; the layout before 0.12 ran
        # ``python -P -m cad_server._internal.proxy ARGS``.
        python.write_text('#!/bin/sh\n[ "$1" = -P ] && { echo "legacy $*"; exit 0; }\nexec "$@"\n', encoding="utf-8")
        cad.write_text(f'#!/bin/sh\necho "{name} ${{CAD_INSTALLATION_VERSION-unset}} $*"\n', encoding="utf-8")
        python.chmod(0o755)
        cad.chmod(0o755)
        final = self.state / "versions" / name / "code" / "server" / "bin"
        record = {"schema": places.VERSION_SCHEMA, "version": name, "python": str(final / "python"),
                  "cad": str(final / "cad"), "prefix": str(final.parent)}
        # As ``versions.make_present`` writes it: a key a line, its paths as they are.
        (code / places.VERSION_MARKER).write_text(json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False)
                                                  + "\n", encoding="utf-8")

    def point(self, channel: str | None, name: str) -> None:
        path = self.state / ("default" if channel is None else f"channels/{channel}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{name}\n", encoding="utf-8")

    def legacy(self, name: str = "0.11.10") -> None:
        """A device the install command set up before 0.12: its receipt, and its current installation."""
        flat = self.state / "releases" / name / "bin"
        flat.mkdir(parents=True)
        for script in ("python", "cad"):
            (flat / script).write_text('#!/bin/sh\n[ "$1" = -P ] && { echo "legacy $*"; exit 0; }\n', encoding="utf-8")
            (flat / script).chmod(0o755)
        (self.state / "install-receipt.json").write_text('{"schema": 1}', encoding="utf-8")
        record = {"version": name, "python": str(flat / "python"), "cad": str(flat / "cad"), "prefix": str(flat.parent)}
        (self.state / "installations").mkdir()
        (self.state / "installations" / f"{name}.json").write_text(json.dumps(record, indent=1, sort_keys=True) + "\n",
                                                                   encoding="utf-8")
        (self.state / "installations" / "current").write_text(name, encoding="utf-8")

    def uvx(self, *, installs: str | None = None, fails: str | None = None) -> None:
        """uv's stub: it records how it was run (and the name it was told), then installs version ``installs`` --
        staged, copied in as ``cad setup --add`` would make it -- or fails saying ``fails``."""
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

    def refused(self, done: subprocess.CompletedProcess, reason: str, words: str) -> None:
        self.assertEqual((done.returncode, done.stdout, done.stderr), (REASONS[reason], "", f"cad: {words}\n"))

    def test_a_pinned_version_installed_runs_with_the_pin_whatever_its_channel_is_on(self) -> None:
        def check(how: str) -> None:
            self.version(X)
            # Equal, newer than its channel's, the channel's first use, older than its channel's: the command never
            # judges a version that is there; that version's own cad reads the pin (``pins.apply``).
            for pointer in (X, OLDER, None, NEWER):
                if pointer is not None:
                    self.point("store", pointer)
                self.ran(self.cad(how, f"+{X}@store", "status", "a b", "$HOME"), f"{X} unset +{X}@store status a b $HOME")
            # A release is told no name, whatever this shell inherited (a daemon's children carry one).
            self.ran(self.cad(how, f"+{X}", "run", CAD_INSTALLATION_VERSION="0.9.0"), f"{X} unset +{X} run")
            self.assertEqual(self.uv_runs(), [])

        self.both(check)

    def test_a_pin_not_installed_older_than_its_channel_is_stale_and_nothing_is_installed(self) -> None:
        def check(how: str) -> None:
            self.uvx(installs=X)
            self.point("store", NEWER)
            self.refused(self.cad(how, f"+{X}@store", "status"), "stale_pin", pins.stale(X, "store", NEWER))
            self.point(None, NEWER)
            for pin in (f"+{X}", f"+{X}@default"):  # @default is the default channel
                self.refused(self.cad(how, pin, "status"), "stale_pin", pins.stale(X, None, NEWER))
            self.assertEqual(self.uv_runs(), [], "nothing installed")

        self.both(check)

    def test_a_pin_not_installed_is_installed_by_its_own_release_then_run(self) -> None:
        def check(how: str) -> None:
            self.uvx(installs=X)
            self.point("store", OLDER)  # newer than its channel's: installed (and its own cad moves the channel)
            self.ran(self.cad(how, f"+{X}@store", "status", CAD_INSTALLATION_VERSION="0.9.0"),
                     f"{X} unset +{X}@store status")
            self.assertEqual(self.uv_runs(), [f"unset --no-config --managed-python --python 3.14 --from "
                                              f"cad-server=={X} cad setup --add --quiet"])
            self.assertEqual(self.cad(how, f"+{X}@other", "status").returncode, 0, "the first use of a channel")
            self.assertEqual(len(self.uv_runs()), 1, "installed once")

        self.both(check)

    def test_a_pin_that_cannot_be_installed_from_this_shell_says_the_line_to_run(self) -> None:
        def check(how: str) -> None:
            system = "nt" if how == "windows" else "posix"
            self.refused(self.cad(how, f"+{X}", "status"), "cannot_install_here",
                         pins.not_installed(X, "uv is not installed", system))
            self.uvx(fails="error: Failed to fetch: dns error")
            self.refused(self.cad(how, f"+{X}", "status"), "cannot_install_here",
                         pins.not_installed(X, "error: Failed to fetch: dns error", system))
            self.assertEqual(len(self.uv_runs()), 1)

        self.both(check)

    def test_a_development_version_runs_by_its_record_told_its_name_and_is_never_installed(self) -> None:
        def check(how: str) -> None:
            self.uvx(installs=X)
            self.refused(self.cad(how, f"+{DEV}", "status"), "cannot_install_here", pins.development(DEV))
            self.version(DEV)
            self.ran(self.cad(how, f"+{DEV}", "status"), f"{DEV} {DEV} +{DEV} status")
            self.assertEqual(self.uv_runs(), [])

        self.both(check)

    def test_a_word_that_is_no_pin_or_names_no_channel_is_refused(self) -> None:
        def check(how: str) -> None:
            self.version(X)
            for word in ("+", "+abc", "+.1", "+0.12.0;rm", "+@store"):
                self.refused(self.cad(how, word, "status"), "bad_pin", pins.bad_pin(word))
            for word in (f"+{X}@", f"+{X}@Store", f"+{X}@-x", f"+{X}@a@b", f"+{X}@{'a' * 33}"):
                self.refused(self.cad(how, word, "status"), "bad_pin", pins.bad_channel(word))
            self.ran(self.cad(how, f"+{X}@{'a' * 32}", "status"), f"{X} unset +{X}@{'a' * 32} status")

        self.both(check)

    def test_no_pin_runs_the_default_channel_s_version(self) -> None:
        def check(how: str) -> None:
            self.refused_none(how)
            self.version("0.9.0")
            self.version(X)
            self.ran(self.cad(how, "status"), f"{X} unset status")  # the newest installed, by its numbers
            self.legacy()
            self.ran(self.cad(how, "status"), "legacy -P -m cad_server._internal.proxy status")  # before 0.12
            self.point(None, "0.9.0")
            self.ran(self.cad(how, "status", "x"), "0.9.0 unset status x")  # its pointer
            self.uvx(installs=NEWER)
            self.point(None, NEWER)
            self.ran(self.cad(how, "status"), f"{NEWER} unset status")  # its pointer's, installed
            self.assertEqual(len(self.uv_runs()), 1)

        self.both(check)

    def refused_none(self, how: str) -> None:
        done = self.cad(how, "status")
        self.assertEqual((done.returncode, done.stderr), (1, proxy.NONE_INSTALLED + "\n"))

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
        # A7: a release is run from where every release puts its Python and cad, no path parsed; a development
        # version's and the layout before 0.12's read with JSON's escapes undone.
        self.state = self.root / 'odd "quoted" \\ back' / "cad"
        self.state.mkdir(parents=True)
        self.version(X)
        self.ran(self.cad("sh", f"+{X}", "status"), f"{X} unset +{X} status")
        self.ran(self.cad("sh", "status"), f"{X} unset status")
        self.version(DEV)
        self.ran(self.cad("sh", f"+{DEV}", "status"), f"{DEV} {DEV} +{DEV} status")
        shutil.rmtree(self.state / "versions")
        self.legacy()
        self.ran(self.cad("sh", "status"), "legacy -P -m cad_server._internal.proxy status")

    def test_no_pin_runs_the_newest_version_that_has_started(self) -> None:
        def check(how: str) -> None:
            self.version(X)
            self.version(NEWER)
            (self.state / "versions" / X / "data").mkdir()
            (self.state / "versions" / X / "data" / "format.json").write_text("{}", encoding="utf-8")
            self.ran(self.cad(how, "status"), f"{X} unset status")

        self.both(check)

    def test_a_stale_line_names_the_repair_for_its_channel(self) -> None:
        def check(how: str) -> None:
            self.point("store", NEWER)
            self.point(None, NEWER)
            for pin, channel in ((f"+{X}@store", "store"), (f"+{X}", None)):
                done = self.cad(how, pin, "status")
                self.assertEqual(done.stderr, f"cad: {pins.stale(X, channel, NEWER)}\n")
            self.assertIn("`cad update`", pins.stale(X, None, NEWER))
            self.assertIn("update the text-to-cad plugin in the app it came from", pins.stale(X, "store", NEWER))

        self.both(check)


class AnOlderReleaseNeverRewritesIt(unittest.TestCase):
    def test_a_writer_of_revision_11_finds_revision_12_newer_and_leaves_it(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for windows in (False, True):
                path = Path(installations.proxy_path(folder, windows=windows))
                data = installations.script(False).encode() if not windows else _exe(installations.script(True))
                path.write_bytes(data)
                with mock.patch.object(installations, "REVISION", 11):  # 0.11.10's code, which writes 11
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


class Applying(unittest.TestCase):
    """``pins.apply``: the channel's pointer read, and the channel moved, or the pin found stale."""

    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp(prefix="cad-pins-"))
        self.addCleanup(shutil.rmtree, self.state, True)
        self.moved: list = []
        for patch in (mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state)}),
                      mock.patch.object(places, "versioned", return_value=X),
                      mock.patch.object(versions, "move", side_effect=self.move),
                      mock.patch.object(pins, "update_default", side_effect=self.update)):
            patch.start()
            self.addCleanup(patch.stop)
        self.answer = "moved"

    def move(self, channel, version, told=None):
        self.moved.append(("move", channel, version))
        return versions.Moved(self.answer, channel, version, NEWER if self.answer == "stale" else None, error="why")

    def update(self, version, told=None):
        self.moved.append(("update", None, version))
        return versions.Moved("moved", None, version, None)

    def apply(self, word: str) -> Failure | None:
        try:
            pins.apply(pins.parse(word))
        except Failure as failure:
            return failure
        return None

    def test_equal_runs_reads_the_pointer_and_marks_the_channel_used_once_a_day(self) -> None:
        pointers.write("store", X, self.state)
        with mock.patch.dict(pointers._used, clear=True):
            self.assertIsNone(self.apply(f"+{X}@store"))
        self.assertEqual((self.moved, sorted(os.listdir(self.state))), ([], ["channels", "used"]), "no move, no lock")
        stamp = self.state / "used" / "store"
        os.utime(stamp, (1_000_000, 1_000_000))
        with mock.patch.dict(pointers._used, clear=True):
            self.assertIsNone(self.apply(f"+{X}@store"))
        self.assertGreater(stamp.stat().st_mtime, 1_000_000, "a pinned command that reaches no server is a use too")
        os.utime(stamp, None)
        with mock.patch.dict(pointers._used, clear=True), mock.patch("os.utime", side_effect=PermissionError(1, "no")):
            self.assertIsNone(self.apply(f"+{X}@store"), "within the day: nothing written; and a mark never fails it")

    def test_a_pointer_that_cannot_be_read_runs_nothing_and_an_emptied_one_is_moved(self) -> None:
        pointers.write("store", X, self.state)
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError(13, "sharing violation")):
            refused = self.apply(f"+{X}@store")
        self.assertEqual((refused.reason, self.moved), ("failed", []))
        self.assertIn("cannot be read", str(refused))
        (self.state / "channels" / "store").write_bytes(b"")
        self.assertIsNone(self.apply(f"+{X}@store"))
        self.assertEqual(self.moved, [("move", "store", X)])

    def test_older_than_its_channel_is_stale(self) -> None:
        pointers.write("store", NEWER, self.state)
        stale = self.apply(f"+{X}@store")
        self.assertEqual((str(stale), stale.reason, stale.status), (pins.stale(X, "store", NEWER), "stale_pin", 4))
        self.assertEqual(self.moved, [])

    def test_newer_or_a_first_use_moves_the_channel(self) -> None:
        self.assertIsNone(self.apply(f"+{X}@store"))  # its first use
        pointers.write("other", OLDER, self.state)
        self.assertIsNone(self.apply(f"+{X}@other"))
        self.assertIsNone(self.apply(f"+{X}"))  # the default channel, with no install command run here
        (self.state / pointers.RECEIPT).write_text("{}", encoding="utf-8")
        self.assertIsNone(self.apply(f"+{X}@default"))  # where it has run: the updater
        self.assertEqual(self.moved, [("move", "store", X), ("move", "other", X), ("move", None, X),
                                      ("update", None, X)])

    def test_a_move_that_fails_says_why_and_runs_nothing(self) -> None:
        for answer, reason in (("cannot", "cannot_install_here"), ("failed", "failed"), ("stale", "stale_pin")):
            self.answer = answer
            self.assertEqual(self.apply(f"+{X}@store").reason, reason)
        with mock.patch.object(versions, "move", side_effect=PermissionError(1, "Operation not permitted")):
            refused = self.apply(f"+{X}@store")
        self.assertEqual((str(refused), refused.status),
                         (pins.cannot_move(pins.parse(f"+{X}@store"), "Operation not permitted"), 3))

    def test_a_process_of_another_version_or_none_moves_nothing(self) -> None:
        with mock.patch.object(places, "versioned", return_value=None):
            self.assertIsNone(self.apply(f"+{X}@store"))
        self.assertEqual(self.moved, [])


class TheChannel(unittest.TestCase):
    def setUp(self) -> None:
        for patch in (mock.patch.object(places, "_channel", None), mock.patch.dict(os.environ, clear=False)):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop(places.RUN_WITH, None)

    def test_default_unless_a_pin_or_cad_run_names_one(self) -> None:
        self.assertEqual(places.channel(), "default")
        self.assertEqual(client.with_channel({"op": "status"}), {"op": "status"}, "the default's requests name none")
        extras.tell([])
        self.assertNotIn(places.RUN_WITH, os.environ)
        places.set_channel("store")
        self.assertEqual(client.with_channel({"op": "status"}), {"op": "status", "channel": "store"})
        extras.tell([])  # cad run hands it to its program, whose requests name it too
        places._channel = None
        self.assertEqual(places.channel(), "store")
        self.assertEqual(places.run_with(), {"with": [], "script": None, "header": []})
        places.set_channel(None)
        self.assertEqual(places.channel(), "default")
        with self.assertRaises(ValueError):
            places.set_channel("Bad")


if __name__ == "__main__":
    unittest.main()
