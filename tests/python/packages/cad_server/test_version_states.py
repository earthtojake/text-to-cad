"""Every state a version folder can be in, and what each removal does with it (``versions.fate``'s table): a plain
``cad uninstall`` keeps the data, which a later install finds (D1); a pointer that names no version is never read as
none, and only ``cad setup``, the updater and ``cad doctor`` write it again (D2, D9); a ``channels`` entry this
release does not understand stops removal (D3); only a process of a version's heir carries its data and removes it
(D4); "used" means a pointer named it, so an import alone leaks nothing, and ``--prune`` forgetting a channel with no
heir removes its version whole (D5); ``cad doctor --check`` takes and makes nothing (D6); a sweep never waits on a
process that runs from a folder (D7); a ledger that cannot be read stops the carry, and what the person deleted stays
deleted (D10); the mirror read strictly for a removal (D11); the proof's door is never the version's own (D13). The
device is ``test_versions.Device``'s."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.python.packages.cad_server.test_versions import IDENT, Device, X, Y, Z

from cad.engine import places
from cad_server._internal import imports, legacy, pins, pointers, releases, versions
from cad_server._internal.cli_errors import Failure
from cad_server.engine import registry

LATE = "2b0e0a8e-6d0a-4c6e-9a63-1f2d3c4b5a69"


def record(data: Path, ident: str, opened: float) -> None:
    folder = data / "documents" / ident
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "document.json").write_text(json.dumps({"schema": registry.SCHEMA, "id": ident, "kind": "file",
                                                      "opened": opened}), encoding="utf-8")


def has(name: str, ident: str) -> bool:
    return (places.data_dir(name) / "documents" / ident / "document.json").is_file()


def settings(name: str) -> dict:
    return json.loads((places.data_dir(name) / "settings.json").read_text(encoding="utf-8"))


class Uninstall(Device):
    """D1: ``cad uninstall`` without ``--purge`` removes the default version's code and keeps its data."""

    def leave(self) -> None:
        """What ``cad uninstall`` does to the default channel's pointer (``setup.Installer._remove_versions``): it and
        the mirror removed."""
        (self.state / "default").unlink()
        (self.state / "installations" / "current").unlink(missing_ok=True)

    def uninstall(self, name: str) -> None:
        """And its version's code removed."""
        self.leave()
        self.assertEqual(versions.remove_code(name, told=self.said.append), "removed")

    def test_the_data_stays_and_a_later_install_of_the_same_or_a_newer_release_takes_it(self) -> None:
        self.moved(None, X)
        record(places.data_dir(X), IDENT, 1.0)
        held = registry.Registry(places.data_dir(X))
        held.token() or held.make_token("t" * 43)
        token = held.token()
        self.uninstall(X)
        self.assertFalse(places.code_dir(X).exists(), "its code removed")
        self.assertTrue(has(X, IDENT), "its documents' records kept")
        self.assertEqual(versions.fate(X, versions._kept()), "uninstalled")
        self.assertEqual(versions.sweep(), {X: "uninstalled"}, "no sweep takes it")
        self.assertEqual(versions.prune(versions.prune_plan()), {}, "nor cad doctor --prune")
        # The install command again, the same release: its data found as it was.
        moved = self.moved(None, X)
        self.assertEqual(moved.kind, "moved")
        self.assertTrue(has(X, IDENT))
        self.assertEqual(registry.Registry(places.data_dir(X)).token(), token, "the same token: old links open")
        self.assertFalse((places.version_dir(X) / versions.UNINSTALLED).exists())
        # Uninstalled again, then a newer release: its data imported, and the folder left goes after the carry.
        self.uninstall(X)
        moved = self.moved(None, Y)
        self.assertEqual((moved.old, imports.marker(Y)["imported"]["version"]), (X, X))
        self.assertTrue(has(Y, IDENT))
        self.assertEqual(moved.removed, {X: "removed"})
        self.assertFalse(places.version_dir(X).exists())

    def test_a_newer_release_that_has_data_already_has_the_kept_data_carried_in(self) -> None:
        self.moved("store", Y)  # a store's channel on Y: Y has data of its own
        self.moved(None, X)
        record(places.data_dir(X), LATE, 2.0)
        self.uninstall(X)
        moved = self.moved(None, Y)
        self.assertEqual(moved.old, X)
        self.assertTrue(has(Y, LATE), "carried in")
        self.assertFalse(places.version_dir(X).exists())

    def test_an_older_release_after_it_starts_afresh_and_the_kept_data_stays(self) -> None:
        self.moved(None, Y)
        self.uninstall(Y)
        moved = self.moved(None, X)
        self.assertIsNone(moved.old, "data never goes back to an older version")
        self.assertTrue(places.data_dir(Y).is_dir())
        self.assertEqual(versions.fate(Y, versions._kept()), "uninstalled")

    def test_code_the_system_refused_goes_at_the_next_sweep_and_the_data_stays(self) -> None:
        self.moved(None, X)
        self.leave()
        real = os.rename

        def refuse(source, target):
            if Path(source) == places.code_dir(X):
                raise PermissionError(13, "in use")
            return real(source, target)

        with mock.patch.object(os, "rename", refuse):
            self.assertEqual(versions.remove_code(X), "refused")
        self.assertTrue(places.code_dir(X).is_dir())
        self.assertTrue(versions.garbage())
        self.assertEqual(versions.sweep(), {X: "uninstalled"})
        self.assertFalse(places.code_dir(X).exists(), "the code gone at the next sweep")
        self.assertTrue(places.data_dir(X).is_dir(), "its data kept")


    def test_an_uninstall_tries_a_refused_rename_again_for_a_while_and_says_why_a_sweep_tries_once(self) -> None:
        # On Windows a stopped server's process keeps its files a moment after it lets its lock go: the uninstall (a
        # person waiting) tries the rename again, bounded; a sweep tries once and says the next sweep.
        real, refusals = os.rename, []

        def refuse(times: int):
            def rename(source, target):
                if Path(source) in (places.code_dir(X), places.version_dir(X)) and len(refusals) < times:
                    refusals.append(source)
                    raise PermissionError(13, "The process cannot access the file")
                return real(source, target)
            return rename

        for remove in (versions.remove_code, versions.remove_now):
            with self.subTest(remove=remove.__name__):
                self.moved(None, X)
                self.leave()
                refusals.clear()
                why: list = []
                with mock.patch.object(os, "rename", refuse(2)):
                    self.assertEqual(remove(X, wait=30.0, why=why), "removed")
                self.assertEqual((len(refusals), why), (2, []))
        self.moved(None, X)
        self.leave()
        refusals.clear()
        said: list[str] = []
        with mock.patch.object(os, "rename", refuse(2)):
            self.assertEqual(versions.remove_code(X, told=said.append), "refused", "a sweep's: once")
        self.assertEqual(len(refusals), 1)
        self.assertIn(f"text-to-cad {X}'s code stays until the next sweep: The process cannot access the file", said)

    def test_a_refusal_says_its_cause_and_this_command_running_from_it_needs_no_wait(self) -> None:
        self.moved(None, X)
        self.leave()
        real, tries = os.rename, []

        def refuse(source, target):
            if Path(source) == places.code_dir(X):
                tries.append(source)
                raise PermissionError(13, "The process cannot access the file")
            return real(source, target)

        why: list = []
        with mock.patch.object(os, "rename", refuse), mock.patch.object(versions, "runs_from", return_value=True):
            self.assertEqual(versions.remove_code(X, wait=30.0, why=why), "refused")
        self.assertEqual(len(tries), 1, "no wait changes it: this command runs from it")
        self.assertEqual(why, [versions.Refusal("the system refused to remove it (The process cannot access the file): "
                                                "this command runs from it", True)])
        why.clear()
        with mock.patch.object(versions, "_take", side_effect=PermissionError(13, "Access is denied")):
            self.assertEqual(versions.remove_code(X, wait=30.0, why=why), "refused")
        self.assertEqual(why, [versions.Refusal("its server's lock could not be taken (Access is denied)")])
        # Where this process runs from, by its own interpreter and environment, resolved.
        import sys

        self.assertTrue(versions.runs_from(Path(sys.prefix)))
        self.assertFalse(versions.runs_from(places.version_dir(X)))


