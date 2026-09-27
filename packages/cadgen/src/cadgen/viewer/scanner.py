"""CAD directory scanner — produces the raw viewer catalog.

A raw entry is ``{file, kind, url, hash, bytes, ...}``: ``file`` is
root-relative POSIX, ``url`` is repo-relative (``/seg/seg?v=<token>``) and gets
rewritten to the ``/__cad/asset?file=...`` form by the backend's absolutizer,
``hash`` is sha256 hex, ``bytes`` is the byte size, and the ``?v=`` token is
``base36(size)-base36(mtime_ns)``.

The catalog is ARTIFACTS-ONLY. Model scripts are never entries: a model with no
artifact simply does not appear until its script has been run, and
artifact-to-source linkage is assembly.json provenance rather than filenames. The
catalog publishes no provenance at all — never a ``sourceKind``, never a
generator script name.

FIDELITY NOTES (each one is a place a "natural" Python spelling diverges)
------------------------------------------------------------------------
* ``file`` refs are POSIX BY CONTRACT because they become URLs.
  ``os.path.join`` would spell them ``library\\part.step`` on Windows and never
  match.
* Directory symlinks are followed ON PURPOSE. ``Dirent.isDirectory()`` is false
  for a link, which is why link targets get an explicit follow-stat here too;
  loops terminate on a set of visited REAL directory paths, with the depth cap
  as the outer guard.
* Walk order is ``readdir`` sorted by JS string comparison, which is UTF-16
  CODE-UNIT order. Python's ``sorted`` is code-POINT order and the two disagree
  above U+E000, so names sort on their UTF-16-BE encoding. This leaks into the
  output: the catalog sort is stable and primary-strength collation produces a
  lot of ties, so tied entries keep their walk order.
* ``path.extname`` is not ``os.path.splitext`` (see ``content_types``).
* JS ``\\s`` and ``\\w`` are not Python's, so ``_xml_root_name`` spells both
  character classes out.
* A ``kinematics: {}`` object is a declaration even though Python considers it
  falsey, so it still emits ``poseUrl``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat as stat_module
import threading


from .content_types import extension_of
from .encoding import encode_uri_component, encode_url_path, file_version
from .natural_sort import sort_catalog_entries
from .store_paths import (
    SOURCE_SIDECAR_NAMES,
    artifact_path_key,
    cadgen_cache_root_dir,
    result_descriptor,
    result_snapshot,
    source_sidecar_path,
)

__all__ = [
    "CAD_CATALOG_SCHEMA_VERSION",
    "SCAN_MAX_DEPTH",
    "SOURCE_EXTENSIONS",
    "VIEWER_SKIPPED_DIRECTORIES",
    "asset_for_path",
    "catalog_input_fingerprint",
    "is_hidden_name",
    "is_served_cad_asset",
    "path_is_inside",
    "node_basename",
    "path_relative",
    "read_step_catalog_metadata",
    "real_path_or",
    "relative_path_stays_inside_root",
    "repo_relative_path",
    "scan_cad_directory",
    "sort_catalog_entries",
    "source_format_for_path",
    "step_kind_from_topology",
    "to_posix_path",
]

CAD_CATALOG_SCHEMA_VERSION = 4

SOURCE_EXTENSIONS = frozenset(
    {".step", ".stp", ".stl", ".3mf", ".glb", ".dxf", ".urdf", ".srdf", ".sdf"}
)

# Dot-prefixed (hidden) directories are skipped generically, so this set only
# needs the non-hidden names. Matched with EXACT case: ``Dist/`` and ``Build/``
# are scanned, only the lowercase spellings are skipped.
VIEWER_SKIPPED_DIRECTORIES = frozenset(
    {"__cadgen__", "__pycache__", "build", "coverage", "dist", "node_modules", "viewer"}
)

# Far beyond what a real layout reaches, and enough to stop a symlink-loop
# crash even if the visited-real-path tracking ever fails to see one.
SCAN_MAX_DEPTH = 64

_STEP_DESCRIPTOR_NAME = "assembly.json"
_STEP_PACKAGE_KIND = "assembly-package"


# --- path / ref helpers ---------------------------------------------------


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


def path_relative(from_path: str, to_path: str) -> str:
    """``path.relative(from, to)``.

    NOT ``os.path.relpath``, which answers ``"."`` for two equal paths where
    ``path.relative`` answers ``""``. That difference is load-bearing: the
    hidden-component check splits this result on the separator, and ``"."``
    would make the served root itself read as a hidden path.
    """
    try:
        relative = os.path.relpath(to_path, from_path)
    except ValueError:
        # Windows, different drives: path.relative gives back the absolute
        # target, which relative_path_stays_inside_root then refuses.
        return to_path
    return "" if relative == os.curdir else relative


def real_path_or(value: str) -> str:
    """``realpathSync`` that resolves as much as exists.

    A not-yet-created view directory under a symlinked parent still keys the
    way ``Path.resolve()`` does.
    """
    try:
        return os.path.realpath(value)
    except (OSError, ValueError):
        return value


def relative_path_stays_inside_root(relative_path: str) -> bool:
    return relative_path == "" or (
        relative_path != ".."
        and not relative_path.startswith(f"..{os.sep}")
        and not os.path.isabs(relative_path)
    )


def path_is_inside(file_path: str, root_path: str) -> bool:
    """Containment, with real paths used for ALIAS EQUALITY and never refusal.

    macOS's ``/var`` -> ``/private/var`` and a symlinked served root must both
    compare as inside, so a path is contained when EITHER its lexical or its
    resolved location stays inside the root. The lexical branch runs FIRST and
    collapses ``..`` before any link is followed, which is what still refuses
    ``root/lib/../../outside.step`` when ``lib`` is a symlink.

    Symlinked model directories are a feature — this repo's own dev layout is
    symlinks, and pointing a link at a shared parts library is a normal way to
    bring external content in. A link out of the served directory grants no
    reach the URL did not already grant: the viewer serves whatever absolute
    directory it was started on.
    """
    if relative_path_stays_inside_root(
        path_relative(os.path.abspath(root_path), os.path.abspath(file_path))
    ):
        return True
    return relative_path_stays_inside_root(
        path_relative(
            real_path_or(os.path.abspath(root_path)), real_path_or(os.path.abspath(file_path))
        )
    )


def repo_relative_path(repo_root, file_path) -> str:
    return to_posix_path(path_relative(os.path.abspath(repo_root), os.path.abspath(file_path)))


def is_hidden_name(name) -> bool:
    return str(name or "").startswith(".")


# --- file stats / hashing / urls ------------------------------------------


def _file_stats(file_path):
    """``statSync`` restricted to regular files; ``None`` on any failure."""
    try:
        result = os.stat(file_path)
    except (OSError, ValueError):
        return None
    return result if stat_module.S_ISREG(result.st_mode) else None


# sha256 memoised on (path, size, mtime_ns): the catalog is polled every 2s and
# re-hashing a multi-hundred-MB STEP per poll would put a full file read on the
# hot path. Same output as an uncached hash for any file the OS reports
# unchanged. Cleared wholesale on overflow, matching the JS.
_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_HASH_CACHE_LIMIT = 4096
_HASH_CACHE_LOCK = threading.Lock()

# A STEP catalog row is derived from immutable geometry plus the document-bound
# sidecar, including its optional embedded animation. Catalog
# refreshes still resolve the document digest to its current tree on every
# scan; only the expensive flattened-tree validation and annotation shaping is
# reused when all of those inputs are unchanged. Misses build outside the lock;
# metadata capture has its own per-tree single-flight, and unrelated documents
# must remain independently readable while one large tree is verified.
_STEP_ENTRY_CACHE: dict[tuple, dict] = {}
_STEP_ENTRY_CACHE_LIMIT = 4096
_STEP_ENTRY_CACHE_LOCK = threading.Lock()


def _sha256_file(file_path, stat_result=None) -> str:
    st = stat_result if stat_result is not None else _file_stats(file_path)
    key = (str(file_path), st.st_size, st.st_mtime_ns) if st is not None else None
    if key is not None:
        with _HASH_CACHE_LOCK:
            cached = _HASH_CACHE.get(key)
        if cached is not None:
            return cached
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
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


def asset_for_path(repo_root, file_path) -> dict | None:
    st = _file_stats(file_path)
    if st is None:
        return None
    version = file_version(st.st_size, st.st_mtime_ns)
    repo_path = repo_relative_path(repo_root, file_path)
    return {
        "url": f"{encode_url_path(repo_path)}?v={encode_uri_component(version)}",
        "hash": _sha256_file(file_path, st),
        "bytes": int(st.st_size),
    }


def _asset_url_for_path(repo_root, file_path) -> str:
    return encode_url_path(repo_relative_path(repo_root, file_path))


# --- classification -------------------------------------------------------


def source_format_for_path(source_path, extension=None) -> str:
    r"""``extension.toLowerCase().replace(/^\./, "")`` — ONE leading dot."""
    ext = (extension_of(source_path) if extension is None else extension).lower()
    return ext[1:] if ext.startswith(".") else ext


# --- directory scan -------------------------------------------------------


def _should_skip_directory(name: str) -> bool:
    return name in VIEWER_SKIPPED_DIRECTORIES or is_hidden_name(name)


def _walk_sort_key(name: str) -> bytes:
    """JS string ``<``: UTF-16 CODE-UNIT order.

    Big-endian so that byte order equals code-unit order; ``surrogatepass``
    because a lone surrogate must still encode.
    """
    return name.encode("utf-16-be", "surrogatepass")


def _node_decoded_name(name: str) -> str:
    """Match Node's directory-entry decoding.

    ``os.scandir`` hands back ``surrogateescape`` text for bytes that are not
    valid UTF-8, while Node decodes with U+FFFD replacement. Reproducing Node
    means such a name is mangled the same way here — and, exactly as in Node,
    the mangled name then fails to stat, so the entry lands with ``hash: ""``
    and ``bytes: 0``. Divergence would be worse than the shared limitation.
    """
    if name.isascii():
        return name
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return name.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    return name


def _collect_cad_source_files(root_path: str, result: list, visited=None, depth: int = 0) -> list:
    if depth > SCAN_MAX_DEPTH:
        return result
    try:
        real_root = os.path.realpath(root_path, strict=True)
    except (OSError, ValueError):
        return result
    if visited is None:
        visited = set()
    if real_root in visited:
        # An earlier-sorted alias of a directory therefore HIDES the real one.
        # That is the flip side of the loop guard, not a separate rule.
        return result
    visited.add(real_root)
    try:
        with os.scandir(root_path) as scan:
            # Node sorts the DECODED names, so decode first and sort on that.
            entries = sorted(
                ((_node_decoded_name(entry.name), entry) for entry in scan),
                key=lambda pair: _walk_sort_key(pair[0]),
            )
    except (OSError, ValueError):
        return result
    for name, entry in entries:
        entry_path = os.path.join(root_path, name)
        try:
            is_directory = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
            is_symlink = entry.is_symlink()
        except OSError:
            continue
        if is_symlink:
            try:
                target = os.stat(entry_path)
            except (OSError, ValueError):
                continue  # broken link
            is_directory = stat_module.S_ISDIR(target.st_mode)
            is_file = stat_module.S_ISREG(target.st_mode)
        if is_directory:
            if not _should_skip_directory(name):
                _collect_cad_source_files(entry_path, result, visited, depth + 1)
            continue
        if not is_file:
            continue
        if is_hidden_name(name):
            continue
        if extension_of(name) in SOURCE_EXTENSIONS:
            result.append(entry_path)
    return result


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
        with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
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


def _create_single_asset_entry(repo_root, root_path, source_path, extension) -> dict:
    kind = source_format_for_path(source_path, extension)
    asset = asset_for_path(repo_root, source_path)
    entry = {
        "file": repo_relative_path(root_path, source_path),
        "kind": kind,
        "url": (asset["url"] if asset else "") or _asset_url_for_path(repo_root, source_path),
        "hash": (asset["hash"] if asset else "") or "",
        "bytes": (asset["bytes"] if asset else 0) or 0,
    }
    if kind == "srdf":
        paired_urdf = _paired_urdf_path_for_srdf(source_path)
        if paired_urdf:
            urdf_asset = asset_for_path(repo_root, paired_urdf)
            if urdf_asset:
                # Key order is file, then the spread of the asset.
                entry["relations"] = {
                    "urdf": {"file": repo_relative_path(root_path, paired_urdf), **urdf_asset}
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


def _read_json(file_path):
    """``JSON.parse(readFileSync(...))`` with every failure folded to ``None``."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def read_step_catalog_metadata(descriptor, source_path=None, *, document_hash=None) -> dict:
    """Catalog-facing facts from a document's flattened tree, or ``{}`` when
    there is no valid one.

    ``assembly.json`` is the flattened tree (``result_descriptor``). ``None``, a
    non-dict, or a ``kind`` that is not ``assembly-package`` all answer ``{}``
    — and that is what suppresses ``sourceUrl``/``poseUrl`` even when the
    sidecar exists and declares kinematics.
    """
    if not descriptor or not isinstance(descriptor, dict):
        return {}
    if descriptor.get("kind") != _STEP_PACKAGE_KIND:
        return {}
    # Everything SOURCE-derived rides the model-side sidecar
    # (<name>.step.json); the store assembly.json is STEP-pure.
    #
    # A sidecar this build cannot read is no sidecar: the document renders with
    # no kinematics, no materials and no routine, and the viewer says nothing
    # about it. The migration is announced where it can be acted on -- the build
    # and the cad skill -- not beside a model that is on screen and correct.
    sidecar = None
    if source_path:
        from cadgen._internal.source_sidecar import (
            SidecarAppearanceError,
            SidecarBindingError,
            SidecarSchemaError,
            validate_appearance_targets,
            read_source_sidecar,
        )

        try:
            sidecar = read_source_sidecar(source_path, document_hash=document_hash)
            if isinstance(sidecar, dict) and sidecar.get("appearance") is not None:
                validate_appearance_targets(descriptor, sidecar["appearance"])
        except (SidecarAppearanceError, SidecarBindingError, SidecarSchemaError):
            sidecar = None
    entry_kind = descriptor.get("entryKind")
    kinematics = sidecar.get("kinematics") if isinstance(sidecar, dict) else None
    appearance = sidecar.get("appearance") if isinstance(sidecar, dict) else None
    result = {
        "topology": {
            "index": descriptor,
            "entryKind": str(entry_kind if entry_kind is not None else "").strip().lower(),
        },
        # Publish the validated artifact annotations with this geometry snapshot.
        # What produced the document is not a catalog fact.
        "hasSourceSidecar": sidecar is not None,
        "sourceSidecar": sidecar,
        "kinematics": kinematics if _is_js_object(kinematics) else None,
        "appearance": appearance if isinstance(appearance, dict) else None,
    }
    return result


