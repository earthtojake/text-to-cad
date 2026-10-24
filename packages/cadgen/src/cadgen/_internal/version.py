"""The version a cadgen reports and keys with: the one declared beside its code.

ONE source of truth. A checkout imported by path (``PYTHONPATH``) and an installed wheel
both answer from the files that are actually running: the source tree's ``pyproject.toml``
beside the package, else the ``.dist-info`` installed beside it. Never the first ``cadgen``
metadata on ``sys.path``: a machine carries several (a stale editable install's egg-info, a
wheel in site-packages, the checkout's own), and the one ``importlib.metadata`` finds first
is whichever install happens to sort first, not the code that was imported -- which reported
an older release as the version of this tree.
"""

from __future__ import annotations

from pathlib import Path


def declared_version(package_dir: Path) -> str:
    """The version declared beside the ``cadgen`` package at ``package_dir``: its source
    tree's ``pyproject.toml`` (``<tree>/pyproject.toml`` two levels up, as ``src/cadgen``
    lies), else the newest ``cadgen-*.dist-info`` beside it -- more than one only after an
    install that failed midway, and the last one written is the install that put these
    files here. ``0+unknown`` with neither."""
    import tomllib

    base = Path(package_dir)
    pyproject = base.parent.parent / "pyproject.toml"
    try:
        with pyproject.open("rb") as handle:
            project = tomllib.load(handle).get("project") or {}
        if project.get("name") == "cadgen" and project.get("version"):
            return str(project["version"])
    except (OSError, ValueError):
        pass
    found = []
    for metadata in base.parent.glob("cadgen-*.dist-info"):
        try:
            found.append((metadata.stat().st_mtime_ns, metadata.name))
        except OSError:
            continue
    if found:
        return max(found)[1][len("cadgen-"):-len(".dist-info")]
    return "0+unknown"
