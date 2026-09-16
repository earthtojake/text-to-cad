"""The development auto-reload: what it watches, when it fires, and what it re-runs.

The mechanism is gated on ONE predicate — ``running_from_source_checkout`` —
and everything here either exercises that predicate or drives the watcher
through its seams (``poll_once``, an injected idle gate, an injected restart).
Nothing here binds a socket or replaces a process; the end-to-end restart is a
subprocess test in ``test_launcher.py``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen.viewer import reload as reload_module
from cadgen.viewer.http_app import create_cad_app


def _stage_package(base: Path, *, parent_name: str, with_project: bool) -> Path:
    """A minimal cadgen-shaped tree: ``<base>/<parent_name>/cadgen/...``."""
    package = base / parent_name / "cadgen"
    (package / "viewer").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "viewer" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (package / "viewer" / "collation.json").write_text("{}", encoding="utf-8")
    if with_project:
        (base / parent_name / ".." / "pyproject.toml").resolve().write_text(
            '[project]\nname = "cadgen"\nversion = "0.0.0"\n', encoding="utf-8"
        )
    return package


class ThePredicate(unittest.TestCase):
    """One predicate decides the whole feature. It must not be loose."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_a_checkout_layout_reads_as_development(self) -> None:
        package = _stage_package(self.base / "checkout", parent_name="src", with_project=True)
        self.assertTrue(reload_module.running_from_source_checkout(package))

    def test_an_installed_wheel_reads_as_production(self) -> None:
        package = _stage_package(
            self.base / "venv", parent_name="site-packages", with_project=False
        )
        self.assertFalse(reload_module.running_from_source_checkout(package))

    def test_a_src_directory_without_a_cadgen_project_is_not_a_cadgen_checkout(self) -> None:
        # Someone else's `src/cadgen` — a vendored copy, an unpacked sdist of
        # something else — must not turn a user's viewer into a self-restarting
        # one. The project file has to name cadgen.
        package = _stage_package(self.base / "other", parent_name="src", with_project=False)
        (self.base / "other" / "pyproject.toml").write_text(
            '[project]\nname = "not-cadgen"\n', encoding="utf-8"
        )
        self.assertFalse(reload_module.running_from_source_checkout(package))

    def test_this_checkout_reads_as_development(self) -> None:
        # The suite runs cadgen from packages/cadgen/src, so the real predicate
        # over the real package directory must agree with the staged one.
        self.assertTrue(reload_module.running_from_source_checkout())


