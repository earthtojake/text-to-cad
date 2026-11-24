"""Sharing a document: its view bundle kept in cad's cache, and the files of it its share lacks uploaded to the share
service, for anyone with its link to open in the hosted viewer (``cad share``, ``cad_server.cli.share``; the engine's
**Sharing**).

What is here is the client's half of the protocol, ``cad-share/2``, the standard library alone:

- **names** (``Share.new``): a share's id (16 random bytes), its write secret and its delete secret (32 each), every
  one from ``secrets``, base64url without padding. The id is the capability: the service derives from it the key it
  seals the share with, and keeps neither; of the two secrets it keeps only each one's SHA-256 (``digest``);
- **links** (``Share.view``, ``Share.remove``): ``<origin>/<id>``, and ``<origin>/<id>#delete=<secret>``, whose part
  after ``#`` no browser sends to a server;
- **the files** (``files``): ``manifest.json`` and every file it lists but ``LEFT_OUT``'s, each a path the protocol
  takes (``sharable``), a regular file inside the bundle and the bytes the manifest says, in reading order
  (``reading``): the bundle is taken as its manifest lists it, and nothing else of it is read;
- **the packs** (``Packer``): each file the share lacks as one gzip member (RFC 1952: mtime 0, no name), back to
  back, a pack closed at ``PACK_BYTES`` and a member that does not fit the room left going on into the next; a pack
  is named by the lowercase hex SHA-256 of its bytes;
- **the API** (``send``, ``delete``): ``PUT /v1/shares/<id>/packs/<pack id>``, ``UPLOADS`` at a time as each pack
  closes, then the commit of the share's manifest, ``PUT /v1/shares/<id>``; and ``DELETE /v1/shares/<id>``. With
  ``urllib``, in the calling process, so an agent app's sandbox sees the connection and its network rules apply;
  proxies as ``urllib`` takes them from the environment. A 429 waits for its ``Retry-After``; a commit's 409 that
  names missing packs sends the files in them again (``RESENDS`` times at most), and one that names none commits
  again, once. A connection that cannot be made, or an answer that is not the service's (a proxy's refusal: no JSON
  ``error``), is ``Unreachable``; the service's own refusal is ``Refused``, with its ``error`` and ``hint``;
- **what is kept** (``change``): the person's agreement and whether sharing is on (the settings' ``share`` section:
  ``{"agreed": <ISO time>, "on": false}``, on where ``on`` is absent); each share's record (``shares.json`` in the
  state folder, readable and writable by this user alone: ``RECORDS``); and each shared document's folder in the
  cache (``folder_of``): its bundle (``BUNDLE``), written over at each share; where each file of the share's last
  commit lives (``STORED``); and the lock one ``cad share`` of the document holds at a time (``held``). A command
  asks the running server to write them (``{"op": "share"}``: ``answer``), as it does every other write a shell's
  sandbox may be refused, and writes them itself where none answers. As the records are written, a folder that no
  live record names is removed: a share deleted, expired, or never committed.

The id and the two secrets leave this module only inside the two links, in a record, and where the protocol puts them
in a request -- the id in its path, the write secret as its ``Authorization``, the delete secret as a hash, or as a
delete's ``Authorization`` --: never in an exception's words, a log, telemetry or the cache, where ``STORED`` names a
share by its id's SHA-256 (``Share.named``).
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

FORMAT = "cad-share/2"
RECORDS = "shares.json"
RECORDS_FORMAT = "cad-shares/1"
SECTION = "share"
EXPIRY_DAYS = 7
# The cache's folder of shared documents, one each by its document id, and what each holds.
SHARES = "shares"
BUNDLE = "bundle.view"
STORED = "stored.json"
LOCK = "lock"
MANIFEST = "manifest.json"
# Left out of every share: the picture a page last kept, which may be of an earlier version of the document.
LEFT_OUT = frozenset({"thumbnail.png"})
# Where a pack is closed: half the most a pack may be by the service's default (``MAX_PACK_BYTES``, 8 MiB).
PACK_BYTES = 4 * 1024 * 1024
# How many packs are uploaded at a time.
UPLOADS = 4
# The most files a share holds, and the longest path of one, in bytes of UTF-8 (the protocol's).
MOST_FILES = 200_000
PATH_BYTES = 1024
# How many times a commit's 409 naming missing packs has their files sent again before the share fails.
RESENDS = 2
# A 429's waits for one request: each its ``Retry-After`` (``WAIT`` where it names none), of ``LONGEST_WAIT`` at most.
WAITS = 10
WAIT = 5.0
LONGEST_WAIT = 120.0
# How long one request may take: a pack of ``PACK_BYTES`` over a slow link.
TIMEOUT_SECONDS = 120.0
# The most of an answer read: every answer of the API is a small JSON object, the longest a 409's missing packs.
ANSWER_BYTES = 1024 * 1024
# How often a wait for another holder of a document's lock looks again.
_POLL_SECONDS = 0.1

_ID = re.compile(r"[A-Za-z0-9_-]{22}")
_SECRET = re.compile(r"[A-Za-z0-9_-]{43}")
_HEX = re.compile(r"[0-9a-f]{64}")


class Unsharable(ValueError):
    """A bundle a share cannot hold as the protocol says: its words."""


class Unreachable(ConnectionError):
    """No answer of the service's: the connection could not be made, or something else answered for it."""


