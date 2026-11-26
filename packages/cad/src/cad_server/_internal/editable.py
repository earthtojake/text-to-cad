"""Whether this cad is a development build: an editable install of a source tree, or a version named as one.

``pip install -e <dir>`` (and ``uv pip install -e``, ``uv tool install -e``) records the source directory beside
the distribution's metadata (``direct_url.json``, PEP 610), and the import path then points at that live directory
(``editable_source``).

**A development build** (``development``) is a version named ``<release>-dev.<time>``, or a source tree -- installed
editable, or imported from a checkout by path -- that was not told which version it runs as
(``places.INSTALLATION_ENV``). It reads no version feed (``cad_server.updates``) and sends no telemetry by default
(``cad_server.analytics``).
"""

from __future__ import annotations

import functools
import logging
import os
import re
from pathlib import Path

LOG = logging.getLogger("cad_server.editable")

# A development build's name, ``<release>-dev.<YYYYmmddHHMMSS>``.
_DEVELOPMENT = re.compile(r"(?P<release>.+)-dev\.(?P<stamp>[0-9]+)")


def editable_source() -> str | None:
    """The directory this cad was EDITABLE-installed from, or ``None``.

    Anything unreadable, unparseable or non-editable answers ``None``: a caller that cannot tell
    does the ordinary thing rather than guessing.
    """
    import json
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        recorded = distribution("cad").read_text("direct_url.json")
    except (PackageNotFoundError, OSError):
        return None
    try:
        direct = json.loads(recorded or "")
    except ValueError:
        return None
    if not isinstance(direct, dict):
        return None
    directory = direct.get("dir_info")
    if not isinstance(directory, dict) or not directory.get("editable"):
        return None
    url = str(direct.get("url") or "")
    if not url.startswith("file://"):
        return None
    # url2pathname, not a prefix strip: a Windows record is file:///C:/... and
    # the path component of that is "/C:/...".
    from urllib.parse import unquote, urlparse
    from urllib.request import url2pathname

    return url2pathname(unquote(urlparse(url).path))


@functools.cache
def _source_tree() -> bool:
    """An editable install, or the server imported from a checkout by path -- as the engine daemon and its
    workers are (``PYTHONPATH`` names the checkout's ``src`` first), where the first metadata found can be a
    build's leftover rather than the editable install's record. Told by where the server is imported from before
    any metadata is read: the scan costs every command that counts something tens of milliseconds, and a server
    imported from a folder of installed packages is no source tree (an editable install imports from its
    source)."""
    package = Path(__file__).resolve().parents[1]  # cad_server/
    if package.parent.name == "src" and (package.parents[1] / "pyproject.toml").is_file():
        return True
    if package.parent.name in ("site-packages", "dist-packages"):
        return False
    return editable_source() is not None


def development() -> bool:
    """Whether this process is a development build (see the module): the version it was told it runs as
    (``CAD_INSTALLATION_VERSION``) is a development build's name; told none, a source tree is one, and an installed
    server is one where the version it runs as (``places.installation``: the one it is registered as) is. Never
    raises: what cannot be read is no development build."""
    try:
        told = os.environ.get("CAD_INSTALLATION_VERSION", "").strip()
        if told:
            return _DEVELOPMENT.fullmatch(told) is not None
        if _source_tree():
            return True
        from cad.engine.places import installation

        return _DEVELOPMENT.fullmatch(installation() or "") is not None
    except Exception:  # noqa: BLE001 - a fact for a report and a default, never a reason to fail
        LOG.debug("could not tell whether this is a development build", exc_info=True)
        return False
