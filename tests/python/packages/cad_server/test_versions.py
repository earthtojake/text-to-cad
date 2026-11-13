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
    REAL_SERVERS = False

    def setUp(self) -> None:
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="cad-versions-")))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state, self.cache, self.engines = self.root / "state", self.root / "cache", self.root / "engines"
        self.wheels = self.root / "wheels"
        environment = {"CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.engines),
                       "CAD_CACHE_DIR": str(self.cache), "CAD_INSTALLATION_VERSION": "",
                       "CAD_LAUNCHER_DIR": str(self.root / "bin"),
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
        # The versions whose server runs (``serving``): asked of its door by ``versions.serves``, which these tests,
        # running no server, answer from here (``REAL_SERVERS``: a suite whose servers are real asks them).
        self.servers: dict[str, object] = {}
        if not self.REAL_SERVERS:
            serves = mock.patch.object(versions, "serves", side_effect=lambda name: name in self.servers
                                       and not self.servers[name].closed)
            serves.start()
            self.addCleanup(serves.stop)

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
        """Version ``name``'s server lock held, as its running server holds it, and its door answering
        (``versions.serves``): let go at the test's end, or by closing what this returns."""
        held = places.lock(places.engine_dir(name) / "engine.lock")
        self.assertIsNotNone(held)
        self.addCleanup(held.close)
        self.servers[name] = held
        return held

    def moved(self, channel: str | None, name: str) -> versions.Moved:
        found = versions.move(channel, name, told=self.said.append)
        self.assertTrue(found.ok, found.error)
        return found

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
        for name in ("documents", "hulls", "mjcf", "homes", "interference", "base", "pycache"):
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
        loud = io.StringIO()
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}):
            code = versions.add(quiet=True, out=out, err=err)
            self.assertEqual(versions.add(out=io.StringIO(), err=loud), 3)
        (reason,) = err.getvalue().splitlines()  # the cad command's own run: the reason alone, said in its line
        self.assertEqual((code, out.getvalue()), (3, ""))
        self.assertIn("dns error", reason)
        said = loud.getvalue().splitlines()[-1]  # a person's run: the one line, with the command to run
        self.assertTrue(said.startswith(f"cad: text-to-cad {X} is not installed, and could not be installed from this shell ("))
        self.assertTrue(said.endswith(versions.add_command(X)))


