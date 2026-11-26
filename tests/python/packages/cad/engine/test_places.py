"""The state folder an earlier release kept, adopted (``cad.engine.places.adopt``, ``adopt_earlier``).

0.10 names its state folder ``cad`` where 0.8's was ``cadgen``: what this release keeps of the earlier one
-- the person's settings, the documents' records and Recents, and setup's receipt -- moves into its own, each
once, and the rest stays -- 0.8's installations' records, its engines' records and page token, its install
channels --, with the person's telemetry no for the earlier release still installed. Every folder here is a
temporary one: the platform's places are stood in for, never read.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import handoff, places

EVERYTHING = ["settings.json", "documents", "recents", "install-receipt.json"]


def write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Folders(unittest.TestCase):
    """An earlier release's state folder, as 0.8 left it, and where this release's goes."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="places-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.earlier, self.folder = self.root / "cadgen", self.root / "cad"
        write(self.earlier / "settings.json", '{"telemetry": {"choice": "off"}}')
        write(self.earlier / "installations" / "0.8.4.json", '{"version": "0.8.4"}')
        write(self.earlier / "installations" / "current", "0.8.4")
        write(self.earlier / "engines" / "token", "t" * 43)
        write(self.earlier / "engines" / "engine.json", '{"port": 3245}')
        write(self.earlier / "documents" / "a" / "document.json", "{}")
        write(self.earlier / "recents" / "thumbnails" / "a.png")
        write(self.earlier / "install-receipt.json", "{}")
        write(self.earlier / "install-channels.json", "{}")
        for kept in ("settings.lock", "install.lock", "telemetry-spool.jsonl"):
            write(self.earlier / kept)


class AdoptTest(Folders):
    def test_what_this_release_keeps_moves_and_the_rest_stays(self) -> None:
        self.assertEqual(places.adopt(self.earlier, self.folder), EVERYTHING)
        self.assertEqual((self.folder / "settings.json").read_text(encoding="utf-8"), '{"telemetry": {"choice": "off"}}',
                         "a no stays a no")
        self.assertTrue((self.folder / "documents" / "a" / "document.json").is_file())
        self.assertTrue((self.folder / "recents" / "thumbnails" / "a.png").is_file())
        self.assertEqual((self.folder / "install-receipt.json").read_text(encoding="utf-8"), "{}")
        # Moved, never copied: what only 0.8 runs by -- its installations' records, its engines' with the page
        # token, its install channels --, the locks and what was noted and not sent stay behind, and the
        # person's no, for the earlier release still installed, which would take settings it found missing for
        # never told.
        self.assertEqual(sorted(path.name for path in self.earlier.iterdir()),
                         ["engines", "install-channels.json", "install.lock", "installations", "settings.json",
                          "settings.lock", "telemetry-spool.jsonl"])
        self.assertEqual((self.earlier / "engines" / "token").read_text(encoding="utf-8"), "t" * 43)
        self.assertEqual((self.earlier / "installations" / "current").read_text(encoding="utf-8"), "0.8.4")
        self.assertFalse((self.folder / "engines").exists() or (self.folder / "installations").exists())
        self.assertEqual(json.loads((self.earlier / "settings.json").read_text(encoding="utf-8")),
                         {"telemetry": {"choice": "off"}})
        self.assertEqual(places.adopt(self.earlier, self.folder), [], "once")

    def test_only_a_no_stays_behind_and_without_the_deletion_it_owes(self) -> None:
        for kept, behind in (({"choice": "off", "decidedAt": 2, "forget": ["id"]}, {"choice": "off", "decidedAt": 2}),
                             ({"choice": "on", "decidedAt": 2}, None), ({"notice": 1, "notifiedAt": 1}, None)):
            with self.subTest(kept=kept):
                for folder in (self.earlier, self.folder):
                    (folder / "settings.json").unlink(missing_ok=True)
                write(self.earlier / "settings.json", json.dumps({"telemetry": kept, "language": "de"}))
                places.adopt(self.earlier, self.folder)
                self.assertEqual(json.loads((self.folder / "settings.json").read_text(encoding="utf-8")),
                                 {"telemetry": kept, "language": "de"}, "the settings move whole")
                left = self.earlier / "settings.json"
                self.assertEqual(json.loads(left.read_text(encoding="utf-8")) if left.exists() else None,
                                 {"telemetry": behind} if behind else None)

    def test_what_this_release_already_keeps_is_never_replaced(self) -> None:
        write(self.folder / "settings.json", '{"telemetry": {"notifiedAt": 1}}')
        write(self.folder / "recents" / "thumbnails" / "b.png", "mine")
        self.assertEqual(places.adopt(self.earlier, self.folder),
                         [name for name in EVERYTHING if name not in ("settings.json", "recents")])
        self.assertEqual(sorted(path.name for path in (self.folder / "recents" / "thumbnails").iterdir()), ["b.png"])
        self.assertEqual((self.folder / "settings.json").read_text(encoding="utf-8"), '{"telemetry": {"notifiedAt": 1}}')
        self.assertTrue((self.earlier / "recents" / "thumbnails" / "a.png").is_file(), "left where it was")

    def test_no_earlier_folder_moves_nothing_and_makes_nothing(self) -> None:
        self.assertEqual(places.adopt(self.root / "absent", self.folder), [])
        self.assertFalse(self.folder.exists())


