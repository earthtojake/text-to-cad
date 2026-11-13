"""The update's sequence on a device of versions (``cad_server._internal.update``'s docstring, run by
``cad_server.cli.setup``): this release present, the default channel moved, the apps step; a failure injected at each
step and a process killed at each point of the move, each followed by a second attempt, with a working device
throughout; what an updater of 0.11.10 expects of ``cad setup --engine-update`` once it returns; ``cad setup`` on a
fresh device, one 0.11.10 set up and one with only a store's version; ``pins.update_default``; and ``cad uninstall``.

The device is ``test_versions``'s (uv stood in for: each version a real virtual environment of this Python naming
this checkout's sources); the agent apps are a home of the test's own with none of them in it, and the plugin folder
is written from a plugin of the test's own. This process plays the version whose setup runs (``places.versioned``).
A real 0.11.10 updating into this build is scripts/test/rehearse-update.py's.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.python.packages.cad_server.test_setup import plugin_source
from tests.python.packages.cad_server.test_versions import IDENT, OLD, SOURCES, TOKEN, Device

from cad.engine import places
from cad_server import analytics
from cad_server._internal import imports, installations, legacy, pins, plugin, pointers, providers, versions
from cad_server.cli import setup, telemetry, uninstall

X, Y = "0.12.0", "0.12.1"


class Sequence(Device):
    def setUp(self) -> None:
        super().setUp()
        self.home = self.root / "home"
        self.home.mkdir()
        machine = providers.Machine(self.home, {"HOME": str(self.home), "PATH": str(self.root / "no-apps")}, bundled={})
        source = plugin_source(self.root / "plugin-source")
        for patch in (mock.patch.object(providers.Machine, "here", return_value=machine),
                      mock.patch.object(plugin, "source", return_value=source),
                      mock.patch.object(analytics, "notify", return_value=False),
                      mock.patch.object(telemetry, "describe", return_value="off: your choice"),
                      mock.patch.object(installations, "_make_interpreter", side_effect=self.interpreter)):
            patch.start()
            self.addCleanup(patch.stop)

    def interpreter(self, folder: str) -> None:
        """On Windows the cad command's Python, as uv makes it, without uv."""
        Path(folder, "Scripts").mkdir(parents=True, exist_ok=True)
        Path(folder, "Scripts", "python.exe").write_bytes(b"MZ")
        Path(folder, "pyvenv.cfg").write_text(f"home = {self.root}\nversion_info = 3.14.0\n", encoding="utf-8")

    def setup_as(self, name: str, *argv: str) -> tuple[int, str, str]:
        """``cad setup`` run by version ``name``'s own process (its code says its version by its folder)."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(places, "versioned", return_value=name), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            try:
                code = setup.main(list(argv))
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()

    def on(self, name: str) -> None:
        """The device on version ``name`` by the install command: present, the default channel on it, its receipt."""
        self.present(name)
        code, out, err = self.setup_as(name)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(pointers.read(None), name)

    def working(self) -> str:
        """That the device works now: the default channel names a present version whose data is imported, and the
        mirror 0.11.10 and earlier read names a version that runs too. The version a command with no pin runs."""
        found = pointers.default().version
        self.assertIsNotNone(found)
        self.assertIn(found, versions.present(), "the default channel's version is present")
        record = installations.current()
        self.assertIsNotNone(record, "the mirror names an installation that is there")
        self.assertTrue(imports.imported(found) or not legacy.importable(), "its data is imported, or will be")
        return found

    def documents(self, name: str) -> None:
        data = places.data_dir(name)
        (data / "documents" / IDENT).mkdir(parents=True, exist_ok=True)
        (data / "documents" / IDENT / "document.json").write_text('{"id": "x"}', encoding="utf-8")
        (data / "engines").mkdir(exist_ok=True)
        (data / "engines" / "token").write_text(TOKEN + "\n", encoding="ascii")


class FailureAtEachStep(Sequence):
    """A failure at each step of an update from X to Y leaves a working device, and the next attempt completes."""

    def test_making_y_present_fails_and_nothing_changes(self) -> None:
        self.on(X)
        self.uv.fail = lambda step: (1, "error: no solution for cad-server==0.12.1") if step[1] == "pip" else None
        found = versions.make_present(Y)
        self.assertFalse(found.ok)
        self.assertEqual(self.working(), X)
        self.uv.fail = None
        self.present(Y)
        self.assertEqual(self.setup_as(Y, "--engine-update")[0], 0)
        self.assertEqual(self.working(), Y)
        self.assertFalse(places.version_dir(X).exists(), "the version left, which nothing names, removed")

    def test_the_move_fails_before_the_pointer_and_changes_nothing_then_completes(self) -> None:
        self.on(X)
        self.documents(X)
        self.present(Y)
        for name, patch in (("the import", mock.patch.object(imports, "_copy", side_effect=OSError(28, "No space left"))),
                            ("the proof", mock.patch.object(versions, "proof", side_effect=versions.base.Refused(
                                "it does not run", "probe"))),
                            ("the pointer", mock.patch.object(pointers, "write", side_effect=OSError(30, "Read-only")))):
            with self.subTest(failed=name), patch:
                try:
                    code, out, err = self.setup_as(Y, "--engine-update")
                except OSError:
                    code = 1
                self.assertEqual(code, 1)
                self.assertEqual(pointers.read(None), X)
                self.assertEqual(self.working(), X)
                self.assertEqual(installations.current_version(), X)
                if code == 1 and "out" in locals():
                    stages = [json.loads(line)["progress"]["stage"] for line in out.splitlines() if line.strip()]
                    self.assertNotIn("apps", stages, "no app was given Y's text")
        code, out, err = self.setup_as(Y, "--engine-update")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.working(), Y)
        self.assertTrue((places.data_dir(Y) / "documents" / IDENT / "document.json").is_file(), "X's records came")

    def test_after_the_pointer_a_failed_mirror_or_a_removal_refused_leaves_both_and_the_next_finishes(self) -> None:
        self.on(X)
        self.present(Y)
        with mock.patch.object(pointers, "mirror", side_effect=OSError(13, "Permission denied")):
            code, out, err = self.setup_as(Y, "--engine-update")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(pointers.read(None), Y)
        self.assertIn("the record clients of 0.11.10 and earlier find the server by could not be written", err)
        self.assertEqual(installations.current_version(), X, "the mirror still names X ...")
        self.assertIsNotNone(installations.current(), "... which stays while it does: a client of 0.11.10 starts it")
        self.assertEqual(versions.sweep(), {}, "nothing is removed while the mirror names it")
        # The next run of the same setup repairs what the move left: the mirror, then the sweep.
        code, out, err = self.setup_as(Y, "--engine-update")
        self.assertEqual((code, installations.current_version()), (0, Y), out + err)
        self.assertFalse(places.version_dir(X).exists())
        # A removal the system refuses (Windows: a file in use) keeps the version left for the next sweep.
        Z = "0.12.2"
        self.present(Z)
        with mock.patch.object(versions.os, "rename", side_effect=OSError(32, "in use")):
            code, out, err = self.setup_as(Z, "--engine-update")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.working(), Z)
        self.assertEqual(installations.current_version(), Z, "the next move rewrote the mirror")
        self.assertTrue(places.version_dir(Y).exists(), "kept for now")
        self.assertEqual(versions.sweep(), {Y: "removed"}, "removed by the next sweep")

    def test_the_apps_step_fails_and_the_device_runs_y_and_the_next_update_does_it_again(self) -> None:
        self.on(X)
        self.present(Y)
        with mock.patch.object(plugin, "write", side_effect=OSError(13, "Permission denied")):
            code, out, err = self.setup_as(Y, "--engine-update")
            self.assertEqual(code, 0, "the channel moved: an updater's run says the app and goes on")
            code, out, err = self.setup_as(Y)
            self.assertEqual(code, 1, "a person's run says it failed, and the install command to run again")
            self.assertIn("could not be written", out)
            self.assertIn("Once they are fixed, run the install command again", out)
        self.assertEqual(self.working(), Y)
        code, out, err = self.setup_as(Y)
        self.assertEqual(code, 0, out + err)
        self.assertTrue((plugin.folder() / plugin.MANIFEST).is_file(), "written by the next run")


# A move run in a process of its own, killed (``os._exit``: nothing after it runs, no ``finally``) at one point.
KILL = """
import os, sys
sys.path[:0] = {sources!r}
from cad.engine import places
places.versioned = lambda: {new!r}
point = sys.argv[1]
from cad._internal import atomic_replace
from cad_server._internal import pointers, versions, imports
import shutil
if point == "before-the-import-is-marked":
    write = imports.write_bytes_atomic if hasattr(imports, "write_bytes_atomic") else None
    original = atomic_replace.write_bytes_atomic
    def marked(path, data, *args, **kwargs):
        if str(path).endswith(imports.MARKER):
            os._exit(9)
        return original(path, data, *args, **kwargs)
    atomic_replace.write_bytes_atomic = marked
