"""Projects: folders a person opened as one, each shown a folder at a time.

A folder becomes a project only when someone opens it as one: ``cad viewer <folder>``, or Import,
Folder on the viewer's Home (``POST /api/v1/projects``), which a standalone document's menu offers
too, starting at its folder. Nothing else makes one: a run never does, no file in the folder marks
one, and nothing is written to the folder. A project is one entry of the library
(``cad_server.engine.library``: ``root`` the folder's canonical path, its id derived from it,
``ids.derived_id``, when it was first and last opened as one). Remove forgets that entry alone: the
folder and everything in it stay as they are, and its documents are standalone again.

A document belongs to the nearest project above it (``Projects.of``). A file is in the project it is
reached in: one in a linked folder inside a project's is that project's, as one stored there is
(``Projects.holding``: the path a listing or a page reached it by, before its canonical path). So a
folder opened inside a project is that project (``Projects.add`` answers it and makes no entry: projects
do not nest by accident), and a project opened around another leaves the inner one its own.

A project's page is one folder of it (``Projects.folder``): the CAD files directly in it, each the
library's row where it has an entry, and the subfolders that hold a CAD file somewhere below
(``has_cad_below``, which stops at the first one it meets), never a hidden or a build folder. The folder is
the disk's: a file another program drops in is listed, one deleted is gone, and no file is read to list
it. A search (``Projects.search``) is the one place the levels are flattened: the CAD files anywhere below the
folder whose path holds every word, found by a walk that no folder can hold up -- it stops at
``WALK_LIMIT`` files, ``WALK_DEPTH`` folders down and ``WALK_SECONDS``, skips hidden and build folders, and
never walks a folder twice (a link back into one is how a walk would never end). Either says when it
stopped early (``truncated``), and is kept for ``WALK_KEPT_SECONDS`` after it ends -- longer than any page
waits between two reads -- and read by one reader at a time, so the Home and every page asking again and
again cost one read.

An id names a file with no record of it (``locate``): the files the engine was named since it started, then
the library's, then the project folders', walked.

The home folder, a folder above it and a disk's root are no project (``Refused``): a walk of one would
be the whole disk's.

Paths go out with ``/`` separators on every platform.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Callable

from cad.engine.ids import canonical, derived_id, file_id
from cad_server.engine.state import stamp

from .backend import absolute_path
from .content_types import extension_of
from .folders import LIST_LIMIT, _entries
from .natural_sort import collation_key
from .recents import present, row
from .scanner import VIEWER_EXTENSIONS, VIEWER_SKIPPED_DIRECTORIES, is_hidden_name, to_posix_path

# The most files a walk lists, how deep it goes, and for how long it walks.
WALK_LIMIT = 1000
WALK_DEPTH = 24
WALK_SECONDS = 1.5
# How long a folder's read answers again, from when it ended, before the folder is read anew: longer than a page
# waits between two reads (the home's two seconds, a document's three), so that readers share one.
WALK_KEPT_SECONDS = 4.0
# How many of a folder's entries are read between two looks at the clock.
WALK_CLOCK_ENTRIES = 512


class Refused(ValueError):
    """A folder that is no project, with what to open instead (``hint``)."""

    def __init__(self, words: str, hint: str) -> None:
        super().__init__(words)
        self.hint = hint


class NoFolder(LookupError):
    """A path that names no folder below a project's root."""


def _key(path: str) -> str:
    """``path`` as two paths are compared: the platform's case rule, ``/`` separators."""
    return os.path.normcase(path).replace("\\", "/").rstrip("/") or "/"


def inside(path: str, root: str) -> bool:
    """Whether ``path`` is ``root`` or under it."""
    path, root = _key(path), _key(root)
    return path == root or path.startswith(root if root.endswith("/") else root + "/")


def public(record: dict[str, Any]) -> dict[str, Any]:
    """A project as every route says it: its ``id``, its ``name`` (its folder's), its ``root``, when it was
    first and last opened as one, and whether its folder is gone (``missing``)."""
    root = record["root"]
    return {"id": record["id"], "name": os.path.basename(root.rstrip("/\\")) or root, "root": to_posix_path(root),
            "created": record.get("created"), "opened": record.get("opened"), "missing": not os.path.isdir(root)}


def project_root(path: object) -> str:
    """The canonical folder a project of the folder ``path`` is kept by. ``ValueError`` for a path that is not
    absolute, ``FileNotFoundError`` for one that is no folder, ``Refused`` for the home folder, a folder above
    it or a disk's root."""
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
    return root


