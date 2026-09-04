"""Store facts as the viewer server spells them: cadgen's helpers, returning ``str``.

The store itself -- root, objects, index kinds, records, trees, the sidecar name --
has ONE implementation, in ``cadgen.store``, ``cadgen.catalog`` and
``cadgen._internal.source_sidecar`` (``STORE.md`` is the contract). This module
is the server's adapter over it: every helper here delegates and hands back a
string or a plain dict, because the routes compare, join and prefix-match paths
as strings.

All of these read the environment on EVERY call, never memoised: the suites set
``CADGEN_CACHE_DIR`` after the app is constructed and expect the next call to
observe the change. None of them imports the CAD kernel.
"""

from __future__ import annotations

import os
from pathlib import Path

from cadgen import catalog
from cadgen._internal import source_sidecar

__all__ = [
    "SOURCE_SIDECAR_NAMES",
    "SOURCE_SIDECAR_SCHEMA_VERSION",
    "SOURCE_SIDECAR_SUFFIX",
    "artifact_file_hash",
    "artifact_path_key",
    "cadgen_cache_root_dir",
    "component_object_present",
    "build_scope",
    "record_for",
    "result_descriptor",
    "result_tree",
    "source_sidecar_path",
    "virtual_store_asset",
]

# The source sidecar sits beside the model at ``<name>.step.json`` and carries
# the model's DECLARATIONS. Never test a path with ``endswith(SOURCE_SIDECAR_SUFFIX)``
# alone -- it is ``.json``, and serving every JSON file under a served root would
# hand out configs and secrets. Use SOURCE_SIDECAR_NAMES where a path is all you have.
SOURCE_SIDECAR_SUFFIX = source_sidecar.SOURCE_SIDECAR_SUFFIX
SOURCE_SIDECAR_NAMES = (".step.json", ".stp.json")
SOURCE_SIDECAR_SCHEMA_VERSION = source_sidecar.SOURCE_SIDECAR_SCHEMA_VERSION


def cadgen_cache_root_dir() -> str:
    """``CADGEN_CACHE_DIR``, else the platform convention, else ``~/.cache/cadgen``."""
    from cadgen.store.paths import store_root

    return str(store_root())


def artifact_file_hash(file_path) -> str | None:
    """sha256 of the file's bytes, or ``None`` when it cannot be read."""
    return catalog.artifact_file_hash(Path(str(file_path)))


def artifact_path_key(file_path) -> str:
    """Model-PATH identity for progress records."""
    return catalog.artifact_path_key(Path(str(file_path)))


def build_scope(file_path) -> str:
    """The model's build scope: a NAME derived from its path (``cadgen.catalog.build_scope``).
    Also the server's identity key for one model's in-flight build."""
    return catalog.build_scope(Path(str(file_path)))


def record_for(file_path) -> dict | None:
    """The model record behind a document (``STORE.md`` §records), or ``None``."""
    from cadgen.store.records import record_for_document

    return record_for_document(Path(str(file_path)))


def result_tree(file_path) -> str | None:
    """The tree for a document's BYTES (``index/document``), or ``None`` (never built, or
    the tree object is gone)."""
    return catalog.result_tree_for(Path(str(file_path)))


def result_descriptor(tree_hash: str) -> dict | None:
    """The flattened tree in the shape the client reads (component refs spelled
    ``components/<object>.surf``), or ``None`` for an unknown tree."""
    from cadgen.store.view import descriptor_for_view

    return descriptor_for_view(str(tree_hash))


def component_object_present(digest: str) -> bool:
    """Whether a component's object (``surfObject``/``brepObject``) is in the store."""
    from cadgen.store.objects import has_object, is_object_hash

    return bool(is_object_hash(digest) and has_object(str(digest)))


def virtual_store_asset(rel: str):
    """``(payload, content_type)`` for ``<tree>/assembly.json`` or
    ``<tree>/components/<object>.<suffix>``; ``(None, "")`` for anything else."""
    from cadgen.store.view import virtual_path

    return virtual_path(str(rel or ""))


def source_sidecar_path(entry_path) -> str:
    """``part.step`` -> ``part.step.json``, spelled absolutely."""
    return str(source_sidecar.source_sidecar_path(Path(os.path.abspath(str(entry_path)))))