elif point == "before-the-pointer":
    pointers.write = lambda *args, **kwargs: os._exit(9)
elif point == "after-the-pointer":
    pointers.mirror = lambda *args, **kwargs: os._exit(9)
elif point == "during-removal":
    remove = shutil.rmtree
    def removing(path, *args, **kwargs):
        if versions.TRASH in str(path):
            os._exit(9)
        return remove(path, *args, **kwargs)
    shutil.rmtree = removing
versions.move(None, {new!r})
os._exit(0)
"""


class Interrupted(Sequence):
    """The process killed at each point of the import and of ``move``: the device still runs a working version, and a
    second attempt completes."""

    def test_killed_at_each_point_then_a_second_attempt_completes(self) -> None:
        for point in ("before-the-import-is-marked", "before-the-pointer", "after-the-pointer", "during-removal"):
            with self.subTest(point=point):
                self.tearDown_device()
                self.on(X)
                self.documents(X)
                self.present(Y)
                environment = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
                done = subprocess.run([sys.executable, "-c", KILL.format(sources=list(SOURCES), new=Y), point],
                                      env=environment, capture_output=True, text=True, timeout=120)
                self.assertEqual(done.returncode, 9, done.stderr)
                places._versioned.cache_clear()
                running = self.working()
                self.assertIn(running, (X, Y))
                self.assertEqual(running, Y if point in ("after-the-pointer", "during-removal") else X)
                # The second attempt: the updater runs the same setup again.
                code, out, err = self.setup_as(Y, "--engine-update")
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.working(), Y)
                self.assertEqual(installations.current_version(), Y)
                self.assertTrue((places.data_dir(Y) / "documents" / IDENT / "document.json").is_file())
                versions.sweep()
                self.assertFalse(places.version_dir(X).exists(), "X goes, by this move or the next sweep")
                self.assertFalse([entry for entry in os.listdir(places.versions_dir()) if entry.startswith(versions.TRASH)])

    def tearDown_device(self) -> None:
        """A fresh device for the next point."""
        import shutil

        for folder in (self.state, self.cache, self.engines, self.root / "bin"):
            shutil.rmtree(folder, ignore_errors=True)
        places._versioned.cache_clear()
        places._registered.cache_clear()


class LegacyCaller(Sequence):
    """What 0.11.10's updater expects once this release's ``cad setup --engine-update`` returns (its frozen
    ``Update._switch_to``, ``switch.spawn``, ``switch.switch``, ``_point``, ``_started``, ``releases.collect`` and
    ``follow``), stood in for here and met: the real 0.11.10 is scripts/test/rehearse-update.py's."""

    def test_its_two_runs_from_the_flat_folder_it_made_leave_what_its_helper_needs(self) -> None:
        self.legacy()  # 0.11.10 installed by the install command: its data, its flat release, its receipt
        flat = self.state / "releases" / Y  # the flat folder 0.11.10's `releases.make` makes for Y
        flat.mkdir(parents=True)
        made: list[str] = []
        original = versions.make_present

        def present(name, **kwargs):
            made.append(name)
            return original(name, **kwargs)

        frames = io.StringIO()
        # The first run (`CAD_UPDATE_PREPARE=1`): Y present, and nothing else; exit 0.
        with mock.patch.object(setup.Installer, "_home", return_value=Y), \
                mock.patch.object(versions, "make_present", side_effect=present), \
                mock.patch.dict(os.environ, {setup.PREPARE_ENV: "1", installations.NAME_ENV: ""}), \
                contextlib.redirect_stdout(frames), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(setup.main(["--engine-update"]), 0)
        self.assertEqual(made, [Y])
        self.assertEqual([json.loads(line)["progress"]["stage"] for line in frames.getvalue().splitlines()],
                         ["install", "build123d"], "frames its updater reads: kind update, a stage it knows")
        self.assertIsNone(pointers.read(None), "the first run changes nothing but Y's own folder")
        self.assertEqual(installations.current_version(), OLD)
        # The second run, once 0.11.10's server is idle: run from the flat folder, it runs Y's own setup, which moves
        # the default channel (importing the layout of 0.11.10) and gives the apps Y's text; exit 0.
        code, out, err = self.setup_as(Y, "--engine-update")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(pointers.read(None), Y)
        self.assertTrue(imports.imported(Y))
        self.assertEqual(imports.marker(Y)["imported"]["kind"], "legacy")
        # 1. `previous = installations.current_version()`, read after the setup: Y, so its way back is Y itself.
        self.assertEqual(installations.current_version(), Y)
        # 2. `_point(Y)`: the flat lock free -- no server of Y's took it during the setup -- and `point` writes current.
        held = places.lock(places.engines_dir() / "engine.lock")
        self.assertIsNotNone(held, "the flat lock is free for its helper to take")
        held.close()
        # 3. `_started(Y)`: `installations.current()` names Y, alive, its record's prefix Y's server environment, which
        #    the daemon it starts (that record's Python, `-m cad_server._internal.engine_daemon`) says in `status`.
        record = installations.current()
        self.assertEqual((record["version"], record["prefix"]), (Y, str(places.code_dir(Y) / "server")))
        self.assertTrue(os.path.isfile(record["python"]) and os.path.isfile(record["cad"]))
        # 4. `releases.collect({Y})`: it removes the flat folders but Y's; the flat `releases/Y` it ran from is the
        #    layout's, removed with it once nothing runs from it.
        self.assertTrue(flat.exists(), "the setup leaves the folder it was run from")
        self.assertTrue((self.state / "releases" / OLD).exists(), "kept until Y serves and nothing runs from it")
        self.serving(Y)
        with mock.patch.object(legacy, "flat_server", return_value=str(places.code_dir(Y) / "server")):
            versions.sweep()
        self.assertFalse((self.state / "releases").exists(), "the layout of 0.11.10 went, Y's flat folder with it")
        for kept in ("settings.json", "engines/token", "engines/engine.json", "installations/current",
                     f"installations/{Y}.json", "install-receipt.json", "plugin"):
            self.assertTrue((self.state / kept).exists(), kept)
        # 5. `follow()`: `<current's cad> plugin --refresh` -- Y's, which writes nothing new: Y's setup wrote it.
        self.assertTrue((plugin.folder() / plugin.MANIFEST).is_file())


