"""The local-filesystem backend: root resolution, catalog absolutization, and
the guarded path resolver.

The viewer serves ONE directory, fixed when the process starts. Requests never
name a directory — a page URL is just the origin, and ``?file=`` names a file
inside this root — so the containment check is unconditional.

``asset_path_for_file_ref`` is for bytes we will SEND, so on top of containment
it requires the path to be a served CAD asset — which is why a ``.py`` model
script never resolves through it.

It funnels through ``_reject_outside_root``, whose two jobs produce two
DIFFERENT statuses: a path outside the root RAISES (403 Forbidden), while a
path inside it with a hidden root-relative component returns ``True`` and the
caller answers ``None`` (404 Not found). Only ROOT-RELATIVE components are
dot-checked, so a served root that itself lives under a hidden absolute path
still serves.

The ordering of those checks decides the status code and is part of the
contract: the served-extension filter runs BEFORE the containment raise, so
``?file=/etc/passwd`` is 404 (wrong extension) while ``?file=/tmp/x.step`` is
403 (right extension, outside the root).

``require_contained`` IS THE CONTAINMENT RULE, FOR EVERY ROUTE
--------------------------------------------------------------
The outside-the-root half is factored out so the artifact routes can enforce
the SAME rule the asset routes do. They could not before, and the gap was
exploitable end to end: ``GET /__cad/asset?file=<outside>.step`` was correctly
403, but ``POST /__cad/artifact?file=<outside>.step`` compiled that file into
the shared store, after which ``GET /__cad/store?file=<key>/...`` served the
tessellated geometry of a document the viewer was never pointed at. Every
resolver that turns a ``?file=`` ref into a path the server will act on calls
this, and there is exactly one implementation of it to keep them honest.
"""

from __future__ import annotations

import os

from .content_types import content_type_for_path
from .encoding import UriError, local_asset_url_for_path, strict_decode_uri_component
from .scanner import (
    CAD_CATALOG_SCHEMA_VERSION,
    is_served_cad_asset,
    node_basename,
    path_is_inside,
    path_relative,
    scan_cad_directory,
    to_posix_path,
)
from .url_norm import request_pathname, request_query

__all__ = [
    "ForbiddenAssetError",
    "LocalAssetBackend",
    "absolute_file_ref",
    "normalized_file_ref",
    "relative_file_ref",
    "require_contained",
]


class ForbiddenAssetError(Exception):
    """A path resolved outside the served root. The route funnels map it to 403."""

    status_code = 403

    def __init__(self) -> None:
        super().__init__("Forbidden")


def require_contained(root_path: str, candidate: str) -> str:
    """``candidate``, or ``ForbiddenAssetError`` if it is outside ``root_path``.

    Returns the path so a caller uses the value it just checked rather than
    re-deriving one — check-then-use on two different strings is how a
    containment check passes and the wrong file gets opened anyway.

    An ABSOLUTE ref inside the root stays allowed, deliberately: the catalog
    absolutizes every entry's ``file`` and the client sends exactly that back,
    so refusing absolute refs as a class would refuse the normal case. What
    this refuses is an absolute ref that LANDS outside — the same line the
    asset route has always drawn.

    ``path_is_inside`` collapses ``..`` lexically FIRST and only then compares
    real paths for alias equality, so a ``..`` that walks out after a symlinked
    component is still refused while a symlinked served root still serves.
    """
    if not (candidate == root_path or path_is_inside(candidate, root_path)):
        raise ForbiddenAssetError()
    return candidate


def absolute_file_ref(file_path) -> str:
    return to_posix_path(os.path.abspath(str(file_path)))


def relative_file_ref(root_path, file_path) -> str:
    return to_posix_path(path_relative(os.path.abspath(root_path), os.path.abspath(file_path)))


def normalized_file_ref(value) -> str:
    """Normalise a ``?file=`` ref.

    Backslashes become forward slashes ALWAYS and BEFORE the absolute test, so
    on POSIX ``C:\\x`` becomes ``C:/x`` and is treated as relative, while
    ``\\\\server\\share\\x.step`` becomes ``/server/share/x.step`` — absolute,
    outside the root, and refused by containment rather than turned into an SMB
    fetch.

    There is deliberately NO percent-decoding: ``file=`` carries a filesystem
    path, not a URL path, and the catalog is the only source of refs.
    """
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return ""
    if "\0" in raw:
        raise ValueError("File path contains an invalid null byte")
    return absolute_file_ref(raw) if os.path.isabs(raw) else raw.lstrip("/")


def _query_value(raw_url, name: str) -> str:
    try:
        return request_query(str(raw_url or "")).get(name) or ""
    except Exception:  # noqa: BLE001 - mirrors the JS try/catch around new URL
        return ""


def _asset_path_from_catalog_url(scan_repo_root: str, raw_url) -> str:
    """Turn a raw scanner URL back into the absolute path it names."""
    text = str(raw_url or "").strip()
    if not text:
        return ""
    try:
        explicit_file = request_query(text).get("file") or ""
        if explicit_file:
            return os.path.abspath(explicit_file)
        decoded = strict_decode_uri_component(request_pathname(text))
        return os.path.abspath(os.path.join(scan_repo_root, decoded.lstrip("/")))
    except (UriError, ValueError):
        # decodeURIComponent throws on a malformed escape and the JS falls back
        # to a lenient split.
        cleaned = text.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        return os.path.abspath(os.path.join(scan_repo_root, cleaned))