class Refused(Exception):
    """The service's own refusal of ``what`` (``a pack``, ``the share's manifest``, ``the delete``): its status,
    ``error`` and ``hint``, and the packs a commit's 409 found missing (``missing``)."""

    def __init__(self, status: int, error: str, hint: str = "", *, what: str = "the request",
                 missing: tuple[str, ...] = ()) -> None:
        super().__init__(f"{error} ({hint})" if hint else error)
        self.status, self.error, self.hint, self.what, self.missing = status, error, hint, what, missing


class Busy(Exception):
    """Another holder kept a document's lock for the whole of the wait (``held``)."""


def _token(size: int) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(size)).rstrip(b"=").decode("ascii")


def digest(secret: str) -> str:
    """A secret as the service keeps it: the lowercase hex SHA-256 of its 43-character text (its ASCII bytes), never
    of the bytes it decodes to; the service hashes an ``Authorization`` bearer's text the same way."""
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Share:
    """One share's names: its id and its two secrets (the module), and the origin it lives at."""

    service: str
    id: str
    write: str
    delete: str

    @classmethod
    def new(cls, service: str) -> Share:
        return cls(service, _token(16), _token(32), _token(32))

    @property
    def view(self) -> str:
        """The view link: the id is the capability, so the link holds nothing else."""
        return f"{self.service}/{self.id}"

    @property
    def remove(self) -> str:
        return f"{self.service}/{self.id}#delete={self.delete}"

    @property
    def named(self) -> str:
        """The share as the cache names it (``STORED``): its id's lowercase hex SHA-256, never the id."""
        return hashlib.sha256(self.id.encode("ascii")).hexdigest()

    def __repr__(self) -> str:  # never the id or a secret, wherever a share is printed
        return f"Share({_host(self.service)!r})"


# --- the files ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class File:
    """One file of a bundle that a share holds: its path in the bundle, its bytes' SHA-256 and size, and where it is."""

    path: str
    sha256: str
    size: int
    source: Path

    def read(self) -> bytes:
        """Its bytes, still the ones ``files`` read (``Unsharable`` for a bundle changed since)."""
        data = self.source.read_bytes()
        if len(data) != self.size or hashlib.sha256(data).hexdigest() != self.sha256:
            raise Unsharable(f"the view bundle's {self.path} changed while it was shared: share it again")
        return data


def sharable(path: object) -> bool:
    """Whether ``path`` is one a share's manifest takes: relative, ``/`` separated, with no empty, ``.`` or ``..``
    segment, at most ``PATH_BYTES`` bytes of UTF-8 (the protocol's); and, so that it names one file on every system,
    printable, with no ``\\`` or ``:``."""
    if not isinstance(path, str) or not path or not path.isprintable() or "\\" in path or ":" in path:
        return False
    try:
        size = len(path.encode("utf-8"))
    except UnicodeEncodeError:
        return False
    return size <= PATH_BYTES and all(part not in ("", ".", "..") for part in path.split("/"))


def reading(file: File) -> tuple[int, str]:
    """A file's place in the order a page reads a bundle, which new files are packed in: ``manifest.json``,
    ``structure.json``, ``names/...``, the other files at the bundle's root, the meshes (``parts/...`` but each part's
    ``elements.json``, and ``meshes/...``), each part's ``elements.json``, then the rest; by path within each."""
    path = file.path
    if path == MANIFEST:
        place = 0
    elif path == "structure.json":
        place = 1
    elif path.startswith("names/"):
        place = 2
    elif "/" not in path:
        place = 3
    elif path.startswith("parts/") and path.rsplit("/", 1)[1] == "elements.json":
        place = 5
    elif path.startswith(("parts/", "meshes/")):
        place = 4
    else:
        place = 6
    return place, path


def _digest_of(path: Path) -> tuple[str, int]:
    found, size = hashlib.sha256(), 0
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            found.update(chunk)
            size += len(chunk)
    return found.hexdigest(), size


