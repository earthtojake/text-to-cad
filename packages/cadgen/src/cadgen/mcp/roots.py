"""Where a view browses from. The server decides; the view never guesses.

A root is a directory and how deep its catalog walks. A thread's views root at
the thread's workspace -- the folder the host started this process in, confirmed
by the working directory the host reports on the agent's calls -- and walk the
whole tree. A model opened from anywhere else roots at its own folder and walks
only that folder, so opening a file in a home directory never scans the home
directory.

What is open is always an absolute path; the root only says where browsing
starts, so references never depend on it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

from cadgen.viewer.scanner import SCAN_MAX_DEPTH, VIEWER_SKIPPED_DIRECTORIES, is_hidden_name

WORKSPACE = "workspace"
FOLDER = "folder"
_DEPTH = {WORKSPACE: SCAN_MAX_DEPTH, FOLDER: 0}


@dataclass(frozen=True)
class Root:
    kind: str
    path: str

    @property
    def depth(self) -> int:
        return _DEPTH[self.kind]

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, os.path.normcase(os.path.realpath(self.path)))

    def public(self) -> dict[str, Any]:
        return {"kind": self.kind, "path": self.path, "name": os.path.basename(self.path.rstrip(os.sep)) or self.path}


def folder_of(model: str) -> Root:
    return Root(FOLDER, os.path.dirname(model))


def listed_under(root: str, model: str) -> bool:
    """Whether a catalog of ``root`` lists ``model``: no folder between them is one the scan skips.

    A model the agent writes under ``build/`` or a hidden folder is still the thread's,
    but the workspace's catalog never shows it, so it is browsed from its own folder.
    """
    relative = os.path.relpath(os.path.dirname(os.path.realpath(model)), os.path.realpath(root))
    if relative == os.curdir:
        return True
    parts = relative.split(os.sep)
    return len(parts) <= SCAN_MAX_DEPTH and not any(part in VIEWER_SKIPPED_DIRECTORIES or is_hidden_name(part) for part in parts)


def _usable_directory(path: str | None, *, excluded: tuple[str, ...]) -> str | None:
    if not path:
        return None
    path = os.path.abspath(path)
    if not os.path.isdir(path) or os.path.dirname(path) == path:  # the filesystem root is no workspace
        return None
    real = os.path.normcase(os.path.realpath(path))
    if any(real == os.path.normcase(os.path.realpath(other)) for other in excluded if other):
        return None
    return path


def _path_from_file_uri(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if not value.startswith("file:"):
        return value if os.path.isabs(value) else None
    parsed = urlparse(value)
    path = unquote(parsed.path)
    if os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path or None


class ThreadWorkspace:
    """What this process knows about its thread's workspace folders."""

    def __init__(self, launch_cwd: str | None, *, excluded: tuple[str, ...] = ()) -> None:
        self._excluded = excluded
        first = _usable_directory(launch_cwd, excluded=excluded)
        self._paths: list[str] = [first] if first else []

    @property
    def primary(self) -> str | None:
        return self._paths[0] if self._paths else None

    @property
    def paths(self) -> list[str]:
        return list(self._paths)

    def learn(self, meta: dict[str, Any]) -> None:
        """Adopt the folders the host reports on an agent's tool call."""
        sandbox = meta.get("codex/sandbox-state-meta")
        turn = meta.get("x-codex-turn-metadata")
        found: list[str] = []
        if isinstance(sandbox, dict):
            path = _usable_directory(_path_from_file_uri(sandbox.get("sandboxCwd")), excluded=self._excluded)
            if path:
                found.append(path)
        if isinstance(turn, dict) and isinstance(turn.get("workspaces"), dict):
            for key in turn["workspaces"]:
                path = _usable_directory(_path_from_file_uri(key), excluded=self._excluded)
                if path and path not in found:
                    found.append(path)
        if found:
            self._paths = found + [path for path in self._paths if path not in found]

    def root(self) -> Root | None:
        return Root(WORKSPACE, self.primary) if self.primary else None

    def contains(self, path: str) -> str | None:
        """The workspace folder holding ``path``, if any."""
        real = os.path.realpath(path)
        for folder in self._paths:
            base = os.path.realpath(folder)
            if real == base or real.startswith(base.rstrip(os.sep) + os.sep):
                return folder
        return None

    def accept(self, root: dict[str, Any]) -> Root:
        """Validate a root a view asks for: workspaces must be this thread's."""
        kind, path = root.get("kind"), root.get("path")
        if kind not in _DEPTH or not isinstance(path, str) or not os.path.isabs(path):
            raise ValueError("a root is {kind: 'workspace'|'folder', path: <absolute directory>}")
        if not os.path.isdir(path):
            raise ValueError(f"not a folder: {path}")
        if kind == WORKSPACE and path not in self._paths:
            raise ValueError("that folder is not this thread's workspace")
        return Root(kind, path)
