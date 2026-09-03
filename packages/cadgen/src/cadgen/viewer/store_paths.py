"""Store layout as the viewer server spells it: cadgen's helpers, returning ``str``.

The layout itself -- cache root, tiers, content keys, sidecar and record names --
has ONE implementation, in ``cadgen.catalog``, ``cadgen._internal.cache_paths``,
``cadgen._internal.cache_schema`` and ``cadgen._internal.source_sidecar``. This
module is the server's adapter over it: every helper here delegates and hands back
a string, because the routes compare, join and prefix-match paths as strings.

It used to be a deliberate local copy, kept equal by a parity test, so that
viewing could work without cadgen installed. The server ships inside cadgen now;
the copy and its guard are gone.

All of these read the environment on EVERY call, never memoised: the suites set
``CADGEN_CACHE_DIR`` after the app is constructed and expect the next call to
observe the change. None of them imports the CAD kernel.
"""

from __future__ import annotations

import os
from pathlib import Path

from cadgen import catalog
from cadgen._internal import cache_paths, cache_schema, source_sidecar

__all__ = [
    "ARTIFACT_PATH_KEY_LENGTH",
    "CACHE_SCHEMA_VERSION",
    "PROVENANCE_RECORD_SUFFIX",
    "RECORDS_DIR_NAME",
    "SOURCE_SIDECAR_NAMES",
    "SOURCE_SIDECAR_SCHEMA_VERSION",
    "SOURCE_SIDECAR_SUFFIX",
    "artifact_file_hash",
    "artifact_path_key",
    "cadgen_cache_root_dir",
    "coordination_scope",
    "package_dir_for_hash",
    "render_package_dir",
    "source_provenance_record_path",
    "source_sidecar_path",
    "store_locks_dir",
    "store_packages_dir",
    "store_records_dir",
]

# The ONE cache-scheme number. It salts every store package key
# (``<hash>-v<N>``), so a bump orphans old artifacts BY NAME and everything
# regenerates on demand.
CACHE_SCHEMA_VERSION = cache_schema.CACHE_SCHEMA_VERSION

# The source sidecar sits beside the model at ``<name>.step.json`` and carries
# the model's DECLARATIONS. Never test a path with ``endswith(SOURCE_SIDECAR_SUFFIX)``
# alone -- it is ``.json``, and serving every JSON file under a served root would
# hand out configs and secrets. Use SOURCE_SIDECAR_NAMES where a path is all you have.
SOURCE_SIDECAR_SUFFIX = source_sidecar.SOURCE_SIDECAR_SUFFIX
SOURCE_SIDECAR_NAMES = (".step.json", ".stp.json")
SOURCE_SIDECAR_SCHEMA_VERSION = source_sidecar.SOURCE_SIDECAR_SCHEMA_VERSION

# The records tier, where a build's provenance actually lives. Evictable by
# design (``cadgen cache gc`` sweeps it): a missing record must degrade to
# "imported", never to an error.
RECORDS_DIR_NAME = "records"
PROVENANCE_RECORD_SUFFIX = ".source.json"
ARTIFACT_PATH_KEY_LENGTH = 24


def cadgen_cache_root_dir() -> str:
    """``CADGEN_CACHE_DIR``, else the platform convention, else ``~/.cache/cadgen``."""
    return str(cache_paths.cache_root())


def store_packages_dir() -> str:
    return str(cache_paths.packages_dir())


def store_locks_dir() -> str:
    return str(cache_paths.locks_dir())


def store_records_dir() -> str:
    return str(cache_paths.records_dir())


def artifact_file_hash(file_path) -> str | None:
    """sha256 of the file's bytes, or ``None`` when it cannot be read.

    ``None`` is the "no package" answer, not an error: every caller turns it
    into a deterministic never-created path.
    """
    return catalog.artifact_file_hash(Path(str(file_path)))


def package_dir_for_hash(step_hash: str) -> str:
    return str(catalog.package_dir_for_hash(step_hash))


def render_package_dir(file_path) -> str:
    """The store package for an artifact, resolved by CONTENT.

    Same bytes anywhere on disk resolve to the same package; an unreadable or
    missing file resolves to ``packages/unbuilt-<pathKey>``, a deterministic
    path that is never created.
    """
    return str(catalog.render_package_dir(Path(str(file_path))))


def artifact_path_key(file_path) -> str:
    """Model-PATH identity for the locks and records tiers."""
    return catalog.artifact_path_key(Path(str(file_path)))


def coordination_scope(file_path) -> str:
    """``<cache>/locks/<pathKey>`` -- a NAME, never created as a directory."""
    return str(catalog.coordination_scope(Path(str(file_path))))


def source_provenance_record_path(file_path) -> str:
    """``<cache>/records/<pathKey>.source.json``."""
    return str(source_sidecar.provenance_record_path(Path(str(file_path))))


def source_sidecar_path(entry_path) -> str:
    """``part.step`` -> ``part.step.json``, spelled absolutely."""
    return str(source_sidecar.source_sidecar_path(Path(os.path.abspath(str(entry_path)))))
