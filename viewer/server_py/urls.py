"""Asset-URL stamping, matching localAssetBackend.localAssetUrlForPath.

The client reads ``entry.url`` / ``moduleUrl`` / ``relations[*].url`` verbatim
and packageAssetUrl.js rewrites ONLY the ``file`` param, so this must emit the
exact byte string: ``/__cad/asset?file=<ABS>&dir=<root>&v=<token>`` with the
``file``/``dir``/``v`` order, ``file`` always absolute, ``dir`` and ``v``
omitted when empty, and ``URLSearchParams`` form encoding (space -> ``+``).
"""

from __future__ import annotations

import os

from .encoding import url_search_params_encode


def absolute_file_ref(file_path: str) -> str:
    """Port of localAssetBackend.absoluteFileRef (path.resolve)."""
    return os.path.abspath(str(file_path or ""))


def local_asset_url_for_path(file_path: str, version: str = "", root_dir: str = "") -> str:
    pairs = [("file", absolute_file_ref(file_path))]
    normalized_root = str(root_dir or "").strip()
    if normalized_root:
        pairs.append(("dir", normalized_root))
    normalized_version = str(version or "").strip()
    if normalized_version:
        pairs.append(("v", normalized_version))
    return "/__cad/asset?" + url_search_params_encode(pairs)