def _absolute_path_from_catalog_value(scan_repo_root: str, value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return os.path.abspath(text if os.path.isabs(text) else os.path.join(scan_repo_root, text))


def _absolutize_keyed(obj, scan_repo_root: str, keys) -> object:
    if not isinstance(obj, dict):
        return obj
    nxt = dict(obj)
    for key in keys:
        if nxt.get(key):
            nxt[key] = absolute_file_ref(_absolute_path_from_catalog_value(scan_repo_root, nxt[key]))
    return nxt


def _is_store_url(value) -> bool:
    return str(value or "").startswith("/__cad/store")


def _absolutize_entry(entry: dict, *, root_path: str, scan_repo_root: str) -> dict:
    output_path = os.path.abspath(os.path.join(root_path, str(entry.get("file") or "")))
    nxt = dict(entry)
    nxt["file"] = absolute_file_ref(output_path)
    nxt["rootRelativeFile"] = relative_file_ref(root_path, output_path)
    if entry.get("url") and not _is_store_url(entry["url"]):
        asset_path = _asset_path_from_catalog_url(scan_repo_root, entry["url"])
        nxt["url"] = local_asset_url_for_path(asset_path, _query_value(entry["url"], "v"))
        nxt["assetFile"] = absolute_file_ref(asset_path)
    for key in ("poseUrl", "sourceUrl"):
        # Store URLs are already in their served form: their file param is
        # store-relative by contract, never a root path to absolutize.
        if entry.get(key) and not _is_store_url(entry[key]):
            asset_path = _asset_path_from_catalog_url(scan_repo_root, entry[key])
            nxt[key] = local_asset_url_for_path(asset_path, _query_value(entry[key], "v"))
    if entry.get("artifact"):
        nxt["artifact"] = _absolutize_keyed(
            entry["artifact"], scan_repo_root, ("stepPath", "packagePath", "sourcePath", "cadPath")
        )
    relations = entry.get("relations")
    if isinstance(relations, dict):
        next_relations = {}
        for key, relation in relations.items():
            if not isinstance(relation, dict):
                next_relations[key] = relation
                continue
            relation_path = os.path.abspath(
                os.path.join(root_path, str(relation.get("file") or ""))
            )
            next_relation = dict(relation)
            next_relation["file"] = absolute_file_ref(relation_path)
            next_relation["rootRelativeFile"] = relative_file_ref(root_path, relation_path)
            if relation.get("url"):
                rel_asset = _asset_path_from_catalog_url(scan_repo_root, relation["url"])
                next_relation["url"] = local_asset_url_for_path(
                    rel_asset, _query_value(relation["url"], "v")
                )
                next_relation["assetFile"] = absolute_file_ref(rel_asset)
            next_relations[key] = next_relation
        nxt["relations"] = next_relations
    return nxt


class LocalAssetBackend:
    kind = "local-fs"

    def __init__(self, root: str = ""):
        root_path = os.path.abspath(str(root or "").strip() or os.getcwd())
        if "\0" in root_path:
            raise ValueError("CAD Viewer directory contains an invalid null byte")
        if not os.path.isdir(root_path):
            raise ValueError(f"CAD Viewer directory not found: {root_path}")
        # path.resolve, NOT realpath: the launcher's registry and serverInfo
        # both report the spelling the operator gave.
        self.root_path = root_path
        self.root_name = node_basename(root_path)

    def resolve_root(self) -> dict:
        return {"rootPath": self.root_path, "rootName": self.root_name}

    def read_catalog(self) -> dict:
        raw = scan_cad_directory(self.root_path)
        return {
            "schemaVersion": CAD_CATALOG_SCHEMA_VERSION,
            "entries": [
                _absolutize_entry(entry, root_path=self.root_path, scan_repo_root=self.root_path)
                for entry in raw["entries"]
            ],
        }

    # --- containment ------------------------------------------------------

    def _reject_outside_root(self, candidate: str) -> bool:
        """Raise for anything outside the root; return True for a hidden path.

        The containment half is ``require_contained`` — the one the artifact
        routes share. The hidden-component half stays here, because it is a rule
        about bytes this backend would SERVE, not about what the server may
        touch: a hidden ``.step`` is still a document the import path may
        legitimately compile.
        """
        require_contained(self.root_path, candidate)
        relative = path_relative(self.root_path, candidate)
        return any(
            part and part != ".." and part.startswith(".") for part in relative.split(os.sep)
        )

    def asset_path_for_file_ref(self, file_ref) -> str | None:
        normalized = normalized_file_ref(file_ref)
        if not normalized or not os.path.isabs(normalized):
            # A ROOT-RELATIVE ref 404s here. That asymmetry with
            # /__cad/artifact (which accepts one) is shipped behaviour.
            return None
        candidate = os.path.abspath(normalized)
        if not is_served_cad_asset(candidate):
            return None
        if self._reject_outside_root(candidate):
            return None
        return candidate

    # --- helpers ----------------------------------------------------------

    def content_type_for_path(self, file_path) -> str:
        return content_type_for_path(file_path)

    def catalog_entry_for_file_ref(self, catalog, file_ref):
        norm = normalized_file_ref(file_ref)
        if not norm or not isinstance(catalog, dict):
            return None
        for entry in catalog.get("entries") or []:
            if (
                normalized_file_ref(entry.get("file")) == norm
                or normalized_file_ref(entry.get("rootRelativeFile")) == norm
            ):
                return entry
        return None
