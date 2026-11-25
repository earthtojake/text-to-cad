"""Recents: the engine's registry of documents, as every CAD view's home lists it.

Every CAD view writes here -- the MCP app's views and the viewer -- and every
home shows all of it (``GET /api/v1/documents``, which the MCP app's views reach
through its tunnel).

Recents is a view of the registry (``cad_server.engine.registry``, ``<state>/documents/<id>/document.json``):
a CAD file opened on a page is a record of its own (``kind: "file"``: its path, when it was first
opened, ``created``, and last, ``opened``, whether it is pinned), and every model a script built is one already (``kind: "model"``, which the
engine writes when it registers the build), as is every shape a program handed over (``kind:
"shape"``). The home's picture of each is UI state on its record (``preview``), the PNG under
``recents/thumbnails`` named by the record and its content: the light viewport's, which the home
shows in both themes. A project's file the home pictures before any page opened it (``projects.py``)
is given a record to keep its picture on, with no ``opened`` and no ``created``, which the first page to
open it gives it: Recents lists a file only once a page opened it (``RecentStore.list``), and a project
lists its files whatever their records (``RecentStore.entries``).

A row says how many part occurrences its document holds (``parts``: what ``cad model inspect`` counts as its
parts' occurrences) where its record says, and null where it does not: a model's and a shape's from its last build
(the record's ``facts``, which the engine writes when it registers the build or the hand-over); an ``.xbf`` the
engine wrote (a build's declared file, an export) from the document it wrote it from, as it wrote it
(``Models.written``); any other file the engine read because a page opened it (an ``.xbf``, a STEP) from that read
(``RecentStore.counted``) -- a file's only while the file is the version counted. A listing reads records alone:
nothing is read to count them, a model's script never, a file's bytes never.

An ``.xbf`` the engine wrote from a model's document -- the build's declared file, an export of the model's id, the
viewer's export -- is that model, and a listing shows one card of them (``fold``): its record names the model, the
file's version as written and the document's revision (``of``: ``Models.written``), and while the file is still
that version and the model's record still that revision, the file's row says whose it is (``of``) and is left out of
any list that holds the model's row (``fold``). A file edited or copied since, or one whose model was built into
another revision since (an export the build did not write again: an older model now), is a file of its own. A
model's row says where its declared ``.xbf`` is (``saved``) while that file is the model so.

The pictures are bounded however often a document is edited: a record names one, a new picture
replaces it at once (``RecentStore.thumbnail``: the old one goes as the new is named), only
the ``LIMIT`` records the home lists first keep theirs, within ``THUMBNAIL_BYTES`` in all (the rest,
least recently used first, lose theirs, which a page takes again when it shows them), a forgotten
record's go with it (``Registry.delete``), and a PNG no record names goes once no writer can still be
about to name it (``THUMBNAIL_GRACE_SECONDS``: a crash's, or an earlier release's). Removing a file's entry forgets its record, the file
untouched; a model's entry is deleted with its document (``cad_server.engine.models.delete``: its record
and its document in the engine's cache). Nothing goes on its own: a model whose script is gone stays
listed, ``missing``, until the person deletes it.

A file is named by its canonical path (``cad.engine.ids.canonical``), the engine's, and its
record by that path's id, so a symlink and its target, or two spellings of one file, are one
entry. A model is named by its id, which is also the ``path`` the home opens it by (``/<id>``).

Every write goes through the registry's one owner of the state folder (``registry.Folder``), and
lands whole. Each record is its own file, so two processes opening different files never meet; a
change of one record is a read and a write under the registry's lock.
"""

from __future__ import annotations

import hashlib
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cad.engine.places import cache_dir, state_dir
from cad_server.engine.registry import PICTURES as THUMBNAILS
from cad_server.engine.registry import file_record, pictures

LIMIT = 200
MAX_THUMBNAIL_BYTES = 512 * 1024
# Every picture kept, in all: the ``LIMIT`` records' first, until this is reached (a board's pair is
# about 250 KB, a part's one picture a few tens).
THUMBNAIL_BYTES = 64 * 1024 * 1024
THUMBNAIL_GRACE_SECONDS = 600


