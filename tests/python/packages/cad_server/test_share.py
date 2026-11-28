"""``cad share`` and ``cad import``, the client's half of the share protocol (``cad-share/2``), run against a stand-in
service written here that speaks its API and holds a client to it -- a pack named by the SHA-256 of its body, the
owner and its two hashes made by the first write and a write of another secret refused, a manifest of the protocol's
shape (its name, entry and made, its view and the files that made it), a commit's 409 naming the packs it lacks, a
commit that another replaced meanwhile refused, the packs neither manifest names deleted, a delete by either secret,
and a share's files served as the service serves them, a zip of one folder made from their stored gzip members --
storing what it is sent, and an engine of this file's own that builds a model and writes each view bundle.

What it holds the command to: the first share is refused, naming ``--yes`` and what goes, and ``--yes`` shares and
records the agreement; ``cad share off`` refuses even with ``--yes``; a first share sends every file of the bundle the
engine wrote and the files that made it, and the file's folder of the cache keeps the bundle, which the next share
writes over and reuses, and where each file lives; sharing again keeps the link, starts the expiry again and sends
only what changed (nothing, for a file unchanged); a share is of one file, by its canonical path, named by its path or
its document's id the same share, the same after the engine restarts, kept in the file's entry of the library, which
this user alone may read; a 403, a share the library holds without its keys and an expired one each make a new share;
one ``cad share`` of a file at a time; a delete works from the library and from a link, and removes what the share
kept in the cache; what travelled in words and in ``--json``; no secret in any request's address, error or file but
the library, and the view link only in the output and the library; a connection refused, or refused by something that
is not the service, said in one line; a folder and a script refused (a KiCad board's and a schematic's shares are
``test_share_kicad.py``'s, against the share service itself). A model, shared by its ``.xbf``: the ``.xbf`` itself and
the files of the closure it holds, its script, its
modules and what it read, under its project's root, the rest left out and said; a model edited and not run again
refused, naming the run of its script; one whose module is gone refused; a re-share after a run sending the module
and the ``.xbf`` that changed; a file document's file itself (its bytes once, the view's too) and a URDF's mesh files
beside it. With no engine: the files that made a model, from a closure an ``.xbf`` of this test's making holds, its
root and the two caps on it, what is left out and the refusals; what is sent, the files a bundle's manifest lists as
gzip members in reading order and then the files that made it, one member for identical bytes, in packs closed at
4 MiB with a file split over two (a large ``.xbf`` among them), a 409 naming missing packs sending their files again
(twice at most), one naming none committing again once, and a 429 waited out; and ``cad import``: the files written as
the zip holds them, a model's ``.xbf`` among them, the file it is of, the script that builds it and the next steps
said, where what built it differs from this computer, nothing run, a folder that holds files refused, a share gone
said, every entry refused that would land outside its folder, and the shared file kept in the library with the link it
came from, one entry a link.
A share's link wherever cad takes a document: the file this computer shared under it, else its import's copy of the
shared file (a model's ``.xbf``, there with nothing run), else refused in one line naming the import to make, an import
whose folder is gone too. The fixtures are made in a temporary folder.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
import zipfile
import zlib
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import SOURCE_PATH, add_sources

add_sources()

ID = re.compile(r"[A-Za-z0-9_-]{22}")
# The document a share this computer made is of, in the records a test writes.
DOCUMENT = "1024a2f2-2b65-5151-8299-282973f2a9fc"
SECRET = re.compile(r"[A-Za-z0-9_-]{43}")
HASH = re.compile(r"[0-9a-f]{64}")
MIB = 1024 * 1024
NO_PROXY = {"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
MEMBERS = {"format", "name", "entry", "made", "view", "files"}

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

# A robot of two links, each drawn by a mesh file: one beside it, one in a folder above its own.
URDF = """<robot name="arm">
  <link name="base"><visual><geometry><mesh filename="meshes/base.stl"/></geometry></visual>
    <collision><geometry><mesh filename="meshes/base.stl"/></geometry></collision></link>
  <link name="tip"><visual><geometry><mesh filename="../parts/tip.stl"/></geometry></visual></link>
  <joint name="turn" type="revolute"><parent link="base"/><child link="tip"/><axis xyz="0 0 1"/>
    <limit lower="-1" upper="1" effort="1" velocity="1"/></joint>
</robot>
"""

# A model of one part: a module of its project gives its width and a file of it the hole; a file beside the project,
# which the project's .git keeps out of it, its thickness.
PLATE = """import json
from pathlib import Path

import build123d as bd
from cad import xbf

from lib.sizes import WIDTH


@xbf
def plate():
    here = Path(__file__).parent
    hole = json.loads((here / "data" / "hole.json").read_text(encoding="utf-8"))["radius"]
    thick = json.loads((here.parent / "stock.json").read_text(encoding="utf-8"))["thick"]
    body = bd.Box(WIDTH, 30, thick) - bd.Cylinder(hole, 10)
    body.label = "plate"
    return body


if __name__ == "__main__":
    plate()
"""


def _sha(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("ascii") if isinstance(data, str) else data).hexdigest()


def _judged(found: Any) -> str | None:
    """Why ``found`` is no share manifest of the protocol's shape, or None for one that is."""
    if not isinstance(found, dict) or set(found) != MEMBERS or found.get("format") != "cad-share/2":
        return "not a cad-share/2 manifest: its format, name, entry, made, view and files"
    name, made, entry, view, files = (found[key] for key in ("name", "made", "entry", "view", "files"))
    if not isinstance(name, str) or not 1 <= len(name) <= 200 or any(unicodedata.category(c) == "Cc" for c in name):
        return "its name is no document's"
    if made is not None and (not isinstance(made, dict) or len(made) > 32 or not all(
            isinstance(key, str) and isinstance(value, str) and len(key) <= 100 and len(value) <= 100
            for key, value in made.items())):
        return "its made is not what built it"
    if not isinstance(view, dict) or not isinstance(files, dict):
        return "its view and its files are files by their paths"
    if "manifest.json" not in view or "thumbnail.png" in view or len(view) + len(files) > 200_000:
        return "its view is not a bundle's"
    if entry is not None and (not isinstance(entry, str) or entry not in files):
        return "its entry is none of its files"
    for path, listed in (*view.items(), *files.items()):
        if not path or len(path.encode("utf-8")) > 1024 or any(part in ("", ".", "..") for part in path.split("/")) \
                or "\\" in path or path.startswith("/"):
            return f"{path!r} is no path"
        if not isinstance(listed, dict) or set(listed) != {"sha256", "bytes", "at"} \
                or not HASH.fullmatch(str(listed["sha256"])) or type(listed["bytes"]) is not int or listed["bytes"] < 0:
            return f"{path}: not its sha256, bytes and at"
        at = listed["at"]
        if not isinstance(at, list) or not at or not all(
                isinstance(piece, list) and len(piece) == 3 and HASH.fullmatch(str(piece[0]))
                and type(piece[1]) is int and type(piece[2]) is int and piece[1] >= 0 and piece[2] > 0
                for piece in at):
            return f"{path}: at is not [[pack, offset, length], ...]"
    return None


def _listed(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Every entry of a manifest's two maps."""
    return [*manifest["view"].values(), *manifest["files"].values()]


def _safe(name: str) -> str:
    """A share's name as its zip's folder and file are named: letters, digits, ``.``, ``-`` and ``_``, others ``_``,
    no dot first or last, 100 characters at most; ``share`` where nothing is left."""
    kept = "".join(character if re.fullmatch(r"[A-Za-z0-9._-]", character) else "_" for character in name)
    return kept.lstrip(".")[:100].rstrip(".") or "share"


def _header(text: str) -> str:
    """Text as the service's headers carry it: its UTF-8, every byte but a letter, a digit and ``._~/+-`` as ``%XX``."""
    return "".join(chr(byte) if re.fullmatch(rb"[A-Za-z0-9._~/+-]", bytes([byte])) else f"%{byte:02X}"
                   for byte in text.encode("utf-8"))


def _zipped(folder: str, members: list[tuple[str, bytes]]) -> bytes:
    """The zip the service makes of a share's files (each its path and its stored gzip member): its folder's entry,
    then each file sorted by its path's bytes, the member's deflate stream as it is with its trailer's CRC-32 and size
    (method 8) -- one not of the plain form gunzipped and stored (method 0) --, named in UTF-8, dated 1980-01-01 00:00;
    then the central directory."""
    data, central, count = bytearray(), bytearray(), 0

    def add(name: bytes, method: int, crc: int, body: bytes, size: int, attributes: int) -> None:
        nonlocal count
        offset = len(data)
        data.extend(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0x0800, method, 0, 0x21, crc, len(body), size,
                                len(name), 0) + name + body)
        central.extend(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, (3 << 8) | 20, 20, 0x0800, method, 0, 0x21, crc,
                                   len(body), size, len(name), 0, 0, 0, 0, attributes, offset) + name)
        count += 1

    add(f"{folder}/".encode(), 0, 0, b"", 0, (0o40755 << 16) | 0x10)
    for path, member in sorted(members, key=lambda item: item[0].encode("utf-8")):
        name = f"{folder}/{path}".encode()
        if member[:4] == b"\x1f\x8b\x08\x00":
            crc, size = struct.unpack("<II", member[-8:])
            add(name, 8, crc, member[10:-8], size, 0o100644 << 16)
        else:
            plain = gzip.decompress(member)
            add(name, 0, zlib.crc32(plain), plain, len(plain), 0o100644 << 16)
    return bytes(data + central + struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, count, count, len(central), len(data), 0))


class Service:
    """The share service's API as the protocol says it, in memory: ``shares`` by id, each its ``owner`` (the two hashes
    the first write made), its ``packs`` by pack id, its ``manifest`` and the one it replaced, and its expiry; and each
    share's files as a zip (``GET /<id>.zip``). Every request seen (``seen``: method, path, headers, when). Each
    commit's expiry is a second later than the one before, as if time passed between them. Its knobs: ``most_pack``
    (the most a pack may be), ``limited`` (how many requests to answer 429 next, with ``Retry-After: retry_after``),
    ``conflicts`` (how many commits to refuse as if another replaced the manifest meanwhile), ``losing`` (how many
    commits find every pack of their share gone) and ``zips`` (a zip to answer for an id in place of the share's)."""

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
                self.raw(status, b"" if body is None else json.dumps(body).encode(),
                         {**({"Content-Type": "application/json"} if body is not None else {}), **(headers or {})})

            def raw(self, status: int, data: bytes, headers: dict[str, str]) -> None:
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
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

            def do_GET(self) -> None:  # noqa: N802
                service.seen.append((self.command, self.path, dict(self.headers), time.monotonic()))
                match = re.fullmatch(r"/([A-Za-z0-9_-]{22})\.zip", self.path)
                if match is None:
                    return self.refuse(404, "not_found", "no such page")
                with service.lock:
                    if service.limited:
                        service.limited -= 1
                        return self.refuse(429, "rate_limited", "too many", {"Retry-After": service.retry_after})
                    crafted = service.zips.get(match.group(1))
                    share = service.shares.get(match.group(1)) or {}
                    manifest = share.get("manifest")
                    if crafted is None and manifest is None:
                        return self.refuse(404, "not_found", "no such share: it expired, or was deleted")
                    name = _safe(manifest["name"] if manifest else "share")
                    body = crafted if crafted is not None else _zipped(name, [
                        (path, service.member(match.group(1), path, "files")) for path in manifest["files"]])
                headers = {"Content-Type": "application/zip", "Cache-Control": "no-store",
                           "Content-Disposition": f'attachment; filename="{name}.zip"',
                           "X-Robots-Tag": "noindex, nofollow"}
                if manifest and manifest["entry"] is not None:
                    headers["Cad-Share-Entry"] = _header(manifest["entry"])
                if manifest and manifest["made"]:
                    headers["Cad-Share-Made"] = ", ".join(f"{_header(key)}={_header(value)}"
                                                          for key, value in manifest["made"].items())
                return self.raw(200, body, headers)

            do_HEAD = do_GET  # noqa: N815

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
                named = {piece[0] for entry in _listed(manifest) for piece in entry["at"]}
                missing = sorted(named - set(share["packs"]))
                if missing:
                    return self.refuse(409, "missing_packs", "upload them, then commit again", missing=missing)
                for entry in _listed(manifest):
                    for pack, offset, length in entry["at"]:
                        if offset + length > len(share["packs"][pack]):
                            return self.refuse(400, "bad_manifest", f"a file lies past the end of {pack}")
                if service.conflicts:
                    service.conflicts -= 1
                    return self.refuse(409, "conflict", "another commit replaced the share meanwhile: try again")
                replaced, share["replaced"], share["manifest"] = share["manifest"], share["manifest"], manifest
                kept = named | ({piece[0] for entry in _listed(replaced) for piece in entry["at"]} if replaced else set())
                share["packs"] = {name: data for name, data in share["packs"].items() if name in kept}
                expires = datetime(2030, 1, 1, tzinfo=timezone.utc) + timedelta(days=7, seconds=service.commits)
                share["expires"] = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
                return self.answer(201 if replaced is None else 200, {
                    "id": ident, "expires": share["expires"], "files": len(_listed(manifest)),
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
            self.zips: dict[str, bytes] = {}

    def puts(self, kind: str) -> list[tuple[str, str, dict[str, str], float]]:
        """The PUTs seen of ``kind``: ``pack`` or ``commit``."""
        return [seen for seen in self.seen if seen[0] == "PUT" and ("/packs/" in seen[1]) == (kind == "pack")]

    def member(self, ident: str, path: str, kept: str = "view") -> bytes:
        """A file's gzip member as a share holds it: the ranges of its entry in the manifest's ``kept`` map, joined."""
        share = self.shares[ident]
        return b"".join(share["packs"][pack][offset:offset + length]
                        for pack, offset, length in share["manifest"][kept][path]["at"])

    def read(self, ident: str, path: str, kept: str = "view") -> bytes:
        """A file of a share as a page (``view``) or a zip (``files``) reads it: its ranges joined, gunzipped, and
        checked against its entry."""
        entry = self.shares[ident]["manifest"][kept][path]
        data = gzip.decompress(self.member(ident, path, kept))
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
        "id": "1024a2f2-2b65-5151-8299-282973f2a9fc", "kind": "xbf", "name": "arm", "version": "1"},
        "files": entries if listed is None else listed}, indent=1), encoding="utf-8")
    return folder


