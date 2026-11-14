"""Versions installed side by side (``cad_server._internal.versions``, ``imports``, ``legacy``): making one present,
its settings and store copied in once, its use record, the cleanup the newest version's server runs, the layout of
0.11.10 and earlier, and what the servers decide by.

A fake device in a temporary folder (``CAD_STATE_DIR``, ``CAD_ENGINE_DIR``, ``CAD_CACHE_DIR``). uv is stood in for
(``Uv``): each step recorded; ``venv`` makes a real virtual environment of this Python with no pip, and installing
the server writes a ``.pth`` naming this checkout's sources and a ``cad`` beside its Python, so the version's own
Python really runs the proof (``versions._probe``); the kernel's install writes nothing. The folder of wheels uv
reads beside its index is the suites' seam (``CAD_UPDATE_FIND_LINKS``), named and never served: nothing reaches an
index. The cleanup's clock is passed in (``versions.clean``'s ``now``, ``Daemon.versions``'s): nothing sleeps.
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
from types import SimpleNamespace
from unittest import mock

from tests.python.support.paths import repo_path

from cad.engine import places
from cad_server._internal import base, imports, installations, legacy, releases, versions
from cad_server.engine import registry

OLD, X, Y, Z = "0.11.10", "0.12.0", "0.12.1", "0.12.2"
IDENT = "0b0e0a8e-6d0a-4c6e-9a63-1f2d3c4b5a69"
LATE = "2b0e0a8e-6d0a-4c6e-9a63-1f2d3c4b5a69"
SOURCES = (str(repo_path("packages/cad/src")), str(repo_path("packages/cad-server/src")))
TOKEN = "t" * 43
DAY = 86400.0


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

    def aged(self, name: str, *, installed: float, used: float | None = None) -> None:
        """Version ``name`` installed at ``installed`` (its code marker's time) and last used at ``used`` (its
        ``versions.USED`` file's), or never."""
        os.utime(places.code_dir(name) / places.VERSION_MARKER, (installed, installed))
        if used is not None:
            path = places.version_dir(name) / versions.USED
            path.write_bytes(b"")
            os.utime(path, (used, used))

    def clean(self, own: str, now: float) -> dict[str, str]:
        """The cleanup as version ``own``'s server runs it, at ``now``."""
        with mock.patch.object(places, "versioned", return_value=own):
            return versions.clean(now=now, told=self.said.append)

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


class CopyOnce(Device):
    """A version's settings and store, copied in once from the newest older installed version, or from the layout of
    0.11.10 and earlier (``imports``)."""

    def test_from_the_newest_older_installed_version_never_its_caches_or_telemetry_and_never_again(self) -> None:
        self.data(X, {"language": {"locale": "fr"}})
        data = self.data(Y, {"language": {"locale": "de"}})
        (data / "documents" / IDENT).mkdir(parents=True)
        (data / "documents" / IDENT / "document.json").write_text("{}", encoding="utf-8")
        (data / "cache" / "hulls").mkdir(parents=True)
        (data / "cache" / "hulls" / "h.npz").write_bytes(b"hull")
        (data / "telemetry-spool.jsonl").write_text("{}\n", encoding="utf-8")
        self.present(Z)
        done = imports.ensure(Z)
        self.assertEqual((done.source.kind, done.source.version), ("version", Y), "the newest older one")
        new = places.data_dir(Z)
        self.assertEqual(json.loads((new / "settings.json").read_text(encoding="utf-8")), {"language": {"locale": "de"}})
        self.assertTrue((new / "documents" / IDENT / "document.json").is_file())
        self.assertFalse((new / "cache").exists() or (new / "telemetry-spool.jsonl").exists())
        self.assertEqual(imports.marker(Z)["imported"], {"kind": "version", "version": Y})
        self.assertTrue((data / "telemetry-spool.jsonl").exists(), "the source is not changed")
        (data / "settings.json").write_text('{"language": {"locale": "it"}}', encoding="utf-8")
        self.assertFalse(imports.ensure(Z).done, "once: what the older version writes later stays its own")
        self.assertEqual(json.loads((new / "settings.json").read_text(encoding="utf-8")), {"language": {"locale": "de"}})

    def test_never_from_a_newer_version_and_never_from_one_not_installed(self) -> None:
        self.data(Z, {"language": {"locale": "z"}})
        self.data(X, {"language": {"locale": "x"}})
        shutil.rmtree(places.code_dir(X))  # its data there, the version no longer installed
        self.present(Y)
        done = imports.ensure(Y)
        self.assertEqual((done.done, done.source), (True, None), "only a newer one installed: fresh, nothing copied")
        self.assertEqual(os.listdir(places.data_dir(Y)), [imports.MARKER])

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
        imports.ensure(Y)
        settings = json.loads((mine / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((settings["telemetry"]["choice"], settings["language"]), ("off", {"locale": "fr"}))
        self.assertEqual((mine / "engines" / "token").read_text(encoding="ascii").strip(), TOKEN)
        self.assertTrue((mine / "documents" / ident / "document.json").is_file(), "a record written first stays")

    def test_the_layout_ranks_below_older_versions_and_once_removed_gives_its_settings_alone(self) -> None:
        self.legacy()
        self.data(X)
        self.present(Y)
        self.assertEqual(imports.source(Y).version, X, "the newest older version, not the layout")
        self.serving(X)
        (self.cache / "interference").mkdir(exist_ok=True)
        self.assertTrue(legacy.remove(X))
        self.assertFalse(self.cache.exists(), "the interference cache too: the cache folder emptied and gone")
        self.assertFalse(legacy.present())
        shutil.rmtree(places.version_dir(X))
        found = imports.source(Y)
        self.assertEqual((found.kind, found.settings_only), ("legacy", True))
        imports.ensure(Y)
        self.assertEqual(sorted(os.listdir(places.data_dir(Y))), ["carried.json", "format.json", "settings.json"],
                         "its kept settings alone (and what it took of them): no token, no batches, nothing sent again")


class Use(Device):
    """Each version's own last use by an agent (``versions.used``, ``last_used``)."""

    def test_a_use_is_its_file_s_time_written_at_most_once_an_hour_and_only_for_a_version_installed(self) -> None:
        self.present(X)
        path = places.version_dir(X) / versions.USED
        self.assertEqual(versions.last_used(X), os.stat(places.code_dir(X) / places.VERSION_MARKER).st_mtime,
                         "never used: from its install")
        now = time.time() + 10 * DAY
        self.assertTrue(versions.used(X, now=now))
        self.assertEqual((path.stat().st_mtime, versions.last_used(X)), (now, now))
        self.assertFalse(versions.used(X, now=now + 60), "within the hour: not written again")
        self.assertTrue(versions.used(X, now=now + versions.USE_SECONDS))
        self.assertFalse(versions.used(Y, now=now), "not installed: nothing made")
        self.assertFalse(places.version_dir(Y).exists())
        self.assertFalse(versions.used(None), "a process of no version records nothing")
        with mock.patch.object(places, "versioned", return_value=X):
            self.assertTrue(versions.used(now=now + 2 * versions.USE_SECONDS), "this process's own by default")


class Cleanup(Device):
    """The newest installed version's server removes every older one no agent has used for 2 days."""

    def test_older_versions_unused_for_two_days_go_and_the_rest_stay(self) -> None:
        now = time.time()
        stale, lately, fresh, never = "0.11.20", X, "0.11.30", "0.11.40"
        for name in (stale, lately, fresh, never, Y):
            self.data(name)
        self.aged(stale, installed=now - 30 * DAY, used=now - 2 * DAY - 1)
        self.aged(lately, installed=now - 30 * DAY, used=now - 2 * DAY + 60)
        self.aged(fresh, installed=now - DAY)  # never used: counted from its install
        self.aged(never, installed=now - 3 * DAY)
        installations.register(stale, (str(places.version_record(stale)["cad"]), str(places.version_record(stale)["python"]),
                                       str(places.version_record(stale)["prefix"])))
        done = self.clean(Y, now)
        self.assertEqual(done, {stale: "removed", lately: "used", fresh: "used", never: "removed"})
        self.assertEqual(versions.folders(), [fresh, X, Y])
        self.assertFalse(places.engine_dir(stale).exists())
        self.assertFalse(any(record["version"] == stale for record in installations.records()), "its record forgotten")
        self.assertFalse(any(entry.startswith(".trash-") for entry in os.listdir(places.versions_dir())))
        self.assertIn(f"removed cad {stale}, which no agent has used for 2 days", self.said)

    def test_going_back_from_a_development_install_removes_its_versions_used_or_not(self) -> None:
        # A development version sorts after its release: `dev_install.py --release` removes it (its REMOVE, run by the
        # checkout's Python), so the release is the newest installed again.
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev_install_under_test",
                                                      repo_path("scripts/install/dev_install.py"))
        dev_install = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dev_install)
        self.data(X)
        development = f"{X}-dev.20261114000000"
        versions.development(development, sys.executable, sys.executable, sys.prefix)
        versions.used(development)
        self.assertEqual(versions.newest(), development)
        printed: list[str] = []
        with mock.patch("builtins.print", side_effect=lambda *words, **_: printed.append(" ".join(map(str, words)))):
            exec(dev_install.REMOVE, {})  # noqa: S102 - the snippet the script runs, run here on this device
        self.assertEqual((versions.present(), versions.newest()), ([X], X))
        self.assertEqual(printed, [f"removed cad {development}"])

    def test_a_version_that_is_not_the_newest_cleans_nothing(self) -> None:
        now = time.time()
        for name in (X, Y, Z):
            self.present(name)
            self.aged(name, installed=now - 30 * DAY)
        self.assertEqual(self.clean(Y, now), {})
        with mock.patch.object(places, "versioned", return_value=None):
            self.assertEqual(versions.clean(now=now), {}, "nor a process of no version")
        self.assertEqual(versions.folders(), [X, Y, Z])

    def test_work_in_flight_a_process_running_from_it_or_a_refused_move_keeps_it_and_nothing_is_waited_on(self) -> None:
        now = time.time()
        self.present(X)
        self.present(Y)
        self.aged(X, installed=now - 30 * DAY)
        held = self.serving(X)
        self.assertEqual(self.clean(Y, now), {X: "connected"}, "a running server that cannot say counts as working")
        with mock.patch.object(releases, "running", return_value=True) as running, \
                mock.patch.object(versions, "quiet", side_effect=AssertionError("waited")):
            held.close()
            self.assertEqual(self.clean(Y, now), {X: "in use"}, "a process runs from its folder: looked at once")
        running.assert_called_once()
        real = os.rename

        def refuse(source, target):
            if Path(source) == places.version_dir(X):
                raise PermissionError(13, "in use")
            return real(source, target)

        with mock.patch.object(os, "rename", refuse):
            self.assertEqual(self.clean(Y, now), {X: "refused"}, "Windows: a file in use")
        self.assertTrue(places.version_dir(X).is_dir())
        # Its server idle: asked to stop, then the folder goes.
        held = self.serving(X)
        with mock.patch.object(versions, "connected", return_value=False), \
                mock.patch.object(versions, "stop_server", side_effect=lambda _name: held.close() or True), \
                mock.patch.object(releases, "running", return_value=False):
            self.assertEqual(self.clean(Y, now), {X: "removed"})
        self.assertEqual(versions.present(), [Y])

    @unittest.skipIf(os.name == "nt", "POSIX lists processes (ps); Windows has its own answer, the test below")
    def test_running_spares_the_server_s_own_processes_and_no_other(self) -> None:
        listed =("  10   1 /bin/zsh\n  20  10 /v/code/server/bin/python -m cad_server._internal.engine_daemon\n"
                  "  21  20 /v/code/base/k/bin/python -m cad.engine.worker\n")
        done = subprocess.CompletedProcess([], 0, listed, "")
        with mock.patch.object(releases.subprocess, "run", return_value=done), \
                mock.patch.object(releases.os.path, "realpath", side_effect=lambda path: str(path)):
            self.assertTrue(releases.running("/v"))
            self.assertFalse(releases.running("/v", besides=20), "the server and its worker")
            self.assertTrue(releases.running("/v", besides=21), "the worker alone: the server is another")

    @unittest.skipIf(os.name != "nt", "Windows' answer; POSIX lists processes, the test above")
    def test_running_on_windows_asks_nothing_and_leaves_the_folder_to_its_rename(self) -> None:
        # Windows cannot be asked which process runs from a folder: False, nothing run, and the removal's rename
        # aside, which the system refuses while a file there is in use (a running python.exe, a loaded .pyd), keeps it.
        with mock.patch.object(releases.subprocess, "run") as run:
            self.assertFalse(releases.running(r"C:\v"))
            self.assertFalse(releases.running(r"C:\v", besides=20))
        run.assert_not_called()


    def test_the_server_cleans_as_it_starts_then_every_24_hours(self) -> None:
        from cad_server import updates
        from cad_server.engine import daemon

        self.assertTrue(versions.due(None, 5.0))
        self.assertFalse(versions.due(5.0, 5.0 + versions.CLEAN_SECONDS - 1))
        self.assertTrue(versions.due(5.0, 5.0 + versions.CLEAN_SECONDS))
        cleaned: list[float] = []
        engine = SimpleNamespace(draining=False, stopping=threading.Event(), cleaning=None, cleaned=None,
                                 legacy_tried=None, bridge=SimpleNamespace(reconcile=lambda: False))
        with mock.patch.object(daemon, "versioned", return_value=Y), mock.patch.object(updates, "refresh"), \
                mock.patch.object(legacy, "removable", return_value=False), \
                mock.patch.object(versions, "clean", side_effect=lambda **_kwargs: cleaned.append(engine.cleaned)):
            for now in (100.0, 200.0, 100.0 + versions.CLEAN_SECONDS - 1, 100.0 + versions.CLEAN_SECONDS):
                daemon.Daemon.versions(engine, now=now)
                engine.cleaning.join(10)
        self.assertEqual(cleaned, [100.0, 100.0 + versions.CLEAN_SECONDS], "as it starts, then a day later")

    def test_the_layout_before_is_tried_again_every_minute_between_cleanups(self) -> None:
        # The cleanup as the server starts finds the layout of 0.11.10 and earlier unsafe while the shipped updater's
        # helper that started the server still runs from it: its removal is tried again a minute later, not a day.
        from cad_server import updates
        from cad_server.engine import daemon

        cleaned, tried = [], []
        engine = SimpleNamespace(draining=False, stopping=threading.Event(), cleaning=None, cleaned=None,
                                 legacy_tried=None, bridge=SimpleNamespace(reconcile=lambda: False))
        with mock.patch.object(daemon, "versioned", return_value=Y), mock.patch.object(updates, "refresh"), \
                mock.patch.object(legacy, "removable", return_value=True), \
                mock.patch.object(versions, "clean", side_effect=lambda **_kwargs: cleaned.append(True)), \
                mock.patch.object(versions, "clean_legacy", side_effect=lambda **_kwargs: tried.append(True)):
            for now in (100.0, 100.0 + versions.LEGACY_SECONDS - 1, 100.0 + versions.LEGACY_SECONDS,
                        100.0 + versions.LEGACY_SECONDS + 1, 100.0 + 2 * versions.LEGACY_SECONDS):
                daemon.Daemon.versions(engine, now=now)
                if engine.cleaning is not None:
                    engine.cleaning.join(10)
        self.assertEqual((len(cleaned), len(tried)), (1, 2), "the cleanup as it starts, then the layout each minute")


class TheLayoutBefore(Device):
    """The layout of 0.11.10 and earlier: imported from where no older version is installed, and removed by the newest
    version's cleanup once that is safe (``legacy``)."""

    def test_the_cleanup_removes_it_once_safe_keeping_what_old_clients_read(self) -> None:
        self.legacy()
        self.present(X)
        self.assertEqual(imports.ensure(X).source.kind, "legacy")
        self.assertEqual(self.clean(X, time.time()), {})
        self.assertTrue((self.state / "releases" / OLD).exists(), "kept until its server serves")
        self.assertTrue(any("has not started yet" in line for line in self.said), self.said)
        self.serving(X)
        self.clean(X, time.time())
        gone = [self.state / "releases", self.state / "documents", self.state / "recents",
                *(self.cache / name for name in legacy.CACHES)]
        self.assertEqual([path for path in gone if path.exists()], [])
        for kept in ("settings.json", "engines/token", "engines/engine.json", "install-receipt.json", "plugin",
                     "installations/current", "versions.json"):
            self.assertTrue((self.state / kept).exists(), kept)
        self.assertFalse((self.state / "installations" / f"{OLD}.json").exists(), "the flat release's record went")
        # Its kept batches moved, once, to the version: never copied, so never sent twice.
        self.assertFalse((self.state / "telemetry-batches.jsonl").exists())
        self.assertIn('"b1"', (places.data_dir(X) / "telemetry-batches.jsonl").read_text(encoding="utf-8"))

    def test_it_stays_while_any_condition_fails(self) -> None:
        self.legacy()
        self.present(X)
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


    def test_what_it_wrote_after_the_import_is_carried_in_before_it_goes(self) -> None:
        def record(root: Path, ident: str, opened: float) -> None:
            folder = root / "documents" / ident
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "document.json").write_text(json.dumps({"schema": registry.SCHEMA, "id": ident, "kind": "file",
                                                              "opened": opened}), encoding="utf-8")

        def opened(ident: str) -> float | None:
            found = registry.Registry(places.data_dir(X)).get(ident)
            return None if found is None else found.get("opened")

        self.legacy()
        record(self.state, IDENT, 1.0)
        self.present(X)
        imports.ensure(X)
        self.assertEqual(opened(IDENT), 1.0)
        # A client of 0.11.10 still running writes on: a document made, an old one opened again.
        record(self.state, LATE, 2.0)
        record(self.state, IDENT, 9.0)
        self.serving(X)
        self.clean(X, time.time())
        self.assertFalse((self.state / "documents").exists(), "the layout removed")
        self.assertEqual((opened(LATE), opened(IDENT)), (2.0, 9.0), "carried in, the later use winning")

    def test_a_record_deleted_in_a_version_stays_deleted_when_the_layout_is_carried_in(self) -> None:
        self.legacy()
        self.present(X)
        imports.ensure(X)  # X imports the layout's record
        self.assertTrue((places.data_dir(X) / "documents" / IDENT / "document.json").is_file())
        registry.Registry(places.data_dir(X)).delete(IDENT)  # deleted in X
        self.present(Y)
        imports.ensure(Y)  # Y copies X, which no longer has it
        imports.carry(imports.of_legacy(), Y)  # the layout, which still has it, carried into Y
        self.assertFalse((places.data_dir(Y) / "documents" / IDENT).exists(), "deleted before: it stays deleted")