class PointersThatCannotBeRead(Device):
    """D2, D3, D9, D11: anything there that cannot be read or understood is never read as nothing."""

    def corrupt(self, channel: str | None) -> Path:
        path = self.state / ("default" if channel is None else f"channels/{channel}")
        path.write_bytes(b"")
        return path

    def test_an_old_chat_s_pin_never_moves_a_channel_back_over_a_pointer_that_names_no_version(self) -> None:
        self.moved("store", X)
        self.moved("store", Y)
        self.present(X)
        self.corrupt("store")
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}):
            places._versioned.cache_clear()
            with self.assertRaises(Failure) as refused:
                pins.apply(pins.parse(f"+{X}@store"))
        self.assertEqual(refused.exception.reason, "failed")
        self.assertIn("names no version: run `cad doctor`", str(refused.exception))
        self.assertEqual((self.state / "channels" / "store").read_bytes(), b"", "a pin never writes it")
        self.assertEqual(versions.move("store", X).kind, "failed", "nor does a move that is not a repair")
        self.assertEqual(versions.move("store", X, mend=True).kind, "stale",
                         "a repair never names a version older than the newest a channel has been on")
        moved = versions.move("store", Z, mend=True)
        self.assertEqual((moved.kind, pointers.read("store")), ("moved", Z))

    def test_cad_doctor_writes_one_that_names_no_version_again_naming_the_newest_a_channel_was_on(self) -> None:
        self.moved("store", X)
        self.moved(None, Y)
        self.present(Z)  # installed, never a channel's: never named in its place
        self.corrupt(None)
        said = versions.mend()
        self.assertEqual(pointers.read(None), Y, said)
        self.assertIn(f"it names text-to-cad {Y} now", said[0])
        self.assertEqual(installation_current(self.state), Y, "the mirror with it")

    def test_a_command_with_no_pin_writes_nothing_on_a_default_pointer_it_cannot_read(self) -> None:
        self.present(X)
        self.corrupt(None)
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}):
            places._versioned.cache_clear()
            with self.assertRaises(Failure) as refused:
                pins.first_use()
        self.assertIn("names no version", str(refused.exception))
        self.assertFalse(places.data_dir(X).exists(), "nothing written before its first start")

    def test_a_channels_entry_this_release_does_not_understand_stops_every_removal(self) -> None:
        self.data(X)
        self.data(Y)
        pointers.write(None, Y, mirrored=False)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")
        (self.state / "channels").mkdir()
        (self.state / "channels" / "Store").write_text(f"{X}\n", encoding="utf-8")  # a later release's name
        (self.state / "channels" / ".store.123.tmp").write_text("", encoding="utf-8")  # a write's own: not one
        with self.assertRaises(pointers.Unreadable):
            pointers.listing()
        self.own = Y
        self.assertFalse(versions.garbage())
        self.assertEqual(versions.sweep(), {})
        self.assertTrue(places.version_dir(X).is_dir())
        surveyed = [found for found in pointers.survey() if isinstance(found, pointers.Unreadable)]
        self.assertEqual([found.path.name for found in surveyed], ["Store"])
        (self.state / "channels" / "Store").unlink()
        self.assertEqual(versions.sweep(), {X: "removed"})

    def test_the_mirror_that_cannot_be_read_stops_every_removal(self) -> None:
        self.data(X)
        self.data(Y)
        pointers.write(None, Y)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")
        current = self.state / "installations" / "current"
        current.unlink()
        current.mkdir()  # there, and it cannot be read
        self.own = Y
        with self.assertRaises(pointers.Unreadable):
            versions._kept()
        self.assertEqual(versions.sweep(), {})
        self.assertFalse(versions.retiring(X, working=False))
        self.assertTrue(places.version_dir(X).is_dir())


