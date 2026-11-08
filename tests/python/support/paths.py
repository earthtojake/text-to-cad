from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

# The three distributions' projects: the library, the server and the shim (packages/README.md).
LIBRARY = REPO_ROOT / "packages" / "cad"
SERVER = REPO_ROOT / "packages" / "cad-server"
SHIM = REPO_ROOT / "packages" / "cad-mcp"
PROJECTS = (LIBRARY, SERVER, SHIM)
# Their source trees, and ``PYTHONPATH``'s spelling of them: a child a test starts imports this
# checkout's packages, never whatever its interpreter has installed.
SOURCES = tuple(project / "src" for project in PROJECTS)
SOURCE_PATH = os.pathsep.join(str(source) for source in SOURCES)


def repo_path(*parts: str) -> Path:
    return REPO_ROOT.joinpath(*parts)


def add_repo_path(*parts: str) -> Path:
    path = repo_path(*parts)
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)
    return path


def add_sources() -> str:
    """The three packages' source trees first on this process's path, the library's first: ``SOURCE_PATH``."""
    for source in reversed(SOURCES):
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
    return SOURCE_PATH