class Pointers(Device):
    def test_read_written_whole_and_listed(self) -> None:
        self.assertIsNone(pointers.read(None))
        pointers.write("my-store.2", X)
        pointers.write("a", Y)
        self.assertEqual((self.state / "channels" / "a").read_text(encoding="utf-8"), f"{Y}\n")
        with mock.patch.object(pointers, "replace_atomic", side_effect=OSError("disk full")):
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

    def test_recents_opens_after_an_update(self) -> None:
        from cad.engine.atomic_replace import put

        self.legacy()
        self.present(X)
        imports.ensure(X)
        old = self.cache / "documents" / IDENT / "document.xbf"
        new = places.cache_dir(X) / "documents" / IDENT / "document.xbf"
        self.assertEqual(new.read_bytes(), b"the legacy document's bytes", "the record's bytes came with it")
        if os.name != "nt":
            self.assertEqual(os.stat(new).st_ino, os.stat(old).st_ino, "one volume: a hard link, no copy")
        self.assertFalse((places.data_dir(X) / "telemetry-batches.jsonl").exists() or
                         (places.data_dir(X) / "telemetry-spool.jsonl").exists(),
                         "what was kept for sending is never copied: it moves once, as the layout goes")
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
        # Only the new version's own folder may change, and the note in the version left of where its data would go,
        # written before the pointer (``versions.SUCCESSOR``), which names nothing while a pointer names that version.
        note = places.version_dir(X) / versions.SUCCESSOR

        def listed() -> list[str]:
            return sorted(str(path.relative_to(self.state)) for path in self.state.rglob("*")
                          if Path(places.version_dir(Y)) not in path.parents and path not in (places.version_dir(Y), note))

        before = listed()

        def unchanged(kind: str | None, moved: versions.Moved | None = None) -> None:
            if moved is not None:
                self.assertEqual(moved.kind, kind)
            self.assertEqual(pointers.read("store"), X)
            self.assertEqual(listed(), before, "only the new version's own folder may have changed")

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
            self.data(name)
        pointers.write("store", Z, mirrored=False)
        pointers.write(None, Z, mirrored=False)
        for name in (X, Y):  # left, the channel now on Z
            (places.version_dir(name) / versions.SUCCESSOR).write_text(f"{Z}\n", encoding="utf-8")
        self.assertEqual(versions.remove(Z), "named")
        held = self.serving(Y)
        self.assertEqual(versions.remove(Y), "connected", "a running server that cannot say counts as connected")
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
                mock.patch.object(versions, "stop_server", side_effect=lambda _name: held.close() or True), \
                mock.patch.object(releases, "running", return_value=False):
            self.assertEqual(versions.sweep(), {Y: "removed"})
        self.assertEqual(versions.present(), [Z])

    def test_a_server_is_left_running_where_another_process_runs_from_its_folder(self) -> None:
        # A8: a process other than the server and its own (a command, a ``cad run``) keeps the folder whatever the
        # server does, so the server is not stopped for nothing.
        self.data(X)
        self.data(Y)
        pointers.write(None, Y, mirrored=False)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")
        self.serving(X)
        asked: list[dict] = []

        def ask(_name, message, **_kwargs):
            asked.append(message)
            return {"ok": True, "pid": 4242} if message == {"op": "pid"} else {"ok": True, "working": False}

        with mock.patch.object(versions, "ask", ask), \
                mock.patch.object(releases, "running", return_value=True) as running, \
                mock.patch.object(versions, "stop_server") as stopped:
            self.assertEqual(versions.remove(X), "in use")
        running.assert_called_once_with(places.version_dir(X), besides=4242)
        stopped.assert_not_called()
        self.assertEqual(asked, [{"op": "pid"}], "not even asked whether it works")

    def test_running_spares_the_server_s_own_processes_and_no_other(self) -> None:
        listed = ("  10   1 /bin/zsh\n  20  10 /v/code/server/bin/python -m cad_server._internal.engine_daemon\n"
                  "  21  20 /v/code/base/k/bin/python -m cad.engine.worker\n")
        done = subprocess.CompletedProcess([], 0, listed, "")
        with mock.patch.object(releases.subprocess, "run", return_value=done), \
                mock.patch.object(releases.os.path, "realpath", side_effect=lambda path: str(path)):
            self.assertTrue(releases.running("/v"))
            self.assertFalse(releases.running("/v", besides=20), "the server and its worker")
            self.assertTrue(releases.running("/v", besides=21), "the worker alone: the server is another")


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
        # Its kept batches moved, once, to the default's version: never copied, so never sent twice.
        self.assertFalse((self.state / "telemetry-batches.jsonl").exists())
        self.assertIn('"b1"', (places.data_dir(X) / "telemetry-batches.jsonl").read_text(encoding="utf-8"))

    def test_it_stays_while_any_condition_fails(self) -> None:
        self.legacy()
        self.present(X)
        pointers.write(None, X)
        self.assertIn("not imported", legacy.unsafe(X))
        imports.ensure(X)
        self.assertIn("has not started", legacy.unsafe(X))
        self.serving(X)
        flat = places.lock(self.engines / "engine.lock")  # a server of 0.11.10 or earlier, started outside releases/
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
    def interpreter(self, folder: str) -> None:
        home = self.root / "home"
        home.mkdir(exist_ok=True)
        (home / "python.exe").write_bytes(b"MZ")
        Path(folder, "Scripts").mkdir(parents=True, exist_ok=True)
        Path(folder, "Scripts", "python.exe").write_bytes(b"MZ")
        Path(folder, "pyvenv.cfg").write_text(f"home = {home}\nversion_info = 3.14.0\n", encoding="utf-8")

    def test_add_makes_this_version_present_and_changes_nothing_else(self) -> None:
        from cad_server.cli import setup

        dev = f"{X}-dev.20261113000000"
        out, err = io.StringIO(), io.StringIO()
        # On Windows the cad command's Python, as uv makes it, without uv.
        making = mock.patch.object(installations, "_make_interpreter", side_effect=self.interpreter)
        making.start()
        self.addCleanup(making.stop)
        command = Path(installations.proxy_path())
        command.parent.mkdir()
        if os.name != "nt":  # 0.11.10's, which knows no pin: replaced (on Windows, none: written)
            command.write_text(f"#!/bin/sh\n# {installations.MARK}11\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": dev}), \
                mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            self.assertEqual(setup.main(["--add"]), 0)
            self.assertEqual(setup.main(["--add", "--quiet"]), 0)
        self.assertEqual(out.getvalue(), f"text-to-cad {dev} is installed now: {places.version_dir(dev)}\n")
        self.assertIsNotNone(places.version_record(dev))
        self.assertTrue(any("-e" in step for step in self.uv.steps), "a development version from its checkout")
        self.assertEqual(sorted(os.listdir(self.state)), ["install.lock", "versions"],
                         "no pointer, no mirror, no receipt, no settings, no plugin folder")
        self.assertEqual(installations.proxy_status(), installations.OK, "and the cad command, of this revision")
        with mock.patch.object(sys, "stderr", io.StringIO()), self.assertRaises(SystemExit):
            setup.main(["--add", "--only", "claude-code"])


