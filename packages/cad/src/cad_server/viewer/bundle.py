"""A document's view bundle: what its page reads, written down ahead of time (the engine's **View bundle**).

A page shows a document by asking this application for each thing it draws (``kinds.py``). A view bundle
is those answers as files in one folder, so that a page can show the document from any plain file server,
with no engine: ``write`` opens the document as a page does, asks this application, in process, for every
read of its kind, and puts each answer's bytes at the path the layout gives its route. Nothing here makes
an answer: the engine and this application make each as they make it for a page -- kernel work in the
engine's own processes, never in this one -- so a bundled answer is the HTTP answer, byte for byte, but
where the layout says otherwise: a structure names no place and no code of the computer it was made on (a
file's ``path``, a model's ``closure``), and a robot's names its meshes where the bundle holds them. And a
structure holds two things apart, each once: its mechanism, which is ``kinematics.json`` and so is left
out of it, and its prototypes' element names, each prototype's in a file named by its own bytes
(``_names``). A reader puts both back.

What a page asks for on demand, a bundle holds whole: each part's ``elements`` table (every face's,
edge's and vertex's facts and its groups), made once per part. A document's part files are asked at once
(``take_all``): the engine makes each table in a process of its pool, so a first bundle's tables are made
on every core it has.

Every answer is gathered into a folder made beside the bundle's (``atomic_replace.staging``) before the
bundle's own is touched, so an export that fails -- the engine's refusal, a document that keeps changing --
leaves what was there as it was. A new bundle is then that folder, renamed. One written over an earlier
bundle keeps what it can: a part's files are named by its geometry key (and its mesh by the tessellation),
and a prototype's names by their bytes, so they are the same bytes in every bundle that holds them; the
engine is asked only for the parts the folder lacks, only the files whose bytes changed are moved in, the
manifest last, and the files the document no longer names are removed. A folder whose manifest names a
file holds it.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import itertools
import json
import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import quote

from cad.engine.atomic_replace import replace_atomic, same_bytes, staging
from cad.engine.export import ExportRefused
from cad.registry import DOCUMENT_TYPES

from . import url_norm
from .response import Captured, Request, Response

__all__ = ["FORMAT", "MANIFEST", "write"]

#: The layout's name, which a manifest says first: a reader of another number reads none of it.
FORMAT = "view-bundle/1"
MANIFEST = "manifest.json"
# How often a bundle is begun again when its document changes under it (a model built again, a file
# rewritten) before the export fails saying so.
TRIES = 3
# The longest wait between two asks of an answer still being made (a drawing, a file's read), in seconds.
RETRY_SECONDS = 1.0
# How many of a document's part files are asked at once (``take_all``): twice as many as the engine's pool has
# processes (one a core), each making one part's table, so a process that finishes one finds the next in its
# queue (measured on a 245-part model, 4 cores: 10.7 s one at a time, 4.7 s four at a time, 4.1 s eight).
ASKS = 2 * (os.cpu_count() or 2)
# A prototype's element names, which a bundle holds in a file of their own (``_names``).
NAMES = ("faceNames", "edgeNames", "vertexNames")
_JSON = "application/json"
_CHUNK = 1 << 20
# A path of a bundle, as a manifest of ours names one: segments of ``_segment``'s letters, joined by ``/``.
_PATH = re.compile(r"[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_digest(path: Path) -> tuple[str, int] | None:
    """A file's digest and size, or None for one that is not there."""
    found, size = hashlib.sha256(), 0
    try:
        with open(path, "rb") as handle:
            while chunk := handle.read(_CHUNK):
                found.update(chunk)
                size += len(chunk)
    except OSError:
        return None
    return found.hexdigest(), size


def _segment(name: str) -> str:
    """A name (a part's key, a tessellation) as one segment of a bundle path: its ASCII letters, digits,
    ``.``, ``_`` and ``-`` as they are, every other byte ``~`` and its two hex digits (a STEP part's key
    ``step-0a1b-0:1:2`` is ``step-0a1b-0~3A1~3A2``). So a segment is a file name on every system, reads the
    same in a URL as on a disk -- no ``%`` for a file server to decode -- and names one key alone."""
    found = "".join(char if char.isascii() and (char.isalnum() or char in "._-") else
                    "".join(f"~{byte:02X}" for byte in char.encode("utf-8")) for char in str(name))
    if found in ("", ".", ".."):
        raise ExportRefused(f"{name!r} names no file of a view bundle")
    return found