def files(folder: Path) -> list[File]:
    """The files of the bundle in ``folder`` that a share holds, in reading order (``reading``): ``manifest.json``, and
    every file it lists but ``LEFT_OUT``'s, each a path a share takes (``sharable``), a regular file inside the folder
    and the bytes the manifest says (its ``sha256`` and ``bytes``). Anything else is ``Unsharable``, in its words."""
    manifest = folder / MANIFEST
    try:
        raw = manifest.read_bytes()
    except FileNotFoundError:
        raise Unsharable("the folder holds no view bundle: it has no manifest.json") from None
    try:
        listed = json.loads(raw.decode("utf-8")).get("files")
    except (UnicodeDecodeError, ValueError, AttributeError):
        listed = None
    if not isinstance(listed, dict):
        raise Unsharable("the view bundle's manifest.json lists no files")
    if len(listed) + 1 > MOST_FILES:
        raise Unsharable(f"the view bundle holds {len(listed) + 1} files, more than the {MOST_FILES} a share holds")
    root = os.path.realpath(folder)
    found = [File(MANIFEST, hashlib.sha256(raw).hexdigest(), len(raw), manifest)]
    for path, entry in listed.items():
        if path in LEFT_OUT or path == MANIFEST:
            continue
        if not sharable(path):
            raise Unsharable(f"the view bundle names {path!r}, which is no path a share takes")
        source = folder / path
        if os.path.islink(source) or not source.is_file() \
                or not os.path.realpath(source).startswith(root + os.sep):
            raise Unsharable(f"the view bundle's {path} is no regular file inside it")
        sha256, size = _digest_of(source)
        if not isinstance(entry, dict) or (entry.get("sha256"), entry.get("bytes")) != (sha256, size):
            raise Unsharable(f"the view bundle's {path} is not what its manifest says: share it again")
        found.append(File(path, sha256, size, source))
    return sorted(found, key=reading)


def bundle(target: str, folder: Path) -> dict[str, Any]:
    """``target``'s view bundle (a document id the engine holds, or a file's path) written into ``folder`` by the
    running server, as ``cad <type> export TARGET DST.view`` writes one (the engine's **View bundle**), over the one it
    holds: its manifest. Called from here, never from a ``__main__``, so the export says nothing of the folder it
    wrote."""
    from cad.engine import api

    api.export(target, folder)
    return json.loads((folder / MANIFEST).read_text(encoding="utf-8"))


# --- the packs ---------------------------------------------------------------------------------------------------


def member(data: bytes) -> bytes:
    """``data`` as one gzip member (RFC 1952): deflated at level 6, mtime 0, no file name."""
    return gzip.compress(data, compresslevel=6, mtime=0)


class Packer:
    """Gzip members laid back to back in packs (the module): ``add`` puts a file's member and answers the packs it
    closed, each ``(pack id, bytes)``, ``finish`` the last; ``at`` says, once every pack is closed, where each file's
    member lies: ``[pack id, offset, length]`` for each of its pieces, in order."""

    def __init__(self, size: int = PACK_BYTES) -> None:
        self.size = size
        self.names: list[str] = []
        self._pieces: dict[str, list[tuple[int, int, int]]] = {}
        self._buffer = bytearray()

    def add(self, sha256: str, data: bytes) -> list[tuple[str, bytes]]:
        closed = []
        pieces = self._pieces[sha256] = []
        view, start = memoryview(data), 0
        while start < len(data):
            piece = view[start:start + self.size - len(self._buffer)]
            pieces.append((len(self.names), len(self._buffer), len(piece)))
            self._buffer += piece
            start += len(piece)
            if len(self._buffer) == self.size:
                closed.append(self._close())
        return closed

    def finish(self) -> list[tuple[str, bytes]]:
        return [self._close()] if self._buffer else []

    def _close(self) -> tuple[str, bytes]:
        pack = bytes(self._buffer)
        self._buffer = bytearray()
        self.names.append(hashlib.sha256(pack).hexdigest())
        return self.names[-1], pack

    @property
    def at(self) -> dict[str, list[list[Any]]]:
        return {sha256: [[self.names[pack], offset, length] for pack, offset, length in pieces]
                for sha256, pieces in self._pieces.items()}


# --- the API -----------------------------------------------------------------------------------------------------