class WhatIsWatched(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.package = _stage_package(
            Path(self._tmp.name) / "checkout", parent_name="src", with_project=True
        )
        self.source = self.package / "viewer" / "main.py"

    def test_only_python_outside_pycache_and_runtime_counts(self) -> None:
        (self.package / "_runtime").mkdir()
        (self.package / "_runtime" / "bundled.py").write_text("noise\n", encoding="utf-8")
        (self.package / "__pycache__").mkdir()
        (self.package / "__pycache__" / "stale.py").write_text("noise\n", encoding="utf-8")
        watched = reload_module.watched_sources(self.package)
        self.assertEqual(
            [os.path.relpath(path, self.package) for path in watched],
            ["__init__.py", os.path.join("viewer", "main.py")],
        )

    def test_a_touch_changes_the_signature_but_not_the_digest(self) -> None:
        before_stat = reload_module.source_stat_signature(self.package)
        before_content = reload_module.source_content_digest(self.package)
        os.utime(self.source, (1, 1))
        self.assertNotEqual(reload_module.source_stat_signature(self.package), before_stat)
        self.assertEqual(reload_module.source_content_digest(self.package), before_content)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class WhenItFires(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.package = _stage_package(
            Path(self._tmp.name) / "checkout", parent_name="src", with_project=True
        )
        self.source = self.package / "viewer" / "main.py"
        self.clock = Clock()
        self.restarts: list[float] = []
        self.idle = True
        self._edits = 0
        self._epoch = os.stat(self.source).st_mtime

    def reloader(self, **kwargs) -> reload_module.SourceReloader:
        return reload_module.SourceReloader(
            is_idle=lambda: self.idle,
            restart=lambda: self.restarts.append(self.clock.now),
            base_dir=self.package,
            clock=self.clock,
            **kwargs,
        )

    def edit(self, text: str) -> None:
        """One distinct edit: exact bytes, and an mtime a second past the last.

        The bytes are written in BINARY so the file holds what this test says it
        holds on every platform -- text mode translates ``\n`` to ``\r\n`` on
        Windows, and a test about a digest of file contents should not have an
        opinion smuggled into it by the open mode.

        The stamp is COUNTED, never read back from the filesystem. It used to be
        ``os.stat(...).st_mtime + 1``, taken right after the write -- which asks
        the platform what time it just recorded, and Windows answers from the
        ~15.6ms interrupt clock. Two edits inside one tick came back with the
        SAME mtime and the same size, so the second edit was invisible to a
        size+mtime guard and a revert never registered. Counting makes every
        edit distinct by construction, which is what a test that means to
        perform distinct edits is entitled to.
        """
        self.source.write_bytes(text.encode("utf-8"))
        self._edits += 1
        stamp = self._epoch + self._edits
        os.utime(self.source, (stamp, stamp))

    def test_an_unchanged_tree_never_restarts(self) -> None:
        watcher = self.reloader()
        for _ in range(5):
            self.clock.now += 10
            self.assertFalse(watcher.poll_once())
        self.assertEqual(self.restarts, [])

    def test_a_touch_with_no_content_change_never_restarts(self) -> None:
        watcher = self.reloader()
        os.utime(self.source, (12345, 12345))
        self.clock.now += 10
        self.assertFalse(watcher.poll_once())
        self.assertEqual(self.restarts, [])

    def test_rapid_successive_changes_restart_exactly_once(self) -> None:
        watcher = self.reloader(quiet=1.0)
        for index in range(6):
            self.edit(f"x = {index}\n")
            self.clock.now += 0.2
            self.assertFalse(watcher.poll_once(), "every edit pushes the quiet deadline out")
        self.clock.now += 1.0
        self.assertTrue(watcher.poll_once())
        self.assertEqual(len(self.restarts), 1)

        # And nothing fires again on the next ticks.
        self.clock.now += 5
        self.assertFalse(watcher.poll_once())
        self.assertEqual(len(self.restarts), 1)

    def test_a_restart_waits_for_the_build_it_is_proxying(self) -> None:
        watcher = self.reloader(quiet=0.0)
        self.idle = False
        self.edit("x = 99\n")
        for _ in range(10):
            self.clock.now += 1
            self.assertFalse(watcher.poll_once(), "an in-flight compile defers the restart")
        self.assertEqual(self.restarts, [])
        self.idle = True
        self.clock.now += 1
        self.assertTrue(watcher.poll_once(), "and it fires the moment the build is done")
        self.assertEqual(len(self.restarts), 1)

    def test_an_edit_undone_before_the_restart_stops_being_pending(self) -> None:
        original = self.source.read_bytes().decode("utf-8")
        watcher = self.reloader(quiet=1.0)
        self.edit("x = 2\n")
        self.clock.now += 0.2
        self.assertFalse(watcher.poll_once())
        self.assertTrue(watcher.pending)
        self.edit(original)
        self.clock.now += 5
        self.assertFalse(watcher.poll_once(), "the code on disk is the code already running")
        self.assertEqual(self.restarts, [])

    def test_a_revert_the_platform_timestamps_identically_is_still_noticed(self) -> None:
        """The cheap guard cannot veto a pending restart settling back.

        Windows stamps a write from the ~15.6ms interrupt clock, so an edit and
        the edit that undoes it can land in ONE tick: same size, same mtime, a
        size+mtime signature that is byte-identical across a change it must not
        hide. Simulated here by writing the original bytes back under the
        edit's own timestamp, which is the same thing the platform does by
        itself -- and which used to leave the watcher permanently pending and
        restart the server into code that no longer existed.
        """
        original = self.source.read_bytes()
        watcher = self.reloader(quiet=1.0)
        self.edit("x = 2\n")
        self.clock.now += 0.2
        self.assertFalse(watcher.poll_once())
        self.assertTrue(watcher.pending)

        edited_signature = reload_module.source_stat_signature(self.package)
        frozen = os.stat(self.source).st_mtime
        self.source.write_bytes(original)
        os.utime(self.source, (frozen, frozen))
        self.assertEqual(
            reload_module.source_stat_signature(self.package),
            edited_signature,
            "the guard must be blind here, or this test is not the one it claims to be",
        )

        self.clock.now += 5
        self.assertFalse(watcher.poll_once(), "a pending restart re-reads the bytes")
        self.assertFalse(watcher.pending)
        self.assertEqual(self.restarts, [])


class WhatItReRuns(unittest.TestCase):
    """The restart is the same launch, pinned to the port already held."""

    def test_the_binding_is_rewritten_and_nothing_else_is(self) -> None:
        self.assertEqual(
            reload_module.restart_argv(
                ["--host", "127.0.0.1", "--dist", "/d", "--api-only", "--no-registry", "--json"],
                port=4321,
            ),
            ["--host", "127.0.0.1", "--dist", "/d", "--api-only", "--no-registry", "--json",
             "--port", "4321"],
        )

    def test_an_ephemeral_launch_comes_back_on_the_port_it_took(self) -> None:
        # This is the `npm run dev` shape: Vite proxies to the port the backend
        # announced once, so the restart must take that same port back.
        self.assertEqual(
            reload_module.restart_argv(["--ephemeral", "--no-registry", "--api-only"], port=51234),
            ["--no-registry", "--api-only", "--port", "51234"],
        )

    def test_an_earlier_explicit_port_is_replaced_not_duplicated(self) -> None:
        self.assertEqual(
            reload_module.restart_argv(["--port", "3245", "--new"], port=3245),
            ["--new", "--port", "3245"],
        )
        self.assertEqual(
            reload_module.restart_argv(["--port=3245"], port=3245), ["--port", "3245"]
        )

    def test_posix_execs_in_place_and_windows_spawns_then_exits(self) -> None:
        argv = ["--no-registry", "--port", "8123"]
        with mock.patch.object(reload_module.os, "execv") as execv:
            reload_module.execute_restart(argv, executable="/py", platform="linux")
        execv.assert_called_once_with("/py", ["/py", "-m", "cadgen.viewer", *argv])

        with mock.patch.object(reload_module.subprocess, "Popen") as popen, \
                mock.patch.object(reload_module.os, "_exit", side_effect=SystemExit) as hard_exit:
            with self.assertRaises(SystemExit):
                reload_module.execute_restart(argv, executable="py.exe", platform="win32")
        # The standard handles are passed EXPLICITLY. An exec keeps whatever
        # stdout and stderr were; a Windows spawn keeps them only if told to,
        # and a restarted server whose narration went to a redirected stderr
        # must keep writing there rather than to a console that may not exist.
        popen.assert_called_once_with(
            ["py.exe", "-m", "cadgen.viewer", *argv], stdout=1, stderr=2
        )
        hard_exit.assert_called_once_with(0)


class TheProductionPath(unittest.TestCase):
    """An installed wheel carries none of it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def app(self, *, checkout: bool):
        with mock.patch.object(
            reload_module, "running_from_source_checkout", return_value=checkout
        ):
            return create_cad_app(root=self._tmp.name, host="127.0.0.1", port=0, dist_dir="")

    def test_a_wheel_reports_no_auto_reload_and_counts_no_requests(self) -> None:
        app = self.app(checkout=False)
        info = app.server_info()
        self.assertIs(info["autoReload"], False)
        self.assertNotIn("restartRequired", info)
        self.assertNotIn("currentIdentityToken", info)

        # Even a route that WOULD be counted in development leaves the counter
        # untouched, so nothing in the wheel can defer a restart that does not
        # exist.
        self.assertEqual(app.busy_requests(), 0)
        seen = []
        with mock.patch.object(type(app), "_dispatch", lambda self, *_: seen.append(self.busy_requests())):
            app.handle(_Request("/__cad/catalog"), None)
        self.assertEqual(seen, [0])

    def test_a_checkout_reports_auto_reload_and_counts_the_routes_that_matter(self) -> None:
        app = self.app(checkout=True)
        self.assertIs(app.server_info()["autoReload"], True)
        seen = {}
        with mock.patch.object(
            type(app), "_dispatch",
            lambda self, request, _: seen.__setitem__(request.path, self.busy_requests()),
        ):
            for path in ("/__cad/catalog", "/__cad/artifact", "/__cad/server", "/__cad/preview"):
                app.handle(_Request(path), None)
        self.assertEqual(seen["/__cad/catalog"], 1)
        self.assertEqual(seen["/__cad/artifact"], 1, "a compile must defer the restart")
        self.assertEqual(seen["/__cad/server"], 0, "the reload watcher's own poll must not")
        self.assertEqual(seen["/__cad/preview"], 0, "a parked long-poll must not")
        self.assertEqual(app.busy_requests(), 0, "and the counter unwinds")
        self.assertTrue(app.restart_is_safe())


class _Request:
    def __init__(self, path: str) -> None:
        self.path = path
        self.method = "GET"
        self.query = {}


if __name__ == "__main__":
    unittest.main()
