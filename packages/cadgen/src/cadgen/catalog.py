from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .metadata import GeneratorMetadata, parse_generator_metadata

from ._internal.doors import STEP_SUFFIXES
from ._internal.shared_read import open_shared_for_read


@dataclass(frozen=True)
class CadSource:
    source_ref: str
    cad_ref: str
    source_path: Path
    source: str
    script_path: Path | None = None
    generator_metadata: GeneratorMetadata | None = None
    step_path: Path | None = None
    dxf_path: Path | None = None


def source_from_path(
    path: Path,
    *,
    function: str | None = None,
) -> CadSource | None:
    """The source behind ``path``: a model script (``function`` names one model of a
    file holding several; a file holding one needs no name) or a STEP document."""
    resolved = Path(path).expanduser().resolve()
    if resolved.suffix.lower() == ".py":
        return _read_python_source(resolved, function=function)
    if resolved.suffix.lower() in STEP_SUFFIXES:
        return _read_step_source(resolved)
    return None


def source_ref_from_path(path: Path) -> str:
    # Entry-identity string (sourceRef), relative to the live cwd. Has no assembly.json readers and
    # is consistent within a build; the persisted model-folder-relative paths come from elsewhere.
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        return resolved.as_posix()
    return relative.as_posix()


def cad_ref_from_step_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        relative = PurePosixPath(resolved.as_posix())
    if relative.suffix.lower() in STEP_SUFFIXES:
        return relative.with_suffix("").as_posix()
    raise ValueError(f"{_display_path(path)} is not a CAD STEP source")


def cad_ref_from_dxf_path(path: Path) -> str:
    # A drawing's ref KEEPS the `.dxf` suffix, so it never reads as a same-stem
    # model's STEP ref.
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        relative = PurePosixPath(resolved.as_posix())
    if relative.suffix.lower() != ".dxf":
        raise ValueError(f"{_display_path(path)} is not a CAD DXF output path")
    return relative.as_posix()


def artifact_path_key(entry_path: Path) -> str:
    """The model-path identity for progress records and unbuilt views:
    sha256 of the resolved artifact path, truncated. Path-keyed on purpose —
    a build's progress must be findable while the content hash it will produce
    is still unknown.

    A path that cannot be resolved (an embedded NUL, a symlink loop) keys on
    its lexical absolute form rather than raising: the viewer server derives
    this key for whatever a request names, and an odd path must be a "no
    package" answer there, not a 500."""
    import hashlib

    try:
        resolved = str(Path(entry_path).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        resolved = os.path.abspath(str(entry_path))
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:24]


# Content-hash cache for artifact files, keyed by the path and the file's
# version (`_file_version`): a catalog scan or status poll re-asks for the same
# file's hash constantly, and rereading megabytes each time would turn polling
# into IO. A version is the mtime and size, which a real editor's save moves,
# and the inode and ctime, which a save by rename (every build's) moves even
# where the mtime is coarse: HFS+, FAT, exFAT and some network shares keep it to
# a second or two, so a same-size save inside one tick keeps mtime and size.
#
# Bounded and locked: the viewer server shares this cache across request
# threads for the life of the process, and a large corpus would otherwise
# grow it without limit.
_ARTIFACT_HASH_MEMO: dict[str, tuple[tuple[int, ...], str]] = {}
_ARTIFACT_HASH_MEMO_LIMIT = 4096
_ARTIFACT_HASH_MEMO_LOCK = threading.Lock()
# One read per file version. A just-saved document is asked for by several readers at once --
# the CAD Viewer's catalog, its status routes, and the catalog row it warms as the save is
# announced -- and each would otherwise read every byte of it beside the others. A reader that
# finds the same file version already being read waits for that read's answer.
_ARTIFACT_HASH_FLIGHTS: dict[tuple, threading.Event] = {}
_ARTIFACT_HASH_CHUNK_BYTES = 16 << 20


def _remember_artifact_hash(key: str, version: tuple[int, ...], digest: str) -> None:
    with _ARTIFACT_HASH_MEMO_LOCK:
        if len(_ARTIFACT_HASH_MEMO) >= _ARTIFACT_HASH_MEMO_LIMIT:
            _ARTIFACT_HASH_MEMO.clear()
        _ARTIFACT_HASH_MEMO[key] = (version, digest)


def _file_version(stat: os.stat_result) -> tuple[int, ...]:
    """What the memo keys a file's version by (beside its path). Always of the path's stat, as
    the lookup takes it, never of a read handle's (``_held_version``)."""
    return stat.st_mtime_ns, stat.st_size, stat.st_ino, stat.st_ctime_ns


