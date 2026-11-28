"""Sharing a file: its view bundle kept in its folder of cad's cache, and the files that made it, uploaded to the
share service where its share lacks them, for anyone with its link to open in the hosted viewer and to download
(``cad share``, ``cad_server.cli.share``); and a share's files written into a folder (``cad import``,
``cad_server.cli.import_``; the engine's **Sharing**). A share is of one file, named by its canonical path: a model is
shared by its ``.xbf``, and a file that moves is another file, which shares to another link.

What is here is the client's half of the protocol, ``cad-share/2``, the standard library alone:

- **names** (``Share.new``): a share's id (16 random bytes, never text that begins with ``-``), its write secret and
  its delete secret (32 each), every one from ``secrets``, base64url without padding. The id is the capability: the service derives from it the key it
  seals the share with, and keeps neither; of the two secrets it keeps only each one's SHA-256 (``digest``);
- **links** (``Share.view``, ``Share.zip``, ``Share.remove``): ``<origin>/<id>``, ``<origin>/<id>.zip`` (its files),
  and ``<origin>/<id>#delete=<secret>``, whose part after ``#`` no browser sends to a server;
- **the view** (``view_files``): ``manifest.json`` and every file it lists but ``LEFT_OUT``'s, each a path the
  protocol takes (``sharable``), a regular file inside the bundle and the bytes the manifest says, in reading order
  (``reading``): the bundle is taken as its manifest lists it, and nothing else of it is read; its document named by
  the share's own id for it (``document_of``), never this computer's, a digest of the file's path;
- **the files that made it** (``Sources``): a model's (``model_sources``) from the build closure its ``.xbf``
  holds -- its script, every module of the project its build imported and every file it read, at their paths under
  the files' root (``root_of``: its project, never the home folder; a file outside it is left out, and said), none
  of them changed since the ``.xbf`` was written or the model last ran, nor gone -- and the ``.xbf`` itself, at its path there; and a file document's (``file_sources``): the file itself, and a
  robot description's mesh files beside it; a KiCad board's or schematic's project (``kicad_sources``): its project
  file, its project's own libraries, a board's 3D model files and rules, a schematic's sheets, at their paths under the
  files' root as a model's are. Never an installed library (``made`` names each by its version; KiCad's are KiCad's),
  nor a version control's file (``controlled``);
- **the packs** (``Packer``): each file the share lacks as one gzip member (RFC 1952: mtime 0, no name), back to
  back, the view's files first, a pack closed at ``PACK_BYTES`` and a member that does not fit the room left going
  on into the next, so a file of any size travels; a pack is named by the lowercase hex SHA-256 of its bytes; two
  files of the same bytes are one member, named twice;
- **the API** (``send``, ``delete``, ``download``): ``PUT /v1/shares/<id>/packs/<pack id>``, ``UPLOADS`` at a time as
  each pack closes, then the commit of the share's manifest, ``PUT /v1/shares/<id>``; ``DELETE /v1/shares/<id>``; and
  ``GET /<id>.zip``, a share's files. With ``urllib``, in the calling process, so an agent app's sandbox sees the
  connection and its network rules apply; proxies as ``urllib`` takes them from the environment. A 429 waits for its
  ``Retry-After``; a commit's 409 that names missing packs sends the files in them again (``RESENDS`` times at most),
  and one that names none commits again, once. A connection that cannot be made, or an answer that is not the
  service's (a proxy's refusal: no JSON ``error``), is ``Unreachable``; the service's own refusal is ``Refused``, with
  its ``error`` and ``hint``;
- **an import** (``import_link``, ``zip_entries``, ``unpack``, ``shared_file``, ``import_record``): a share's zip
  read as the service makes one, one folder of files, and written into a folder through one made beside it, refusing
  any entry that would land outside it, and any that would make a later command there run what a version control's
  settings name (a ``.git``: ``controlled``, ``unsafe_folder``); nothing of it is run; the shared file found among them (a model's ``.xbf``, a
  file document's file), which the library keeps with the link it came from;
- **a share's link as a document's name** (``document_link``, ``copy_of``, ``local``): wherever cad takes a
  document, a share's view link of the service this computer shares with or of cad.fun names this computer's copy of
  it -- the file it shared under that link, else the file an import of it wrote, as the library holds them --, a
  ``#<selector>`` after it the same in the copy as in the share; a link this computer has no copy of is refused in a
  line naming the import that makes one (``NoCopy``);
- **what is kept** (``change``): the person's agreement and whether sharing is on (the settings' ``share`` section:
  ``{"agreed": <ISO time>, "on": false}``, on where ``on`` is absent); in the library (``cad_server.engine.library``,
  which this user alone may read), each shared file's entry's ``shares``, by each service's origin: its view link, its
  two keys, its expiry and where the files that made it are (``record_of``, which ``records`` makes again), and a
  imported file's entry's ``imported``, the link it came from (``import_record``); and in the shared file's own folder
  of the cache (``folder_of``, ``<cache>/documents/<id>/``): its view bundle (``VIEW``), made only when it is shared
  and written over at each share, the base the next one reuses; where each file of the share's last commit lives
  (``STORED``); and the lock one ``cad share`` of the file holds at a time (``LOCK``, ``held``). A command asks the
  running server to write them (``{"op": "share"}``: ``answer``), which writes the library as it writes every change
  of it, and writes them itself where none answers. As a share is kept or dropped, the share's files of a folder that
  no live share's file names are removed (a share deleted, expired, or never committed). Nothing in the cache is
  needed: deleted, the next share makes the bundle again and keeps its link, whose keys are the library's.

The id and the two secrets leave this module only inside the links, in the library, and where the protocol puts them in
a request -- the id in its path, the write secret as its ``Authorization``, the delete secret as a hash, or as a
delete's ``Authorization`` --: never in an exception's words (but a view link a command was given, said back:
``NoCopy``), a log, telemetry or the cache, where ``STORED`` names a share by its id's SHA-256 (``Share.named``).
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import json
import os
import posixpath
import re
import secrets
import shutil
import stat
import sys
import tempfile
import time
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

if TYPE_CHECKING:
    import zipfile

FORMAT = "cad-share/2"
SECTION = "share"
EXPIRY_DAYS = 7
# What a share keeps in its file's folder of the cache (``folder_of``): the view bundle, where each file of its last
# commit lives, and the lock of the one ``cad share`` of the file at a time.
VIEW = "view"
STORED = "stored.json"
LOCK = "share.lock"
MANIFEST = "manifest.json"
# Left out of every share: the picture a page last kept, which may be of an earlier version of the document.
LEFT_OUT = frozenset({"thumbnail.png"})
# Where a pack is closed: half the most a pack may be by the service's default (``MAX_PACK_BYTES``, 8 MiB).
PACK_BYTES = 4 * 1024 * 1024
# How many packs are uploaded at a time.
UPLOADS = 4
# The most files a share holds over its two maps, the view's and the files that made it, and the longest path of one,
# in bytes of UTF-8 (the protocol's).
MOST_FILES = 200_000
PATH_BYTES = 1024
# A share's name, its toolchain's members, and the longest name and value of one (the protocol's: in characters as a
# browser counts them, UTF-16's).
NAME_CHARACTERS = 200
MOST_MADE = 32
MADE_CHARACTERS = 100
# What a share's name is where its document's gives nothing a manifest takes.
UNNAMED = "share"
# The most of a share's zip an import downloads, and the most it writes out of it: a share is at most 256 MiB as the
# service stores it (``MAX_SHARE_BYTES``, by default), its files compressed.
ZIP_BYTES = 1024 * 1024 * 1024
IMPORT_BYTES = 4 * 1024 * 1024 * 1024
# The names Windows gives its devices, which no file there takes (``con.py`` neither).
_DEVICES = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)),
                      *(f"LPT{n}" for n in range(1, 10))})
# The folders of a version control, whose settings name commands that an ordinary command run in the folder they
# are in, or below it, runs: git's (``core.fsmonitor``, which ``git status`` runs; a hook, an alias, a pager,
# ``core.sshCommand``), Mercurial's hooks, and the like of Subversion, Bazaar, Darcs, Jujutsu, Pijul and Fossil (a
# checkout's database). Agents, shell prompts and editors run such commands unasked, so no share holds a file in one:
# ``cad share`` leaves it out, saying so, the service refuses a manifest that names one, and ``cad import`` writes
# none, whoever made the share. Each as ``_folded`` spells it.
CONTROL = frozenset({".git", ".hg", ".svn", ".bzr", "_darcs", ".jj", ".pijul", ".fslckout", "_fossil_"})
# Windows' short names of them (``GIT~1``, as git's ``core.protectNTFS`` refuses), the first six letters of each and
# a number.
_SHORT = re.compile(r"(?:git|hg|svn|bzr|jj|pijul|fslcko)~[0-9]+")
# What git takes a folder for a repository by, wherever it lies, with no ``.git``: its bare form, a ``HEAD`` file
# beside an ``objects`` and a ``refs`` folder.
BARE = frozenset({"head", "objects", "refs"})
# The code points HFS+ ignores in a name (git's ``core.protectHFS``): ``.g‌it`` opens ``.git`` there.
_IGNORED = frozenset("‌‍‎‏‪‫‬‭‮⁪⁫⁬⁭⁮⁯﻿")
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


class Cut(Unreachable):
    """An answer of the service's that stopped part way: its status and headers came, then the connection was closed,
    reset or went silent before its body was whole."""


class Refused(Exception):
    """The service's own refusal of ``what`` (``a pack``, ``the share's manifest``, ``the delete``): its status,
    ``error`` and ``hint``, and the packs a commit's 409 found missing (``missing``)."""

    def __init__(self, status: int, error: str, hint: str = "", *, what: str = "the request",
                 missing: tuple[str, ...] = ()) -> None:
        super().__init__(f"{error} ({hint})" if hint else error)
        self.status, self.error, self.hint, self.what, self.missing = status, error, hint, what, missing


class Busy(Exception):
    """Another holder kept a document's lock for the whole of the wait (``held``)."""