class AdoptEarlierTest(Folders):
    """Where no state folder is named: the platform's places, stood in for."""

    def platform(self, names: tuple[str, str]) -> Path:
        return {places.EARLIER_STATE: self.earlier}[names]

    def setUp(self) -> None:
        super().setUp()
        local = mock.patch.object(places, "_local_state", return_value=self.root)  # this release's: root/cad
        local.start()
        self.addCleanup(local.stop)

    def test_the_earlier_folder_is_adopted_once_whatever_this_release_wrote_first(self) -> None:
        # A told command (`cad doctor`'s notice) may have written this release's folder first.
        write(self.folder / "telemetry-batches.jsonl")
        with mock.patch.object(places, "_platform_state", side_effect=self.platform), \
                mock.patch.dict(os.environ, {"CAD_STATE_DIR": ""}):
            self.assertEqual(places.adopt_earlier(), EVERYTHING)
            self.assertEqual(places.state_dir(), self.folder)
            write(self.earlier / "documents" / "b" / "document.json", "{}")  # written by 0.8 after the move
            self.assertEqual(places.adopt_earlier(), [], "this release's folder has it: never again")
        self.assertFalse((self.folder / "documents" / "b").exists())

    def test_what_earlier_releases_left_is_looked_for_in_their_own_folders_or_the_ones_named(self) -> None:
        with mock.patch.object(places, "_platform_state", side_effect=self.platform), \
                mock.patch.dict(os.environ, {"CAD_STATE_DIR": "", "CAD_CACHE_DIR": "", "XDG_CACHE_HOME": str(self.root),
                                             "LOCALAPPDATA": str(self.root)}):
            self.assertEqual(places.earlier_state_dir(), self.earlier)
            self.assertEqual(places.earlier_cache_dir(), self.root / "cadgen")
            self.assertEqual(places.cache_dir(), self.root / "cad")
        named = {"CAD_STATE_DIR": str(self.root / "s"), "CAD_CACHE_DIR": str(self.root / "c")}
        with mock.patch.dict(os.environ, named):
            self.assertEqual((places.earlier_state_dir(), places.earlier_cache_dir()), (self.root / "s", self.root / "c"))

    def test_a_named_state_folder_adopts_nothing(self) -> None:
        named = self.root / "named"
        with mock.patch.object(places, "_platform_state", side_effect=self.platform), \
                mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(named)}):
            self.assertEqual(places.adopt_earlier(), [])
            self.assertEqual(places.state_dir(), named)
        self.assertFalse(self.folder.exists())
        self.assertFalse(named.exists())
        self.assertTrue((self.earlier / "installations" / "current").is_file())