def thumbnail_png(encoded) -> bytes:
    """A thumbnail as a view sends it, base64; ``ValueError`` for anything but a small PNG."""
    import base64
    import binascii

    try:
        png = base64.b64decode(encoded or "", validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("the thumbnail is not base64") from error
    if not png.startswith(b"\x89PNG") or len(png) > MAX_THUMBNAIL_BYTES:
        raise ValueError("a thumbnail is a PNG of at most 512 KiB")
    return png


@dataclass
class Recent:
    """One entry of Recents: a file's (``path`` its canonical path) or a model's (``path`` its id)."""

    path: str
    # When a page last opened it (the record's ``opened``); None for a model no page has opened.
    opened: float | None
    # When it last changed: a file's mtime (the file itself; None once it is gone), a model's or a
    # shape's run (the record's ``built``). A model's script is never read for it.
    updated: float | None = None
    # When its record was first made (the record's ``created``): a model's first run, a file's first
    # open, a shape's first hand-over; None for a record from before the engine kept it.
    created: float | None = None
    pinned: bool = False
    thumbnail: str | None = None
    # When the picture was taken, in seconds: a document updated since has an old one.
    pictured: float | None = None
    # A file's size on disk, in bytes (None once it is gone); a model's and a shape's: None, its
    # script never read.
    size: int | None = None
    # ``file``, ``model`` or ``shape`` (the record's ``kind``).
    kind: str = "file"
    # A model's (and a shape's): its name, its script, and the command that builds it again.
    name: str | None = None
    namespace: str | None = None
    script: str | None = None
    rebuild: str | None = None
    # A shape handed over: its home is the script or the folder it was handed over from, nothing
    # builds it again, and ``shown`` says so, from the program that handed it over.
    shown: str | None = None
    # How many part occurrences its document holds, where its record says (the module): None where it does not.
    parts: int | None = None
    # A model and an .xbf the engine wrote from its document (the module): the file's, that model's id (``of``) and
    # the revision written (``written``), while the file is the version written; a model's (and a shape's), its
    # revision now (``revision``) and the path of its declared .xbf while that file is the model so (``saved``).
    of: str | None = None
    written: str | None = None
    revision: str | None = None
    saved: str | None = None

    @property
    def activity(self) -> float:
        """Its last activity, the library's order: the later of when it was opened and updated."""
        return max(self.opened or 0, self.updated or 0)

    def row(self) -> dict[str, Any] | None:
        """The entry as every list of Recents carries it -- ``GET /api/v1/documents``'s rows and a CAD
        app home's launch alike: its public row (``public``) with its document's ``id``, ``kind`` and
        ``api``, its record's own kind as ``record``; None for a file no page reads."""
        from cad.engine.ids import file_id

        from .kinds import document_api, file_kind
        from .scanner import VIEWER_EXTENSIONS, extension_of

        if self.kind == "file":
            kind = file_kind(self.path)
            if kind is None or extension_of(self.path) not in VIEWER_EXTENSIONS:
                return None
            ident = file_id(self.path)
        else:
            # A model's document, or a shape a program handed over: either is the engine's, read as a model's.
            kind, ident = "model", self.path
        return {**self.public(), "id": ident, "kind": kind, "record": self.kind, "api": document_api(kind, ident)}

    def public(self) -> dict[str, Any]:
        """The row a home reads: its times (``opened``, ``updated``, ``created``). Of a model's script only whether
        it is still there is asked (``missing``), never its contents or its times: the engine reads a
        script in a run alone."""
        if self.kind == "file":
            present, folder = self.updated is not None, os.path.dirname(self.path)
        else:
            # A shape's document is the engine's, not its home's: a folder home (a REPL's) is where it
            # came from, and nothing of it goes missing (``registry.detached``).
            present = self.kind == "shape" or bool(self.script and os.path.isfile(self.script))
            folder = self.script if self.script and self.kind == "shape" and os.path.isdir(self.script) \
                else os.path.dirname(self.script or "")
        found = {
            "path": self.path,
            "name": self.name or os.path.basename(self.path),
            # Where it is, as the person reads it: a file's folder, a model's script's.
            "folder": folder,
            "namespace": self.namespace or folder,
            "opened": self.opened,
            "updated": self.updated,
            "created": self.created,
            "pinned": self.pinned,
            # A file that is gone, or a model whose script is (``detached``): listed, and removable.
            "missing": not present,
            "thumbnail": self.thumbnail,
            "pictured": self.pictured,
            "size": self.size,
            "parts": self.parts,
        }
        found["kind"] = self.kind
        if self.kind == "file" and self.of is not None:
            found["of"] = self.of
        if self.kind != "file":
            found.update(id=self.path, script=self.script, rebuild=self.rebuild)
            if self.saved is not None:
                found["saved"] = self.saved.replace(os.sep, "/")
        if self.kind == "shape":
            found.update(shown=self.shown or "a shape handed over: no script to rerun")
        return found


def _on_disk(path: str) -> tuple[float | None, int | None, str | None]:
    """A CAD file's time and size on disk, and its version as the engine names the file state it read
    (``mtime_ns-size``, a served structure's ``version``: ``registry.file_version``), from one stat; None for
    each once it is gone (or is no file)."""
    try:
        status = os.stat(path)
    except OSError:
        return None, None, None
    if not stat.S_ISREG(status.st_mode):
        return None, None, None
    return status.st_mtime, status.st_size, f"{status.st_mtime_ns}-{status.st_size}"


def _parts(facts: Any, version: str | None = None) -> int | None:
    """How many part occurrences a record's ``facts`` say its document holds: a model's or a shape's as they
    are, a file's (``version`` its version on disk now) only where they are of that version; None for none."""
    if not isinstance(facts, dict):
        return None
    if version is not None and facts.get("version") != version:
        return None
    found = facts.get("parts")
    return found if type(found) is int and found >= 0 else None


class RecentStore:
    """Recents over the registry of the state folder ``root`` (``places.state_dir`` by default)."""

    def __init__(self, root: Path | None = None) -> None:
        from cad_server.engine.registry import Folder, Registry

        self.state = Folder(root or state_dir())
        self.registry = Registry(self.state, cache=cache_dir())
        self.root = self.state.root / "recents"
        self.thumbnails = self.state.path(THUMBNAILS)

    # -- writes ----------------------------------------------------------------

    def opened(self, path: str) -> dict | None:
        """A CAD file opened on a page: its record, opened now, and made now (``created``) when it had
        none. A model's id: its record (the engine's, written by its run) says when a page opened it,
        and nothing else of it changes. The record as it is now: None for an id no document has."""
        from cad.engine.ids import canonical, file_id, is_id

        now = time.time()
        if is_id(path):
            return self._change(path, lambda record: {**record, "opened": now})
        found = canonical(path)

        def change(record):
            # Where it is now, as its record says it (``root``, ``home``): one an earlier release wrote is
            # said again as this one says it. Made now (``created``) where no page opened it before: a new
            # record, or one the home's picture made. A record from before ``created`` was kept stays without.
            made = file_record(found)
            first = record is None or not record.get("opened")
            return {**made, **({"created": now} if first else {}), **(record or {}),
                    **{key: made[key] for key in ("root", "home", "namespace", "name")}, "opened": now}

        return self.registry.update(file_id(found), change)

    def counted(self, ident: str, structure: dict[str, Any]) -> None:
        """What the engine read of the CAD file of id ``ident`` (``structure``, the document it serves of an
        ``.xbf`` or a STEP, read because a page opened it): how many part occurrences it holds and the file's
        version they are of, on its record (``Registry.counted``) where it has one -- a file no page opened or
        pictured has none, and is given none for it."""
        self.registry.counted(ident, len(structure.get("instances") or []), str(structure.get("version") or ""))

    def pin(self, path: str, pinned: bool) -> None:
        self._change(path, lambda record: {**record, "pinned": bool(pinned)})

    def remove(self, path: str) -> None:
        """Forget a file's entry: its record. The file stays where it is."""
        self.registry.delete(self._ident(path))

    def thumbnail(self, path: str, png: bytes, *, make: bool = False) -> str:
        """Keep a PNG for an entry (a file's path, or a model's id): its name. It replaces the record's
        picture in place: written and named under the record's lock, the one it named before then
        removed (``_sweep_thumbnails``). An entry with no record keeps nothing, but for a CAD file with
        ``make`` (one of a project's, which the home pictures before any page opens it): it is given a
        record, not opened, which keeps the picture, and Recents lists it only once a page opens it."""
        from cad.engine.ids import is_id

        ident = self._ident(path)
        name = _picture_name(ident, png)
        before: set[str] = set()

        def change(record):
            if record is None:
                if not make or is_id(path) or not _cad_file(path):
                    return None
                record = file_record(path)
            before.update(pictures(record))
            if not (self.thumbnails / name).exists():
                self.state.write(f"{THUMBNAILS}/{name}", png)
            return {**record, "preview": {"thumbnail": name, "pictured": time.time()}}

        self.registry.update(ident, change)
        self._sweep_thumbnails(before - {name})
        return name

    def read_thumbnail(self, name: str) -> bytes | None:
        if not name or "/" in name or "\\" in name or not name.endswith(".png"):
            return None
        return self.state.read(f"{THUMBNAILS}/{name}")

    def _ident(self, path: str) -> str:
        from cad.engine.ids import file_id, is_id

        return path if is_id(path) else file_id(path)

    def _change(self, path: str, change) -> dict | None:
        """A change to an entry's record, when it has one (a file not opened has none): the record as it is now."""
        return self.registry.update(self._ident(path), lambda record: change(record) if record is not None else None)

    # -- reads -----------------------------------------------------------------

    def list(self) -> list[Recent]:
        """Recents: pinned first, then by last activity (``Recent.activity``), newest first; at most ``LIMIT``.
        A file is in it once a page opened it (a project's file pictured on the home alone is not)."""
        listed = [entry for entry in self.entries() if entry.kind != "file" or entry.opened is not None]
        return sorted(listed, key=lambda entry: (not entry.pinned, -entry.activity))[:LIMIT]

    def entries(self) -> list[Recent]:
        """Every record's entry, in no order: every model's and shape's, and every file's, opened or not."""
        from cad_server.engine import registry as registering
        from cad_server.engine.models import Models

        entries = []
        for record in self.registry.list():
            preview = record.get("preview") or {}
            common = {"pinned": bool(record.get("pinned")), "thumbnail": preview.get("thumbnail"),
                      "pictured": preview.get("pictured"), "created": record.get("created")}
            if record.get("kind") == "file":
                path = str(registering.home(self.registry, record))
                updated, size, version = _on_disk(path)
                opened = record.get("opened")
                of = record.get("of") if isinstance(record.get("of"), dict) else {}
                entries.append(Recent(path=path, opened=float(opened) if isinstance(opened, (int, float)) and opened else None,
                                      updated=updated, size=size, parts=_parts(record.get("facts"), version)
                                      if version else None,
                                      of=of.get("id") if version and of.get("version") == version
                                      and isinstance(of.get("id"), str) else None,
                                      written=of.get("revision") if isinstance(of.get("revision"), str) else None,
                                      **common))
            elif record.get("kind") in ("model", "shape"):
                program = registering.program(self.registry, record)
                entries.append(Recent(path=record["id"], kind=record["kind"], name=record.get("name") or record.get("entry"),
                                      namespace=record.get("namespace") or record.get("root"),
                                      script=str(registering.home(self.registry, record)),
                                      rebuild=registering.command(self.registry, record),
                                      shown=Models.shown(str(program) if program else None)
                                      if record["kind"] == "shape" else None, updated=record.get("built"),
                                      opened=record.get("opened"), parts=_parts(record.get("facts")),
                                      saved=os.path.normpath(self.registry.root(record) / record["saved"])
                                      if record["kind"] == "model" and isinstance(record.get("saved"), str) else None,
                                      revision=record.get("revision") if isinstance(record.get("revision"), str)
                                      else None, **common))
        return _linked(entries)

    def _sweep_thumbnails(self, replaced: set[str] | frozenset[str] = frozenset()) -> None:
        """The pictures held to their bound (the module): the pictures of the ``LIMIT`` records used
        most recently (pinned first, then by when they were last opened, built or pictured) are kept
        while they fit in ``THUMBNAIL_BYTES``, and every other record's are taken off it and removed;
        ``replaced`` (a record's pictures a new one replaced) go now; any other picture no record
        names goes once it is old enough that no writer can still be about to name it (a writer saves
        the PNG, then writes its record)."""
        ranked = sorted((record for record in self.registry.list() if pictures(record)),
                        key=lambda record: (not record.get("pinned"), -_used(record)))
        kept: set[str] = set()
        gone = set(replaced)
        total = 0
        for rank, record in enumerate(ranked):
            names = pictures(record)
            size = sum(self._size(name) for name in names - kept)
            if rank < LIMIT and total + size <= THUMBNAIL_BYTES:
                kept |= names
                total += size
                continue
            preview = record.get("preview")
            self.registry.update(record["id"], lambda found, preview=preview: (
                {key: value for key, value in found.items() if key != "preview"}
                if found is not None and found.get("preview") == preview else None))
            gone |= names
        cutoff = time.time() - THUMBNAIL_GRACE_SECONDS
        for name in self.state.names(THUMBNAILS):
            if not name.endswith(".png") or name in kept:
                continue
            try:
                if name in gone or (self.thumbnails / name).stat().st_mtime < cutoff:
                    self.state.remove(f"{THUMBNAILS}/{name}")
            except OSError:
                continue

    def _size(self, name: str) -> int:
        try:
            return (self.thumbnails / name).stat().st_size
        except OSError:
            return 0


def _linked(entries: list[Recent]) -> list[Recent]:
    """``entries`` with each ``.xbf`` the engine wrote from a model's document linked to that model (``Recent.of``)
    only while the model's record is still the revision it was written from -- the file's version was checked as it
    was read -- and each model's declared ``.xbf`` named (``Recent.saved``) only while that file is linked to it;
    unlinked anywhere else: a model deleted, or built into another revision since."""
    def key(path: str) -> str:
        return os.path.normcase(os.path.normpath(path))

    models = {entry.path: entry for entry in entries if entry.kind in ("model", "shape")}
    files: dict[str, Recent] = {}
    for entry in entries:
        if entry.kind != "file" or entry.of is None:
            continue
        model = models.get(entry.of)
        if model is None or model.revision is None or model.revision != entry.written:
            entry.of = None
        else:
            files[key(entry.path)] = entry
    for entry in models.values():
        found = files.get(key(entry.saved)) if entry.saved else None
        if found is None or found.of != entry.path:
            entry.saved = None
    return entries


def fold(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A listing's ``rows`` (Recents', a project's) with each ``.xbf`` that is a model's document left out where the
    model's own row stands for it: a file row the person has not pinned whose ``of`` (``Recent.of``: unchanged since
    the engine wrote it from the model's document, and the model still that revision) names a model's (or a shape's)
    row of the same list, in the same project, whose script is there. Anything else is listed as any file is: a file
    edited or copied, a model built into another revision since, deleted or not in this list. Records alone are
    read: no file's bytes, no script."""
    models = {row["id"]: row for row in rows if row.get("record") in ("model", "shape") and not row.get("missing")}

    def folded(row: dict[str, Any]) -> bool:
        model = models.get(row.get("of")) if row.get("record") == "file" else None
        return model is not None and not row.get("pinned") and model.get("project") == row.get("project")

    return [row for row in rows if not folded(row)]


def _cad_file(path: str) -> bool:
    """Whether ``path`` is a CAD file there now, of a type every view opens."""
    from .scanner import VIEWER_EXTENSIONS, extension_of

    return extension_of(path) in VIEWER_EXTENSIONS and os.path.isfile(path)


def _picture_name(ident: str, png: bytes) -> str:
    """A picture's file name: of its record and its bytes, so no two records share one (a record's
    picture goes with it) and a new picture is a new name (a page keeps a picture by it)."""
    digest = hashlib.sha256(f"{ident}\0".encode("utf-8"))
    digest.update(png)
    return digest.hexdigest()[:32] + ".png"


def _used(record: dict) -> float:
    """When a record was last used, as far as its record says: opened, built or pictured."""
    preview = record.get("preview") if isinstance(record.get("preview"), dict) else {}
    times = (record.get("opened"), record.get("built"), preview.get("pictured"))
    return max((float(value) for value in times if isinstance(value, (int, float)) and not isinstance(value, bool)), default=0.0)
