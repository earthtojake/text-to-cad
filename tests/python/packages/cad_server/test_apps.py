"""Open in's apps (``cad_server._internal.apps``): each platform's lookup, run against a temporary tree
and a fake registry or PATH, the kinds each app takes, the cache that a request reads and never
fills, and the opening's commands. Nothing here starts an app or asks the computer's own index."""
from __future__ import annotations

import os
import plistlib
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cad_server._internal import apps


def bundle(path: Path, ident: str | None = None) -> str:
    """A fake app bundle at ``path``, its Info.plist naming ``ident``."""
    (path / "Contents").mkdir(parents=True)
    if ident is not None:
        (path / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": ident}))
    return str(path)


def executable(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return str(path)


class Tree(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)


class MacTest(Tree):
    def test_a_bundle_of_a_known_name_in_the_folders_then_spotlight_for_the_rest(self) -> None:
        system, user = self.root / "Applications [system]", self.root / "home" / "Applications"
        code = bundle(system / "Visual Studio Code.app")
        bundle(user / "Visual Studio Code.app")  # the first folder that holds one wins
        ce = bundle(user / "PyCharm CE.app")
        bundle(user / "PyCharm 2025.2.app")  # a Toolbox name: a later pattern than the exact one
        fusion = bundle(user / "Autodesk Fusion.app")
        prusa = bundle(system / "Original Prusa Drivers" / "PrusaSlicer.app")
        (system / "Zed.app").write_bytes(b"")  # a file, not a bundle
        blender = bundle(self.root / "elsewhere" / "Blender.app", "org.blenderfoundation.blender")
        stranger = bundle(self.root / "elsewhere" / "Other.app", "com.example.other")
        asked = []

        def spotlight(idents):
            asked.append(idents)
            return [blender, stranger, str(self.root / "gone.app")]

        found = apps.mac([system, user], spotlight)
        self.assertEqual(found, {"vscode": code, "pycharm": ce, "fusion": fusion, "prusa": prusa, "blender": blender})
        # One query, for the identifiers of the apps the folders did not have.
        [idents] = asked
        self.assertNotIn("com.microsoft.VSCode", idents)
        self.assertIn("dev.zed.Zed", idents)
        self.assertIn("org.blenderfoundation.blender", idents)
        # Without Spotlight, the folders alone.
        self.assertNotIn("blender", apps.mac([system, user], None))

    def test_a_toolbox_pycharm_is_found_by_its_glob(self) -> None:
        toolbox = bundle(self.root / "PyCharm 2025.2.app")
        self.assertEqual(apps.mac([self.root], None), {"pycharm": toolbox})


class WindowsTest(Tree):
    def test_app_paths_first_then_the_installers_folders(self) -> None:
        local, program_files = self.root / "Local", self.root / "Program Files"
        code = executable(self.root / "anywhere" / "Code.exe")
        cursor = executable(local / "Programs" / "cursor" / "Cursor.exe")
        old = executable(local / "Autodesk" / "webdeploy" / "production" / "a1" / "Fusion360.exe")
        new = executable(local / "Autodesk" / "webdeploy" / "production" / "b2" / "Fusion360.exe")
        os.utime(old, (1_000_000, 1_000_000))
        freecad = executable(program_files / "FreeCAD 1.0" / "bin" / "FreeCAD.exe")
        bambu = executable(program_files / "Bambu Studio" / "bambu-studio.exe")
        prusa = executable(program_files / "Prusa3D" / "PrusaSlicer" / "prusa-slicer.exe")
        blender = executable(program_files / "Blender Foundation" / "Blender 4.2" / "blender.exe")
        registry = {"Code.exe": code, "Cursor.exe": str(self.root / "moved" / "Cursor.exe")}  # Cursor's is stale
        asked = []

        def app_path(exe):
            asked.append(exe)
            return registry.get(exe)

        found = apps.windows({"LOCALAPPDATA": str(local), "ProgramFiles": str(program_files)}, app_path)
        self.assertEqual(found, {"vscode": code, "cursor": cursor, "fusion": new, "freecad": freecad, "bambu": bambu,
                                 "prusa": prusa, "blender": blender})
        self.assertEqual(asked, list(apps.WINDOWS_EXES.values()))
        # A folder variable that is not absolute is no folder.
        self.assertEqual(apps.windows({"LOCALAPPDATA": "Local", "ProgramFiles": "Program Files"}, lambda exe: None), {})


class LinuxTest(unittest.TestCase):
    def test_each_app_by_its_first_command_found(self) -> None:
        commands = {"code": "/usr/bin/code", "zeditor": "/usr/bin/zeditor", "pycharm-community": "/snap/bin/pycharm-community",
                    "FreeCAD": "/opt/freecad/FreeCAD", "blender": "/usr/bin/blender"}
        self.assertEqual(apps.linux(commands.get), {"vscode": "/usr/bin/code", "zed": "/usr/bin/zeditor",
                                                    "pycharm": "/snap/bin/pycharm-community",
                                                    "freecad": "/opt/freecad/FreeCAD", "blender": "/usr/bin/blender"})
        # Fusion has no Linux build: no command finds it.
        self.assertNotIn("fusion", apps.linux(lambda name: f"/usr/bin/{name}"))


class KindsTest(unittest.TestCase):
    def test_the_apps_each_kind_takes_in_the_menus_order(self) -> None:
        every = {app: f"/apps/{app}" for app in apps.APPS}
        ids = {kind: [entry["id"] for entry in apps.apps_for(kind, every)]
               for kind in ("script", "step", "stl", "3mf", "glb", "dxf", "urdf", "sdf", "srdf", "xbf")}
        self.assertEqual(ids, {"script": ["vscode", "cursor", "zed", "pycharm", "sublime"],
                               "step": ["fusion", "freecad", "bambu", "orca", "prusa"],
                               "stl": ["bambu", "orca", "prusa", "freecad", "blender"],
                               "3mf": ["bambu", "orca", "prusa", "freecad", "blender"],
                               "glb": ["blender"], "dxf": [], "urdf": [], "sdf": [], "srdf": [], "xbf": []})
        self.assertEqual(apps.apps_for("step", {"bambu": "/b", "vscode": "/v"}), [{"id": "bambu", "name": "Bambu Studio"}])
        self.assertEqual(apps.APPS, {"vscode": "Visual Studio Code", "cursor": "Cursor", "zed": "Zed",
                                     "pycharm": "PyCharm", "sublime": "Sublime Text", "fusion": "Autodesk Fusion",
                                     "freecad": "FreeCAD", "bambu": "Bambu Studio", "orca": "OrcaSlicer",
                                     "prusa": "PrusaSlicer", "blender": "Blender"})
        self.assertEqual([apps.file_manager(platform) for platform in ("darwin", "win32", "linux")],
                         ["finder", "explorer", "files"])


def settle(detected: apps.Detected) -> None:
    """Wait for the look running now, if one is."""
    thread = detected._looking
    if thread is not None:
        thread.join(10)
        assert not thread.is_alive()


class CacheTest(unittest.TestCase):
    def make(self, platform: str):
        self.now = 0.0
        self.calls = []

        def detect(on, *, spotlight):
            self.calls.append((on, spotlight, threading.get_ident()))
            return {"vscode": f"/apps/{len(self.calls)}"}

        return apps.Detected(detect, clock=lambda: self.now, platform=platform)

    def test_the_start_looks_without_a_command_and_use_looks_fully_then_every_five_minutes(self) -> None:
        detected = self.make("darwin")
        detected.warm().join(10)
        self.assertEqual([call[:2] for call in self.calls], [("darwin", False)])
        # The first use reads the start's look, and asks Spotlight in the background.
        self.assertEqual(detected.found(), {"vscode": "/apps/1"})
        settle(detected)
        self.assertEqual([call[:2] for call in self.calls], [("darwin", False), ("darwin", True)])
        self.now = apps.REFRESH_SECONDS - 1
        self.assertEqual(detected.found(), {"vscode": "/apps/2"})
        settle(detected)
        self.assertEqual(len(self.calls), 2)  # fresh: no look
        self.now = apps.REFRESH_SECONDS + 1  # five minutes after the full look
        detected.found()
        settle(detected)
        self.assertEqual(len(self.calls), 3)
        self.assertNotIn(threading.get_ident(), [call[2] for call in self.calls])

    def test_elsewhere_the_starts_look_is_the_whole_look(self) -> None:
        detected = self.make("linux")
        detected.warm().join(10)
        self.assertEqual(detected.found(), {"vscode": "/apps/1"})
        settle(detected)
        self.assertEqual([call[:2] for call in self.calls], [("linux", False)])

    def test_a_request_never_runs_a_command_nor_waits_for_a_look(self) -> None:
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        bundle(Path(root.name) / "Cursor.app")
        release = threading.Event()
        commands = []

        def run(argv, **kwargs):
            commands.append((argv[0], threading.get_ident()))
            return subprocess.CompletedProcess(argv, 0, "", "")

        def detect(platform, *, spotlight):
            release.wait(10)
            return apps.mac([root.name], apps._spotlight if spotlight else None)

        detected = apps.Detected(detect, platform="darwin")
        with mock.patch.object(apps.subprocess, "run", side_effect=run), \
                mock.patch.object(apps.subprocess, "Popen", side_effect=AssertionError("no app is started")):
            # Nothing found yet: the request answers at once, with none, while the look runs.
            self.assertEqual(detected.found(), {})
            self.assertEqual(detected.found(), {})  # one look at a time
            self.assertEqual(commands, [])
            release.set()
            settle(detected)
        self.assertEqual(detected.found(), {"cursor": str(Path(root.name) / "Cursor.app")})
        self.assertEqual([argv for argv, _thread in commands], ["/usr/bin/mdfind"])
        self.assertNotEqual(commands[0][1], threading.get_ident())

    def test_a_look_that_fails_keeps_what_was_found(self) -> None:
        answers = [{"zed": "/z"}, RuntimeError("no")]

        def detect(platform, *, spotlight):
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        detected = apps.Detected(detect, platform="linux")
        detected.warm().join(10)
        detected._full = False  # due again
        detected.found()
        settle(detected)
        self.assertEqual(detected.found(), {"zed": "/z"})


class OpenTest(unittest.TestCase):
    def opened(self, platform, app, **kwargs):
        spawn = mock.Mock()
        apps.open_file("/m/part.step", app, platform=platform, spawn=spawn, **kwargs)
        return spawn

    def test_each_platforms_command_detached_and_never_through_a_shell(self) -> None:
        quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
        spawn = self.opened("darwin", "/Applications/FreeCAD.app")
        spawn.assert_called_once_with(["/usr/bin/open", "-a", "/Applications/FreeCAD.app", "/m/part.step"],
                                      start_new_session=True, **quiet)
        self.opened("darwin", None).assert_called_once_with(["/usr/bin/open", "/m/part.step"], start_new_session=True, **quiet)
        self.opened("win32", "C:/FreeCAD/bin/FreeCAD.exe").assert_called_once_with(
            ["C:/FreeCAD/bin/FreeCAD.exe", "/m/part.step"], creationflags=0x00000008 | 0x00000200, **quiet)
        startfile = mock.Mock()
        self.opened("win32", None, startfile=startfile).assert_not_called()
        startfile.assert_called_once_with("/m/part.step")
        self.opened("linux", "/usr/bin/freecad").assert_called_once_with(["/usr/bin/freecad", "/m/part.step"],
                                                                        start_new_session=True, **quiet)
        with mock.patch.object(apps.executables, "find", return_value="/usr/bin/xdg-open"):
            self.opened("linux", None).assert_called_once_with(["/usr/bin/xdg-open", "/m/part.step"],
                                                              start_new_session=True, **quiet)
        with mock.patch.object(apps.executables, "find", return_value=None), \
                self.assertRaisesRegex(FileNotFoundError, "xdg-open"):
            self.opened("linux", None)


if __name__ == "__main__":
    unittest.main()