class Stale(Exception):
    """A model whose files are not the ones its last run built from (``model_sources``): ``path`` changed after the
    build (``why``: ``changed``), or is gone from the disk (``gone``). Its share would not be what built its view."""

    def __init__(self, path: str, why: str) -> None:
        super().__init__(f"{path} {'changed after the build' if why == 'changed' else 'is gone'}")
        self.path, self.why = path, why


class Damaged(ValueError):
    """A share's zip that is not one the service makes (``zip_entries``, ``unpack``, ``download``): its words."""


class Unsafe(Damaged):
    """A share's zip, or the folder an import would write it into, that would make a later command there run what a
    version control's settings name (``controlled``, ``unsafe_folder``): the path, in its words."""


def _token(size: int) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(size)).rstrip(b"=").decode("ascii")


def _ident() -> str:
    """A new share's id: 16 random bytes, drawn again while their text begins with ``-`` (one draw in 64), which a
    command line reads as an option (``cad import <id>``)."""
    while (ident := _token(16)).startswith("-"):
        pass
    return ident


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
        return cls(service, _ident(), _token(32), _token(32))

    @property
    def view(self) -> str:
        """The view link: the id is the capability, so the link holds nothing else."""
        return f"{self.service}/{self.id}"

    @property
    def zip(self) -> str:
        """The files' link: the files that made the document, as a zip of one folder."""
        return f"{self.service}/{self.id}.zip"

    @property
    def remove(self) -> str:
        return f"{self.service}/{self.id}#delete={self.delete}"

    @property
    def named(self) -> str:
        """The share as the cache names it (``STORED``): its id's lowercase hex SHA-256, never the id."""
        return hashlib.sha256(self.id.encode("ascii")).hexdigest()

    def __repr__(self) -> str:  # never the id or a secret, wherever a share is printed
        return f"Share({_host(self.service)!r})"


# --- the view ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class File:
    """One file a share holds: its path in the share (in the view bundle, or under the files' root), its bytes'
    SHA-256 and size, and where it is; or, for a file a share holds as it made it (``view_files``: the bundle's
    manifest and structure, named by the share), its bytes (``data``)."""

    path: str
    sha256: str
    size: int
    source: Path
    data: bytes | None = None

    def read(self) -> bytes:
        """Its bytes, still the ones that were read of it (``Unsharable`` for a file changed since)."""
        data = self.source.read_bytes() if self.data is None else self.data
        if len(data) != self.size or hashlib.sha256(data).hexdigest() != self.sha256:
            raise Unsharable(f"{self.path} changed while it was shared: share it again")
        return data


def sharable(path: object) -> bool:
    """Whether ``path`` is one a share's manifest takes: relative, ``/`` separated, with no empty, ``.`` or ``..``
    segment, at most ``PATH_BYTES`` bytes of UTF-8 (the protocol's); so that it names one file on every system,
    printable, with no ``\\`` or ``:``; and in no version control's folder (``controls``)."""
    if not isinstance(path, str) or not path or not path.isprintable() or "\\" in path or ":" in path:
        return False
    try:
        size = len(path.encode("utf-8"))
    except UnicodeEncodeError:
        return False
    parts = path.split("/")
    return size <= PATH_BYTES and all(part not in ("", ".", "..") and not controls(part) for part in parts)


def _folded(segment: str) -> str:
    """A path's segment as the file systems that open it compare it: without the code points HFS+ ignores, before an
    NTFS stream's ``:`` (``.git::$INDEX_ALLOCATION`` opens ``.git``), composed, without the dots and spaces Windows
    drops from a name's end, case folded."""
    name = "".join(character for character in segment if character not in _IGNORED).split(":", 1)[0]
    return unicodedata.normalize("NFC", name).rstrip(". ").casefold()


def controls(segment: str) -> bool:
    """Whether a path's segment names a version control's folder (``CONTROL``) on some system: as any of them
    compares it (``_folded``), or as Windows' short name of it (``GIT~1``)."""
    name = _folded(segment)
    return name in CONTROL or _SHORT.fullmatch(name) is not None


def controlled(paths: list[str]) -> str | None:
    """The first of ``paths`` (``/`` separated, under one folder) that would make a later command in that folder or
    below it read settings that run commands, or None: one with a segment that names a version control's folder
    (``controls``), or a ``HEAD`` beside an ``objects`` and a ``refs`` folder, which git takes for a repository
    wherever it lies (its bare form, ``BARE``), the one folder too."""
    children: dict[str, dict[str, str]] = {}
    for path in paths:
        parts = path.split("/")
        if any(controls(part) for part in parts):
            return path
        for depth in range(len(parts)):
            folder = "/".join(parts[:depth])
            children.setdefault(folder, {}).setdefault(_folded(parts[depth]),
                                                       path if depth == len(parts) - 1 else "")
    for folder, names in children.items():
        if BARE <= names.keys() and names["head"]:
            return names["head"]
    return None


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


def _read_digest(path: str) -> str:
    """A file's digest as a build's closure records one it read itself (an input of kind ``read``): BLAKE2b of 32
    bytes, in lowercase hex (``memo._read_digest``); one read through the engine (``file``) is its SHA-256."""
    found = hashlib.blake2b(digest_size=32)
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            found.update(chunk)
    return found.hexdigest()


def _digest_of(path: Path) -> tuple[str, int]:
    found, size = hashlib.sha256(), 0
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            found.update(chunk)
            size += len(chunk)
    return found.hexdigest(), size


def document_of(share: Share) -> str:
    """The id a share's view names its document by, in place of the one this computer names it by (``ids.file_id``,
    a digest of the file's path that anyone could test guesses of the person's folders against): one made from the
    share's id alone, so the same in every commit of the share, which a page keeps what it remembers of the document
    by, and of no path."""
    import uuid

    return str(uuid.UUID(bytes=hashlib.sha256(f"{FORMAT} document {share.id}".encode("ascii")).digest()[:16],
                         version=4))


def _named(raw: bytes, local: str, ident: str, members: tuple[str, ...]) -> bytes:
    """A bundle's JSON object (``raw``) with each of its ``members`` that names the document by ``local`` naming it by
    ``ident``, written compactly, as the bundle writes it; ``raw`` as it is where none does."""
    found = json.loads(raw.decode("utf-8"))
    if not isinstance(found, dict) or not any(found.get(member) == local for member in members):
        return raw
    return json.dumps({name: ident if name in members and value == local else value for name, value in found.items()},
                      separators=(",", ":")).encode("utf-8")


def view_files(folder: Path, share: Share | None = None) -> list[File]:
    """The files of the bundle in ``folder`` that a share holds, in reading order (``reading``): ``manifest.json``, and
    every file it lists but ``LEFT_OUT``'s, each a path a share takes (``sharable``), a regular file inside the folder
    and the bytes the manifest says (its ``sha256`` and ``bytes``). Anything else is ``Unsharable``, in its words.

    For ``share``, the bundle names its document as the share does (``document_of``), never as this computer does:
    the manifest's ``document.id`` and the structure's ``path`` and ``id`` that are the file's id here, a digest of
    its path, are the share's id for it, the manifest listing the structure's bytes as they are then."""
    manifest = folder / MANIFEST
    try:
        raw = manifest.read_bytes()
    except FileNotFoundError:
        raise Unsharable("the folder holds no view bundle: it has no manifest.json") from None
    try:
        told = json.loads(raw.decode("utf-8"))
        listed = told.get("files")
    except (UnicodeDecodeError, ValueError, AttributeError):
        told, listed = None, None
    if not isinstance(listed, dict):
        raise Unsharable("the view bundle's manifest.json lists no files")
    if len(listed) + 1 > MOST_FILES:
        raise Unsharable(f"the view bundle holds {len(listed) + 1} files, more than the {MOST_FILES} a share holds")
    local = (told.get("document") or {}).get("id") if isinstance(told.get("document"), dict) else None
    renamed = share is not None and isinstance(local, str) and bool(local)
    root = os.path.realpath(folder)
    found: list[File] = []
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
        if renamed and path == "structure.json":
            data = File(path, sha256, size, source).read()
            try:
                made = _named(data, str(local), document_of(share), ("path", "id"))
            except (UnicodeDecodeError, ValueError):
                made = data
            if made != data:
                listed = {**listed, path: {**entry, "sha256": hashlib.sha256(made).hexdigest(), "bytes": len(made)}}
                found.append(File(path, listed[path]["sha256"], len(made), source, made))
                continue
        found.append(File(path, sha256, size, source))
    if renamed:
        raw = json.dumps({**told, "document": {**told["document"], "id": document_of(share)}, "files": listed},
                         separators=(",", ":")).encode("utf-8")
        found.append(File(MANIFEST, hashlib.sha256(raw).hexdigest(), len(raw), manifest, raw))
    else:
        found.append(File(MANIFEST, hashlib.sha256(raw).hexdigest(), len(raw), manifest))
    return sorted(found, key=reading)


def bundle(path: str, folder: Path) -> dict[str, Any]:
    """The view bundle of the file at ``path`` (canonical) written into ``folder`` by the running server, from what it
    answers the file's page (``api.bundle``, the engine's **View bundle**), over the one it holds there: its
    manifest. A model's ``.xbf`` is the model a live worker holds, else the file: the same document."""
    from cad.engine import api

    api.bundle(path, folder)
    return json.loads((folder / MANIFEST).read_text(encoding="utf-8"))


# --- the files that made it --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Sources:
    """The files that made a document, as its share holds them (``model_sources``, ``file_sources``): each a ``File``
    by its path under the files' ``root``, in path order; the path among them of the script that builds it
    (``entry``: None for a file document, and for a model no closure names the code of); what built it (``made``:
    cad's release, the build's libraries and its platform, each as text; None where no closure says); each file left
    out and why (``left_out``: ``(path, why)``, ``outside`` the files' root, ``gone`` from the disk, a ``name`` no
    share takes, or a version control's file, ``control``: ``controlled``); whether the build read a file the engine could not see (``unseen``: its closure's key is null),
    which an import may not rebuild it without; and the file shared, a model's ``.xbf`` or a file document's own file:
    its absolute path (``file``) and its path among ``files`` (``shared``)."""

    files: tuple[File, ...] = ()
    entry: str | None = None
    made: dict[str, str] | None = None
    root: str | None = None
    left_out: tuple[tuple[str, str], ...] = ()
    unseen: bool = False
    file: str | None = None
    shared: str | None = None

    @property
    def size(self) -> int:
        return sum(file.size for file in self.files)