class SetupOnEachDevice(Sequence):
    def test_a_fresh_device(self) -> None:
        self.present(X)
        code, out, err = self.setup_as(X)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((pointers.read(None), installations.current_version()), (X, X))
        self.assertTrue((self.state / setup.RECEIPT).is_file())
        self.assertEqual(installations.proxy_status(), installations.OK)
        self.assertTrue((plugin.folder() / plugin.MANIFEST).is_file())

    def test_a_device_0_11_10_set_up(self) -> None:
        self.legacy()
        self.present(X)
        code, out, err = self.setup_as(X)
        self.assertEqual(code, 0, out + err)
        self.assertIn(f"default  text-to-cad {X} (was {OLD})", out)
        self.assertEqual(imports.marker(X)["imported"]["kind"], "legacy")
        self.assertEqual((places.data_dir(X) / "engines" / "token").read_text(encoding="ascii").strip(), TOKEN)

    def test_a_device_with_only_a_store_s_version_keeps_it(self) -> None:
        self.present(Y)
        versions.move("claude", Y)
        (places.data_dir(Y) / "settings.json").write_text('{"telemetry": {"choice": "off"}}', encoding="utf-8")
        self.present(X)
        code, out, err = self.setup_as(X)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((pointers.read(None), pointers.read("claude")), (X, Y), "the store's channel left alone")
        self.assertTrue(places.version_record(Y), "and its version")
        # The default's first use imports from the highest older version present: never the store's newer one.
        self.assertIsNone(imports.marker(X)["imported"])

    def test_the_same_version_as_a_store_s_shares_it(self) -> None:
        self.present(X)
        versions.move("codex", X)
        code, out, err = self.setup_as(X)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((pointers.read(None), pointers.read("codex")), (X, X))


