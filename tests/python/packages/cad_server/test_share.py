"""``cad share``, the client's half of the share protocol (``cad-share/2``), run against a stand-in service written
here that speaks its API and holds a client to it -- a pack named by the SHA-256 of its body, the owner and its two
hashes made by the first write and a write of another secret refused, a manifest of the protocol's shape, a commit's
409 naming the packs it lacks, a commit that another replaced meanwhile refused, the packs neither manifest names
deleted, a delete by either secret -- storing what it is sent, and an engine of this file's own that writes each view
bundle.

What it holds the command to: the first share is refused, naming ``--yes``, and ``--yes`` shares and records the
agreement; ``cad share off`` refuses even with ``--yes``; a first share sends every file of the bundle the engine
wrote, and the cache keeps the bundle and where each file lives; sharing again keeps the link, starts the expiry again
and sends only what changed (nothing, for a document unchanged); a 403, a record of ``cad-share/1``'s and an expired
record each make a new share; one ``cad share`` of a document at a time; a delete works from the record and from a
link, and removes the document's folder in the cache; what travelled in words and in ``--json``; no secret in any
request's address, error or file but the record, and the view link only in the output and the record; a connection
refused, or refused by something that is not the service, said in one line; a KiCad board and a folder refused. And,
with no engine, what is sent: the files a bundle's manifest lists as gzip members in reading order, in packs closed at
4 MiB with a file split over two, a 409 naming missing packs sending their files again (twice at most), one naming
none committing again once, and a 429 waited out. The fixtures are made in a temporary folder.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import SOURCE_PATH, add_sources

add_sources()

ID = re.compile(r"[A-Za-z0-9_-]{22}")
SECRET = re.compile(r"[A-Za-z0-9_-]{43}")
HASH = re.compile(r"[0-9a-f]{64}")
MIB = 1024 * 1024
NO_PROXY = {"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}

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


def _sha(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("ascii") if isinstance(data, str) else data).hexdigest()


def _judged(found: Any) -> str | None:
    """Why ``found`` is no share manifest of the protocol's shape, or None for one that is."""
    if not isinstance(found, dict) or found.get("format") != "cad-share/2" or not isinstance(found.get("files"), dict):
        return "not a cad-share/2 manifest"
    files = found["files"]
    if "manifest.json" not in files or "thumbnail.png" in files or len(files) > 200_000:
        return "its files are not a bundle's"
    for path, entry in files.items():
        if not path or len(path.encode("utf-8")) > 1024 or any(part in ("", ".", "..") for part in path.split("/")):
            return f"{path!r} is no path"
        if not isinstance(entry, dict) or set(entry) != {"sha256", "bytes", "at"} \
                or not HASH.fullmatch(str(entry["sha256"])) or type(entry["bytes"]) is not int or entry["bytes"] < 0:
            return f"{path}: not its sha256, bytes and at"
        at = entry["at"]
        if not isinstance(at, list) or not at or not all(
                isinstance(piece, list) and len(piece) == 3 and HASH.fullmatch(str(piece[0]))
                and type(piece[1]) is int and type(piece[2]) is int and piece[1] >= 0 and piece[2] > 0
                for piece in at):
            return f"{path}: at is not [[pack, offset, length], ...]"
    return None


