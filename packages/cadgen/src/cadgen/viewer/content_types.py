"""The two hand-written content-type maps.

Do NOT replace these with ``mimetypes``: the three.js GLB/WASM loaders and the
browser's ES-module loader are strict, so the bytes must match what the client
has always been served. ``mimetypes`` is also platform-dependent — it reads the
system's mime.types — which would make the wire format vary by machine.
"""

from __future__ import annotations

from cadgen.file_types import COMPOUND_EXTENSIONS, extension_of, format_of

__all__ = [
    "COMPOUND_EXTENSIONS",
    "content_type_for_static_asset",
    "content_type_for_path",
    "extension_of",
    "format_of",
]

# Static dist/SPA assets. Unknown extension -> "" and the caller sets NO
# content-type header at all (not octet-stream).
_STATIC_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
    ".wasm": "application/wasm",
    ".woff2": "font/woff2",
}

# CAD assets (/__cad/asset, /__cad/store). Unknown -> octet-stream.
#
# Exactly the extensions those two routes can actually emit: the asset route
# serves the cataloged formats (scanner.SOURCE_EXTENSIONS) plus the
# `.step.json`/`.stp.json` sidecars, and the store tier holds `.surf`/`.brep`
# component files (octet-stream by fallthrough) beside `assembly.json`.
_ASSET_CONTENT_TYPES = {
    ".json": "application/json; charset=utf-8",
    ".glb": "model/gltf-binary",
    ".stl": "model/stl",
    ".3mf": "model/3mf",
    ".step": "application/step",
    ".stp": "application/step",
    ".dxf": "application/dxf",
    ".kicad_pcb": "text/plain; charset=utf-8",
    ".kicad_sch": "text/plain; charset=utf-8",
    ".harness.yml": "application/yaml; charset=utf-8",
    ".urdf": "application/xml; charset=utf-8",
    ".srdf": "application/xml; charset=utf-8",
    ".sdf": "application/xml; charset=utf-8",
}


def content_type_for_static_asset(file_path) -> str:
    return _STATIC_CONTENT_TYPES.get(extension_of(file_path), "")


def content_type_for_path(file_path) -> str:
    return _ASSET_CONTENT_TYPES.get(extension_of(file_path), "application/octet-stream")
