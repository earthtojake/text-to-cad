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
"""
from __future__ import annotations

import os
from urllib.parse import urlparse
from urllib.request import url2pathname

__all__ = ["local_path", "scheme"]

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