class PinnedUpdate(Sequence):
    def test_an_unnamed_pin_newer_than_the_default_runs_the_update_whatever_the_switch(self) -> None:
        from cad_server import auto_updates

        self.on(X)
        auto_updates.change({"automatic": False})
        self.present(Y)
        said: list[str] = []
        with mock.patch.object(places, "versioned", return_value=Y):
            moved = pins.update_default(Y, told=said.append)
        self.assertEqual((moved.kind, pointers.read(None)), ("moved", Y))
        self.assertIn(f"default  text-to-cad {Y} (was {X})", said)
        manifest = json.loads((plugin.folder() / plugin.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "text-to-cad", "the apps step: the plugin folder written by Y")
        self.assertFalse(places.version_dir(X).exists())
        # A development version's pin moves the channel alone: its apps are its checkout's.
        dev = f"{Y}-dev.20261113000000"
        with mock.patch.object(versions, "move", return_value=versions.Moved("moved", None, dev, Y)) as moved_alone, \
                mock.patch.object(places, "versioned", return_value=dev), \
                mock.patch.object(setup.Installer, "update_own", side_effect=AssertionError("no apps step")):
            pins.update_default(dev)
        moved_alone.assert_called_once()


class DevelopmentInstall(Sequence):
    """``scripts/install/dev_install.py``'s install of a checkout as a version (``INSTALL_VERSION``, run by the
    checkout's own Python against this device), and the way back: the install command's setup."""

    @unittest.skipIf(os.name == "nt", "its cad command's Python on Windows is made by uv")
    def test_a_checkout_becomes_the_default_channel_s_version_and_the_install_command_goes_back(self) -> None:
        import importlib.util

        from tests.python.support.paths import REPO_ROOT

        spec = importlib.util.spec_from_file_location("dev_install", REPO_ROOT / "scripts/install/dev_install.py")
        dev_install = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dev_install)
        self.on(X)
        dev = f"{X}-dev.20261113000000"
        done = subprocess.run([sys.executable, "-c", dev_install.INSTALL_VERSION, dev], capture_output=True, text=True,
                              timeout=300, env={key: value for key, value in os.environ.items()
                                                if key not in ("PYTHONPATH", "PYTHONHOME")})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout.splitlines()[-1]), {"version": dev, "before": X})
        places._versioned.cache_clear()
        record = places.version_record(dev)
        self.assertEqual(record["prefix"], sys.prefix, "the marker names the checkout's environment: nothing copied")
        self.assertEqual((pointers.read(None), installations.current_version()), (dev, dev))
        self.assertTrue(imports.imported(dev), "its data imported from the release it replaced")
        self.assertFalse(places.version_dir(X).exists(), "the release left, which nothing names, removed")
        self.assertEqual(installations.proxy_status(), installations.OK)
        # Going back: no pinned command moves the channel to an older version; a person's install command does.
        self.present(X)
        self.assertEqual(versions.move(None, X).kind, "stale")
        code, out, err = self.setup_as(X)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(pointers.read(None), X)
        self.assertFalse(places.version_dir(dev).exists(), "the development version went with the move")
        self.assertTrue(os.path.isfile(sys.executable), "and the checkout's environment stays")