class ServerDecisions(Device):
    """What the servers decide by, at the cheapest level: no server runs (``test_version_servers`` runs them)."""

    def test_connected_means_work_in_flight_and_a_server_that_cannot_say_is_connected(self) -> None:
        for answer, expected in (({"ok": True, "working": False}, False), ({"ok": True, "working": True}, True),
                                 (None, True), ({"failed": "unknown request 'working'"}, True)):
            with self.subTest(answer=answer), mock.patch.object(versions, "ask", return_value=answer) as asked:
                self.assertEqual(versions.connected(X), expected)
                asked.assert_called_once_with(X, {"op": "working"})

    def test_an_unnamed_idle_server_retires_and_nothing_else_does(self) -> None:
        for name in (X, Y, Z):
            self.present(name)
        pointers.write(None, Y, mirrored=False)
        pointers.write("store", Z, mirrored=False)
        self.assertTrue(versions.retiring(X, working=False))
        self.assertFalse(versions.retiring(X, working=True), "work in flight keeps it")
        self.assertFalse(versions.retiring(Y, working=False), "the default's")
        self.assertFalse(versions.retiring(Z, working=False), "a named channel's")
        held, release = threading.Event(), threading.Event()

        def moving() -> None:
            with versions.install_lock():
                held.set()
                release.wait(30)

        mover = threading.Thread(target=moving)
        mover.start()
        held.wait(30)
        try:
            self.assertFalse(versions.retiring(X, working=False), "decided again once no move holds the lock")
        finally:
            release.set()
            mover.join()
        (self.state / "default").unlink()
        self.assertTrue(versions.retiring(Y, working=False), "unnamed, and not the newest present")
        pointers.forget("store")
        self.assertFalse(versions.retiring(Z, working=False), "no pointer at all: the newest present is the default's")

    def test_the_flat_door_is_the_default_channel_s_version_s_alone(self) -> None:
        for name in (X, Y):
            self.present(name)
        pointers.write("store", Y, mirrored=False)
        self.assertTrue(versions.flat(Y), "no pointer: the newest present is the default's")
        pointers.write(None, X, mirrored=False)
        self.assertEqual((versions.flat(X), versions.flat(Y), versions.flat(None)), (True, False, False))

    def test_garbage_is_a_left_version_never_one_installed_and_never_used(self) -> None:
        # A1 (this test asserted the opposite before): a version installed and not yet named -- an update's target
        # waiting for its setup, a pin's version before its move -- is never a sweep's, nor is an incomplete one.
        left = "0.11.50"
        self.present(X)
        self.data(Y)
        pointers.write(None, Y, mirrored=False)
        (places.code_dir(Z)).mkdir(parents=True)  # an install cut short: no code marker
        self.assertFalse(versions.garbage(), "installed and never used, or incomplete: no sweep's")
        self.assertEqual(versions.sweep(), {})
        self.assertEqual(versions.folders(), [X, Y, Z])
        self.assertEqual((versions.fate(X, versions._kept()), versions.fate(Z, versions._kept())), ("unused", "partial"))
        # A version a channel left (used, unnamed, its successor known) is: swept, but never by its own server.
        self.data(left)
        (places.version_dir(left) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")
        self.assertTrue(versions.garbage())
        self.assertFalse(versions.garbage(spare=left), "a server never sweeps its own version")
        with mock.patch.object(versions, "_remove", return_value="connected") as removing:
            self.assertEqual(versions.sweep(spare=left), {})
            removing.assert_not_called()
        self.assertEqual(versions.sweep(), {left: "removed"})
        self.assertEqual(versions.folders(), [X, Y, Z], "what was never used stays")
        # cad doctor --prune removes those, as the person asks.
        plan = versions.prune_plan()
        self.assertEqual(set(plan.versions), {X, Z})
        self.assertEqual(versions.prune(plan), {X: "removed", Z: "removed"})
        self.assertEqual(versions.folders(), [Y])

    def test_an_automatic_update_s_target_is_there_when_its_setup_runs_after_the_quiet_hour(self) -> None:
        # A1: the target installed at once, its setup an hour later (the clock made short here), servers tending
        # meanwhile -- each tend's sweep finds nothing to remove.
        from types import SimpleNamespace

        from cad_server import auto_updates
        from cad_server._internal import update

        self.data(X)
        pointers.write(None, X, mirrored=False)
        (self.state / "install-receipt.json").write_text('{"schema": 1}', encoding="utf-8")
        seen: list[bool] = []

        def install(version: str) -> dict:
            self.present(version)
            return {"cad": "the release's cad"}

        def setup(record, frame=None):
            seen.append(places.version_dir(Y).is_dir() and places.version_record(Y) is not None)
            return 0, ""

        engine = SimpleNamespace(stopping=threading.Event(), draining=False, worked=0.0, working=lambda: False)
        job = update.Update()
        with mock.patch.object(auto_updates, "IDLE_SECONDS", 0.5), mock.patch.object(update, "IDLE_POLL_SECONDS", 0.02), \
                mock.patch.dict(os.environ, {"CAD_UPDATE_CHECK": "", "CI": ""}), \
                mock.patch("cad_server.updates.notice", return_value={"latest": Y, "version": X}), \
                mock.patch("cad_server.updates.refresh", return_value=None), \
                mock.patch.object(update, "install", side_effect=install), \
                mock.patch.object(update, "run_setup", side_effect=setup):
            self.assertEqual(job.automatic(engine), Y)
            while not seen:  # the quiet hour, the servers tending all through it
                self.assertFalse(versions.garbage(spare=X))
                versions.sweep(spare=X)
                job.thread.join(0.05)
            job.thread.join(30)
        self.assertEqual(seen, [True], "the target was there when its setup ran")

    def test_an_updater_removes_its_own_earlier_target_as_it_prepares_a_newer_one(self) -> None:
        from cad_server import auto_updates
        from cad_server._internal import update

        self.data(X)
        pointers.write(None, X, mirrored=False)
        self.present(Y)  # an earlier automatic attempt's target, never moved to
        auto_updates.attempt(Y)
        with mock.patch.object(update, "install", side_effect=lambda version: self.present(version).record):
            update._discard(Y, Z)
            self.assertFalse(places.version_dir(Y).exists())
            self.present(Y)
            pointers.write("store", Y, mirrored=False)
            update._discard(Y, Z)
        self.assertTrue(places.version_dir(Y).exists(), "a channel's version is never an updater's to remove")
        self.assertEqual(versions.remove_unused(X), "named")

    def test_a_handover_takes_the_port_only_from_a_server_that_went(self) -> None:
        asked: list[tuple[str, dict]] = []

        def ask(name, message, **_kwargs):
            asked.append((name, message))
            return {"ok": True, "url": "http://127.0.0.1:4000/", "port": 4000} if message.get("op") == "http" else {}

        with mock.patch.object(versions, "ask", ask), mock.patch.object(versions, "start_server", return_value=True), \
                mock.patch.object(versions, "serves", side_effect=lambda name: name == Y):
            self.assertTrue(versions.handover(None, X, Y, 4000))
            self.assertEqual(asked, [(Y, {"op": "bridge"}), (Y, {"op": "http", "port": 4000})])
            asked.clear()
            self.assertFalse(versions.handover("store", X, Y, None), "a server that served no pages: nothing")
            self.assertEqual(asked, [], "and a named channel's move never asks about the flat door")
        with mock.patch.object(versions, "ask", ask), mock.patch.object(versions, "serves", return_value=True):
            asked.clear()
            self.assertFalse(versions.handover(None, X, Y, 4000), "the old server still runs: it keeps its port")
            self.assertEqual(asked, [(X, {"op": "bridge"}), (Y, {"op": "bridge"})], "the old one let go first")

    def test_a_channel_s_use_is_a_stamp_beside_its_pointer_which_only_a_move_writes(self) -> None:
        pointers.write("store", X, mirrored=False)
        path = self.state / "channels" / "store"
        os.utime(path, (1_000_000, 1_000_000))
        with mock.patch.dict(pointers._used, clear=True):
            self.assertTrue(pointers.used("store"))
            stamp = self.state / "used" / "store"
            self.assertGreater(stamp.stat().st_mtime, 1_000_000)
            self.assertEqual(path.stat().st_mtime, 1_000_000, "the pointer is never written for a use")
            self.assertGreater(pointers.last_used(pointers.listing()[0]), 1_000_000)
            self.assertFalse(pointers.used("store"), "once a minute at most")
            self.assertFalse(pointers.used(None), "the default channel has no pointer here: none is made")
            self.assertFalse(pointers.used("../x"), "no channel")
        with mock.patch.dict(pointers._used, clear=True):
            self.assertFalse(pointers.used("store", every=pointers.USED_DAILY), "a pinned command's: once a day")
        self.assertFalse((self.state / "default").exists())
        pointers.forget("store")
        self.assertFalse(stamp.exists(), "a channel forgotten, its stamp with it")

    def test_a_pointer_that_cannot_be_read_is_not_no_pointer_and_nothing_is_removed(self) -> None:
        # A3: an emptied pointer (a crash), or one that cannot be read now, never makes its version garbage.
        self.data(X)
        self.data(Y)
        pointers.write("store", X, mirrored=False)
        pointers.write(None, Y, mirrored=False)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")
        (self.state / "channels" / "store").write_bytes(b"")
        with self.assertRaises(pointers.Unreadable):
            pointers.listing()
        self.assertFalse(versions.garbage())
        said: list[str] = []
        self.assertEqual(versions.sweep(told=said.append), {})
        self.assertIn("nothing is removed this time", said[0])
        self.assertFalse(versions.retiring(X, working=False))
        self.assertTrue(places.version_dir(X).is_dir())
        real = Path.read_bytes

        def denied(path):
            if path.name == "store":
                raise PermissionError(13, "sharing violation")
            return real(path)

        pointers.write("store", X, mirrored=False)
        with mock.patch.object(Path, "read_bytes", denied):
            with self.assertRaises(pointers.Unreadable):
                pointers.read("store")
            self.assertEqual(versions.sweep(), {})
            moved = versions.move("store", Z)
            self.assertEqual(moved.kind, "failed", "no move on a guess")
        self.assertTrue(places.version_dir(X).is_dir())
        (self.state / "channels" / "store").write_bytes(b"")
        self.assertEqual(self.moved("store", Z).old, None, "an emptied pointer is written again by a move")
        self.assertEqual(pointers.read("store"), Z)

    def test_a_pinned_command_s_stop_and_status_reach_its_own_version_alone(self) -> None:
        from cad.engine import client

        self.present(X)
        places._versioned.cache_clear()
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}):
            places._versioned.cache_clear()
            self.assertEqual(places.endpoints(), [versions.endpoint(X)])
            self.assertEqual(client.sweep(stop=True), {"stopped": [], "running": [], "removed": []})
        places._versioned.cache_clear()
        self.assertEqual(places.endpoints()[0].lock, self.engines / "engine.lock", "no version: the flat one")

    def test_an_event_says_its_channel_and_the_app_it_came_from(self) -> None:
        from cad_server._internal.channel import describe

        with mock.patch("cad_server._internal.channel._source_tree", return_value=False):  # a release, not a checkout
            self.assertEqual(describe("codex", "codex-mcp-client"), {"channel": "codex", "app": "codex"})
            self.assertEqual(describe(None, "cursor-vscode", {}), {"channel": "default", "app": "cursor"})
            self.assertEqual(describe("claude", None, {"CLAUDECODE": "1"}), {"channel": "claude", "app": "claude-code"})
            self.assertEqual(describe("Not A Channel", "Some Host", {}), {"channel": "default", "app": "some-host"})
            self.assertEqual(describe(None, None, {}), {"channel": "default", "app": "unknown"})
        # A development build says `dev`: a checkout not told the version it runs as is one.
        self.assertEqual(describe("codex", "codex-mcp-client")["channel"], "dev")
        from cad_server._internal import channel

        self.assertEqual(channel._DEVELOPMENT.pattern, versions.DEVELOPMENT.pattern, "one rule, copied")