def below(path: object) -> list[str]:
    """The names of the folder ``path`` names below a project's root (``/``-separated; none: the root itself).
    ``ValueError`` for an absolute path, or one with an empty, ``.`` or ``..`` part."""
    if path is None or path == "":
        return []
    parts = path.split("/") if isinstance(path, str) else [""]
    if any(part in ("", ".", "..") or os.path.basename(part) != part or os.path.splitdrive(part)[0] for part in parts):
        raise ValueError("path is a folder below the project's root: names joined by /, none of them empty, . or ..")
    return parts


class Projects:
    """The projects of ``library`` (``cad_server.engine.library.Library``), and the reads of their folders."""

    def __init__(self, library) -> None:
        self.library = library
        self._lock = threading.Lock()
        # Each folder read (a listing's scan, a search's walk), by what was read and where: when, and its answer.
        self._kept: dict[tuple[str, str], tuple[float, Any]] = {}
        # One lock a folder read: readers that arrive while it is read take that read's answer.
        self._reading: dict[tuple[str, str], threading.Lock] = {}

    # -- the library's entries ----------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """Every project, ``{id, root, created, opened}``, in no order."""
        return [{"id": ident, **entry} for ident, entry in self.library.read()["projects"].items()]

    def get(self, ident: str) -> dict[str, Any] | None:
        entry = self.library.read()["projects"].get(ident)
        return {"id": ident, **entry} if entry is not None else None

    def add(self, path: object) -> tuple[dict[str, Any], bool]:
        """Open the folder ``path`` as a project: it, and whether it was made now. A folder in a
        project is that project, opened again; a folder that is one already is too. It raises as
        ``project_root`` does for a folder that is no project."""
        root = project_root(path)
        now = self.library.clock()
        found: list[Any] = []

        def change(data: dict[str, Any]) -> None:
            around = self.of(root, [{"id": ident, **entry} for ident, entry in data["projects"].items()])
            ident = around["id"] if around is not None else derived_id(root)
            entry = data["projects"].setdefault(ident, {"root": root, "created": now})
            entry["opened"] = now
            found[:] = [{"id": ident, **entry}, around is None]

        self.library.change(change)
        return found[0], found[1]

    def remove(self, ident: str) -> bool:
        """Forget project ``ident``: its entry alone. Nothing in its folder changes."""
        if self.get(ident) is None:
            return False
        self.library.change(lambda data: data["projects"].pop(ident, None))
        return True

    # -- membership --------------------------------------------------------------

    def of(self, path: str | None, records: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        """The project ``path`` (a file, a folder) is in: the nearest above it, or None. ``path`` is
        compared as it is spelled, against each project's canonical folder: a caller holding a path a person
        typed makes it canonical first (``ids.canonical``)."""
        if not path:
            return None
        found = None
        for record in self.list() if records is None else records:
            if inside(path, record["root"]) and (found is None or len(_key(record["root"])) > len(_key(found["root"]))):
                found = record
        return found

    def holding(self, reached: str | None, path: str | None, records: list[dict[str, Any]] | None = None
                ) -> dict[str, Any] | None:
        """The project a file is in: the one the path it was reached by is in (``reached``, as spelled: a file in a
        linked folder inside a project's folder is that project's), else the one its canonical ``path`` is in."""
        return (self.of(reached, records) if reached else None) or self.of(path, records)

    # -- a project's page ----------------------------------------------------------

    def folder(self, record: dict[str, Any], path: object, notes) -> dict[str, Any]:
        """One folder of the project ``record`` as its page shows it (the module): ``{project, path, folders,
        documents, truncated}``, the folder ``path`` names below its root (``below``). ``NoFolder`` where its
        root is there and that is no folder in it."""
        answer, folder = self._place(record, path)
        if folder is not None:
            level = answer["path"].count("/") + 1 if answer["path"] else 0
            folders, files, answer["truncated"] = self._read("scan", folder, lambda: scan(folder, level))
            answer["folders"] = [{"name": name, "path": f"{answer['path']}/{name}".lstrip("/")} for name in folders]
            answer["documents"] = self._rows(record["id"], ((os.path.join(folder, name), ident) for name, ident in files),
                                             notes)
        return answer

    def search(self, record: dict[str, Any], path: object, words: str, notes) -> dict[str, Any]:
        """``folder``'s answer for a search: the CAD files anywhere below that folder whose path below it holds
        every word of ``words``, whatever its case, in the walk's order; no folders."""
        answer, folder = self._place(record, path)
        if folder is not None:
            needles = words.casefold().split()
            paths, answer["truncated"] = self._walk(folder)
            matched = [found for found in paths if all(
                needle in to_posix_path(os.path.relpath(found, folder)).casefold() for needle in needles)]
            answer["documents"] = self._rows(record["id"], ((found, file_id(found)) for found in matched), notes)
        return answer

    @staticmethod
    def _place(record: dict[str, Any], path: object) -> tuple[dict[str, Any], str | None]:
        """An answer of the project ``record`` with nothing listed yet, and the folder ``path`` names in it:
        None where the project's root is gone."""
        parts, found = below(path), public(record)
        answer = {"project": found, "path": "/".join(parts), "folders": [], "documents": [], "truncated": False}
        if found["missing"]:
            return answer, None
        folder = os.path.join(record["root"], *parts)
        if not os.path.isdir(folder):
            raise NoFolder(f"no folder {answer['path']} in {found['name']}")
        return answer, folder

    def _rows(self, project: str, files, notes) -> list[dict[str, Any]]:
        """The row of each of ``files`` (its path as reached, its id) that is there now, this project's."""
        entries = self.library.read()["files"]
        rows = []
        for path, ident in files:
            found = present(path)
            if found is not None:
                rows.append(row(ident, to_posix_path(path), entries.get(ident) or {}, notes.read(ident, stamp(found)),
                                found, project))
        return rows

    def seek(self, ident: str) -> str | None:
        """The file of id ``ident`` in a project's folder, the project opened last looked in first: its path as
        the walk reached it, or None for none a walk lists."""
        for record in sorted(self.list(), key=lambda record: record.get("opened") or 0, reverse=True):
            ids = self._read("ids", record["root"], lambda root=record["root"]: {
                file_id(path): path for path in self._walk(root)[0]})
            if ident in ids:
                return ids[ident]
        return None

    def _walk(self, folder: str) -> tuple[list[str], bool]:
        """``walk`` of ``folder``, kept and shared (``_read``)."""
        return self._read("walk", folder, lambda: walk(folder))

    def _read(self, what: str, folder: str, read: Callable[[], Any]) -> Any:
        """``read()``'s answer for ``folder``: kept ``WALK_KEPT_SECONDS`` from when it ended, and read by one
        reader at a time."""
        key = (what, _key(folder))
        with self._lock:
            reading = self._reading.setdefault(key, threading.Lock())
        with reading:
            with self._lock:
                kept = self._kept.get(key)
            if kept is not None and time.monotonic() - kept[0] < WALK_KEPT_SECONDS:
                return kept[1]
            found = read()
            now = time.monotonic()
            with self._lock:
                # Old reads go: the folders asked for change.
                self._kept = {held: value for held, value in self._kept.items() if now - value[0] < WALK_KEPT_SECONDS}
                self._kept[key] = (now, found)
        return found


def locate(ident: str, server, library, projects: Projects) -> str | None:
    """The path of the file of id ``ident``, with no record of it: the one ``server`` knows it by (every file
    it was named since it started: ``file_of``), else the library's, else the one a project's folder holds
    (``Projects.seek``) -- the first that is a file now, which ``server`` knows from then on (``remember``).
    None: the id names nothing."""
    for look in (lambda: server.file_of(ident), lambda: library.path_of(ident), lambda: projects.seek(ident)):
        path = look()
        if path is not None and os.path.isfile(path):
            return server.file_of(server.remember(path))
    return None


def scan(folder: str, level: int = 0, *, seconds: float = WALK_SECONDS, clock: Callable[[], float] = time.monotonic
         ) -> tuple[list[str], list[tuple[str, str]], bool]:
    """What a project's page lists of ``folder`` (``level`` folders below its root): the names of its subfolders
    that hold a CAD file somewhere below, each CAD file directly in it with its id, both in natural order, and
    whether that is not all of it -- it holds more than ``LIST_LIMIT`` entries, of which the first are listed, or a
    subfolder could not be read to the end within ``seconds`` (all of them share it), which is then listed."""
    deadline = clock() + seconds
    try:
        entries = sorted(_entries(folder), key=lambda item: (item[1] != "directory", collation_key(item[0])))
    except OSError:  # a folder that cannot be read lists nothing
        entries = []
    truncated = len(entries) > LIST_LIMIT
    folders, files = [], []
    for name, kind in entries[:LIST_LIMIT]:
        if kind == "file":
            files.append((name, file_id(os.path.join(folder, name))))
            continue
        found = has_cad_below(os.path.join(folder, name), deadline, level + 1, clock)
        if found is not False:
            folders.append(name)
        truncated = truncated or found is None
    return folders, files, truncated


def has_cad_below(folder: str, deadline: float, level: int = 1, clock: Callable[[], float] = time.monotonic
                  ) -> bool | None:
    """Whether ``folder`` (``level`` folders below a project's root) holds a CAD file somewhere below: True at
    the first one met, depth first, nothing counted or sorted; False once all of it was read and none found. Hidden
    and build folders are never entered, no folder is read twice, and none deeper than ``WALK_DEPTH``. None where
    it cannot say: ``deadline`` (the clock's) passed first, or a folder too deep was left unread."""
    walked: set[str] = set()
    unread = False
    stack = [(folder, level)]
    while stack:
        if clock() > deadline:
            return None
        current, at = stack.pop()
        try:
            real = os.path.realpath(current)
            if real in walked:
                continue
            walked.add(real)
            children = []
            for name, kind in _entries(current):
                if kind == "file":
                    return True
                children.append(name)
        except OSError:  # a folder that cannot be read is passed over, as a person would
            continue
        if at >= WALK_DEPTH:
            unread = unread or bool(children)
        else:
            stack.extend((os.path.join(current, name), at + 1) for name in children)
    return None if unread else False


def walk(root: str, *, limit: int = WALK_LIMIT, depth: int = WALK_DEPTH,
         seconds: float = WALK_SECONDS, clock: Callable[[], float] = time.monotonic) -> tuple[list[str], bool]:
    """The CAD files under the folder ``root`` (the module docstring), ``/``-separated: the folder's own first,
    then each folder's under it by its path below ``root``, each folder's in natural order; and whether it
    stopped early: at ``limit`` files, past ``depth`` or past ``seconds``."""
    deadline = clock() + seconds
    folders: list[tuple[str, list[str]]] = []
    count = 0
    truncated = False
    walked: set[str] = set()
    late = False  # the clock ran out inside a folder
    queue = deque([(root, 0)])
    while queue and not late:
        current, level = queue.popleft()
        if clock() > deadline:
            truncated = True
            break
        names, children = [], []
        try:
            real = os.path.realpath(current)
            if real in walked:
                continue
            walked.add(real)
            with os.scandir(current) as found:
                # Read unsorted, and only what is kept is sorted: a folder of a hundred thousand other files costs
                # its read, never their order. The clock is looked at as it is read, so one such folder ends the walk.
                for read, entry in enumerate(found, 1):
                    if read % WALK_CLOCK_ENTRIES == 0 and clock() > deadline:
                        late = True
                        break
                    try:
                        if entry.is_dir():
                            if not (is_hidden_name(entry.name) or entry.name in VIEWER_SKIPPED_DIRECTORIES):
                                children.append(entry.name)
                        elif entry.is_file() and not is_hidden_name(entry.name) and extension_of(entry.name) in VIEWER_EXTENSIONS:
                            names.append(entry.name)
                    except OSError:  # a broken link or an entry that went away while it was read
                        continue
        except OSError:  # a folder that cannot be read is passed over, as a person would
            continue
        truncated = truncated or late
        if children and level + 1 > depth:
            truncated = True
        elif not late:
            queue.extend((os.path.join(current, name), level + 1) for name in sorted(children, key=collation_key))
        if not names:
            continue
        names.sort(key=collation_key)
        room = limit - count
        if len(names) > room:
            names, truncated = names[:room], True
        folders.append((current, names))
        count += len(names)
        if count >= limit:
            truncated = truncated or bool(queue)
            break

    def under(folder: str) -> tuple:
        """A folder's place among the folders: by its path below ``root``, a name at a time (``a/b`` before ``a b``)."""
        return () if folder == root else tuple(collation_key(part) for part in _key(os.path.relpath(folder, root)).split("/"))

    folders.sort(key=lambda item: under(item[0]))
    return [to_posix_path(os.path.join(folder, name)) for folder, names in folders for name in names], truncated