def installation_current(state: Path) -> str:
    return (state / "installations" / "current").read_text(encoding="utf-8").strip()


class OnlyTheHeirCarries(Device):
    """D4: a version left is carried and removed by a process of the version its data goes to, in its formats."""

    def test_another_version_s_sweep_leaves_it_for_its_heir(self) -> None:
        self.moved(None, Z)
        self.moved("store", X)
        self.moved("store", Y)  # the move ran as Y: X carried and removed then
        self.assertFalse(places.version_dir(X).exists())
        self.data(X)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")
        record(places.data_dir(X), LATE, 3.0)
        self.own = Z  # the default's server, tending
        self.assertFalse(versions.garbage(spare=Z), "nothing of its own to do")
        with mock.patch.object(imports, "carry", side_effect=AssertionError("carried by another version")):
            self.assertEqual(versions.sweep(spare=Z), {X: "heir"})
        self.assertTrue(places.version_dir(X).is_dir())
        self.own = Y  # its heir's server
        self.assertTrue(versions.garbage(spare=Y))
        self.assertEqual(versions.sweep(spare=Y), {X: "removed"})
        self.assertTrue(has(Y, LATE))

    def test_the_layout_before_is_removed_by_the_default_channel_s_version_alone(self) -> None:
        self.legacy()
        self.moved(None, X)
        self.serving(X)
        self.moved("store", Y)
        self.assertTrue(legacy.removable(), "kept while the default's server had not started")
        self.own = Y
        self.assertFalse(versions.garbage(spare=Y))
        versions.sweep(spare=Y)
        self.assertTrue(legacy.removable(), "another channel's server leaves it")
        self.own = X
        versions.sweep(spare=X)
        self.assertFalse(legacy.removable())


