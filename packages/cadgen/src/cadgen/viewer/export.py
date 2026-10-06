"""``cadgen viewer export``: a folder's CAD files recorded as a static copy of the viewer API.

The CAD Viewer's client asks its server a fixed set of questions about a file -- its catalog row,
its artifact status, its build feed, a drawing's payload, a STEP's flattened tree and the SURF of
each component, a mesh's or robot's bytes -- and the answers are a pure function of the file and
the store. An export writes those answers down once, so that a server with no cadgen behind it (a
static host, a read-only copy of the API) can answer the same client exactly as this one does.
Nothing is reimplemented: every JSON answer is recorded by dispatching the request to the viewer's
own router (:class:`~cadgen.viewer.http_app.CadApp`) in this process, with no socket, and every
byte the client may fetch is stored by its content hash.

Layout of ``OUT``::

    export.json            schema 1: files, views, routes (below)
    objects/<sha256>       every body the client may fetch, by content hash

Paths are **virtual**: POSIX, relative to ``ROOT``, with a leading slash (``ROOT/STEP/a.step`` is
``/STEP/a.step``). Every absolute path the router answers is rewritten to its virtual path, and a
path outside ``ROOT`` is refused: an export names nothing of the machine it was made on.

``routes`` maps each route to its answers by request key -- the ``file`` query the client sends
(``""`` for a request with none), or for the store's object form the ``object`` it names::

    "/__cad/server":   {"": <json>}
    "/__cad/catalog":  {"": <json>, "/STEP/a.step": <json>}
    "/__cad/artifact": {"/STEP/a.step": <json>}
    "/__cad/preview":  {"/STEP/a.step": <json>}
    "/__cad/drawing":  {"/DXF/plate.dxf": <json>}
    "/__cad/asset":    {"/STEP/a.step": {"object": <sha256>, "type": <content-type>, "bytes": N}}
    "/__cad/store":    {"/<tree>/assembly.json": {...}, "/<tree>/components/<cid>.surf": {...}, "<object>": {...}}

A STEP's descriptor is recorded complete -- every component carries its ``surfaceObject`` and
``surf`` -- so the client reads surfaces as static files and never asks ``POST /__cad/surfaces``.
A document whose bytes have no tree yet is compiled first, as the viewer compiles it: a job in the
build pool, never the kernel in this process.
"""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import io
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import parse_qsl

from .encoding import form_encode
from .response import Request, Response
from .scanner import SOURCE_EXTENSIONS, VIEWER_SKIPPED_DIRECTORIES, is_catalog_file, is_hidden_name, to_posix_path
from .url_norm import Query

__all__ = ["EXPORT_SCHEMA", "ExportError", "export_views", "main", "virtual_path_of"]

