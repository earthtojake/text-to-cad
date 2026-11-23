"""Projects: folders a person opened as one, each with the documents in it.

A folder becomes a project only when someone opens it as one: ``cad viewer <folder>``, or Import,
Folder on the viewer's Home (``POST /api/v1/projects``), which a standalone document's menu offers
too, starting at its folder. Nothing else makes one: a run never does, no file in the folder marks
one, and nothing is written to the folder. A project is one record in the state folder,
``<state>/projects/<id>.json`` (``{schema, id, root, created, opened}``: ``root`` the folder's
canonical path, its id derived from it, ``ids.derived_id``). Remove forgets that record alone: the
folder and everything in it stay as they are, and its documents are standalone again.

A document belongs to the nearest project above it (``Projects.of``): a file by its path, a model by
its script, a shape by where it was handed over. So a folder opened inside a project is that
project (``Projects.add`` answers it and makes no record: projects do not nest by accident), and a
project opened around another leaves the inner one its own, with its documents.

A project's documents (``Projects.documents``) are its models -- the registry's, whose script is in
it -- then its CAD files, found by a walk of its folder that no folder can hold up: it stops at
``WALK_LIMIT`` files, ``WALK_DEPTH`` folders down and ``WALK_SECONDS``, says when it stopped early
(``truncated``), skips hidden and build folders and the folders of the projects inside it, and never
walks a folder twice (a link back into one is how a walk would never end). A walk is kept for
``WALK_KEPT_SECONDS``, so the Home and every page's Project list asking each second cost one walk.

The home folder, a folder above it and a disk's root are no project (``Refused``): a walk of one would
be the whole disk's, and its documents every document there is.

Paths go out with ``/`` separators on every platform.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from typing import Any, Callable

from cad.engine.ids import canonical, derived_id, is_id

from .backend import absolute_path
from .content_types import extension_of
from .natural_sort import collation_key
from .scanner import VIEWER_EXTENSIONS, VIEWER_SKIPPED_DIRECTORIES, is_hidden_name, to_posix_path

PROJECTS = "projects"
SCHEMA = 1
# The most files a project lists, how deep its walk goes, and for how long it walks.
WALK_LIMIT = 1000
WALK_DEPTH = 24
WALK_SECONDS = 1.5
# How long a walk answers again before the folder is walked anew.
WALK_KEPT_SECONDS = 2.0


class Refused(ValueError):
    """A folder that is no project, with what to open instead (``hint``)."""

    def __init__(self, words: str, hint: str) -> None:
        super().__init__(words)
        self.hint = hint


def _key(path: str) -> str:
    """``path`` as two paths are compared: the platform's case rule, ``/`` separators."""
    return os.path.normcase(path).replace("\\", "/").rstrip("/") or "/"


def inside(path: str, root: str) -> bool:
    """Whether ``path`` is ``root`` or under it."""
    path, root = _key(path), _key(root)
    return path == root or path.startswith(root if root.endswith("/") else root + "/")


def _record(raw: bytes | None, ident: str) -> dict[str, Any] | None:
    """A project's record as its file holds it, or None for one this schema does not read."""
    try:
        record = json.loads(raw) if raw is not None else None
    except ValueError:
        return None
    if not isinstance(record, dict) or record.get("schema") != SCHEMA or record.get("id") != ident:
        return None
    root = record.get("root")
    if not isinstance(root, str) or not os.path.isabs(root):
        return None
    return record


def public(record: dict[str, Any]) -> dict[str, Any]:
    """A project as every route says it: its ``id``, its ``name`` (its folder's), its ``root``, when it was
    first and last opened as one, and whether its folder is gone (``missing``)."""
    root = record["root"]
    return {"id": record["id"], "name": os.path.basename(root.rstrip("/\\")) or root, "root": to_posix_path(root),
            "created": record.get("created"), "opened": record.get("opened"), "missing": not os.path.isdir(root)}