class UsedMeansNamed(Device):
    """D5: a version is a channel's once a pointer named it, not when it imported."""

    def test_a_version_whose_proof_failed_after_its_import_leaks_nothing(self) -> None:
        self.moved(None, X)
        with mock.patch.object(versions, "proof", side_effect=versions.base.Refused("it does not start", "probe")):
            self.assertEqual(versions.move(None, Y).kind, "failed")
        self.assertTrue(imports.imported(Y), "its import ran")
        self.assertFalse(versions.used(Y), "and no pointer ever named it")
        self.assertEqual(versions.fate(Y, versions._kept()), "unused", "no sweep takes it: a target may wait")
        self.assertEqual(versions.remove_unused(Y), "removed", "an updater preparing a newer one does")
        self.moved(None, Y)
        self.assertTrue(versions.used(Y))

    def test_prune_forgetting_a_channel_ahead_of_the_default_removes_its_version_whole_and_says_so(self) -> None:
        self.moved(None, X)
        self.moved("store", Y)  # ahead of the default: X cannot take its data
        record(places.data_dir(Y), LATE, 4.0)
        long_ago = time.time() - (pointers.FORGOTTEN_DAYS + 1) * 86400
        os.utime(self.state / "channels" / "store", (long_ago, long_ago))
        self.own = X
        plan = versions.prune_plan()
        self.assertEqual([pointer.channel for pointer in plan.channels], ["store"])
        self.assertIn("its settings and Recents with it", plan.versions[Y])
        self.assertEqual(versions.prune(plan), {Y: "removed"})
        self.assertFalse(places.version_dir(Y).exists())
        self.assertFalse(has(X, LATE), "nothing carried into an older version")


class ASweepNeverWaits(Device):
    """D7: a process running from a folder (no server there) is looked at once, never waited on."""

    def test_in_use_answered_at_once(self) -> None:
        self.data(X)
        self.data(Y)
        pointers.write(None, Y, mirrored=False)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")
        self.own = Y
        with mock.patch.object(releases, "running", return_value=True) as running, \
                mock.patch.object(versions, "quiet", side_effect=AssertionError("waited")):
            self.assertEqual(versions.sweep(spare=Y), {X: "in use"})
        running.assert_called_once()


class TheLedger(Device):
    """D10: a ledger that cannot be read stops the carry; what the person deleted or removed stays so."""

    def test_a_ledger_that_cannot_be_read_carries_nothing_and_removes_nothing(self) -> None:
        from cad_server.cli import doctor

        self.data(X)
        self.data(Y)
        pointers.write(None, Y, mirrored=False)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")
        record(places.data_dir(X), IDENT, 1.0)
        (places.data_dir(Y) / imports.LEDGER).write_text("{ cut short", encoding="utf-8")
        self.own = Y
        self.assertEqual(versions.sweep(spare=Y), {X: "carry"})
        self.assertFalse(has(Y, IDENT))
        self.assertTrue(places.version_dir(X).is_dir())
        said = [line for line in doctor._versions() if line.startswith(f"version  text-to-cad {X} ")]
        self.assertIn("record of what it took cannot be read", said[0])

    def test_a_record_deleted_before_a_later_import_stays_deleted(self) -> None:
        self.legacy()
        record(self.state, IDENT, 1.0)
        self.moved("store", X)  # X imports the layout's record
        self.assertTrue(has(X, IDENT))
        registry.Registry(places.data_dir(X)).delete(IDENT)  # deleted in X
        self.moved("store", Y)  # Y imports from X, which no longer has it
        self.assertFalse(has(Y, IDENT))
        imports.carry(imports.of_legacy(), Y)  # the layout, which still has it, carried into Y
        self.assertFalse(has(Y, IDENT), "deleted in X before Y imported: it stays deleted")

    def test_a_setting_removed_stays_removed(self) -> None:
        self.data(X, {"language": {"locale": "fr"}, "updates": {"automatic": False}})
        self.moved(None, X)
        self.moved("store", Y)  # Y imports X's settings
        from cad_server.settings import write_section

        write_section("language", None, path=places.data_dir(Y) / "settings.json")  # back to the browser's language
        self.assertTrue(imports.carry(imports.of_version(X), Y).complete)
        self.assertNotIn("language", settings(Y), "a section the person removed is not carried back")