def _utf16(text: str) -> int:
    """How many characters a browser counts in ``text``: its UTF-16 code units."""
    return sum(2 if ord(character) > 0xFFFF else 1 for character in text)


def share_name(name: object) -> str:
    """A document's name as a share's manifest takes it (``name``): its text without control characters, at most
    ``NAME_CHARACTERS`` characters; ``UNNAMED`` where nothing is left."""
    kept: list[str] = []
    counted = 0
    for character in str(name or "").strip():
        if unicodedata.category(character) in ("Cc", "Cs"):
            continue
        counted += _utf16(character)
        if counted > NAME_CHARACTERS:
            break
        kept.append(character)
    return "".join(kept).strip() or UNNAMED


def made_of(closure: dict[str, Any]) -> dict[str, str]:
    """What built a model, from its build closure, as a share's manifest says it (``made``): ``cad``, the release
    that built it (the closure's ``engine.release``, ``cadgen <release>``), then its ``libs`` and its ``platform``, in
    the closure's order; each a name and a value of text, of ``MADE_CHARACTERS`` at most, ``MOST_MADE`` of them."""
    found: dict[str, str] = {}
    release = str((closure.get("engine") or {}).get("release") or "").split()
    if release and len(release[-1]) <= MADE_CHARACTERS:
        found["cad"] = release[-1]
    for group in ("libs", "platform"):
        members = closure.get(group)
        for name, value in (members.items() if isinstance(members, dict) else ()):
            if (isinstance(name, str) and isinstance(value, str) and name and value and name not in found
                    and _utf16(name) <= MADE_CHARACTERS and _utf16(value) <= MADE_CHARACTERS
                    and len(found) < MOST_MADE):
                found[name] = value
    return found


def _inside(path: str, folder: str) -> bool:
    """Whether ``path`` is ``folder`` or lies in it (both absolute and normalized), as this system compares them."""
    path, folder = os.path.normcase(path), os.path.normcase(folder)
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:  # another drive
        return False


def project_roots() -> list[str]:
    """The folders the viewer has as projects (the library's ``projects``: each a folder a person opened as one), each
    canonical; none where the library cannot be read (a sandbox may refuse it): a checkout's root still names one."""
    try:
        found = _library().read().get("projects") or {}
    except OSError:
        return []
    return [str(entry["root"]) for entry in found.values() if isinstance(entry, dict) and isinstance(entry.get("root"), str)]


def root_of(core: list[str], paths: list[str], *, home: str | None = None, projects: list[str] | None = None) -> str:
    """The files' root of a document's files -- ``core`` (absolute: the file shared first, a model's ``.xbf``, then
    the files that must go with it, its script) and ``paths``, the others -- its project: the nearest folder over the
    first of ``core`` that holds all of ``core`` and is a project the viewer has (``projects``: ``project_roots``) or a
    checkout's root (it holds a ``.git``). Where there is none, the deepest folder that holds them all. Never the
    home folder (``home``, else this user's) or a folder over it, nor a disk's root: where none holds them all, the
    deepest that holds ``core`` and those of ``paths`` that the highest folder allowed over ``core`` holds; the files
    outside the root are left out by the caller. ``Unsharable`` where ``core`` alone needs a folder never allowed (a
    model in the home folder itself)."""
    home = home if home is not None else os.path.expanduser("~")
    homes = [os.path.realpath(home)] if os.path.isabs(home) else []
    held = {os.path.normcase(os.path.realpath(root)) for root in projects or ()}

    def allowed(at: str) -> bool:  # neither a disk's root nor the home folder or one over it
        real = os.path.realpath(at)
        return os.path.dirname(real) != real and not any(_inside(each, real) for each in homes)

    def chain(at: str) -> list[str]:
        found = [at]
        while os.path.dirname(found[-1]) != found[-1]:
            found.append(os.path.dirname(found[-1]))
        return found

    first = os.path.normpath(core[0])
    drive = os.path.normcase(os.path.splitdrive(first)[0])
    core = [os.path.normpath(path) for path in core]
    for at in chain(os.path.dirname(first)):
        if not allowed(at):
            break
        if (os.path.normcase(os.path.realpath(at)) in held or os.path.lexists(os.path.join(at, ".git"))) \
                and all(_inside(path, at) for path in core):
            return at
    same = [os.path.normpath(path) for path in paths if os.path.normcase(os.path.splitdrive(path)[0]) == drive]
    try:
        centre = os.path.commonpath([os.path.dirname(path) for path in core])
    except ValueError:  # another drive
        centre = os.path.dirname(first)
    room = [at for at in chain(centre) if allowed(at)]
    if not room or room[0] != centre:
        above = ("the home folder, or a folder over it" if homes and _inside(homes[0], os.path.realpath(centre))
                 else "a disk's root")
        names = " and ".join(dict.fromkeys(os.path.basename(path) for path in core))
        raise Unsharable(f"no folder but {centre} ({above}) holds {names}, and a share holds a project's files, never "
                         "those of the home folder or a disk: move them into a folder of their own, or open the "
                         "folder that holds them as a project in the viewer")
    top = room[-1]
    return os.path.commonpath([centre, *(os.path.dirname(path) for path in same if _inside(path, top))])


def _taken(path: str, root: str) -> str | None:
    """``path``'s path under ``root``, as a share's manifest names it (``/`` separated), where a share takes it."""
    relative = Path(os.path.relpath(path, root)).as_posix()
    return relative if sharable(relative) else None


def _untaken(path: str, root: str) -> str:
    """Why a share does not take ``path``, which lies under ``root``: ``control``, in a version control's folder
    (``controls``), else ``name``, a name no share holds."""
    relative = Path(os.path.relpath(path, root)).as_posix()
    return "control" if any(controls(part) for part in relative.split("/")) else "name"


def _unbare(chosen: dict[str, str], root: str, left: list[tuple[str, str]]) -> None:
    """Each ``HEAD`` among the files ``chosen`` (by their path as this system compares it) that would make a folder
    of them a repository (``controlled``) left out of them, into ``left`` as ``control``."""
    while (found := controlled([str(_taken(path, root)) for path in chosen.values()])) is not None:
        key = next(key for key, path in chosen.items() if _taken(path, root) == found)
        left.append((chosen.pop(key), "control"))


def model_sources(xbf: str, built: float, *, home: str | None = None, projects: list[str] | None = None) -> Sources:
    """The files that made the model whose ``.xbf`` is at ``xbf`` (canonical), from the build closure that file holds
    (``previous.of``: every path relative to the ``.xbf``'s folder): the script, every module, and every input of kind
    ``file`` or ``read`` the build found, each at its path under the files' root (``root_of``: the model's project, of
    ``projects``, a checkout's root, else the folder that holds them, never the home folder); a ``font`` only where
    it lies in that root (a system font is recorded nowhere else needed); and the ``.xbf`` itself, at its path there,
    so an import has the model with nothing run. ``built`` is when the model was last made here: the ``.xbf``'s time, or
    its last run's where that is later (a run that took the ``.xbf`` whole writes nothing). A file outside the root is
    left out, as is an input gone from the disk, each said (``left_out``). ``Stale`` for the script or a module gone
    from the disk, for an input whose bytes are not the ones its closure holds the digest of, whatever its time, and
    for the script, a module or a font modified after ``built`` (the closure's digest of code is of what the build
    reached in it, which only running it tells): those are not the files the ``.xbf`` was made from. An ``.xbf`` that holds no closure (a shape a program handed over, a file another document exported) goes
    alone, at its own name. ``Unsharable`` for an ``.xbf`` and a script that no folder but the home folder holds."""
    from cad.engine import previous

    xbf = os.path.normpath(xbf)
    try:
        closure = previous.of(Path(xbf))
    except (OSError, UnicodeDecodeError, ValueError):
        closure = None
    told = closure.get("source") if isinstance(closure, dict) else None
    if not isinstance(told, dict) or not isinstance(told.get("path"), str) or not told["path"]:
        root, name = os.path.dirname(xbf), os.path.basename(xbf)
        if not sharable(name):
            raise Unsharable(f"{name} is named in a way a share cannot hold: rename it")
        sha256, size = _digest_of(Path(xbf))
        return Sources((File(name, sha256, size, Path(xbf)),), None, made_of(closure) if closure else None, root,
                       file=xbf, shared=name)
    base = Path(os.path.dirname(xbf))

    def at(given: Any) -> str | None:
        return previous.absolute(given, base) if isinstance(given, str) and given else None

    code = [str(at(told["path"]))]
    for row in closure.get("modules") or []:
        path = at(row[0]) if isinstance(row, list) and row else None
        if path is not None:
            code.append(path)
    reads, fonts = [], []
    held: dict[str, list[tuple[str, str]]] = {}  # each input's digests as the build recorded them, by its path
    for row in closure.get("inputs") or []:
        if not isinstance(row, list) or not row or row[-1] is None:
            continue  # a file the build found missing: it read nothing of it
        if row[0] in ("file", "read") and len(row) >= 3 and at(row[1]):
            reads.append(at(row[1]))
            if isinstance(row[2], str) and _HEX.fullmatch(row[2]):
                held.setdefault(os.path.normcase(at(row[1])), []).append((row[0], row[2]))
        elif row[0] == "font" and len(row) >= 5 and at(row[2]):
            fonts.append(at(row[2]))
    for path in code:
        if not os.path.isfile(path):
            raise Stale(path, "gone")
    present = [path for path in reads if os.path.isfile(path)]
    root = root_of([xbf, code[0]], [*code[1:], *present], home=home, projects=projects)
    if _taken(xbf, root) is None:
        raise Unsharable(f"{xbf} is named in a way a share cannot hold: rename it")
    left: list[tuple[str, str]] = []
    chosen: dict[str, str] = {}  # each file that goes, by its path as this system compares paths
    seen: set[str] = {os.path.normcase(xbf)}  # the .xbf goes, and is no file of the code
    for path in [*code, *present]:
        if os.path.normcase(path) in seen:
            continue
        seen.add(os.path.normcase(path))
        if not _inside(path, root):
            left.append((path, "outside"))
        elif _taken(path, root) is None:
            left.append((path, _untaken(path, root)))
        else:
            chosen[os.path.normcase(path)] = path
    for path in fonts:
        if os.path.isfile(path) and _inside(path, root) and _taken(path, root) is not None \
                and os.path.normcase(path) != os.path.normcase(xbf):
            chosen.setdefault(os.path.normcase(path), path)
    _unbare(chosen, root, left)
    left += [(path, "gone") for path in dict.fromkeys(reads) if not os.path.isfile(path)]
    if os.path.normcase(code[0]) not in chosen:
        raise Unsharable(f"{os.path.basename(code[0])} is named in a way a share cannot hold: rename it")
    found: list[File] = []
    coded = {os.path.normcase(path) for path in code}
    for path in chosen.values():
        digests = held.get(os.path.normcase(path), [])
        try:
            sha256, size = _digest_of(Path(path))
            modified = os.stat(path).st_mtime  # after the read: a file written meanwhile is newer still
            if any(digest != (sha256 if kind == "file" else _read_digest(path)) for kind, digest in digests):
                raise Stale(path, "changed")
        except OSError:
            raise Stale(path, "gone") from None
        # A file the build read is judged by its bytes, which its closure holds the digest of; the code (whose
        # digest is of what the build reached in it, which only running it tells) and a font, by time.
        if (not digests or os.path.normcase(path) in coded) and modified > built:
            raise Stale(path, "changed")
        found.append(File(str(_taken(path, root)), sha256, size, Path(path)))
    sha256, size = _digest_of(Path(xbf))
    shared = str(_taken(xbf, root))
    found.append(File(shared, sha256, size, Path(xbf)))
    return Sources(tuple(sorted(found, key=lambda file: file.path)), _taken(code[0], root), made_of(closure), root,
                   tuple(left), closure.get("key") is None, xbf, shared)