class Service:
    """The share service's API as the protocol says it, in memory: ``shares`` by id, each its ``owner`` (the two hashes
    the first write made), its ``packs`` by pack id, its ``manifest`` and the one it replaced, and its expiry; every
    request seen (``seen``: method, path, headers, when). Each commit's expiry is a second later than the one before,
    as if time passed between them. Its knobs: ``most_pack`` (the most a pack may be), ``limited`` (how many requests
    to answer 429 next, with ``Retry-After: retry_after``), ``conflicts`` (how many commits to refuse as if another
    replaced the manifest meanwhile) and ``losing`` (how many commits find every pack of their share gone)."""

    def __init__(self) -> None:
        self.shares: dict[str, dict[str, Any]] = {}
        self.seen: list[tuple[str, str, dict[str, str], float]] = []
        self.lock = threading.Lock()
        self.reset()
        service = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def answer(self, status: int, body: dict[str, Any] | None = None,
                       headers: dict[str, str] | None = None) -> None:
                data = b"" if body is None else json.dumps(body).encode()
                self.send_response(status)
                if body is not None:
                    self.send_header("Content-Type", "application/json")
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def refuse(self, status: int, error: str, hint: str = "", headers: dict[str, str] | None = None,
                       **more: Any) -> None:
                self.answer(status, {"error": error, "hint": hint, **more}, headers)

            def route(self) -> tuple[str | None, str | None]:
                match = re.fullmatch(r"/v1/shares/([^/]+)(?:/packs/([^/]+))?", self.path)
                if match is None or not ID.fullmatch(match.group(1)):
                    return None, None
                return match.group(1), match.group(2)

            def bearer(self) -> str | None:
                given = self.headers.get("Authorization") or ""
                secret = given[len("Bearer "):] if given.startswith("Bearer ") else ""
                return secret if SECRET.fullmatch(secret) else None

            def body(self) -> bytes | None:
                if self.headers.get("Content-Length") is None:
                    self.refuse(411, "length_required")
                    return None
                return self.rfile.read(int(self.headers["Content-Length"]))

            def owned(self, ident: str, write: str, hashed: str) -> dict[str, Any] | None:
                """The share, its owner made by this first write; None, refused, where another write secret made it."""
                share = service.shares.setdefault(ident, {"owner": None, "packs": {}, "manifest": None,
                                                          "replaced": None, "expires": None})
                if share["owner"] is None:
                    share["owner"] = {"write": _sha(write), "delete": hashed}
                elif share["owner"]["write"] != _sha(write):
                    self.refuse(403, "forbidden", "this share is another's")
                    return None
                return share

            def do_PUT(self) -> None:  # noqa: N802
                service.seen.append(("PUT", self.path, dict(self.headers), time.monotonic()))
                ident, pack = self.route()
                hashed = self.headers.get("Cad-Delete-Hash") or ""
                body = self.body()
                if body is None:
                    return None
                if ident is None or (pack is not None and not HASH.fullmatch(pack)) or not HASH.fullmatch(hashed):
                    return self.refuse(400, "bad_request", "a bad id, pack id or hash")
                write = self.bearer()
                if write is None:
                    return self.refuse(401, "unauthorized")
                with service.lock:
                    if service.limited:
                        service.limited -= 1
                        return self.refuse(429, "rate_limited", "too many", {"Retry-After": service.retry_after})
                    return self.pack(ident, pack, body, write, hashed) if pack is not None else \
                        self.commit(ident, body, write, hashed)

            def pack(self, ident: str, pack: str, body: bytes, write: str, hashed: str) -> None:
                if len(body) > service.most_pack:
                    return self.refuse(413, "too_large", f"at most {service.most_pack} bytes")
                if _sha(body) != pack:
                    return self.refuse(400, "bad_pack", "the body's SHA-256 is not its pack id")
                share = self.owned(ident, write, hashed)
                if share is None:
                    return None
                share["packs"][pack] = body
                return self.answer(201, {"pack": pack, "bytes": len(body) + 28})

            def commit(self, ident: str, body: bytes, write: str, hashed: str) -> None:
                if self.headers.get("Content-Type") != "application/json":
                    return self.refuse(400, "bad_manifest", "not JSON")
                try:
                    manifest = json.loads(body)
                except ValueError:
                    manifest = None
                why = _judged(manifest)
                if why is not None:
                    return self.refuse(400, "bad_manifest", why)
                share = self.owned(ident, write, hashed)
                if share is None:
                    return None
                service.commits += 1
                if service.losing:
                    service.losing -= 1
                    share["packs"].clear()
                named = {piece[0] for entry in manifest["files"].values() for piece in entry["at"]}
                missing = sorted(named - set(share["packs"]))
                if missing:
                    return self.refuse(409, "missing_packs", "upload them, then commit again", missing=missing)
                for path, entry in manifest["files"].items():
                    for pack, offset, length in entry["at"]:
                        if offset + length > len(share["packs"][pack]):
                            return self.refuse(400, "bad_manifest", f"{path} lies past the end of {pack}")
                if service.conflicts:
                    service.conflicts -= 1
                    return self.refuse(409, "conflict", "another commit replaced the share meanwhile: try again")
                replaced, share["replaced"], share["manifest"] = share["manifest"], share["manifest"], manifest
                kept = named | ({piece[0] for entry in replaced["files"].values() for piece in entry["at"]}
                                if replaced else set())
                share["packs"] = {name: data for name, data in share["packs"].items() if name in kept}
                expires = datetime(2030, 1, 1, tzinfo=timezone.utc) + timedelta(days=7, seconds=service.commits)
                share["expires"] = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
                return self.answer(201 if replaced is None else 200, {
                    "id": ident, "expires": share["expires"], "files": len(manifest["files"]),
                    "bytes": sum(len(share["packs"][name]) + 28 for name in named)})

            def do_DELETE(self) -> None:  # noqa: N802
                service.seen.append(("DELETE", self.path, dict(self.headers), time.monotonic()))
                ident, pack = self.route()
                if ident is None or pack is not None:
                    return self.refuse(400, "bad_request")
                secret = self.bearer()
                if secret is None:
                    return self.refuse(401, "unauthorized")
                with service.lock:
                    found = service.shares.get(ident)
                    if found is None or found["owner"] is None:
                        return self.refuse(404, "not_found")
                    if _sha(secret) not in (found["owner"]["write"], found["owner"]["delete"]):
                        return self.refuse(403, "forbidden", "that secret deletes nothing here")
                    del service.shares[ident]
                return self.answer(204)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def reset(self) -> None:
        with self.lock:
            self.shares.clear()
            self.seen.clear()
            self.most_pack, self.limited, self.retry_after = 8 * MIB, 0, "1"
            self.conflicts = self.losing = self.commits = 0

    def puts(self, kind: str) -> list[tuple[str, str, dict[str, str], float]]:
        """The PUTs seen of ``kind``: ``pack`` or ``commit``."""
        return [seen for seen in self.seen if seen[0] == "PUT" and ("/packs/" in seen[1]) == (kind == "pack")]

    def read(self, ident: str, path: str) -> bytes:
        """A file of a share as a page reads it: its ranges joined, gunzipped, and checked against its entry."""
        share = self.shares[ident]
        entry = share["manifest"]["files"][path]
        data = gzip.decompress(b"".join(share["packs"][pack][offset:offset + length]
                                        for pack, offset, length in entry["at"]))
        assert (len(data), _sha(data)) == (entry["bytes"], entry["sha256"]), path
        return data

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