class FromEight(Device):
    """A computer that comes from 0.7 or 0.8 straight to this release: what those kept in their own state folder
    (``cadgen``) is taken in by the first version's import, through the layout of 0.11.10 and earlier, as every release
    since 0.10 did as it set itself up (``places.adopt_earlier``)."""

    def test_its_settings_records_and_telemetry_no_are_taken_in_and_whats_new_is_shown(self) -> None:
        environment = {key: value for key, value in os.environ.items() if key not in ("CAD_STATE_DIR", "XDG_STATE_HOME")}
        environment.update({"HOME": str(self.root / "home"), "USERPROFILE": str(self.root / "home")})
        patch = mock.patch.dict(os.environ, environment, clear=True)  # the platform's folders, in a home of its own
        patch.start()
        self.addCleanup(patch.stop)
        eight = places._platform_state(places.EARLIER_STATE)
        (eight / "documents" / IDENT).mkdir(parents=True)
        (eight / "documents" / IDENT / "document.json").write_text('{"id": "eight"}', encoding="utf-8")
        (eight / "settings.json").write_text(json.dumps({"telemetry": {"choice": "off", "decidedAt": 1.0},
                                                         "language": {"locale": "de"}}), encoding="utf-8")
        (eight / "installations").mkdir()
        (eight / "installations" / "0.8.4.json").write_text(json.dumps(
            {"version": "0.8.4", "python": "/gone/python", "cadgen": "/gone/cadgen", "prefix": "/gone"}),
            encoding="utf-8")
        self.present(X)
        done = imports.ensure(X)
        self.assertEqual(done.source.kind, "legacy")
        data = places.data_dir(X)
        settings = json.loads((data / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((settings["telemetry"]["choice"], settings["language"]), ("off", {"locale": "de"}))
        self.assertEqual(settings["whats_new"], {"seen": []}, "0.8 on record: shown what this release brought")
        self.assertTrue((data / "documents" / IDENT / "document.json").is_file(), "Recents' record")
        said_no = json.loads((eight / "settings.json").read_text(encoding="utf-8"))["telemetry"]["choice"]
        self.assertEqual(said_no, "off", "0.8's folder keeps the no, for a 0.8 still installed")


class ReadOnly(Device):
    """Whether a version's server runs is asked, never made or taken (``versions.serves``): ``cad doctor --check``
    writes nothing, and never holds a lock a server starting that instant needs."""

    REAL_SERVERS = True

    def test_asking_whether_a_server_runs_makes_and_takes_nothing(self) -> None:
        from cad_server.cli import doctor

        self.legacy()
        self.data(X)
        self.assertFalse(versions.serves(X))
        with mock.patch.object(places, "lock", side_effect=AssertionError("a lock taken")):
            said = doctor._versions()
        self.assertFalse(self.engines.exists(), "no engine folder made")
        self.assertTrue(any(line.startswith("legacy ") for line in said), said)
        folder = places.engine_dir(X)
        folder.mkdir(parents=True)
        (folder / "engine.lock").write_text("", encoding="utf-8")  # a lock file and no door: no server answers
        with mock.patch.object(places, "lock", side_effect=AssertionError("no lock taken")):
            self.assertFalse(versions.serves(X))


class ServerDecisions(Device):
    """What the servers decide by, at the cheapest level: no server runs (``test_version_servers`` runs them)."""

    def test_connected_means_work_in_flight_and_a_server_that_cannot_say_is_connected(self) -> None:
        for answer, expected in (({"ok": True, "working": False}, False), ({"ok": True, "working": True}, True),
                                 (None, True), ({"failed": "unknown request 'working'"}, True)):
            with self.subTest(answer=answer), mock.patch.object(versions, "ask", return_value=answer) as asked:
                self.assertEqual(versions.connected(X), expected)
                asked.assert_called_once_with(X, {"op": "working"})

    def test_the_flat_door_is_held_by_the_version_installations_current_names(self) -> None:
        for name in (X, Y):
            self.present(name)
        self.assertEqual((versions.flat(X), versions.flat(Y)), (False, False), "none named: no version holds it")
        self.assertTrue(installations.mirror(X))
        self.assertEqual((versions.flat(X), versions.flat(Y), versions.flat(None)), (True, False, False))
        self.assertEqual(installations.current()["prefix"], str(places.code_dir(X) / "server"),
                         "the record a client of 0.11.10 starts the server by")
        self.assertFalse(installations.mirror(Z), "not installed: nothing written")
        self.assertEqual(installations.current_version(), X)

    def test_a_development_build_is_newer_than_its_release(self) -> None:
        build = "0.12.0-dev.20261113120000"
        self.assertTrue(versions.older("0.12.0", build))
        self.assertTrue(versions.older(build, "0.12.1"))
        self.assertTrue(versions.older(build, "0.12.0-dev.20261114120000"))
        self.assertFalse(versions.older(build, "0.12.0"))

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


class TelemetryAcrossVersions(Device):
    """A no is a no everywhere (``analytics.everywhere``, ``inherit_no``)."""

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
        self.assertEqual((x["choice"], "id" in x, "forget" in x), ("off", False, False),
                         "its id deleted there, and its deletion asked for at once (``everywhere``'s ``forget``)")
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
        imports.ensure(Y)
        self.assertTrue(self.sharing(Y), "the yes is newer than the device's no")

    def test_a_read_only_report_heeds_the_device_s_no_without_writing_it(self) -> None:
        # E7: cad doctor --check (``status(keep=False)``) writes nothing, the device's no in force all the same.
        import time

        told = {"telemetry": {"choice": "on", "disclosure": 1, "by": "cli", "decidedAt": time.time() - 60, "id": "an-id"}}
        settings = self.data(X, told) / "settings.json"
        before = settings.read_bytes()
        device = {"telemetry": {"choice": "off", "disclosure": 1, "by": "cli", "decidedAt": time.time()}}
        (self.state / "settings.json").write_text(json.dumps(device), encoding="utf-8")
        self.assertFalse(self.sharing(X))
        self.assertEqual(settings.read_bytes(), before, "nothing written")

    def test_a_no_said_through_0_11_10_after_the_import_is_this_version_s_no_and_nothing_is_sent(self) -> None:
        """The default stays on 0.11.10 (automatic updates off), a store's copy at a newer version imports its settings
        with sharing on, and the person runs `cad telemetry off`, which 0.11.10 answers, writing the state folder's
        settings alone: the version honours it from its next count or send, and sends nothing."""
        import time

        from cad_server import analytics

        told = {"telemetry": {"choice": "on", "disclosure": 1, "by": "cli", "decidedAt": time.time() - 60, "id": "an-id",
                              "notifiedAt": 1.0, "notice": 1}}
        self.data(X, told)
        self.assertTrue(self.sharing(X))
        sent: list = []
        kept = {"answer": [told["telemetry"]["decidedAt"], 1.0], "batch": {"schema": 11, "batch": "b"}}
        (places.data_dir(X) / analytics.KEPT).write_text(json.dumps(kept) + "\n", encoding="utf-8")
        with mock.patch.object(places, "versioned", return_value=X), \
                mock.patch("cad_server._internal.channel._source_tree", return_value=False), \
                mock.patch.dict(os.environ, {"CI": "", "DO_NOT_TRACK": "", "CAD_TELEMETRY": ""}):
            recorder = analytics.Recorder(process="viewer", send=lambda payload: sent.append(payload) or True)
            recorder.viewed()  # counted under the answer it imported
            # 0.11.10's `cad telemetry off`: its own settings file, the state folder's, and nothing else.
            device = {"telemetry": {"choice": "off", "disclosure": 1, "by": "cli", "decidedAt": time.time()}}
            (self.state / "settings.json").write_text(json.dumps(device), encoding="utf-8")
            recorder.flush()
            recorder.close()
        self.assertEqual(sent, [], "neither what it noted nor the batch it kept is sent")
        self.assertFalse(self.sharing(X))
        x = json.loads((places.data_dir(X) / "settings.json").read_text(encoding="utf-8"))["telemetry"]
        self.assertEqual((x["choice"], "id" in x, x["forget"]), ("off", False, ["an-id"]), "its id owed a deletion")
        self.assertFalse((places.data_dir(X) / analytics.KEPT).exists())
        # A yes said in the version afterwards is newer than the device's no: its own, kept.
        with mock.patch.object(places, "versioned", return_value=X):
            analytics.choose(True, by="cli")
        self.assertTrue(self.sharing(X))


class TokenRotatedEverywhere(Device):
    def test_every_version_s_data_and_the_state_folder_take_the_new_token_and_every_running_server_is_told(self) -> None:
        """``cad server --rotate-token`` acts on the device: every version a server reads the token from, and the state
        folder 0.11.10 and earlier read it from, get the new one; each running server is told to take it at once,
        and one that cannot be told is said."""
        import secrets

        from cad_server.engine import daemon

        before = secrets.token_urlsafe(32)
        for name in (X, Y):
            self.data(name)
            registry.Registry(places.data_dir(name)).put_token(before)
        registry.Registry(self.state).put_token(before)
        self.present(Z)  # never started: it imports the new token as it starts
        self.serving(X)
        self.serving(Y)
        asked: list = []

        def ask(name, message, **_kwargs):
            asked.append((name, message))
            return {"ok": True} if name == X else {"failed": "unknown request 'token'"}

        said: list[str] = []
        with mock.patch.object(versions, "ask", side_effect=ask), \
                mock.patch.object(versions, "ask_flat", return_value={"failed": "unknown request 'token'"}), \
                mock.patch.object(places, "versioned", return_value=X):
            token = daemon.rotate_token(told=said.append)
        self.assertNotEqual(token, before)
        for root in (places.data_dir(X), places.data_dir(Y), self.state):
            self.assertEqual(registry.Registry(root).token(), token, root)
        self.assertFalse((places.data_dir(Z) / registry.TOKEN).exists(), "a version not started writes nothing")
        self.assertEqual(asked, [(X, {"op": "token"}), (Y, {"op": "token"})], "each running server told")
        self.assertTrue(any(line.startswith(f"cad {Y}'s server could not take the new token") for line in said), said)
        self.assertTrue(any("0.11.10 or earlier" in line for line in said), said)


class DoctorReadsEveryVersion(Device):
    """``cad doctor`` is the one command that reads every version installed."""

    def test_each_version_its_server_its_last_use_and_when_the_cleanup_takes_it(self) -> None:
        from cad_server.cli import doctor

        now = time.time()
        for name in (X, Y, Z):
            self.data(name)
        self.aged(X, installed=now - 30 * DAY, used=now - 3 * DAY)
        self.aged(Y, installed=now - 30 * DAY, used=now - 60)
        (places.code_dir("0.11.99")).mkdir(parents=True)  # an install cut short
        self.serving(Z)
        with mock.patch.object(versions, "serving", return_value=4000):
            said = doctor._versions()

        def line(start: str) -> str:
            found = [each for each in said if each.startswith(start)]
            self.assertEqual(len(found), 1, said)
            return found[0]

        self.assertIn("not completely installed", line("version  cad 0.11.99 "))
        self.assertIn("its server is not running; last used ", line(f"version  cad {X} "))
        self.assertIn("(at its next cleanup)", line(f"version  cad {X} "))
        self.assertIn(f"cad {Z}'s server removes it once it has gone unused for 2 days (in ",
                      line(f"version  cad {Y} "))
        self.assertIn("its server runs, pages on port 4000", line(f"version  cad {Z} "))
        self.assertIn("the newest: a command with no pin runs it", line(f"version  cad {Z} "))


if __name__ == "__main__":
    unittest.main()