def _held_version(stat: os.stat_result) -> tuple[int, ...]:
    """What a read handle's stat (``os.fstat``) and its path's report alike of a file version:
    the file, its size, its mtime. Not its ctime: on Windows (Python 3.12+) a path's is the
    file's creation, kept there for compatibility, and a handle's its last change. They differ
    for any file changed a clock tick after it was made, which a save by rename over an earlier
    file always is: it takes on that file's creation time."""
    return stat.st_ino, stat.st_size, stat.st_mtime_ns


def _remembered_artifact_hash(key: str, stat: os.stat_result) -> str | None:
    """The digest remembered for this version of the file; the caller holds the memo's lock."""
    cached = _ARTIFACT_HASH_MEMO.get(key)
    return cached[1] if cached is not None and cached[0] == _file_version(stat) else None


def _read_artifact_hash(resolved: Path, key: str) -> str | None:
    """Hash the file's bytes. The digest is remembered under the version the path names once
    the read handle is open, and only when the handle holds that version and the path still
    names it once the read is done: a file replaced or rewritten during the read is read again
    by the next asker."""
    import hashlib

    digest = hashlib.sha256()
    try:
        with open_shared_for_read(resolved) as handle:
            held = os.fstat(handle.fileno())
            named = resolved.stat()
            # Each chunk is two waits for the GIL (after the read, after the update), and beside
            # a thread running Python each wait is a switch interval: 1 MiB chunks hashed a
            # 227 MB STEP in 2.8 s beside one busy thread (0.11 s alone), 16 MiB ones in 0.31 s.
            buffer = bytearray(min(_ARTIFACT_HASH_CHUNK_BYTES, max(held.st_size, 1 << 16)))
            view = memoryview(buffer)
            while count := handle.readinto(buffer):
                digest.update(view[:count])
        after = resolved.stat()
    except OSError:
        return None
    hexdigest = digest.hexdigest()
    version = _file_version(named)
    if _file_version(after) == version and _held_version(held) == _held_version(named):
        _remember_artifact_hash(key, version, hexdigest)
    return hexdigest


def artifact_file_hash(entry_path: Path) -> str | None:
    """sha256 of the artifact file's bytes, memoized; None when unreadable.

    Streamed in chunks of at most 16 MiB: a status poll must not materialize a
    multi-hundred-MB STEP in memory to learn its key. Opened with delete
    sharing, so a poll hashing the file never blocks the user deleting it
    on Windows. Concurrent askers of one file version share one read."""
    try:
        resolved = Path(entry_path).expanduser().resolve()
        stat = resolved.stat()
    except (OSError, ValueError, RuntimeError):
        return None
    key = str(resolved)
    flight_key = (key, *_file_version(stat))
    with _ARTIFACT_HASH_MEMO_LOCK:
        remembered = _remembered_artifact_hash(key, stat)
        if remembered is not None:
            return remembered
        flight = _ARTIFACT_HASH_FLIGHTS.get(flight_key)
        leading = flight is None
        if leading:
            flight = _ARTIFACT_HASH_FLIGHTS[flight_key] = threading.Event()
    if not leading:
        flight.wait()
        # The read before ours remembered its answer, unless the file moved on under it or was
        # unreadable: then this asker reads the file itself.
        with _ARTIFACT_HASH_MEMO_LOCK:
            remembered = _remembered_artifact_hash(key, stat)
        return remembered if remembered is not None else _read_artifact_hash(resolved, key)
    try:
        return _read_artifact_hash(resolved, key)
    finally:
        with _ARTIFACT_HASH_MEMO_LOCK:
            _ARTIFACT_HASH_FLIGHTS.pop(flight_key, None)
        flight.set()


def seed_artifact_hash(entry_path: Path, digest: str) -> None:
    """Prime the content-hash cache for a file the caller JUST wrote and
    hashed (generation's export). Saves the full-file re-read the first
    post-build resolution would otherwise pay — linear in document size."""
    resolved = Path(entry_path).expanduser().resolve()
    try:
        stat = resolved.stat()
    except OSError:
        return
    _remember_artifact_hash(str(resolved), _file_version(stat), digest)


def result_snapshot_for(entry_path: Path) -> tuple[str, str] | None:
    """One coherent (document digest, tree) lookup from the same consumed hash."""
    from cadgen.store.objects import has_object
    from cadgen.store.records import tree_for_document_hash

    digest = artifact_file_hash(Path(entry_path))
    if not digest:
        return None
    tree = tree_for_document_hash(digest)
    return (digest, tree) if tree and has_object(tree) else None