def _bundle(folder: Path, files: dict[str, bytes], listed: dict[str, Any] | None = None) -> Path:
    """A view bundle of these files in ``folder``, as the writer lays one: each file, and a manifest listing each with
    its size and SHA-256 (``listed`` in its place where given)."""
    folder.mkdir(parents=True, exist_ok=True)
    for path, data in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(data)
    entries = {path: {"bytes": len(data), "sha256": _sha(data), "type": "application/octet-stream"}
               for path, data in files.items()}
    (folder / "manifest.json").write_text(json.dumps({"format": "view-bundle/1", "document": {
        "id": "1024a2f2-2b65-5151-8299-282973f2a9fc", "kind": "model", "name": "arm", "version": "1"},
        "files": entries if listed is None else listed}, indent=1), encoding="utf-8")
    return folder


class ShareTest(unittest.TestCase):
    """The command, run as a person runs it, with an engine and a state and cache of this file's own."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.given = engine_daemon.isolate(cls.addClassCleanup)  # an engine, a state and a cache of this file's own
        cls.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="share-")))
        cls.addClassCleanup(shutil.rmtree, cls.base, True)
        cls.service = Service()
        cls.addClassCleanup(cls.service.close)
        patch = mock.patch.dict(os.environ, NO_PROXY)
        patch.start()
        cls.addClassCleanup(patch.stop)
        (cls.base / "other.stl").write_text(STL.replace("tetra", "other"), encoding="utf-8")
        (cls.base / "board.kicad_pcb").write_text("(kicad_pcb (version 20240108))\n", encoding="utf-8")
        (cls.base / "parts").mkdir()
        cls.state = Path(cls.given["CAD_STATE_DIR"])
        cls.cache = Path(cls.given["CAD_CACHE_DIR"])

    def setUp(self) -> None:
        from cad_server.settings import write_section

        (self.base / "tetra.stl").write_text(STL, encoding="utf-8")
        (self.state / "shares.json").unlink(missing_ok=True)
        write_section("share", None, path=self.state / "settings.json")
        shutil.rmtree(self.cache / "shares", ignore_errors=True)
        self.service.reset()

    def env(self, **more: str) -> dict[str, str]:
        return {**os.environ, "PYTHONPATH": SOURCE_PATH, "CAD_SHARE_URL": self.service.url, "CAD_TELEMETRY": "0",
                "CAD_UPDATE_CHECK": "0", **NO_PROXY, **more}

    def command(self, *args: str) -> list[str]:
        return [sys.executable, "-m", "cad_server.cli", "share", *args]

    def cad(self, *args: str, **more: str) -> Any:
        return engine_daemon.run(self.command(*args), env=self.env(**more), cwd=self.base)

    def shared(self, *args: str, target: str = "tetra.stl", **more: str) -> dict[str, Any]:
        done = self.cad(target, "--yes", "--json", *args, **more)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(len(done.stdout.splitlines()), 1, done.stdout)
        return json.loads(done.stdout)

    def records(self) -> list[dict[str, Any]]:
        return json.loads((self.state / "shares.json").read_text(encoding="utf-8"))["shares"]

    def write_records(self, rows: list[dict[str, Any]]) -> None:
        path = self.state / "shares.json"
        path.write_text(json.dumps({"format": "cad-shares/1", "shares": rows}), encoding="utf-8")
        os.chmod(path, 0o600)

    def folder(self, target: str = "tetra.stl") -> Path:
        from cad.engine.ids import file_id
        from cad_server import sharing

        return sharing.folder_of(file_id(self.base / target))

    # --- agreeing, and the setting -------------------------------------------------------------------------------

    def test_the_first_share_is_refused_naming_yes_and_yes_shares_and_records(self) -> None:
        refused = self.cad("tetra.stl")
        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertEqual(refused.stdout, "")
        words = refused.stderr
        for said in ("cad share tetra.stl --yes", "never its code or the CAD file", "the file itself",
                     self.service.url, "anyone with the link", "7 days", "delete link", "Ask the person"):
            self.assertIn(said, words)
        self.assertEqual(self.service.seen, [])
        as_json = json.loads(self.cad("tetra.stl", "--json").stdout)
        self.assertEqual((as_json["ok"], as_json["reason"], as_json["userActionRequired"], as_json["next"]),
                         (False, "confirmation_required", True, ["cad share tetra.stl --json --yes"]))
        self.assertEqual(self.service.seen, [])

        done = self.cad("tetra.stl", "--yes")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(len(lines), 4, done.stdout)
        self.assertRegex(lines[0], r"^Shared tetra\.stl, an STL: the file itself; 2 files, [\d.]+ (B|KiB) uploaded; "
                                   r"no code went$")
        self.assertRegex(lines[1], rf"^View: +{re.escape(self.service.url)}/[A-Za-z0-9_-]{{22}}$")
        self.assertRegex(lines[2], rf"^Delete: +{re.escape(self.service.url)}/[A-Za-z0-9_-]{{22}}#delete="
                                   r"[A-Za-z0-9_-]{43}$")
        self.assertRegex(lines[3], r"^Expires: 2030-01-08 00:00 UTC, 7 days after this share; sharing it again")
        (ident,) = self.service.shares
        (record,) = self.records()
        self.assertEqual(record["id"], ident)
        self.assertNotIn("key", record)
        self.assertEqual((record["view"], record["remove"]), (lines[1].split()[1], lines[2].split()[1]))
        # Each hash is of the secret's 43-character text, not of the bytes it decodes to.
        owner = self.service.shares[ident]["owner"]
        self.assertEqual(owner, {"write": hashlib.sha256(record["write"].encode()).hexdigest(),
                                 "delete": hashlib.sha256(record["delete"].encode()).hexdigest()})
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
        self.assertEqual(self.service.seen, [])
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

    # --- what travels --------------------------------------------------------------------------------------------

    def test_a_first_share_sends_every_file_and_the_cache_keeps_the_bundle(self) -> None:
        found = self.shared()
        folder = self.folder()
        bundle = folder / "bundle.view"
        listed = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["files"]
        paths = sorted(["manifest.json", *(path for path in listed if path != "thumbnail.png")])
        share = self.service.shares[found["id"]]
        self.assertEqual(sorted(share["manifest"]["files"]), paths)
        for path in paths:
            self.assertEqual(self.service.read(found["id"], path), (bundle / path).read_bytes(), path)
        packs = self.service.puts("pack")
        self.assertEqual(found["sent"]["files"], len(paths))
        self.assertEqual((found["sent"]["packs"], found["sent"]["bytes"]),
                         (len(packs), sum(len(share["packs"][seen[1].rsplit("/", 1)[1]]) for seen in packs)))
        self.assertEqual(found["stored"], {"files": len(paths), "bytes": sum(len(data) + 28 for data in
                                                                            share["packs"].values())})
        # The folder keeps where each file lives, naming the share by its id's SHA-256, never by the id.
        kept = json.loads((folder / "stored.json").read_text(encoding="utf-8"))
        self.assertEqual(kept, {"share": _sha(found["id"]), "files": {
            entry["sha256"]: entry["at"] for entry in share["manifest"]["files"].values()}})
        self.assertTrue((folder / "lock").is_file())

    def test_sharing_again_keeps_the_link_sends_only_what_changed_and_starts_the_expiry_again(self) -> None:
        first = self.shared()
        packs = len(self.service.puts("pack"))
        second = self.shared()
        self.assertEqual((second["view"], second["delete"], second["id"]), (first["view"], first["delete"], first["id"]))
        self.assertEqual((first["again"], second["again"]), (False, True))
        self.assertGreater(second["expires"], first["expires"])
        self.assertEqual((len(self.service.puts("pack")), len(self.service.puts("commit"))), (packs, 2))
        self.assertEqual({name: second["sent"][name] for name in ("files", "bytes", "packs")},
                         {"files": 0, "bytes": 0, "packs": 0})
        self.assertEqual(second["stored"], first["stored"])
        self.assertEqual(len(self.service.shares), 1)
        self.assertEqual([record["expires"] for record in self.records()], [second["expires"]])
        unchanged = self.cad("tetra.stl").stdout.splitlines()
        self.assertRegex(unchanged[0], r"; nothing changed, nothing uploaded \([\d.]+ (B|KiB) in all\); no code went$")
        self.assertIn("(the same link as before)", unchanged[3])

        # An edit of the file: its new bytes travel, and the bundle's manifest that lists them; nothing else.
        (self.base / "tetra.stl").write_text(STL.replace("vertex 10 0 0", "vertex 12 0 0"), encoding="utf-8")
        before = set(self.service.shares[first["id"]]["packs"])
        edited = self.cad("tetra.stl", "--yes")
        self.assertEqual(edited.returncode, 0, edited.stdout + edited.stderr)
        self.assertRegex(edited.stdout.splitlines()[0], r"; 2 files changed, [\d.]+ (B|KiB) uploaded \([\d.]+ (B|KiB) "
                                                        r"in all\); no code went$")
        self.assertEqual(edited.stdout.splitlines()[1].split()[1], first["view"])
        share = self.service.shares[first["id"]]
        new = [name for name in share["packs"] if name not in before]
        self.assertEqual({path for path, entry in share["manifest"]["files"].items()
                          if any(piece[0] in new for piece in entry["at"])}, {"manifest.json", "source.stl"})
        self.assertIn("vertex 12 0 0", self.service.read(first["id"], "source.stl").decode())

    def test_a_403_makes_a_new_share_with_a_new_link(self) -> None:
        first = self.shared()
        self.service.shares[first["id"]]["owner"]["write"] = _sha("another computer's write secret")
        second = self.shared()
        self.assertNotEqual(second["id"], first["id"])
        self.assertNotEqual(second["view"], first["view"])
        self.assertFalse(second["again"])
        self.assertEqual(second["sent"]["files"], len(self.service.shares[second["id"]]["manifest"]["files"]))
        (record,) = self.records()
        self.assertEqual(record["id"], second["id"])

    def test_a_record_of_version_1_is_none_and_the_document_gets_a_new_share(self) -> None:
        from cad.engine.ids import file_id

        ident, key, write, delete = "0sHbv5_DYsmyh0xEOGyhAw", "k" * 43, "w" * 43, "d" * 43
        self.write_records([{
            "id": ident, "key": key, "write": write, "delete": delete, "service": self.service.url,
            "view": f"{self.service.url}/{ident}#key={key}", "remove": f"{self.service.url}/{ident}#delete={delete}",
            "expires": "2030-01-08T00:00:00Z", "shared": "2026-11-24T10:00:00Z", "bytes": 100,
            "document": {"id": file_id(self.base / "tetra.stl"), "kind": "stl", "name": "tetra.stl",
                         "path": str(self.base / "tetra.stl")}}])
        self.assertEqual(json.loads(self.cad("status", "--json").stdout)["shares"], [])
        found = self.shared()
        self.assertNotEqual(found["id"], ident)
        self.assertFalse(found["again"])
        (record,) = self.records()
        self.assertEqual(record["id"], found["id"])
        self.assertNotIn("key", record)

    def test_an_expired_share_is_none_and_its_folder_goes_as_the_records_are_written(self) -> None:
        first = self.shared()
        self.assertTrue(self.folder().is_dir())
        rows = self.records()
        rows[0]["expires"] = "2020-01-01T00:00:00Z"
        self.write_records(rows)
        self.shared(target="other.stl")
        self.assertFalse(self.folder().exists())
        self.assertTrue((self.folder("other.stl") / "stored.json").is_file())
        again = self.shared()
        self.assertNotEqual(again["id"], first["id"])
        self.assertFalse(again["again"])

    def test_one_share_of_a_document_runs_at_a_time(self) -> None:
        from cad.engine.ids import file_id
        from cad_server import sharing
        from cad_server._internal.cli_errors import Failure
        from cad_server.cli import share as command

        first = self.shared()
        folder = self.folder()
        said: list[bytes] = []
        with sharing.held(folder):
            process = subprocess.Popen(self.command("tetra.stl", "--json"), env=self.env(), cwd=self.base,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            def read() -> None:
                for line in iter(process.stderr.readline, b""):
                    said.append(line)
                    if b"waiting for it to end" in line:
                        return

            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            reader.join(engine_daemon.TIMEOUT_SECONDS)
            self.assertIn(b"another `cad share` of tetra.stl runs on this computer", b"".join(said))
        out, err = engine_daemon.communicate(process, self.env())
        self.assertEqual(process.returncode, 0, out + err)
        self.assertEqual(json.loads(out)["id"], first["id"])
        # One that waits all of its time is refused, in a line.
        with sharing.held(folder), mock.patch.object(command, "LOCK_SECONDS", 0.2), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(Failure) as refused, command._locked(file_id(self.base / "tetra.stl"), "tetra.stl",
                                                                         "cad share"):
                pass
        self.assertEqual(len(str(refused.exception).splitlines()), 1)
        self.assertIn("another `cad share` of tetra.stl has run on this computer for 0 seconds",
                      str(refused.exception))

    # --- delete --------------------------------------------------------------------------------------------------

    def test_delete_from_the_record_and_from_a_link_removes_the_cache_folder(self) -> None:
        first = self.shared()
        self.assertTrue(self.folder().is_dir())
        asked = self.cad("delete", "tetra.stl", "--json")
        self.assertEqual((asked.returncode, json.loads(asked.stdout)["reason"]), (2, "confirmation_required"))
        self.assertIn(first["id"], self.service.shares)
        done = self.cad("delete", "tetra.stl", "--yes")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Deleted the share of tetra.stl", done.stdout)
        self.assertEqual(self.service.shares, {})
        self.assertEqual(self.records(), [])
        self.assertFalse(self.folder().exists())
        missing = self.cad("delete", "tetra.stl", "--yes", "--json")
        self.assertEqual((missing.returncode, json.loads(missing.stdout)["reason"]), (2, "not_found"))

        second = self.shared()
        by_link = self.cad("delete", second["delete"], "--yes", "--json")
        self.assertEqual(by_link.returncode, 0, by_link.stdout + by_link.stderr)
        self.assertEqual(json.loads(by_link.stdout)["deleted"], True)
        self.assertEqual((self.service.shares, self.records()), ({}, []))
        self.assertFalse(self.folder().exists())
        gone = self.cad("delete", second["delete"], "--yes")
        self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
        self.assertIn("gone already", gone.stdout)
        # A view link deletes the share this computer keeps of it, and nothing where it keeps none.
        third = self.shared()
        by_view = self.cad("delete", third["view"], "--yes", "--json")
        self.assertEqual((by_view.returncode, json.loads(by_view.stdout)["deleted"]), (0, True))
        self.assertFalse(self.folder().exists())
        unknown = self.cad("delete", third["view"], "--yes", "--json")
        self.assertEqual((unknown.returncode, json.loads(unknown.stdout)["reason"]), (2, "invalid_argument"))

    # --- what it says --------------------------------------------------------------------------------------------

    def test_the_json_answers_shapes(self) -> None:
        found = self.shared()
        self.assertEqual(set(found), {"ok", "view", "delete", "expires", "id", "again", "document", "sent", "stored",
                                      "kept"})
        self.assertEqual((found["ok"], found["kept"]), (True, True))
        self.assertEqual(found["document"]["kind"], "stl")
        self.assertEqual(found["document"]["name"], "tetra.stl")
        self.assertEqual(set(found["sent"]), {"what", "without", "parts", "files", "bytes", "packs", "format", "code",
                                              "cad_file"})
        self.assertEqual((found["sent"]["format"], found["sent"]["code"], found["sent"]["cad_file"]),
                         ("cad-share/2", False, True))
        self.assertEqual(set(found["stored"]), {"files", "bytes"})
        self.assertEqual(found["view"], f"{self.service.url}/{found['id']}")
        status = json.loads(self.cad("status", "--json").stdout)
        self.assertEqual(set(status), {"ok", "sharing", "agreed", "service", "shares"})
        self.assertEqual((status["sharing"], status["agreed"]), ("on", True))
        self.assertEqual(status["shares"], [{"document": found["document"], "view": found["view"],
                                             "delete": found["delete"], "expires": found["expires"]}])

    def test_no_secret_in_a_request_an_error_or_a_file_and_the_view_link_only_in_output_and_record(self) -> None:
        said = []
        for args in (("tetra.stl", "--yes"), ("tetra.stl", "--yes", "--json"), ("status",), ("status", "--json")):
            done = self.cad(*args)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            said += [done.stdout, done.stderr]
        (record,) = self.records()
        self.assertIn(record["view"], "\n".join(said))
        # The service's refusal, and a connection refused: neither says a name of the share's.
        self.service.most_pack = 10
        refused = self.cad("other.stl", "--yes")
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.service.most_pack = 8 * MIB
        unseen = {seen[1].split("/")[3] for seen in self.service.seen} - {record["id"]}
        self.assertEqual(len(unseen), 1, self.service.seen)  # other.stl's share, its id said nowhere
        errors = [refused.stdout, refused.stderr]
        closed = socket.socket()
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
        closed.close()
        unreached = self.cad("other.stl", "--yes", CAD_SHARE_URL=f"http://127.0.0.1:{port}")
        self.assertEqual(unreached.returncode, 1, unreached.stdout + unreached.stderr)
        errors += [unreached.stdout, unreached.stderr]
        for text in errors:
            for name in (*unseen, record["id"], record["write"], record["delete"]):
                self.assertNotIn(name, text)
        deleted = self.cad("delete", "tetra.stl", "--yes")
        said += [deleted.stdout, deleted.stderr]
        text = "\n".join(said)
        # The id is the link's: said inside the two links, and as --json's ``id``, alone.
        bare = text.replace(record["remove"], "").replace(record["view"], "").replace(f'"id":"{record["id"]}"', "")
        for name in ("id", "write", "delete"):
            self.assertNotIn(record[name], bare, name)
        self.assertNotIn(record["write"], text)
        # The write secret goes as each write's Authorization, the delete secret as its hash or a delete's: never in
        # a request's address.
        for method, path, headers, _when in self.service.seen:
            self.assertNotIn(record["write"], path)
            self.assertNotIn(record["delete"], path)
            if method == "PUT" and record["id"] in path:
                self.assertEqual((headers["Authorization"], headers["Cad-Delete-Hash"]),
                                 (f"Bearer {record['write']}", _sha(record["delete"])))
        self.assertEqual([headers["Authorization"] for method, _path, headers, _when in self.service.seen
                          if method == "DELETE"], [f"Bearer {record['delete']}"])
        # Nor in any file of the engine's, the state's (but the records) or the cache's: its logs, its telemetry, the
        # bundle and where its files are, which names the share by its id's SHA-256. The engine's lock is the one file
        # passed over: the running engine holds its first byte locked, which Windows will not let another process
        # read, and it holds no byte of a share (``places.lock``).
        from cad.engine import places

        locked = Path(self.given["CAD_ENGINE_DIR"]) / f"{places.NAME}.lock"
        self.shared()
        (record,) = self.records()
        self.assertTrue((self.folder() / "stored.json").is_file())
        for folder in (self.given["CAD_ENGINE_DIR"], self.given["CAD_STATE_DIR"], self.given["CAD_CACHE_DIR"]):
            for path in Path(folder).rglob("*"):
                if path.is_file() and path.name != "shares.json" and path != locked:
                    data = path.read_bytes()
                    for name in ("id", "write", "delete"):
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
        self.service.most_pack = 10
        done = self.cad("tetra.stl", "--yes")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("the share service refused a pack (413): too_large; at most 10 bytes", done.stderr)
        self.assertFalse((self.state / "shares.json").exists())

    def test_a_kicad_board_and_a_folder_are_refused(self) -> None:
        for target, said, reason in (("board.kicad_pcb", "a KiCad board, which has no view bundle yet", "wrong_type"),
                                     ("parts", "is a folder, which has no view bundle", "wrong_type"),
                                     ("nothere.stl", "no such file: nothere.stl", "not_found")):
            done = self.cad(target, "--yes", "--json")
            self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
            found = json.loads(done.stdout)
            self.assertEqual(found["reason"], reason)
            self.assertIn(said, found["error"])
        self.assertEqual(self.service.seen, [])


class SendTest(unittest.TestCase):
    """What is sent of a bundle, with no engine: its files, its packs, and the recoveries, in this process."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.service = Service()
        cls.addClassCleanup(cls.service.close)
        patch = mock.patch.dict(os.environ, NO_PROXY)
        patch.start()
        cls.addClassCleanup(patch.stop)

    def setUp(self) -> None:
        self.service.reset()
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="share-send-")))
        self.addCleanup(shutil.rmtree, self.base, True)

    def share(self) -> Any:
        from cad_server import sharing

        return sharing.Share.new(self.service.url)

    def send(self, share: Any, folder: Path, stored: dict[str, Any] | None = None, **options: Any) -> Any:
        from cad_server import sharing

        return sharing.send(share, sharing.files(folder), stored, **options)

    def test_new_files_go_as_gzip_members_in_reading_order_in_packs_closed_at_4_mib(self) -> None:
        from cad_server import sharing

        large = os.urandom(6 * MIB)  # gzip leaves it as large: its member is split over two packs
        files = {"look/environment.hdr": b"#?RADIANCE\n", "parts/k/elements.json": b'{"faces":[]}',
                 "parts/k/0.25-28.5.xbm": large, "measure.json": b'{"parts":{}}', "kinematics.json": b"{}",
                 "names/ab.json": b'{"faceNames":["a"]}', "structure.json": b'{"prototypes":[]}',
                 "thumbnail.png": b"\x89PNG an earlier picture"}
        folder = _bundle(self.base / "a.view", files)
        share = self.share()
        sent = self.send(share, folder)
        committed = self.service.shares[share.id]["manifest"]["files"]
        order = ["manifest.json", "structure.json", "names/ab.json", "kinematics.json", "measure.json",
                 "parts/k/0.25-28.5.xbm", "parts/k/elements.json", "look/environment.hdr"]
        self.assertEqual(sorted(committed), sorted(order))  # every file but the picture
        named = [seen[1].rsplit("/", 1)[1] for seen in self.service.puts("pack")]
        self.assertEqual(len(named), 2)
        packs = self.service.shares[share.id]["packs"]
        self.assertEqual(len(packs[named[0]]), sharing.PACK_BYTES)
        self.assertEqual(sorted(committed, key=lambda path: (named.index(committed[path]["at"][0][0]),
                                                             committed[path]["at"][0][1])), order)
        self.assertEqual([piece[0] for piece in committed["parts/k/0.25-28.5.xbm"]["at"]], named)
        for path in order:
            data = self.service.read(share.id, path)
            self.assertEqual(data, (folder / path).read_bytes(), path)
            first = committed[path]["at"][0]
            head = packs[first[0]][first[1]:first[1] + 10]
            # One gzip member: deflate, no flags (no file name), mtime 0.
            self.assertEqual((head[:4], head[4:8]), (b"\x1f\x8b\x08\x00", b"\x00\x00\x00\x00"), path)
        self.assertEqual(sent.travelled, {"files": 8, "packs": 2, "bytes": sum(len(packs[name]) for name in named)})
        self.assertEqual((sent.answer["files"], sent.answer["made"]), (8, True))
        self.assertEqual(sent.stored, {"share": _sha(share.id), "files": {
            entry["sha256"]: entry["at"] for entry in committed.values()}})

    def test_after_an_edit_only_what_changed_travels_and_the_rest_keeps_its_ranges(self) -> None:
        files = {"structure.json": b'{"tree":1}', "measure.json": b'{"m":1}', "names/a.json": b'{"faceNames":[]}',
                 "parts/k/0.xbm": os.urandom(4096), "parts/k/elements.json": b"[]"}
        folder = _bundle(self.base / "a.view", files)
        share = self.share()
        first = self.send(share, folder)
        before = json.loads(json.dumps(self.service.shares[share.id]["manifest"]["files"]))
        _bundle(folder, {**files, "structure.json": b'{"tree":2}'})
        packs = len(self.service.puts("pack"))
        second = self.send(share, folder, first.stored)
        after = self.service.shares[share.id]["manifest"]["files"]
        self.assertEqual((second.travelled["files"], second.travelled["packs"], second.answer["made"]), (2, 1, False))
        self.assertEqual(len(self.service.puts("pack")), packs + 1)
        for path in after:
            if path in ("structure.json", "manifest.json"):
                self.assertNotEqual(after[path]["at"], before[path]["at"], path)
            else:
                self.assertEqual(after[path]["at"], before[path]["at"], path)
        self.assertEqual(self.service.read(share.id, "structure.json"), b'{"tree":2}')
        # Unchanged: no pack, only the commit.
        third = self.send(share, folder, second.stored)
        self.assertEqual(third.travelled, {"files": 0, "bytes": 0, "packs": 0})
        self.assertEqual(len(self.service.puts("pack")), packs + 1)
        # Where it keeps another share's files, everything goes.
        whole = self.send(self.share(), folder, second.stored)
        self.assertEqual(whole.travelled["files"], len(after))

    def test_a_409_naming_missing_packs_sends_their_files_again_twice_at_most(self) -> None:
        from cad_server import sharing

        files = {"structure.json": b'{"tree":1}', "parts/k/0.xbm": os.urandom(5 * MIB), "parts/k/elements.json": b"[]"}
        folder = _bundle(self.base / "a.view", files)
        share = self.share()
        first = self.send(share, folder)
        committed = self.service.shares[share.id]["manifest"]["files"]
        lost = committed["parts/k/elements.json"]["at"][0][0]  # the second pack: the mesh's end, and the table
        del self.service.shares[share.id]["packs"][lost]
        again = self.send(share, folder, first.stored)
        self.assertEqual(again.travelled["files"], 2)  # the mesh (whose member ends there) and the table, again
        self.assertEqual(self.service.commits, 3)
        for path in ("manifest.json", *files):
            self.assertEqual(self.service.read(share.id, path), (folder / path).read_bytes(), path)
        # A service that keeps losing them: sent again twice, then the refusal.
        self.service.losing, commits = 3, self.service.commits
        with self.assertRaises(sharing.Refused) as refused:
            self.send(share, folder, again.stored)
        self.assertEqual((refused.exception.status, bool(refused.exception.missing)), (409, True))
        self.assertEqual(self.service.commits - commits, 3)

    def test_a_409_naming_no_pack_commits_again_once(self) -> None:
        from cad_server import sharing

        folder = _bundle(self.base / "a.view", {"structure.json": b"{}"})
        share = self.share()
        self.service.conflicts = 1
        self.send(share, folder)
        self.assertEqual(self.service.commits, 2)
        self.service.conflicts = 2
        with self.assertRaises(sharing.Refused) as refused:
            self.send(share, folder)
        self.assertEqual((refused.exception.status, refused.exception.missing), (409, ()))
        self.assertEqual(self.service.commits, 4)

    def test_a_429_waits_for_its_retry_after(self) -> None:
        folder = _bundle(self.base / "a.view", {"structure.json": b"{}"})
        self.service.limited, self.service.retry_after = 1, "1"
        told: list[float] = []
        self.send(self.share(), folder, waiting=told.append)
        self.assertEqual(told, [1.0])
        (refused, taken), commit = self.service.puts("pack"), self.service.puts("commit")
        self.assertGreaterEqual(taken[3] - refused[3], 1.0)
        self.assertEqual((refused[1], len(commit)), (taken[1], 1))

    def test_the_files_of_a_bundle_a_share_takes(self) -> None:
        from cad_server import sharing

        folder = _bundle(self.base / "a.view", {"structure.json": b"{}", "thumbnail.png": b"png"})
        self.assertEqual([file.path for file in sharing.files(folder)], ["manifest.json", "structure.json"])
        entry = {"bytes": 2, "sha256": _sha(b"{}"), "type": "application/json"}
        for listed, said in (({"../structure.json": entry}, "no path a share takes"),
                             ({"/structure.json": entry}, "no path a share takes"),
                             ({"gone.json": entry}, "no regular file inside it"),
                             ({"structure.json": {**entry, "sha256": _sha(b"[]")}}, "not what its manifest says")):
            _bundle(folder, {"structure.json": b"{}"}, listed)
            with self.assertRaisesRegex(sharing.Unsharable, re.escape(said)):
                sharing.files(folder)
        if os.name != "nt":
            (self.base / "outside.json").write_bytes(b"{}")
            (folder / "linked.json").symlink_to(self.base / "outside.json")
            _bundle(folder, {"structure.json": b"{}"}, {"linked.json": entry})
            with self.assertRaisesRegex(sharing.Unsharable, "no regular file inside it"):
                sharing.files(folder)
        (folder / "manifest.json").unlink()
        with self.assertRaisesRegex(sharing.Unsharable, "no manifest.json"):
            sharing.files(folder)

    def test_one_holder_of_a_documents_lock_at_a_time(self) -> None:
        from cad_server import sharing

        folder = self.base / "1024a2f2-2b65-5151-8299-282973f2a9fc"
        folder.mkdir()
        (folder / "stored.json").write_text("{}", encoding="utf-8")
        waited, took = threading.Event(), threading.Event()

        def wait() -> None:
            with sharing.held(folder, wait=engine_daemon.TIMEOUT_SECONDS, waiting=waited.set,
                              make=lambda: folder.mkdir(exist_ok=True)):
                took.set()

        with sharing.held(folder):
            with self.assertRaises(sharing.Busy):
                with sharing.held(folder):
                    pass
            waiter = threading.Thread(target=wait, daemon=True)
            waiter.start()
            self.assertTrue(waited.wait(engine_daemon.TIMEOUT_SECONDS))
            self.assertFalse(took.is_set())
        waiter.join(engine_daemon.TIMEOUT_SECONDS)
        self.assertTrue(took.is_set())
        self.assertTrue((folder / "lock").is_file())  # a folder that holds more than its lock stays
        # Its share deleted while another waits: the folder goes as its holder lets go, and the waiter makes it again.
        waited.clear()
        took.clear()
        with sharing.held(folder):
            waiter = threading.Thread(target=wait, daemon=True)
            waiter.start()
            self.assertTrue(waited.wait(engine_daemon.TIMEOUT_SECONDS))
            (folder / "stored.json").unlink()
        waiter.join(engine_daemon.TIMEOUT_SECONDS)
        self.assertTrue(took.is_set())
        self.assertFalse(folder.exists())  # the waiter's, holding nothing but its lock, went too


if __name__ == "__main__":
    unittest.main()