def _library(state: Path, rows: list[dict[str, Any]]) -> None:
    """The library of the state folder ``state`` written with the shares ``rows`` (records, ``sharing.record_of``'s)
    in their files' entries, as ``cad share`` keeps them, and nothing else."""
    files: dict[str, Any] = {}
    for row in rows:
        entry = files.setdefault(row["document"]["id"], {"path": row["document"]["path"], "created": 1.0})
        entry.setdefault("shares", {})[row["service"]] = {
            "link": row["view"], "write": row["write"], "delete": row["delete"], "expires": row["expires"],
            **{name: (row.get("files") or {}).get(name) for name in ("root", "entry")}}
    state.mkdir(parents=True, exist_ok=True)
    (state / "library.json").write_text(json.dumps({"schema": 1, "projects": {}, "files": files}), encoding="utf-8")


def _write(folder: Path, files: dict[str, str | bytes]) -> Path:
    """These files written in ``folder``, each by its path there."""
    for path, data in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
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
        (cls.base / "other.stl").write_bytes(STL.replace("tetra", "other").encode())
        (cls.base / "parts").mkdir()
        cls.state = Path(cls.given["CAD_STATE_DIR"])
        cls.cache = Path(cls.given["CAD_CACHE_DIR"])

    def setUp(self) -> None:
        from cad_server.settings import write_section

        (self.base / "tetra.stl").write_bytes(STL.encode())  # bytes: Windows writes text with \r\n
        (self.state / "library.json").unlink(missing_ok=True)
        write_section("share", None, path=self.state / "settings.json")
        shutil.rmtree(self.cache / "documents", ignore_errors=True)
        self.service.reset()

    def env(self, **more: str) -> dict[str, str]:
        return {**os.environ, "PYTHONPATH": SOURCE_PATH, "CAD_SHARE_URL": self.service.url, "CAD_TELEMETRY": "0",
                "CAD_UPDATE_CHECK": "0", **NO_PROXY, **more}

    def command(self, *args: str) -> list[str]:
        return [sys.executable, "-m", "cad_server.cli", "share", *args]

    def cad(self, *args: str, cwd: Path | None = None, **more: str) -> Any:
        return engine_daemon.run(self.command(*args), env=self.env(**more), cwd=cwd or self.base)

    def shared(self, *args: str, target: str = "tetra.stl", cwd: Path | None = None, **more: str) -> dict[str, Any]:
        done = self.cad(target, "--yes", "--json", *args, cwd=cwd, **more)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(len(done.stdout.splitlines()), 1, done.stdout)
        return json.loads(done.stdout)

    def records(self) -> list[dict[str, Any]]:
        """The shares this computer keeps, as the library holds them (``sharing.records``)."""
        from cad_server import sharing

        return sharing.records()

    def write_records(self, rows: list[dict[str, Any]]) -> None:
        _library(self.state, rows)

    def folder(self, target: str = "tetra.stl") -> Path:
        from cad.engine.ids import file_id
        from cad_server import sharing

        return sharing.folder_of(file_id(self.base / target))

    def import_(self, *args: str, cwd: Path, elsewhere: bool = False) -> Any:
        """``cad import``, on this computer, or ``elsewhere``: on another, with a state, a cache and an engine folder of
        its own (no server runs there, so the import's record is kept by the command), which keep no record of this
        computer's shares."""
        other = Path(tempfile.mkdtemp(prefix="elsewhere-", dir=self.base)) if elsewhere else None
        more = {"CAD_STATE_DIR": str(other / "state"), "CAD_CACHE_DIR": str(other / "cache"),
                "CAD_ENGINE_DIR": str(other / "engine")} if other else {}
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", "import", *args], env=self.env(**more),
                                 cwd=cwd)

    # --- agreeing, and the setting -------------------------------------------------------------------------------

    def test_the_first_share_is_refused_naming_yes_and_yes_shares_and_records(self) -> None:
        refused = self.cad("tetra.stl")
        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertEqual(refused.stdout, "")
        words = refused.stderr
        for said in ("cad share tetra.stl --yes", "the file itself, which anyone with the link can download",
                     "Never an installed library", f"\n  Its files, from {self.base}: tetra.stl\n", self.service.url,
                     "anyone with the link can open it and download its files", "7 days", "delete link",
                     "Ask the person"):
            self.assertIn(said, words)
        self.assertNotIn("never its code", words)
        self.assertEqual(self.service.seen, [])
        as_json = json.loads(self.cad("tetra.stl", "--json").stdout)
        self.assertEqual((as_json["ok"], as_json["reason"], as_json["userActionRequired"], as_json["next"]),
                         (False, "confirmation_required", True, ["cad share tetra.stl --json --yes"]))
        self.assertEqual(self.service.seen, [])

        done = self.cad("tetra.stl", "--yes")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(len(lines), 6, done.stdout)
        self.assertRegex(lines[0], r"^Shared tetra\.stl, an STL: the file itself and its view; 3 files, [\d.]+ "
                                   r"(B|KiB) uploaded$")
        self.assertEqual(lines[1], f"Its files, from {self.base}: tetra.stl")
        lines = lines[1:]
        self.assertRegex(lines[1], rf"^View: +{re.escape(self.service.url)}/[A-Za-z0-9_-]{{22}}$")
        self.assertEqual(lines[2], f"Files:   {lines[1].split()[1]}.zip")
        self.assertRegex(lines[3], rf"^Delete: +{re.escape(self.service.url)}/[A-Za-z0-9_-]{{22}}#delete="
                                   r"[A-Za-z0-9_-]{43}$")
        self.assertRegex(lines[4], r"^Expires: 2030-01-08 00:00 UTC, 7 days after this share; sharing it again")
        (ident,) = self.service.shares
        (record,) = self.records()
        self.assertEqual(record["id"], ident)
        self.assertNotIn("key", record)
        self.assertEqual((record["view"], record["remove"]), (lines[1].split()[1], lines[3].split()[1]))
        # Each hash is of the secret's 43-character text, not of the bytes it decodes to.
        owner = self.service.shares[ident]["owner"]
        self.assertEqual(owner, {"write": hashlib.sha256(record["write"].encode()).hexdigest(),
                                 "delete": hashlib.sha256(record["delete"].encode()).hexdigest()})
        self.assertEqual(record["document"]["path"], str(self.base / "tetra.stl"))
        # Kept in the file's entry of the library, which holds the share's keys: this user's alone to read.
        from cad.engine.ids import file_id

        library = json.loads((self.state / "library.json").read_text(encoding="utf-8"))
        self.assertEqual(library["files"][file_id(self.base / "tetra.stl")]["shares"],
                         {self.service.url: {"link": record["view"], "write": record["write"],
                                             "delete": record["delete"], "expires": record["expires"],
                                             "root": str(self.base), "entry": None}})
        self.assertEqual(sorted(path.name for path in self.state.glob("*.json") if "shares" in path.name
                                or "imports" in path.name), [])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((self.state / "library.json").stat().st_mode), 0o600)
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

    def test_a_first_share_sends_every_file_and_the_files_folder_of_the_cache_keeps_the_bundle(self) -> None:
        found = self.shared()
        folder = self.folder()
        self.assertEqual(folder, self.cache / "documents" / found["document"]["id"])  # the cache's folder of the file
        bundle = folder / "view"
        listed = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["files"]
        paths = sorted(["manifest.json", *(path for path in listed if path != "thumbnail.png")])
        share = self.service.shares[found["id"]]
        self.assertEqual(sorted(share["manifest"]["view"]), paths)
        for path in paths:
            self.assertEqual(self.service.read(found["id"], path), (bundle / path).read_bytes(), path)
        packs = self.service.puts("pack")
        self.assertEqual(found["sent"]["files"], len(paths) + 1)  # and the file itself
        self.assertEqual((found["sent"]["packs"], found["sent"]["bytes"]),
                         (len(packs), sum(len(share["packs"][seen[1].rsplit("/", 1)[1]]) for seen in packs)))
        self.assertEqual(found["stored"], {"files": len(paths) + 1, "bytes": sum(len(data) + 28 for data in
                                                                                share["packs"].values())})
        # The folder keeps where each file lives, naming the share by its id's SHA-256, never by the id.
        kept = json.loads((folder / "stored.json").read_text(encoding="utf-8"))
        self.assertEqual(kept, {"share": _sha(found["id"]), "files": {
            entry["sha256"]: entry["at"] for entry in _listed(share["manifest"])}})
        self.assertTrue((folder / "share.lock").is_file())
        # Shared again, the bundle is written over the one there, each file whose bytes are the same left as it was,
        # and nothing is sent. Deleted, the next share makes it again, and keeps the link: its secrets are the record's.
        stamps = {path: (bundle / path).stat().st_mtime_ns for path in paths}
        again = self.shared()
        self.assertEqual({path: (bundle / path).stat().st_mtime_ns for path in paths}, stamps)
        self.assertEqual((again["id"], again["sent"]["files"]), (found["id"], 0))
        shutil.rmtree(self.cache / "documents")
        remade = self.shared()
        self.assertEqual((remade["id"], remade["again"]), (found["id"], True))
        self.assertTrue((bundle / "manifest.json").is_file())

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
        self.assertRegex(unchanged[0], r"; nothing changed, nothing uploaded \([\d.]+ (B|KiB) in all\)$")
        self.assertIn("(the same link as before)", unchanged[5])

        # An edit of the file: its new bytes travel, once for the view's copy and the file itself, and the bundle's
        # manifest that lists them; nothing else.
        (self.base / "tetra.stl").write_bytes(STL.replace("vertex 10 0 0", "vertex 12 0 0").encode())
        before = set(self.service.shares[first["id"]]["packs"])
        edited = self.cad("tetra.stl", "--yes")
        self.assertEqual(edited.returncode, 0, edited.stdout + edited.stderr)
        self.assertRegex(edited.stdout.splitlines()[0], r"; 3 files changed, [\d.]+ (B|KiB) uploaded \([\d.]+ (B|KiB) "
                                                        r"in all\)$")
        self.assertEqual(edited.stdout.splitlines()[2].split()[1], first["view"])
        manifest = self.service.shares[first["id"]]["manifest"]
        new = [name for name in self.service.shares[first["id"]]["packs"] if name not in before]
        self.assertEqual({(kept, path) for kept in ("view", "files") for path, entry in manifest[kept].items()
                          if any(piece[0] in new for piece in entry["at"])},
                         {("view", "manifest.json"), ("view", "source.stl"), ("files", "tetra.stl")})
        self.assertIn("vertex 12 0 0", self.service.read(first["id"], "tetra.stl", "files").decode())

    def test_a_file_documents_files_are_the_file_itself_its_bytes_sent_once(self) -> None:
        found = self.shared()
        manifest = self.service.shares[found["id"]]["manifest"]
        self.assertEqual((manifest["name"], manifest["entry"], manifest["made"]), ("tetra.stl", None, None))
        self.assertEqual(list(manifest["files"]), ["tetra.stl"])
        self.assertEqual(self.service.read(found["id"], "tetra.stl", "files"), (self.base / "tetra.stl").read_bytes())
        # The view's copy of the file is the same bytes: one member, named twice.
        self.assertEqual(manifest["files"]["tetra.stl"], manifest["view"]["source.stl"])
        self.assertEqual(found["files"], {"count": 1, "bytes": len(STL), "entry": None, "file": "tetra.stl",
                                          "root": str(self.base), "paths": ["tetra.stl"], "left_out": [],
                                          "unseen": False})
        self.assertEqual(found["document"]["path"], str(self.base / "tetra.stl"))
        # Named by its document's id, it is the same share, and the file itself goes.
        from cad.engine.ids import file_id

        by_id = self.shared(target=file_id(self.base / "tetra.stl"))
        self.assertEqual((by_id["id"], by_id["again"], by_id["files"]["count"], by_id["sent"]["files"]),
                         (found["id"], True, 1, 0))
        # Imported on this computer, which shared it: the file is where it was, and nothing is downloaded or written.
        place = Path(tempfile.mkdtemp(prefix="import-", dir=self.base))
        here = self.import_(found["zip"], cwd=place)
        self.assertEqual(here.returncode, 0, here.stdout + here.stderr)
        self.assertEqual(here.stdout, f"tetra.stl was shared from this computer: it is {self.base / 'tetra.stl'}. "
                                      "Nothing was downloaded; work there.\n")
        self.assertEqual((list(place.iterdir()), [seen for seen in self.service.seen if seen[0] == "GET"]), ([], []))
        # Imported on another computer: the file itself, and the step that shows it.
        imported = self.import_(found["zip"], cwd=place, elsewhere=True)
        self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
        self.assertEqual((place / "tetra.stl" / "tetra.stl").read_bytes(), (self.base / "tetra.stl").read_bytes())
        self.assertIn(f"Next: cad viewer {os.path.join('tetra.stl', 'tetra.stl')}", imported.stdout)
        self.assertNotIn("Made with", imported.stdout)

    def test_a_urdfs_mesh_files_go_and_one_outside_its_folder_is_left_out_and_said(self) -> None:
        robot = _write(self.base / "robot", {"arm.urdf": URDF, "meshes/base.stl": STL, "notes.md": "not drawn"})
        _write(self.base, {"parts/tip.stl": STL.replace("10", "20")})
        self.addCleanup(shutil.rmtree, robot, True)
        done = self.cad("arm.urdf", "--yes", cwd=robot)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertRegex(lines[0], r"^Shared arm\.urdf, a URDF: the file itself with 1 file it draws from and its view "
                                   r"\(its links and joints, with 2 mesh files\); ")
        self.assertEqual(lines[1], f"Its files, from {robot}: arm.urdf, meshes/base.stl")
        self.assertEqual(lines[2], f"Left out, outside the project: {self.base / 'parts' / 'tip.stl'}")
        (ident,) = self.service.shares
        manifest = self.service.shares[ident]["manifest"]
        self.assertEqual(sorted(manifest["files"]), ["arm.urdf", "meshes/base.stl"])
        self.assertEqual(self.service.read(ident, "meshes/base.stl", "files"), STL.encode())

    # --- a model -------------------------------------------------------------------------------------------------

    def run_model(self, project: Path) -> str:
        """``cad run plate.py`` in ``project``, against this file's engine: the id it printed, its ``.xbf``'s."""
        done = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "run", "plate.py"], env=self.env(),
                                 cwd=project)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return re.search(r"id: ([0-9a-f-]{36})", done.stdout).group(1)

    def restart(self) -> None:
        """The engine stopped and started again, as ``cad server stop`` and ``start`` do: no worker holds a model, and
        each is its ``.xbf``."""
        pid = engine_daemon.engine_pid(dict(os.environ))
        stopped = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "server", "stop"], env=self.env())
        self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
        engine_daemon.await_exit(pid)
        engine_daemon.start()

    def project(self, name: str) -> tuple[Path, Path]:
        """A workspace of the stock the plate reads, and in it the plate's project, a checkout's root: both paths."""
        workspace = _write(self.base / name, {"stock.json": '{"thick": 6}'})
        self.addCleanup(shutil.rmtree, workspace, True)
        project = _write(workspace / "plate", {
            "plate.py": PLATE, "lib/__init__.py": "", "lib/sizes.py": "WIDTH = 40.0\n", "data/hole.json": '{"radius": 4}',
            "README.md": "how to build it", "draft.py": "raise SystemExit('a script the build never ran')\n"})
        (project / ".git").mkdir()  # a checkout's root: the project's files are the ones under it
        return workspace, project

    def test_a_model_shares_its_xbf_and_the_files_that_built_it_and_imports_back_into_a_folder(self) -> None:
        from cad.engine.ids import file_id

        workspace, project = self.project("workspace")
        ident = self.run_model(project)
        xbf = project / "plate.xbf"
        self.assertEqual(ident, file_id(xbf))  # a model's id is its .xbf's
        found = self.shared(target="plate.xbf", cwd=project)
        expected = ["data/hole.json", "lib/__init__.py", "lib/sizes.py", "plate.py", "plate.xbf"]
        manifest = self.service.shares[found["id"]]["manifest"]
        self.assertEqual((manifest["name"], manifest["entry"], sorted(manifest["files"])), ("plate", "plate.py",
                                                                                           expected))
        from cad.engine import previous

        self.assertEqual(manifest["made"], {"cad": previous.version(), **previous._libraries(),
                                            **previous._platform()})
        for path in expected:
            self.assertEqual(self.service.read(found["id"], path, "files"), (project / path).read_bytes(), path)
        stock = str(workspace / "stock.json")
        self.assertEqual(found["files"], {"count": 5, "bytes": sum(len((project / path).read_bytes())
                                                                   for path in expected),
                                          "entry": "plate.py", "file": "plate.xbf", "root": str(project),
                                          "paths": expected, "left_out": [{"path": stock, "reason": "outside"}],
                                          "unseen": False})
        self.assertEqual(found["document"], {"id": ident, "kind": "xbf", "name": found["document"]["name"],
                                             "path": str(xbf)})
        # By its document's id, the same file and the same share; and so after the engine restarts, when no worker
        # holds the model and its .xbf is what the engine reads, by its path and by its id alike.
        said = self.cad(ident, cwd=project).stdout.splitlines()
        self.assertRegex(said[0], r"^Shared plate(\.xbf)?, a model: its \.xbf and the 4 files that made it and its view "
                                  r"\(1 part as meshes, with their names and measurements\); nothing changed")
        self.assertEqual(said[1], f"Its files, from {project}: {', '.join(expected)}")
        self.assertEqual(said[2], f"Left out, outside the project: {stock}")
        self.assertEqual(said[4], f"Files:   {found['zip']}")
        parts = [path for path in self.service.shares[found["id"]]["manifest"]["view"] if path.startswith("parts/")]
        bundle = self.folder("workspace/plate/plate.xbf") / "view"
        stamps = {path: (bundle / path).stat().st_mtime_ns for path in parts}
        self.restart()
        for target in ("plate.xbf", ident):
            with self.subTest(target=target):
                after = self.shared(target=target, cwd=project)
                self.assertEqual((after["id"], after["again"], after["document"]["path"]), (found["id"], True, str(xbf)))
                self.assertEqual(sorted(self.service.shares[found["id"]]["manifest"]["files"]), expected)
        # The bundle written over the one the share made, its parts' files, named by their geometry, kept as they were.
        self.assertTrue(parts)
        self.assertEqual({path: (bundle / path).stat().st_mtime_ns for path in parts}, stamps)

        # Imported by its view link on this computer, which shared it: where its files are said, nothing downloaded, and
        # the folder named not written.
        place = Path(tempfile.mkdtemp(prefix="import-", dir=self.base))
        here = self.import_(found["view"], "copy", cwd=place)
        self.assertEqual(here.returncode, 0, here.stdout + here.stderr)
        self.assertRegex(here.stdout, rf"^plate(\.xbf)? was shared from this computer: it is {re.escape(str(xbf))}, its "
                                      rf"files in {re.escape(str(project))}, its script "
                                      rf"{re.escape(str(project / 'plate.py'))}\. Nothing was downloaded, and copy was "
                                      r"not written; work there\.\n$")
        mine = json.loads(self.import_(found["view"], "--json", cwd=place).stdout)
        self.assertEqual(mine, {"ok": True, "local": True, "name": mine["name"], "file": str(xbf),
                                "root": str(project), "entry": "plate.py", "ignored": None,
                                "next": [f"cad run {project / 'plate.py'}"]})
        self.assertEqual((list(place.iterdir()), [seen for seen in self.service.seen if seen[0] == "GET"]), ([], []))

        # Imported on another computer: the same bytes at the same paths, the .xbf among them, nothing run, and the steps
        # that show it and build it said.
        imported = self.import_(found["view"], "copy", cwd=place, elsewhere=True)
        self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
        written = sorted(path.relative_to(place / "copy").as_posix() for path in (place / "copy").rglob("*")
                         if path.is_file())
        self.assertEqual(written, expected)
        for path in expected:
            self.assertEqual((place / "copy" / path).read_bytes(), (project / path).read_bytes(), path)
        lines = imported.stdout.splitlines()
        self.assertRegex(lines[0], r"^Imported plate into copy: 5 files, [\d.]+ (B|KiB); it is plate\.xbf; its script "
                                   r"is plate\.py$")
        # The file its build read that the share left out, which a build here needs where its closure names it.
        self.assertEqual(lines[1], "Its build read 1 file the share does not hold: ../stock.json (from plate.xbf's "
                                   "folder); a build here needs it there")
        self.assertEqual(lines[2], "Made with the cad and libraries this computer has")
        self.assertEqual(lines[3], "Nothing was run: the code is someone else's, the person's to read and run. Next: "
                                   f"cad viewer {os.path.join('copy', 'plate.xbf')} shows it as it was shared; "
                                   f"cad run {os.path.join('copy', 'plate.py')} builds it here")

        # Edited and not run again: refused, naming the file and the run of its script, with nothing uploaded.
        (project / "lib" / "sizes.py").write_bytes(b"WIDTH = 44.0\n")  # bytes: Windows writes text with \r\n
        seen = len(self.service.seen)
        stale = self.cad("plate.xbf", "--json", cwd=project)
        self.assertEqual(stale.returncode, 1, stale.stdout + stale.stderr)
        refusal = json.loads(stale.stdout)
        self.assertIn(f"{project / 'lib' / 'sizes.py'} changed after plate.xbf was last made", refusal["error"])
        self.assertEqual(refusal["next"], [f"cad run {project / 'plate.py'}"
                                           if os.name != "nt" else refusal["next"][0]])
        self.assertEqual(len(self.service.seen), seen)

        # Run again: shared again, the module that changed travels with the .xbf the run wrote, and the files that did
        # not keep their ranges.
        before = {path: entry["at"] for path, entry in manifest["files"].items()}
        self.run_model(project)
        again = self.shared(target=ident, cwd=project)
        self.assertEqual((again["id"], again["again"]), (found["id"], True))
        after = self.service.shares[found["id"]]["manifest"]["files"]
        self.assertEqual({path for path in expected if after[path]["at"] != before[path]}, {"lib/sizes.py", "plate.xbf"})
        self.assertEqual(self.service.read(found["id"], "lib/sizes.py", "files"), b"WIDTH = 44.0\n")

        # An edit no build sees (a comment changes no key): the run takes the .xbf whole and writes nothing, and the
        # share goes, since the model was made by that run.
        with open(project / "plate.py", "ab") as handle:
            handle.write(b"# a comment\n")
        self.assertIn("plate.py changed after", json.loads(self.cad("plate.xbf", "--json", cwd=project).stdout)["error"])
        written = xbf.stat().st_mtime_ns
        self.run_model(project)
        self.assertEqual(xbf.stat().st_mtime_ns, written)
        self.assertEqual(self.shared(target="plate.xbf", cwd=project)["id"], found["id"])

        # A file it read gone: left out and said; a module gone: refused, naming it and the run.
        (project / "data" / "hole.json").unlink()
        gone = self.shared(target="plate.xbf", cwd=project)
        self.assertEqual(gone["files"]["left_out"], [{"path": stock, "reason": "outside"},
                                                     {"path": str(project / "data" / "hole.json"), "reason": "gone"}])
        self.assertNotIn("data/hole.json", self.service.shares[found["id"]]["manifest"]["files"])
        (project / "lib" / "sizes.py").unlink()
        refused = self.cad("plate.xbf", "--json", cwd=project)
        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertEqual(json.loads(refused.stdout)["reason"], "not_found")
        self.assertIn(f"{project / 'lib' / 'sizes.py'}, which built plate.xbf, is gone",
                      json.loads(refused.stdout)["error"])

    def test_a_shares_link_is_the_file_it_shared_else_the_copy_its_import_wrote(self) -> None:
        """Wherever cad takes a document, the share's link is this computer's copy of it: the file it shared under that
        link; else, its record gone and the share imported here, the copy of the shared file the import wrote, a model's
        .xbf there at once with nothing run; a ref's selector the same in either. A link this computer has no copy of,
        its import's folder since gone too, is refused, as a ref's file, an inspect's document, a snapshot's source, an
        export's and a packet's input, in one line naming the import to make."""
        from cad.engine.ids import file_id
        from cad_server.engine import cli

        workspace, project = self.project("linked")
        ident = self.run_model(project)
        link = self.shared(target="plate.xbf", cwd=project)["view"]

        def cad(*args: str, given: str | None = None) -> Any:
            return engine_daemon.run([sys.executable, "-m", "cad_server.cli", *args, "--json"], env=self.env(),
                                     cwd=workspace, input=given)

        shared = cad("inspect", f"{link}#plate")
        self.assertEqual(shared.returncode, 0, shared.stdout + shared.stderr)
        volume = json.loads(shared.stdout)["volume"]

        self.write_records([])
        place = Path(tempfile.mkdtemp(prefix="linked-", dir=self.base))
        imported = self.import_(link, "copy", cwd=place)
        self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
        copy = place / "copy" / "plate.xbf"
        for args in (("inspect", f"{link}#plate"), ("inspect", link, f"{link}#plate"),
                     ("inspect", str(copy), f"{link}#plate")):
            with self.subTest(args=args):
                built = cad(*args)
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
                self.assertAlmostEqual(json.loads(built.stdout)["volume"], volume, places=3)
        exported = cad("export", link, str(place / "out.step"))
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        self.assertTrue((place / "out.step").is_file())
        with mock.patch.dict(os.environ, {"CAD_SHARE_URL": self.service.url}):
            self.assertEqual(cli._linked_inputs({"input": link, "jobs": [{"input": link}, {"camera": "iso"}]}),
                             {"input": str(copy), "jobs": [{"input": str(copy)}, {"camera": "iso"}]})
        self.assertNotEqual(file_id(copy), ident)  # the import's copy is a file of its own

        # Its folder gone, the import is no copy: refused as a link this computer never saw.
        shutil.rmtree(place / "copy")
        refusal = {"ok": False, "reason": "not_found", "next": [f"cad import {link}"],
                   "error": f"{link} is a shared model this computer has no copy of: run `cad import {link}`."}
        other = f"{self.service.url}/{'B' * 22}"
        unknown = {"ok": False, "reason": "not_found", "next": [f"cad import {other}"],
                   "error": f"{other} is a shared model this computer has no copy of: run `cad import {other}`."}
        packet = json.dumps({"input": other, "jobs": [{"camera": "iso", "outputs": [{"label": "view 1"}]}]})
        for args, given, answer in (
                (("inspect", link), None, refusal), (("inspect", f"{other}#plate"), None, unknown),
                (("inspect", str(project / "plate.xbf"), f"{other}#plate"), None, unknown),
                (("snapshot", other, "out.png"), None, unknown),
                (("export", other, "out.step"), None, unknown),
                (("snapshot", "--job", "-"), packet, unknown)):
            with self.subTest(args=args):
                missing = cad(*args, given=given)
                self.assertEqual((missing.returncode, json.loads(missing.stdout)), (2, answer))
        self.assertEqual(list(workspace.glob("*.png")) + list(workspace.glob("*.step")), [])

    def test_a_403_makes_a_new_share_with_a_new_link(self) -> None:
        first = self.shared()
        self.service.shares[first["id"]]["owner"]["write"] = _sha("another computer's write secret")
        second = self.shared()
        self.assertNotEqual(second["id"], first["id"])
        self.assertNotEqual(second["view"], first["view"])
        self.assertFalse(second["again"])
        self.assertEqual(second["sent"]["files"], len(_listed(self.service.shares[second["id"]]["manifest"])))
        (record,) = self.records()
        self.assertEqual(record["id"], second["id"])

    def test_a_share_the_library_holds_without_its_keys_is_none_and_the_document_gets_a_new_share(self) -> None:
        from cad.engine.ids import file_id

        ident = "0sHbv5_DYsmyh0xEOGyhAw"
        (self.state / "library.json").write_text(json.dumps({"schema": 1, "projects": {}, "files": {
            file_id(self.base / "tetra.stl"): {"path": str(self.base / "tetra.stl"), "created": 1.0, "shares": {
                self.service.url: {"link": f"{self.service.url}/{ident}", "key": "k" * 43,
                                   "expires": "2030-01-08T00:00:00Z"}}}}}), encoding="utf-8")
        self.assertEqual(json.loads(self.cad("status", "--json").stdout)["shares"], [])
        found = self.shared()
        self.assertNotEqual(found["id"], ident)
        self.assertFalse(found["again"])
        (record,) = self.records()
        self.assertEqual(record["id"], found["id"])

    def kept(self, target: str = "tetra.stl") -> list[str]:
        """What a share keeps in the file's folder of the cache, of what it keeps there."""
        return sorted(name for name in ("view", "stored.json", "share.lock") if (self.folder(target) / name).exists())

    def test_an_expired_share_is_none_and_what_it_kept_goes_as_the_records_are_written(self) -> None:
        first = self.shared()
        self.assertEqual(self.kept(), ["share.lock", "stored.json", "view"])
        rows = self.records()
        rows[0]["expires"] = "2020-01-01T00:00:00Z"
        self.write_records(rows)
        self.shared(target="other.stl")
        self.assertEqual(self.kept(), [])
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

    def test_delete_from_the_record_and_from_a_link_removes_what_it_kept_in_the_cache(self) -> None:
        first = self.shared()
        self.assertTrue(self.folder().is_dir())
        (self.folder() / "note.json").write_text("{}", encoding="utf-8")  # the cache's own note of the file stays
        asked = self.cad("delete", "tetra.stl", "--json")
        self.assertEqual((asked.returncode, json.loads(asked.stdout)["reason"]), (2, "confirmation_required"))
        self.assertIn(first["id"], self.service.shares)
        done = self.cad("delete", "tetra.stl", "--yes")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Deleted the share of tetra.stl", done.stdout)
        self.assertEqual(self.service.shares, {})
        self.assertEqual(self.records(), [])
        self.assertEqual((self.kept(), (self.folder() / "note.json").read_text(encoding="utf-8")), ([], "{}"))
        missing = self.cad("delete", "tetra.stl", "--yes", "--json")
        self.assertEqual((missing.returncode, json.loads(missing.stdout)["reason"]), (2, "not_found"))

        second = self.shared()
        by_link = self.cad("delete", second["delete"], "--yes", "--json")
        self.assertEqual(by_link.returncode, 0, by_link.stdout + by_link.stderr)
        self.assertEqual(json.loads(by_link.stdout)["deleted"], True)
        self.assertEqual((self.service.shares, self.records()), ({}, []))
        self.assertEqual(self.kept(), [])
        gone = self.cad("delete", second["delete"], "--yes")
        self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
        self.assertIn("gone already", gone.stdout)
        # A view link deletes the share this computer keeps of it, and nothing where it keeps none.
        third = self.shared()
        by_view = self.cad("delete", third["view"], "--yes", "--json")
        self.assertEqual((by_view.returncode, json.loads(by_view.stdout)["deleted"]), (0, True))
        self.assertEqual(self.kept(), [])
        # By its document's id, the share of the file it is of.
        from cad.engine.ids import file_id

        self.shared()
        by_id = self.cad("delete", file_id(self.base / "tetra.stl"), "--yes", "--json")
        self.assertEqual((by_id.returncode, json.loads(by_id.stdout)["deleted"]), (0, True), by_id.stdout)
        self.assertEqual(self.records(), [])
        unknown = self.cad("delete", third["view"], "--yes", "--json")
        self.assertEqual((unknown.returncode, json.loads(unknown.stdout)["reason"]), (2, "invalid_argument"))

    # --- what it says --------------------------------------------------------------------------------------------

    def test_the_json_answers_shapes(self) -> None:
        found = self.shared()
        self.assertEqual(set(found), {"ok", "view", "zip", "delete", "expires", "id", "again", "document", "files",
                                      "sent", "stored", "kept"})
        self.assertEqual((found["ok"], found["kept"]), (True, True))
        self.assertEqual(found["document"]["kind"], "stl")
        self.assertEqual(found["document"]["name"], "tetra.stl")
        self.assertEqual(found["document"]["path"], str(self.base / "tetra.stl"))
        self.assertEqual(set(found["files"]), {"count", "bytes", "entry", "file", "root", "paths", "left_out",
                                               "unseen"})
        self.assertEqual((found["files"]["root"], found["files"]["paths"]), (str(self.base), ["tetra.stl"]))
        self.assertEqual(set(found["sent"]), {"what", "parts", "files", "bytes", "packs", "format"})
        self.assertEqual(found["sent"]["format"], "cad-share/2")
        self.assertEqual(set(found["stored"]), {"files", "bytes"})
        self.assertEqual(found["view"], f"{self.service.url}/{found['id']}")
        self.assertEqual(found["zip"], f"{self.service.url}/{found['id']}.zip")
        status = json.loads(self.cad("status", "--json").stdout)
        self.assertEqual(set(status), {"ok", "sharing", "agreed", "service", "shares"})
        self.assertEqual((status["sharing"], status["agreed"]), ("on", True))
        self.assertEqual(status["shares"], [{"document": found["document"], "view": found["view"], "zip": found["zip"],
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
        # The id is the link's: said inside the links, and as --json's ``id``, alone.
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
        # Nor in any file of the engine's, the state's (but the library) or the cache's: its logs, its telemetry, the
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
                if path.is_file() and path.name != "library.json" and path != locked:
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
        self.assertEqual(self.records(), [])

    def test_a_folder_and_a_script_are_refused(self) -> None:
        (self.base / "plate.py").write_text(PLATE, encoding="utf-8")
        for target, said, reason in (("parts", "is a folder, which has no view bundle", "wrong_type"),
                                     ("nothere.stl", "no such file: nothere.stl", "not_found"),
                                     ("plate.py", "plate.py is a model's script, not a CAD file: share the model's "
                                                  ".xbf, which running it writes (`cad run plate.py`)", "wrong_type")):
            done = self.cad(target, "--yes", "--json")
            self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
            found = json.loads(done.stdout)
            self.assertEqual(found["reason"], reason)
            self.assertIn(said, found["error"])
            self.assertNotIn("\n", found["error"])
        self.assertEqual(self.service.seen, [])


def _xbf(path: Path, closure: dict[str, Any] | None) -> Path:
    """An ``.xbf`` as far as a share reads one: the head its writer leaves, its writer's mark and the build closure its
    main label holds (``previous.scan``), or none."""
    head = b"cadgen.engine xbf/9 (cadgen 0.11.17)\x00"
    if closure is not None:
        head += json.dumps(closure, separators=(",", ":")).encode("ascii") + b"\x00"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(head + bytes(64))
    return path


class SourcesTest(unittest.TestCase):
    """The files that made a document, with no engine: a model's from the build closure an ``.xbf`` of this test's
    making holds, the ``.xbf`` among them, its root and the two caps on it, what is left out and the refusals; a file
    document's."""

    def setUp(self) -> None:
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="share-sources-")))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.home = str(self.base / "home")

    def closure(self, modules: list[str], inputs: list[list[Any]] | None = None, key: str | None = "k" * 32,
                script: str = "plate.py") -> dict[str, Any]:
        """A build closure as the engine writes one, its paths relative to its .xbf's folder."""
        return {"schema": "cadgen.engine closure/2", "engine": {"release": "cadgen 0.11.17", "format": "xbf/9"},
                "libs": {"build123d": "0.13.0", "OCP": "8.0.1.1.0"},
                "platform": {"python": "3.13.18", "system": "Linux", "arch": "x86_64"},
                "source": {"kind": "script", "path": script, "function": "plate"},
                "modules": [[path, "d" * 32] for path in modules], "symbols": {}, "inputs": inputs or [],
                "bodies": 1, "key": key}

    def sources(self, folder: Path, closure: dict[str, Any] | None, built: float | None = None,
                name: str = "plate.xbf", projects: list[Path] | None = None) -> Any:
        """The files that made the model whose .xbf, holding ``closure``, is written in ``folder`` now, the viewer
        having ``projects``."""
        from cad_server import sharing

        xbf = _xbf(folder / name, closure)
        return sharing.model_sources(str(xbf), time.time() + 60 if built is None else built, home=self.home,
                                     projects=[str(project) for project in projects or ()])

    def test_the_root_is_the_models_project_else_the_folder_that_holds_them_never_the_home_folder(self) -> None:
        from cad_server import sharing

        home = Path(self.home)
        project = _write(home / "work" / "plate", {"src/plate.py": "", "lib/parts.py": ""})
        closure = self.closure(["plate.py", "../lib/parts.py"])
        # No project and no checkout: the deepest folder that holds them all.
        found = self.sources(project / "src", closure)
        self.assertEqual((found.root, found.entry, found.shared), (str(project), "src/plate.py", "src/plate.xbf"))
        self.assertEqual([file.path for file in found.files], ["lib/parts.py", "src/plate.py", "src/plate.xbf"])
        self.assertEqual(found.file, str(project / "src" / "plate.xbf"))
        # A checkout's root over the .xbf that holds its script is its project: what lies outside it is left out.
        (project / "src" / ".git").mkdir()
        found = self.sources(project / "src", closure)
        self.assertEqual((found.root, found.entry, [file.path for file in found.files]),
                         (str(project / "src"), "plate.py", ["plate.py", "plate.xbf"]))
        self.assertEqual(found.left_out, ((str(project / "lib" / "parts.py"), "outside"),))
        (project / "src" / ".git").rmdir()
        # So is a project the viewer has, the nearest over the .xbf that holds its script, whatever the files are.
        self.assertEqual(self.sources(project / "src", closure, projects=[project / "src"]).left_out,
                         ((str(project / "lib" / "parts.py"), "outside"),))
        _write(home / "work", {"common.json": "{}"})
        found = self.sources(project / "src", self.closure(["plate.py"], [["read", "../../common.json", "c" * 64]]),
                             projects=[home / "work", project / "XBF"])
        self.assertEqual((found.root, [file.path for file in found.files]),
                         (str(home / "work"), ["common.json", "plate/src/plate.py", "plate/src/plate.xbf"]))
        # One that holds the .xbf and not its script is not the model's.
        found = self.sources(project / "XBF", self.closure(["../src/plate.py"], script="../src/plate.py"),
                             projects=[project / "XBF"])
        self.assertEqual((found.root, found.left_out), (str(project), ()))
        # Never the home folder, nor a folder over it, though the build read a file elsewhere in it (the person's
        # documents) or elsewhere on the disk: the root holds the model, and those files are left out and named.
        _write(home, {"Documents/private.json": "{}"})
        _write(self.base, {"elsewhere/shared.py": ""})
        far = self.closure(["plate.py", "../lib/parts.py", "../../../../elsewhere/shared.py"],
                           [["read", "../../../Documents/private.json", "c" * 64]])
        for projects in ([], [home]):
            found = self.sources(project / "src", far, projects=projects)
            self.assertEqual(found.root, str(project))
            self.assertEqual([file.path for file in found.files], ["lib/parts.py", "src/plate.py", "src/plate.xbf"])
            self.assertEqual(sorted(found.left_out), [(str(self.base / "elsewhere" / "shared.py"), "outside"),
                                                      (str(home / "Documents" / "private.json"), "outside")])
            (home / ".git").mkdir(exist_ok=True)  # a checkout at the home folder is no model's project either
        # A model that no folder but the home folder holds, .xbf and script, is refused, saying how to share it.
        _write(home, {"arm.py": ""})
        with self.assertRaisesRegex(sharing.Unsharable, r"^no folder but .* \(the home folder, or a folder over it\) "
                                                        r"holds arm\.xbf and arm\.py.*open the folder that holds them "
                                                        r"as a project in the viewer$"):
            self.sources(home, self.closure(["arm.py"], script="arm.py"), name="arm.xbf")
        with self.assertRaisesRegex(sharing.Unsharable, r"^no folder but .* holds plate\.xbf and plate\.py"):
            self.sources(home / "elsewhere", self.closure(["../work/plate/src/plate.py"],
                                                          script="../work/plate/src/plate.py"))

    def test_the_closures_paths_are_its_xbfs_folders_and_an_xbf_with_none_goes_alone(self) -> None:
        from cad_server import sharing

        # An .xbf declared in a folder of its own beside the script's: its closure names the script from there.
        project = _write(self.base / "home" / "plate", {"src/plate.py": "", "src/lib/parts.py": ""})
        found = self.sources(project / "XBF", self.closure(["../src/plate.py", "../src/lib/parts.py"],
                                                           script="../src/plate.py"))
        self.assertEqual((found.root, found.entry, found.shared), (str(project), "src/plate.py", "XBF/plate.xbf"))
        self.assertEqual([file.path for file in found.files], ["XBF/plate.xbf", "src/lib/parts.py", "src/plate.py"])
        # One that holds no closure (a shape a program handed over): the .xbf alone, at its own name.
        alone = self.sources(self.base / "home" / "shapes", None, name="crate.xbf")
        self.assertEqual(([file.path for file in alone.files], alone.entry, alone.made, alone.shared),
                         (["crate.xbf"], None, None, "crate.xbf"))
        # An .xbf that no folder but the home folder holds with its script is refused: a share holds a project's.
        (project / ".git").mkdir()
        with self.assertRaisesRegex(sharing.Unsharable, "no folder but .* holds plate.xbf and plate.py"):
            self.sources(self.base / "home" / "elsewhere", self.closure(["../plate/src/plate.py"],
                                                                        script="../plate/src/plate.py"))

    def test_what_a_model_read_goes_and_what_is_gone_or_a_font_outside_is_left_out(self) -> None:
        from cad_server import sharing

        project = _write(self.base / "home" / "plate", {"plate.py": "", "data/hole.json": "{}", "fonts/a.ttf": "f"})
        _write(self.base, {"system/b.ttf": "f"})
        found = self.sources(project, self.closure(["plate.py"], [
            ["read", "data/hole.json", "c" * 64], ["file", "data/gone.step", "c" * 32],
            ["read", "data/never.json", None],  # found missing by the build: it read nothing of it
            ["font", "A", "fonts/a.ttf", "REGULAR", "f:1"], ["font", "B", "../../system/b.ttf", None, "f:2"],
            ["font", "Arial", None, None, "f:3"]]))
        self.assertEqual([file.path for file in found.files], ["data/hole.json", "fonts/a.ttf", "plate.py",
                                                               "plate.xbf"])
        self.assertEqual(found.left_out, ((str(project / "data" / "gone.step"), "gone"),))
        self.assertEqual(found.made, {"cad": "0.11.17", "build123d": "0.13.0", "OCP": "8.0.1.1.0", "python": "3.13.18",
                                      "system": "Linux", "arch": "x86_64"})
        self.assertFalse(found.unseen)
        self.assertTrue(self.sources(project, self.closure(["plate.py"], key=None)).unseen)
        # Two files of the same bytes are two files that go.
        _write(project, {"lib/__init__.py": "", "lib/more/__init__.py": ""})
        both = self.sources(project, self.closure(["plate.py", "lib/__init__.py", "lib/more/__init__.py"]))
        self.assertEqual([file.sha256 for file in both.files if file.path.endswith("__init__.py")], [_sha(b"")] * 2)
        self.assertEqual(sharing.share_name(" a\x00rm\t "), "arm")
        self.assertEqual(sharing.share_name("x" * 300), "x" * 200)
        self.assertEqual(sharing.share_name("\x07"), "share")

    def test_a_version_controls_file_the_build_read_is_left_out_and_said(self) -> None:
        from cad_server import sharing

        project = _write(self.base / "home" / "plate", {
            "plate.py": "", ".git/config": "", "data/.GIT./x": "", "data/GIT~1/y": "", "data/.h‌g/z": "",
            "store/HEAD": "", "store/objects/a": "", "store/refs/b": "", "data/ok.json": "", ".gitignore": ""})
        reads = [".git/config", "data/.GIT./x", "data/GIT~1/y", "data/.h‌g/z", "store/HEAD", "store/objects/a",
                 "store/refs/b", "data/ok.json", ".gitignore"]
        found = self.sources(project, self.closure(["plate.py"], [["read", path, "c" * 64] for path in reads]))
        self.assertEqual([file.path for file in found.files], [".gitignore", "data/ok.json", "plate.py", "plate.xbf",
                                                               "store/objects/a", "store/refs/b"])
        self.assertEqual(sorted(found.left_out), sorted((str(project / path), "control") for path in (
            ".git/config", "data/.GIT./x", "data/GIT~1/y", "data/.h‌g/z", "store/HEAD")))
        from cad_server.cli.share import _notes

        self.assertIn("Left out, a version control's file (a .git folder's), which no share holds: ",
                      _notes(found, "xbf", "plate")[1])
        # As a share's manifest takes a path, and as an import judges what it writes.
        for path in (".git/config", ".Git /HEAD", "a/GIT~1/b", ".svn/wc.db", "_darcs/x", ".jj/repo/config.toml"):
            self.assertFalse(sharing.sharable(path), path)
        self.assertEqual(sharing.controlled(["a.py", "x/HEAD", "x/Objects/1", "x/refs/heads/main"]), "x/HEAD")
        self.assertIsNone(sharing.controlled(["a.py", "HEAD", "objects/1", ".github/x", "git/HEAD", "a.git"]))

    def test_a_file_changed_after_the_xbf_was_made_or_code_gone_is_refused(self) -> None:
        from cad_server import sharing

        project = _write(self.base / "home" / "plate", {"plate.py": "", "lib/parts.py": "", "data/a.json": "{}"})
        built = time.time()
        later = built + 5
        os.utime(project / "data" / "a.json", (later, later))
        with self.assertRaises(sharing.Stale) as changed:
            self.sources(project, self.closure(["plate.py", "lib/parts.py"], [["read", "data/a.json", "c" * 64]]),
                         built)
        self.assertEqual((changed.exception.path, changed.exception.why), (str(project / "data" / "a.json"), "changed"))
        # Made later than the edit (a run that took the .xbf whole, writing nothing): the files are what made it.
        self.assertIn("data/a.json", [file.path for file in self.sources(
            project, self.closure(["plate.py", "lib/parts.py"], [["read", "data/a.json", "c" * 64]]), later + 1).files])
        for gone, closure in (("lib/gone.py", self.closure(["plate.py", "lib/gone.py"])),
                              ("nothere.py", self.closure(["lib/parts.py"], script="nothere.py"))):
            with self.subTest(gone=gone), self.assertRaises(sharing.Stale) as missing:
                self.sources(project, closure)
            self.assertEqual((missing.exception.path, missing.exception.why), (str(project / gone), "gone"))

    def test_what_a_share_of_a_model_does_not_hold_is_said_a_line_each(self) -> None:
        from cad_server import sharing
        from cad_server.cli.share import _notes

        file = sharing.File("arm.py", _sha(b""), 0, Path("/p/arm.py"))
        self.assertEqual(_notes(sharing.Sources((file,), "arm.py", {}, "/p", (("/q/a.json", "outside"),
                                                                              ("/p/b.json", "gone")), True),
                                "xbf", "arm"), [
            "Its files, from /p: arm.py", "Left out, outside the project: /q/a.json", "Left out, no longer on the disk: /p/b.json",
            "Its build read a file cad could not see, which the share does not hold: an import may not rebuild it "
            "without that file"])
        self.assertEqual(_notes(sharing.Sources(), "xbf", "crate"), [
            "Its .xbf alone went: no build closure names the code that made crate (a shape a program handed over, or a "
            "file exported from another)"])
        self.assertEqual(_notes(sharing.Sources(), "stl", "tetra.stl"), [])

    def test_a_file_documents_files_are_the_file_and_a_urdfs_meshes_beside_it(self) -> None:
        from cad_server import sharing

        robot = _write(self.base / "robot", {"arm.urdf": URDF, "meshes/base.stl": STL})
        found = sharing.file_sources(str(robot / "arm.urdf"), "urdf")
        self.assertEqual(([file.path for file in found.files], found.entry, found.made),
                         (["arm.urdf", "meshes/base.stl"], None, None))
        self.assertEqual(found.left_out, ((str(self.base / "parts" / "tip.stl"), "gone"),))
        _write(self.base, {"parts/tip.stl": STL})
        self.assertEqual(sharing.file_sources(str(robot / "arm.urdf"), "urdf").left_out,
                         ((str(self.base / "parts" / "tip.stl"), "outside"),))
        self.assertEqual([file.path for file in sharing.file_sources(str(robot / "meshes" / "base.stl"), "stl").files],
                         ["base.stl"])