def _described(path: str, kind: str) -> list[str]:
    """The files a robot description is drawn from beside itself: a URDF's mesh files, each ``<mesh filename>`` of
    its visuals and its collisions resolved as the engine resolves one (``urdf_source.mesh_file``); an SRDF's URDF,
    the one it plans for (``urdf_source.read_srdf``), and that one's. None of a file that does not read: its view
    bundle says why."""
    import xml.etree.ElementTree as ET

    from cad.engine import urdf_source
    from cad.engine.robot_model import local_name

    found: list[str] = []
    urdf = Path(path)
    if kind == "srdf":
        try:
            described = urdf_source.read_srdf(urdf).sources
        except Exception:  # noqa: BLE001 - any refusal of it is its view bundle's to say
            return found
        if len(described) < 2:
            return found
        urdf = Path(described[1])
        found.append(str(urdf))
    try:
        root = ET.parse(urdf).getroot()
    except (OSError, ET.ParseError):
        return found
    for element in root.iter():
        name = str(element.get("filename") or "").strip() if local_name(element.tag) == "mesh" else ""
        mesh = urdf_source.mesh_file(name, urdf.parent, str(urdf)) if name else None
        if mesh is not None:
            found.append(str(mesh))
    return found


# A KiCad project's library tables, beside its project file: a board's footprint and symbol libraries, a
# schematic's symbol libraries.
_LIBRARY_TABLES = {"kicad_pcb": ("fp-lib-table", "sym-lib-table"), "kicad_sch": ("sym-lib-table",)}
# ${NAME} or $(NAME), KiCad's two spellings of a variable.
_VARIABLE = re.compile(r"\$\{([^}]*)\}|\$\(([^)]*)\)")
_DRIVE_RELATIVE = re.compile(r"^[A-Za-z]:(?!/)")
_VRML = (".wrl", ".wrz")


def _placed(name: str, folder: str, variables: dict[str, str]) -> tuple[str, bool] | None:
    """Where a place a KiCad project names (a library's URI, a 3D model's name) is on this computer, and whether the
    name was relative: ``${KIPRJMOD}`` is the project's ``folder``, a variable the project defines its value (its
    ``.kicad_pro``'s ``text_variables``), a relative place is under ``folder``. None for a name that holds any other
    variable -- a library of KiCad's (``${KICAD9_3DMODEL_DIR}``) or one the person's own settings name, an installed
    library an import has of its own -- and for a network share, a device or a drive-relative name, which nothing here
    looks at (on Windows, looking connects to the share's server)."""
    unknown = False

    def value(match: re.Match) -> str:
        nonlocal unknown
        named = match.group(1) or match.group(2) or ""
        if named == "KIPRJMOD":
            return folder
        if named in variables:
            return variables[named]
        unknown = True
        return match.group(0)

    place = _VARIABLE.sub(value, name.strip()).replace("\\", "/")
    if unknown or not place or "\0" in place or place.startswith("//") or _DRIVE_RELATIVE.match(place):
        return None
    relative = not os.path.isabs(place)
    return os.path.realpath(os.path.join(folder, place) if relative else place), relative


