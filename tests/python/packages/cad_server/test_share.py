"""``cad share``, the client's half of the share protocol, run against a stand-in service written here that speaks
its API (``PUT`` and ``DELETE /v1/shares/<id>``: its statuses, the two hashes kept, an upload again replacing, a
delete by either secret), storing what it is sent, and an engine of this file's own that writes each view bundle.

What it holds the command to: the archive is ``cad-share/1`` and the same bytes for the same bundle (the bundle
``cad stl export SRC DST.view`` writes, packed); the first share is refused, naming ``--yes``, and ``--yes`` shares
and records the agreement; ``cad share off`` refuses even with ``--yes``; sharing again keeps the link and starts the
expiry again; a 403 on the record's id makes a new share; a delete works from the record and from a delete link;
``--json``'s shape; no key or secret anywhere but inside the two links and the record (no other output, no file of
the engine's, the state's or the cache's); a connection refused, or refused by something that is not the service,
said in one line; a KiCad board and a folder refused. The fixtures are made in a temporary folder.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import socket
import stat
import sys
import tarfile
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from tests.python.support import engine_daemon
from tests.python.support.paths import SOURCE_PATH, add_sources

add_sources()

ID = re.compile(r"[A-Za-z0-9_-]{22}")
SECRET = re.compile(r"[A-Za-z0-9_-]{43}")
HASH = re.compile(r"[0-9a-f]{64}")

# A tetrahedron, as an ASCII STL.
STL = """solid tetra
facet normal 0 0 -1
 outer loop
  vertex 0 0 0
  vertex 0 10 0
  vertex 10 0 0
 endloop
endfacet
facet normal 0 -1 0
 outer loop
  vertex 0 0 0
  vertex 10 0 0
  vertex 0 0 10
 endloop
endfacet
facet normal -1 0 0
 outer loop
  vertex 0 0 0
  vertex 0 0 10
  vertex 0 10 0
 endloop
endfacet
facet normal 0.577 0.577 0.577
 outer loop
  vertex 10 0 0
  vertex 0 10 0
  vertex 0 0 10
 endloop
