"""The two hand-written content-type maps, ported verbatim.

Do NOT replace these with the stdlib ``mimetypes`` module: it returns
``application/javascript`` (not ``text/javascript``), guesses or omits
``.glb``/``.step``/``.wasm``, and may attach charsets where the JS sends none.
The three.js GLB/WASM loaders and the browser ES-module loader are strict, so
the bytes must match.

- ``content_type_for_path`` mirrors localAssetBackend.contentTypeForPath (the
  ``/__cad/asset`` + ``/__cad/download`` map).
- ``content_type_for_static_asset`` mirrors httpHandlers STATIC_CONTENT_TYPES
  (the dist/SPA map). Unknown extensions return "" -> the caller sets NO
  content-type header, matching the Node behavior.
"""

from __future__ import annotations

import os

# httpHandlers.mjs STATIC_CONTENT_TYPES (dist assets). Unknown ext -> "".
_STATIC_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
}


def content_type_for_static_asset(file_path: str) -> str:
    ext = os.path.splitext(str(file_path or ""))[1].lower()
    return _STATIC_CONTENT_TYPES.get(ext, "")


# CAD asset content-type map. Note: this is an
# ordered if/else chain in JS; reproduced as a dict with the same mappings.
# Unknown ext -> application/octet-stream (the JS default).
_ASSET_CONTENT_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".wasm": "application/wasm",
    ".glb": "model/gltf-binary",
    ".stl": "model/stl",
    ".3mf": "model/3mf",
    ".step": "application/step",
    ".stp": "application/step",
    ".dxf": "application/dxf",
    ".py": "text/plain; charset=utf-8",
    ".urdf": "application/xml; charset=utf-8",
    ".srdf": "application/xml; charset=utf-8",
    ".sdf": "application/xml; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


def content_type_for_path(file_path: str) -> str:
    ext = os.path.splitext(str(file_path or ""))[1].lower()
    return _ASSET_CONTENT_TYPES.get(ext, "application/octet-stream")