class TelemetryAcrossVersions(Device):
    """A no is a no everywhere (``analytics.everywhere``, ``inherit_no``), and what a version had not sent goes on with
    the next as its folder goes (``analytics.hand_on``)."""

    def off_in(self, name: str) -> None:
        from cad_server import analytics

        with mock.patch.object(places, "versioned", return_value=name):
            chosen = analytics.choose(False, by="cli", forget=lambda _id: True)
        self.assertTrue(chosen["saved"])

    def sharing(self, name: str) -> bool:
        from cad_server import analytics

        with mock.patch.object(places, "versioned", return_value=name), \
                mock.patch("cad_server._internal.channel._source_tree", return_value=False), \
                mock.patch.dict(os.environ, {"CI": "", "DO_NOT_TRACK": "", "CAD_TELEMETRY": ""}):
            return analytics.status(probe=False, keep=False)["sharing"]

    def test_off_in_one_version_is_off_in_every_version_and_in_any_made_present_afterwards(self) -> None:
        told = {"telemetry": {"choice": "on", "disclosure": 1, "by": "cli", "decidedAt": 1.0, "id": "an-id"}}
        self.data(X, told)
        self.data(Y, told)
        self.assertTrue(self.sharing(X) and self.sharing(Y))
        self.off_in(Y)
        self.assertFalse(self.sharing(X), "said in the other version too")
        self.assertFalse(self.sharing(Y))
        device = json.loads((self.state / "settings.json").read_text(encoding="utf-8"))["telemetry"]
        self.assertEqual(device["choice"], "off", "and at the old place, made, in the form every release reads")
        x = json.loads((places.data_dir(X) / "settings.json").read_text(encoding="utf-8"))["telemetry"]
        self.assertEqual((x["choice"], "id" in x, x["forget"]), ("off", False, ["an-id"]), "its id owed a deletion")
        # A version made present afterwards: a newer one importing from Y, and an older one with nothing older to
        # import from -- both start with the off.
        for name in (Z, "0.11.99"):
            self.present(name)
            imports.ensure(name)
            with self.subTest(version=name):
                self.assertFalse(self.sharing(name))
                kept = json.loads((places.data_dir(name) / "settings.json").read_text(encoding="utf-8"))
                self.assertEqual(kept["telemetry"]["choice"], "off")

    def test_a_later_yes_in_a_version_is_its_own_and_what_imports_from_it(self) -> None:
        from cad_server import analytics

        self.data(X)
        self.off_in(X)
        with mock.patch.object(places, "versioned", return_value=X):
            analytics.choose(True, by="cli")
        self.assertTrue(self.sharing(X))
        self.present(Y)
        imports.ensure(Y, leaving=X)
        self.assertTrue(self.sharing(Y), "the yes is newer than the device's no")

    def test_what_a_version_kept_for_sending_goes_to_the_next_as_its_folder_goes(self) -> None:
        from cad_server import analytics

        self.data(X)
        self.data(Y)
        row = {"answer": [None, None], "at": 1.0, "source": {"version": X, "channel": "codex", "app": "codex"},
               "counts": {"features": ["drawing"]}}
        (places.data_dir(X) / analytics.SPOOL).write_text(json.dumps(row) + "\n", encoding="utf-8")
        pointers.write(None, Y)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")  # the default left it
        self.assertEqual(versions.sweep(), {X: "removed"})
        kept = [json.loads(line) for line in
                (places.data_dir(Y) / analytics.SPOOL).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(kept, [row], "handed on whole, still saying who counted it")


class DoctorReadsEveryVersion(Device):
    """``cad doctor`` is the one command that reads every version and channel; ``--prune`` forgets the named channels
    unused for 30 days, never the default, and removes the versions then unnamed."""

    def report(self) -> list[str]:
        from cad_server.cli import doctor

        with mock.patch.object(versions, "serving", return_value=None):
            return doctor._versions()

    def test_the_report_and_the_prune(self) -> None:
        import contextlib
        import io
        import time

        from cad_server.cli import doctor

        self.data(X)
        self.data(Y)
        self.data(Z)
        pointers.write(None, Y)
        pointers.write("old-store", X, mirrored=False)
        versions.move("store", Z)
        long_ago = time.time() - (pointers.FORGOTTEN_DAYS + 1) * 86400
        for path in (self.state / "channels" / "old-store", self.state / "default"):
            os.utime(path, (long_ago, long_ago))
        held = self.serving(Z)
        said = self.report()

        def line(start: str) -> str:
            found = [each for each in said if each.startswith(start)]
            self.assertEqual(len(found), 1, said)
            return found[0]

        self.assertIn("channels old-store; its server is not running", line(f"version  text-to-cad {X} "))
        self.assertIn("channels default; its server is not running", line(f"version  text-to-cad {Y} "))
        self.assertIn("channels store; its server runs", line(f"version  text-to-cad {Z} "))
        self.assertIn("unused for 30 days: cad doctor --prune forgets it", line("channel  old-store: "))
        self.assertIn(f"text-to-cad {Z}, last used ", line("channel  store: "))
        self.assertNotIn("forgets it", line("channel  default: "), "the default channel is never forgotten")
        held.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(versions, "connected", return_value=False):
            self.assertEqual(doctor.main(["--prune", "--yes"]), 0)
        printed = out.getvalue()
        self.assertIn(f"forgot the old-store channel (text-to-cad {X})", printed)
        self.assertIn(f"removed text-to-cad {X}", printed)
        self.assertIsNone(pointers.read("old-store"))
        self.assertEqual((pointers.read(None), pointers.read("store")), (Y, Z))
        self.assertEqual(versions.folders(), [Y, Z])


if __name__ == "__main__":
    unittest.main()