class SendTest(unittest.TestCase):
    """What is sent of a bundle and of the files that made it, with no engine: its files, its packs, and the
    recoveries, in this process."""

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

    def made(self, files: dict[str, bytes]) -> Any:
        """The files that made a model, as ``model_sources`` answers them: ``plate.py`` its script."""
        from cad_server import sharing

        folder = _write(self.base / "project", files)
        return sharing.Sources(tuple(sharing.File(path, _sha(data), len(data), folder / path)
                                     for path, data in sorted(files.items())), "plate.py",
                               {"cad": "0.11.17", "build123d": "0.13.0"}, str(folder))

    def send(self, share: Any, folder: Path, stored: dict[str, Any] | None = None, sources: Any = None,
             **options: Any) -> Any:
        from cad_server import sharing

        return sharing.send(share, sharing.view_files(folder), sources or sharing.Sources(), stored, name="arm",
                            **options)

    def test_a_new_share_s_id_never_begins_with_a_dash_which_a_command_line_reads_as_an_option(self) -> None:
        import base64

        from cad_server import sharing

        def text(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        # 0xf8's top six bits are 62, base64url's "-": that id is drawn again, and the secrets are the next draws.
        drawn = [b"\xf8" + bytes(15), bytes(16), b"\x01" * 32, b"\x02" * 32]
        self.assertTrue(text(drawn[0]).startswith("-"))
        with mock.patch.object(sharing.secrets, "token_bytes", side_effect=drawn):
            share = sharing.Share.new(self.service.url)
        self.assertEqual((share.id, share.write, share.delete), ("A" * 22, text(drawn[2]), text(drawn[3])))

    def test_new_files_go_as_gzip_members_in_reading_order_in_packs_closed_at_4_mib(self) -> None:
        from cad_server import sharing

        large = os.urandom(6 * MIB)  # gzip leaves it as large: its member is split over two packs
        files = {"sheets/~2F.json": b'{"sheets":[]}', "parts/k/elements.json": b'{"faces":[]}',
                 "parts/k/0.25-28.5.xbm": large, "measure.json": b'{"parts":{}}', "kinematics.json": b"{}",
                 "names/ab.json": b'{"faceNames":["a"]}', "structure.json": b'{"prototypes":[]}',
                 "thumbnail.png": b"\x89PNG an earlier picture"}
        folder = _bundle(self.base / "a.view", files)
        share = self.share()
        sent = self.send(share, folder)
        committed = self.service.shares[share.id]["manifest"]["view"]
        order = ["manifest.json", "structure.json", "names/ab.json", "kinematics.json", "measure.json",
                 "parts/k/0.25-28.5.xbm", "parts/k/elements.json", "sheets/~2F.json"]
        self.assertEqual(sorted(committed), sorted(order))  # every file but the picture
        # The packs in the order they were made: the large file's member runs from the first into the second.
        # They go up concurrently, so the order they arrive in says nothing of it.
        named = [piece[0] for piece in committed["parts/k/0.25-28.5.xbm"]["at"]]
        self.assertEqual(len(set(named)), 2)
        self.assertEqual(sorted(seen[1].rsplit("/", 1)[1] for seen in self.service.puts("pack")), sorted(named))
        packs = self.service.shares[share.id]["packs"]
        self.assertEqual(len(packs[named[0]]), sharing.PACK_BYTES)
        self.assertEqual(sorted(committed, key=lambda path: (named.index(committed[path]["at"][0][0]),
                                                             committed[path]["at"][0][1])), order)
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

    def test_the_files_that_made_it_go_after_the_view_and_the_same_bytes_are_one_member(self) -> None:
        folder = _bundle(self.base / "a.view", {"structure.json": b'{"tree":1}', "source.stl": STL.encode()})
        sources = self.made({"plate.py": b"import lib\n", "lib/__init__.py": b"", "lib/more/__init__.py": b"",
                             "data/part.stl": STL.encode()})
        share = self.share()
        sent = self.send(share, folder, sources=sources)
        manifest = self.service.shares[share.id]["manifest"]
        self.assertEqual((manifest["name"], manifest["entry"], manifest["made"]),
                         ("arm", "plate.py", {"cad": "0.11.17", "build123d": "0.13.0"}))
        self.assertEqual(sorted(manifest["files"]), ["data/part.stl", "lib/__init__.py", "lib/more/__init__.py",
                                                     "plate.py"])
        # The same bytes, one member: the two empty modules, and the mesh the view holds as its own copy.
        self.assertEqual(manifest["files"]["lib/__init__.py"]["at"], manifest["files"]["lib/more/__init__.py"]["at"])
        self.assertEqual(manifest["files"]["data/part.stl"]["at"], manifest["view"]["source.stl"]["at"])
        # In one pack: the view's members first, in reading order, then the files that made it, by their paths.
        starts = sorted((entry["at"][0][1], kept, path) for kept in ("view", "files")
                        for path, entry in manifest[kept].items())
        self.assertEqual([(kept, path) for _offset, kept, path in starts
                          if (kept, path) not in (("files", "lib/more/__init__.py"), ("files", "data/part.stl"))],
                         [("view", "manifest.json"), ("view", "structure.json"), ("view", "source.stl"),
                          ("files", "lib/__init__.py"), ("files", "plate.py")])
        for path in manifest["files"]:
            self.assertEqual(self.service.read(share.id, path, "files"), (Path(sources.root) / path).read_bytes())
        self.assertEqual((sent.travelled["files"], len(self.service.shares[share.id]["packs"])), (7, 1))

        # A module changed: it alone of the files travels again; the others keep their ranges.
        before = json.loads(json.dumps(manifest["files"]))
        (Path(sources.root) / "lib" / "__init__.py").write_bytes(b"WIDTH = 4\n")
        changed = self.made({"plate.py": b"import lib\n", "lib/__init__.py": b"WIDTH = 4\n",
                             "lib/more/__init__.py": b"", "data/part.stl": STL.encode()})
        again = self.send(share, folder, sent.stored, sources=changed)
        after = self.service.shares[share.id]["manifest"]["files"]
        self.assertEqual({path for path in after if after[path]["at"] != before[path]["at"]}, {"lib/__init__.py"})
        self.assertEqual((again.travelled["files"], again.travelled["packs"]), (1, 1))

    def test_a_models_xbf_larger_than_a_pack_goes_split_over_packs_and_comes_back_whole(self) -> None:
        from cad_server import sharing

        folder = _bundle(self.base / "a.view", {"structure.json": b'{"tree":1}'})
        xbf = os.urandom(sharing.PACK_BYTES + MIB)  # gzip leaves it as large: its member is more than a pack
        sources = self.made({"plate.py": b"import lib\n", "plate.xbf": xbf})
        share = self.share()
        self.send(share, folder, sources=sources)
        manifest = self.service.shares[share.id]["manifest"]
        pieces = manifest["files"]["plate.xbf"]["at"]
        self.assertEqual(len({piece[0] for piece in pieces}), 2, pieces)  # its member runs from one pack into the next
        self.assertEqual(self.service.read(share.id, "plate.xbf", "files"), xbf)
        # And the share's zip, which an import downloads, holds it whole.
        with tempfile.TemporaryFile() as archive:
            sharing.download(self.service.url, share.id, archive)
            archive.seek(0)
            with zipfile.ZipFile(archive) as opened:
                self.assertEqual(opened.read("arm/plate.xbf"), xbf)

    def test_after_an_edit_only_what_changed_travels_and_the_rest_keeps_its_ranges(self) -> None:
        files = {"structure.json": b'{"tree":1}', "measure.json": b'{"m":1}', "names/a.json": b'{"faceNames":[]}',
                 "parts/k/0.xbm": os.urandom(4096), "parts/k/elements.json": b"[]"}
        folder = _bundle(self.base / "a.view", files)
        share = self.share()
        first = self.send(share, folder)
        before = json.loads(json.dumps(self.service.shares[share.id]["manifest"]["view"]))
        _bundle(folder, {**files, "structure.json": b'{"tree":2}'})
        packs = len(self.service.puts("pack"))
        second = self.send(share, folder, first.stored)
        after = self.service.shares[share.id]["manifest"]["view"]
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
        committed = self.service.shares[share.id]["manifest"]["view"]
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
        self.assertEqual([file.path for file in sharing.view_files(folder)], ["manifest.json", "structure.json"])
        entry = {"bytes": 2, "sha256": _sha(b"{}"), "type": "application/json"}
        for listed, said in (({"../structure.json": entry}, "no path a share takes"),
                             ({"/structure.json": entry}, "no path a share takes"),
                             ({"gone.json": entry}, "no regular file inside it"),
                             ({"structure.json": {**entry, "sha256": _sha(b"[]")}}, "not what its manifest says")):
            _bundle(folder, {"structure.json": b"{}"}, listed)
            with self.assertRaisesRegex(sharing.Unsharable, re.escape(said)):
                sharing.view_files(folder)
        if os.name != "nt":
            (self.base / "outside.json").write_bytes(b"{}")
            (folder / "linked.json").symlink_to(self.base / "outside.json")
            _bundle(folder, {"structure.json": b"{}"}, {"linked.json": entry})
            with self.assertRaisesRegex(sharing.Unsharable, "no regular file inside it"):
                sharing.view_files(folder)
        (folder / "manifest.json").unlink()
        with self.assertRaisesRegex(sharing.Unsharable, "no manifest.json"):
            sharing.view_files(folder)

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
        self.assertTrue((folder / "share.lock").is_file())  # a folder that holds a share's files keeps its lock
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
        # A file's folder holds what the cache keeps of the file beside a share's: its lock goes, and the folder stays.
        folder.mkdir()
        (folder / "note.json").write_text("{}", encoding="utf-8")
        with sharing.held(folder, make=lambda: folder.mkdir(exist_ok=True)):
            pass
        self.assertEqual([entry.name for entry in folder.iterdir()], ["note.json"])


class ImportTest(unittest.TestCase):
    """``cad import``, run as a person runs it, against a share this test makes on the stand-in service with no engine:
    a model's files, which a script among them would say it ran."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.service = Service()
        cls.addClassCleanup(cls.service.close)
        patch = mock.patch.dict(os.environ, NO_PROXY)
        patch.start()
        cls.addClassCleanup(patch.stop)

    def setUp(self) -> None:
        from cad_server import sharing

        self.service.reset()
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="import-")))
        self.addCleanup(shutil.rmtree, self.base, True)
        # Each script says, where it runs, that it did: an import runs none. The script's name is no ASCII, as the
        # service's header carries it. The model's .xbf, which names that script in its build closure, goes too.
        closure = {"schema": "cadgen.engine closure/2", "source": {"kind": "script", "path": "modèle.py",
                                                                    "function": "plate"}, "inputs": [], "key": None}
        self.files = {"modèle.py": "open('RAN', 'w').close()\nimport lib.sizes\n", "lib/__init__.py": "",
                      "lib/sizes.py": "open('RAN', 'w').close()\nWIDTH = 40\n", "data/hole é.json": '{"radius": 4}',
                      "plate.xbf": "cadgen.engine xbf/9 (cadgen 0.11.17)\x00"
                                   + json.dumps(closure, separators=(",", ":")) + "\x00"}
        project = _write(self.base / "project", self.files)
        view = _bundle(self.base / "plate.view", {"structure.json": b"{}"})
        # What built it: another release, on another system, and two members the header must carry as they are.
        self.made = {"cad": "0.0.1", "system": "Plan9", "empty": "", "odd, name": "a=b, c é+~/"}
        sources = sharing.Sources(tuple(sharing.File(path, _sha(data.encode()), len(data.encode()), project / path)
                                        for path, data in sorted(self.files.items())), "modèle.py", self.made,
                                  str(project))
        self.share = sharing.Share.new(self.service.url)
        sharing.send(self.share, sharing.view_files(view), sources, name="plate: the first")
        self.project = project
        self.here = self.base / "here"
        self.here.mkdir()
        # This computer's state: no record of the share, until a test writes one (``recorded``).
        self.state = self.base / "state"

    def import_(self, *args: str, **more: str) -> Any:
        return subprocess.run([sys.executable, "-m", "cad_server.cli", "import", *args], cwd=self.here,
                              env={**os.environ, "PYTHONPATH": SOURCE_PATH, "CAD_SHARE_URL": self.service.url,
                                   "CAD_TELEMETRY": "0", "CAD_UPDATE_CHECK": "0", "PYTHONIOENCODING": "utf-8",
                                   "CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.base / "engine"),
                                   **NO_PROXY, **more},
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                              timeout=engine_daemon.TIMEOUT_SECONDS)

    def recorded(self, path: Path | str, *, files: dict[str, Any] | None = None, service: str | None = None,
                 expires: str = "2030-01-08T00:00:00Z", kind: str = "xbf") -> None:
        """This computer's share, as ``cad share`` keeps it in the library: of the file at ``path``, at ``service``
        (the share's own by default), expiring at ``expires``, the files that made it where ``files`` says (by
        default, a model's in the project and a file document's beside it)."""
        from cad.engine.ids import file_id

        share = self.share
        if files is None:
            files = ({"root": str(self.project), "entry": "modèle.py"} if kind == "xbf" else
                     {"root": os.path.dirname(path), "entry": None})
        service = service or share.service
        _library(self.state, [{"id": share.id, "write": share.write, "delete": share.delete, "service": service,
                               "view": f"{service}/{share.id}", "expires": expires, "files": files,
                               "document": {"id": file_id(path), "path": str(path)}}])

    def downloads(self) -> list[str]:
        return [seen[1] for seen in self.service.seen if seen[0] == "GET"]

    def test_a_share_this_computer_made_is_pointed_at_and_nothing_is_downloaded_or_written(self) -> None:
        script, xbf = self.project / "modèle.py", self.project / "plate.xbf"
        self.recorded(xbf)
        for link in (self.share.view, self.share.zip, self.share.id):
            with self.subTest(link=link):
                done = self.import_(link)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(done.stdout, f"plate was shared from this computer: it is {xbf}, its files in "
                                              f"{self.project}, its script {script}. Nothing was downloaded; work "
                                              "there.\n")
        # A folder named is not written, and the answer says so.
        named = self.import_(self.share.view, "copy")
        self.assertIn("Nothing was downloaded, and copy was not written; work there.", named.stdout)
        found = json.loads(self.import_(self.share.view, "copy", "--json").stdout)
        self.assertEqual(found, {"ok": True, "local": True, "name": "plate", "file": str(xbf),
                                 "root": str(self.project), "entry": "modèle.py", "ignored": "copy",
                                 "next": [f"cad run {self.quoted(str(script))}"]})
        self.assertEqual((self.downloads(), list(self.here.iterdir())), ([], []))
        # A file document's: its own file.
        mesh = _write(self.base / "parts", {"tetra.stl": STL})
        self.recorded(mesh / "tetra.stl", kind="stl")
        self.assertEqual(self.import_(self.share.view).stdout, "tetra.stl was shared from this computer: it is "
                                                             f"{mesh / 'tetra.stl'}. Nothing was downloaded; work "
                                                             "there.\n")
        self.assertEqual(json.loads(self.import_(self.share.view, "--json").stdout)["next"],
                         [f"cad viewer {self.quoted(str(mesh / 'tetra.stl'))}"])
        self.assertEqual(self.downloads(), [])

    def test_a_record_of_another_service_expired_or_whose_file_moved_is_downloaded_as_any_link(self) -> None:
        here = self.project / "plate.xbf"
        for name, path, more in (("another service's", here, {"service": "http://127.0.0.1:1"}),
                                 ("expired", here, {"expires": "2020-01-01T00:00:00Z"}),
                                 ("its file moved", self.base / "moved" / "plate.xbf", {})):
            with self.subTest(name):
                self.recorded(path, **more)
                done = self.import_(self.share.view, name, "--json")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertFalse(json.loads(done.stdout)["local"])
                self.assert_written(self.here / name)
        self.assertEqual(len(self.downloads()), 3)

    def assert_written(self, folder: Path) -> None:
        self.assertEqual(sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()),
                         sorted(self.files))
        for path, data in self.files.items():
            self.assertEqual((folder / path).read_bytes(), data.encode(), path)

    @staticmethod
    def quoted(path: str) -> str:
        """A path as a person pastes it into this platform's shell."""
        return subprocess.list2cmdline([path]) if os.name == "nt" else shlex.quote(path)

    def test_a_import_writes_the_files_says_what_built_them_and_runs_nothing(self) -> None:
        import platform

        from cad.engine import previous

        size = sum(len(data.encode()) for data in self.files.values())
        done = self.import_(self.share.view)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assert_written(self.here / "plate__the_first")  # its folder, named as the zip names it
        # The shared file it wrote is in the library, this user's alone, with the link it came from, by which the
        # share's link names it here: the .xbf whose closure names the share's script.
        self.assertEqual(self.imports(), [{"link": self.share.view,
                                         "path": str(self.here / "plate__the_first" / "plate.xbf")}])
        lines = done.stdout.splitlines()
        self.assertEqual(lines[0], f"Imported plate__the_first into plate__the_first: 5 files, {size} B; it is "
                                   "plate.xbf; its script is modèle.py")
        self.assertEqual(lines[1], f"Made with cad 0.0.1, system Plan9, where this computer has cad {previous.version()}, "
                                   f"system {platform.system()}: a build here may differ from the shared view")
        self.assertEqual(lines[2], "Nothing was run: the code is someone else's, the person's to read and run. Next: "
                                   f"cad viewer {self.quoted(os.path.join('plate__the_first', 'plate.xbf'))} shows it "
                                   "as it was shared; "
                                   f"cad run {self.quoted(os.path.join('plate__the_first', 'modèle.py'))} builds it here")
        # No project, and of its files the shared one alone: an import writes its files, and its entry.
        library = json.loads((self.state / "library.json").read_text(encoding="utf-8"))
        self.assertEqual((library["projects"], len(library["files"])), ({}, 1))
        self.assertEqual(list(self.here.rglob("RAN")), [])
        self.assertEqual(list(self.here.rglob("__pycache__")), [])
        self.assertEqual([seen[1] for seen in self.service.seen if seen[0] == "GET"], [f"/{self.share.id}.zip"])
        # By its files' link and by its id alone, into a folder named: the same files, and --json's one object.
        named = self.import_(self.share.zip, "zipped")
        self.assertEqual(named.returncode, 0, named.stdout + named.stderr)
        self.assert_written(self.here / "zipped")
        as_json = self.import_(self.share.id, str(self.here / "by id"), "--json")
        self.assertEqual(as_json.returncode, 0, as_json.stdout + as_json.stderr)
        self.assert_written(self.here / "by id")
        found = json.loads(as_json.stdout)
        self.assertEqual(set(found), {"ok", "local", "folder", "name", "files", "file", "entry", "missing", "made",
                                      "here", "differs", "next"})
        self.assertEqual((found["local"], found["missing"]), (False, []))
        self.assertEqual((found["folder"], found["name"], found["file"], found["entry"]),
                         (str(self.here / "by id"), "plate__the_first", "plate.xbf", "modèle.py"))
        self.assertEqual(found["files"], {"count": 5, "bytes": size, "paths": sorted(self.files)})
        self.assertEqual(found["made"], self.made)  # as the share holds it, each member as it is
        self.assertEqual([row["name"] for row in found["differs"]], ["cad", "system"])
        self.assertEqual(found["next"], [f"cad viewer {self.quoted(str(self.here / 'by id' / 'plate.xbf'))}",
                                         f"cad run {self.quoted(str(self.here / 'by id' / 'modèle.py'))}"])
        # One entry a share's link: the latest import of it.
        self.assertEqual(self.imports(), [{"link": self.share.view, "path": str(self.here / "by id" / "plate.xbf")}])

    def imports(self) -> list[dict[str, Any]]:
        """The files the library keeps with the link they came from (``imported``), in a file this user alone may read
        or write."""
        path = self.state / "library.json"
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        found = json.loads(path.read_text(encoding="utf-8"))
        return [{"link": entry["imported"], "path": entry["path"]} for entry in found["files"].values()
                if "imported" in entry]

    def test_a_link_names_the_copy_this_computer_keeps_and_is_refused_where_it_keeps_none(self) -> None:
        """Wherever cad takes a document, a share's link of this service or of cad.fun names this computer's copy of
        it, as the library holds it: the file it shared under the link, a selector after it kept; else the file a
        import of it wrote that the share is of -- a model's .xbf, a file document's file --, the latest import of it; and
        with neither, or an import whose file is gone, refused in one line naming the import. Another origin's link, or a
        files' link, names no document."""
        from cad_server import sharing

        view = self.share.view
        refusal = (f"{view} is a shared model this computer has no copy of: run `cad import {view}`.",
                   (f"cad import {view}",))
        with mock.patch.dict(os.environ, {"CAD_SHARE_URL": self.service.url, "CAD_STATE_DIR": str(self.state)}):
            with self.assertRaises(sharing.NoCopy) as none:
                sharing.local(f"{view}#plate")
            self.assertEqual((str(none.exception), none.exception.next), refusal)
            for named in (f"https://elsewhere.example/{self.share.id}", self.share.zip, "plate.step#plate", DOCUMENT):
                self.assertEqual(sharing.local(named), named)
            self.assertEqual(sharing.document_link(f"https://cad.fun/{self.share.id}#plate/face 1"),
                             ("https://cad.fun", self.share.id, "plate/face 1"))

            # Shared from here: the file it shared, by its path; a ref's file JSON-quoted where its path holds a '#'.
            xbf = self.project / "plate.xbf"
            self.recorded(xbf)
            self.assertEqual((sharing.local(view), sharing.local(f"{view}#plate/face 1", ref=True)),
                             (str(xbf), f"{xbf}#plate/face 1"))
            mesh = _write(self.base / "parts#1", {"tetra.stl": STL}) / "tetra.stl"
            self.recorded(mesh, kind="stl")
            self.assertEqual((sharing.local(view), sharing.local(f"{view}#tetra", ref=True)),
                             (str(mesh), f"{json.dumps(str(mesh), ensure_ascii=False)}#tetra"))

            # Imported: the file of the import's that the share is of, the .xbf there with nothing run; the latest import of
            # a link the one entry that holds it; an import whose file is gone, no copy.
            _library(self.state, [])
            copy = _write(self.here / "copy", self.files)
            self.assertEqual(sharing.shared_file(copy, sorted(self.files), "modèle.py"), "plate.xbf")
            sharing.change({"imported": sharing.import_record(self.service.url, self.share.id, copy / "plate.xbf")})
            self.assertEqual(sharing.local(f"{view}#plate"), f"{copy / 'plate.xbf'}#plate")
            sharing.change({"imported": sharing.import_record(self.service.url, self.share.id, mesh)})
            self.assertEqual(sharing.local(view), str(mesh))
            self.assertEqual(self.imports(), [{"link": view, "path": str(mesh)}])
            mesh.unlink()
            with self.assertRaises(sharing.NoCopy) as gone:
                sharing.local(view)
            self.assertEqual((str(gone.exception), gone.exception.next), refusal)
            sharing.change({"imported": sharing.import_record(self.service.url, self.share.id, copy / "plate.xbf")})
            shutil.rmtree(copy)
            with self.assertRaises(sharing.NoCopy) as moved:
                sharing.local(view)
            self.assertEqual((str(moved.exception), moved.exception.next), refusal)

    def test_the_shared_file_of_a_import_is_the_xbf_its_script_builds_or_a_file_documents_file(self) -> None:
        from cad_server import sharing

        def xbf(script: str, *read: str) -> str:
            closure = {"schema": "cadgen.engine closure/2", "source": {"kind": "script", "path": script},
                       "inputs": [["file", path, "c" * 32] for path in read]}
            return "cadgen.engine xbf/9 (cadgen 0.11.17)\x00" + json.dumps(closure, separators=(",", ":")) + "\x00"

        # Of a model: the .xbf whose closure names the share's script, from its own folder; of two, the one no other
        # read (a model that read another of its script's).
        folder = _write(self.base / "model", {"src/arm.py": "", "XBF/arm.xbf": xbf("../src/arm.py", "base.xbf"),
                                              "XBF/base.xbf": xbf("../src/arm.py"), "XBF/other.xbf": xbf("other.py")})
        paths = ["XBF/arm.xbf", "XBF/base.xbf", "XBF/other.xbf", "src/arm.py"]
        self.assertEqual(sharing.shared_file(folder, paths, "src/arm.py"), "XBF/arm.xbf")
        self.assertIsNone(sharing.shared_file(folder, ["XBF/other.xbf", "src/arm.py"], "src/arm.py"))
        # Of a file document: the one SRDF at its top, else the one URDF, else its one file.
        robot = ["arm.srdf", "arm.urdf", "meshes/base.stl"]
        self.assertEqual(sharing.shared_file(self.base, robot, None), "arm.srdf")
        self.assertEqual(sharing.shared_file(self.base, robot[1:], None), "arm.urdf")
        self.assertEqual(sharing.shared_file(self.base, ["tetra.stl"], None), "tetra.stl")
        self.assertIsNone(sharing.shared_file(self.base, ["a.stl", "b.stl"], None))
        # Of a KiCad project: the one board among its files; of a schematic's sheets, the root of their hierarchy, the
        # one beside a project file of its name, else the one no other draws as a sheet (KiCad's Sheetfile).
        board = ["blinky.kicad_pcb", "blinky.kicad_pro", "lib/blinky.pretty/R.kicad_mod", "models/led.step"]
        self.assertEqual(sharing.shared_file(self.base, board, None), "blinky.kicad_pcb")
        sheet = '(kicad_sch (sheet (property "Sheetfile" "{}")))'
        sheets = _write(self.base / "sheets", {"top.kicad_sch": sheet.format("sub/power.kicad_sch"),
                                                "sub/power.kicad_sch": sheet.format("../io.kicad_sch"),
                                                "io.kicad_sch": "(kicad_sch)", "lone.kicad_sch": "(kicad_sch)"})
        self.assertEqual(sharing.shared_file(sheets, ["io.kicad_sch", "sub/power.kicad_sch", "top.kicad_sch"], None),
                         "top.kicad_sch")
        self.assertIsNone(sharing.shared_file(sheets, ["io.kicad_sch", "lone.kicad_sch", "top.kicad_sch",
                                                       "sub/power.kicad_sch"], None))
        _write(sheets, {"lone.kicad_pro": "{}"})
        self.assertEqual(sharing.shared_file(sheets, ["io.kicad_sch", "lone.kicad_pro", "lone.kicad_sch",
                                                      "sub/power.kicad_sch", "top.kicad_sch"], None), "lone.kicad_sch")

    def test_what_this_computer_cannot_say_of_its_libraries_is_said_not_compared(self) -> None:
        from cad_server.cli import import_ as command

        here = {"cad": "0.0.1", "build123d": None, "OCP": None, "python": None, "system": "Plan9", "arch": "x"}
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CAD_SHARE_URL": self.service.url, "CAD_STATE_DIR": str(self.state)}), \
                mock.patch.object(command, "_here", return_value=here), contextlib.redirect_stdout(out):
            self.assertEqual(command.main([self.share.id, str(self.here / "kept")]), 0)
        self.assertEqual(out.getvalue().splitlines()[1:], [
            "Made with the cad and libraries this computer has",
            f"Nothing was run: the code is someone else's, the person's to read and run. Next: "
            f"cad viewer {self.quoted(str(self.here / 'kept' / 'plate.xbf'))} shows it as it was shared; "
            f"cad run {self.quoted(str(self.here / 'kept' / 'modèle.py'))} builds it here"])
        self.made["build123d"] = "0.13.0"
        with self.subTest("a library this computer's kernel environment has not said"):
            from cad_server import sharing

            view = _bundle(self.base / "again.view", {"structure.json": b"{}"})
            sharing.send(self.share, sharing.view_files(view), sharing.Sources(
                tuple(sharing.File(path, _sha(data.encode()), len(data.encode()), self.base / "project" / path)
                      for path, data in sorted(self.files.items())), "modèle.py", self.made, str(self.base)),
                name="plate")
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"CAD_SHARE_URL": self.service.url, "CAD_STATE_DIR": str(self.state)}), \
                    mock.patch.object(command, "_here", return_value=here), contextlib.redirect_stdout(out):
                self.assertEqual(command.main([self.share.id, str(self.here / "unsaid")]), 0)
            self.assertEqual(out.getvalue().splitlines()[1], "Made with build123d 0.13.0: this computer's CAD kernel "
                                                             "environment is made with its first build, so those were "
                                                             "not compared")

    def test_a_folder_that_holds_files_is_refused_and_a_share_gone_is_said(self) -> None:
        (self.here / "taken").mkdir()
        (self.here / "taken" / "mine.txt").write_text("mine", encoding="utf-8")
        (self.here / "a file").write_text("mine", encoding="utf-8")
        for folder in ("taken", "a file"):
            with self.subTest(folder=folder):
                refused = self.import_(self.share.view, folder, "--json")
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertEqual(json.loads(refused.stdout)["reason"], "invalid_argument")
        self.assertEqual(self.service.seen[-1][0], "PUT", "refused before anything was downloaded")
        self.assertEqual(sorted(path.name for path in (self.here / "taken").iterdir()), ["mine.txt"])
        (self.here / "empty").mkdir()
        self.assertEqual(self.import_(self.share.view, "empty").returncode, 0)
        self.assert_written(self.here / "empty")
        gone = self.import_(f"{self.service.url}/{'A' * 22}", "--json")
        self.assertEqual(gone.returncode, 2, gone.stdout + gone.stderr)
        self.assertEqual(json.loads(gone.stdout), {"ok": False, "error": "This shared model has expired or was "
                                                                         "deleted.", "reason": "not_found"})
        for link in ("https://cad.fun/nope", "not a link"):
            self.assertEqual(json.loads(self.import_(link, "--json").stdout)["reason"], "invalid_argument")

    def test_an_entry_that_would_land_outside_its_folder_is_refused_and_nothing_is_left(self) -> None:
        def crafted(*entries: tuple[str, bytes, int]) -> bytes:
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as made:
                for name, body, mode in entries:
                    info = zipfile.ZipInfo(name)
                    info.external_attr = mode << 16
                    made.writestr(info, body)
            return data.getvalue()

        regular = 0o100644
        for name, said, zipped in (
                ("a ..", "no path inside its folder",
                 crafted(("plate/ok.py", b"", regular), ("plate/../escaped.py", b"x", regular))),
                ("an absolute path", "no path inside its folder",
                 crafted(("plate/ok.py", b"", regular), ("/tmp/escaped.py", b"x", regular))),
                ("a drive", "no path inside its folder", crafted(("plate/C:escaped.py", b"x", regular),)),
                ("a backslash", "no path inside its folder", crafted(("plate/..\\escaped.py", b"x", regular),)),
                # A name that zipfile reads as up to its NUL, and another tool may read whole.
                ("a NUL", "no path inside its folder",
                 _zipped("plate", [("ok.py\x00/../../escaped.py", gzip.compress(b"x", mtime=0))])),
                ("a link", "is a link",
                 crafted(("plate/ok.py", b"", regular), ("plate/link", b"/etc/passwd", 0o120777))),
                ("outside the folder", "outside the one folder",
                 crafted(("plate/ok.py", b"", regular), ("other/escaped.py", b"x", regular))),
                ("a file and a folder of one name", "lies in a folder that is a file of it",
                 crafted(("plate/a", b"", regular), ("plate/a/b", b"", regular))),
                ("no folder", "outside the one folder", crafted(("escaped.py", b"x", regular),))):
            with self.subTest(name):
                self.service.zips[self.share.id] = zipped
                refused = self.import_(self.share.view, "--json")
                self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
                self.assertIn("did not arrive as a share's zip", json.loads(refused.stdout)["error"])
                self.assertIn(said, json.loads(refused.stdout)["error"])
                self.assertEqual(list(self.here.iterdir()), [])
                self.assertFalse((self.base / "escaped.py").exists())
        # A version control's folder, or a repository's bare form, which would make a later command where it is
        # written (git status, a shell prompt's) run what its settings name: refused whole, whoever made the zip (a
        # share service of another origin may name its one folder too), and nothing is written.
        config = b'[core]\n\tfsmonitor = "touch RAN; false"\n'
        repository = [("HEAD", b"ref: refs/heads/main\n", regular), ("config", config, regular),
                      ("objects/info/packs", b"", regular), ("refs/heads/.keep", b"", regular)]
        for name, zipped in (
                ("a .git", crafted(("plate/ok.py", b"", regular),
                                   *((f"plate/.git/{path}", body, mode) for path, body, mode in repository))),
                ("its one folder .git", crafted(*((f".git/{path}", body, mode) for path, body, mode in repository))),
                ("a .git deeper", crafted(("plate/sub/.git/config", config, regular),)),
                ("as Windows reads it", crafted(("plate/.GIT. /config", config, regular),)),
                ("its short name", crafted(("plate/git~1/config", config, regular),)),
                ("an NTFS stream", crafted(("plate/.git::$INDEX_ALLOCATION/config", config, regular),)),
                ("as HFS+ reads it", crafted(("plate/.g‌it/config", config, regular),)),
                ("Mercurial's", crafted(("plate/.hg/hgrc", b"[hooks]\npre-status = touch RAN\n", regular),)),
                ("a bare repository", crafted(*((f"plate/{path}", body, mode) for path, body, mode in repository))),
                ("a bare repository deeper", crafted(("plate/ok.py", b"", regular),
                                                     *((f"plate/a/{path}", body, mode) for path, body, mode
                                                       in repository)))):
            with self.subTest(name):
                self.service.zips[self.share.id] = zipped
                refused = self.import_(self.share.view, "--json")
                self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
                said = json.loads(refused.stdout)
                self.assertRegex(said["error"], r"^the share's files cannot be imported: it holds .+(, of a version "
                                                r"control's folder| beside objects and refs, a repository's bare "
                                                r"form), which would make a later command there, such as git status, "
                                                r"run what it names; nothing was written$")
                self.assertEqual(list(self.here.iterdir()), [])
        # A FOLDER in a version control's folder, or one that would make its own a repository's bare form.
        self.service.zips.pop(self.share.id)
        downloaded = len(self.downloads())
        (self.here / "repo" / ".git").mkdir(parents=True)
        (self.here / "bare" / "refs").mkdir(parents=True)
        (self.here / "bare" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        for folder in ("repo/.git/hooks", ".git", "repo/.GIT.", "bare/objects", "bare/Objects"):
            with self.subTest(folder=folder):
                refused = self.import_(self.share.view, folder, "--json")
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertIn("cad import writes no version control's files, so nothing was written",
                              json.loads(refused.stdout)["error"])
        self.assertEqual(sorted(str(path.relative_to(self.here)) for path in self.here.rglob("*")),
                         ["bare", "bare/HEAD", "bare/refs", "repo", "repo/.git"])
        self.assertEqual(len(self.downloads()), downloaded)
        shutil.rmtree(self.here)
        self.here.mkdir()
        # A file whose bytes are not its CRC's: refused once it is read, and nothing of it, or of the others, stays.
        good = bytearray(_zipped("plate", [("a.py", gzip.compress(b"print(1)\n", mtime=0)),
                                           ("b.py", gzip.compress(b"print(2)\n" * 50, mtime=0))]))
        good[good.index(b"PK\x01\x02") - 3] ^= 0xFF  # a byte of the last file's deflate stream, before the directory
        self.service.zips[self.share.id] = bytes(good)
        broken = self.import_(self.share.view, "--json")
        self.assertEqual(broken.returncode, 1, broken.stdout + broken.stderr)
        self.assertEqual(list(self.here.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
