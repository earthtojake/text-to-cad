"""Byte-faithful ports of the JS encoders the client depends on.

Every function here mirrors a specific Node site in viewer/src/server. The
divergences from Python stdlib defaults are the whole point — they are the
silent-breakage traps:

- ``base36`` matches ``Number.prototype.toString(36)`` / ``BigInt.toString(36)``
  (lowercase). Python has no stdlib base36 and ``os.stat`` returns float
  seconds, so the ``?v=`` cache token must be hand-rolled over ``st_mtime_ns``.
- ``encode_uri_component`` matches JS ``encodeURIComponent`` (leaves ``!*'()``
  unescaped; ``urllib.parse.quote`` would escape ``()*``).
- ``url_search_params_encode`` matches ``URLSearchParams.toString()`` /
  application-x-www-form-urlencoded (space -> ``+``, ``~`` -> ``%7E``); Python's
  ``quote_plus`` keeps ``~`` and so would diverge.
- ``attachment_content_disposition`` matches httpHandlers.mjs
  ``attachmentContentDisposition`` (dual ``filename`` + RFC5987 ``filename*``).
- ``compact_json`` matches ``JSON.stringify`` (no spaces, raw non-ASCII,
  insertion-ordered keys).
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import string

_BASE36_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def base36(value: int) -> str:
    """Match JS ``Number(value).toString(36)`` for integers (lowercase).

    Handles arbitrarily large ints (file mtimes in nanoseconds are ~1e18,
    which Node reads as BigInt via ``fs.statSync(p, {bigint:true})``).
    """
    n = int(value)
    if n == 0:
        return "0"
    negative = n < 0
    n = -n if negative else n
    out = []
    while n:
        n, rem = divmod(n, 36)
        out.append(_BASE36_DIGITS[rem])
    out.reverse()
    text = "".join(out)
    return "-" + text if negative else text


def file_version(file_path: str) -> str:
    """Port of cadDirectoryScanner.fileVersion: ``base36(size)-base36(mtimeNs)``.

    Uses ``st_mtime_ns`` (nanoseconds) to match Node's ``stats.mtimeNs``;
    ``st_mtime`` (float seconds) would produce a different token. Returns ""
    for anything that is not a regular file (matching the JS fileStats guard).
    """
    try:
        stats = os.stat(file_path)
    except OSError:
        return ""
    if not os.path.isfile(file_path):
        return ""
    return f"{base36(stats.st_size)}-{base36(stats.st_mtime_ns)}"


# JS encodeURIComponent leaves these unreserved in addition to the always-safe
# alphanumerics and "-_.~" that urllib already preserves.
_ENCODE_URI_COMPONENT_SAFE = "!*'()"


def encode_uri_component(value: str) -> str:
    """Match JS ``encodeURIComponent`` exactly (uppercase %XX, UTF-8)."""
    from urllib.parse import quote

    return quote(str(value), safe=_ENCODE_URI_COMPONENT_SAFE)


def encode_content_disposition_filename(value: str) -> str:
    """Port of httpHandlers.encodeContentDispositionFilename.

    ``encodeURIComponent`` then additionally percent-escape ``'()*`` as
    uppercase %XX (RFC5987 token tightening).
    """
    encoded = encode_uri_component(value)
    return re.sub(r"['()*]", lambda m: "%" + format(ord(m.group()), "02X"), encoded)


def download_filename(value: str) -> str:
    """Port of httpHandlers.downloadFilename.

    Take the POSIX basename of the backslash-normalized value (default
    "download"), then replace control chars, quotes and backslashes with "_".
    """
    normalized = str(value or "").replace("\\", "/")
    base = posixpath.basename(normalized) or "download"
    return re.sub(r'[\x00-\x1f"\\]', "_", base)


def attachment_content_disposition(filename: str) -> str:
    """Port of httpHandlers.attachmentContentDisposition (dual filename form)."""
    safe = download_filename(filename)
    quoted = re.sub(r"[^\x20-\x7e]", "_", safe)
    star = encode_content_disposition_filename(safe)
    return f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{star}"


# URLSearchParams / application-x-www-form-urlencoded keeps alphanumerics and
# "*-._"; space becomes "+"; everything else (including "~") is %XX uppercase.
_FORM_SAFE = frozenset(string.ascii_letters + string.digits + "*-._")


def _form_encode(value: str) -> str:
    out = []
    for byte in str(value).encode("utf-8"):
        char = chr(byte)
        if char == " ":
            out.append("+")
        elif char in _FORM_SAFE:
            out.append(char)
        else:
            out.append("%" + format(byte, "02X"))
    return "".join(out)


def url_search_params_encode(pairs) -> str:
    """Match ``URLSearchParams.toString()`` for an ordered list of (key, value).

    Pairs preserve insertion order (as the JS ``URLSearchParams`` does); empty
    values are still emitted as ``key=`` only if explicitly included by the
    caller (callers omit empties, matching localAssetUrlForPath).
    """
    return "&".join(f"{_form_encode(k)}={_form_encode(v)}" for k, v in pairs)


def compact_json(payload) -> str:
    """Match ``JSON.stringify(payload)``: no spaces, raw non-ASCII, key order."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