def _library_files(table: Path, folder: str) -> list[str]:
    """The files of the libraries a KiCad library table lists (``fp-lib-table``, ``sym-lib-table``), each URI where
    the project at ``folder`` has it (``_placed``): a library folder's files (a ``.pretty``'s footprints), a library
    file (a ``.kicad_sym``; a legacy ``.lib`` with the ``.dcm`` beside it); a library gone, its place. A library of
    KiCad's or of the person's own settings is none."""
    from cad.engine.formats.kicad import sexpr

    try:
        tree = sexpr.parse(table.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return []
    found: list[str] = []
    for library in sexpr.find_all(tree, "lib"):
        uri = sexpr.value(library, "uri")
        placed = _placed(str(uri), folder, {}) if uri else None
        if placed is None:
            continue
        place = placed[0]
        if os.path.isdir(place):
            found += sorted(os.path.join(place, name) for name in os.listdir(place)
                            if not name.startswith(".") and os.path.isfile(os.path.join(place, name)))
        else:
            found.append(place)
            documentation = _on_disk(place[:-4] + ".dcm") if place.lower().endswith(".lib") else None
            if documentation is not None:
                found.append(documentation)
    return found


def _on_disk(path: str) -> str | None:
    """The file ``path`` reaches, as its folder spells it, or None where it reaches none. A disk blind to case
    (Windows', a Mac's) opens ``lens.step`` for a file named ``lens.STEP``; a share keeps the file's own name, so an
    import on any disk writes the file its board names."""
    if not os.path.isfile(path):
        return None
    folder, name = os.path.split(path)
    try:
        entries = os.listdir(folder or ".")
    except OSError:
        return path
    if name in entries:
        return path
    for entry in entries:
        if entry.lower() == name.lower():
            candidate = os.path.join(folder, entry)
            try:
                if os.path.samefile(candidate, path):
                    return candidate
            except OSError:
                continue
    return path


def _model_files(board: str) -> list[str]:
    """The 3D model files a board's footprints name in its project (``models3d.model_names``): each name that is a
    place of the project (``_placed``), the file it names, and for a VRML name the STEP beside it, which the viewer's
    3D draws. A name in a library of KiCad's is the library's, as is a relative name the board's folder lacks (KiCad
    looks for it in its 3D library too), and so is a file inside a 3D library (``models3d.library_roots``); a model
    embedded in the board is the board's. A name of the project's whose file is gone is its place."""
    from cad.engine.formats.kicad.models3d import _project_variables, library_roots, model_names

    try:
        text = Path(board).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    folder, variables = os.path.dirname(board), _project_variables(Path(board))
    libraries = [os.path.normcase(library) for library in library_roots()]
    found: list[str] = []
    for name in model_names(text):
        placed = None if name.strip().lower().startswith("kicad-embed://") else _placed(name, folder, variables)
        if placed is None:
            continue
        place, relative = placed
        if any(_inside(place, library) for library in libraries):
            continue
        stem, suffix = os.path.splitext(place)
        beside = [stem + ending for ending in (".step", ".stp", ".STEP", ".STP")] if suffix.lower() in _VRML else []
        there: list[str] = []
        for each in [place, *beside]:
            real = _on_disk(each)
            if real is not None and real not in there:
                there.append(real)
        if there or not relative:
            found += there or [place]
    return found


def kicad_sources(path: str, kind: str, *, home: str | None = None, projects: list[str] | None = None) -> Sources:
    """The files an import of a KiCad board or schematic needs to open it and work on it (``kind``: ``kicad_pcb`` or
    ``kicad_sch``), each at its path under the files' root (``root_of``, from the file's folder): the file itself;
    of a board, its project file (``<board>.kicad_pro``) and custom rules (``.kicad_dru``) beside it, its project's
    footprint and symbol libraries (``fp-lib-table``, ``sym-lib-table`` and the libraries they list in it:
    ``_library_files``) and the 3D model files its footprints name in it (``_model_files``); of a schematic, every
    sheet of the hierarchy it is drawn in (``schematic.read_schematic_index``: its project's, from the root sheet), the
    root's project file and its project's symbol libraries. A file outside the root, and one gone from the disk, is
    left out, each said (``left_out``); a library of KiCad's is installed, as a model's libraries are, and goes in no
    share."""
    from cad.engine.formats.kicad.schematic import read_schematic_index, root_of as root_sheet

    real = os.path.realpath(path)
    named = [real]
    if kind == "kicad_sch":
        project_sheet = root_sheet(real)
        try:
            named += [os.path.realpath(sheet) for sheet in read_schematic_index(real)[0].trees]
        except (OSError, ValueError):  # no readable schematic: its view bundle says why
            pass
        project, beside = project_sheet.with_suffix(".kicad_pro"), []
    else:
        project, beside = Path(real).with_suffix(".kicad_pro"), [Path(real).with_suffix(".kicad_dru")]
    folder = str(project.parent)
    named += [str(file) for file in (project, *beside) if file.is_file()]
    for table in _LIBRARY_TABLES[kind]:
        listed = Path(folder) / table
        if listed.is_file():
            named += [str(listed), *_library_files(listed, folder)]
    if kind == "kicad_pcb":
        named += _model_files(real)
    candidates = list({os.path.normcase(each): each for each in named}.values())
    root = root_of([real], [each for each in candidates if os.path.isfile(each)], home=home, projects=projects)
    found: list[File] = []
    left: list[tuple[str, str]] = []
    chosen: dict[str, str] = {}
    for each in candidates:
        taken = _taken(each, root) if _inside(each, root) else None
        if not os.path.isfile(each):
            left.append((each, "gone"))
        elif not _inside(each, root):
            left.append((each, "outside"))
        elif taken is None:
            left.append((each, _untaken(each, root)))
        else:
            chosen[os.path.normcase(each)] = each
    _unbare(chosen, root, left)
    for each in chosen.values():
        sha256, size = _digest_of(Path(each))
        found.append(File(str(_taken(each, root)), sha256, size, Path(each)))
    own = _taken(real, root)
    return Sources(tuple(sorted(found, key=lambda file: file.path)), None, None, root, tuple(left), file=real,
                   shared=own if any(file.path == own for file in found) else None)


def file_sources(path: str, kind: str, *, projects: list[str] | None = None) -> Sources:
    """The files that made a file document (``kind``: its type's id): the file itself, at its own name; a URDF's mesh
    files too, and an SRDF's URDF with that one's (``_described``), each at its path under the file's folder. One
    outside that folder is left out, as is one gone from the disk, each said (``left_out``). A KiCad board's or
    schematic's are its project's (``kicad_sources``)."""
    if kind in _LIBRARY_TABLES:
        return kicad_sources(path, kind, projects=projects)
    real = os.path.realpath(path)
    root = os.path.dirname(real)
    found: list[File] = []
    left: list[tuple[str, str]] = []
    seen: set[str] = set()
    chosen: dict[str, str] = {}
    for each in [real, *(os.path.realpath(more) for more in (_described(real, kind) if kind in ("urdf", "srdf")
                                                            else []))]:
        if os.path.normcase(each) in seen:
            continue
        seen.add(os.path.normcase(each))
        taken = _taken(each, root) if _inside(each, root) else None
        if not os.path.isfile(each):
            left.append((each, "gone"))
        elif not _inside(each, root):
            left.append((each, "outside"))
        elif taken is None:
            left.append((each, _untaken(each, root)))
        else:
            chosen[os.path.normcase(each)] = each
    _unbare(chosen, root, left)
    for each in chosen.values():
        sha256, size = _digest_of(Path(each))
        found.append(File(str(_taken(each, root)), sha256, size, Path(each)))
    own = _taken(real, root)
    return Sources(tuple(sorted(found, key=lambda file: file.path)), None, None, root, tuple(left), file=real,
                   shared=own if any(file.path == own for file in found) else None)


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


def _streamed(answer: Any, into: BinaryIO) -> None:
    """An answer's body written into ``into`` as it arrives: ``ZIP_BYTES`` at most, else ``Damaged``; one that ends
    short of the length it said (a read in parts says so in no other way) is ``http.client.IncompleteRead``."""
    import http.client

    size = 0
    while chunk := answer.read(1 << 20):
        size += len(chunk)
        if size > ZIP_BYTES:
            raise Damaged(f"it is larger than the {ZIP_BYTES // (1024 * 1024)} MiB a share's files are at most")
        into.write(chunk)
    if getattr(answer, "length", None):
        raise http.client.IncompleteRead(b"", answer.length)


def _call(method: str, share: Share, path: str, headers: dict[str, str], body: bytes | None = None,
          timeout: float = TIMEOUT_SECONDS, *, address: str | None = None,
          into: BinaryIO | None = None) -> tuple[int, dict[str, Any] | None, Any]:
    """One request of the API, from this process -- at ``/v1/shares/<id><path>``, or at ``address`` -- its status,
    its JSON answer (None for none) and its headers; with ``into``, a successful answer's body is written there
    (``_streamed``) rather than read as JSON. A connection that cannot be made, or a refusal that is not the
    service's -- no JSON ``error``, as a proxy's is -- is ``Unreachable``, and an answer cut off part way ``Cut``, in
    words that hold no name of the share's."""
    import http.client
    import urllib.error
    import urllib.request

    host = _host(share.service)
    url = address or f"{share.service}/v1/shares/{share.id}{path}"
    request = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": "cad", **headers})
    try:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310 - http(s) only (``share_url``)
                try:
                    if into is not None:
                        _streamed(answer, into)
                        return answer.status, None, answer.headers
                    return answer.status, _answer(answer.read(ANSWER_BYTES)), answer.headers
                except (OSError, http.client.HTTPException) as error:  # the network reached it: the answer stopped
                    if isinstance(error, http.client.IncompleteRead):
                        detail = f"{error.expected} bytes short" if error.expected else "it ended before its last part"
                    else:
                        detail = f"{type(error).__name__}{': ' + _scrubbed(str(error), share) if str(error) else ''}"
                    raise Cut(f"{host} began to answer, then stopped ({detail})") from None
        except urllib.error.HTTPError as refusal:
            found = _answer(refusal.read(ANSWER_BYTES))
            if found is None or not isinstance(found.get("error"), str):
                raise Unreachable(f"something other than the share service answered for {host} "
                                  f"(HTTP {refusal.code})") from None
            return refusal.code, found, refusal.headers
    except (Unreachable, Damaged):
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
           waiting: Callable[[float], None] | None, **more: Any) -> tuple[int, dict[str, Any] | None, Any]:
    """``_call`` (with ``more``: its ``address``, its ``into``), asked again after each 429's ``Retry-After``
    (``waiting`` told the seconds first), ``WAITS`` times at most and never past ``LONGEST_WAIT``: the status, the
    answer and the headers of the last."""
    for attempt in range(WAITS + 1):
        status, found, told = _call(method, share, path, headers, body, **more)
        seconds = _seconds(told.get("Retry-After") if told is not None else None)
        if status != 429 or attempt == WAITS or seconds > LONGEST_WAIT:
            break
        if waiting is not None:
            waiting(seconds)
        time.sleep(seconds)
    return status, found, told


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
    status, found, _told = _asked("PUT", share, f"/packs/{name}", {
        **_owner(share), "Content-Type": "application/octet-stream", "Content-Length": str(len(pack))}, pack, waiting)
    if status not in (200, 201):
        raise _refused(status, found, "a pack", share)


