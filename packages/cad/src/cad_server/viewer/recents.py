"""Recents: the library's files that are there now, as every CAD view's home lists them.

Every CAD view reads the one list (``GET /api/v1/documents``, which the MCP app's views reach through its
tunnel): each file the library knows (``cad_server.engine.library``: a CAD file a page opened or a person
pinned, a model's ``.xbf`` a run wrote) whose file is there, pinned first, then by its last activity, at most
``LIMIT``. A file that is gone is not listed, and is listed again when it is back.

A row is one file's (``row``): where it is and its name, its times -- ``opened`` and ``created`` the library's,
``updated`` and ``size`` the file's own, from one ``stat`` --, whether it is pinned, and what the cache's note
says of the file as it is now (``parts``, its picture). A model is its ``.xbf``, one file, one row. Nothing is
read to list one: not a model's script, not a file's bytes.
"""

from __future__ import annotations

import os
import stat
from typing import Any

from cad_server.engine.library import reaching
from cad_server.engine.state import stamp

# The most rows Recents lists.
LIMIT = 200
MAX_THUMBNAIL_BYTES = 512 * 1024


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


def row(ident: str, path: str, entry: dict[str, Any], note: dict[str, Any], found: os.stat_result,
        project: str | None) -> dict[str, Any]:
    """The file of id ``ident`` as every list carries it -- ``GET /api/v1/documents``'s rows, a project's
    folder's and a CAD app home's launch alike: at ``path`` (as the list reached it), with its library
    ``entry`` (``{}``: none), the cache's ``note`` of the file as it is now (``{}``: none), its ``stat`` and
    the id of the project it is in."""
    from .kinds import document_api, file_kind

    kind = file_kind(path)
    folder = os.path.dirname(path)
    pictured = note.get("pictured")
    return {"id": ident, "kind": kind, "record": "file", "api": document_api(kind, ident),
            "path": path, "name": os.path.basename(path), "folder": folder, "namespace": folder,
            "opened": entry.get("opened"), "updated": found.st_mtime, "created": entry.get("created"),
            "pinned": bool(entry.get("pinned")), "missing": False,
            # A token that changes with the picture: what a page's picture address carries.
            "thumbnail": str(round(pictured * 1000)) if pictured else None, "pictured": pictured,
            "size": found.st_size, "parts": note.get("parts"), "project": project}


def present(path: str) -> os.stat_result | None:
    """The ``stat`` of the CAD file at ``path``, of a type every view opens; None for none there."""
    from .scanner import VIEWER_EXTENSIONS, extension_of

    if extension_of(path) not in VIEWER_EXTENSIONS:
        return None
    try:
        found = os.stat(path)
    except OSError:
        return None
    return found if stat.S_ISREG(found.st_mode) else None


def listing(library, notes, projects) -> list[dict[str, Any]]:
    """Recents (the module): each row with the project its file is in (``projects.Projects.holding``: by the
    path a page reached it by, else by where it is)."""
    records = projects.list()
    rows = []
    for ident, entry in library.read()["files"].items():
        path = entry["path"]
        found = present(path)
        if found is None:
            continue
        project = projects.holding(reaching(entry.get("reached"), path), path, records)
        rows.append(row(ident, path, entry, notes.read(ident, stamp(found)), found, project["id"] if project else None))
    rows.sort(key=lambda each: (not each["pinned"], -max(each["opened"] or 0, each["updated"])))
    return rows[:LIMIT]