EXPORT_SCHEMA = 1
DEFAULT_PROG = "cadgen viewer export"
_ASSET_ROUTE = "/__cad/asset"
# A robot description's link meshes: `<mesh filename="…">` (URDF) and `<uri>…</uri>` (SDF).
_MESH_REFS = (re.compile(r'<mesh\b[^>]*?\bfilename\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE),
              re.compile(r"<uri>\s*([^<]+?)\s*</uri>", re.IGNORECASE))
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


class ExportError(RuntimeError):
    """The export cannot be made as asked: the message says what to change."""


class _CapturedHandler:
    """The slice of ``BaseHTTPRequestHandler`` a viewer ``Response`` writes to, in memory."""

    def __init__(self) -> None:
        self.status = 500
        self.headers: dict[str, str] = {}
        self.wfile = io.BytesIO()
        self.close_connection = False
        self.connection = self

    def send_response_only(self, status: int, message: str | None = None) -> None:  # noqa: ARG002
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        self.headers[name.lower()] = value

    def date_time_string(self) -> str:
        return email.utils.formatdate(usegmt=True)

    def end_headers(self) -> None:
        pass

    def shutdown(self, how: int) -> None:  # noqa: ARG002
        pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _kind_of(path: str) -> str:
    """The CAD kind a file's extension names (``step``, ``dxf``, …), or ``other``."""
    name = os.path.basename(path)
    dot = name.rfind(".")
    extension = name[dot:].lower() if dot > 0 else ""
    return extension[1:] if extension in SOURCE_EXTENSIONS else "other"


class _Root:
    """``ROOT`` and the virtual spelling of every path under it."""

    def __init__(self, root: str) -> None:
        self.path = os.path.abspath(root)
        if not os.path.isdir(self.path):
            raise ExportError(f"{root} is not a folder")
        # Both spellings the router may answer: as given, and resolved (the preview route
        # answers real paths; on macOS /var is /private/var).
        self._prefixes = sorted({to_posix_path(self.path), to_posix_path(os.path.realpath(self.path))}, key=len, reverse=True)

    def virtual(self, path: str) -> str | None:
        """The virtual path of ``path`` (absolute, in either separator), or None when it is not under ROOT."""
        text = to_posix_path(str(path or ""))
        if os.name == "nt":
            text = text.replace("\\", "/")
        for prefix in self._prefixes:
            if text == prefix:
                return "/"
            if text.startswith(prefix + "/"):
                return "/" + text[len(prefix) + 1:]
        return None

    def absolute(self, virtual: str) -> str:
        return os.path.join(self.path, *virtual.lstrip("/").split("/")) if virtual.strip("/") else self.path


def virtual_path_of(root: str, path: str) -> str:
    """The virtual path of ``path`` under ``root``; ``ExportError`` when it is outside."""
    virtual = _Root(root).virtual(os.path.abspath(path))
    if virtual is None:
        raise ExportError(f"{path} is outside {root}: an export names nothing outside its root")
    return virtual


class _Exporter:
    def __init__(self, root: _Root, out: str) -> None:
        from .http_app import create_cad_app

        self.root = root
        self.out = os.path.abspath(out)
        self.objects_dir = os.path.join(self.out, "objects")
        self.app = create_cad_app(host="127.0.0.1", port=0, dist_dir="", start=root.path)
        # Facts of this machine no export carries: it has no file chooser, no analytics, and no
        # code to watch for a restart.
        self.app.pick = False
        self.app.analytics = None
        self.app.auto_reload = False
        # The display producer every STEP's surfaces are derived under: asked of the build pool
        # once (a job that loads the kernel), the first time a document carries no hint of its own.
        self._producer: dict | None = None
        self.routes: dict[str, dict[str, object]] = {
            "/__cad/server": {}, "/__cad/catalog": {}, "/__cad/artifact": {}, "/__cad/preview": {},
            "/__cad/drawing": {}, "/__cad/asset": {}, "/__cad/store": {},
        }
        self.object_bytes: dict[str, int] = {}

    # --- the router, in-process ------------------------------------------------

    def dispatch(self, path: str, params: Sequence[tuple[str, str]] = ()) -> tuple[int, dict[str, str], bytes]:
        request = Request(raw_method="GET", path=path, query=Query(list(params)), headers={}, read_body=lambda: b"")
        handler = _CapturedHandler()
        response = Response(handler)
        self.app.handle(request, response)
        if not response.written:
            raise ExportError(f"the viewer answered nothing for {path}")
        return handler.status, handler.headers, handler.wfile.getvalue()

    def json_answer(self, path: str, params: Sequence[tuple[str, str]] = ()) -> object:
        status, _, body = self.dispatch(path, params)
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError as error:
            raise ExportError(f"{path} answered {status} with no JSON: {body[:200]!r}") from error
        if status != 200:
            detail = payload.get("error") if isinstance(payload, dict) else payload
            raise ExportError(f"{path} answered {status}: {detail}")
        return payload

    # --- objects ------------------------------------------------------------------

    def store_object(self, data: bytes) -> str:
        digest = _sha256(data)
        if digest not in self.object_bytes:
            os.makedirs(self.objects_dir, exist_ok=True)
            target = os.path.join(self.objects_dir, digest)
            if not os.path.isfile(target):
                temporary = f"{target}.{os.getpid()}.tmp"
                with open(temporary, "wb") as handle:
                    handle.write(data)
                os.replace(temporary, target)
            self.object_bytes[digest] = len(data)
        return digest

    def record_object(self, route: str, key: str, data: bytes, content_type: str) -> dict:
        entry = {"object": self.store_object(data), "type": content_type, "bytes": len(data)}
        self.routes[route][key] = entry
        return entry

    # --- path rewriting -------------------------------------------------------------

    def virtual(self, path: str) -> str:
        found = self.root.virtual(path)
        if found is None:
            raise ExportError(f"{path} is outside {self.root.path}: an export names nothing outside its root")
        return found

    def rewrite(self, value):
        """``value`` with every absolute path of this machine spelled virtually: a path under ROOT
        as a whole string, or as the ``file`` of an asset URL. A path outside ROOT is refused."""
        if isinstance(value, dict):
            return {key: self.rewrite(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.rewrite(item) for item in value]
        if not isinstance(value, str):
            return value
        if value.startswith(_ASSET_ROUTE + "?"):
            pairs = parse_qsl(value[len(_ASSET_ROUTE) + 1:], keep_blank_values=True)
            rewritten = [(name, self.virtual(item) if name == "file" else item) for name, item in pairs]
            return f"{_ASSET_ROUTE}?{form_encode(rewritten)}"
        found = self.root.virtual(value)
        return value if found is None else found

    # --- one file -------------------------------------------------------------------

    def record_asset(self, absolute: str) -> dict | None:
        """``GET /__cad/asset`` for ``absolute``, recorded under its virtual path; None when the
        viewer does not serve it (a file that is not a CAD file or sidecar)."""
        status, headers, body = self.dispatch(_ASSET_ROUTE, [("file", absolute)])
        if status != 200:
            return None
        return self.record_object("/__cad/asset", self.virtual(absolute), body, headers.get("content-type", "application/octet-stream"))

    def ensure_compiled(self, absolute: str) -> None:
        """A STEP's tree, current: compiled now where its bytes have none (a job in the build pool)."""
        status = self.app.ops.artifact_status(absolute)
        if status.get("state") == "not-compiled" and status.get("compile"):
            result = self.app.ops.client.compile(absolute)
            if not result.get("ok"):
                raise ExportError(f"{absolute}: {result.get('error') or 'compiling the document failed'}")
            status = self.app.ops.artifact_status(absolute)
        if status.get("state") != "compiled":
            raise ExportError(f"{absolute}: {status.get('error') or status.get('reason') or status.get('state')}")

    def record_step(self, absolute: str, entry: dict) -> None:
        from cadgen.store.objects import read_verified_object
        from cadgen.store.view import descriptor_for_view, materialize_view_surfaces

        tree, document_hash = str(entry.get("hash") or ""), str(entry.get("documentHash") or "")
        if not tree:
            raise ExportError(f"{absolute}: the catalog has no tree for the document")
        descriptor = descriptor_for_view(tree, producer=self._producer, document_hash=document_hash or None)
        if descriptor is None:
            raise ExportError(f"{absolute}: the store has no complete tree {tree}")
        descriptor = materialize_view_surfaces(descriptor)
        self._producer = dict(descriptor["surfaceProducer"])
        # The descriptor as the store route spells it, surfaces included (the module docstring).
        self.record_object("/__cad/store", f"/{tree}/assembly.json", json.dumps(descriptor).encode("utf-8"), "application/json")
        for cid, component in descriptor["components"].items():
            digest = str(component.get("surfaceObject") or "")
            if not digest or not component.get("surf"):
                raise ExportError(f"{absolute}: component {cid} has no surface after derivation")
            found = self.record_object("/__cad/store", f"/{tree}/{component['surf']}", read_verified_object(digest), "application/octet-stream")
            self.routes["/__cad/store"][digest] = found
        self.routes["/__cad/preview"][self.virtual(absolute)] = self.preview(absolute)
        for key in ("sourceUrl", "poseUrl"):
            url = str(entry.get(key) or "")
            if url.startswith(_ASSET_ROUTE + "?"):
                sidecar = dict(parse_qsl(url[len(_ASSET_ROUTE) + 1:], keep_blank_values=True)).get("file", "")
                if sidecar and self.record_asset(sidecar) is None:
                    raise ExportError(f"{absolute}: the viewer does not serve its sidecar {sidecar}")

    def preview(self, absolute: str) -> dict:
        answer = self.rewrite(self.app.build_status(absolute))
        # A static export has no feed to follow: the answer is the file's build as it stands.
        answer.pop("feedCursor", None)
        answer.pop("feedLimited", None)
        return answer

    def record_robot_meshes(self, absolute: str) -> None:
        """The link meshes a description names, relative to it, as the client resolves them."""
        try:
            with open(absolute, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError as error:
            raise ExportError(f"{absolute}: {error}") from error
        folder = os.path.dirname(absolute)
        for pattern in _MESH_REFS:
            for match in pattern.finditer(text):
                reference = next((group for group in match.groups() if group), "").strip()
                if not reference or _SCHEME.match(reference):
                    continue
                candidate = os.path.normpath(os.path.join(folder, reference.replace("\\", "/")) if not reference.startswith("/") else reference)
                if self.root.virtual(candidate) is None or not os.path.isfile(candidate):
                    continue
                self.record_asset(candidate)

    def record_view(self, absolute: str) -> str:
        virtual = self.virtual(absolute)
        kind = _kind_of(absolute)
        if kind in ("step", "stp"):
            self.ensure_compiled(absolute)
        catalog = self.json_answer("/__cad/catalog", [("file", absolute)])
        entries = catalog.get("entries") if isinstance(catalog, dict) else None
        if not entries:
            raise ExportError(f"{absolute}: the viewer has no catalog row for it")
        self.routes["/__cad/catalog"][virtual] = self.rewrite(catalog)
        self.routes["/__cad/artifact"][virtual] = self.rewrite(self.json_answer("/__cad/artifact", [("file", absolute)]))
        if self.record_asset(absolute) is None:
            raise ExportError(f"{absolute}: the viewer does not serve it")
        entry = entries[0]
        if kind in ("step", "stp"):
            self.record_step(absolute, entry)
        elif kind == "dxf":
            self.routes["/__cad/drawing"][virtual] = self.rewrite(self.json_answer("/__cad/drawing", [("file", absolute)]))
        elif kind in ("urdf", "sdf", "srdf"):
            paired = ((entry.get("relations") or {}).get("urdf") or {}).get("file")
            if paired:
                self.record_asset(str(paired))
                self.record_robot_meshes(str(paired))
            self.record_robot_meshes(absolute)
        return virtual

    # --- the export -----------------------------------------------------------------

    def files(self) -> list[dict]:
        found = []
        for dirpath, dirnames, filenames in os.walk(self.root.path):
            dirnames[:] = sorted(
                name for name in dirnames
                if not is_hidden_name(name) and name not in VIEWER_SKIPPED_DIRECTORIES and name != "__pycache__"
                and os.path.abspath(os.path.join(dirpath, name)) != self.out
            )
            for name in sorted(filenames):
                path = os.path.join(dirpath, name)
                if is_hidden_name(name) or not os.path.isfile(path) or os.path.islink(path):
                    continue
                found.append({"path": self.virtual(path), "kind": _kind_of(path), "bytes": os.path.getsize(path), "sha256": _file_sha256(path)})
        return sorted(found, key=lambda item: item["path"])

    def run(self, requested: Sequence[str] | None) -> dict:
        files = self.files()
        if requested is None:
            views = [item["path"] for item in files if item["kind"] != "other" and is_catalog_file(item["path"])]
        else:
            views = []
            for item in requested:
                absolute = os.path.abspath(item if os.path.isabs(item) else os.path.join(self.root.path, item))
                virtual = self.virtual(absolute)
                if not os.path.isfile(absolute):
                    raise ExportError(f"{item}: no such file under {self.root.path}")
                if _kind_of(absolute) == "other" or not is_catalog_file(absolute):
                    raise ExportError(f"{item}: not a CAD file the viewer shows ({', '.join(sorted(SOURCE_EXTENSIONS))})")
                if virtual not in views:
                    views.append(virtual)
        if not views:
            raise ExportError(f"nothing to export: no CAD file under {self.root.path}")
        self.routes["/__cad/server"][""] = self.rewrite(self.json_answer("/__cad/server"))
        self.routes["/__cad/catalog"][""] = self.rewrite(self.json_answer("/__cad/catalog"))
        for virtual in views:
            self.record_view(self.root.absolute(virtual))
        from cadgen import __version__

        index = {"schema": EXPORT_SCHEMA, "cadgen": __version__, "files": files, "views": views, "routes": self.routes}
        os.makedirs(self.out, exist_ok=True)
        temporary = os.path.join(self.out, f"export.json.{os.getpid()}.tmp")
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(index, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporary, os.path.join(self.out, "export.json"))
        return {"ok": True, "out": self.out, "views": views, "objects": len(self.object_bytes), "bytes": sum(self.object_bytes.values())}


def export_views(root: str, out: str, files: Sequence[str] | None = None) -> dict:
    """Export the CAD files under ``root`` (every one, or ``files``: root-relative or absolute
    paths inside it) as ``out/export.json`` and ``out/objects/``. Returns the summary line's
    fields: ``{"ok": True, "out", "views", "objects", "bytes"}``."""
    return _Exporter(_Root(root), out).run(files)


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog, allow_abbrev=False,
        description="Record a folder's CAD files as a static export of the CAD Viewer's API: "
                    "OUT/export.json and OUT/objects/<sha256>, for a server with no cadgen behind it.",
    )
    parser.add_argument("root", metavar="ROOT", help="the folder to export; paths in the export are relative to it")
    parser.add_argument("--out", required=True, metavar="DIR", help="where export.json and objects/ are written")
    parser.add_argument("--file", action="append", default=None, metavar="PATH",
                        help="export this file alone (repeatable): a path under ROOT; default every CAD file under it")
    parser.add_argument("--json", action="store_true", help="print one JSON line: ok, out, views, objects, bytes")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        result = export_views(args.root, args.out, args.file)
    except ExportError as error:
        if args.json:
            sys.stdout.write(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False) + "\n")
        else:
            sys.stderr.write(f"{prog}: {error}\n")
        return 1
    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    else:
        sys.stdout.write(f"Exported {len(result['views'])} file(s) to {result['out']}: {result['objects']} objects, {result['bytes']} bytes\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(prog="python -m cadgen.viewer.export"))
