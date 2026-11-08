"""Open in's apps (``cad_server._internal.apps``): each platform's lookup, run against a temporary tree
and a fake registry or PATH, the kinds each app takes, which KiCad reads which file, the cache that a
request reads and never fills, and the opening's commands. Nothing here starts an app or asks the
computer's own index."""
from __future__ import annotations

import calendar
import os
import plistlib
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from datetime import date
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


def kicad_bundle(path: Path, version: str | None = None, *, ident: str = "org.kicad.kicad",
                 editors: tuple[str, ...] = ("pcbnew", "eeschema"), built: date | None = None, **info) -> str:
    """A fake KiCad.app: its Info.plist, its nested editors and its program's build time."""
    (path / "Contents" / "MacOS").mkdir(parents=True)
    keys = {"CFBundleIdentifier": ident, **({"CFBundleShortVersionString": version} if version else {}), **info}
    (path / "Contents" / "Info.plist").write_bytes(plistlib.dumps(keys))
    for editor in editors:
        (path / "Contents" / "Applications" / f"{editor}.app").mkdir(parents=True)
    written(path / "Contents" / "MacOS" / "kicad", built)
    return str(path)


def written(path: Path, day: date | None) -> str:
    """A file at ``path`` last written at noon, UTC, on ``day``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    if day is not None:
        stamp = calendar.timegm(day.timetuple()) + 12 * 3600
        os.utime(path, (stamp, stamp))
    return str(path)


def editor(bundle: str, name: str) -> str:
    return os.path.join(bundle, "Contents", "Applications", f"{name}.app")


NIGHTLY_DAY = date(2026, 10, 13)
STABLE = apps.KiCad("9.0.6", date(2025, 11, 1), "/k/pcbnew", "/k/eeschema", False)
NIGHTLY = apps.KiCad("10.99.0-5334-ge37c27a8ce", NIGHTLY_DAY, "/n/pcbnew", "/n/eeschema", True)


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


class MacKiCadTest(Tree):
    def test_both_channels_at_once_each_its_newest_of_the_folders_and_spotlight(self) -> None:
        system, user = self.root / "Applications", self.root / "home" / "Applications"
        nightly = kicad_bundle(system / "KiCad" / "KiCad.app", "10.99.0-5334-ge37c27a8ce", built=NIGHTLY_DAY)
        kicad_bundle(system / "KiCad 8" / "KiCad.app", "8.0.9")
        stable = kicad_bundle(user / "KiCad" / "KiCad.app", "10.0.6", built=date(2026, 9, 1))
        renamed = kicad_bundle(self.root / "old" / "KiCad.app", "10.99.0-4000-gabcdef0123")
        newer = kicad_bundle(self.root / "elsewhere" / "KiCad.app", "10.99.0-6000-gabcdef0123", built=date(2026, 11, 1))
        self.assertEqual(apps.mac([system, user], None), {
            "kicad": apps.KiCad("10.0.6", date(2026, 9, 1), editor(stable, "pcbnew"), editor(stable, "eeschema"), False),
            "kicad-nightly": apps.KiCad("10.99.0-5334-ge37c27a8ce", NIGHTLY_DAY, editor(nightly, "pcbnew"), editor(nightly, "eeschema"), True)})
        # Spotlight's bundles count beside the folders', and the same bundle counts once.
        found = apps.mac([system, user], lambda idents: [renamed, newer, stable])
        self.assertEqual(found["kicad-nightly"].board, editor(newer, "pcbnew"))
        self.assertEqual(found["kicad"].board, editor(stable, "pcbnew"))

    def test_a_kicad_bundle_directly_in_a_folder_and_the_same_version_by_its_build(self) -> None:
        kicad_bundle(self.root / "KiCad Old.app", "10.99.0", built=date(2026, 1, 1))
        newer = kicad_bundle(self.root / "KiCad.app", "10.99.0", built=date(2026, 2, 1))
        self.assertEqual(apps.mac([self.root], None)["kicad-nightly"].board, editor(newer, "pcbnew"))

    def test_spotlight_is_always_asked_for_kicad(self) -> None:
        # Even when the folders hold every other app, so the rest of its query is empty.
        asked = []
        for names in apps.MAC_BUNDLES.values():
            bundle(self.root / names[0])
        apps.mac([self.root], lambda idents: asked.append(idents) or [])
        self.assertEqual(asked, [["org.kicad.kicad"]])

    def test_only_a_kicad_with_both_editors_and_kicads_identifier_is_one(self) -> None:
        folder = self.root / "Applications"
        kicad_bundle(folder / "KiCad" / "KiCad.app", "10.0.6", editors=("pcbnew",))
        kicad_bundle(folder / "KiCad 2" / "KiCad.app", "10.0.6", editors=("eeschema",))
        stranger = kicad_bundle(self.root / "elsewhere" / "KiCad.app", "11.0.0", ident="com.example.kicad")
        self.assertEqual(apps.mac([folder], lambda idents: [stranger]), {})

    def test_an_installations_symlinks_are_not_installations(self) -> None:
        folder = self.root / "Applications"
        real = kicad_bundle(folder / "KiCad" / "KiCad.app", "10.0.6")
        # What KiCad's folder holds beside it, and one that a KiCad* glob reaches.
        (folder / "KiCad" / "PCB Editor.app").symlink_to(editor(real, "pcbnew"))
        pcbnew = Path(editor(real, "pcbnew"))
        (pcbnew / "Contents").mkdir()
        (pcbnew / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "org.kicad.pcbnew"}))
        (folder / "KiCad PCB Editor.app").symlink_to(pcbnew)
        (folder / "KiCad Link.app").symlink_to(real)  # the same installation by another name
        self.assertEqual(list(apps.mac([folder], None)), ["kicad"])

    def test_what_a_bundle_says_of_its_version(self) -> None:
        kicad_bundle(self.root / "a" / "KiCad" / "KiCad.app", None, CFBundleVersion="9.0.8")
        self.assertEqual(apps.mac([self.root / "a"], None)["kicad"].version, "9.0.8")
        kicad_bundle(self.root / "b" / "KiCad" / "KiCad.app", None)
        self.assertEqual(apps.mac([self.root / "b"], None)["kicad"].version, None)

    def test_a_kicad_never_changes_the_first_folder_rule(self) -> None:
        first, second = self.root / "first", self.root / "second"
        kicad_bundle(first / "KiCad" / "KiCad.app", "10.0.6")
        code = bundle(first / "Visual Studio Code.app")
        bundle(second / "Visual Studio Code.app")
        self.assertEqual(apps.mac([first, second], None)["vscode"], code)


class WindowsKiCadTest(Tree):
    def install(self, folder: Path, built: date | None = None, *, editors=("pcbnew", "eeschema")) -> str:
        for name in editors:
            written(folder / "bin" / f"{name}.exe", built)
        return str(folder / "bin")

    def test_the_registry_says_the_version_and_any_custom_folder_and_the_installers_folders_the_rest(self) -> None:
        local, program_files = self.root / "Local", self.root / "Program Files"
        stable = self.install(program_files / "KiCad" / "9.0", date(2025, 11, 1))
        self.install(program_files / "KiCad" / "8.0")
        nightly = self.install(local / "Programs" / "KiCad" / "10.99", NIGHTLY_DAY)
        installs = [("9.0", "9.0.6", None), ("8.0", "8.0.9", str(program_files / "KiCad" / "8.0")),
                    ("10.99", "10.99.0.6305.g5ac898839d", None)]
        environ = {"LOCALAPPDATA": str(local), "ProgramFiles": str(program_files)}
        self.assertEqual(apps.windows(environ, lambda exe: None, lambda: installs), {
            "kicad": apps.KiCad("9.0.6", date(2025, 11, 1), os.path.join(stable, "pcbnew.exe"), os.path.join(stable, "eeschema.exe"), False),
            "kicad-nightly": apps.KiCad("10.99.0-6305-g5ac898839d", NIGHTLY_DAY, os.path.join(nightly, "pcbnew.exe"), os.path.join(nightly, "eeschema.exe"), True)})
        # A custom install is the registry's alone, and its folder is not the installers'.
        custom = self.install(self.root / "D" / "EDA" / "KiCad", date(2026, 9, 1))
        found = apps.windows({}, lambda exe: None, lambda: [("10.0", "10.0.8", str(self.root / "D" / "EDA" / "KiCad")),
                                                            ("9.0", "9.0.6", str(self.root / "gone"))])
        self.assertEqual(found, {"kicad": apps.KiCad("10.0.8", date(2026, 9, 1), os.path.join(custom, "pcbnew.exe"),
                                                     os.path.join(custom, "eeschema.exe"), False)})

    def test_with_no_key_the_folders_name_is_the_version(self) -> None:
        program_files = self.root / "Program Files"
        self.install(program_files / "KiCad" / "10.99")
        self.install(program_files / "KiCad" / "9.0")
        self.install(program_files / "KiCad" / "8.0", editors=("pcbnew",))
        found = apps.windows({"ProgramFiles": str(program_files)}, lambda exe: None)
        self.assertEqual({app: (kicad.version, kicad.nightly) for app, kicad in found.items()},
                         {"kicad": ("9.0", False), "kicad-nightly": ("10.99", True)})
        self.assertEqual(apps.kicad_label(found["kicad-nightly"]), "KiCad 10.99 nightly")
        self.assertEqual(apps.kicad_label(found["kicad"]), "KiCad 9.0")

    def test_the_uninstall_keys_are_read_the_users_then_the_machines_tolerantly(self) -> None:
        hkcu, hklm = object(), object()
        tree = {(hkcu, apps._UNINSTALL): {"KiCad 10.99": {"DisplayVersion": "10.99.0.6305.g5ac898839d", "InstallLocation": '"C:\\K"'},
                                          "Other": {"DisplayVersion": "1.0"}},
                (hklm, apps._UNINSTALL): {"KiCad 9.0": {"DisplayVersion": 9}}}
        fake = types.SimpleNamespace(HKEY_CURRENT_USER=hkcu, HKEY_LOCAL_MACHINE=hklm)

        class Key:
            def __init__(self, values):
                self.values = values

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        def open_key(parent, name):
            if isinstance(parent, Key):
                return Key(parent.values[name])
            if (parent, name) not in tree:
                raise OSError(name)
            return Key(tree[(parent, name)])

        def query(key, name):
            if name not in key.values:
                raise OSError(name)
            return key.values[name], 1

        fake.OpenKey, fake.QueryInfoKey = open_key, lambda key: (len(key.values), 0, 0)
        fake.EnumKey, fake.QueryValueEx = lambda key, index: list(key.values)[index], query
        with mock.patch.dict(sys.modules, {"winreg": fake}):
            self.assertEqual(apps._registry_kicads(), [("10.99", "10.99.0.6305.g5ac898839d", "C:\\K"), ("9.0", None, None)])
            tree.clear()
            self.assertEqual(apps._registry_kicads(), [])


class LinuxKiCadTest(Tree):
    def test_each_channel_by_its_editors_its_version_asked_of_its_command_line(self) -> None:
        commands = {name: f"/usr/bin/{name}" for name in ("pcbnew", "eeschema", "kicad-cli", "pcbnew-nightly",
                                                          "eeschema-nightly", "kicad-cli-nightly")}
        asked = []
        about = {"/usr/bin/kicad-cli": ("9.0.6+dfsg-1", date(2025, 11, 1)),
                 "/usr/bin/kicad-cli-nightly": ("10.99.0-5334-ge37c27a8ce", NIGHTLY_DAY)}

        def ask(cli):
            asked.append(cli)
            return about[cli]

        found = apps.linux(commands.get, ask)
        self.assertEqual({app: found[app] for app in ("kicad", "kicad-nightly")}, {
            "kicad": apps.KiCad("9.0.6+dfsg-1", date(2025, 11, 1), "/usr/bin/pcbnew", "/usr/bin/eeschema", False),
            "kicad-nightly": apps.KiCad("10.99.0-5334-ge37c27a8ce", NIGHTLY_DAY, "/usr/bin/pcbnew-nightly", "/usr/bin/eeschema-nightly", True)})
        self.assertEqual(asked, ["/usr/bin/kicad-cli", "/usr/bin/kicad-cli-nightly"])
        # A look that may run nothing asks nothing and sees no KiCad, so no menu offers one it has no version of.
        asked.clear()
        self.assertEqual(apps.linux(commands.get), {})
        self.assertEqual(asked, [])

    def test_without_both_editors_none_and_without_a_command_line_no_version(self) -> None:
        about = mock.Mock(side_effect=AssertionError("no kicad-cli to ask"))
        self.assertEqual(apps.linux({"pcbnew": "/p"}.get, about), {})
        found = apps.linux({"pcbnew-nightly": "/p", "eeschema-nightly": "/e"}.get, about)
        self.assertEqual(found, {"kicad-nightly": apps.KiCad(None, None, "/p", "/e", True)})
        self.assertEqual(apps.kicad_label(found["kicad-nightly"]), "KiCad nightly")
        self.assertEqual(apps.kicad_label(apps.linux({"pcbnew": "/p", "eeschema": "/e"}.get, about)["kicad"]), "KiCad")

    def test_built_is_the_abouts_else_the_day_the_editor_was_written(self) -> None:
        real = written(self.root / "lib" / "pcbnew", date(2026, 3, 4))
        link = self.root / "bin" / "pcbnew"
        link.parent.mkdir()
        link.symlink_to(real)
        commands = {"pcbnew": str(link), "eeschema": "/e", "kicad-cli": "/c"}
        self.assertEqual(apps.linux(commands.get, lambda cli: ("10.0.6", None))["kicad"].built, date(2026, 3, 4))
        # One that says nothing is unversioned; its channel is what found it.
        self.assertEqual(apps.linux(commands.get, lambda cli: (None, None))["kicad"].version, None)

    def test_a_versions_channel_is_its_minor_whatever_found_it(self) -> None:
        commands = {"pcbnew": "/p", "eeschema": "/e", "kicad-cli": "/c"}
        self.assertTrue(apps.linux(commands.get, lambda cli: ("10.99.0", None))["kicad-nightly"].nightly)


class KiCadAboutTest(unittest.TestCase):
    ABOUT = ("Application: kicad-cli x86_64 on x86_64\n\nVersion: 10.99.0-5334-ge37c27a8ce, release build\n\nLibraries:\n"
             "    wxWidgets 3.2.6\n\nPlatform: Ubuntu 24.04\n\nBuild Info:\n    Date: Oct  3 2026 01:37:00\n")

    def test_what_kicad_cli_says_of_itself_tolerantly(self) -> None:
        self.assertEqual(apps._parse_kicad_about(self.ABOUT), ("10.99.0-5334-ge37c27a8ce", date(2026, 10, 3)))
        self.assertEqual(apps._parse_kicad_about("Version: 9.0.6, release build\nDate: Oct 13 2026 01:37:00"),
                         ("9.0.6", date(2026, 10, 13)))
        self.assertEqual(apps._parse_kicad_about("Version: (5.1.9)-1, release build"), ("5.1.9", None))
        self.assertEqual(apps._parse_kicad_about("Date: Foo 13 2026\nDate: Feb 31 2026"), (None, None))
        self.assertEqual(apps._parse_kicad_about("nothing useful"), (None, None))

    def test_a_person_s_kicad_cli_runs_headless_and_leaves_nothing(self) -> None:
        seen = {}

        def run(argv, **options):
            seen.update(argv=argv, options=options, home=options["env"]["HOME"], there=os.path.isdir(options["env"]["HOME"]))
            return subprocess.CompletedProcess(argv, 0, self.ABOUT, "")

        with mock.patch.object(apps.subprocess, "run", side_effect=run), \
                mock.patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0", "HOME": "/home/person"}):
            self.assertEqual(apps._kicad_about("/usr/bin/kicad-cli-nightly"), ("10.99.0-5334-ge37c27a8ce", date(2026, 10, 3)))
        self.assertEqual(seen["argv"], ["/usr/bin/kicad-cli-nightly", "version", "--format", "about"])
        options = seen["options"]
        self.assertEqual((options["stdin"], options["timeout"], options.get("shell")), (subprocess.DEVNULL, apps.KICAD_ABOUT_SECONDS, None))
        self.assertFalse({"DISPLAY", "WAYLAND_DISPLAY"} & set(options["env"]))
        self.assertNotEqual(seen["home"], "/home/person")
        self.assertTrue(seen["there"])
        self.assertFalse(os.path.exists(seen["home"]))
        self.assertTrue(options["env"]["KICAD_CONFIG_HOME"].startswith(os.path.dirname(seen["home"])))

    def test_one_that_fails_says_nothing(self) -> None:
        for outcome in (subprocess.TimeoutExpired("kicad-cli", 10), OSError("gone"),
                        subprocess.CompletedProcess([], 1, self.ABOUT, "")):
            with self.subTest(outcome=outcome), mock.patch.object(apps.subprocess, "run", side_effect=[outcome]):
                self.assertEqual(apps._kicad_about("/usr/bin/kicad-cli"), (None, None))


class KiCadReadsTest(unittest.TestCase):
    def test_a_stable_reads_up_to_its_majors_format_for_the_files_kind(self) -> None:
        table = {6: (20211014, 20211123), 7: (20221018, 20230121), 8: (20240108, 20231120),
                 9: (20241229, 20250114), 10: (20260206, 20260306)}
        for major, (board, schematic) in table.items():
            kicad = STABLE._replace(version=f"{major}.0.3")
            for kind, stamp in (("kicad_pcb", board), ("kicad_sch", schematic)):
                with self.subTest(major=major, kind=kind):
                    self.assertTrue(apps.kicad_reads(kicad, str(stamp), kind))
                    self.assertFalse(apps.kicad_reads(kicad, str(stamp + 10000), kind))  # a year on
        self.assertTrue(apps.kicad_reads(STABLE, "20241229", "kicad_pcb"))
        self.assertFalse(apps.kicad_reads(STABLE, "20241230", "kicad_pcb"))
        self.assertTrue(apps.kicad_reads(STABLE, "20250114", "kicad_sch"))  # the board's and the schematic's differ
        self.assertFalse(apps.kicad_reads(STABLE, "20250114", "kicad_pcb"))
        # Past the table, a later major reads what it reads; a 5.x reads its own boards, and no schematic.
        self.assertTrue(apps.kicad_reads(STABLE._replace(version="11.0.0"), "20301231", "kicad_pcb"))
        five = STABLE._replace(version="5.1.9")
        self.assertTrue(apps.kicad_reads(five, "20171130", "kicad_pcb"))
        self.assertFalse(apps.kicad_reads(five, "20211014", "kicad_pcb"))
        self.assertFalse(apps.kicad_reads(five, "20211123", "kicad_sch"))
        self.assertFalse(apps.kicad_reads(STABLE._replace(version="4.0.7"), "20211014", "kicad_pcb"))

    def test_a_nightly_reads_from_the_day_before_its_build_on(self) -> None:
        self.assertTrue(apps.kicad_reads(NIGHTLY, "20261014", "kicad_pcb"))  # built + 1 day = the stamp
        self.assertFalse(apps.kicad_reads(NIGHTLY, "20261015", "kicad_pcb"))  # built + 1 day < the stamp
        self.assertTrue(apps.kicad_reads(NIGHTLY, "20241229", "kicad_sch"))
        self.assertTrue(apps.kicad_reads(NIGHTLY._replace(built=None), "20301231", "kicad_pcb"))

    def test_what_is_unknown_is_offered(self) -> None:
        for kicad, stamp in ((STABLE, None), (STABLE, "soon"), (STABLE, "20261399"), (STABLE, "2026"), (NIGHTLY, None),
                             (STABLE._replace(version=None), "20301231"), (NIGHTLY._replace(version=None), "20301231")):
            with self.subTest(kicad=kicad.version, stamp=stamp):
                self.assertTrue(apps.kicad_reads(kicad, stamp, "kicad_pcb"))

    def test_labels(self) -> None:
        for version, nightly, label in (("9.0.6", False, "KiCad 9.0.6"), ("10.0.8-rc1", False, "KiCad 10.0.8-rc1"),
                                        ("10.0.8-rc1-12-gabcdef", False, "KiCad 10.0.8-rc1"),
                                        ("9.0.6+dfsg-1", False, "KiCad 9.0.6"), ("9.0.6-1", False, "KiCad 9.0.6"),
                                        ("10.99.0-5334-ge37c27a8ce", True, "KiCad 10.99 nightly"),
                                        ("10.99.0-6305-g5ac898839d", True, "KiCad 10.99 nightly"),
                                        (None, False, "KiCad"), (None, True, "KiCad nightly")):
            with self.subTest(version=version):
                self.assertEqual(apps.kicad_label(STABLE._replace(version=version, nightly=nightly)), label)

    def test_newest_by_version_a_release_after_its_candidates_a_nightly_by_its_commits(self) -> None:
        ordered = ("9.0.6", "10.0.8-rc1", "10.0.8-rc2", "10.0.8", "10.0.9")
        self.assertEqual(apps._newest(STABLE._replace(version=version) for version in ordered)["kicad"].version, "10.0.9")
        self.assertEqual([apps._version_key(version) for version in ordered], sorted(apps._version_key(version) for version in ordered))
        self.assertLess(apps._version_key("10.99.0-5334-gabc"), apps._version_key("10.99.0-6305-gabc"))
        self.assertLess(apps._version_key(None), apps._version_key("5.1.9"))


class AppsForKiCadTest(Tree):
    def test_a_kicad_is_named_by_its_version_and_says_whether_it_refuses_the_file(self) -> None:
        board = self.root / "new.kicad_pcb"
        board.write_text("(kicad_pcb\n\t(version 20261031)\n\t(generator \"pcbnew\")\n)\n", encoding="utf-8")
        found = {"kicad": STABLE, "kicad-nightly": NIGHTLY._replace(built=date(2026, 11, 1))}
        self.assertEqual(apps.apps_for("kicad_pcb", found, board), [
            {"id": "kicad", "name": "KiCad 9.0.6", "refuses": "newer"}, {"id": "kicad-nightly", "name": "KiCad 10.99 nightly"}])
        # A file gone, a folder or no file at all: nothing to say against either.
        for file in (self.root / "gone.kicad_pcb", self.root, None):
            with self.subTest(file=file):
                self.assertEqual(apps.apps_for("kicad_pcb", found, file), [
                    {"id": "kicad", "name": "KiCad 9.0.6"}, {"id": "kicad-nightly", "name": "KiCad 10.99 nightly"}])

    def test_the_file_is_read_only_for_a_kicad(self) -> None:
        with mock.patch.object(apps, "_file_stamp", return_value="20241229") as stamp:
            self.assertEqual(apps.apps_for("kicad_pcb", {"kicad": "/plain"}, "/b.kicad_pcb"), [{"id": "kicad", "name": "KiCad"}])
            self.assertEqual(apps.apps_for("kicad_pcb", {"vscode": "/v"}, "/b.kicad_pcb"), [])
            self.assertEqual(apps.apps_for("step", {"kicad": STABLE, "freecad": "/f"}, "/b.step"), [{"id": "freecad", "name": "FreeCAD"}])
            stamp.assert_not_called()
            apps.apps_for("kicad_sch", {"kicad": STABLE, "kicad-nightly": NIGHTLY}, "/s.kicad_sch")
            stamp.assert_called_once_with("/s.kicad_sch")


class DetectTest(Tree):
    def test_a_look_without_commands_runs_none_and_a_full_one_asks(self) -> None:
        kicad_bundle(self.root / "KiCad" / "KiCad.app", "10.0.6")
        commands = {"pcbnew": "/p", "eeschema": "/e", "kicad-cli": "/c"}
        with mock.patch.object(apps, "MAC_FOLDERS", (str(self.root),)), \
                mock.patch.object(apps.executables, "find", side_effect=commands.get), \
                mock.patch.object(apps, "_kicad_about", return_value=("10.0.6", None)) as about, \
                mock.patch.object(apps, "_spotlight", return_value=[]) as spotlight, \
                mock.patch.object(apps, "_registry_app_path", return_value=None), \
                mock.patch.object(apps, "_registry_kicads", return_value=[]) as registry, \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": "", "ProgramFiles": ""}):
            self.assertEqual(list(apps.detect("darwin", commands=False)), ["kicad"])
            spotlight.assert_not_called()
            apps.detect("darwin")
            spotlight.assert_called_once()
            self.assertEqual(apps.detect("linux", commands=False), {})
            about.assert_not_called()
            self.assertEqual(apps.detect("linux")["kicad"].version, "10.0.6")
            about.assert_called_once_with("/c")
            apps.detect("win32", commands=False)
            registry.assert_called_once_with()


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
               for kind in ("script", "step", "stl", "3mf", "glb", "dxf", "urdf", "sdf", "srdf", "xbf", "kicad_pcb", "kicad_sch",
                            "mjcf")}
        self.assertEqual(ids, {"script": ["vscode", "cursor", "zed", "pycharm", "sublime"],
                               "step": ["fusion", "freecad", "bambu", "orca", "prusa"],
                               "stl": ["bambu", "orca", "prusa", "freecad", "blender"],
                               "3mf": ["bambu", "orca", "prusa", "freecad", "blender"],
                               "glb": ["blender"], "dxf": [], "urdf": [], "sdf": [], "srdf": [], "xbf": [],
                               "kicad_pcb": ["kicad", "kicad-nightly"], "kicad_sch": ["kicad", "kicad-nightly"],
                               "mjcf": ["mujoco-studio"]})
        self.assertEqual(apps.apps_for("step", {"bambu": "/b", "vscode": "/v"}), [{"id": "bambu", "name": "Bambu Studio"}])
        self.assertEqual(apps.APPS, {"vscode": "Visual Studio Code", "cursor": "Cursor", "zed": "Zed",
                                     "pycharm": "PyCharm", "sublime": "Sublime Text", "fusion": "Autodesk Fusion",
                                     "freecad": "FreeCAD", "bambu": "Bambu Studio", "orca": "OrcaSlicer",
                                     "prusa": "PrusaSlicer", "blender": "Blender", "kicad": "KiCad",
                                     "kicad-nightly": "KiCad nightly", "mujoco-studio": "MuJoCo Studio"})
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

        def detect(on, *, commands):
            self.calls.append((on, commands, threading.get_ident()))
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

    def test_on_linux_use_looks_again_with_commands_as_on_macos(self) -> None:
        detected = self.make("linux")
        detected.warm().join(10)
        self.assertEqual(detected.found(), {"vscode": "/apps/1"})
        settle(detected)
        self.assertEqual([call[:2] for call in self.calls], [("linux", False), ("linux", True)])

    def test_on_windows_the_starts_look_is_the_whole_look(self) -> None:
        detected = self.make("win32")
        detected.warm().join(10)
        self.assertEqual(detected.found(), {"vscode": "/apps/1"})
        settle(detected)
        self.assertEqual([call[:2] for call in self.calls], [("win32", False)])

    def test_a_request_never_runs_a_command_nor_waits_for_a_look(self) -> None:
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        bundle(Path(root.name) / "Cursor.app")
        release = threading.Event()
        commands = []

        def run(argv, **kwargs):
            commands.append((argv[0], threading.get_ident()))
            return subprocess.CompletedProcess(argv, 0, "", "")

        def detect(platform, *, commands):
            release.wait(10)
            return apps.mac([root.name], apps._spotlight if commands else None)

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

        def detect(platform, *, commands):
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

    def test_a_kicad_opens_its_editor_for_the_files_extension_and_nothing_else_opens_such_a_file(self) -> None:
        quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
        kicad = apps.KiCad("10.0.6", None, "/K/pcbnew.app", "/K/eeschema.app", False)
        windows = apps.KiCad("10.0.6", None, "C:/K/bin/pcbnew.exe", "C:/K/bin/eeschema.exe", False)
        linux = apps.KiCad("10.0.6", None, "/usr/bin/pcbnew-nightly", "/usr/bin/eeschema-nightly", True)
        for platform, record, command, options in (
                ("darwin", kicad, ["/usr/bin/open", "-a"], {"start_new_session": True}),
                ("win32", windows, [], {"creationflags": 0x00000008 | 0x00000200}),
                ("linux", linux, [], {"start_new_session": True})):
            for file, chosen in (("/m/a.kicad_pcb", record.board), ("/m/A.KICAD_SCH", record.schematic)):
                with self.subTest(platform=platform, file=file):
                    spawn = mock.Mock()
                    apps.open_file(file, record, platform=platform, spawn=spawn)
                    spawn.assert_called_once_with([*command, chosen, file], **options, **quiet)
        spawn, startfile = mock.Mock(), mock.Mock()
        for file, app in (("/m/a.kicad_pcb", None), ("/m/a.kicad_sch", "/usr/bin/pcbnew"), ("/m/a.kicad_pro", None),
                          ("/m/a.kicad_pro", kicad), ("/m/a.step", kicad)):
            for platform in ("darwin", "win32", "linux"):
                with self.subTest(file=file, app=app, platform=platform), self.assertRaises(PermissionError):
                    apps.open_file(file, app, platform=platform, spawn=spawn, startfile=startfile)
        spawn.assert_not_called()
        startfile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
