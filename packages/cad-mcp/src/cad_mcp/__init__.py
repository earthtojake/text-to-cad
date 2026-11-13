"""CAD beside an agent's chat: the stdio transport an agent app starts, forwarding MCP to the device's CAD
server over HTTP (``shim``).

The standard library alone. It is one version (its own release) on one delivery channel (``--channel``), and
reaches that version's server the way the server's own clients do -- its door in the engine folder (``engine``)
--, makes its version present and its channel on it as it starts, and starts that version's server when none
answers. A source tree has no version, and reaches the current installation's, as every release of 0.11.10 and
earlier. Everything CAD is, the server is: this process carries the host's requests to it and its answers
back, opens the person's browser where a text host's ``cad_show`` asks, and tells the server which host
started it.
"""

from __future__ import annotations

from functools import cache as _cache
from pathlib import Path as _Path

# The distribution this package ships in, whose release it is (``__version__``).
DISTRIBUTION = "cad-mcp"

__all__ = ["DISTRIBUTION", "__version__"]


def __getattr__(name: str):
    if name == "__version__":
        return _version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def source_tree() -> bool:
    """Whether this package runs from a source tree (its ``pyproject.toml`` two levels up, ``src/cad_mcp``): a
    checkout's, which has no version of its own on the device."""
    return (_Path(__file__).resolve().parent.parent.parent / "pyproject.toml").is_file()


@_cache
def _version() -> str:
    """The version declared beside this very package: the source tree's ``pyproject.toml`` two levels up
    (``src/cad_mcp``), else the newest ``.dist-info`` of its distribution installed beside it; ``0+unknown``
    with neither. Never the first metadata on the import path, which can be another install's."""
    import tomllib

    package = _Path(__file__).resolve().parent
    try:
        with (package.parent.parent / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle).get("project") or {}
        if project.get("name") == DISTRIBUTION and project.get("version"):
            return str(project["version"])
    except (OSError, ValueError):
        pass
    stem = DISTRIBUTION.replace("-", "_")
    found = []
    for metadata in package.parent.glob(f"{stem}-*.dist-info"):
        try:
            found.append((metadata.stat().st_mtime_ns, metadata.name))
        except OSError:
            continue
    if found:
        return max(found)[1][len(stem) + 1:-len(".dist-info")]
    return "0+unknown"
