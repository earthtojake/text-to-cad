"""Runnable Python CAD Viewer backend (stdlib http.server, zero deps).

Serves the /__cad/* contract the client consumes: GET /__cad/server,
GET /__cad/catalog, GET /__cad/asset, GET /__cad/download, GET /__cad/artifact,
POST /__cad/artifact (build) and POST /__cad/export, plus the static dist/SPA and
legacy Referer assets.

Run: python -m server_py.server [--port N] [--host H]

There is no served root. A page URL's PATH is the absolute directory to open
(`http://host:port/Users/me/models`), exactly as in a file:// URL; the client
reads it from location.pathname and passes it to /__cad/* as ?dir=. The bare
origin names no directory, which the backend reads as the process cwd. The only
paths that are NOT a directory are the bundle's /assets/* and the /__cad/* API.

Security / trust model: binds to loopback (127.0.0.1) and serves UNAUTHENTICATED.
Any local process can read files under --dir (GET /__cad/asset), trigger STEP
builds/exports, and activate directories. This is a single-user, local-filesystem
viewer where loopback binding is the trust boundary. Do NOT bind a non-loopback
--host or expose this server beyond localhost without adding auth.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs, unquote

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from server_py import backend as backend_mod
    from server_py import cadgen_bridge
    from server_py import paths
    from server_py import server_info as server_info_mod
    from server_py import encoding as enc
    from server_py.content_types import content_type_for_static_asset
else:
    from . import backend as backend_mod
    from . import cadgen_bridge
    from . import paths
    from . import server_info as server_info_mod
    from . import encoding as enc
    from .content_types import content_type_for_static_asset

LOCAL_SERVER_FEATURES = ["path-directory"]
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _strict_decode_uri_component(value: str) -> str:
    """Match JS decodeURIComponent: raise on a malformed percent escape."""
    if _BAD_PERCENT_RE.search(value):
        raise ValueError("URI malformed")
    return unquote(value)


def _sibling_file_ref(source_file_ref: str, relative_file_ref: str) -> str:
    source = str(source_file_ref or "").replace("\\", "/")
    relative = re.sub(r"^/+", "", str(relative_file_ref or "").replace("\\", "/"))
    if not source or not relative:
        return ""
    if os.path.isabs(source):
        return os.path.normpath(os.path.join(os.path.dirname(source), relative))
    source_dir = posixpath.dirname(source)
    return posixpath.normpath(posixpath.join("" if source_dir == "." else source_dir, relative))


class _Ctx:
    backend = None
    directory_root = ""
    dist_root = ""
    port = server_info_mod.DEFAULT_VIEWER_PORT
    host = server_info_mod.DEFAULT_VIEWER_HOST


def _server_info(root_dir: str = "") -> dict:
    return server_info_mod.build_viewer_server_info(
        root_dir=root_dir or "",
        port=_Ctx.port,
        host=_Ctx.host,
        backend="local-fs",
        step_artifact_generation_available=True,
        server_mode="serve",
        server_features=LOCAL_SERVER_FEATURES,
    )


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # --- helpers ---
    def _send_json(self, status: int, payload, cache_control: str = "no-store"):
        body = enc.compact_json(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", cache_control or "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_bytes(self, status: int, data: bytes, content_type: str, *, disposition: str | None = None):
        self.send_response(status)
        if content_type:
            self.send_header("content-type", content_type)
        if disposition:
            self.send_header("content-disposition", disposition)
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _query(self):
        parts = urlsplit(self.path)
        q = parse_qs(parts.query)
        return parts.path, {k: (v[0] if v else "") for k, v in q.items()}

    def log_message(self, *args):  # quieter
        pass

    # --- dispatch ---
    def do_GET(self):
        path, q = self._query()
        try:
            if path == "/__cad/server":
                self._send_json(200, _server_info(q.get("dir", "")))
            elif path == "/__cad/catalog":
                catalog = _Ctx.backend.read_catalog(root_dir=q.get("dir", ""), file_ref=q.get("file", ""))
                self._send_json(200, catalog)
            elif path == "/__cad/artifact":
                root_dir = q.get("dir", "")
                catalog = _Ctx.backend.read_catalog(root_dir=root_dir, file_ref=q.get("file", ""))
                resolved = _Ctx.backend.resolve_root(root_dir)
                self._send_json(200, _Ctx.backend.artifact_status(q.get("file", ""), resolved, catalog))
            elif path == "/__cad/asset":
                self._serve_asset(q, download=False)
            elif path == "/__cad/download":
                self._serve_asset(q, download=True)
            elif self._legacy_cad_asset(path, q):
                pass  # served (or 403) by the legacy Referer-based handler
            else:
                self._serve_dist(path)
        except backend_mod.ForbiddenAssetError:
            self._send_json(403, {"error": "Forbidden"})
        except Exception as exc:  # noqa: BLE001
            self._send_json(400, {"error": str(exc)})

    def do_POST(self):
        path, q = self._query()
        try:
            if path == "/__cad/artifact":
                self._artifact_build(q)
            elif path == "/__cad/export":
                self._export(q)
            else:
                self.send_response(405)
                self.send_header("allow", "POST")
                self.send_header("content-length", "0")
                self.end_headers()
        except backend_mod.ForbiddenAssetError:
            self._send_json(403, {"error": "Forbidden"})
        except Exception as exc:  # noqa: BLE001
            self._send_json(400, {"ok": False, "error": str(exc)})

    def do_HEAD(self):
        self.do_GET()

    # --- route bodies ---
    def _serve_static_file(self, file_path: str, content_type: str | None) -> bool:
        """Stream a file with no-store + content-length, NO etag/last-modified/range.
        Returns False (no response written) if the path is missing/not a regular file."""
        if not os.path.isfile(file_path):
            return False
        with open(file_path, "rb") as handle:
            data = handle.read()
        self.send_response(200)
        if content_type:
            self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)
        return True

    def _request_referer_file_ref(self):
        value = self.headers.get("referer") or self.headers.get("referrer") or ""
        if not value:
            return ""
        try:
            ref_url = urlsplit(value if "://" in value else "http://localhost" + value)
            return (parse_qs(ref_url.query).get("file") or [""])[0].strip()
        except ValueError:
            return ""

    def _legacy_cad_asset(self, path: str, q) -> bool:
        # GET /__cad/<rel>.<ext>: a sibling-of-Referer asset request (relative package
        # assets like URDF meshes / ../components). Returns True if it handled the
        # response (served or 403), False to fall through to dist serving.
        if not path.startswith("/__cad/") or path == "/__cad/asset":
            return False
        try:
            relative_path = _strict_decode_uri_component(path[len("/__cad/"):])
        except ValueError:
            return False
        if not relative_path or not os.path.splitext(relative_path)[1]:
            return False
        file_ref = _sibling_file_ref(self._request_referer_file_ref(), relative_path)
        if not file_ref:
            return False
        root_dir = q.get("dir", "")
        try:
            candidate = _Ctx.backend.asset_path_for_file_ref(file_ref, root_dir=root_dir)
        except backend_mod.ForbiddenAssetError:
            self.send_response(403)
            self.send_header("content-length", str(len(b"Forbidden")))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(b"Forbidden")
            return True
        if not candidate:
            return False
        content_type = _Ctx.backend.content_type_for_path(candidate) or None
        return self._serve_static_file(candidate, content_type)

    def _serve_dist(self, path: str):
        # Static dist + SPA fallback (serve mode). dev mode serves the client via Vite.
        #
        # Every path that is not a bundle asset is a DIRECTORY the client will open
        # (the page URL's path is the absolute directory), so it must fall through to
        # index.html. That includes directory paths containing dots — `/Users/j/v0.4/models`
        # is a directory, not a missing file — which is why "has an extension" cannot be
        # the static-asset test here; only the bundle's own /assets/ prefix can be.
        #
        # The join must be given a RELATIVE path: a Windows directory request arrives as
        # `/D:/models`, and os.path.join drops its base when a later component is
        # drive-absolute, so joining that raw escaped dist_root and the containment check
        # below rejected an ordinary directory as traversal (issue #211). Stripping the
        # drive keeps the join inside dist_root, where no such file exists, so the request
        # falls through to index.html like any other directory. Traversal segments survive
        # the strip and are still caught by the check.
        dist_root = _Ctx.dist_root
        request_path = "/index.html" if path == "/" else path
        try:
            decoded = _strict_decode_uri_component(request_path)
        except ValueError:
            self._plain(400, "Bad request")
            return
        file_path = os.path.abspath(os.path.join(dist_root, paths.url_path_as_relative(decoded)))
        if not (file_path == dist_root or file_path.startswith(dist_root + os.sep)):
            self._plain(403, "Forbidden")
            return
        if os.path.isfile(file_path):
            self._serve_static_file(file_path, content_type_for_static_asset(file_path) or None)
            return
        if request_path.startswith("/assets/"):
            self.send_response(404)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(b"Not found")))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(b"Not found")
            return
        index_html = os.path.join(dist_root, "index.html")
        if not self._serve_static_file(index_html, content_type_for_static_asset(index_html) or None):
            self.send_response(404)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(b"Not found")))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(b"Not found")

    def _plain(self, status: int, text: str):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_asset(self, q, *, download: bool):
        if self.command not in ("GET", "HEAD"):
            self.send_response(405)
            self.send_header("allow", "GET")
            self.send_header("content-length", "0")
            self.end_headers()
            return
        file_ref = q.get("file", "")
        root_dir = q.get("dir", "")
        resolved = _Ctx.backend.resolve_root(root_dir) if root_dir else None
        candidate = _Ctx.backend.asset_path_for_file_ref(file_ref, resolved_root=resolved, root_dir=root_dir)
        if not candidate or not os.path.isfile(candidate):
            self._send_json(404, {"error": "Not found"})
            return
        with open(candidate, "rb") as handle:
            data = handle.read()
        content_type = _Ctx.backend.content_type_for_path(candidate) or "application/octet-stream"
        disposition = None
        if download:
            disposition = enc.attachment_content_disposition(os.path.basename(candidate))
        self._send_bytes(200, data, content_type, disposition=disposition)

    def _artifact_build(self, q):
        root_dir = q.get("dir", "")
        catalog = _Ctx.backend.read_catalog(root_dir=root_dir, file_ref=q.get("file", ""))
        resolved = _Ctx.backend.resolve_root(root_dir)
        result = _Ctx.backend.resolve_artifact(q.get("file", ""), q.get("force", "") == "1", resolved, catalog)
        # Refresh the catalog AFTER the build (even on failure) and attach it, matching Node.
        next_catalog = _Ctx.backend.read_catalog(root_dir=root_dir, file_ref=q.get("file", ""))
        status = 500 if result.get("ok") is False else 200
        self._send_json(status, {**result, "catalog": next_catalog})

    def _export(self, q):
        root_dir = q.get("dir", "")
        catalog = _Ctx.backend.read_catalog(root_dir=root_dir, file_ref=q.get("file", ""))
        resolved = _Ctx.backend.resolve_root(root_dir)
        result = _Ctx.backend.generate_export(q.get("file", ""), q.get("format", "step") or "step", resolved, catalog)
        if result.get("cancelled"):
            self._send_json(200, {"ok": False, "cancelled": True})
            return
        if not result.get("ok"):
            self._send_json(400, {"ok": False, "error": result.get("error", "Export failed")})
            return
        payload = {"ok": True, "path": result["path"], "filename": result["filename"], "format": result["format"]}
        if result.get("catalogChanged"):
            payload["catalogChanged"] = True
        if result.get("fallback") and result.get("outputFileRef"):
            payload["fallback"] = True
            payload["downloadUrl"] = (
                f"/__cad/download?dir={enc.encode_uri_component(root_dir)}"
                f"&file={enc.encode_uri_component(result['outputFileRef'])}&asset=output"
            )
        self._send_json(200, payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Python CAD Viewer backend")
    parser.add_argument("--port", type=int, default=server_info_mod.DEFAULT_VIEWER_PORT)
    parser.add_argument("--host", default=server_info_mod.DEFAULT_VIEWER_HOST)
    parser.add_argument("--dist-root", default="", help="built SPA dist directory (serve mode)")
    args = parser.parse_args(argv)

    # No served root: the request's URL path IS the directory (see Handler.do_GET).
    # cwd is only the fallback for a request that names no directory at all.
    directory_root = os.getcwd()
    if os.environ.get("VIEWER_CAD_BACKEND_VALIDATED") != "1":
        try:
            cadgen_bridge.require_cadgen_runtime(directory_root)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    _Ctx.directory_root = directory_root
    # viewer app root is the parent of this server_py package -> dist is <viewer>/dist.
    viewer_app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _Ctx.dist_root = os.path.abspath(args.dist_root) if args.dist_root else os.path.join(viewer_app_root, "dist")
    _Ctx.port = server_info_mod.normalize_viewer_port(args.port)
    _Ctx.host = args.host
    _Ctx.backend = backend_mod.LocalAssetBackend()

    httpd = ThreadingHTTPServer((args.host, _Ctx.port), Handler)
    print(f"Python CAD Viewer backend listening on http://{args.host}:{_Ctx.port}/ (local-fs)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