def _previous(folder: Path) -> dict:
    """The manifest of the bundle ``folder`` holds, ``{}`` for a folder that is empty or not there yet.
    Anything else is refused by name before a file is written: a bundle is written over a bundle alone,
    since writing one removes the files its document no longer names."""
    if folder.is_file():
        raise ExportRefused(f"{folder.name} is a file: a view bundle is a folder")
    try:
        text = (folder / MANIFEST).read_text(encoding="utf-8")
    except FileNotFoundError:
        if folder.is_dir() and any(folder.iterdir()):
            raise ExportRefused(f"{folder.name} holds other files and no {MANIFEST}: a view bundle is written "
                                "into a new folder, or over an earlier bundle") from None
        return {}
    except OSError as error:
        raise ExportRefused(f"{folder.name}/{MANIFEST} could not be read ({error})") from None
    try:
        found = json.loads(text)
    except ValueError:
        found = None
    if not isinstance(found, dict) or not isinstance(found.get("files"), dict) or \
            not str(found.get("format") or "").startswith("view-bundle/"):
        raise ExportRefused(f"{folder.name}/{MANIFEST} is no view bundle's manifest: export to a new folder")
    return found


class _Changed(Exception):
    """The document changed while its bundle was read: begun again (``write``)."""


def _named(path: object) -> bool:
    """Whether ``path`` is a path inside a bundle as this module writes one (``_PATH``, no ``.`` or ``..``):
    the only kind a manifest read from disk is believed about, kept or removed by."""
    return isinstance(path, str) and _PATH.fullmatch(path) is not None and not {".", ".."} & set(path.split("/"))