class WindowsTest(Folders):
    """On Windows 0.10.0 kept its folders in the local application data, which an app package (the Claude
    desktop app's) virtualizes for every process it starts; this release keeps them in the user's own
    folder, as Linux does, and moves what 0.10.0 kept there once -- 0.10.0's folder before 0.8's, whose
    settings are only the telemetry no it kept behind (#759)."""

    def setUp(self) -> None:
        super().setUp()
        self.home = self.root / "home"
        self.appdata = self.root / "AppData" / "Local"
        self.ten = self.appdata / "cad-state"
        (self.earlier / "settings.json").write_text('{"telemetry": {"choice": "off"}}', encoding="utf-8")
        for name in ("documents", "recents", "install-receipt.json"):
            path = self.earlier / name
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        write(self.ten / "settings.json", '{"telemetry": {"choice": "off"}, "language": "zh-TW"}')
        write(self.ten / "engines" / "token", "u" * 43)
        write(self.ten / "engines" / "engine.json", '{"port": 3246, "schema": 3}')
        write(self.ten / "documents" / "a" / "document.json", "{}")
        write(self.ten / "recents" / "thumbnails" / "a.png")
        write(self.ten / "install-receipt.json", "{}")
        write(self.ten / "install-channels.json", "{}")
        write(self.ten / "installations" / "current", "0.10.0")
        write(self.ten / "releases" / "0.10.0" / "Scripts" / "python.exe")
        write(self.appdata / "cad" / "documents" / "a" / "document.xbf", "xbf")
        write(self.appdata / "cad" / "base" / "0123" / "pyvenv.cfg")
        environment = {"CAD_STATE_DIR": "", "CAD_CACHE_DIR": "", "CAD_ENGINE_DIR": "", "XDG_STATE_HOME": "",
                       "XDG_CACHE_HOME": "", "HOME": str(self.home), "USERPROFILE": str(self.home),
                       "LOCALAPPDATA": str(self.appdata)}
        for patch in (mock.patch.object(places, "WINDOWS", True), mock.patch("sys.platform", "win32"),
                      mock.patch.object(places, "_platform_state", side_effect=lambda names: self.earlier),
                      mock.patch.dict(os.environ, environment)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_folders_are_the_users_own_out_of_the_local_application_data(self) -> None:
        self.assertEqual(places.state_dir(), self.home / ".local" / "state" / "cad")
        self.assertEqual(places.cache_dir(), self.home / ".cache" / "cad")
        self.assertEqual(Path(places.default_engine_dir()), self.home / ".local" / "state" / "cad-engine")
        self.assertEqual((places.appdata_state_dir(), places.appdata_cache_dir()), (self.ten, self.appdata / "cad"))
        self.assertEqual(places.appdata_engine_dir(), Path(tempfile.gettempdir()) / "cad-engine")
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": "s", "CAD_CACHE_DIR": "c", "CAD_ENGINE_DIR": "e"}):
            self.assertEqual((places.appdata_state_dir(), places.appdata_cache_dir(), places.appdata_engine_dir()),
                             (None, None, None))

    def test_what_0_10_kept_moves_once_with_the_page_token_its_port_and_its_documents_bytes(self) -> None:
        state, cache = places.state_dir(), places.cache_dir()
        self.assertEqual(places.adopt_earlier(), [*places.APPDATA_ADOPTED, "documents"])
        self.assertEqual(json.loads((state / "settings.json").read_text(encoding="utf-8")),
                         {"telemetry": {"choice": "off"}, "language": "zh-TW"}, "0.10's whole settings, not 0.8's no")
        self.assertEqual((state / "engines" / "token").read_text(encoding="utf-8"), "u" * 43, "every link still works")
        self.assertEqual(json.loads((state / "engines" / "engine.json").read_text(encoding="utf-8"))["port"], 3246)
        self.assertTrue((state / "documents" / "a" / "document.json").is_file())
        self.assertEqual((cache / "documents" / "a" / "document.xbf").read_text(encoding="utf-8"), "xbf")
        # What 0.10.0 runs by stays for it -- its installations, its release, its base --, and its telemetry no.
        self.assertTrue((self.ten / "installations" / "current").is_file())
        self.assertTrue((self.ten / "releases" / "0.10.0" / "Scripts" / "python.exe").is_file())
        self.assertTrue((self.appdata / "cad" / "base" / "0123" / "pyvenv.cfg").is_file())
        self.assertEqual(json.loads((self.ten / "settings.json").read_text(encoding="utf-8")),
                         {"telemetry": {"choice": "off"}})
        self.assertFalse((state / "installations").exists() or (cache / "base").exists())
        self.assertEqual(places.adopt_earlier(), [], "once")


class OutsidePackageTest(unittest.TestCase):
    """On Windows, from inside an app package, the server and cad's update start outside it (``places.outside_package``):
    Task Scheduler starts a go-between (``cad.engine.handoff``) that starts them; elsewhere, and where that hand-off
    cannot be made, ``subprocess.Popen`` as before. ``schtasks`` and kernel32 are stand-ins here; the go-between is the
    real one, its start of the command a stand-in."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="handoff-")
        self.addCleanup(scratch.cleanup)
        self.state = Path(scratch.name) / "state"
        patched = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state)})
        patched.start()
        self.addCleanup(patched.stop)

    def test_not_packaged_starts_as_popen_does(self) -> None:
        with mock.patch.object(places, "packaged", return_value=False), \
                mock.patch.object(places, "_hand_off") as hand_off, \
                mock.patch.object(places.subprocess, "Popen", return_value="started") as popen:
            self.assertEqual(places.outside_package(["cad"], env={"A": "1"}, cwd="here", creationflags=8,
                                                    stdin=-3), "started")
        hand_off.assert_not_called()
        popen.assert_called_once_with(["cad"], env={"A": "1"}, cwd="here", creationflags=8, stdin=-3)
        self.assertFalse(places.packaged() if os.name != "nt" else False, "never packaged off Windows")

    def test_out_of_the_starter_s_job_where_it_allows_it_else_in_it(self) -> None:
        """``detached(breakaway=True)``: out of the job of the app that ran cad (an app closing it ends what is in it);
        a job that allows no breakaway refuses the start (access denied), and the command starts in it. A start
        refused with no breakaway asked raises as Popen does; the go-between is never handed the flag, which it asks
        for itself and drops where refused (``cad.engine.handoff``)."""
        away, group = places.CREATE_BREAKAWAY_FROM_JOB, 0x08000200
        with mock.patch.object(places, "packaged", return_value=False), \
                mock.patch.object(places.subprocess, "Popen", side_effect=[PermissionError(5, "denied"), "started"]) as popen:
            self.assertEqual(places.outside_package(["py"], creationflags=group | away, stdin=-3), "started")
        self.assertEqual(popen.call_args_list, [mock.call(["py"], creationflags=group | away, stdin=-3),
                                                mock.call(["py"], creationflags=group, stdin=-3)])
        with mock.patch.object(places, "packaged", return_value=False), \
                mock.patch.object(places.subprocess, "Popen", side_effect=FileNotFoundError("py")) as popen, \
                self.assertRaises(FileNotFoundError):
            places.outside_package(["py"], creationflags=group)
        popen.assert_called_once()
        with mock.patch.object(places, "packaged", return_value=True), \
                mock.patch.object(places, "_hand_off", return_value="started") as hand_off:
            places.outside_package(["py"], env={}, cwd="here", creationflags=group | away)
        hand_off.assert_called_once_with(["py"], env={}, cwd="here", flags=group)
        with mock.patch.object(places, "os", mock.Mock(wraps=os, name="nt")) as faked:
            faked.name = "nt"
            self.assertEqual(places.detached(breakaway=True), {"creationflags": group | away})
            self.assertEqual(places.detached(), {"creationflags": group})

    def test_packaged_hands_the_command_to_task_scheduler(self) -> None:
        with mock.patch.object(places, "packaged", return_value=True), \
                mock.patch.object(places, "_hand_off", return_value="started") as hand_off, \
                mock.patch.object(places.subprocess, "Popen") as popen:
            self.assertEqual(places.outside_package(["py", "-m", "daemon"], env={"A": "1"}, cwd="here",
                                                    creationflags=0x08000200, stdin=-3), "started")
            places.outside_package(["py"], creationflags=8)
        popen.assert_not_called()
        self.assertEqual(hand_off.call_args_list[0], mock.call(["py", "-m", "daemon"], env={"A": "1"}, cwd="here",
                                                               flags=0x08000200))
        self.assertEqual(hand_off.call_args_list[1], mock.call(["py"], env=dict(os.environ), cwd=os.getcwd(), flags=8),
                         "the caller's environment and folder, as Popen would inherit them")

    def test_a_hand_off_that_fails_starts_as_popen_does_logged_once_and_never_raises_past_it(self) -> None:
        for failure in (OSError(5, "refused"), TimeoutError("no answer"), FileNotFoundError("schtasks.exe"),
                        ValueError("anything")):
            with self.subTest(failure=failure), mock.patch.object(places, "packaged", return_value=True), \
                    mock.patch.object(places, "_hand_off", side_effect=failure), \
                    mock.patch.object(places.subprocess, "Popen", return_value="started") as popen, \
                    self.assertLogs("cad.engine.places", "WARNING") as logged:
                self.assertEqual(places.outside_package(["C:/env/python.exe", "-m", "x"], creationflags=8), "started")
                popen.assert_called_once_with(["C:/env/python.exe", "-m", "x"], creationflags=8)
                self.assertEqual(len(logged.output), 1)
                self.assertIn("python.exe outside this Windows app package, so it starts inside it", logged.output[0])

    def test_the_task_has_no_trigger_runs_on_battery_as_the_user_with_no_password(self) -> None:
        from xml.etree import ElementTree

        data = places._task_definition([r"C:\Program Files\py\pythonw.exe", "-I", r"C:\a b\handoff.py", "r&<.json"],
                                       user=r"PC\jo")
        self.assertTrue(data.startswith(b"\xff\xfe"), "UTF-16 with its byte order mark, as schtasks /XML reads it")
        text = data[2:].decode("utf-16-le")
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="UTF-16"?>'))
        task = ElementTree.fromstring(text.split("\n", 1)[1])
        ns = {"t": places.TASK}

        def said(path: str) -> str | None:
            found = task.find(path, ns)
            return None if found is None else found.text

        self.assertIsNone(task.find("t:Triggers", ns), "no trigger: it runs only on /Run")
        self.assertEqual([said(f"t:Settings/t:{name}") for name in ("DisallowStartIfOnBatteries",
                                                                     "StopIfGoingOnBatteries")], ["false", "false"])
        self.assertEqual(said("t:Settings/t:MultipleInstancesPolicy"), "Parallel")
        self.assertEqual(said("t:Settings/t:Hidden"), "true")
        self.assertEqual(said("t:Settings/t:Priority"), "5", "normal: the default, 7, is below normal and inherited")
        self.assertEqual(said("t:Principals/t:Principal/t:LogonType"), "InteractiveToken")
        self.assertEqual(said("t:Principals/t:Principal/t:RunLevel"), "LeastPrivilege")
        self.assertEqual(said("t:Principals/t:Principal/t:UserId"), r"PC\jo")
        self.assertNotIn("Password", text)
        self.assertEqual(said("t:Actions/t:Exec/t:Command"), r'"C:\Program Files\py\pythonw.exe"')
        self.assertEqual(said("t:Actions/t:Exec/t:Arguments"), r'-I "C:\a b\handoff.py" r&<.json')
        bare = places._task_definition(["py"])[2:].decode("utf-16-le").split("\n", 1)[1]
        self.assertIsNone(ElementTree.fromstring(bare).find("t:Principals/t:Principal/t:UserId", ns),
                          "no user named: the current one's")

    def test_the_go_between_runs_isolated_from_the_module_file(self) -> None:
        command = places._between(Path("state/handoff/x.json"))
        self.assertEqual(command[1:], ["-I", str(Path(places.__file__).with_name("handoff.py")),
                                       str(Path("state/handoff/x.json"))])
        self.assertTrue(Path(command[2]).is_file())

    def test_a_hand_off_starts_the_command_by_the_go_between_and_leaves_nothing(self) -> None:
        schtasks, kernel = Schtasks(self, between=True), Kernel()
        given = {"Path": "caller-path", "CAD_ENGINE_DIR": "e", "uv_cache_dir": "u", "PYTHONPATH": "src",
                 "https_proxy": "h", "SSL_CERT_FILE": "c", "OPENAI_API_KEY": "sk-never-written", "A": "1"}
        own = {"PERSONS_OWN": "theirs", "PYTHONDONTWRITEBYTECODE": "1", "PATH": "default-path"}
        with mock.patch.dict(os.environ, own), \
                mock.patch.object(handoff.subprocess, "Popen", side_effect=[OSError(5, "no breakaway"), Child(4321)]) \
                as popen:
            os.environ.pop("OPENAI_API_KEY", None)
            started = places._hand_off(["py", "-m", "daemon"], env=given, cwd="here", flags=0x08000200,
                                       run=schtasks, kernel=kernel, seconds=5)
        schtasks.thread.join(5)
        self.assertEqual((started.pid, started.handle), (4321, 104321))
        self.assertEqual([call[0] for call in schtasks.calls], ["/Create", "/Run", "/Delete"])
        create, name = schtasks.calls[0], schtasks.calls[0][4]
        self.assertEqual(create[1:3], ("/XML", str(self.state / "handoff" / f"{name}.xml")))
        self.assertEqual(schtasks.calls[1:], [("/Run", "/TN", name), ("/Delete", "/TN", name, "/F")])
        self.assertEqual(schtasks.request.parent, self.state / "handoff", "in the state folder, never under AppData")
        self.assertEqual(schtasks.told["argv"], ["py", "-m", "daemon"])
        carried = {name: value for name, value in given.items() if name not in ("OPENAI_API_KEY", "A")}
        self.assertEqual((schtasks.told["env"], schtasks.told["cwd"]), (carried, "here"), "only what cad needs")
        self.assertNotIn("sk-never-written", schtasks.text)
        self.assertNotIn("OPENAI_API_KEY", schtasks.text, "never the whole environment on disk")
        if os.name != "nt":
            self.assertEqual(schtasks.mode, 0o600, "its owner's alone")
        breakaway, kept = popen.call_args_list
        self.assertEqual(breakaway.kwargs["creationflags"], 0x08000200 | handoff.CREATE_BREAKAWAY_FROM_JOB)
        self.assertEqual(kept.kwargs["creationflags"], 0x08000200, "in the job where it allows no breakaway")
        self.assertEqual({kept.kwargs[name] for name in ("stdin", "stdout", "stderr")}, {subprocess.DEVNULL})
        self.assertEqual((kept.args[0], kept.kwargs["cwd"]), (["py", "-m", "daemon"], "here"))
        env = kept.kwargs["env"]
        self.assertEqual({name: env[name] for name in carried}, carried, "what cad needs, from its caller")
        self.assertEqual(env["PERSONS_OWN"], "theirs", "the rest the person's own, as the task has it")
        self.assertFalse({"PATH", "PYTHONDONTWRITEBYTECODE", "OPENAI_API_KEY", "A"} & set(env),
                         "a carried name the caller had not set is not set: the default's PATH gives way to Path")
        self.assertEqual(schtasks.between_code, 0)
        self.assertIn(os.getpid() + 100000, kernel.waited, "the go-between waited for before its task goes")
        self.assertEqual(list((self.state / "handoff").iterdir()), [], "no request, definition or answer left")
        self.assertIsNone(started.poll())
        kernel.ended[104321] = 3
        self.assertEqual((started.poll(), started.poll()), (3, 3))
        self.assertIn(104321, kernel.closed)

    def test_a_refused_task_or_one_that_never_runs_raises_and_leaves_nothing(self) -> None:
        refused = Schtasks(self, refuse="/Create")
        with self.assertRaisesRegex(OSError, "refused by policy"):
            places._hand_off(["py"], env={}, cwd="here", flags=0, run=refused, kernel=Kernel(), seconds=5)
        self.assertEqual([call[0] for call in refused.calls], ["/Create"], "nothing made, nothing to delete")
        never = Schtasks(self)  # /Run says yes, and no session runs the task
        with self.assertRaisesRegex(TimeoutError, "did not answer"):
            places._hand_off(["py"], env={}, cwd="here", flags=0, run=never, kernel=Kernel(), seconds=0.2)
        self.assertEqual([call[0] for call in never.calls], ["/Create", "/Run", "/Delete"])
        self.assertEqual(handoff.main([str(never.request)]), 1, "a go-between that starts late starts nothing")
        self.assertEqual(list((self.state / "handoff").iterdir()), [])

    def test_a_command_the_go_between_cannot_start_raises_and_leaves_nothing(self) -> None:
        schtasks = Schtasks(self, between=True)
        with mock.patch.object(handoff.subprocess, "Popen", side_effect=FileNotFoundError(2, "no such file")), \
                self.assertRaisesRegex(OSError, "the go-between could not start it: FileNotFoundError"):
            places._hand_off(["nothing"], env={}, cwd="here", flags=0, run=schtasks, kernel=Kernel(), seconds=5)
        schtasks.thread.join(5)
        self.assertEqual(schtasks.between_code, 1)
        self.assertEqual([call[0] for call in schtasks.calls], ["/Create", "/Run", "/Delete"])
        self.assertEqual(list((self.state / "handoff").iterdir()), [])

    def test_what_a_crash_left_goes_at_the_next_hand_off_and_at_the_servers_start(self) -> None:
        folder = self.state / "handoff"
        folder.mkdir(parents=True)
        old, fresh = write(folder / "cad-1-old.json", '{"env": {}}'), write(folder / "cad-2-fresh.pid", "{}")
        left = write(folder / "cad-1-old.pid.part", "{")
        os.utime(old, (time.time() - 61, time.time() - 61))
        os.utime(left, (time.time() - 3600, time.time() - 3600))
        self.assertEqual(sorted(places.tidy_handoff()), sorted([old, left]))
        self.assertEqual(list(folder.iterdir()), [fresh], "one a hand-off underway may be using stays")
        self.assertEqual(places.tidy_handoff(now=time.time() + 61), [fresh])
        stale = write(folder / "cad-3-old.xml", "")
        os.utime(stale, (time.time() - 120, time.time() - 120))
        refused = Schtasks(self, refuse="/Create")
        with self.assertRaises(OSError):
            places._hand_off(["py"], env={}, cwd="here", flags=0, run=refused, kernel=Kernel(), seconds=5)
        self.assertEqual(list(folder.iterdir()), [], "a hand-off removes what a crash left first")
        shutil.rmtree(folder)
        self.assertEqual(places.tidy_handoff(), [], "no folder: nothing to do, and no error")

    def test_a_request_taken_late_is_waited_for_once_more(self) -> None:
        folder = self.state / "handoff"
        folder.mkdir(parents=True)
        request, reply = folder / "x.json", folder / "x.pid"
        self.assertFalse(request.exists())  # taken by a go-between: it answers within the second wait
        timer = threading.Timer(0.6, handoff.answer, (str(reply), {"pid": 9, "between": 8}))
        timer.start()
        self.addCleanup(timer.cancel)
        self.assertEqual(places._answer(request, reply, 0.5), {"pid": 9, "between": 8})
        if os.name != "nt":
            self.assertEqual(reply.stat().st_mode & 0o777, 0o600, "the answer its owner's alone")
        reply.unlink()
        with self.assertRaises(TimeoutError):
            places._answer(request, reply, 0.05)


class Child:
    """A process the go-between started."""

    def __init__(self, pid: int) -> None:
        self.pid = pid


class Schtasks:
    """``schtasks`` as ``places._hand_off`` runs it: each call kept, the definition read as it is registered, and on
    ``/Run`` (``between``) the go-between run from it, on a thread, as Task Scheduler would run it."""

    def __init__(self, test: unittest.TestCase, *, between: bool = False, refuse: str | None = None) -> None:
        self.test, self.between, self.refuse = test, between, refuse
        self.calls: list[tuple[str, ...]] = []
        self.request = self.told = self.thread = self.between_code = self.text = self.mode = None

    def __call__(self, *arguments: str) -> None:
        from xml.etree import ElementTree

        self.calls.append(arguments)
        if arguments[0] == self.refuse:
            raise OSError(f"schtasks {arguments[0]} exited 1: ERROR: refused by policy")
        if arguments[0] == "/Create":
            text = Path(arguments[2]).read_bytes()[2:].decode("utf-16-le").split("\n", 1)[1]
            line = ElementTree.fromstring(text).find(f"{{{places.TASK}}}Actions/{{{places.TASK}}}Exec/"
                                                     f"{{{places.TASK}}}Arguments").text
            self.request = Path(line.split()[-1])
            self.text = self.request.read_text(encoding="utf-8")
            self.told, self.mode = json.loads(self.text), self.request.stat().st_mode & 0o777
            self.test.assertEqual(line.split()[:2], ["-I", str(Path(places.__file__).with_name("handoff.py"))])
        if arguments[0] == "/Run" and self.between:
            def go() -> None:
                self.between_code = handoff.main([str(self.request)])

            self.thread = threading.Thread(target=go)
            self.thread.start()


class Kernel:
    """kernel32 as ``places._hand_off`` and ``places.Started`` call it: a handle is its process's id plus 100000;
    ``ended`` the processes that ended, by handle, with their exit status."""

    def __init__(self) -> None:
        self.ended: dict[int, int] = {}
        self.waited: list[int] = []
        self.closed: list[int] = []

    def OpenProcess(self, access, inherit, pid):  # noqa: N802 - Windows' names
        assert access == places.SYNCHRONIZE | places.PROCESS_QUERY_LIMITED_INFORMATION and not inherit
        return pid + 100000

    def WaitForSingleObject(self, handle, milliseconds):  # noqa: N802
        self.waited.append(handle)
        return 0 if handle in self.ended or milliseconds else 258

    def GetExitCodeProcess(self, handle, code):  # noqa: N802
        code._obj.value = self.ended[handle]
        return True

    def CloseHandle(self, handle):  # noqa: N802
        self.closed.append(handle)
        return True


if __name__ == "__main__":
    unittest.main()