endfacet
endsolid tetra
"""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()


class Service:
    """The share service's API as the protocol says it, in memory: ``shares`` by id, each its stored body, its two
    hashes, its key and its expiry; every request seen (``seen``). Each upload's expiry is a second later than the
    one before, as if time passed between them."""

    def __init__(self, limit: int = 25 * 1024 * 1024) -> None:
        self.shares: dict[str, dict[str, Any]] = {}
        self.seen: list[tuple[str, str, dict[str, str]]] = []
        self.limit = limit
        self.uploads = 0
        self.races = 0  # how many PUTs to answer 409 next: a create that lost its race
        self.lock = threading.Lock()
        service = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def answer(self, status: int, body: dict[str, Any] | None = None) -> None:
                data = b"" if body is None else json.dumps(body).encode()
                self.send_response(status)
                if body is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def refuse(self, status: int, error: str, hint: str = "") -> None:
                self.answer(status, {"error": error, "hint": hint})

            def share_id(self) -> str | None:
                match = re.fullmatch(r"/v1/shares/([^/]+)", self.path)
                return match.group(1) if match and ID.fullmatch(match.group(1)) else None

            def bearer(self) -> str | None:
                given = self.headers.get("Authorization") or ""
                return given[len("Bearer "):] if given.startswith("Bearer ") else None

            def do_PUT(self) -> None:  # noqa: N802
                service.seen.append(("PUT", self.path, dict(self.headers)))
                ident, key, hashed = self.share_id(), self.headers.get("Cad-Share-Key") or "", \
                    self.headers.get("Cad-Delete-Hash") or ""
                if ident is None or not SECRET.fullmatch(key) or not HASH.fullmatch(hashed):
                    return self.refuse(400, "bad id, key or hash")
                write = self.bearer()
                if write is None:
                    return self.refuse(401, "no write secret")
                if self.headers.get("Content-Length") is None:
                    return self.refuse(411, "no length")
                length = int(self.headers["Content-Length"])
                body = self.rfile.read(length)
                if length > service.limit:
                    return self.refuse(413, "the archive is too large", f"at most {service.limit} bytes")
                if body[:2] != b"\x1f\x8b":
                    return self.refuse(400, "not gzip")
                with service.lock:
                    if service.races:
                        service.races -= 1
                        return self.refuse(409, "the share could not be made", "try again")
                    found = service.shares.get(ident)
                    if found is not None and found["write"] != _sha(write):
                        return self.refuse(403, "this share is another's")
                    service.uploads += 1
                    expires = (datetime(2030, 1, 1, tzinfo=timezone.utc) + timedelta(days=7, seconds=service.uploads))
                    service.shares[ident] = {"body": body, "write": _sha(write), "delete": hashed, "key": key,
                                             "expires": expires.strftime("%Y-%m-%dT%H:%M:%SZ")}
                self.answer(201 if found is None else 200,
                            {"id": ident, "expires": service.shares[ident]["expires"], "bytes": len(body) + 28})

            def do_DELETE(self) -> None:  # noqa: N802
                service.seen.append(("DELETE", self.path, dict(self.headers)))
                ident, secret = self.share_id(), self.bearer()
                if ident is None:
                    return self.refuse(400, "bad id")
                with service.lock:
                    found = service.shares.get(ident)
                    if found is None:
                        return self.refuse(404, "no such share")
                    if secret is None or _sha(secret) not in (found["write"], found["delete"]):
                        return self.refuse(403, "that secret deletes nothing here")
                    del service.shares[ident]
                self.answer(204)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.http.shutdown()
        self.http.server_close()


class NotTheService:
    """What a proxy that refuses a host answers: a 403 with a page, no JSON."""

    def __init__(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_PUT(self) -> None:  # noqa: N802
                self.send_response(403)
                page = b"<html>blocked by policy</html>"
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.http.shutdown()
        self.http.server_close()


class ShareTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.given = engine_daemon.isolate(cls.addClassCleanup)  # an engine, a state and a cache of this file's own
        cls.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="share-")))
        cls.addClassCleanup(shutil.rmtree, cls.base, True)
        cls.service = Service()
        cls.addClassCleanup(cls.service.close)
        (cls.base / "tetra.stl").write_text(STL, encoding="utf-8")
        (cls.base / "other.stl").write_text(STL.replace("tetra", "other"), encoding="utf-8")
        (cls.base / "board.kicad_pcb").write_text("(kicad_pcb (version 20240108))\n", encoding="utf-8")
        (cls.base / "parts").mkdir()
        cls.state = Path(cls.given["CAD_STATE_DIR"])

    def setUp(self) -> None:
        from cad_server.settings import write_section

        (self.state / "shares.json").unlink(missing_ok=True)
        write_section("share", None, path=self.state / "settings.json")
        with self.service.lock:
            self.service.shares.clear()

    def env(self, **more: str) -> dict[str, str]:
        return {**os.environ, "PYTHONPATH": SOURCE_PATH, "CAD_SHARE_URL": self.service.url, "CAD_TELEMETRY": "0",
                "CAD_UPDATE_CHECK": "0", "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
                **more}

    def cad(self, *args: str, **more: str) -> Any:
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", "share", *args], env=self.env(**more),
                                 cwd=self.base)

    def shared(self, *args: str, target: str = "tetra.stl", **more: str) -> dict[str, Any]:
        done = self.cad(target, "--yes", "--json", *args, **more)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(len(done.stdout.splitlines()), 1, done.stdout)
        return json.loads(done.stdout)

    def records(self) -> list[dict[str, Any]]:
        return json.loads((self.state / "shares.json").read_text(encoding="utf-8"))["shares"]

    # --- the archive ---------------------------------------------------------------------------------------------

    def test_the_archive_is_the_protocols_and_the_same_bytes_each_time(self) -> None:
        from cad_server import sharing

        folder = self.base / "made.view"
        exported = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "stl", "export", "tetra.stl",
                                      str(folder)], env=self.env(), cwd=self.base)
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        (folder / "thumbnail.png").write_bytes(b"\x89PNG an earlier picture")
        body, paths = sharing.archive(folder)
        self.assertEqual(body, sharing.archive(folder)[0])
        self.assertEqual(body[:4], b"\x1f\x8b\x08\x00")  # gzip, deflate, no flags: no file name
        self.assertEqual(body[4:8], b"\x00\x00\x00\x00")  # gzip's mtime 0
        expected = sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*")
                          if path.is_file() and path.name != "thumbnail.png")
        self.assertEqual(paths, expected)
        self.assertIn("manifest.json", paths)
        raw = gzip.decompress(body)
        self.assertEqual(raw[257:263], b"ustar\x00")
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
            members = tar.getmembers()
            self.assertEqual([member.name for member in members], expected)
            for member in members:
                self.assertTrue(member.isreg(), member.name)
                self.assertEqual((member.mtime, member.mode, member.uid, member.gid, member.uname, member.gname),
                                 (0, 0o644, 0, 0, "", ""), member.name)
                self.assertEqual(tar.extractfile(member).read(), (folder / member.name).read_bytes())

        # What the command uploads is that archive of the bundle the engine writes.
        self.shared()
        (stored,) = self.service.shares.values()
        self.assertEqual(stored["body"], body)

        # A path that does not fit a ustar header is refused, not written another way; one that splits fits.
        deep = self.base / "deep.view"
        (deep / ("d" * 150) / ("n" * 99)).parent.mkdir(parents=True)
        (deep / "manifest.json").write_text("{}", encoding="utf-8")
        (deep / ("d" * 150) / ("n" * 99)).write_text("fits", encoding="utf-8")
        self.assertEqual(len(sharing.archive(deep)[1]), 2)
        (deep / ("d" * 150) / ("n" * 101)).write_text("too long", encoding="utf-8")
        with self.assertRaisesRegex(sharing.Unsharable, "does not fit"):
            sharing.archive(deep)

    # --- agreeing, and the setting -------------------------------------------------------------------------------

    def test_the_first_share_is_refused_naming_yes_and_yes_shares_and_records(self) -> None:
        refused = self.cad("tetra.stl")
        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertEqual(refused.stdout, "")
        words = refused.stderr
        for said in ("cad share tetra.stl --yes", "never its code or the CAD file", "the file itself",
                     self.service.url, "anyone with the link", "7 days", "delete link", "Ask the person"):
            self.assertIn(said, words)
        self.assertEqual(self.service.shares, {})
        as_json = json.loads(self.cad("tetra.stl", "--json").stdout)
        self.assertEqual((as_json["ok"], as_json["reason"], as_json["userActionRequired"], as_json["next"]),
                         (False, "confirmation_required", True, ["cad share tetra.stl --json --yes"]))
        self.assertEqual(self.service.shares, {})

        done = self.cad("tetra.stl", "--yes")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(len(lines), 4, done.stdout)
        self.assertRegex(lines[0], r"^Shared tetra\.stl, an STL: the file itself, [\d.]+ (B|KiB) uploaded; no code")
        self.assertRegex(lines[1], rf"^View: +{re.escape(self.service.url)}/[A-Za-z0-9_-]{{22}}#key=[A-Za-z0-9_-]{{43}}$")
        self.assertRegex(lines[2], rf"^Delete: +{re.escape(self.service.url)}/[A-Za-z0-9_-]{{22}}#delete=")
        self.assertRegex(lines[3], r"^Expires: 2030-01-08 00:00 UTC, 7 days after this share")
        (ident,) = self.service.shares
        (record,) = self.records()
        self.assertEqual(record["id"], ident)
        self.assertEqual(self.service.shares[ident]["key"], record["key"])
        # Each hash is of the secret's 43-character text, not of the bytes it decodes to.
        self.assertEqual(self.service.shares[ident]["delete"], hashlib.sha256(record["delete"].encode()).hexdigest())
        self.assertEqual(self.service.shares[ident]["write"], hashlib.sha256(record["write"].encode()).hexdigest())
        self.assertEqual(record["document"]["path"], str(self.base / "tetra.stl"))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((self.state / "shares.json").stat().st_mode), 0o600)
        # Agreed once: another document needs no --yes.
        again = self.cad("other.stl")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(len(self.service.shares), 2)

    def test_off_refuses_even_with_yes_until_on(self) -> None:
        off = self.cad("off")
        self.assertEqual(off.returncode, 0, off.stdout + off.stderr)
        refused = self.cad("tetra.stl", "--yes", "--json")
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertEqual(json.loads(refused.stdout)["reason"], "declined")
        self.assertIn("cad share on", json.loads(refused.stdout)["error"])
        self.assertEqual(self.service.shares, {})
        self.assertEqual(json.loads(self.cad("status", "--json").stdout)["sharing"], "off")
        self.assertEqual(self.cad("on").returncode, 0)
        self.shared()
        self.assertEqual(len(self.service.shares), 1)

    def test_the_setting_is_written_here_where_no_server_runs(self) -> None:
        empty = tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
        self.addCleanup(shutil.rmtree, empty, True)
        self.assertEqual(self.cad("off", CAD_ENGINE_DIR=empty).returncode, 0)
        status = json.loads(self.cad("status", "--json", CAD_ENGINE_DIR=empty).stdout)
        self.assertEqual((status["sharing"], status["agreed"], status["service"]), ("off", False, self.service.url))

    # --- again, and a 403 ----------------------------------------------------------------------------------------

    def test_sharing_again_keeps_the_link_and_starts_the_expiry_again(self) -> None:
        first = self.shared()
        second = self.shared()
        self.assertEqual((second["view"], second["delete"], second["id"]), (first["view"], first["delete"], first["id"]))
        self.assertEqual((first["again"], second["again"]), (False, True))
        self.assertGreater(second["expires"], first["expires"])
        self.assertEqual(len(self.service.shares), 1)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.records()[0]["expires"], second["expires"])

    def test_a_403_on_the_records_id_makes_a_new_share(self) -> None:
        first = self.shared()
        self.service.shares[first["id"]]["write"] = _sha("another computer's write secret")
        second = self.shared()
        self.assertNotEqual(second["id"], first["id"])
        self.assertNotEqual(second["view"], first["view"])
        self.assertFalse(second["again"])
        (record,) = self.records()
        self.assertEqual(record["id"], second["id"])

    # --- delete --------------------------------------------------------------------------------------------------

    def test_delete_from_the_record_and_from_a_delete_link(self) -> None:
        first = self.shared()
        asked = self.cad("delete", "tetra.stl", "--json")
        self.assertEqual((asked.returncode, json.loads(asked.stdout)["reason"]), (2, "confirmation_required"))
        self.assertIn(first["id"], self.service.shares)
        done = self.cad("delete", "tetra.stl", "--yes")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Deleted the share of tetra.stl", done.stdout)
        self.assertEqual(self.service.shares, {})
        self.assertEqual(self.records(), [])
        missing = self.cad("delete", "tetra.stl", "--yes", "--json")
        self.assertEqual((missing.returncode, json.loads(missing.stdout)["reason"]), (2, "not_found"))

        second = self.shared()
        by_link = self.cad("delete", second["delete"], "--yes", "--json")
        self.assertEqual(by_link.returncode, 0, by_link.stdout + by_link.stderr)
        self.assertEqual(json.loads(by_link.stdout)["deleted"], True)
        self.assertEqual(self.service.shares, {})
        self.assertEqual(self.records(), [])
        gone = self.cad("delete", second["delete"], "--yes")
        self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
        self.assertIn("gone already", gone.stdout)

    # --- what it says --------------------------------------------------------------------------------------------

    def test_the_json_answers_shapes(self) -> None:
        found = self.shared()
        self.assertEqual(set(found), {"ok", "view", "delete", "expires", "id", "again", "document", "sent", "kept"})
        self.assertEqual((found["ok"], found["kept"]), (True, True))
        self.assertEqual(found["document"]["kind"], "stl")
        self.assertEqual(found["document"]["name"], "tetra.stl")
        self.assertEqual(set(found["sent"]), {"what", "without", "parts", "files", "bytes", "format", "code",
                                              "cad_file"})
        self.assertEqual((found["sent"]["format"], found["sent"]["code"], found["sent"]["cad_file"]),
                         ("cad-share/1", False, True))
        self.assertEqual(found["sent"]["bytes"], len(self.service.shares[found["id"]]["body"]))
        status = json.loads(self.cad("status", "--json").stdout)
        self.assertEqual(set(status), {"ok", "sharing", "agreed", "service", "shares"})
        self.assertEqual((status["sharing"], status["agreed"]), ("on", True))
        self.assertEqual(status["shares"], [{"document": found["document"], "view": found["view"],
                                             "delete": found["delete"], "expires": found["expires"]}])

    def test_no_key_or_secret_but_in_the_links_and_the_record(self) -> None:
        said = []
        for args in (("tetra.stl", "--yes"), ("tetra.stl", "--yes", "--json"), ("status",), ("status", "--json")):
            done = self.cad(*args)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            said += [done.stdout, done.stderr]
        (record,) = self.records()
        deleted = self.cad("delete", "tetra.stl", "--yes")
        said += [deleted.stdout, deleted.stderr]
        text = "\n".join(said)
        self.assertIn(record["view"], text)
        bare = text.replace(record["view"], "").replace(record["remove"], "")
        for name in ("key", "write", "delete"):
            self.assertNotIn(record[name], bare, name)
        self.assertNotIn(record["write"], text)
        # Nor in any file of the engine's, the state's (but the records) or the cache's: its logs, its telemetry.
        # The engine's lock is the one file passed over: the running engine holds its first byte locked, which
        # Windows will not let another process read, and it holds no byte of a share (``places.lock``).
        from cad.engine import places

        locked = Path(self.given["CAD_ENGINE_DIR"]) / f"{places.NAME}.lock"
        for folder in (self.given["CAD_ENGINE_DIR"], self.given["CAD_STATE_DIR"], self.given["CAD_CACHE_DIR"]):
            for path in Path(folder).rglob("*"):
                if path.is_file() and path.name != "shares.json" and path != locked:
                    data = path.read_bytes()
                    for name in ("key", "write", "delete"):
                        self.assertNotIn(record[name].encode(), data, f"{name} in {path}")

    def test_a_refused_connection_and_a_refusal_not_the_services_say_the_network(self) -> None:
        self.assertEqual(self.cad("on").returncode, 0)
        closed = socket.socket()
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
        closed.close()
        refused = self.cad("tetra.stl", "--yes", CAD_SHARE_URL=f"http://127.0.0.1:{port}")
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        lines = [line for line in refused.stderr.splitlines() if line.startswith("cad share:")]
        self.assertEqual(len(lines), 1, refused.stderr)
        self.assertIn("the network here does not reach the share service", lines[0])
        self.assertIn(f"must allow 127.0.0.1:{port}", lines[0])
        proxy = NotTheService()
        self.addCleanup(proxy.close)
        blocked = self.cad("tetra.stl", "--json", CAD_SHARE_URL=proxy.url)
        self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
        error = json.loads(blocked.stdout)["error"]
        self.assertIn("the network here does not reach the share service", error)
        self.assertIn("HTTP 403", error)

    def test_the_services_refusal_is_shown_with_its_hint(self) -> None:
        self.service.limit = 10
        self.addCleanup(setattr, self.service, "limit", 25 * 1024 * 1024)
        done = self.cad("tetra.stl", "--yes")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("the share service refused the upload (413): the archive is too large; at most 10 bytes",
                      done.stderr)

    def test_a_lost_race_is_tried_once_more_then_said(self) -> None:
        self.service.races = 1
        self.assertEqual(len(self.service.shares), 0)
        self.shared()
        self.assertEqual((self.service.races, len(self.service.shares)), (0, 1))
        self.service.races = 2
        self.addCleanup(setattr, self.service, "races", 0)
        done = self.cad("other.stl", "--yes")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("refused the upload (409): the share could not be made; try again", done.stderr)
        self.assertEqual(len(self.service.shares), 1)

    def test_a_kicad_board_and_a_folder_are_refused(self) -> None:
        for target, said, reason in (("board.kicad_pcb", "a KiCad board, which has no view bundle yet", "wrong_type"),
                                     ("parts", "is a folder, which has no view bundle", "wrong_type"),
                                     ("nothere.stl", "no such file: nothere.stl", "not_found")):
            done = self.cad(target, "--yes", "--json")
            self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
            found = json.loads(done.stdout)
            self.assertEqual(found["reason"], reason)
            self.assertIn(said, found["error"])
        self.assertEqual(self.service.shares, {})


if __name__ == "__main__":
    unittest.main()