class _Bundle:
    """One writing of a bundle: this application asked, each answer put at its path in the staging folder
    (``stage``), and what the bundle then holds (``files``: each file's ``bytes``, ``sha256`` and content
    ``type``), moved into its folder at the end (``land``)."""

    def __init__(self, app, folder: Path, stage: Path, previous: dict, release: str, roots: list[str]) -> None:
        self.app, self.folder, self.stage, self.release = app, folder, stage, release
        # What an earlier writing by this release left, by path: a content-named file among them is kept.
        made = previous.get("made") if isinstance(previous.get("made"), dict) else {}
        same = previous.get("format") == FORMAT and made.get("release") == release
        self.kept = {path: entry for path, entry in (previous.get("files") or {}).items()
                     if _named(path) and isinstance(entry, dict)} if same else {}
        self.files: dict[str, dict] = {}
        self.staged: list[str] = []
        # The folders of this computer the document comes from: no JSON a bundle holds names one.
        self.roots = [root for root in roots if root and len(Path(root).parts) > 1]

    # --- asking this application ------------------------------------------------------------

    def ask(self, method: str, url: str, body: bytes = b"") -> tuple[int, str, bytes]:
        """One request answered in process, as a page's is over HTTP: its status, content type and body."""
        headers = {"x-cad-viewer": "1"}  # what a request that changes something carries
        if body:
            headers["content-length"] = str(len(body))
        request = Request(raw_method=method, path=url_norm.request_pathname(url), query=url_norm.request_query(url),
                          headers=headers, read_body=lambda: body)
        handler = Captured()
        response = Response(handler)
        try:
            self.app.handle(request, response)
        except Exception as error:  # noqa: BLE001 - the route's own crash is this export's failure, in its words
            raise RuntimeError(f"{url}: {type(error).__name__}: {error}") from error
        if not response.written or handler.close_connection:
            raise RuntimeError(f"{url} was not answered whole")
        return handler.status, handler.headers.get("content-type", ""), handler.wfile.getvalue()

    def get(self, url: str, waiting: str | None = None) -> tuple[str, bytes]:
        """A read's 200: its content type and body. One still being made (202, its ``state`` ``waiting``)
        is asked again as a page asks, after the wait it names. Anything else fails in the answer's words."""
        while True:
            status, kind, body = self.ask("GET", url)
            if status == 200:
                return kind, body
            if status == 202 and waiting:
                try:
                    told = json.loads(body)
                except ValueError:
                    told = {}
                if told.get("state") == waiting:
                    time.sleep(min(max(float(told.get("retryMs") or 0) / 1000.0, 0.0), RETRY_SECONDS))
                    continue
            raise RuntimeError(f"{url.split('?', 1)[0]} answered {status}{_said(body)}")

    # --- putting files ----------------------------------------------------------------------

    def holds(self, path: str) -> bool:
        """Whether the folder holds ``path`` already as an earlier writing by this release left it (its
        manifest's digest is the file's): a content-named file, kept and asked of no one."""
        entry = self.kept.get(path)
        if entry is None or _file_digest(self.folder / path) != (entry.get("sha256"), entry.get("bytes")):
            return False
        self.files[path] = {"bytes": entry["bytes"], "sha256": entry["sha256"], "type": entry.get("type") or ""}
        return True

    def _staged(self, path: str) -> Path:
        target = self.stage / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if path not in self.staged:
            self.staged.append(path)
        return target

    def put(self, path: str, body: bytes, kind: str) -> None:
        """``body`` as the bundle's ``path``."""
        if kind.startswith(_JSON):
            self._portable(path, body)
        self._staged(path).write_bytes(body)
        self.files[path] = {"bytes": len(body), "sha256": _digest(body), "type": kind}

    def copy(self, path: str, source: str, kind: str) -> None:
        """The file ``source`` as the bundle's ``path``, never held whole in memory."""
        target = self._staged(path)
        try:
            shutil.copyfile(source, target)
        except FileNotFoundError:
            raise ExportRefused(f"no file {source}") from None
        digest, size = _file_digest(target) or ("", 0)
        self.files[path] = {"bytes": size, "sha256": digest, "type": kind}

    def take(self, path: str, url: str, *, immutable: bool = False, waiting: str | None = None) -> None:
        """The answer of ``url`` at ``path``; one named by its content (``immutable``) and held already
        is not asked for."""
        if immutable and self.holds(path):
            return
        kind, body = self.get(url, waiting)
        self.put(path, body, kind)

    def take_all(self, asks: list[tuple[str, str]]) -> None:
        """The answers of ``asks``, each a ``(path, url)`` named by its content (``take``'s ``immutable``): those
        held already kept, the rest asked ``ASKS`` at a time, each put at its path as it comes in. The engine
        makes each part's table in a process of its pool: asked one after another, a document's tables are
        made on one core; asked at once, on as many as the pool has."""
        waiting = iter([(path, url) for path, url in asks if not self.holds(path)])
        with concurrent.futures.ThreadPoolExecutor(ASKS, thread_name_prefix="cad-bundle") as pool:
            asked: dict[concurrent.futures.Future, str] = {}
            while True:
                for path, url in itertools.islice(waiting, ASKS - len(asked)):
                    asked[pool.submit(self.get, url)] = path
                if not asked:
                    return
                done, _running = concurrent.futures.wait(asked, return_when=concurrent.futures.FIRST_COMPLETED)
                for answer in done:
                    # A refusal fails the writing, once the asks under way are answered: nothing more is asked.
                    kind, body = answer.result()
                    self.put(asked.pop(answer), body, kind)

    def _portable(self, path: str, body: bytes) -> None:
        """Fail, by name, a JSON file that names a folder of this computer the document comes from: a
        bundle holds no path of the machine it was made on, and nothing of one that would is written.
        What this application adds of the computer is taken out before this (``_engine_document``,
        ``_robot``), so what is left is the document's own words or a mistake of cad's."""
        for root in self.roots:
            # As a path is written: the folder, then a separator or the end of its string.
            for spelled in {root + end for end in ("/", "\\", '"')} | {json.dumps(root)[1:-1] + "\\"}:
                if spelled.encode("utf-8") in body:
                    raise RuntimeError(
                        f"the view bundle's {path} would name a folder of this computer ({root}), which a bundle "
                        "never holds: nothing was written. Where the document's own text names it (a label, a "
                        "note), change that; otherwise this is a bug in cad")

    # --- the manifest -----------------------------------------------------------------------

    def land(self, document: dict, previous: dict) -> dict:
        """The bundle put in its folder, and what was done: ``{"document", "files", "bytes", "written",
        "removed"}`` (``files`` and ``bytes`` count the manifest too). A new bundle is the staging folder
        renamed, whole. Over an earlier one, each file whose bytes differ is moved in, the manifest last,
        then the files the earlier manifest named and this one does not are removed."""
        files = {path: self.files[path] for path in sorted(self.files)}
        manifest = {"format": FORMAT, "document": document, "made": {"tool": "cad", "release": self.release},
                    "files": files}
        body = (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        self._portable(MANIFEST, body)
        (self.stage / MANIFEST).write_bytes(body)
        done = {"document": document, "files": len(files) + 1,  # and the manifest
                "bytes": len(body) + sum(entry["bytes"] for entry in files.values())}
        if not previous:
            try:
                self.folder.rmdir()  # an empty folder there, which a rename is refused by on Windows
            except OSError:
                pass
            replace_atomic(self.stage, self.folder)
            return {**done, "written": [*self.staged, MANIFEST], "removed": []}
        written = []
        for path in [*self.staged, MANIFEST]:
            target = self.folder / path
            if same_bytes(target, self.stage / path):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            replace_atomic(self.stage / path, target)
            written.append(path)
        removed = []
        for path in sorted(previous.get("files") or {}):
            # Only a path inside the folder, as a manifest of ours names one: never one a stranger wrote in.
            if path in files or not _named(path):
                continue
            try:
                (self.folder / path).unlink()
            except OSError:
                continue
            removed.append(path)
            for parent in (self.folder / path).parents:
                if parent == self.folder:
                    break
                try:
                    parent.rmdir()
                except OSError:
                    break
        return {**done, "written": written, "removed": removed}


def _said(body: bytes) -> str:
    """An answer's own words for its refusal, in brackets, or nothing."""
    try:
        told = json.loads(body)
    except ValueError:
        return ""
    return f" ({told['error']})" if isinstance(told, dict) and told.get("error") else ""


# --- each kind's reads --------------------------------------------------------------------------
#
# One function per way a type is viewed (``cad.registry``'s ``view``): the page's reads of a document of
# it, each put at its route's path. ``envelope`` is the document as its page reads it first
# (``GET /api/v1/documents/<id>``); each answers the manifest's ``version``.


def _engine_document(bundle: _Bundle, envelope: dict) -> str:
    """A model's, an ``.xbf``'s or a STEP's: its structure once every part is meshed (so it names each
    part's unmeshed faces), every part's buffer and table (asked at once: ``take_all``), its parts' facts as
    wholes, its mechanism, its prototypes' element names, and the look it is drawn in."""
    api = envelope["api"]
    status, _kind, body = bundle.ask("POST", f"{api}/mesh")
    if status != 200:
        raise RuntimeError(f"{api}/mesh answered {status}{_said(body)}")
    kind, first = bundle.get(f"{api}/structure")
    structure = json.loads(first)
    tessellation = str(structure["tessellation"])
    parts = []
    for key in dict.fromkeys(str(prototype["key"]) for prototype in structure["prototypes"]):
        part, folder = f"{api}/parts/{quote(key, safe='')}", f"parts/{_segment(key)}"
        parts += [(f"{folder}/{_segment(tessellation)}.xbm", f"{part}?tessellation={quote(tessellation, safe='')}"),
                  (f"{folder}/elements.json", f"{part}/elements")]
    bundle.take_all(parts)
    bundle.take("measure.json", f"{api}/measure")
    mechanism = None
    if "kinematics" in structure:
        sent, mechanism = bundle.get(f"{api}/kinematics")
        bundle.put("kinematics.json", mechanism, sent)
    bundle.take("look.json", "/api/v1/look")
    bundle.take("look/environment.hdr", "/api/v1/look/environment")
    if bundle.get(f"{api}/structure")[1] != first:
        raise _Changed()
    # The two things a structure says of the computer it was answered on, which a bundle never holds: where
    # a file is (in a bundle, the file's name alone; a model's ``path`` is its id, as a live worker answers it,
    # whether a worker holds it or its ``.xbf`` is read), and a model's build closure, which names the code that
    # built it -- its script and modules by path, their names, its inputs.
    structure["path"] = envelope["id"] if envelope["kind"] == "model" else envelope["name"]
    structure.pop("closure", None)
    # The mechanism is held once: ``kinematics.json`` is the structure's own, which a reader puts back.
    if mechanism is not None and json.loads(mechanism) != structure.pop("kinematics"):
        raise RuntimeError(f"{api}/kinematics is not its structure's kinematics: this is a bug in cad")
    _names(bundle, structure, kind)
    bundle.put("structure.json", json.dumps(structure, separators=(",", ":")).encode(), kind)
    return str(structure["version"])


def _names(bundle: _Bundle, structure: dict, kind: str) -> None:
    """Each prototype's element names (``NAMES``, whichever it has) moved out of ``structure`` into a file of
    their own, ``names/<sha256>.json``: compact JSON of an object holding them, every key sorted, named by the
    SHA-256 of its own bytes, which the prototype names in their place (``"names"``). Prototypes that share a
    part's key can name its elements apart, so a names file is named by what it holds, never by the key, and
    prototypes named alike share one. One the folder holds already is kept (``holds``)."""
    for at, prototype in enumerate(structure["prototypes"]):
        names = {member: prototype[member] for member in NAMES if member in prototype}
        if not names:
            continue
        body = json.dumps(names, separators=(",", ":"), sort_keys=True).encode()
        path = f"names/{_digest(body)}.json"
        if path not in bundle.files and not bundle.holds(path):
            bundle.put(path, body, kind)
        placed: dict = {}
        for member, value in prototype.items():
            if member in NAMES:
                placed.setdefault("names", path)
            else:
                placed[member] = value
        structure["prototypes"][at] = placed


def _mesh_file(bundle: _Bundle, envelope: dict) -> str:
    """An STL's, a GLB's or a 3MF's: the file itself, which its page parses."""
    entry = DOCUMENT_TYPES["threemf" if envelope["kind"] == "3mf" else envelope["kind"]]
    bundle.copy(f"source{entry.suffix}", envelope["source"]["path"], entry.mime)
    return str(envelope["version"])


def _drawing(bundle: _Bundle, envelope: dict) -> str:
    """A DXF's: its drawing, flattened to what its page paints."""
    bundle.take("drawing.json", f"{envelope['api']}/drawing", waiting="drawing")
    return str(envelope["version"])


def _robot(bundle: _Bundle, envelope: dict) -> str:
    """A URDF's or an SRDF's: the robot resolved for its page, and every mesh it draws -- a primitive cad
    meshed (``parts/<digest>``) and a link's mesh file (which a page reads by its path on this computer),
    each named in the bundle by its content. The structure is the answer but for where each mesh is: a
    visual's ``url`` is its mesh's path in the bundle, and the ``path`` a link's facts give a mesh file
    (where it is on this computer) is the file's name alone."""
    api = envelope["api"]
    kind, body = bundle.get(f"{api}/structure")
    structure = json.loads(body)
    placed: dict[str, str] = {}
    for visual in structure.get("visuals") or []:
        mesh = visual.get("mesh") or {}
        url = str(mesh.get("url") or "")
        if url not in placed:
            if url.startswith(f"{api}/parts/"):
                placed[url] = f"parts/{_segment(url.rsplit('/', 1)[1])}.glb"
                bundle.take(placed[url], url, immutable=True)
            elif url.startswith("/api/v1/local/files?"):
                sent, data = bundle.get(url)
                placed[url] = f"meshes/{_digest(data)}.{_segment(str(mesh.get('format') or 'bin'))}"
                bundle.put(placed[url], data, sent)
            else:
                raise RuntimeError(f"{envelope['name']}: the visual {visual.get('id')} names its mesh by {url!r}, "
                                   "which is no read of the engine's: this is a bug in cad")
        mesh["url"] = placed[url]
    for link in structure.get("links") or []:
        for fact in [*(link.get("visuals") or []), *(link.get("collisions") or [])]:
            if isinstance(fact.get("path"), str):
                fact["path"] = os.path.basename(fact["path"])
    bundle.put("structure.json", json.dumps(structure, separators=(",", ":")).encode(), kind)
    return str(envelope["version"])


_READS = {"document": _engine_document, "mesh": _mesh_file, "drawing": _drawing, "robot": _robot}
_VIEWS = {entry.wire: entry.view for entry in DOCUMENT_TYPES.values()}


def _open(bundle: _Bundle, source: dict) -> dict:
    """The document a page opens (``POST /api/v1/documents``: a file by its path, a held model by its
    id), asked again while the engine reads it: its envelope."""
    opening = json.dumps({"id": source["id"]} if "id" in source else {"path": source["path"]}).encode()
    while True:
        status, _kind, body = bundle.ask("POST", "/api/v1/documents", opening)
        if status != 202:
            break
        time.sleep(min(max(float(json.loads(body).get("retryMs") or 0) / 1000.0, 0.0), RETRY_SECONDS))
    if status != 201:
        raise ExportRefused(f"no view bundle of {source.get('id') or Path(source['path']).name}: "
                            f"{json.loads(body).get('error') or status}")
    return json.loads(bundle.get(f"/api/v1/documents/{json.loads(body)['id']}")[1])


def write(app, source: dict, folder, *, release: str) -> dict:
    """Write the view bundle of ``source`` -- ``{"id"}``, a document the engine holds, or ``{"path"}``, a
    CAD file's absolute path -- into ``folder`` through ``app`` (the engine's page's application), by this
    ``release`` of cad. Returns what was done: ``{"path", "document", "files", "bytes", "written",
    "removed"}`` (``written``: the paths whose bytes this writing put, the manifest among them;
    ``removed``: the ones an earlier bundle there held and this document does not name).

    ``ExportRefused`` for a folder that holds something other than a bundle, a source the engine does not
    hold or read, and a type no bundle is made of yet. A document that keeps changing while it is read
    fails, saying so. Whatever fails, the folder is left as it was: its files are moved in only once every
    answer is in hand."""
    folder = Path(folder)
    previous = _previous(folder)
    roots = [os.path.dirname(source["path"])] if "path" in source else []
    opener = _Bundle(app, folder, folder, {}, release, roots)
    envelope = _open(opener, source)
    view = _VIEWS.get(envelope["kind"])
    if view not in _READS:
        raise ExportRefused(f"no view bundle is made of a {envelope['kind']} yet: one is made of "
                            f"{', '.join(kind for kind, viewed in _VIEWS.items() if viewed in _READS)}")
    located = (envelope.get("source") or {}).get("path")
    if isinstance(located, str) and located:
        roots.append(os.path.dirname(located))  # a model's script's folder, a file's own
    folder.parent.mkdir(parents=True, exist_ok=True)
    for _attempt in range(TRIES):
        with staging(folder) as stage:
            stage.mkdir()
            bundle = _Bundle(app, folder, stage, previous, release, roots)
            try:
                version = _READS[view](bundle, envelope)
            except _Changed:
                envelope = _open(opener, source)
                continue
            again = _open(opener, source)
            if view != "document" and again["version"] != envelope["version"]:
                envelope = again
                continue
            # The picture the page kept of it, where it kept one.
            status, kind, body = bundle.ask("GET", f"/api/v1/documents/{envelope['id']}/thumbnail")
            if status == 200:
                bundle.put("thumbnail.png", body, kind)
            document = {"id": envelope["id"], "kind": envelope["kind"], "name": envelope["name"], "version": version}
            return {"path": str(folder), **bundle.land(document, previous)}
    raise RuntimeError(f"{envelope['name']} changed each of the {TRIES} times its view bundle was read: "
                       "export it again once it is built")