class Uninstall(Sequence):
    def run_uninstall(self, name: str, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.object(places, "versioned", return_value=name), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out), mock.patch("cad_server.cli.stop.main", return_value=0):
            code = uninstall.main([*argv, "--yes"])
        return code, out.getvalue()

    def test_it_takes_out_the_default_channel_and_its_version(self) -> None:
        self.on(X)
        code, out = self.run_uninstall(X)
        self.assertEqual(code, 0, out)
        self.assertFalse(places.version_dir(X).exists())
        for gone in ("default", setup.RECEIPT, "installations/current", f"installations/{X}.json", "plugin"):
            self.assertFalse((self.state / gone).exists(), gone)
        self.assertEqual(installations.proxy_status(), installations.MISSING)

    def test_a_store_s_channel_its_version_and_the_cad_command_stay(self) -> None:
        self.on(X)
        self.present(Y)
        versions.move("codex", Y)
        code, out = self.run_uninstall(X)
        self.assertEqual(code, 0, out)
        self.assertFalse(places.version_dir(X).exists())
        self.assertEqual(pointers.read("codex"), Y)
        self.assertTrue(places.version_record(Y))
        self.assertEqual(installations.proxy_status(), installations.OK)
        self.assertIn(f"stays: the copy of the plugin the codex (text-to-cad {Y}) channel delivered still uses it; "
                      "remove that plugin in its app", out)

    def test_a_store_on_the_same_version_keeps_it_and_purge_removes_everything(self) -> None:
        self.on(X)
        versions.move("claude", X)
        code, out = self.run_uninstall(X)
        self.assertEqual(code, 0, out)
        self.assertTrue(places.version_record(X), "the claude channel is on it")
        self.assertIsNone(pointers.read(None))
        code, out = self.run_uninstall(X, "--purge")
        self.assertEqual(code, 0, out)
        self.assertFalse(self.state.exists())
        self.assertEqual(installations.proxy_status(), installations.MISSING)


if __name__ == "__main__":
    unittest.main()
