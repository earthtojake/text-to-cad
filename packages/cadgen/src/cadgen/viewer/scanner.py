"""The catalog row of one CAD file: what a view needs to render it (``catalog_entry``).

A row is ``{file, kind, url, hash, bytes, ...}``: ``file`` is the file's absolute path with ``/``
separators, ``url`` is where its bytes are served (``/__cad/asset?file=<abs>&v=<token>``, the token
``base36(size)-base36(mtime_ns)``; a STEP's is its tree in the store, ``/__cad/store?file=<tree>``),
``hash`` is sha256 hex and ``bytes`` the byte size. A view names its file, so a row is computed for
the file named and nothing walks a folder to find it.

The catalog is ARTIFACTS-ONLY. Model scripts are never entries: a model with no
artifact simply has no row until its script has been run, and artifact-to-source
linkage is assembly.json provenance rather than filenames. The catalog publishes
no provenance at all — never a ``sourceKind``, never a generator script name.

FIDELITY NOTES (each one is a place a "natural" Python spelling diverges)
------------------------------------------------------------------------
* ``file`` is spelled with ``/`` BY CONTRACT, on Windows too (``C:/models/part.step``):
  it is what the page puts back into a URL.
* ``path.extname`` is not ``os.path.splitext`` (see ``content_types``).
* JS ``\\s`` and ``\\w`` are not Python's, so ``_xml_root_name`` spells both
  character classes out.
* A ``kinematics: {}`` object is a declaration even though Python considers it
  falsey, so it still emits ``poseUrl``.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import stat as stat_module
import threading

from cadgen._internal.shared_read import open_shared_for_read

from .content_types import extension_of
from .encoding import encode_uri_component, file_version, local_asset_url_for_path
from .store_paths import (
    SOURCE_SIDECAR_NAMES,
    artifact_file_hash,
    artifact_path_key,
    cadgen_cache_root_dir,
    result_descriptor,
    result_snapshot,
    source_sidecar_path,
)

__all__ = [
    "CAD_CATALOG_SCHEMA_VERSION",
    "SOURCE_EXTENSIONS",
    "VIEWER_SKIPPED_DIRECTORIES",
    "asset_for_path",
    "catalog_entry",
    "catalog_input_fingerprint",
    "is_catalog_file",
    "is_hidden_name",
    "is_served_cad_asset",
    "node_basename",
    "read_step_catalog_metadata",
    "source_format_for_path",
    "step_kind_from_topology",
    "to_posix_path",
]

CAD_CATALOG_SCHEMA_VERSION = 4

SOURCE_EXTENSIONS = frozenset(
    {".step", ".stp", ".stl", ".3mf", ".glb", ".dxf", ".urdf", ".srdf", ".sdf"}
)

# The folders the explorer's search never walks (``folders.py``), beside every hidden one. Matched
# with EXACT case: ``Dist/`` and ``Build/`` are walked, only the lowercase spellings are skipped.
VIEWER_SKIPPED_DIRECTORIES = frozenset(
    {"__cadgen__", "__pycache__", "build", "coverage", "dist", "node_modules", "viewer"}
)

_STEP_PACKAGE_KIND = "assembly-package"


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
    return not is_hidden_name(name) and extension_of(name) in SOURCE_EXTENSIONS


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

# A STEP catalog row is derived from immutable geometry plus the document-bound
# sidecar, including its optional animation keyframes. Catalog
# refreshes still resolve the document digest to its current tree on every
# read; only the expensive flattened-tree validation and annotation shaping is
# reused when all of those inputs are unchanged. Misses build outside the lock;
# metadata capture has its own per-tree single-flight, and unrelated documents
# must remain independently readable while one large tree is verified. A miss
# already being built for the same inputs is waited for, not built twice: the
# catalog row a build's save warms (``warm.py``) and the catalog read that
# follows the build ask for the same row at once.
#
# A row whose tree could not be read is never kept. What failed is the store's
# state (an object of the tree missing or damaged), not an input of the key: a
# compile repairs it by restoring the same bytes at the same hashes, so the key
# would never move, and a kept row would list the document as unbuilt for as
# long as this process lives, however often the compile succeeded.
_STEP_ENTRY_CACHE: dict[tuple, dict] = {}
_STEP_ENTRY_CACHE_LIMIT = 4096
_STEP_ENTRY_CACHE_LOCK = threading.Lock()
_STEP_ENTRY_FLIGHTS: dict[tuple, threading.Event] = {}


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


def _stat_identity(file_path) -> tuple | None:
    value = _file_stats(file_path)
    if value is None:
        return None
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def catalog_input_fingerprint(source_path) -> tuple:
    """Cheap mutable inputs behind one catalog row, excluding STEP store state."""
    source_path = os.path.abspath(str(source_path))
    extension = extension_of(source_path)
    related = ()
    if extension in (".step", ".stp"):
        related = (
            _stat_identity(source_sidecar_path(source_path)),
        )
    elif extension == ".srdf":
        directory = os.path.dirname(source_path)
        try:
            names = sorted(name for name in os.listdir(directory) if extension_of(name) == ".urdf")
        except (OSError, ValueError):
            names = []
        related = tuple((name, _stat_identity(os.path.join(directory, name))) for name in names)
    return source_path, _stat_identity(source_path), related


def _store_asset_url(tree: str) -> str:
    """``/__cad/store?file=<tree>``.

    The tree hash stands where a directory used to: the client's
    ``resolvePackageAssetUrl`` appends ``/assembly.json`` and
    ``/components/<cid>.surf`` to this same ``file`` param, and the store route
    resolves both by hash. The value carries NO leading slash (the route strips
    them, but the catalog must not emit one). No ``?v=`` token: a tree is
    content-addressed, so its hash IS the version.
    """
    return f"/__cad/store?file={encode_uri_component(tree)}"


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


def _is_js_object(value) -> bool:
    """``typeof value === "object" && value``: arrays yes, ``null`` no."""
    return isinstance(value, (dict, list))


def step_kind_from_topology(topology) -> str:
    """``part`` or ``assembly`` for a catalog row: the TREE's answer, relayed.

    The flattened descriptor's ``entryKind`` is written by ``store.trees``
    from the tree itself (links or more than one own occurrence → assembly),
    the one definition every reporter shares. Nothing is inferred here from
    the descriptor's other fields — an ``assembly.root`` object says how the
    occurrences nest, not how many there are.
    """
    if not topology:
        return "part"
    index = topology.get("index") if _is_js_object(topology.get("index")) else topology
    if topology.get("entryKind") == "assembly" or (
        isinstance(index, dict) and index.get("entryKind") == "assembly"
    ):
        return "assembly"
    return "part"


def read_step_catalog_metadata(descriptor, source_path=None, *, document_hash=None) -> dict:
    """Catalog-facing facts from a document's flattened tree, or ``{}`` when
    there is no valid one.

    ``assembly.json`` is the flattened tree (``result_descriptor``). ``None``, a
    non-dict, or a ``kind`` that is not ``assembly-package`` all answer ``{}``
    — and that is what suppresses the articulation and its ``poseUrl`` even
    when the sidecar exists and declares kinematics.
    """
    if not descriptor or not isinstance(descriptor, dict):
        return {}
    if descriptor.get("kind") != _STEP_PACKAGE_KIND:
        return {}
    # Everything SOURCE-derived rides the model-side sidecar
    # (<name>.step.json); the store assembly.json is STEP-pure. The page never reads the
    # sidecar: the row carries what it MEANS, resolved here -- the articulation of its
    # kinematics, what its appearance resolves to per occurrence, its baked animation.
    #
    # A sidecar this build cannot read is no sidecar: the document renders with
    # no kinematics, no materials and no routine, and the viewer says nothing
    # about it. The migration is announced where it can be acted on -- the build
    # and the cad skill -- not beside a model that is on screen and correct.
    sidecar = None
    display = None
    articulation = None
    if source_path:
        from cadgen._internal.source_sidecar import (
            SidecarAppearanceError,
            SidecarBindingError,
            SidecarSchemaError,
            occurrence_display,
            read_source_sidecar,
        )
        from cadgen.articulation import step_articulation

        try:
            sidecar = read_source_sidecar(source_path, document_hash=document_hash)
            if isinstance(sidecar, dict):
                display = occurrence_display(descriptor, sidecar.get("appearance"))
                articulation = step_articulation(descriptor, sidecar.get("kinematics"))
        except (SidecarAppearanceError, SidecarBindingError, SidecarSchemaError, ValueError):
            sidecar = display = articulation = None
    entry_kind = descriptor.get("entryKind")
    appearance = sidecar.get("appearance") if isinstance(sidecar, dict) else None
    animation = sidecar.get("animation") if isinstance(sidecar, dict) else None
    result = {
        "topology": {
            "index": descriptor,
            "entryKind": str(entry_kind if entry_kind is not None else "").strip().lower(),
        },
        # Publish the validated artifact annotations with this geometry snapshot.
        # What produced the document is not a catalog fact.
        "hasSourceSidecar": sidecar is not None,
        "articulation": articulation,
        "animation": animation if isinstance(animation, dict) else None,
        "appearance": appearance if isinstance(appearance, dict) else None,
        "display": display,
    }
    return result


def _create_step_entry(source_path, extension) -> dict:
    snapshot = result_snapshot(source_path)
    if snapshot:
        document_hash, tree = snapshot
    else:
        # An unbuilt document still needs a digest for status/sidecar binding,
        # but there is no geometry selection it could be mixed with. The lookup
        # above has just read it into the digest memo, so this reads nothing.
        document_hash, tree = artifact_file_hash(source_path) or "", None
    sidecar_path = source_sidecar_path(source_path)
    sidecar_stat = _file_stats(sidecar_path)
    sidecar_identity = (
        sidecar_stat.st_dev,
        sidecar_stat.st_ino,
        sidecar_stat.st_size,
        sidecar_stat.st_mtime_ns,
        sidecar_stat.st_ctime_ns,
    ) if sidecar_stat is not None else None
    cache_key = (
        cadgen_cache_root_dir(),
        source_path,
        document_hash,
        tree,
        sidecar_identity,
    )
    with _STEP_ENTRY_CACHE_LOCK:
        cached = _STEP_ENTRY_CACHE.get(cache_key)
        flight = None if cached is not None else _STEP_ENTRY_FLIGHTS.get(cache_key)
        leading = cached is None and flight is None
        if leading:
            flight = _STEP_ENTRY_FLIGHTS[cache_key] = threading.Event()
    if cached is not None:
        return copy.deepcopy(cached)
    if not leading:
        flight.wait()
        with _STEP_ENTRY_CACHE_LOCK:
            cached = _STEP_ENTRY_CACHE.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)
        # The build before ours failed, or could not read the tree and kept nothing: build
        # it here, and let the error be this caller's.
        return _build_step_entry(source_path, extension, document_hash=document_hash, tree=tree)
    try:
        entry = _build_step_entry(source_path, extension, document_hash=document_hash, tree=tree)
        if entry["hash"] or not tree:
            # Kept: the tree was read whole, or the bytes have none (one published
            # for them changes ``tree``, and so the key). Never a tree it could not read.
            with _STEP_ENTRY_CACHE_LOCK:
                if len(_STEP_ENTRY_CACHE) >= _STEP_ENTRY_CACHE_LIMIT:
                    _STEP_ENTRY_CACHE.clear()
                _STEP_ENTRY_CACHE[cache_key] = copy.deepcopy(entry)
        return entry
    finally:
        with _STEP_ENTRY_CACHE_LOCK:
            _STEP_ENTRY_FLIGHTS.pop(cache_key, None)
        flight.set()


def _build_step_entry(source_path, extension, *, document_hash, tree) -> dict:
    descriptor = result_descriptor(tree) if tree else None
    metadata = read_step_catalog_metadata(
        descriptor, source_path, document_hash=document_hash
    )
    if not metadata:
        # No tree this row can stand on: none for these bytes, or one the capture could not
        # read whole (an object missing or damaged). Either way the row is an unbuilt
        # document's, as the artifact status says ("not compiled"): its URL names no tree.
        tree = None
    topology = metadata.get("topology")
    descriptor_body = json.dumps(descriptor) if metadata else ""
    articulation = metadata.get("articulation")
    entry = {
        "file": to_posix_path(source_path),
        "kind": step_kind_from_topology(topology),
        # The tree hash identifies the render; an unbuilt document still gets a
        # deterministic URL the store route answers 404 for.
        "url": _store_asset_url(tree or f"unbuilt-{artifact_path_key(source_path)}") + (
            f"&documentHash={document_hash}" if document_hash and tree else ""
        ),
        "hash": tree if metadata else "",
        "documentHash": document_hash,
        "bytes": len(descriptor_body.encode("utf-8")),
    }
    appearance = metadata.get("appearance")
    if appearance is not None:
        from cadgen._internal.source_sidecar import appearance_digest

        # Appearance participates in the composed scene identity only. The
        # immutable STEP tree/hash and component tessellation keys stay pure.
        entry["appearanceHash"] = appearance_digest(appearance)
        # What it resolves to, per assigned occurrence: the page joins it to the tree by id.
        entry["display"] = metadata.get("display") or {}
    if articulation is not None:
        # The articulation of the typed mates, inline: exactly what the page plays. Its URL
        # is the sidecar's mutable asset route, whose version token says when the
        # articulation was written again (the sidecar changes apart from the STEP bytes,
        # whose tree URL stays content-addressed).
        sidecar_path = source_sidecar_path(source_path)
        sidecar_asset = asset_for_path(sidecar_path) if metadata.get("hasSourceSidecar") else None
        entry["articulation"] = articulation
        entry["poseUrl"] = (sidecar_asset or {}).get("url") or local_asset_url_for_path(sidecar_path)
    animation = metadata.get("animation")
    if animation is not None:
        from cadgen._internal.source_sidecar import animation_digest, bends_a_tube

        # The baked keyframes, inline: the page plays them as they are.
        entry["animation"] = animation
        entry["animationHash"] = animation_digest(animation)
        if tree and document_hash and bends_a_tube(animation):
            # Where a view reads the bound skins its clips bend tubes with.
            from .tube_skins import tube_skins_url

            entry["tubeSkinsUrl"] = tube_skins_url(source_path, document_hash)
    return entry


def is_served_cad_asset(file_path) -> bool:
    """Whether the asset route may stream this path's bytes: a CAD file or its sidecar, never a
    hidden one.

    The hidden check is on the BASENAME only: a file is named by its absolute path, and a hidden
    folder on the way to it is no reason to refuse it.

    The sidecar test matches the FULL pair of suffixes, never
    ``SOURCE_SIDECAR_SUFFIX`` alone — that is ``.json``, and serving every JSON
    file would hand out configs, secrets and anything else that happens to be
    there. Animation is keyframe data in the document-bound JSON sidecar.
    """
    text = str(file_path or "")
    if is_hidden_name(node_basename(text)):
        return False
    lowered = text.lower()
    if any(lowered.endswith(name) for name in SOURCE_SIDECAR_NAMES):
        return True
    return extension_of(text) in SOURCE_EXTENSIONS


# --- the row --------------------------------------------------------------


def catalog_entry(file_path) -> dict | None:
    """The catalog row of the file at absolute ``file_path``, or ``None`` when it has none: not a
    regular CAD file, or one whose own name is hidden (``is_catalog_file``)."""
    source_path = os.path.abspath(str(file_path))
    if not is_catalog_file(source_path) or _file_stats(source_path) is None:
        return None
    extension = extension_of(source_path)
    if extension in (".step", ".stp"):
        return _create_step_entry(source_path, extension)
    return _create_single_asset_entry(source_path, extension)
