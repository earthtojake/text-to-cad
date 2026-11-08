"""A robot description's mesh reference: the URI scheme it is spelled with, and the local file it names.

URDF and SDF name a link's mesh by a path or a URI (``meshes/base.stl``, ``/opt/robot/base.stl``,
``C:\\robot\\base.stl``, ``file:///C:/robot/base.stl``, ``package://arm/meshes/base.stl``,
``model://arm/meshes/base.stl``, ``https://...``). Every reader of one -- the URDF and SDF readers and
validators, the viewer's robot payload, the stills (``formats.robot``) -- turns it into a file here, so
the same reference names the same file in each. The standard library only: the validators that use
it run without the CAD stack.

A drive letter is not a scheme: ``urlparse`` reads ``C:/x`` (and ``C:\\x``) as scheme ``c``, which
would make a Windows path a remote URI. A ``file:`` URI is read by the platform's
``url2pathname``: on Windows ``/C:/x`` loses the slash before its drive and ``%20`` decodes either
way. A ``file:`` URI's host is ``localhost`` or none for a file on this machine; another host
names a share, which Windows reads as the UNC path ``\\\\host\\share\\...``, and which no POSIX
path can name, so there it names no local file (it is not silently read as ``/share/...`` here).

A ``package://NAME/REST`` reference is REST in the ROS package the description is in: the nearest
folder at or above it named NAME, or holding a ``package.xml`` that names it (``package_file``), as
every reader of a robot description finds it (the engine's ``urdf_source`` and ``sdf_source``, and
through them the stills and the viewer's payload).
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname
import xml.etree.ElementTree as ET

__all__ = ["PackageError", "local_path", "package_file", "package_root", "scheme"]

_WINDOWS = os.name == "nt"


def scheme(reference: str) -> str:
    """The URI scheme ``reference`` is spelled with, lower case (``package``, ``file``, ``https``);
    ``""`` for a path, a Windows drive path (``C:/x``, ``c:\\x``) among them."""
    found = urlparse(reference).scheme
    return found if len(found) > 1 else ""


def local_path(reference: str) -> str | None:
    """The path of the file ``reference`` names on this machine, spelled as this machine spells it
    and relative where the reference is (to the description that names it); None where it names
    no local file: a reference with any scheme but ``file``, or a ``file:`` URI on another host
    off Windows."""
    kind = scheme(reference)
    if not kind:
        return reference
    if kind != "file":
        return None
    parsed = urlparse(reference)
    host = parsed.netloc
    if host.lower() in ("", "localhost"):
        return url2pathname(parsed.path)
    if _WINDOWS:
        return url2pathname(f"//{host}{parsed.path}")  # \\host\share\...
    return None


class PackageError(ValueError):
    """A ``package://`` reference no folder above the description holds, or one climbing out of its package."""


def _package_name(manifest: Path) -> str | None:
    """The name a ROS package manifest (``package.xml``) gives its package, or None."""
    try:
        name = ET.parse(manifest).getroot().find("name")
    except (OSError, ET.ParseError):
        return None
    if name is None:
        return None
    return str(name.text or "").strip() or None


def package_root(name: str, base: Path) -> Path | None:
    """ROS package ``name``'s folder for a description in ``base``: the nearest folder at or above
    ``base`` that is named ``name``, or that holds a ``package.xml`` naming it, ROS's own mark of a
    package's root; None when none is."""
    for folder in (base, *base.parents):
        if folder.name == name:
            return folder
        manifest = folder / "package.xml"
        if manifest.is_file() and _package_name(manifest) == name:
            return folder
    return None


def package_file(reference: str, base: Path, where: str) -> Path:
    """``package://NAME/REST``, named by a description in ``base``: REST in package NAME's folder
    (``package_root``), never above it. Refused by name (``where`` names what names it) when no
    folder holds the description as its package, and when REST climbs out of it."""
    parsed = urlparse(reference)
    name, rest = unquote(parsed.netloc).strip(), unquote(parsed.path).lstrip("/")
    base = Path(base).resolve()
    root = package_root(name, base) if name and rest else None
    if root is None:
        raise PackageError(f"{where} names {reference!r}: no folder named {name!r}, nor one holding a package.xml that "
                           f"names it, holds {base}, so its package cannot be found. Keep the description inside its "
                           "package folder, or name the mesh by a path relative to the description")
    found = (root / rest).resolve()
    if root not in found.parents:
        raise PackageError(f"{where} names {reference!r}, which climbs out of its package, {root}")
    return found
