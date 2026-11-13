"""Installed versions, pointers, the first-start import and the moves between them
(``cad_server._internal.versions``, ``pointers``, ``imports``, ``legacy``), and ``cad setup --add``.

A fake device in a temporary folder (``CAD_STATE_DIR``, ``CAD_ENGINE_DIR``, ``CAD_CACHE_DIR``). uv is stood in for
(``Uv``): each step recorded; ``venv`` makes a real virtual environment of this Python with no pip, and installing
the server writes a ``.pth`` naming this checkout's sources and a ``cad`` beside its Python, so the version's own
Python really runs the proof (``versions._probe``); the kernel's install writes nothing. The folder of wheels uv
reads beside its index is the suites' seam (``CAD_UPDATE_FIND_LINKS``), named and never served: nothing reaches an
index.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import repo_path

from cad.engine import places
from cad_server._internal import base, imports, installations, legacy, pointers, releases, versions
from cad_server.engine import registry

OLD, X, Y, Z = "0.11.10", "0.12.0", "0.12.1", "0.12.2"
IDENT = "0b0e0a8e-6d0a-4c6e-9a63-1f2d3c4b5a69"
SOURCES = (str(repo_path("packages/cad/src")), str(repo_path("packages/cad-server/src")))
TOKEN = "t" * 43


def site_packages(env: Path) -> Path:
    found = sorted(env.glob("lib/python*/site-packages")) or [env / "Lib" / "site-packages"]
    return found[0]


class Uv:
    """uv as these tests see it (see the module). ``fail``: given a step, ``(code, stderr)`` to answer it with,
    or None; ``hold``: called before a server environment is installed."""

    def __init__(self) -> None:
        self.steps: list[list[str]] = []
        self.fail = None
        self.hold = None
        self.lock = threading.Lock()

    def __call__(self, step: list[str], folder: Path, settings=None) -> subprocess.CompletedProcess:
        with self.lock:
            self.steps.append(list(step))
        answer = self.fail(step) if self.fail else None
        if answer is not None:
            return subprocess.CompletedProcess(step, answer[0], "", answer[1])
        if step[1] == "venv":
            subprocess.run([sys.executable, "-m", "venv", "--without-pip", step[-1]], check=True)
        elif any("cad-server" in word for word in step):
            if self.hold is not None:
                self.hold()
            env = Path(step[step.index("--python") + 1]).parent.parent
            (site_packages(env) / "_cad_sources.pth").write_text("\n".join(SOURCES) + "\n", encoding="utf-8")
            releases.console(env).write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(step, 0, "", "")

    def made(self) -> list[str]:
        """Each environment made, by its folder's name: ``server``, or the kernel's key."""
        return [Path(step[-1]).name for step in self.steps if step[1] == "venv"]


class Device(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="cad-versions-")))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state, self.cache, self.engines = self.root / "state", self.root / "cache", self.root / "engines"
        self.wheels = self.root / "wheels"
        environment = {"CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.engines),
                       "CAD_CACHE_DIR": str(self.cache), "CAD_INSTALLATION_VERSION": "",
                       "CAD_UPDATE_FIND_LINKS": str(self.wheels)}
        self.uv = Uv()
        for patch in (mock.patch.dict(os.environ, environment), mock.patch.object(places, "HOME", None),
                      mock.patch.object(registry, "FACTORY", None), mock.patch.object(base, "_uv", self.uv),
                      mock.patch.object(base, "find_uv", return_value="uv")):
            patch.start()
            self.addCleanup(patch.stop)
        places._versioned.cache_clear()
        places._registered.cache_clear()
        self.addCleanup(places._versioned.cache_clear)
        self.addCleanup(places._registered.cache_clear)
        self.said: list[str] = []

    def present(self, name: str) -> versions.Present:
        found = versions.make_present(name, told=self.said.append)
        self.assertTrue(found.ok, found.error)
        return found

    def data(self, name: str, settings: dict | None = None) -> Path:
        """Version ``name`` present, its data imported with ``settings``."""
        self.present(name)
        data = places.data_dir(name)
        data.mkdir(parents=True, exist_ok=True)
        (data / "settings.json").write_text(json.dumps(settings or {"language": {"locale": name}}), encoding="utf-8")
        (data / imports.MARKER).write_text(json.dumps({"schema": imports.SCHEMA, "version": name}), encoding="utf-8")
        return data

    def serving(self, name: str):
        """Version ``name``'s server lock held, as its running server holds it: let go at the test's end."""
        held = places.lock(places.engine_dir(name) / "engine.lock")
        self.assertIsNotNone(held)
        self.addCleanup(held.close)
        return held

    def legacy(self) -> None:
        """A device of 0.11.10, installed by the install command: its shared data, its flat release, its
        caches."""
        state = self.state
        (state / "documents" / IDENT).mkdir(parents=True)
        (state / "documents" / IDENT / "document.json").write_text('{"id": "legacy"}', encoding="utf-8")
        (state / "recents" / "thumbnails").mkdir(parents=True)
        (state / "recents" / "thumbnails" / ("a" * 32 + ".png")).write_bytes(b"png")
        (state / "settings.json").write_text('{"telemetry": {"choice": "off"}}', encoding="utf-8")
        (state / "engines").mkdir()
        token = state / "engines" / "token"
        token.write_text(TOKEN + "\n", encoding="ascii")
        os.chmod(token, 0o600)
        (state / "engines" / "engine.json").write_text('{"port": 3300, "schema": 3, "extra": 1}', encoding="utf-8")
        (state / "telemetry-spool.jsonl").write_text("{}\n", encoding="utf-8")
        (state / "versions.json").write_text("{}", encoding="utf-8")
        (state / "install-receipt.json").write_text('{"schema": 1}', encoding="utf-8")
        (state / "plugin").mkdir()
        flat = state / "releases" / OLD
        (flat / "bin").mkdir(parents=True)
        for script in ("python", "cad"):
            (flat / "bin" / script).write_text("", encoding="utf-8")
        installations.register(OLD, (str(flat / "bin" / "cad"), str(flat / "bin" / "python"), str(flat)))
        installations.point(OLD)
        for name in legacy.CACHES:
            (self.cache / name).mkdir(parents=True)
        (self.cache / "documents" / IDENT).mkdir()
        (self.cache / "documents" / IDENT / "document.xbf").write_bytes(b"the legacy document's bytes")
        batch = {"answer": [1.0, 1.0], "batch": {"schema": 6, "batch": "b1", "version": OLD, "events": [{"id": "e1"}]}}
        (state / "telemetry-batches.jsonl").write_text(json.dumps(batch) + "\n", encoding="utf-8")


class MakingPresent(Device):
    def test_made_once_then_found_and_nothing_else_changed(self) -> None:
        found = self.present(X)
        self.assertTrue(found.made)
        code = places.code_dir(X)
        record = places.version_record(X)
        self.assertEqual((record["prefix"], record["version"]), (str(code / "server"), X))
        kernel = Path(record["kernel"])
        self.assertEqual(kernel.parent, code / "base", "the kernel made now, in the version's code")
        self.assertEqual(places.home(str(kernel))["prefix"], str(code / "server"), "the kernel names its server")
        self.assertEqual(self.uv.made(), ["server", kernel.name])
        installs = [step for step in self.uv.steps if step[1] == "pip"]
        self.assertTrue(all("--find-links" in step and str(self.wheels) in step and "--offline" in step
                            for step in installs), "uv's cache first, the suites' wheels beside the index")
        self.assertIn(f"cad-server=={X}", installs[0])
        self.assertTrue((code / "CACHEDIR.TAG").is_file())
        if os.name != "nt":
            self.assertFalse(os.stat(code).st_mode & 0o022, "no one else writes a version's code")
        again = versions.make_present(X)
        self.assertEqual((again.ok, again.made, len(self.uv.steps)), (True, False, 4), "nothing made twice")
        self.assertEqual(sorted(os.listdir(self.state)), ["install.lock", "versions"])
        self.assertEqual(os.listdir(self.state / "versions"), [X])
        self.assertFalse(os.path.exists(places.data_dir(X)), "making a version present imports nothing")

    def test_interrupted_then_finished_from_where_it_stopped(self) -> None:
        def cut(step):
            if step[1] == "pip" and not any("cad-server" in word for word in step):
                raise KeyboardInterrupt  # the kernel's install, cut short
        self.uv.fail = cut
        with self.assertRaises(KeyboardInterrupt):
            versions.make_present(X, told=self.said.append)
        self.assertIsNone(places.version_record(X), "no marker: not present")
        self.uv.fail, self.uv.steps = None, []
        found = self.present(X)
        self.assertEqual(self.uv.made(), [Path(found.record["kernel"]).name], "the server is not made again")

    def test_two_callers_at_once_make_it_once(self) -> None:
        second_waits = threading.Event()
        self.uv.hold = lambda: second_waits.wait(30)
        results: dict[str, versions.Present] = {}

        def first() -> None:
            results["first"] = versions.make_present(X, told=self.said.append)

        def second() -> None:
            results["second"] = versions.make_present(
                X, told=lambda line: second_waits.set() if line.startswith("waiting") else None)

        one = threading.Thread(target=first)
        one.start()
        while not self.uv.steps:  # the first is making it
            one.join(0.01)
        two = threading.Thread(target=second)
        two.start()
        one.join(60)
        two.join(60)
        self.assertTrue(second_waits.is_set(), "the second waited on the install lock")
        self.assertEqual((results["first"].made, results["second"].made, results["second"].ok), (True, False, True))
        self.assertEqual(len(self.uv.made()), 2, "each environment made once")

    def test_where_it_cannot_run_it_says_so_as_a_result(self) -> None:
        with mock.patch.object(base, "find_uv", side_effect=base.Refused("no uv here", "uv")):
            self.assertEqual(versions.make_present(X, told=self.said.append).cannot, "uv")
        self.uv.fail = lambda step: (2, "error: Failed to fetch: dns error") if step[1] == "pip" else None
        self.assertEqual(versions.make_present(X, told=self.said.append).cannot, "network")
        with mock.patch.object(Path, "mkdir", side_effect=PermissionError(1, "Operation not permitted")):
            denied = versions.make_present(Y, told=self.said.append)
        self.assertEqual((denied.ok, denied.cannot), (False, "denied"))
        self.uv.fail = lambda step: (1, "error: no solution") if step[1] == "pip" else None
        failed = versions.make_present(Z, told=self.said.append)
        self.assertEqual((failed.cannot, failed.ok), (None, False), "a failure, not this shell's")

        out, err = io.StringIO(), io.StringIO()
        self.uv.fail = lambda step: (2, "error: dns error") if step[1] == "pip" else None
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}):
            code = versions.add(quiet=True, out=out, err=err)
        lines = err.getvalue().splitlines()
        self.assertEqual((code, out.getvalue(), len(lines)), (3, "", 2))
        self.assertIn(f"text-to-cad {X} is not installed, and could not be installed from this shell", lines[0])
        self.assertTrue(lines[1].endswith(versions.add_command(X)))


class Pointers(Device):
    def test_read_written_whole_and_listed(self) -> None:
        self.assertIsNone(pointers.read(None))
        pointers.write("my-store.2", X)
        pointers.write("a", Y)
        self.assertEqual((self.state / "channels" / "a").read_text(encoding="utf-8"), f"{Y}\n")
        with mock.patch.object(registry, "replace_atomic", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                pointers.write("a", Z)
        self.assertEqual(pointers.read("a"), Y, "a write that fails leaves the one before")
        self.assertEqual(sorted(os.listdir(self.state / "channels")), ["a", "my-store.2"], "no half-written file")
        self.assertEqual([(found.channel, found.version) for found in pointers.listing()],
                         [("a", Y), ("my-store.2", X)])
        self.assertEqual(pointers.named(), {X, Y})

    def test_default_is_the_default_channel_never_a_named_one(self) -> None:
        self.assertIsNone(pointers.channel_name("default"))
        self.assertEqual(versions.move("default", X).channel, None)
        self.assertEqual(pointers.read(None), X)
        self.assertFalse((self.state / "channels").exists(), "no channels/default")
        self.assertEqual(versions.move(None, X).kind, "same")
        with self.assertRaises(ValueError):
            pointers.forget("default")

    def test_a_development_build_is_newer_than_its_release(self) -> None:
        build = "0.12.0-dev.20261113120000"
        self.assertTrue(versions.older("0.12.0", build))
        self.assertTrue(versions.older(build, "0.12.1"))
        self.assertTrue(versions.older(build, "0.12.0-dev.20261114120000"))
        self.assertFalse(versions.older(build, "0.12.0"))

    def test_a_channel_is_any_name_of_safe_characters(self) -> None:
        for name in ("a", "0", "store-7", "x.y_z", "a" * 32):
            self.assertEqual(pointers.channel_name(name), name)
        for name in ("", "A", "-a", ".a", "a/b", "a b", "a" * 33, "..", None):
            with self.assertRaises(ValueError):
                pointers.channel_name(name)

    def test_the_default_channels_version(self) -> None:
        self.assertEqual(pointers.default(), pointers.Default(None, None))
        self.present(X)
        self.present(Y)
        self.assertEqual(pointers.default(), pointers.Default(Y, "newest"), "neither: the newest present")
        self.legacy()
        self.assertEqual(pointers.default(), pointers.Default(OLD, "current", True), "the receipt: current")
        (self.state / "install-receipt.json").unlink()
        self.assertEqual(pointers.default().source, "newest", "current alone, with no receipt, is not the default's")
        pointers.write(None, X)
        self.assertEqual(pointers.default(), pointers.Default(X, "pointer"))

    def test_the_default_pointer_writes_the_mirror_for_releases_before_0_12(self) -> None:
        self.legacy()
        self.present(X)
        pointers.write(None, X)
        self.assertEqual((self.state / "default").read_text(encoding="utf-8"), f"{X}\n")
        self.assertEqual(installations.current_version(), X)
        self.assertEqual(places.current()["prefix"], str(places.code_dir(X) / "server"))
        self.assertEqual(pointers.default(), pointers.Default(X, "pointer"))


class Import(Device):
    def test_from_the_version_being_left_and_never_its_caches_or_telemetry(self) -> None:
        data = self.data(X, {"language": {"locale": "fr"}})
        (data / "documents" / IDENT).mkdir(parents=True)
        (data / "documents" / IDENT / "document.json").write_text("{}", encoding="utf-8")
        (data / "cache" / "hulls").mkdir(parents=True)
        (data / "cache" / "hulls" / "h.npz").write_bytes(b"hull")
        (data / "telemetry-spool.jsonl").write_text("{}\n", encoding="utf-8")
        self.data(Y, {"language": {"locale": "de"}})
        self.present(Z)
        done = imports.ensure(Z, leaving=X)
        self.assertEqual((done.source.kind, done.source.version), ("version", X), "what the channel leaves")
        new = places.data_dir(Z)
        self.assertEqual(json.loads((new / "settings.json").read_text(encoding="utf-8")), {"language": {"locale": "fr"}})
        self.assertTrue((new / "documents" / IDENT / "document.json").is_file())
        self.assertFalse((new / "cache").exists() or (new / "telemetry-spool.jsonl").exists())
        self.assertEqual(imports.marker(Z)["imported"], {"kind": "version", "version": X})
        self.assertTrue((data / "telemetry-spool.jsonl").exists(), "the source is not changed")

    def test_a_first_use_takes_the_highest_older_version_never_a_newer(self) -> None:
        self.data(X, {"language": {"locale": "x"}})
        self.data(Y, {"language": {"locale": "y"}})
        self.data(Z, {"language": {"locale": "z"}})
        self.present("0.12.5")
        self.assertEqual(imports.ensure("0.12.5").source.version, Z)
        self.present("0.11.99")
        done = imports.ensure("0.11.99")
        self.assertEqual((done.done, done.source), (True, None), "only newer versions: fresh, nothing imported")
        self.assertEqual(os.listdir(places.data_dir("0.11.99")), [imports.MARKER])

    def test_from_the_layout_before_0_12_converted_and_unreadable_items_skipped(self) -> None:
        self.legacy()
        self.present(X)
        unreadable = self.state / "documents" / IDENT / "document.json"
        real = Path.read_bytes

        def read_bytes(path):
            if path == unreadable:
                raise PermissionError(13, "Permission denied")
            return real(path)

        with mock.patch.object(Path, "read_bytes", read_bytes):
            done = imports.ensure(X)
        self.assertEqual(done.source.kind, "legacy")
        self.assertEqual(len(done.said), 1)
        self.assertIn("was not imported: Permission denied", done.said[0])
        new = places.data_dir(X)
        self.assertEqual((new / "engines" / "token").read_text(encoding="ascii").strip(), TOKEN)
        self.assertEqual(json.loads((new / "engines" / "engine.json").read_text(encoding="utf-8")), {"port": 3300, "schema": 3},
                         "the port record in this release's schema, the port alone")
        if os.name != "nt":
            self.assertEqual(os.stat(new / "engines" / "token").st_mode & 0o777, 0o600)
        self.assertTrue((new / "recents" / "thumbnails" / ("a" * 32 + ".png")).is_file())
        self.assertFalse((new / "documents").exists(), "the unreadable record skipped, the import done")
        self.assertFalse((new / "versions.json").exists() or (new / "telemetry-spool.jsonl").exists())
        self.assertTrue(imports.imported(X))

    def test_recents_opens_after_an_update_and_kept_telemetry_is_sent_by_the_new_version(self) -> None:
        from cad.engine.atomic_replace import put

        self.legacy()
        self.present(X)
        imports.ensure(X)
        old = self.cache / "documents" / IDENT / "document.xbf"
        new = places.cache_dir(X) / "documents" / IDENT / "document.xbf"
        self.assertEqual(new.read_bytes(), b"the legacy document's bytes", "the record's bytes came with it")
        if os.name != "nt":
            self.assertEqual(os.stat(new).st_ino, os.stat(old).st_ino, "one volume: a hard link, no copy")
        batches = (places.data_dir(X) / "telemetry-batches.jsonl").read_text(encoding="utf-8")
        self.assertIn('"version": "0.11.10"', batches, "each batch whole, its own release in it")
        self.assertFalse((places.data_dir(X) / "telemetry-spool.jsonl").exists(), "bare counts name no release")
        # Every writer of the document cache writes a new file and renames it over: the old version's stays.
        registry.Registry(places.data_dir(X), cache=places.cache_dir(X)).cache.write(
            f"documents/{IDENT}/document.xbf", b"the new version's save")
        self.assertEqual(old.read_bytes(), b"the legacy document's bytes")
        put(new, lambda staged: staged.write_bytes(b"a document saved again"), compare=False)
        self.assertEqual((new.read_bytes(), old.read_bytes()),
                         (b"a document saved again", b"the legacy document's bytes"))

    def test_a_crash_mid_import_is_done_again_at_the_next_start(self) -> None:
        self.legacy()
        self.present(X)
        real, calls = imports._file, []

        def crash(*args):
            calls.append(args)
            if len(calls) == 2:
                raise RuntimeError("killed")
            return real(*args)

        with mock.patch.object(imports, "_file", crash), self.assertRaises(RuntimeError):
            imports.ensure(X)
        self.assertFalse(imports.imported(X))
        self.assertTrue(any(name.startswith(imports.STAGING) for name in os.listdir(places.version_dir(X))))
        self.assertTrue(imports.ensure(X).done)
        self.assertFalse(any(name.startswith(imports.STAGING) for name in os.listdir(places.version_dir(X))))
        self.assertTrue((places.data_dir(X) / "documents" / IDENT / "document.json").is_file())

    def test_a_version_engine_imports_before_it_serves(self) -> None:
        from cad_server.engine import daemon

        self.data(X)
        self.present(Y)
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": Y}):
            places._versioned.cache_clear()
            daemon._first_start()
        self.assertEqual(imports.marker(Y)["imported"], {"kind": "version", "version": X})


class Moving(Device):
    def test_equal_older_first_use_and_newer(self) -> None:
        first = versions.move("store", X)
        self.assertEqual((first.kind, first.old, pointers.read("store")), ("moved", None, X))
        self.assertEqual(versions.move("store", X).kind, "same")
        newer = versions.move("store", Y)
        self.assertEqual((newer.kind, newer.old, pointers.read("store")), ("moved", X, Y))
        self.assertEqual(newer.removed, {X: "removed"}, "the version left, named by none, removed")
        self.assertFalse(places.version_dir(X).exists())
        self.assertEqual(imports.marker(Y)["imported"]["version"], X, "imported from the version left")
        stale = versions.move("store", X)
        self.assertEqual((stale.kind, stale.old, pointers.read("store")), ("stale", Y, Y))
        self.assertFalse(places.version_dir(X).exists(), "a stale move makes nothing present")

    def test_a_failure_before_the_pointer_changes_nothing(self) -> None:
        self.assertEqual(versions.move("store", X).kind, "moved")
        before = sorted(str(path.relative_to(self.state)) for path in self.state.rglob("*")
                        if Path(places.version_dir(Y)) not in path.parents and path != places.version_dir(Y))

        def unchanged(kind: str | None, moved: versions.Moved | None = None) -> None:
            if moved is not None:
                self.assertEqual(moved.kind, kind)
            self.assertEqual(pointers.read("store"), X)
            after = sorted(str(path.relative_to(self.state)) for path in self.state.rglob("*")
                           if Path(places.version_dir(Y)) not in path.parents and path != places.version_dir(Y))
            self.assertEqual(after, before, "only the new version's own folder may have changed")

        self.uv.fail = lambda step: (1, "error: no solution") if step[1] == "pip" else None
        unchanged("failed", versions.move("store", Y))  # making it present
        self.uv.fail = lambda step: (2, "error: dns error") if step[1] == "pip" else None
        unchanged("cannot", versions.move("store", Y))
        self.uv.fail = None
        with mock.patch.object(imports, "_copy", side_effect=RuntimeError("a bug")), self.assertRaises(RuntimeError):
            versions.move("store", Y)  # its first start's import
        unchanged(None)
        with mock.patch.object(versions, "proof", side_effect=base.Refused("it does not run", "probe")):
            unchanged("failed", versions.move("store", Y))  # its first start's proof
        with mock.patch.object(pointers, "write", side_effect=OSError(30, "Read-only file system")):
            unchanged("failed", versions.move("store", Y))  # the pointer's write
        self.assertEqual(versions.move("store", Y).kind, "moved", "and with nothing failing, it moves")

    def test_after_the_pointer_a_connected_version_stays_for_the_next_sweep(self) -> None:
        versions.move("store", X)
        held = self.serving(X)
        moved = versions.move("store", Y)
        self.assertEqual((moved.kind, moved.removed), ("moved", {X: "connected"}))
        self.assertTrue(places.version_dir(X).exists())
        held.close()
        self.assertEqual(versions.sweep(), {X: "removed"})


class Removal(Device):
    def test_unnamed_removed_named_connected_in_use_and_refused_kept(self) -> None:
        for name in (X, Y, Z):
            self.present(name)
        pointers.write("store", Y, mirrored=False)
        pointers.write(None, Y, mirrored=False)
        self.assertEqual(versions.remove(Y), "named")
        held = self.serving(Z)
        self.assertEqual(versions.remove(Z), "connected", "a running server that cannot say counts as connected")
        with mock.patch.object(releases, "running", return_value=True):
            self.assertEqual(versions.remove(X), "in use")
        real = os.rename

        def refuse(source, target):
            if Path(source) == places.version_dir(X):
                raise PermissionError(13, "in use")
            return real(source, target)

        with mock.patch.object(os, "rename", refuse):
            self.assertEqual(versions.remove(X), "refused")
        self.assertTrue(places.version_dir(X).is_dir())
        self.assertEqual(versions.remove(X), "removed")
        self.assertFalse(places.version_dir(X).exists() or places.engine_dir(X).exists())
        # The server's answer: nothing connected, and it stops when asked.
        with mock.patch.object(versions, "connected", return_value=False), \
                mock.patch.object(versions, "stop_server", side_effect=lambda _name: held.close() or True):
            self.assertEqual(versions.sweep(), {Z: "removed"})
        self.assertEqual(versions.present(), [Y])


class BeforeTwelve(Device):
    def move_default(self) -> versions.Moved:
        moved = versions.move(None, X)
        self.assertEqual(moved.kind, "moved", moved.error)
        return moved

    def test_the_first_default_move_imports_and_removes_it_once_safe_keeping_what_old_clients_read(self) -> None:
        self.legacy()
        self.present(Y)  # a newer version another channel uses: the default's first move still imports the layout
        (places.data_dir(Y)).mkdir(parents=True)
        (places.data_dir(Y) / imports.MARKER).write_text(json.dumps({"schema": imports.SCHEMA}), encoding="utf-8")
        pointers.write("store", Y, mirrored=False)
        moved = versions.move(None, X)
        self.assertEqual((moved.kind, moved.old, moved.imported.source.kind), ("moved", OLD, "legacy"))
        self.assertTrue((self.state / "releases" / OLD).exists(), "kept until the new version serves")
        self.assertIn("has not started yet", " ".join(moved.said))
        self.serving(X)
        versions.sweep()
        gone = [self.state / "releases", self.state / "documents", self.state / "recents",
                *(self.cache / name for name in legacy.CACHES)]
        self.assertEqual([path for path in gone if path.exists()], [])
        for kept in ("settings.json", "engines/token", "engines/engine.json", "install-receipt.json", "plugin",
                     "default", f"installations/{X}.json", "installations/current", "versions.json"):
            self.assertTrue((self.state / kept).exists(), kept)
        self.assertEqual(installations.current_version(), X)
        self.assertFalse((self.state / "installations" / f"{OLD}.json").exists(), "the flat release's record went")

    def test_it_stays_while_any_condition_fails(self) -> None:
        self.legacy()
        self.present(X)
        pointers.write(None, X)
        self.assertIn("not imported", legacy.unsafe(X))
        imports.ensure(X)
        self.assertIn("has not started", legacy.unsafe(X))
        self.serving(X)
        flat = places.lock(self.engines / "engine.lock")  # a server before 0.12, started outside releases/
        self.assertIn("holds the flat engine folder", legacy.unsafe(X))
        self.assertFalse(legacy.remove(X))
        with mock.patch.object(legacy, "flat_server", return_value=str(places.code_dir(X) / "server")):
            self.assertNotIn("flat engine", legacy.unsafe(X) or "", "the default's own server, the bridge")
        flat.close()
        with mock.patch.object(releases, "running", side_effect=lambda folder: Path(folder).name == OLD):
            self.assertIn("still runs from", legacy.unsafe(X))
            self.assertFalse(legacy.remove(X))
        self.assertTrue((self.state / "releases" / OLD).exists() and (self.state / "documents").exists())
        self.assertIsNone(legacy.unsafe(X))
        self.assertTrue(legacy.remove(X))
        self.assertFalse(legacy.removable())


class SetupAdd(Device):
    def test_add_makes_this_version_present_and_changes_nothing_else(self) -> None:
        from cad_server.cli import setup

        dev = f"{X}-dev.20261113000000"
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": dev}), \
                mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            self.assertEqual(setup.main(["--add"]), 0)
            self.assertEqual(setup.main(["--add", "--quiet"]), 0)
        self.assertEqual(out.getvalue(), f"text-to-cad {dev} is installed now: {places.version_dir(dev)}\n")
        self.assertIsNotNone(places.version_record(dev))
        self.assertTrue(any("-e" in step for step in self.uv.steps), "a development version from its checkout")
        self.assertEqual(sorted(os.listdir(self.state)), ["install.lock", "versions"],
                         "no pointer, no mirror, no receipt, no settings, no plugin folder")
        with mock.patch.object(sys, "stderr", io.StringIO()), self.assertRaises(SystemExit):
            setup.main(["--add", "--only", "claude-code"])


if __name__ == "__main__":
    unittest.main()