def _answer(raw: bytes) -> dict[str, Any] | None:
    try:
        found = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def _host(service: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(service).netloc or service


def _scrubbed(text: str, share: Share) -> str:
    """``text`` with no name of ``share``'s in it: what an exception says of a request may quote its address."""
    for name in (share.id, share.write, share.delete):
        if name:
            text = text.replace(name, "...")
    return text


def _call(method: str, share: Share, path: str, headers: dict[str, str], body: bytes | None = None,
          timeout: float = TIMEOUT_SECONDS) -> tuple[int, dict[str, Any] | None, str | None]:
    """One request of the API, from this process: its status, its JSON answer (None for none) and its
    ``Retry-After``. A connection that cannot be made, or a refusal that is not the service's -- no JSON ``error``, as a
    proxy's is -- is ``Unreachable``, in words that hold no name of the share's."""
    import http.client
    import urllib.error
    import urllib.request

    host = _host(share.service)
    url = f"{share.service}/v1/shares/{share.id}{path}"
    request = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": "cad", **headers})
    try:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310 - http(s) only (``share_url``)
                return answer.status, _answer(answer.read(ANSWER_BYTES)), answer.headers.get("Retry-After")
        except urllib.error.HTTPError as refusal:
            found = _answer(refusal.read(ANSWER_BYTES))
            if found is None or not isinstance(found.get("error"), str):
                raise Unreachable(f"something other than the share service answered for {host} "
                                  f"(HTTP {refusal.code})") from None
            return refusal.code, found, refusal.headers.get("Retry-After")
    except Unreachable:
        raise
    except TimeoutError:
        raise Unreachable(f"{host} did not answer within {timeout:.0f} seconds") from None
    except urllib.error.URLError as error:
        raise Unreachable(f"{host} could not be reached ({_scrubbed(str(error.reason), share)})") from None
    except (OSError, http.client.HTTPException) as error:
        raise Unreachable(f"{host} could not be reached ({type(error).__name__}: "
                          f"{_scrubbed(str(error), share)})") from None


def _seconds(after: str | None) -> float:
    """A ``Retry-After``'s wait: its seconds, or until its HTTP date; ``WAIT`` where it names neither."""
    text = (after or "").strip()
    if text.isdigit():
        return float(text)
    from email.utils import parsedate_to_datetime

    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return WAIT
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def _asked(method: str, share: Share, path: str, headers: dict[str, str], body: bytes | None,
           waiting: Callable[[float], None] | None) -> tuple[int, dict[str, Any] | None]:
    """``_call``, asked again after each 429's ``Retry-After`` (``waiting`` told the seconds first), ``WAITS`` times at
    most and never past ``LONGEST_WAIT``: the status and the answer of the last."""
    for attempt in range(WAITS + 1):
        status, found, after = _call(method, share, path, headers, body)
        seconds = _seconds(after)
        if status != 429 or attempt == WAITS or seconds > LONGEST_WAIT:
            break
        if waiting is not None:
            waiting(seconds)
        time.sleep(seconds)
    return status, found


def _refused(status: int, found: dict[str, Any] | None, what: str, share: Share) -> Refused:
    found = found or {}
    error = found["error"] if isinstance(found.get("error"), str) else f"HTTP {status}"
    hint = found["hint"] if isinstance(found.get("hint"), str) else ""
    missing = found.get("missing")
    named = tuple(name for name in missing if isinstance(name, str) and _HEX.fullmatch(name)) \
        if isinstance(missing, list) else ()
    return Refused(status, _scrubbed(error, share), _scrubbed(hint, share), what=what, missing=named)


def _owner(share: Share) -> dict[str, str]:
    """What every write carries: the write secret, and the delete secret's hash, which the first one keeps."""
    return {"Authorization": f"Bearer {share.write}", "Cad-Delete-Hash": digest(share.delete)}


def _put_pack(share: Share, name: str, pack: bytes, waiting: Callable[[float], None] | None) -> None:
    """``PUT /v1/shares/<id>/packs/<pack id>``: one pack uploaded, ``Refused`` for the service's refusal."""
    status, found = _asked("PUT", share, f"/packs/{name}", {**_owner(share), "Content-Type": "application/octet-stream",
                                                            "Content-Length": str(len(pack))}, pack, waiting)
    if status not in (200, 201):
        raise _refused(status, found, "a pack", share)


def _commit(share: Share, body: bytes, waiting: Callable[[float], None] | None) -> dict[str, Any]:
    """``PUT /v1/shares/<id>``: the share's manifest committed. The service's answer, ``{"expires", "bytes", "files",
    "made"}`` (``bytes``: the stored size of the packs it names; ``made``: a new share, 201, or one replaced, 200);
    ``Refused`` for its refusal, a 409's with the packs it found missing."""
    status, found = _asked("PUT", share, "", {**_owner(share), "Content-Type": "application/json",
                                              "Content-Length": str(len(body))}, body, waiting)
    if status not in (200, 201) or found is None or not isinstance(found.get("expires"), str):
        raise _refused(status, found, "the share's manifest", share)
    counted = {name: found[name] if type(found.get(name)) is int else 0 for name in ("bytes", "files")}
    return {"expires": found["expires"], **counted, "made": status == 201}


def _upload(share: Share, todo: list[File],
            waiting: Callable[[float], None] | None) -> tuple[dict[str, list[list[Any]]], int, int]:
    """``todo``'s files packed in their order (``Packer``) and each pack uploaded as it closes, ``UPLOADS`` at a time:
    where each file's member now lies, and how many packs and bytes went. The first failure stops the rest, and is
    raised."""
    from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

    packer = Packer()
    count = size = 0
    running: set[Future[None]] = set()

    def settle(most: int) -> None:
        nonlocal running
        while len(running) > most:
            done, running = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                future.result()

    with ThreadPoolExecutor(max_workers=UPLOADS, thread_name_prefix="cad-share") as pool:

        def submit(closed: list[tuple[str, bytes]]) -> None:
            nonlocal count, size
            for name, pack in closed:
                running.add(pool.submit(_put_pack, share, name, pack, waiting))
                count, size = count + 1, size + len(pack)
                settle(2 * UPLOADS)  # what waits to go is held in memory: a few packs at most

        try:
            for file in todo:
                submit(packer.add(file.sha256, member(file.read())))
            submit(packer.finish())
            settle(0)
        except BaseException:
            for future in running:
                future.cancel()
            raise
    return packer.at, count, size


@dataclass(frozen=True)
class Sent:
    """A share committed (``send``): the service's answer (``_commit``), what travelled this time (``files``, ``bytes``
    and ``packs``), and where each file of the share now lives, as ``STORED`` keeps it (``stored``)."""

    answer: dict[str, Any]
    travelled: dict[str, int]
    stored: dict[str, Any]


def _manifest(found: list[File], where: dict[str, list[list[Any]]]) -> bytes:
    """The share's manifest (``cad-share/2``): every file by its path, with its bytes' SHA-256 and size, and the
    ranges of the packs its gzip member lies in."""
    return json.dumps({"format": FORMAT, "files": {file.path: {"sha256": file.sha256, "bytes": file.size,
                                                               "at": where[file.sha256]} for file in found}},
                      separators=(",", ":")).encode("utf-8")


def send(share: Share, found: list[File], stored: dict[str, Any] | None = None, *,
         waiting: Callable[[float], None] | None = None) -> Sent:
    """The share of ``found`` (``files``) committed once the packs it names are uploaded: a file whose content
    ``stored`` holds for this share (``STORED``: its last commit) keeps its ranges, and every other goes into new
    packs, in reading order. A commit's 409 naming missing packs forgets them and sends the files in them again
    (``RESENDS`` times at most); a 409 naming none commits again, once. ``Refused`` for any other refusal (a 403: a
    share of that id that another write secret made, which only a new share can be), ``Unreachable`` where the service
    does not answer, ``Unsharable`` for a file changed meanwhile. ``waiting``: told each wait a 429 asks for."""
    where = {sha256: ranges for sha256, ranges in stored["files"].items()} \
        if stored is not None and stored.get("share") == share.named else {}
    unique: dict[str, File] = {}
    for file in found:
        unique.setdefault(file.sha256, file)
    went: set[str] = set()
    packs = size = 0

    def pack(todo: list[File]) -> None:
        nonlocal packs, size
        if todo:
            at, count, sent = _upload(share, todo, waiting)
            where.update(at)
            went.update(at)
            packs, size = packs + count, size + sent

    pack([file for sha256, file in unique.items() if sha256 not in where])
    resent, again = 0, False
    while True:
        try:
            answer = _commit(share, _manifest(found, where), waiting)
            break
        except Refused as refusal:
            if refusal.status != 409:
                raise
            if refusal.missing:
                gone = set(refusal.missing)
                lost = [file for sha256, file in unique.items() if any(piece[0] in gone for piece in where[sha256])]
                if not lost or resent == RESENDS:
                    raise
                resent += 1
                for file in lost:
                    del where[file.sha256]
                pack(lost)
            elif again:
                raise
            else:
                again = True  # another commit replaced the manifest while this one was judged: once more
    return Sent(answer, {"files": sum(1 for file in found if file.sha256 in went), "bytes": size, "packs": packs},
                {"share": share.named, "files": {sha256: where[sha256] for sha256 in unique}})


def delete(share: Share, secret: str) -> bool:
    """``DELETE /v1/shares/<id>`` with a share's delete (or write) secret: True where it was deleted, False where
    the service holds no share of that id (expired, or deleted before); ``Refused`` otherwise (a 403: a secret that
    matches neither of its hashes)."""
    status, found = _asked("DELETE", share, "", {"Authorization": f"Bearer {secret}"}, None, None)
    if 200 <= status < 300:
        return True
    if status == 404:
        return False
    raise _refused(status, found, "the delete", share)


def parse_link(link: str) -> tuple[str, str, str | None] | None:
    """A share's link as ``(origin, id, delete secret)``: the secret None for a view link (``<origin>/<id>``, with no
    fragment or any but a delete's, as the page reads it); None for text that is neither."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(link.strip())
    except ValueError:
        return None
    ident = parts.path.strip("/")
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or not _ID.fullmatch(ident):
        return None
    origin = f"{parts.scheme}://{parts.netloc}"
    if not parts.fragment.startswith("delete="):
        return origin, ident, None
    secret = parts.fragment[len("delete="):]
    return (origin, ident, secret) if _SECRET.fullmatch(secret) else None


# --- what is kept ------------------------------------------------------------------------------------------------


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def expired(record: dict[str, Any]) -> bool:
    """Whether a record's share is past its expiry, as the service said it: then the service holds it no more."""
    try:
        when = datetime.fromisoformat(str(record.get("expires")).replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= datetime.now(timezone.utc)


def records_path() -> Path:
    from cad.engine.places import state_dir

    return state_dir() / RECORDS


def records(path: Path | None = None) -> list[dict[str, Any]]:
    """Every share's record this computer keeps (``RECORDS``), the expired among them; [] where there are none. A
    record of ``cad-share/1``'s (one with a ``key``) is none. ``OSError`` where the file is there and cannot be
    read."""
    try:
        text = (path or records_path()).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        found = json.loads(text)
    except ValueError:
        return []
    rows = found.get("shares") if isinstance(found, dict) else None
    return [row for row in rows if _record(row)] if isinstance(rows, list) else []


def settings() -> dict[str, Any]:
    """Whether sharing is ``on`` (on unless the person turned it off) and whether this computer's person
    ``agreed``."""
    from cad_server.settings import read_section

    try:
        kept = read_section(SECTION)
    except OSError:
        kept = {}
    return {"on": kept.get("on") is not False, "agreed": isinstance(kept.get("agreed"), str)}


def share_of(record: dict[str, Any]) -> Share:
    return Share(record["service"], record["id"], record["write"], record["delete"])


def record_of(share: Share, document: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    """A share's record: its names and links, where it lives, when it expires, the document it is of
    (``{"id", "kind", "name", "path"}``: ``path`` a file's, else None), when it was last shared and its size as the
    service stores it (``bytes``)."""
    return {"id": share.id, "write": share.write, "delete": share.delete, "service": share.service,
            "view": share.view, "remove": share.remove, "expires": answer["expires"], "document": document,
            "shared": now(), "bytes": answer["bytes"]}


def _record(row: Any) -> bool:
    """Whether ``row`` is a share's record (``record_of``): what the server keeps for a command, and nothing else --
    not one of ``cad-share/1``'s, whose link held a ``key``."""
    from cad.engine.ids import is_id

    if not isinstance(row, dict) or "key" in row:
        return False
    document = row.get("document")
    return (isinstance(row.get("id"), str) and _ID.fullmatch(row["id"]) is not None
            and all(isinstance(row.get(name), str) and _SECRET.fullmatch(row[name]) for name in ("write", "delete"))
            and all(isinstance(row.get(name), str) for name in ("view", "remove", "expires", "shared"))
            and isinstance(row.get("service"), str) and row["service"].startswith(("https://", "http://"))
            and type(row.get("bytes")) is int and isinstance(document, dict) and is_id(document.get("id"))
            and all(isinstance(document.get(name), str) for name in ("kind", "name"))
            and isinstance(document.get("path"), (str, type(None))))


def _write_records(path: Path, rows: list[dict[str, Any]]) -> None:
    """The records written whole, readable and writable by this user alone (a file made 0600 in the same folder,
    then put in place), so no other user of the computer reads a link or a secret."""
    from cad._internal.atomic_replace import replace_atomic

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write((json.dumps({"format": RECORDS_FORMAT, "shares": rows}, indent=1, sort_keys=True)
                        + "\n").encode("utf-8"))
        os.chmod(temporary, 0o600)
        replace_atomic(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def folder_of(document: str) -> Path:
    """A shared document's folder in cad's cache, ``shares/<document id>``: ``ValueError`` for anything but a
    document's id, so no other folder is ever named."""
    from cad.engine.ids import is_id
    from cad.engine.places import cache_dir

    if not is_id(document):
        raise ValueError(f"{document!r} is no document's id")
    return cache_dir() / SHARES / document


def _stored(found: Any) -> bool:
    """Whether ``found`` is what ``STORED`` keeps: ``{"share": <hex SHA-256 of the share's id>, "files": {<a file's
    SHA-256>: [[<pack id>, offset, length], ...]}}``."""
    if not isinstance(found, dict) or not isinstance(found.get("share"), str) or not _HEX.fullmatch(found["share"]) \
            or not isinstance(found.get("files"), dict):
        return False
    return all(isinstance(sha256, str) and _HEX.fullmatch(sha256) and isinstance(ranges, list) and ranges
               and all(isinstance(piece, list) and len(piece) == 3 and isinstance(piece[0], str)
                       and _HEX.fullmatch(piece[0]) and type(piece[1]) is int and type(piece[2]) is int
                       and piece[1] >= 0 and piece[2] > 0 for piece in ranges)
               for sha256, ranges in found["files"].items())


def stored(folder: Path, share: Share) -> dict[str, Any] | None:
    """Where each file of ``share``'s last commit lives, as ``folder``'s ``STORED`` keeps it; None where it keeps
    another share's, or one it cannot read."""
    try:
        found = json.loads((folder / STORED).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return found if _stored(found) and found["share"] == share.named else None


def _opened(lock: Path) -> BinaryIO:
    """``lock`` opened to be locked: to write, where this process may (made where it is missing); else to read, as a
    sandboxed shell's must, for which the server made it (``change``'s ``folder``)."""
    try:
        return open(lock, "a+b")
    except FileNotFoundError:
        raise
    except OSError:
        return open(lock, "rb")


def _took(handle: BinaryIO) -> bool:
    """The lock on ``handle``'s first byte taken if no one holds it, never waited for (``file_lock``'s lock)."""
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _let_go(handle: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _same(handle: BinaryIO, path: Path) -> bool:
    """Whether ``handle`` is still the file at ``path``: not one removed while its taker waited (where the system
    can tell)."""
    try:
        there = os.stat(path)
    except OSError:
        return False
    held = os.fstat(handle.fileno())
    return (there.st_dev, there.st_ino) == (held.st_dev, held.st_ino) or not (there.st_ino and held.st_ino)


def _alone(folder: Path) -> bool:
    """Whether ``folder`` holds nothing but its lock."""
    try:
        return {entry.name for entry in os.scandir(folder)} <= {LOCK}
    except OSError:
        return False


def _remove(folder: Path) -> None:
    """A folder that holds nothing but its lock removed, as far as the system lets it (Windows removes no file one
    holds open)."""
    with contextlib.suppress(OSError):
        (folder / LOCK).unlink(missing_ok=True)
        folder.rmdir()


@contextlib.contextmanager
def held(folder: Path, *, wait: float = 0.0, waiting: Callable[[], None] | None = None,
         make: Callable[[], Any] | None = None) -> Iterator[None]:
    """One ``cad share`` of a document at a time: its folder's ``LOCK`` held for the block. Where another holds it,
    ``waiting`` is told once and the lock waited for ``wait`` seconds, then ``Busy``. A lock file that is not there,
    or was removed while this waited (its share deleted meanwhile), is made again by ``make``; with no ``make``,
    ``FileNotFoundError``. As it is let go, a folder that holds nothing but its lock is removed: a share deleted, or
    one that wrote nothing. A lock removed while held is removed while still held, so a waiter finds it gone."""
    lock = folder / LOCK
    deadline = time.monotonic() + wait
    told, stale = False, 0
    while True:
        try:
            handle = _opened(lock)
        except FileNotFoundError:
            if make is None:
                raise
            make()
            handle = _opened(lock)
        if _took(handle):
            if _same(handle, lock) or stale == 3:  # a system that cannot tell is believed, after a few
                break
            _let_go(handle)
            handle.close()
            stale += 1
            continue
        handle.close()
        if time.monotonic() >= deadline:
            raise Busy()
        if not told and waiting is not None:
            told = True
            waiting()
        time.sleep(_POLL_SECONDS)
    try:
        yield
    finally:
        alone = _alone(folder)
        try:
            if alone and os.name != "nt":
                _remove(folder)
        finally:
            _let_go(handle)
            handle.close()
        if alone and os.name == "nt":
            _remove(folder)


def _clear(folder: Path) -> None:
    """Everything in a shared document's folder but its lock removed: the caller holds the lock, which removes the
    folder as it lets it go (``held``)."""
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return
    for entry in entries:
        if entry.name == LOCK:
            continue
        with contextlib.suppress(OSError):
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path, ignore_errors=True)
            else:
                os.unlink(entry.path)


def _sweep(live: set[str], spared: str | None) -> None:
    """Every shared document's folder that no live record names (``live``: their document ids) removed, but
    ``spared``'s and one whose lock another holds (a share being made): a share deleted, expired or never
    committed."""
    from cad.engine.ids import is_id
    from cad.engine.places import cache_dir

    try:
        entries = list(os.scandir(cache_dir() / SHARES))
    except OSError:
        return
    for entry in entries:
        if entry.name in live or entry.name == spared or not is_id(entry.name) \
                or not entry.is_dir(follow_symlinks=False):
            continue
        folder = Path(entry.path)
        try:
            with held(folder):
                _clear(folder)
        except (Busy, OSError):
            continue


def _write_stored(folder: Path, kept: dict[str, Any]) -> None:
    from cad._internal.atomic_replace import write_bytes_atomic

    folder.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(folder / STORED, json.dumps(kept, separators=(",", ":")).encode("utf-8"))


def change(request: dict[str, Any]) -> dict[str, Any]:
    """One change of what is kept, in this process: ``{"set": "on"|"off"}``, ``{"agree": true}``, ``{"folder":
    <document id>}`` (its folder in the cache made, with its lock: answered as ``folder``), ``{"record": <a share's
    record>, "stored": <its STORED>}`` (the record kept in place of any of the same share, or of the same document at
    the same service, and ``stored``, where given, written in its document's folder) or ``{"forget": <share id>}``
    (its record dropped, and the folder of its document, which the asker holds the lock of, emptied, where no other
    record names it). Every record past its expiry is dropped as the records are written, and every folder no live
    record names removed (``_sweep``). ``{"ok": true, "settings"}``, or ``{"failed"}`` in one line for a change it
    does not take. ``OSError`` where the state folder cannot be written."""
    from cad_server._internal.file_lock import state
    from cad_server.settings import update_section

    asked = [name for name in ("set", "agree", "folder", "record", "forget") if name in request]
    if len(asked) != 1 or ("stored" in request and asked != ["record"]):
        return {"failed": "a change of what sharing keeps is one of set, agree, folder, record (with stored) or forget"}
    if "set" in request:
        if request["set"] not in ("on", "off"):
            return {"failed": "sharing is set on or off"}
        update_section(SECTION, lambda kept: {**{k: v for k, v in kept.items() if k != "on"},
                                              **({} if request["set"] == "on" else {"on": False})})
    elif "agree" in request:
        if request["agree"] is not True:
            return {"failed": "an agreement is true"}
        update_section(SECTION, lambda kept: {**kept, "agreed": now()})
    elif "folder" in request:
        try:
            folder = folder_of(request["folder"])
        except ValueError:
            return {"failed": "folder names a document's id"}
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / LOCK, "a+b"):
            pass
        return {"ok": True, "settings": settings(), "folder": str(folder)}
    else:
        record, forget, kept = request.get("record"), request.get("forget"), request.get("stored")
        if "record" in request and not _record(record):
            return {"failed": "not a share's record"}
        if "stored" in request and not (_stored(kept) and kept["share"] == hashlib.sha256(
                record["id"].encode("ascii")).hexdigest()):
            return {"failed": "not where the files of that record's share are"}
        if "forget" in request and not (isinstance(forget, str) and _ID.fullmatch(forget)):
            return {"failed": "forget names a share's id"}
        path = records_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with state(path.parent):
            rows = [row for row in records(path) if not expired(row)]
            gone: list[dict[str, Any]] = []
            if record is not None:
                rows = [row for row in rows if row["id"] != record["id"] and not (
                    row["service"] == record["service"] and row["document"]["id"] == record["document"]["id"])]
                rows.append(record)
            else:
                gone = [row for row in rows if row["id"] == forget]
                rows = [row for row in rows if row["id"] != forget]
            _write_records(path, rows)
            # The folders, under the records' lock: a record another command writes meanwhile is one this reads.
            live = {row["document"]["id"] for row in rows}
            for row in gone:
                if row["document"]["id"] not in live:
                    _clear(folder_of(row["document"]["id"]))
            _sweep(live, record["document"]["id"] if record is not None else None)
        if kept is not None:
            # The cache's: where it cannot be written, the next share sends the files it would have named again.
            with contextlib.suppress(OSError):
                _write_stored(folder_of(record["document"]["id"]), kept)
    return {"ok": True, "settings": settings()}


def answer(request: dict[str, Any]) -> dict[str, Any]:
    """The server's answer to ``{"op": "share", ...}``: the change made for a command (``change``), so a shell
    whose sandbox may not write cad's state folder or its cache (an agent app's) keeps a share with no permission
    asked."""
    try:
        return change({name: value for name, value in request.items() if name != "op"})
    except OSError as error:
        return {"failed": f"could not keep it: {error.strerror or error}"}


def keep(**asked: Any) -> dict[str, Any]:
    """``change`` made by the running server where one answers that knows it, else in this process -- a sandboxed
    shell's command asks the server, as ``cad update auto`` does. ``OSError`` in either's words where it could not."""
    from cad.engine import client

    try:
        found = client.request({"op": "share", **asked}, start=False, timeout=10.0)
    except ConnectionError:
        found = None
    if isinstance(found, dict) and str(found.get("failed", "")).startswith("unknown request"):
        found = None  # a server of a release before sharing: written here
    if found is None:
        found = change(asked)
    if found.get("ok") is not True:
        raise OSError(str(found.get("failed") or "the cad server did not keep it"))
    return found
