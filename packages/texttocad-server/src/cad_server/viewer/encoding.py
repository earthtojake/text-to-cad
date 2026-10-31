"""Byte-faithful ports of the JavaScript URL encoders.

Three different escaping alphabets live in this backend and none of them is
Python's default:

* ``encode_uri_component``   JS ``encodeURIComponent``: leaves ``!*'()`` alone,
  where ``urllib.parse.quote`` escapes them and leaves ``/`` alone.
* ``form_encode``            ``URLSearchParams``: space becomes ``+``, ``*``
  stays literal, ``~`` becomes ``%7E`` — ``quote_plus`` gets both backwards.
* ``base36``                 lowercase ``0-9a-z``, no padding, no stdlib support.

Every one is pinned against Node's own expressions by
``tests_server/golden/golden.json``. Do not "simplify" any of them without
regenerating that fixture and watching it fail.
"""

from __future__ import annotations

import string
from typing import Iterable

__all__ = [
    "UriError",
    "base36",
    "file_version",
    "encode_uri_component",
    "encode_url_path",
    "form_encode",
    "local_asset_url_for_path",
    "strict_decode_uri_component",
]


class UriError(ValueError):
    """Raised where JavaScript raises ``URIError``.

    ``decodeURIComponent`` throws on a malformed escape, on overlong UTF-8 and
    on a lone surrogate, and callers depend on that throw: ``serve_dist`` maps
    it to 400 "Bad request" and the tess-cache route maps it to a 403 refusal.
    ``urllib.parse.unquote`` raises for none of the three.
    """


# --- base36 ---------------------------------------------------------------

_BASE36_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def base36(value: int) -> str:
    """``BigInt(value).toString(36)``: lowercase, unpadded, ``-`` for negatives."""
    if value == 0:
        return "0"
    negative = value < 0
    remaining = -value if negative else value
    out: list[str] = []
    while remaining:
        remaining, digit = divmod(remaining, 36)
        out.append(_BASE36_DIGITS[digit])
    if negative:
        out.append("-")
    return "".join(reversed(out))


def file_version(size: int, mtime_ns: int) -> str:
    """The ``?v=`` cache token: ``base36(size)-base36(mtimeNs)``.

    ``mtime_ns`` is NANOSECONDS and must come from the same ``os.stat`` call as
    ``size``; ``st_mtime`` (float seconds) silently rewrites every asset URL.
    """
    return f"{base36(size)}-{base36(mtime_ns)}"


# --- encodeURIComponent ---------------------------------------------------

# JS leaves A-Za-z0-9 - _ . ! ~ * ' ( ) unescaped.
_URI_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-_.!~*'()")


def encode_uri_component(value: str) -> str:
    out: list[str] = []
    try:
        raw = value.encode("utf-8")
    except UnicodeEncodeError as exc:  # lone surrogate: JS throws URIError here
        raise UriError("URI malformed") from exc
    for byte in raw:
        char = chr(byte)
        if char in _URI_UNRESERVED:
            out.append(char)
        else:
            out.append(f"%{byte:02X}")
    return "".join(out)


def encode_url_path(repo_relative: str) -> str:
    """``"/" + segments.map(encodeURIComponent).join("/")`` (scanner.mjs)."""
    return "/" + "/".join(encode_uri_component(part) for part in repo_relative.split("/"))


# --- URLSearchParams form encoding ---------------------------------------

# application/x-www-form-urlencoded: space -> "+", and the safe set is
# A-Za-z0-9*-._ — note "*" stays literal while "~" does NOT.
_FORM_SAFE = frozenset(string.ascii_letters + string.digits + "*-._")


def _form_encode_component(value: str) -> str:
    out: list[str] = []
    for byte in value.encode("utf-8", "surrogatepass"):
        char = chr(byte)
        if char in _FORM_SAFE:
            out.append(char)
        elif byte == 0x20:
            out.append("+")
        else:
            out.append(f"%{byte:02X}")
    return "".join(out)


def form_encode(pairs: Iterable[tuple[str, str]]) -> str:
    """``new URLSearchParams(pairs).toString()``."""
    return "&".join(
        f"{_form_encode_component(key)}={_form_encode_component(value)}" for key, value in pairs
    )


def local_asset_url_for_path(file_path: str, version: str = "") -> str:
    """``/__cad/asset?file=<abs>[&v=<token>]``.

    The client rewrites ONLY the ``file`` param (packageAssetUrl.js), so the
    shape must stay exactly this. ``v`` is omitted when it trims to empty.
    """
    import os

    pairs = [("file", os.path.abspath(str(file_path or "")))]
    normalized = str(version or "").strip()
    if normalized:
        pairs.append(("v", normalized))
    return f"/__cad/asset?{form_encode(pairs)}"


# --- strict decodeURIComponent -------------------------------------------

_HEX_DIGITS = frozenset(string.hexdigits)


def strict_decode_uri_component(value: str) -> str:
    """``decodeURIComponent`` including its throws.

    Percent escapes are decoded in RUNS and each run is validated as UTF-8, so
    a malformed escape, an overlong sequence (``%C0%AF``) and a lone surrogate
    (``%ED%A0%80``) all raise, exactly as the JS does. Literal characters pass
    through untouched.
    """
    out: list[str] = []
    index = 0
    length = len(value)
    while index < length:
        if value[index] != "%":
            out.append(value[index])
            index += 1
            continue
        buffer = bytearray()
        while index < length and value[index] == "%":
            pair = value[index + 1 : index + 3]
            if len(pair) != 2 or pair[0] not in _HEX_DIGITS or pair[1] not in _HEX_DIGITS:
                raise UriError("URI malformed")
            buffer.append(int(pair, 16))
            index += 3
        try:
            out.append(buffer.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise UriError("URI malformed") from exc
    return "".join(out)
