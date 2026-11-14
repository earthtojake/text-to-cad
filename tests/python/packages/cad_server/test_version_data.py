"""What a version's data becomes as channels move: carried over from what a channel leaves, at the move and again
before the removal (``imports.carry``, A2); nothing written before a version's first start (``pins.first_use``,
``imports._merge``, A4); the layout of 0.11.10 and earlier kept whole while a client of it still runs it, ranked below
every older version and read for its settings alone once removed (``legacy``, A5, A6, A9); and the proof a version's
server starts before a pointer moves to it (``versions.proof``, B7). The device is ``test_versions.Device``'s."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from unittest import mock

from tests.python.packages.cad_server.test_versions import IDENT, TOKEN, Device, X, Y, Z

from cad.engine import places
from cad_server._internal import imports, legacy, pointers, versions
from cad_server.engine import registry


class CarryOver(Device):
    """A2: what a version left, or the layout of 0.11.10 and earlier, writes after the import is carried over --
    additive, by key, never overwriting, never newer into older -- at the move and again before the removal."""

    def record(self, data: Path, ident: str, opened: float, *, cache: Path | None = None) -> None:
        folder = data / "documents" / ident
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "document.json").write_text(json.dumps({"schema": registry.SCHEMA, "id": ident, "kind": "file",
                                                          "opened": opened}), encoding="utf-8")
        if cache is not None:
            (cache / "documents" / ident).mkdir(parents=True, exist_ok=True)
            (cache / "documents" / ident / "document.xbf").write_bytes(f"bytes of {ident}".encode())

    def opened(self, name: str, ident: str) -> float | None:
        found = registry.Registry(places.data_dir(name)).get(ident)
        return None if found is None else found.get("opened")

    def test_i_the_layout_written_after_another_channel_imported_it_reaches_the_default_s_version(self) -> None:
        late = "2b0e0a8e-6d0a-4c6e-9a63-1f2d3c4b5a69"
        self.legacy()
        self.record(self.state, IDENT, 1.0)
        self.moved("store", X)  # a store's copy moved first: X imported the layout
        self.assertEqual(self.opened(X, IDENT), 1.0)
        # 0.11.10 stays the default for hours: a document made, an old one opened again, a setting chosen.
        self.record(self.state, late, 2.0, cache=self.cache)
        self.record(self.state, IDENT, 9.0)
        (self.state / "settings.json").write_text(json.dumps({"telemetry": {"choice": "off"},
                                                              "language": {"locale": "fr"}}), encoding="utf-8")
        self.moved(None, X)  # the default's first move: X has data already, and the layout's later writes come too
        self.assertEqual((self.opened(X, late), self.opened(X, IDENT)), (2.0, 9.0), "the later use wins")
        self.assertEqual((places.cache_dir(X) / "documents" / late / "document.xbf").read_bytes(), f"bytes of {late}".encode())
        settings = json.loads((places.data_dir(X) / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((settings["language"], settings["telemetry"]["choice"]), ({"locale": "fr"}, "off"))
        # And again as the layout goes: what was written between the move and the removal.
        later = "3b0e0a8e-6d0a-4c6e-9a63-1f2d3c4b5a69"
        self.record(self.state, later, 3.0)
        self.serving(X)
        self.own = X  # the default channel's server, tending: the one that removes the layout (D4)
        versions.sweep()
        self.assertFalse((self.state / "documents").exists(), "the layout removed")
        self.assertEqual(self.opened(X, later), 3.0)

    def test_ii_and_iii_a_version_left_carries_what_it_wrote_after_the_import_before_it_goes(self) -> None:
        late = "2b0e0a8e-6d0a-4c6e-9a63-1f2d3c4b5a69"
        self.moved("store", X)
        self.record(places.data_dir(X), IDENT, 1.0)
        held = self.serving(X)  # X's server busy: it stays after the move
        with mock.patch.object(versions, "connected", return_value=True):
            moved = self.moved("store", Y)
        self.assertEqual(moved.removed, {X: "connected"})
        self.assertEqual(self.opened(Y, IDENT), 1.0, "carried at the move")
        self.assertEqual((places.version_dir(X) / versions.SUCCESSOR).read_text(encoding="utf-8").strip(), Y)
        # X finishes its work in flight: a document made, one opened again; Y deletes one of its own meanwhile.
        self.record(places.data_dir(X), late, 5.0)
        self.record(places.data_dir(X), IDENT, 6.0)
        registry.Registry(places.data_dir(Y)).delete(IDENT)
        held.close()
        self.own = Y  # X's heir's server: the one that carries X and removes it (D4)
        self.assertEqual(versions.sweep(), {X: "removed"})
        self.assertEqual(self.opened(Y, late), 5.0, "written after the import, carried before the removal")
        self.assertIsNone(self.opened(Y, IDENT), "deleted in Y stays deleted")

    def test_additive_idempotent_never_overwriting_never_newer_into_older(self) -> None:
        self.data(X, {"language": {"locale": "x"}, "updates": {"automatic": False}})
        self.data(Y, {"language": {"locale": "y"}})
        self.record(places.data_dir(X), IDENT, 1.0)
        self.record(places.data_dir(Y), IDENT, 4.0)
        first = imports.carry(imports.of_version(X), Y)
        self.assertTrue(first.complete, first.failed)
        settings = json.loads((places.data_dir(Y) / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings, {"language": {"locale": "y"}, "updates": {"automatic": False}},
                         "a key the target lacks added, the target's own kept")
        self.assertEqual(self.opened(Y, IDENT), 4.0, "the target's later use kept")
        before = {path: path.read_bytes() for path in places.data_dir(Y).rglob("*") if path.is_file()}
        again = imports.carry(imports.of_version(X), Y)
        self.assertEqual((again.added, again.failed), ([], []))
        self.assertEqual({path: path.read_bytes() for path in places.data_dir(Y).rglob("*") if path.is_file()}, before)
        backwards = imports.carry(imports.of_version(Y), X)
        self.assertFalse(backwards.complete, "newer into older: refused, so nothing is removed for it")

    def test_a_carry_cut_short_removes_nothing_and_the_next_finishes(self) -> None:
        self.data(X)
        self.data(Y)
        pointers.write(None, Y, mirrored=False)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")
        self.record(places.data_dir(X), IDENT, 1.0)
        self.own = Y
        with mock.patch.object(registry.Folder, "create", side_effect=OSError(28, "No space left on device")):
            self.assertEqual(versions.sweep(), {X: "carry"})
        self.assertTrue(places.data_dir(X).is_dir(), "kept: what it holds could not all be carried")
        self.assertEqual(versions.sweep(), {X: "removed"})
        self.assertEqual(self.opened(Y, IDENT), 1.0)

    def test_a_version_whose_successor_is_unknown_or_gone_is_kept_and_doctor_says_why(self) -> None:
        from cad_server.cli import doctor

        self.data(X)
        self.data(Y)
        pointers.write(None, Y, mirrored=False)
        self.assertEqual(versions.sweep(), {X: "successor"})
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Z}\n", encoding="utf-8")  # gone
        self.assertEqual(versions.sweep(), {X: "successor"})
        self.assertTrue(places.data_dir(X).is_dir())
        said = [line for line in doctor._versions() if line.startswith(f"version  text-to-cad {X} ")]
        self.assertIn(f"its data is kept: text-to-cad {Z}, where its data would go, is gone", said[0])
        self.present(Z)
        self.assertIn("installed and never a channel's: cad doctor --prune removes it",
                      [line for line in doctor._versions() if line.startswith(f"version  text-to-cad {Z} ")][0])

    def test_a_removed_successor_hands_on_to_its_own(self) -> None:
        self.data(X)
        self.data(Y)
        self.data(Z)
        pointers.write(None, Z, mirrored=False)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")
        (places.version_dir(Y) / versions.SUCCESSOR).write_text(f"{Z}\n", encoding="utf-8")
        held = self.serving(X)
        self.own = Z  # Y's heir: X's is Y, so X is left for Y's process (D4) until Y goes and hands it on
        self.assertEqual(versions.sweep(), {X: "heir", Y: "removed"})
        self.assertEqual((places.version_dir(X) / versions.SUCCESSOR).read_text(encoding="utf-8").strip(), Z)
        self.assertEqual(versions.sweep(), {X: "connected"})
        held.close()
        self.assertEqual(versions.sweep(), {X: "removed"})


class NothingWrittenBeforeTheFirstStart(Device):
    """A4."""

    def test_an_unpinned_command_of_a_never_started_version_makes_the_default_s_first_use_first(self) -> None:
        from cad_server._internal import pins

        self.data("0.11.50", {"language": {"locale": "fr"}, "telemetry": {"choice": "off", "decidedAt": 5.0}})
        pointers.write("store", "0.11.50", mirrored=False)
        self.present(X)
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}):
            places._versioned.cache_clear()
            pins.first_use()
        self.assertEqual(pointers.read(None), X)
        self.assertEqual(imports.marker(X)["imported"], {"kind": "version", "version": "0.11.50"})
        settings = json.loads((places.data_dir(X) / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((settings["language"], settings["telemetry"]["choice"]), ({"locale": "fr"}, "off"),
                         "the no came with the import, not lost to a notice written first")
        self.assertEqual(pointers.default(), pointers.Default(X, "pointer"))

    def test_the_command_line_makes_it_before_the_notice_and_never_for_setup(self) -> None:
        from cad_server import cli
        from cad_server._internal import pins

        self.present(X)
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}), \
                mock.patch.object(pins, "first_use") as first, mock.patch.object(cli, "_run", return_value=0), \
                mock.patch.object(cli, "_tell", side_effect=lambda: first.assert_called_once()):
            places._versioned.cache_clear()
            self.assertEqual(cli.main(["stop"]), 0)
            first.assert_called_once()
            first.reset_mock()
            cli.main(["setup", "--dry-run"])
            cli.main(["stop", "--help"])
            first.assert_not_called()

    def test_the_newest_version_a_command_with_no_pin_runs_is_one_that_started(self) -> None:
        self.data(X)
        self.present(Y)
        self.assertEqual(pointers.default(), pointers.Default(X, "newest"))
        shutil.rmtree(places.data_dir(X))
        self.assertEqual(pointers.default(), pointers.Default(Y, "newest"), "none started: the newest present")

    def test_what_a_version_wrote_before_its_marker_loses_to_the_import(self) -> None:
        self.data(X, {"telemetry": {"choice": "off", "decidedAt": 5.0}, "language": {"locale": "fr"}})
        token = places.data_dir(X) / "engines" / "token"
        token.parent.mkdir()
        token.write_text(TOKEN + "\n", encoding="ascii")
        os.chmod(token, 0o600)
        self.present(Y)
        mine = places.data_dir(Y)
        (mine / "engines").mkdir(parents=True)
        (mine / "settings.json").write_text('{"telemetry": {"notifiedAt": 1.0}}', encoding="utf-8")
        (mine / "engines" / "token").write_text("f" * 43 + "\n", encoding="ascii")
        ident = "4b0e0a8e-6d0a-4c6e-9a63-1f2d3c4b5a69"
        (mine / "documents" / ident).mkdir(parents=True)
        (mine / "documents" / ident / "document.json").write_text("{}", encoding="utf-8")
        imports.ensure(Y, leaving=X)
        settings = json.loads((mine / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((settings["telemetry"]["choice"], settings["language"]), ("off", {"locale": "fr"}))
        self.assertEqual((mine / "engines" / "token").read_text(encoding="ascii").strip(), TOKEN)
        self.assertTrue((mine / "documents" / ident / "document.json").is_file(), "a record written first stays")


class TheLayoutBefore(Device):
    """A5, A6, A9."""

    def test_current_naming_a_flat_release_keeps_the_whole_layout(self) -> None:
        self.legacy()
        self.present(X)
        pointers.write(None, X, mirrored=False)  # the mirror could not be written: current names 0.11.10
        imports.ensure(X)
        self.serving(X)
        self.assertIn("installations/current names 0.11.10", legacy.unsafe(X))
        self.assertFalse(legacy.remove(X))
        self.assertTrue((self.state / "documents").is_dir() and (self.cache / "base").is_dir())

    def test_the_layout_ranks_below_older_versions_and_once_removed_gives_its_settings_alone(self) -> None:
        self.legacy()
        self.data(X)
        self.present(Y)
        self.assertEqual(imports.source(Y).version, X, "the highest older version, not the layout")
        self.assertEqual(imports.source(Y, legacy_left=True).kind, "legacy", "unless the channel leaves the layout")
        pointers.write(None, X)
        self.serving(X)
        (self.cache / "interference").mkdir(exist_ok=True)
        self.assertTrue(legacy.remove(X))
        self.assertFalse(self.cache.exists(), "the interference cache too (A9): the cache folder emptied and gone")
        self.assertFalse(legacy.present())
        shutil.rmtree(places.version_dir(X))
        found = imports.source(Y)
        self.assertEqual((found.kind, found.settings_only), ("legacy", True))
        imports.ensure(Y)
        self.assertEqual(sorted(os.listdir(places.data_dir(Y))), ["carried.json", "format.json", "settings.json"],
                         "its kept settings alone (and what it took of them): no token, no batches, nothing sent again")


class ReadOnly(Device):
    """Whether a version's server runs is asked, never made or taken (``versions.serves``): ``cad doctor --check`` and
    every sweep's look write nothing, and never hold a lock a server starting that instant needs."""

    REAL_SERVERS = True

    def test_asking_whether_a_server_runs_makes_and_takes_nothing(self) -> None:
        from cad_server.cli import doctor

        self.data(X)
        self.data(Y)
        pointers.write(None, Y, mirrored=False)
        (self.state / "channels").mkdir()
        (self.state / "channels" / "store").write_bytes(b"")
        self.assertFalse(versions.serves(X))
        said = doctor._versions()
        self.assertFalse(self.engines.exists(), "no engine folder made")
        self.assertTrue(any(line.startswith("pointer  ") and "names no version" in line for line in said), said)
        folder = places.engine_dir(X)
        folder.mkdir(parents=True)
        (folder / "engine.lock").write_text("", encoding="utf-8")  # a lock file and no door: no server answers
        with mock.patch.object(places, "lock", side_effect=AssertionError("no lock taken")):
            self.assertFalse(versions.serves(X))


class TheProof(Device):
    """B7: before a pointer moves, the version's server's own start sequence runs, and leaves nothing running."""

    def test_a_version_whose_server_cannot_start_moves_nothing(self) -> None:
        self.moved("store", X)
        blocked = places.engine_dir(Y)
        blocked.parent.mkdir(parents=True, exist_ok=True)
        blocked.write_text("not a folder", encoding="utf-8")
        moved = versions.move("store", Y)
        self.assertEqual(moved.kind, "failed")
        self.assertIn(f"text-to-cad {Y} does not start", moved.error)
        self.assertEqual(pointers.read("store"), X)
        blocked.unlink()
        self.moved("store", Y)
        self.assertEqual(pointers.read("store"), Y)
        self.assertFalse((places.engine_dir(Y) / "engine.lock").exists(), "the proof let go of everything")
        self.assertFalse((places.engine_dir(Y) / "engine.door").exists())


if __name__ == "__main__":
    import unittest

    unittest.main()