def _create_step_entry(repo_root, root_path, source_path, extension) -> dict:
    snapshot = result_snapshot(source_path)
    if snapshot:
        document_hash, tree = snapshot
    else:
        # An unbuilt document still needs a digest for status/sidecar binding,
        # but there is no geometry selection it could be mixed with.
        document_hash, tree = _sha256_file(source_path), None
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
        os.path.abspath(str(repo_root)),
        root_path,
        source_path,
        document_hash,
        tree,
        sidecar_identity,
    )
    with _STEP_ENTRY_CACHE_LOCK:
        cached = _STEP_ENTRY_CACHE.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)
    entry = _build_step_entry(
        repo_root, root_path, source_path, extension,
        document_hash=document_hash, tree=tree,
    )
    with _STEP_ENTRY_CACHE_LOCK:
        cached = _STEP_ENTRY_CACHE.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)
        if len(_STEP_ENTRY_CACHE) >= _STEP_ENTRY_CACHE_LIMIT:
            _STEP_ENTRY_CACHE.clear()
        _STEP_ENTRY_CACHE[cache_key] = copy.deepcopy(entry)
    return entry


def _build_step_entry(
    repo_root, root_path, source_path, extension, *, document_hash, tree,
) -> dict:
    descriptor = result_descriptor(tree) if tree else None
    metadata = read_step_catalog_metadata(
        descriptor, source_path, document_hash=document_hash
    )
    topology = metadata.get("topology")
    descriptor_body = json.dumps(descriptor) if metadata else ""
    # An EMPTY `kinematics: {}` block still yields a poseUrl (JS truthiness);
    # Python's `or` would drop it, so the test is `is not None`.
    pose_block = metadata.get("kinematics")
    entry = {
        "file": repo_relative_path(root_path, source_path),
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
    if metadata.get("hasSourceSidecar"):
        # The model-side sidecar is mutable independently of the STEP bytes.
        # Its URL therefore carries the ordinary asset version while the STEP
        # tree URL remains content-addressed.
        sidecar_asset = asset_for_path(repo_root, source_sidecar_path(source_path))
        if sidecar_asset:
            entry["sourceUrl"] = sidecar_asset["url"]
        # The URL is a mutable file route. Publish the exact validated snapshot
        # read above so appearance and kinematics cannot observe a later write
        # under the same path/version token.
        entry["sourceSidecar"] = metadata["sourceSidecar"]
    appearance = metadata.get("appearance")
    if appearance is not None:
        from cadgen._internal.source_sidecar import appearance_digest

        # Appearance participates in the composed scene identity only. The
        # immutable STEP tree/hash and component tessellation keys stay pure.
        entry["appearanceHash"] = appearance_digest(appearance)
    if pose_block is not None:
        # Typed mates, the articulation mechanism the sidecar carries.
        entry["poseUrl"] = entry.get("sourceUrl") or _asset_url_for_path(
            repo_root, source_sidecar_path(source_path)
        )
    animation = (metadata.get("sourceSidecar") or {}).get("animation")
    if animation is not None:
        entry["animationHash"] = hashlib.sha256(
            json.dumps(animation, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    return entry


def is_served_cad_asset(file_path) -> bool:
    """Whether the asset routes may stream this path's bytes.

    The hidden check is on the BASENAME only, deliberately: hidden directory
    components below the served root are the backend's business (it knows the
    root), so this stays root-agnostic and a model root that itself lives under
    a hidden absolute path still serves.

    The sidecar test matches the FULL pair of suffixes, never
    ``SOURCE_SIDECAR_SUFFIX`` alone — that is ``.json``, and serving every JSON
    file under the root would hand out configs, secrets and anything else that
    happens to be there. JavaScript files are not model assets; animation
    source is embedded in the document-bound JSON sidecar.
    """
    text = str(file_path or "")
    if is_hidden_name(node_basename(text)):
        return False
    lowered = text.lower()
    if any(lowered.endswith(name) for name in SOURCE_SIDECAR_NAMES):
        return True
    return extension_of(text) in SOURCE_EXTENSIONS


# --- public scan API ------------------------------------------------------


def scan_cad_directory(repo_root, *, preferred_file=None, defer_unpreferred=False) -> dict:
    """Scan one directory. It is its own root — a viewer serves exactly one."""
    if not repo_root:
        raise ValueError("repoRoot is required")
    root_path = os.path.abspath(repo_root)
    source_files = _collect_cad_source_files(root_path, [])
    preferred_path = None
    if preferred_file:
        preferred_text = str(preferred_file).replace("\\", os.sep)
        preferred_path = os.path.abspath(
            preferred_text if os.path.isabs(preferred_text) else os.path.join(root_path, preferred_text)
        )
    entries = []
    for source_path in source_files:
        if defer_unpreferred and os.path.abspath(source_path) != preferred_path:
            entries.append({
                "file": repo_relative_path(root_path, source_path),
                "catalogPending": True,
            })
            continue
        extension = extension_of(source_path)
        if extension in (".step", ".stp"):
            entries.append(_create_step_entry(repo_root, root_path, source_path, extension))
        else:
            entries.append(
                _create_single_asset_entry(repo_root, root_path, source_path, extension)
            )
    return {
        "schemaVersion": CAD_CATALOG_SCHEMA_VERSION,
        "entries": sort_catalog_entries(entries),
    }