class ReadOnlyDoctor(Device):
    """D6: ``cad doctor --check``'s look at the layout before takes no lock and makes no folder."""

    REAL_SERVERS = True

    def test_the_layout_s_check_makes_and_takes_nothing(self) -> None:
        from cad_server.cli import doctor

        self.legacy()
        self.data(X)
        pointers.write(None, X)  # the mirror names it: the flat engine folder is what is looked at
        with mock.patch.object(versions, "serves", return_value=True), \
                mock.patch.object(places, "lock", side_effect=AssertionError("a lock taken")):
            said = doctor._versions()
        self.assertFalse(self.engines.exists(), "no engine folder made")
        self.assertTrue(any(line.startswith("legacy ") for line in said), said)


class TheProofsDoor(Device):
    """D13: the proof makes a door beside the version's own, never at it."""

    def test_the_proof_never_makes_the_version_s_own_door(self) -> None:
        if places.WINDOWS:
            self.skipTest("a Windows server has a port file, not a door")
        from cad.engine import door
        from cad_server.engine import daemon

        self.data(X)
        made: list[Path] = []
        real = door.Door

        def recorded(path, on_hello):
            made.append(Path(path))
            return real(path, on_hello)

        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}), mock.patch.object(door, "Door", recorded):
            places._versioned.cache_clear()
            self.assertEqual(daemon.proof(), 0)
            own = daemon.door_path()
        self.assertEqual(len(made), 1)
        self.assertNotEqual(made[0], own)
        self.assertEqual(made[0].parent, own.parent)
        self.assertFalse(made[0].exists() or own.exists(), "nothing left behind")


class Handover(unittest.TestCase):
    """E5, E6: the pages' port, said and taken as it truly is."""

    def test_a_handover_answered_with_another_port_says_so_and_is_no_handover(self) -> None:
        said: list[str] = []
        answer = {"ok": True, "url": "http://127.0.0.1:3246", "port": 3246}
        with mock.patch.object(versions, "serves", return_value=False), \
                mock.patch.object(versions, "start_server", return_value=True), \
                mock.patch.object(versions, "ask", return_value=answer):
            self.assertFalse(versions.handover("store", X, Y, 3245, told=said.append))
        self.assertFalse(any("serves pages on port 3245" in line for line in said), said)
        self.assertIn("serves pages on port 3246", said[0])
        self.assertEqual(versions.answered_port({"url": "http://127.0.0.1:4000/x"}), 4000)

    def test_the_bridge_taking_the_flat_door_from_0_11_10_takes_the_port_it_served(self) -> None:
        from cad_server.engine import daemon

        asked: list[dict] = []
        engine = SimpleNamespace(listener=None, token="t", serve=asked.append, stopping=threading.Event(),
                                 draining=False)
        bridge = daemon.Bridge(engine)
        folder = Path(tempfile.mkdtemp(prefix="cad-bridge-"))
        self.addCleanup(shutil.rmtree, folder, True)
        held = SimpleNamespace(close=lambda: None)
        with mock.patch.object(daemon.Bridge, "folder", staticmethod(lambda: folder)), \
                mock.patch.object(daemon, "_legacy_port", return_value=3245), \
                mock.patch.object(daemon, "lock", side_effect=[None, held]), \
                mock.patch("cad.engine.door.Door", return_value=SimpleNamespace(path=folder / "engine.door",
                                                                               close=lambda: None)), \
                mock.patch.object(daemon, "_identity", return_value=(1, 1)), \
                mock.patch.object(daemon, "WINDOWS", False):
            bridge._take()  # 0.11.10's server holds it: the port it serves noted
            self.assertIsNone(bridge.held)
            bridge._take()  # it went before its helper asked: the door, and that port
            deadline = time.monotonic() + 10
            while not asked:
                self.assertLess(time.monotonic(), deadline, "the port was not asked for")
                time.sleep(0.01)
        self.assertIs(bridge.held, held)
        self.assertEqual(asked, [{"op": "http", "port": 3245}])


if __name__ == "__main__":
    import unittest

    unittest.main()
