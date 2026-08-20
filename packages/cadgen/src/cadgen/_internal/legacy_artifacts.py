"""Removal of the 0.3.x render artifacts that sat beside a model's source file.

0.3.x wrote a model's render output next to its source, as hidden siblings:

    part.step                     the source
    .part.step.glb                the whole-model GLB
    .part.step/                   the "explorer" directory
        model.glb                 an older location for the same GLB
        topology.json
        topology.bin
        components/<cid>.glb
    ..part.step.glb.<token>.generation.lock.json

0.4.x moved all of it into the per-folder ``__cadgen__`` cache, so none of the
above is read any more — but nothing deleted it, and the GLBs are the large part
of a model directory. A repository upgraded in place therefore carries its whole
0.3.x artifact set forever, and under ``models/`` those files are LFS-tracked, so
they cost on clone as well as on disk.

This module is stdlib-only, like ``package_freshness``, so the viewer's
long-lived server can call it without pulling the CAD runtime in.

Deleting files a user did not ask us to delete is the risk here, so the rules are
narrow: paths are only ever derived from a source entry that exists, names must
match the 0.3.x scheme exactly, the GLB must be a regular file, and the explorer
directory is removed only when everything inside it is a name 0.3.x is known to
have written. Anything unrecognised is reported and left alone rather than swept
up — a hidden directory next to a model is not automatically ours.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Files 0.3.x wrote directly inside `.<entry>/`.
EXPLORER_ARTIFACT_NAMES = frozenset({"model.glb", "topology.json", "topology.bin"})
# The one subdirectory it wrote there, holding content-addressed component GLBs.
EXPLORER_COMPONENT_DIRNAME = "components"
GENERATION_LOCK_SUFFIX = ".generation.lock.json"


def legacy_glb_path(entry_path: Path) -> Path:
    """The 0.3.x hidden whole-model GLB for ``entry_path`` (``.<name>.glb``)."""
    entry = Path(entry_path)
    return entry.parent / f".{entry.name}.glb"


def legacy_explorer_dir(entry_path: Path) -> Path:
    """The 0.3.x explorer directory for ``entry_path`` (``.<name>/``)."""
    entry = Path(entry_path)
    return entry.parent / f".{entry.name}"


def legacy_lock_paths(entry_path: Path) -> list[Path]:
    """Abandoned 0.3.x generation locks for ``entry_path``'s GLB.

    0.3.x named them ``.<glb-name>.<token>.generation.lock.json``, and the GLB name
    already starts with a dot, hence the doubled dot.
    """
    entry = Path(entry_path)
    pattern = f".{legacy_glb_path(entry).name}.*{GENERATION_LOCK_SUFFIX}"
    try:
        return sorted(path for path in entry.parent.glob(pattern) if path.is_file())
    except OSError:
        return []


def _explorer_dir_is_recognised(directory: Path) -> bool:
    """True when every entry under ``directory`` is a name 0.3.x wrote there.

    A hidden directory beside a model is only ours if its contents say so. One
    unrecognised name and the whole directory is left in place: reclaiming a few
    megabytes is not worth deleting something we cannot account for.
    """
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return False
    for entry in entries:
        if entry.is_symlink():
            return False
        if entry.is_dir():
            if entry.name != EXPLORER_COMPONENT_DIRNAME:
                return False
            try:
                components = list(os.scandir(entry.path))
            except OSError:
                return False
            if any(
                component.is_symlink() or not component.name.endswith(".glb")
                for component in components
            ):
                return False
            continue
        if entry.name not in EXPLORER_ARTIFACT_NAMES:
            return False
    return True


def _tree_size(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.stat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


def _remove_tree(path: Path) -> None:
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            try:
                os.unlink(os.path.join(root, name))
            except OSError:
                pass
        for name in dirs:
            try:
                os.rmdir(os.path.join(root, name))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def find_legacy_artifacts(entry_path: Path) -> dict[str, Any]:
    """What 0.3.x left beside ``entry_path``, without touching any of it.

    ``skipped`` holds an explorer directory that exists but whose contents were not
    recognised, so a caller can say why it was left behind.
    """
    entry = Path(entry_path)
    removable: list[Path] = []
    skipped: list[Path] = []

    glb = legacy_glb_path(entry)
    if glb.is_file() and not glb.is_symlink():
        removable.append(glb)

    explorer = legacy_explorer_dir(entry)
    if explorer.is_dir() and not explorer.is_symlink():
        if _explorer_dir_is_recognised(explorer):
            removable.append(explorer)
        else:
            skipped.append(explorer)

    removable.extend(legacy_lock_paths(entry))
    return {
        "paths": removable,
        "skipped": skipped,
        "bytes": sum(_tree_size(path) for path in removable),
    }


def prune_legacy_artifacts(entry_path: Path) -> dict[str, Any]:
    """Delete 0.3.x artifacts beside ``entry_path``; report what went.

    A no-op unless the source entry itself exists: without it there is nothing to
    prove these hidden siblings ever belonged to a model rather than to a user.
    """
    entry = Path(entry_path)
    if not entry.exists():
        return {"removed": [], "skipped": [], "bytes": 0}

    found = find_legacy_artifacts(entry)
    removed: list[Path] = []
    for path in found["paths"]:
        try:
            if path.is_dir():
                _remove_tree(path)
            else:
                path.unlink()
        except OSError:
            continue
        if not path.exists():
            removed.append(path)
    return {"removed": removed, "skipped": found["skipped"], "bytes": found["bytes"]}