def result_tree_for(entry_path: Path) -> str | None:
    """The tree behind a CAD artifact on disk, or None — found by the file's BYTES.

    ``index/document/<sha256(bytes)>-v<schema>`` → tree (STORE.md §2, the law): a reader
    never opens a record to find an artifact. The same file copied anywhere
    resolves to the same tree; a file the store has no tree for answers None
    (a door then compiles it: ``cadgen._internal.doors.document_tree``). The
    hash is memoized by (path, mtime_ns, size), so a status poll does not
    re-read the file. The tree's flattened view (``cadgen.store.trees.flatten``)
    is what every reader that used to open a view directory reads now."""
    snapshot = result_snapshot_for(entry_path)
    return snapshot[1] if snapshot else None


def result_descriptor_for(entry_path: Path) -> dict | None:
    """The flattened tree (assembly.json; component refs as object hashes)
    behind a CAD artifact on disk, or None when it has no current tree."""
    from cadgen.store.trees import capture_tree

    tree = result_tree_for(entry_path)
    if tree is None:
        return None
    try:
        descriptor, _ = capture_tree(tree, retain_payloads=False)
        return descriptor
    except (OSError, ValueError):
        return None


def result_view_dir(entry_path: Path) -> Path:
    """A view directory (assembly.json + components/, a per-process temporary directory) of the tree
    behind a CAD artifact, for consumers that need files on disk — the
    selector-index composer, the snapshot page. When the artifact
    has no current tree, a deterministic never-created path, so existence checks
    answer "no result" without special cases. The store itself holds no result
    directories (``cadgen.store.view``)."""
    from cadgen.store.view import view_dir_for, views_root

    snapshot = result_snapshot_for(entry_path)
    if snapshot is None:
        return views_root() / f"unbuilt-{artifact_path_key(entry_path)}"
    return view_dir_for(snapshot[1], document_hash=snapshot[0])


def build_scope(entry_path: Path) -> str:
    """The progress scope for builds of this model: a path-keyed NAME (never a
    directory). ``cadgen.coordination.paths`` derives the advisory progress
    record from it; the CAD Viewer derives the same name to find that record."""
    return artifact_path_key(entry_path)


def _model_source_ref(script_path: Path, metadata: GeneratorMetadata) -> str:
    """The entry identity string: the script, plus ``::fn`` when it holds several models."""
    from cadgen.metadata import model_function_names

    base = source_ref_from_path(script_path)
    if metadata.entry_function and len(model_function_names(script_path)) > 1:
        return f"{base}::{metadata.entry_function}"
    return base


def _dxf_generator_source(resolved_script_path: Path, metadata: GeneratorMetadata) -> CadSource:
    from cadgen.metadata import resolve_model_output_path

    dxf_path = resolve_model_output_path(
        resolved_script_path, fmt="dxf", explicit_out=metadata.out_target, function=metadata.entry_function
    )
    return CadSource(
        source_ref=_model_source_ref(resolved_script_path, metadata),
        cad_ref=cad_ref_from_dxf_path(dxf_path),
        source_path=resolved_script_path,
        source="generated",
        script_path=resolved_script_path,
        generator_metadata=metadata,
        step_path=None,
        dxf_path=dxf_path,
    )


def _read_python_source(script_path: Path, *, function: str | None = None) -> CadSource | None:
    resolved_script_path = script_path.resolve()
    metadata = parse_generator_metadata(resolved_script_path, function)
    if metadata is None:
        return None
    if metadata.format == "dxf":
        return _dxf_generator_source(resolved_script_path, metadata)
    from cadgen.metadata import resolve_model_output_path

    step_path = resolve_model_output_path(
        resolved_script_path, fmt="step", explicit_out=metadata.out_target, function=metadata.entry_function
    )
    return CadSource(
        source_ref=_model_source_ref(resolved_script_path, metadata),
        cad_ref=cad_ref_from_step_path(step_path),
        source_path=resolved_script_path,
        source="generated",
        script_path=resolved_script_path,
        generator_metadata=metadata,
        step_path=step_path,
        dxf_path=None,
    )


def _read_step_source(step_path: Path) -> CadSource:
    resolved_step_path = step_path.resolve()
    if not resolved_step_path.is_file():
        raise ValueError(
            f"{_display_path(resolved_step_path)} source does not exist"
        )
    cad_ref = cad_ref_from_step_path(resolved_step_path)

    return CadSource(
        source_ref=source_ref_from_path(resolved_step_path),
        cad_ref=cad_ref,
        source_path=resolved_step_path,
        source="imported",
        step_path=resolved_step_path,
    )


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()
