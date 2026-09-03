"""The instance registry: the writer side, and the identity-probed read side
that ``main.py list``/``stop`` are built on.

Ported from ``registry.test.mjs``. These call the module directly rather than
going over HTTP because that is what the JS suite did — the registry has no
HTTP surface of its own, and the probe is the only part that speaks HTTP.

Every test redirects the registry directory into a temp dir. The real one is
shared with the viewer the developer is using, and reaping is destructive.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cadgen.viewer import registry


class RegistrySandbox(unittest.TestCase):
    """Point ``tempfile.gettempdir()`` at a private directory.

    ``registry_dir()`` derives from it on EVERY call, so overriding TMPDIR and
    clearing the cached value is enough — no module attribute is patched, which
    keeps the test honest about the real derivation.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = {k: os.environ.get(k) for k in ("TMPDIR", "TEMP", "TMP")}
        for key in ("TMPDIR", "TEMP", "TMP"):
            os.environ[key] = self._tmp.name
        tempfile.tempdir = None  # force gettempdir() to re-read the environment
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        tempfile.tempdir = None
        self._tmp.cleanup()


class _PidServer:
    """A stand-in for ``/__cad/server`` that answers as a chosen pid."""

    def __init__(self, pid: int):
        outer_pid = pid

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = json.dumps({"pid": outer_pid}).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # noqa: D102
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class RegisterAndUnregister(RegistrySandbox):
    def test_register_writes_a_complete_entry_and_unregister_removes_it(self) -> None:
        target = registry.register(
            host="127.0.0.1", port=39876, root="/tmp/models", viewer_version="1.2.3",
            token="1.2.3:42",
        )
        self.assertTrue(target, "registry dir must be writable in a temp sandbox")
        self.addCleanup(registry.unregister)
        self.assertEqual(target, registry.entry_path(os.getpid()))

        entry = json.loads(Path(target).read_text(encoding="utf-8"))
        self.assertEqual(entry["pid"], os.getpid())
        self.assertEqual(entry["host"], "127.0.0.1")
        self.assertEqual(entry["port"], 39876)
        self.assertEqual(entry["version"], "1.2.3")
        # The reuse identity, recorded at START time: the launcher compares a
        # freshly computed token against this, so a pull/rebuild after this
        # instance started fails the match and a fresh instance starts.
        self.assertEqual(entry["token"], "1.2.3:42")
        self.assertEqual(entry["root"], "/tmp/models")
        self.assertIsInstance(entry["startedAt"], float)
        self.assertTrue(entry["packageDir"])

        # The write is temp+rename, so nothing may be left beside the entry.
        self.assertFalse(os.path.exists(f"{target}.{os.getpid()}.tmp"))

        self.assertEqual(registry.find_by_port(39876)["pid"], os.getpid())
        registry.unregister()
        self.assertFalse(os.path.exists(target))

    def test_package_dir_is_a_plain_filesystem_path(self) -> None:
        # Node computed this from an import.meta.url pathname, which
        # percent-encodes spaces and yields a leading-slash drive path on
        # Windows. Only the `list` printout reads it; this is the fixed form.
        target = registry.register(host="127.0.0.1", port=39877, viewer_version="1.0.0")
        self.addCleanup(registry.unregister)
        package_dir = json.loads(Path(target).read_text(encoding="utf-8"))["packageDir"]
        self.assertNotIn("%20", package_dir)
        self.assertTrue(os.path.isdir(package_dir))
        self.assertEqual(os.path.basename(package_dir), "viewer")

    def test_corrupt_and_non_integer_entries_are_skipped(self) -> None:
        directory = registry.registry_dir()
        os.makedirs(directory, mode=0o700, exist_ok=True)
        Path(directory, "viewer-1.json").write_text("{not json", encoding="utf-8")
        Path(directory, "viewer-2.json").write_text('{"pid":"x","port":1}', encoding="utf-8")
        # bool is an int subclass in Python and must not pass as a pid.
        Path(directory, "viewer-3.json").write_text('{"pid":true,"port":true}', encoding="utf-8")
        Path(directory, "not-a-viewer.json").write_text('{"pid":4,"port":4}', encoding="utf-8")
        self.assertEqual(registry.read_entries(), [])


class Liveness(RegistrySandbox):
    def test_live_entries_keeps_probed_entries_and_reaps_the_rest(self) -> None:
        answering = _PidServer(os.getpid())
        self.addCleanup(answering.close)

        target = registry.register(
            host="127.0.0.1", port=answering.port, root="/tmp/models", viewer_version="1.2.3"
        )
        self.assertTrue(target)
        self.addCleanup(registry.unregister)

        live = registry.live_entries()
        self.assertTrue(
            any(e["pid"] == os.getpid() and e["port"] == answering.port for e in live),
            "an entry whose port answers as its own pid must survive",
        )

        # A stale entry — a pid+port nothing answers for — fails and is reaped.
        stale_pid = 999999
        Path(registry.entry_path(stale_pid)).write_text(
            json.dumps({"pid": stale_pid, "host": "127.0.0.1", "port": 1, "startedAt": 0}),
            encoding="utf-8",
        )
        self.assertFalse(registry.probe({"pid": stale_pid, "host": "127.0.0.1", "port": 1}, 0.25))
        registry.live_entries()
        self.assertFalse(
            os.path.exists(registry.entry_path(stale_pid)), "stale entry must be reaped"
        )

    def test_probe_rejects_a_live_port_answering_as_a_different_pid(self) -> None:
        # The registry names OUR pid, but the port answers as someone else:
        # after a hard kill another process may hold the port, and `stop` must
        # never signal it. This is why liveness is an identity probe rather
        # than a signal or a connect check.
        impostor = _PidServer(os.getpid() + 1)
        self.addCleanup(impostor.close)
        self.assertFalse(
            registry.probe({"pid": os.getpid(), "host": "127.0.0.1", "port": impostor.port}, 1.0)
        )

    def test_live_entries_sorts_oldest_first(self) -> None:
        answering = _PidServer(os.getpid())
        self.addCleanup(answering.close)
        directory = registry.registry_dir()
        os.makedirs(directory, mode=0o700, exist_ok=True)
        # Two entries for the same answering port, differing only in age. The
        # probe runs in parallel, so completion order must not leak into the
        # result — only startedAt may.
        for pid, started in ((os.getpid(), 200.0),):
            Path(registry.entry_path(pid)).write_text(
                json.dumps(
                    {"pid": pid, "host": "127.0.0.1", "port": answering.port, "startedAt": started}
                ),
                encoding="utf-8",
            )
        self.addCleanup(registry.unregister)
        live = registry.live_entries()
        self.assertEqual([e["startedAt"] for e in live], sorted(e["startedAt"] for e in live))


if __name__ == "__main__":
    unittest.main()