def _commit(share: Share, body: bytes, waiting: Callable[[float], None] | None) -> dict[str, Any]:
    """``PUT /v1/shares/<id>``: the share's manifest committed. The service's answer, ``{"expires", "bytes", "files",
    "made"}`` (``bytes``: the stored size of the packs it names; ``made``: a new share, 201, or one replaced, 200);
    ``Refused`` for its refusal, a 409's with the packs it found missing."""
    status, found, _told = _asked("PUT", share, "", {**_owner(share), "Content-Type": "application/json",
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


def _manifest(name: str, view: list[File], sources: Sources, where: dict[str, list[list[Any]]]) -> bytes:
    """The share's manifest (``cad-share/2``): its ``name``, the path of the script that builds it among its files
    (``entry``) and what built it (``made``), then its two maps, ``view`` (the view bundle's files) and ``files`` (the
    files that made it), each file by its path, with its bytes' SHA-256 and size, and the ranges of the packs its gzip
    member lies in."""

    def listed(found: Any) -> dict[str, Any]:
        return {file.path: {"sha256": file.sha256, "bytes": file.size, "at": where[file.sha256]} for file in found}

    return json.dumps({"format": FORMAT, "name": name, "entry": sources.entry, "made": sources.made,
                       "view": listed(view), "files": listed(sources.files)}, separators=(",", ":")).encode("utf-8")


def send(share: Share, view: list[File], sources: Sources, stored: dict[str, Any] | None = None, *, name: str,
         waiting: Callable[[float], None] | None = None) -> Sent:
    """The share of ``view`` (``view_files``) and of ``sources`` (the files that made it), named ``name``
    (``share_name``), committed once the packs it names are uploaded: a file whose content ``stored`` holds for this
    share (``STORED``: its last commit) keeps its ranges, and every other goes into new packs, the view's in reading
    order, then the others by their paths; two files of the same bytes are one member, named twice. A commit's 409
    naming missing packs forgets them and sends the files in them again (``RESENDS`` times at most); a 409 naming
    none commits again, once. ``Refused`` for any other refusal (a 403: a share of that id that another write secret
    made, which only a new share can be), ``Unreachable`` where the service does not answer, ``Unsharable`` for a
    file changed meanwhile, or more files than a share holds. ``waiting``: told each wait a 429 asks for."""
    found = [*view, *sources.files]
    if len(found) > MOST_FILES:
        raise Unsharable(f"its view and its files are {len(found)} files, more than the {MOST_FILES} a share holds")
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
            answer = _commit(share, _manifest(name, view, sources, where), waiting)
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
    status, found, _told = _asked("DELETE", share, "", {"Authorization": f"Bearer {secret}"}, None, None)
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


# --- an import ---------------------------------------------------------------------------------------------------


def import_link(text: str, service: str) -> tuple[str, str] | None:
    """What ``cad import`` takes, as ``(origin, id)``: a share's view link (``<origin>/<id>``, whatever its fragment),
    its files' link (``<origin>/<id>.zip``), or its id alone, of the share service at ``service``; None for anything
    else."""
    from urllib.parse import urlsplit

    text = text.strip()
    if _ID.fullmatch(text):
        return service, text
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    ident = parts.path.strip("/")
    ident = ident[:-len(".zip")] if ident.endswith(".zip") else ident
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or not _ID.fullmatch(ident):
        return None
    return f"{parts.scheme}://{parts.netloc}", ident


def _decoded(text: Any) -> str | None:
    """A header's text as the service writes one: UTF-8, every byte but a letter, a digit and ``._~/+-`` as ``%XX``
    (a ``+`` is itself, never a space); None for none, or for bytes that are no UTF-8."""
    from urllib.parse import unquote

    if not isinstance(text, str):
        return None
    try:
        return unquote(text, encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        return None


def download(origin: str, ident: str, into: BinaryIO, *,
             waiting: Callable[[float], None] | None = None) -> dict[str, Any]:
    """``GET <origin>/<id>.zip``: the files that made a share, a zip of one folder, written into ``into``
    (``ZIP_BYTES`` at most), from this process as every request here is; and what its headers say of them: the
    script that builds it (``entry``, ``Cad-Share-Entry``: None for a file document) and what built it (``made``,
    ``Cad-Share-Made``: ``<name>=<value>, ...``; None for a file document). A 429 is waited out as every request's
    is; ``Refused`` for the service's refusal (a 404: no share of that id, expired or deleted), ``Unreachable`` where
    it does not answer, ``Damaged`` for a zip larger than a share's."""
    share = Share(origin, ident, "", "")
    status, found, told = _asked("GET", share, "", {"Accept": "application/zip"}, None, waiting,
                                 address=f"{origin}/{ident}.zip", into=into)
    if status != 200:
        raise _refused(status, found, "the share's files", share)
    made: dict[str, str] = {}
    for part in str(told.get("Cad-Share-Made") or "").split(","):  # a name's or a value's own comma is %2C
        name, equals, value = part.strip().partition("=")
        name, value = _decoded(name.strip()), _decoded(value.strip())
        if equals and name is not None and value is not None:  # either may be empty text, as the manifest's may
            made[name] = value
    return {"entry": _decoded(told.get("Cad-Share-Entry")) or None, "made": made or None}


def _plain(segment: str) -> bool:
    """Whether a path's segment names a file or a folder here as it does everywhere: no empty, ``.`` or ``..``
    segment, nothing unprintable, no ``\\`` or ``:`` (a drive, a stream); on Windows none of its device names and
    nothing it cannot hold (``<>"|?*``, a dot or a space at the end)."""
    if segment in ("", ".", "..") or not segment.isprintable() or "\\" in segment or ":" in segment:
        return False
    if os.name == "nt":
        if any(character in segment for character in '<>"|?*') or segment[-1] in ". " \
                or segment.split(".")[0].strip().upper() in _DEVICES:
            return False
    return True


def zip_entries(archive: zipfile.ZipFile) -> tuple[str, list[tuple[str, zipfile.ZipInfo]]]:
    """A share's zip read as the service makes one: the name of its one folder, and each file in it by its path
    there (``/`` separated), in the zip's order. ``Damaged`` for anything else: an entry outside the folder; a path
    that is absolute, names a drive or holds a segment no folder here takes (``_plain``); a link, or anything but a
    file or a folder; an encrypted entry; a path twice, or a file where another's folder is; more entries than a
    share's. ``Unsafe`` for a folder or a file that would make a later command in the folder written, or below it,
    run what a version control's settings name (``controlled``): one of a ``.git`` (its own name ``.git`` too), a
    repository's bare form. Whoever made the zip, nothing of it is written then."""
    infos = archive.infolist()
    if len(infos) > 2 * MOST_FILES + 1:
        raise Damaged(f"it holds {len(infos)} entries, more than a share's files")
    top: str | None = None
    found: list[tuple[str, zipfile.ZipInfo]] = []
    for info in infos:
        name = info.filename
        if "\\" in info.orig_filename or name.startswith("/") or "\x00" in info.orig_filename:
            raise Damaged(f"{name!r} is no path inside its folder")
        kind = stat.S_IFMT(info.external_attr >> 16)
        if kind == stat.S_IFLNK:
            raise Damaged(f"{name!r} is a link")
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (kind == stat.S_IFDIR and not info.is_dir()):
            raise Damaged(f"{name!r} is neither a file nor a folder")
        if info.flag_bits & 0x1:
            raise Damaged(f"{name!r} is encrypted")
        if info.compress_type not in (0, 8):  # stored or deflated: a share's member, or its bytes
            raise Damaged(f"{name!r} is compressed as no share's file is")
        segments = name.rstrip("/").split("/") if info.is_dir() else name.split("/")
        if any(controls(segment) for segment in segments):
            raise Unsafe(f"it holds {name}, of a version control's folder")
        if not all(_plain(segment) for segment in segments):
            raise Damaged(f"{name!r} is no path inside its folder")
        if top is None:
            top = segments[0]
        if segments[0] != top or (not info.is_dir() and len(segments) < 2):
            raise Damaged(f"{name!r} is outside the one folder a share's zip holds")
        if not info.is_dir():
            found.append(("/".join(segments[1:]), info))
    if top is None:
        raise Damaged("it holds nothing, not even its folder")
    paths = [path for path, _info in found]
    unsafe = controlled([top, *(f"{top}/{path}" for path in paths)])
    if unsafe is not None:
        raise Unsafe(f"it holds {unsafe} beside objects and refs, a repository's bare form")
    if len(set(paths)) != len(paths):
        raise Damaged("it names a file twice")
    named = set(paths)
    for path in paths:
        parts = path.split("/")
        if any("/".join(parts[:end]) in named for end in range(1, len(parts))):
            raise Damaged(f"{path!r} lies in a folder that is a file of it")
    return top, found


def unsafe_folder(folder: Path | str) -> str | None:
    """Why an import may not write into ``folder``, or None: it lies in a version control's folder, or is one
    (``controls``: any segment of its absolute path), or its name with what its parent holds would make that parent a
    repository (``BARE``). Its files are written into it, and then a later command there or above it would run what
    their settings name."""
    folder = Path(os.path.abspath(folder))
    named = next((part for part in folder.parts if controls(part)), None)
    if named is not None:
        return f"{folder} lies in a version control's folder ({named})"
    if _folded(folder.name) in BARE:
        try:
            beside = {_folded(name) for name in os.listdir(folder.parent)}
        except OSError:
            beside = set()
        if BARE <= beside | {_folded(folder.name)}:
            return f"{folder} beside what its folder holds would make that folder a repository"
    return None


def _place(stage: Path, folder: Path) -> None:
    """``stage``'s files moved into ``folder``: renamed as it, where it is not there; else, into it, an empty folder,
    each entry by ``replace_atomic`` (a bare rename loses to a file an SMB share still holds)."""
    from cad._internal.atomic_replace import replace_atomic

    try:
        os.rename(stage, folder)
        return
    except OSError:
        if not folder.is_dir() or any(folder.iterdir()):
            raise
    for entry in os.listdir(stage):
        replace_atomic(stage / entry, folder / entry)
    stage.rmdir()


def unpack(archive: zipfile.ZipFile, entries: list[tuple[str, zipfile.ZipInfo]], folder: Path) -> list[tuple[str, int]]:
    """``entries`` (``zip_entries``) of ``archive`` written into ``folder`` -- one not there yet, or an empty one --
    through a folder made beside it, moved into place once every file is written whole: each checked against its
    CRC-32 as ``zipfile`` reads it, ``IMPORT_BYTES`` at most in all, never over another (two paths this system takes for
    one). Whatever fails leaves no file of this run's (``Damaged`` for the zip's fault, ``OSError`` for the disk's).
    Each file written, by its path, with its size."""
    import zipfile
    import zlib

    folder = Path(os.path.abspath(folder))
    folder.parent.mkdir(parents=True, exist_ok=True)
    # Made as any folder is (``mkdtemp``'s would be this user's alone), and named so no two imports share one.
    stage = folder.parent / f".cad-import-{secrets.token_hex(8)}"
    stage.mkdir()
    written: list[tuple[str, int]] = []
    total = 0
    try:
        for path, info in entries:
            target = stage.joinpath(*path.split("/"))
            size = 0
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, open(target, "xb") as out:
                    while chunk := source.read(1 << 20):
                        size, total = size + len(chunk), total + len(chunk)
                        if total > IMPORT_BYTES:
                            raise Damaged(f"its files are more than the {IMPORT_BYTES // 1024 ** 3} GiB an import "
                                          "writes")
                        out.write(chunk)
            except (FileExistsError, NotADirectoryError):
                raise Damaged(f"two of its files are one file on this computer: {path}") from None
            except (zipfile.BadZipFile, zlib.error, EOFError) as error:
                raise Damaged(f"{path}: {error}") from None
            written.append((path, size))
        _place(stage, folder)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return written


def shared_file(folder: Path | str, paths: list[str], entry: str | None) -> str | None:
    """The file a share is of, among the ``paths`` of its files an import wrote into ``folder`` (``/`` separated): a
    model's ``.xbf`` -- of a share whose ``entry`` is a script, the ``.xbf`` there whose build closure names that script
    (``previous.of``: its path relative to the ``.xbf``'s folder), and of several, the one no other of them read --; of
    one that names none, the one SRDF at its folder's top (drawn with its URDF), else the one URDF there, else the one
    KiCad board among them, else the root of the hierarchy a schematic's sheets draw (``_root_sheet``), else the one
    file it holds. None where none of those names one. Nothing is run: a closure is text an ``.xbf`` holds, a sheet
    names its sheets in its text."""
    from cad.engine import previous
    from cad.registry import type_of

    if entry is not None:
        built: dict[str, dict[str, Any]] = {}
        for path in paths:
            if not path.lower().endswith(".xbf"):
                continue
            try:
                closure = previous.of(Path(folder, *path.split("/")))
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            told = closure.get("source") if isinstance(closure, dict) else None
            named = told.get("path") if isinstance(told, dict) else None
            if isinstance(named, str) and posixpath.normpath(posixpath.join(posixpath.dirname(path), named)) == entry:
                built[path] = closure
        if len(built) > 1:  # a model that read another's .xbf of the same script: the one no other read
            read = {posixpath.normpath(posixpath.join(posixpath.dirname(path), str(row[1])))
                    for path, closure in built.items() for row in closure.get("inputs") or []
                    if isinstance(row, list) and len(row) >= 2 and row[0] in ("file", "read")}
            built = {path: closure for path, closure in built.items() if path not in read}
        return next(iter(built)) if len(built) == 1 else None
    top = [path for path in paths if "/" not in path]
    for kind in ("srdf", "urdf"):
        found = [path for path in top if getattr(type_of(path), "id", None) == kind]
        if len(found) == 1:
            return found[0]
    boards = [path for path in paths if getattr(type_of(path), "id", None) == "kicad_pcb"]
    if len(boards) == 1:
        return boards[0]
    sheet = _root_sheet(Path(folder), [path for path in paths if getattr(type_of(path), "id", None) == "kicad_sch"])
    if sheet is not None:
        return sheet
    return paths[0] if len(paths) == 1 else None


def unheld(folder: Path | str, paths: list[str], shared: str | None) -> list[str]:
    """The files a model's build read that its share does not hold, among the ``paths`` an import wrote into
    ``folder``: each input of kind ``file`` or ``read`` the build found (its digest not null) that the build closure of
    the ``.xbf`` ``shared`` names, as it names it (relative to the ``.xbf``'s folder), where no file of ``paths`` is
    it. A build here reads them where the closure says, so it needs each there. Nothing is run: a closure is text."""
    from cad.engine import previous

    if shared is None or not shared.lower().endswith(".xbf"):
        return []
    try:
        closure = previous.of(Path(folder, *shared.split("/")))
    except (OSError, UnicodeDecodeError, ValueError):
        return []
    held, found = set(paths), []
    for row in (closure or {}).get("inputs") or []:
        if isinstance(row, list) and len(row) >= 3 and row[0] in ("file", "read") and isinstance(row[1], str) \
                and row[-1] is not None:
            at = posixpath.normpath(posixpath.join(posixpath.dirname(shared), row[1]))
            if at not in held and row[1] not in found:
                found.append(row[1])
    return found


# A sheet a schematic draws, by the file its sheet symbol names (KiCad's ``Sheetfile``, once ``Sheet file``).
_SHEET_FILE = re.compile(r'\(\s*property\s+"Sheet ?file"\s+"((?:[^"\\]|\\.)*)"')


def _root_sheet(folder: Path, sheets: list[str]) -> str | None:
    """Of the ``sheets`` an import wrote into ``folder`` (``/`` separated), the root of the hierarchy they draw: the
    one beside a project file of its name (``<project>.kicad_sch``, which KiCad opens the project at), else the one
    no other of them draws as a sheet. None where none is one alone. A share of a schematic holds every sheet of its
    hierarchy, which its root draws, whichever of them was shared: the same pages."""
    from cad.engine.formats.kicad import sexpr

    if not sheets:
        return None
    projects = [path for path in sheets if (folder / f"{posixpath.splitext(path)[0]}.kicad_pro").is_file()]
    if len(projects) == 1:
        return projects[0]
    drawn: set[str] = set()
    for path in sheets:
        try:
            text = Path(folder, *path.split("/")).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _SHEET_FILE.finditer(text):
            named = sexpr.unescape(match.group(1)).replace("\\", "/")
            drawn.add(posixpath.normpath(posixpath.join(posixpath.dirname(path), named)))
    roots = [path for path in sheets if path not in drawn]
    return roots[0] if len(roots) == 1 else None


def import_record(origin: str, ident: str, file: Path | str) -> dict[str, Any]:
    """What the library keeps of an import (``change``'s ``imported``): the share's view link, and the file it wrote
    that the share is of (``shared_file``'s, absolute), whose entry the link is kept in, so the link names it here
    (``copy_of``)."""
    return {"link": f"{origin}/{ident}", "path": os.path.abspath(file)}


def _imported(row: Any) -> bool:
    """Whether ``row`` is an import's (``import_record``): a share's view link and an absolute path."""
    link = parse_link(row["link"]) if isinstance(row, dict) and isinstance(row.get("link"), str) else None
    return link is not None and link[2] is None and isinstance(row.get("path"), str) and os.path.isabs(row["path"])


# --- a share's link as a document's name --------------------------------------------------------------------------


class NoCopy(LookupError):
    """A share's link that names nothing on this computer (``copy_of``): its words, a line, and the command that would
    make a copy (``next``)."""

    def __init__(self, words: str, next: tuple[str, ...] = ()) -> None:  # noqa: A002 - the failure contract's key
        super().__init__(words)
        self.next = next


def document_link(text: object) -> tuple[str, str, str | None] | None:
    """A share's view link where cad takes a document -- ``<origin>/<id>``, of the share service this computer shares
    with (``CAD_SHARE_URL``'s origin) or of cad.fun -- and the ``#<selector>`` after it where a ref is taken, as
    ``(origin, id, selector)``, the selector None where it has none; None for any other text: a path, a document's
    id, a link of another origin or of the share's files."""
    from urllib.parse import urlsplit

    from cad_server._internal.api import SHARE, share_url

    if not isinstance(text, str):
        return None
    head, separator, selector = text.strip().partition("#")
    try:
        parts = urlsplit(head)
    except ValueError:
        return None
    ident = parts.path.strip("/")
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or not _ID.fullmatch(ident):
        return None
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin.lower() not in (share_url().lower(), SHARE.lower()):
        return None
    return origin, ident, selector if separator else None


def _of(link: str, origin: str, ident: str) -> bool:
    """Whether a record's view link is the share at ``origin`` with the id ``ident``."""
    found = parse_link(link)
    return found is not None and found[1] == ident and found[0].lower() == origin.lower()


def copy_of(origin: str, ident: str) -> str:
    """The path of this computer's copy of the share at ``origin`` with the id ``ident``, as the library holds it: the
    file it shared under that link (an entry's ``shares``, ``records``); else the file an import of it wrote (an
    entry's ``imported``: a model's ``.xbf`` among the files, there with nothing run). ``NoCopy``, in a line naming the
    import that makes one, for a link this computer neither shared nor imported, and one whose import's file is gone."""
    link = f"{origin}/{ident}"
    for row in records():
        if row["id"] == ident and row["service"].lower() == origin.lower():
            return row["document"]["path"]
    command = f"cad import {link}"
    for entry in _library().read()["files"].values():
        if isinstance(entry.get("imported"), str) and _of(entry["imported"], origin, ident) \
                and os.path.isfile(entry["path"]):
            return entry["path"]
    raise NoCopy(f"{link} is a shared model this computer has no copy of: run `{command}`.", (command,))


def local(text: str, *, ref: bool = False) -> str:
    """``text`` -- a document's name, or with ``ref`` a ref's (``FILE#SELECTOR``) -- with the share's link it starts
    with (``document_link``) in the name of this computer's copy of that share (``copy_of``), its ``#<selector>`` kept:
    a ref's selector is the same in the copy as in the share. A ref's file is JSON-quoted where it holds a ``#`` or a
    quote, as the refs grammar reads one. Any other text as it is; ``NoCopy`` where this computer has no copy."""
    found = document_link(text)
    if found is None:
        return text
    origin, ident, selector = found
    name = copy_of(origin, ident)
    if selector is None:
        return name
    if ref and ("#" in name or '"' in name):
        name = json.dumps(name, ensure_ascii=False)
    return f"{name}#{selector}"


# --- what is kept ------------------------------------------------------------------------------------------------


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def expired(record: dict[str, Any]) -> bool:
    """Whether a record's share is past its expiry, as the service said it: then the service holds it no more."""
    from cad_server.engine.library import live

    return not live(record)


def _library() -> Any:
    """The library of this computer's state folder (``cad_server.engine.library``), where what sharing keeps of a
    file is its entry's."""
    from cad_server.engine.library import Library

    return Library()


def library_path() -> Path:
    from cad.engine.places import state_dir
    from cad_server.engine.library import LIBRARY

    return state_dir() / LIBRARY


def _held(service: Any, share: Any) -> bool:
    """Whether ``share`` is one of an entry's ``shares`` as ``record_of`` keeps it, at ``service``: its view link of
    that origin, its two keys, its expiry, and where the files that made it are."""
    link = parse_link(share["link"]) if isinstance(share, dict) and isinstance(share.get("link"), str) else None
    return (link is not None and link[2] is None and isinstance(service, str) and link[0] == service
            and all(isinstance(share.get(name), str) and _SECRET.fullmatch(share[name]) for name in ("write", "delete"))
            and isinstance(share.get("expires"), str)
            and all(isinstance(share.get(name), (str, type(None))) for name in ("root", "entry")))


def _row(ident: str, path: str, service: str, share: dict[str, Any]) -> dict[str, Any]:
    """A share of the file at ``path`` (of id ``ident``) at ``service``, as the library keeps it, made a record
    (``record_of``'s): the file's kind and name worked out from its path."""
    from cad.registry import type_of

    found = type_of(path)
    kind = found.wire if found is not None else "file"
    view = share["link"]
    return {"id": view.rsplit("/", 1)[1], "write": share["write"], "delete": share["delete"], "service": service,
            "view": view, "remove": f"{view}#delete={share['delete']}", "expires": share["expires"],
            "document": {"id": ident, "kind": kind,
                         "name": share_name(Path(path).stem if kind == "xbf" else os.path.basename(path)),
                         "path": path},
            "files": {"root": share.get("root"), "entry": share.get("entry")}}


def records() -> list[dict[str, Any]]:
    """Every share this computer keeps, a record each (``record_of``'s), the expired among them where the library is
    not written since: each file's ``shares`` in the library, one a shared file and service."""
    found = []
    for ident, entry in _library().read()["files"].items():
        shares = entry.get("shares")
        for service, share in (shares.items() if isinstance(shares, dict) else ()):
            if _held(service, share):
                found.append(_row(ident, entry["path"], service, share))
    return found


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


def record_of(share: Share, document: dict[str, Any], answer: dict[str, Any], sources: Sources) -> dict[str, Any]:
    """A share's record, one a shared file and service: its names and links, when it expires, the file it is of
    (``document``: ``{"id", "kind", "name", "path"}``, ``path`` the file's canonical path, its entry's in the library,
    and ``id`` that path's), and where on this computer the files that made it are (``files``: their ``root``, and the
    script among them, ``entry``, a model's), which ``cad import`` of its link points at rather than downloading them.
    The library keeps it in the file's entry (``change``), of which ``records`` makes it again."""
    return {"id": share.id, "write": share.write, "delete": share.delete, "service": share.service,
            "view": share.view, "remove": share.remove, "expires": answer["expires"], "document": document,
            "files": {"root": sources.root, "entry": sources.entry}}


def _record(row: Any) -> bool:
    """Whether ``row`` is a share's record (``record_of``): what the server keeps for a command, and nothing else."""
    from cad.engine.ids import is_id

    if not isinstance(row, dict):
        return False
    document, files = row.get("document"), row.get("files", {})
    return (isinstance(row.get("id"), str) and _ID.fullmatch(row["id"]) is not None
            and all(isinstance(row.get(name), str) and _SECRET.fullmatch(row[name]) for name in ("write", "delete"))
            and isinstance(row.get("expires"), str)
            and isinstance(row.get("service"), str) and row["service"].startswith(("https://", "http://"))
            and row.get("view") == f"{row['service']}/{row['id']}" and isinstance(document, dict)
            and is_id(document.get("id")) and isinstance(document.get("path"), str) and os.path.isabs(document["path"])
            and isinstance(files, dict) and all(isinstance(files.get(name), (str, type(None)))
                                                for name in ("root", "entry")))


def recorded(rows: list[dict[str, Any]], service: str, path: str) -> dict[str, Any] | None:
    """The live record among ``rows`` of the file at canonical ``path`` shared to ``service``; None where there is
    none (it was never shared from this path, or its share expired)."""
    return next((row for row in rows if row["service"] == service and row["document"].get("path") == path
                 and not expired(row)), None)


def made_here(origin: str, ident: str) -> dict[str, Any] | None:
    """The record of a share this computer made (``records``) at ``origin`` with the id ``ident``, live, whose file is
    where it was shared from still; None for any other -- another computer's share, one expired, one whose file moved
    or went -- and where the records cannot be read."""
    try:
        rows = records()
    except OSError:
        return None
    for row in rows:
        if row["id"] != ident or row["service"].lower() != origin.lower() or expired(row):
            continue
        path = row["document"].get("path")
        return row if isinstance(path, str) and os.path.isfile(path) else None
    return None


def folder_of(document: str) -> Path:
    """A shared file's folder in cad's cache, the one the cache keeps of that file, ``documents/<id>`` (the engine's
    **The store**; its note and picture are beside what a share keeps there): ``ValueError`` for anything but a
    document's id, so no other folder is ever named."""
    from cad.engine.ids import is_id
    from cad.engine.places import cache_dir
    from cad_server.engine.library import DOCUMENTS

    if not is_id(document):
        raise ValueError(f"{document!r} is no document's id")
    return cache_dir() / DOCUMENTS / document


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
    """Whether ``folder`` holds none of what a share keeps there but its lock: no view bundle, no ``STORED``."""
    return not any(os.path.lexists(folder / name) for name in (VIEW, STORED))


def _remove(folder: Path) -> None:
    """A folder's lock removed, and the folder with it where nothing else is left in it (what the cache keeps of the
    file beside a share stays), as far as the system lets it (Windows removes no file one holds open)."""
    with contextlib.suppress(OSError):
        (folder / LOCK).unlink(missing_ok=True)
        folder.rmdir()


@contextlib.contextmanager
def held(folder: Path, *, wait: float = 0.0, waiting: Callable[[], None] | None = None,
         make: Callable[[], Any] | None = None) -> Iterator[None]:
    """One ``cad share`` of a file at a time: its folder's ``LOCK`` held for the block. Where another holds it,
    ``waiting`` is told once and the lock waited for ``wait`` seconds, then ``Busy``. A lock file that is not there,
    or was removed while this waited (its share deleted meanwhile), is made again by ``make``; with no ``make``,
    ``FileNotFoundError``. As it is let go, a folder that holds none of a share's files loses its lock, and goes too
    where nothing else is left in it: a share deleted, or one that wrote nothing. A lock removed while held is removed
    while still held, so a waiter finds it gone."""
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
    """What a share keeps in a file's folder removed, its lock alone left: the caller holds the lock, which goes as it
    is let go (``held``). Nothing else of the folder is touched: what the cache keeps of the file (its note, its
    picture, its kept checks) is not a share's."""
    with contextlib.suppress(OSError):
        shutil.rmtree(folder / VIEW)
    with contextlib.suppress(OSError):
        (folder / STORED).unlink()


def _sweep(live: set[str], spared: str | None) -> None:
    """What a share keeps in each file's folder of the cache that no live record names (``live``: their files' ids)
    removed, but ``spared``'s and one whose lock another holds (a share being made): a share deleted, expired or never
    committed."""
    from cad.engine.ids import is_id
    from cad.engine.places import cache_dir
    from cad_server.engine.library import DOCUMENTS

    try:
        entries = list(os.scandir(cache_dir() / DOCUMENTS))
    except OSError:
        return
    for entry in entries:
        if entry.name in live or entry.name == spared or not is_id(entry.name) \
                or not entry.is_dir(follow_symlinks=False):
            continue
        folder = Path(entry.path)
        if _alone(folder) and not os.path.lexists(folder / LOCK):
            continue  # a file's folder no share ever wrote in
        try:
            with held(folder):
                _clear(folder)
        except (Busy, OSError):
            continue


def _write_stored(folder: Path, kept: dict[str, Any]) -> None:
    from cad._internal.atomic_replace import write_bytes_atomic

    folder.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(folder / STORED, json.dumps(kept, separators=(",", ":")).encode("utf-8"))


def _keep_record(record: dict[str, Any]) -> Callable[[dict[str, Any]], None]:
    """The library changed to keep ``record`` (``record_of``'s) in its file's entry, at its service, in place of any
    share of that file there and of the same share anywhere else: a share is of one file."""
    def put(data: dict[str, Any]) -> None:
        for entry in data["files"].values():
            shares = entry.get("shares")
            for service in [service for service, share in (shares.items() if isinstance(shares, dict) else ())
                            if isinstance(share, dict) and _of(str(share.get("link")), service, record["id"])]:
                del shares[service]
            if isinstance(shares, dict) and not shares:
                del entry["shares"]
        path = record["document"]["path"]
        entry = data["files"].setdefault(record["document"]["id"], {"path": path, "created": time.time()})
        entry.setdefault("shares", {})[record["service"]] = {
            "link": record["view"], "write": record["write"], "delete": record["delete"],
            "expires": record["expires"], "root": record["files"]["root"], "entry": record["files"]["entry"]}

    return put


def _forget(ident: str) -> Callable[[dict[str, Any]], None]:
    """The library changed to drop the share of the id ``ident`` from the entry that keeps it."""
    def drop(data: dict[str, Any]) -> None:
        for entry in data["files"].values():
            shares = entry.get("shares")
            for service in [service for service, share in (shares.items() if isinstance(shares, dict) else ())
                            if isinstance(share, dict) and _of(str(share.get("link")), service, ident)]:
                del shares[service]
            if isinstance(shares, dict) and not shares:
                del entry["shares"]

    return drop


def _import(row: dict[str, Any]) -> Callable[[dict[str, Any]], None]:
    """The library changed to keep an import's ``row`` (``import_record``'s): its file's entry, made where it had
    none, holds the link it came from, which no other entry holds then: a link names the latest import of it."""
    from cad.engine.ids import canonical, file_id

    path = canonical(row["path"])
    origin, ident, _none = parse_link(row["link"]) or ("", "", None)  # a view link: ``_imported`` holds it so

    def put(data: dict[str, Any]) -> None:
        for entry in data["files"].values():
            if isinstance(entry.get("imported"), str) and _of(entry["imported"], origin, ident):
                del entry["imported"]
        data["files"].setdefault(file_id(path), {"path": path, "created": time.time()})["imported"] = row["link"]

    return put


def change(request: dict[str, Any]) -> dict[str, Any]:
    """One change of what is kept, in this process: ``{"set": "on"|"off"}``, ``{"agree": true}``, ``{"folder":
    <file's id>}`` (the file's folder in the cache made, with its lock: answered as ``folder``), ``{"record": <a share's
    record>, "stored": <its STORED>}`` (the record kept in its file's entry of the library, in place of any of the same
    share, or of the same file at the same service, and ``stored``, where given, written in the file's folder),
    ``{"forget": <share id>}`` (the share dropped from its entry, and what it kept in its file's folder, which the asker
    holds the lock of, removed, where no other live share is of that file) or ``{"imported": <an import's record>}``
    (``import_record``: its file's entry holds its link). A share past its expiry goes from its entry as the library is
    written, and what a share kept in every folder no live share's file names is removed (``_sweep``), under the
    library's lock. ``{"ok": true, "settings"}``, or ``{"failed"}`` in one line for a change it does not take.
    ``OSError`` where the state folder cannot be written."""
    from cad_server.engine.library import live as alive
    from cad_server.settings import update_section

    asked = [name for name in ("set", "agree", "folder", "record", "forget", "imported") if name in request]
    if len(asked) != 1 or ("stored" in request and asked != ["record"]):
        return {"failed": "a change of what sharing keeps is one of set, agree, folder, record (with stored), forget "
                          "or imported"}
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
    elif "imported" in request:
        if not _imported(request["imported"]):
            return {"failed": "not an import's record"}
        _library().change(_import(request["imported"]))
    else:
        record, forget, kept = request.get("record"), request.get("forget"), request.get("stored")
        if "record" in request and not _record(record):
            return {"failed": "not a share's record"}
        if "stored" in request and not (_stored(kept) and kept["share"] == hashlib.sha256(
                record["id"].encode("ascii")).hexdigest()):
            return {"failed": "not where the files of that record's share are"}
        if "forget" in request and not (isinstance(forget, str) and _ID.fullmatch(forget)):
            return {"failed": "forget names a share's id"}
        library = _library()
        # The folders, under the library's lock: a share another command keeps meanwhile is one this reads.
        with library._lock():
            gone = [row["document"]["id"] for row in records() if row["id"] == forget]
            data = library.change(_keep_record(record) if record is not None else _forget(forget))
            live = {ident for ident, entry in data["files"].items()
                    if any(alive(share) for share in (entry.get("shares") or {}).values())}
            for ident in gone:
                if ident not in live:
                    _clear(folder_of(ident))
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
