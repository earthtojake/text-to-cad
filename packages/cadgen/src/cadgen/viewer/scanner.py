"""The catalog row of one CAD file: what a view needs to render it (``catalog_entry``).

A row is ``{file, kind, url, hash, bytes, ...}``: ``file`` is the file's absolute path with ``/``
separators, ``url`` is where its bytes are served (``/__cad/asset?file=<abs>&v=<token>``, the token
``base36(size)-base36(mtime_ns)``), ``hash`` is sha256 hex and ``bytes`` the byte size. A view names
its file, so a row is computed for the file named and nothing walks a folder to find it. Every
format's row is the file's own: a STEP and an ``.xbf`` are drawn from what the cadgen engine serves
of them (``documents.py``), never from a row, so theirs say only that the file is there and which bytes
it has, which is what a view watches for a change.

The catalog is ARTIFACTS-ONLY. Model scripts are never entries: a model with no
artifact simply has no row until its script has been run. The catalog publishes
no provenance at all — never a ``sourceKind``, never a generator script name.

FIDELITY NOTES (each one is a place a "natural" Python spelling diverges)
------------------------------------------------------------------------
* ``file`` is spelled with ``/`` BY CONTRACT, on Windows too (``C:/models/part.step``):
  it is what the page puts back into a URL.
* ``path.extname`` is not ``os.path.splitext`` (see ``content_types``).
* JS ``\\s`` and ``\\w`` are not Python's, so ``_xml_root_name`` spells both
  character classes out.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat as stat_module
import threading

from cadgen._internal.shared_read import open_shared_for_read

from .content_types import extension_of
from .encoding import file_version, local_asset_url_for_path

__all__ = [
    "CAD_CATALOG_SCHEMA_VERSION",
    "SOURCE_EXTENSIONS",
    "VIEWER_EXTENSIONS",
    "VIEWER_SKIPPED_DIRECTORIES",
    "asset_for_path",
    "catalog_entry",
    "is_catalog_file",
    "is_hidden_name",
    "is_served_cad_asset",
    "node_basename",
    "source_format_for_path",
    "to_posix_path",
]

# 5: a STEP's row is its file's, as every format's is (the engine draws it), no longer its tree's.
CAD_CATALOG_SCHEMA_VERSION = 5

# The CAD files whose bytes the asset route sends.
SOURCE_EXTENSIONS = frozenset(
    {".step", ".stp", ".stl", ".3mf", ".glb", ".dxf", ".urdf", ".srdf", ".sdf"}
)
# What every CAD view lists and opens: every CAD source, and a cadgen engine document (`.xbf`),
# which the engine serves to the page as it serves a STEP (`documents.py`).
VIEWER_EXTENSIONS = SOURCE_EXTENSIONS | frozenset({".xbf"})

# The folders the explorer's search never walks (``folders.py``), beside every hidden one. Matched
# with EXACT case: ``Dist/`` and ``Build/`` are walked, only the lowercase spellings are skipped.
VIEWER_SKIPPED_DIRECTORIES = frozenset(
    {"__cadgen__", "__pycache__", "build", "coverage", "dist", "node_modules", "viewer"}
)

# --- path helpers ---------------------------------------------------------


def to_posix_path(value) -> str:
    return str(value or "").replace(os.sep, "/")


# Node treats only "/" as a separator on POSIX, and both "\\" and "/" on win32.
_SEPARATORS = "\\/" if os.name == "nt" else "/"


def node_basename(value: str) -> str:
    """``path.basename``: trailing separators are stripped first.

    ``os.path.basename`` answers ``""`` for ``"/a/b/"`` where Node answers
    ``"b"``, and on POSIX a literal backslash is an ordinary filename
    character — normalising it here would let ``.secret\\x.step`` pass the
    hidden-name gate.
    """
    stripped = value.rstrip(_SEPARATORS)
    if not stripped:
        return ""
    for index in range(len(stripped) - 1, -1, -1):
        if stripped[index] in _SEPARATORS:
            return stripped[index + 1 :]
    return stripped


def is_hidden_name(name) -> bool:
    return str(name or "").startswith(".")


def is_catalog_file(file_path) -> bool:
    """Whether ``file_path`` can have a catalog row: a CAD file whose own name is not hidden.

    Only the file's own name: a file under a hidden folder is named, never found, and has its row.
    """
    name = node_basename(str(file_path or ""))
    return not is_hidden_name(name) and extension_of(name) in VIEWER_EXTENSIONS


# --- file stats / hashing / urls ------------------------------------------


def _file_stats(file_path):
    """``statSync`` restricted to regular files; ``None`` on any failure."""
    try:
        result = os.stat(file_path)
    except (OSError, ValueError):
        return None
    return result if stat_module.S_ISREG(result.st_mode) else None


# sha256 memoised on (path, size, mtime_ns): a view re-reads its file's row on every change it
# hears of, and re-hashing a multi-hundred-MB STEP each time would put a full file read on the
# hot path. Same output as an uncached hash for any file the OS reports unchanged. Cleared
# wholesale on overflow, matching the JS.
_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_HASH_CACHE_LIMIT = 4096
_HASH_CACHE_LOCK = threading.Lock()


def _sha256_file(file_path, stat_result=None) -> str:
    """The file's sha256, or ``""`` when it vanished (or became unreadable) mid-read.

    Opened with delete sharing: a user deleting the model meanwhile must win, on Windows too. A
    file gone by the time it is opened simply has no hash this read; the next read has no row.
    """
    st = stat_result if stat_result is not None else _file_stats(file_path)
    key = (str(file_path), st.st_size, st.st_mtime_ns) if st is not None else None
    if key is not None:
        with _HASH_CACHE_LOCK:
            cached = _HASH_CACHE.get(key)
        if cached is not None:
            return cached
    digest = hashlib.sha256()
    try:
        with open_shared_for_read(file_path) as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return ""
    hexdigest = digest.hexdigest()
    if key is not None:
        with _HASH_CACHE_LOCK:
            if len(_HASH_CACHE) >= _HASH_CACHE_LIMIT:
                _HASH_CACHE.clear()
            _HASH_CACHE[key] = hexdigest
    return hexdigest


def asset_for_path(file_path) -> dict | None:
    """``{url, hash, bytes}`` of the file at absolute ``file_path``, or ``None`` when it is not a file."""
    st = _file_stats(file_path)
    if st is None:
        return None
    return {
        "url": local_asset_url_for_path(file_path, file_version(st.st_size, st.st_mtime_ns)),
        "hash": _sha256_file(file_path, st),
        "bytes": int(st.st_size),
    }


# --- classification -------------------------------------------------------


def source_format_for_path(source_path, extension=None) -> str:
    r"""``extension.toLowerCase().replace(/^\./, "")`` — ONE leading dot."""
    ext = (extension_of(source_path) if extension is None else extension).lower()
    return ext[1:] if ext.startswith(".") else ext


# --- URDF/SRDF pairing ----------------------------------------------------

# JS \s, spelled out: Python's differs (it includes U+001C-U+001F and U+0085,
# and excludes U+FEFF).
_JS_SPACE = "\t\n\x0b\x0c\r                  　﻿"
# JS \w is ASCII-only; Python's re \w is Unicode-aware.
_TAG_RE = re.compile(r'^<([A-Za-z_][A-Za-z0-9_.:\-]*)((?:"[^"]*"|\'[^\']*\'|[^>"\'])*)>')
_NAME_ATTR_RE = re.compile(
    rf'(?:^|[{re.escape(_JS_SPACE)}])name[{re.escape(_JS_SPACE)}]*=[{re.escape(_JS_SPACE)}]*'
    r'("([^"]*)"|\'([^\']*)\')'
)


def _xml_root_name(file_path, expected_tag: str = "robot") -> str | None:
    """The root element's ``name`` attribute, when the root tag matches.

    A minimal prolog scan, not a parser — URDF/SRDF pairing only needs the
    first start tag. Read with REPLACEMENT, never strict: Node's
    ``readFileSync(p, "utf8")`` does not throw on invalid bytes, and an SRDF and
    URDF carrying the same mojibake still pair.
    """
    try:
        with io.TextIOWrapper(
            open_shared_for_read(file_path), encoding="utf-8", errors="replace"
        ) as handle:
            text = handle.read()
    except (OSError, ValueError):
        return None
    index = 1 if text[:1] == "﻿" else 0
    length = len(text)
    while True:
        while index < length and text[index] in _JS_SPACE:
            index += 1
        if index >= length or text[index] != "<":
            return None
        if text.startswith("<?", index):
            end = text.find("?>", index)
            if end == -1:
                return None
            index = end + 2
            continue
        if text.startswith("<!--", index):
            end = text.find("-->", index)
            if end == -1:
                return None
            index = end + 3
            continue
        if text.startswith("<!", index):
            end = text.find(">", index)
            if end == -1:
                return None
            index = end + 1
            continue
        break
    match = _TAG_RE.match(text[index:])
    if match is None or match.group(1) != expected_tag:
        return None
    attr = _NAME_ATTR_RE.search(match.group(2))
    if attr is None:
        # A <robot> with no name attribute yields "", which is falsy and blocks
        # pairing — distinct from None, which means "not a <robot> at all".
        return ""
    return str(attr.group(2) if attr.group(2) is not None else attr.group(3) or "").strip()


def _paired_urdf_path_for_srdf(source_path: str) -> str | None:
    """The same-directory URDF whose root ``<robot name>`` matches.

    Ambiguity — zero matches or two — yields NO pairing at all rather than a
    guess.
    """
    robot_name = _xml_root_name(source_path)
    if not robot_name:
        return None
    directory = os.path.dirname(source_path)
    try:
        names = sorted(
            name for name in os.listdir(directory) if extension_of(name) == ".urdf"
        )
    except (OSError, ValueError):
        return None
    matches = [
        candidate
        for candidate in (os.path.join(directory, name) for name in names)
        if _xml_root_name(candidate) == robot_name
    ]
    if len(matches) != 1:
        return None
    return matches[0] if _file_stats(matches[0]) is not None else None


# --- entry builders -------------------------------------------------------


def _create_single_asset_entry(source_path, extension) -> dict:
    kind = source_format_for_path(source_path, extension)
    asset = asset_for_path(source_path)
    entry = {
        "file": to_posix_path(source_path),
        "kind": kind,
        "url": (asset["url"] if asset else "") or local_asset_url_for_path(source_path),
        "hash": (asset["hash"] if asset else "") or "",
        "bytes": (asset["bytes"] if asset else 0) or 0,
    }
    if kind == "srdf":
        paired_urdf = _paired_urdf_path_for_srdf(source_path)
        if paired_urdf:
            urdf_asset = asset_for_path(paired_urdf)
            if urdf_asset:
                # Key order is file, then the spread of the asset.
                entry["relations"] = {
                    "urdf": {"file": to_posix_path(paired_urdf), **urdf_asset}
                }
    return entry


def is_served_cad_asset(file_path) -> bool:
    """Whether the asset route may stream this path's bytes: a CAD file, never a hidden one, and
    nothing else -- never a ``.json``, a config or a key file beside it.

    The hidden check is on the BASENAME only: a file is named by its absolute path, and a hidden
    folder on the way to it is no reason to refuse it.
    """
    text = str(file_path or "")
    if is_hidden_name(node_basename(text)):
        return False
    return extension_of(text) in SOURCE_EXTENSIONS


# --- the row --------------------------------------------------------------


def catalog_entry(file_path) -> dict | None:
    """The catalog row of the file at absolute ``file_path``, or ``None`` when it has none: not a
    regular CAD file, or one whose own name is hidden (``is_catalog_file``)."""
    source_path = os.path.abspath(str(file_path))
    if not is_catalog_file(source_path) or _file_stats(source_path) is None:
        return None
    return _create_single_asset_entry(source_path, extension_of(source_path))
