"""Files by absolute path: the one rule every route applies to a file it is named, and the gate on
the bytes the asset route sends.

There is no served directory. Every ``?file=`` -- and every path in a request's body -- names a
file by its ABSOLUTE path, anywhere on this machine, and anything else is refused with a 400: the
page resolves a developer's relative link against the folder this viewer was started in
(``serverInfo.start``) before it asks. Nothing is refused for WHERE it is: no root, no containment,
and no rule about hidden folders on the way to a file that is named.

What is refused is what would LEAVE as bytes. The asset route sends only CAD files and their
sidecars (``scanner.is_served_cad_asset``), so a ``.py``, a config or a key file is a 404 whatever
path names it, and the browser's same-origin policy -- no ``Access-Control-*`` header is ever
served (``http_app``) -- keeps another site from reading even those.

A path is a filesystem path, never a URL: nothing here percent-decodes it. On Windows it names its
drive (``C:\\models\\a.step`` or ``C:/models/a.step``); a UNC path (``\\\\host\\share\\a.step``) is
refused, because any web page can make the browser send this server a GET, and a GET must never
send this machine out to the network.
"""

from __future__ import annotations

import os

from .scanner import is_served_cad_asset

__all__ = ["absolute_path", "asset_path"]


def absolute_path(ref) -> str:
    """The absolute path ``ref`` names, in this platform's spelling; ``ValueError`` (400) for a ref
    that is not one."""
    if not isinstance(ref, str) or not ref:
        raise ValueError("name the file by its absolute path")
    if "\0" in ref:
        raise ValueError("File path contains an invalid null byte")
    if os.name == "nt":
        drive, rest = os.path.splitdrive(ref.replace("/", "\\"))
        absolute = len(drive) == 2 and drive[1] == ":" and rest.startswith("\\")
    else:
        absolute = ref.startswith("/")
    if not absolute:
        raise ValueError(f"{ref} is not an absolute path: name the file by its absolute path")
    return os.path.abspath(ref)


def asset_path(ref) -> str | None:
    """The file the asset route may send for ``ref``: a CAD file or its sidecar, else ``None`` (404)."""
    path = absolute_path(ref)
    return path if is_served_cad_asset(path) else None
