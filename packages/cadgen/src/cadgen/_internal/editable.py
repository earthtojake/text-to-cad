"""Whether this cadgen is an editable install of a source tree, and of which one.

``pip install -e <dir>`` (and ``uv pip install -e``) records the source directory beside the
distribution's metadata (``direct_url.json``, PEP 610), and the import path then points at that
live directory. ``cadgen doctor`` names it when a skill's pin disagrees with the version that
install recorded, and the install channel counts a source tree as a development install
(``channel.py``).
"""

from __future__ import annotations


def editable_source() -> str | None:
    """The directory this cadgen was EDITABLE-installed from, or ``None``.

    Anything unreadable, unparseable or non-editable answers ``None``: a caller that cannot tell
    does the ordinary thing rather than guessing.
    """
    import json
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        recorded = distribution("cadgen").read_text("direct_url.json")
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
