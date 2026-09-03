"""WHATWG request-target parsing, because ``urlsplit`` is not it.

The Node backend routes on ``new URL(req.url, "http://localhost").pathname``,
which normalises dot segments, converts backslashes to slashes, discards an
authority and re-percent-encodes part of ASCII. ``urllib.parse.urlsplit`` does
none of that, so routing on ``urlsplit().path`` would send
``/__cad/../etc/passwd`` into the ``/__cad/`` API dispatch instead of the SPA,
and would miss ``/__cad\\asset`` entirely. Every behaviour below is pinned by
``tests_server/golden/golden.json``.

Byte handling: ``BaseHTTPRequestHandler`` hands us a request line decoded as
latin-1, so each character stands for one byte. ``target_from_request_line``
turns that back into text; the encoders here then work on real characters and
percent-encode their UTF-8 bytes, which is what Node does.
"""

from __future__ import annotations

import re
from typing import Sequence
from urllib.parse import parse_qsl

__all__ = ["Query", "request_pathname", "request_query", "target_from_request_line"]

_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")

# Derived empirically from Node (see golden.json's pathPercentEncodeSet): the
# printable characters the path percent-encode set escapes. "#" and "?" are not
# here because they terminate the path, and "\" is not here because it has
# already become "/". Note "|" is NOT escaped.
_PATH_ESCAPED = frozenset(' "<>^`{}')


def target_from_request_line(raw: str) -> str:
    """Undo ``BaseHTTPRequestHandler``'s latin-1 decode of the request target."""
    return raw.encode("iso-8859-1", "surrogateescape").decode("utf-8", "surrogateescape")


def _strip_fragment_and_query(target: str) -> tuple[str, str]:
    """Return ``(path_part, query_part)``.

    The fragment is cut FIRST, at the first ``#``: in ``/a#b?c`` the ``?`` lives
    inside the fragment and is not a query.
    """
    head = target.split("#", 1)[0]
    path_part, _, query_part = head.partition("?")
    return path_part, query_part


def _strip_authority(path: str) -> str:
    """Drop a scheme and/or authority, leaving the path.

    ``//evil.example/__cad/server`` and ``http://evil.example/__cad/server`` both
    route as ``/__cad/server``: the Host HEADER is the only host that matters,
    and the host gate is what checks it.
    """
    match = _SCHEME_RE.match(path)
    if match:
        rest = path[match.end() :]
        if rest[:1] in ("/", "\\"):
            index = 0
            while index < len(rest) and rest[index] in "/\\":
                index += 1
            return _authority_tail(rest[index:])
        return rest
    if path[:1] == "/" and path[1:2] in ("/", "\\"):
        index = 0
        while index < len(path) and path[index] in "/\\":
            index += 1
        return _authority_tail(path[index:])
    return path


def _authority_tail(rest: str) -> str:
    for index, char in enumerate(rest):
        if char in "/\\":
            return rest[index:]
    return ""


def _is_single_dot(segment: str) -> bool:
    return segment == "." or segment.lower() == "%2e"


def _is_double_dot(segment: str) -> bool:
    return segment == ".." or segment.lower() in (".%2e", "%2e.", "%2e%2e")


def _remove_dot_segments(path: str) -> str:
    segments = path.split("/")
    out: list[str] = []
    last = len(segments) - 1
    for index, segment in enumerate(segments[1:], start=1):
        if _is_double_dot(segment):
            if out:
                out.pop()
            if index == last:
                out.append("")
        elif _is_single_dot(segment):
            if index == last:
                out.append("")
        else:
            out.append(segment)
    return "/" + "/".join(out)


def _percent_encode_path(path: str) -> str:
    out: list[str] = []
    for char in path:
        if char in _PATH_ESCAPED or ord(char) < 0x20 or ord(char) > 0x7E:
            for byte in char.encode("utf-8", "surrogateescape"):
                out.append(f"%{byte:02X}")
        else:
            out.append(char)
    return "".join(out)


def request_pathname(target: str) -> str:
    """``new URL(target, "http://localhost").pathname``."""
    path_part, _ = _strip_fragment_and_query(str(target or ""))
    path_part = path_part.replace("\\", "/")
    path_part = _strip_authority(path_part)
    if not path_part.startswith("/"):
        path_part = "/" + path_part
    return _percent_encode_path(_remove_dot_segments(path_part))


class Query:
    """``URLSearchParams``: split on ``&`` only, ``+`` is a space, first wins.

    Blank values are KEPT — ``?file=&v=1&file=z`` must answer ``""`` for
    ``file``, not ``"z"``.
    """

    __slots__ = ("_pairs",)

    def __init__(self, pairs: Sequence[tuple[str, str]]) -> None:
        self._pairs = list(pairs)

    def get(self, key: str, default: str | None = None) -> str | None:
        for name, value in self._pairs:
            if name == key:
                return value
        return default

    def get_all(self, key: str) -> list[str]:
        return [value for name, value in self._pairs if name == key]

    def __contains__(self, key: object) -> bool:
        return any(name == key for name, _ in self._pairs)

    def __iter__(self):
        return iter(self._pairs)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Query({self._pairs!r})"


def request_query(target: str) -> Query:
    _, query_part = _strip_fragment_and_query(str(target or ""))
    if not query_part:
        return Query([])
    return Query(parse_qsl(query_part, keep_blank_values=True, separator="&"))