class Projects:
    """The projects of the state folder ``state`` (``registry.Folder``)."""

    def __init__(self, state) -> None:
        self.state = state
        self._lock = threading.Lock()
        self._walks: dict[tuple[str, tuple[str, ...]], tuple[float, list[str], bool]] = {}

    # -- records ---------------------------------------------------------------

    def get(self, ident: str) -> dict[str, Any] | None:
        if not is_id(ident):
            return None
        return _record(self.state.read(f"{PROJECTS}/{ident}.json"), ident)

    def list(self) -> list[dict[str, Any]]:
        """Every project's record, in no order."""
        names = (name[:-5] for name in self.state.names(PROJECTS) if name.endswith(".json"))
        return [record for record in (self.get(name) for name in names) if record is not None]

    def _put(self, record: dict[str, Any]) -> None:
        text = json.dumps({**record, "schema": SCHEMA}, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
        self.state.write(f"{PROJECTS}/{record['id']}.json", text.encode("utf-8"))

    def add(self, path: object) -> tuple[dict[str, Any], bool]:
        """Open the folder ``path`` as a project: its record, and whether it was made now. A folder in a
        project is that project, opened again; a folder that is one already is too. ``ValueError`` for a
        path that is not absolute, ``FileNotFoundError`` for one that is no folder, ``Refused`` for the
        home folder, a folder above it or a disk's root."""
        folder = absolute_path(path)
        if not os.path.isdir(folder):
            raise FileNotFoundError(folder)
        root = canonical(folder)
        home = canonical(os.path.expanduser("~"))
        if os.path.dirname(root) == root:
            raise Refused(f"{to_posix_path(root)} is the root of a disk, not one project's folder",
                          "open the folder of one project, inside your home folder")
        if inside(home, root):
            said = "your home folder" if _key(home) == _key(root) else "a folder that holds your home folder"
            raise Refused(f"{to_posix_path(root)} is {said}, not one project's folder",
                          "open the folder of one project inside it")
        now = time.time()
        with self._lock:
            around = self.of(root)
            if around is not None:
                record = {**around, "opened": now}
                self._put(record)
                return record, False
            record = {"id": derived_id(root), "root": root, "created": now, "opened": now}
            self._put(record)
            return record, True

    def remove(self, ident: str) -> bool:
        """Forget project ``ident``: its record alone. Nothing in its folder changes."""
        if self.get(ident) is None:
            return False
        self.state.remove(f"{PROJECTS}/{ident}.json")
        return True

    # -- membership --------------------------------------------------------------

    def of(self, path: str | None, records: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        """The project ``path`` (a file, a script, a folder) is in: the nearest above it, or None."""
        if not path:
            return None
        found = None
        for record in self.list() if records is None else records:
            if inside(path, record["root"]) and (found is None or len(_key(record["root"])) > len(_key(found["root"]))):
                found = record
        return found

    # -- documents ---------------------------------------------------------------

    def documents(self, record: dict[str, Any], entries, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """The project ``record`` as the routes answer it (``public``), with its ``documents``: its models
        (``entries``, Recents' ``Recent``s, whose script or home is in it and in no project inside it),
        by name, then its CAD files, by folder then name (each Recents' entry where it has one), as
        Recents' rows with their ``project``; ``truncated`` where the walk stopped early."""
        from .recents import Recent

        records = self.list() if records is None else records
        ident = record["id"]

        def mine(path: str | None) -> bool:
            found = self.of(path, records) if path else None
            return found is not None and found["id"] == ident

        models, recorded = [], {}
        for entry in entries:
            if entry.kind == "file":
                recorded[_key(entry.path)] = entry
            elif mine(entry.script):
                models.append(entry)
        models.sort(key=lambda entry: collation_key(entry.name or ""))
        nested = tuple(sorted(other["root"] for other in records
                              if other["id"] != ident and inside(other["root"], record["root"])))
        paths, truncated = self._walk(record["root"], nested)
        files = []
        for path in paths:
            entry = recorded.get(_key(path))
            if entry is None:
                updated, size = _on_disk(path)
                entry = Recent(path=path, opened=None, updated=updated, size=size)
            files.append(entry)
        rows = [row for row in (entry.row() for entry in [*models, *files]) if row is not None]
        return {**public(record), "documents": [{**row, "project": ident} for row in rows], "truncated": truncated}

    def _walk(self, root: str, nested: tuple[str, ...]) -> tuple[list[str], bool]:
        """The CAD files under ``root``, but those under ``nested`` (the projects inside it), by folder
        then name; and whether the walk stopped early. Kept ``WALK_KEPT_SECONDS``."""
        key = (_key(root), nested)
        now = time.monotonic()
        with self._lock:
            kept = self._walks.get(key)
            if kept is not None and now - kept[0] < WALK_KEPT_SECONDS:
                return list(kept[1]), kept[2]
        found, truncated = walk(root, skip=nested)
        with self._lock:
            # Old walks go: the folders asked for change, and so do the projects in them.
            self._walks = {held: value for held, value in self._walks.items() if now - value[0] < WALK_KEPT_SECONDS}
            self._walks[key] = (now, found, truncated)
        return list(found), truncated


def _on_disk(path: str) -> tuple[float | None, int | None]:
    try:
        status = os.stat(path)
    except OSError:
        return None, None
    return status.st_mtime, status.st_size


def walk(root: str, *, skip: tuple[str, ...] = (), limit: int = WALK_LIMIT, depth: int = WALK_DEPTH,
         seconds: float = WALK_SECONDS, clock: Callable[[], float] = time.monotonic) -> tuple[list[str], bool]:
    """The CAD files under the folder ``root`` (the module docstring), ``/``-separated: the folder's own first,
    then each folder's under it by its path below ``root``, each folder's in natural order; and whether it
    stopped early: at ``limit`` files, past ``depth`` or past ``seconds``. ``skip``: folders not walked."""
    deadline = clock() + seconds
    skipped = {_key(path) for path in skip}
    folders: list[tuple[str, list[str]]] = []
    count = 0
    truncated = False
    walked: set[str] = set()
    queue = deque([(root, 0)])
    while queue:
        current, level = queue.popleft()
        if clock() > deadline:
            truncated = True
            break
        try:
            real = os.path.realpath(current)
            if real in walked:
                continue
            walked.add(real)
            names = []
            with os.scandir(current) as found:
                entries = list(found)
        except OSError:  # a folder that cannot be read is passed over, as a person would
            continue
        for entry in sorted(entries, key=lambda item: collation_key(item.name)):
            try:
                if entry.is_dir():
                    child = os.path.join(current, entry.name)
                    if is_hidden_name(entry.name) or entry.name in VIEWER_SKIPPED_DIRECTORIES or _key(child) in skipped:
                        continue
                    if level + 1 <= depth:
                        queue.append((child, level + 1))
                    else:
                        truncated = True
                elif entry.is_file() and not is_hidden_name(entry.name) and extension_of(entry.name) in VIEWER_EXTENSIONS:
                    names.append(entry.name)
            except OSError:  # a broken link or an entry that went away while it was read
                continue
        if not names:
            continue
        room = limit - count
        if len(names) > room:
            names, truncated = names[:room], True
        folders.append((current, names))
        count += len(names)
        if count >= limit:
            truncated = truncated or bool(queue)
            break

    def below(folder: str) -> str:
        return "" if folder == root else _key(os.path.relpath(folder, root))

    folders.sort(key=lambda item: (item[0] != root, collation_key(below(item[0]))))
    return [to_posix_path(os.path.join(folder, name)) for folder, names in folders for name in names], truncated
