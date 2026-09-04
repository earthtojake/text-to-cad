from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cadgen._internal.assembly_spec import find_step_path, resolve_cad_source_path
from cadgen.cad_ref_syntax import normalize_cad_path, parse_cad_tokens
from cadgen.catalog import find_source_by_cad_ref
from cadgen.selector_types import SelectorBundle


STEP_SUFFIXES = (".step", ".stp")


class CadRefError(RuntimeError):
    pass


@dataclass(frozen=True)
class EntryTarget:
    cad_path: str
    selectors: tuple[str, ...] = ()

    @property
    def token(self) -> str:
        from cadgen.cad_ref_syntax import build_cad_token

        if not self.selectors:
            return build_cad_token(self.cad_path)
        return build_cad_token(self.cad_path, ",".join(self.selectors))


@dataclass(frozen=True)
class ResolvedStepTarget:
    cad_path: str
    source_path: Path
    step_path: Path
    # True when the caller explicitly targeted the Python generator (a `.py`
    # path), as opposed to a `.step`/`.stp` file or a logical cad path. An
    # explicit generator target must keep resolving to the generator entry even
    # when a same-stem exported `.step` file exists beside it.
    explicit_python: bool = False


@dataclass(frozen=True)
class StepTopologyArtifact:
    cad_path: str
    source_path: Path
    step_path: Path
    artifact_path: Path
    manifest: dict[str, object]
    selector_bundle: SelectorBundle | None = None

    @property
    def kind(self) -> str:
        """``part`` or ``assembly``, read off the tree's ``entryKind`` — the one
        place kind is decided (``store.trees.tree_kind``)."""
        value = str(self.manifest.get("entryKind") or "").strip().lower()
        return value if value in {"part", "assembly"} else "part"


class StepTopologyArtifactError(CadRefError):
    """A door could not produce or read the tree behind a document.

    A door never refuses a document and never tells the user to run anything:
    when the compile of the document's bytes fails, ``message`` is that
    compile's own error, and that is the whole report.
    """

    def __init__(
        self,
        *,
        code: str,
        message: str,
        cad_path: str,
        step_path: Path,
        artifact_path: Path,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.cad_path = cad_path
        self.step_path = step_path
        self.artifact_path = artifact_path

    def to_error(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "cadPath": self.cad_path,
            "stepPath": _display_path(self.step_path),
        }


def cad_ref_error_payload(exc: CadRefError) -> dict[str, object]:
    if isinstance(exc, StepTopologyArtifactError):
        return exc.to_error()
    return {"message": str(exc)}


def cad_path_from_target(target: str) -> str:
    return entry_target_from_target(target).cad_path


def entry_target_from_target(target: str) -> EntryTarget:
    parsed_tokens = parse_cad_tokens(target)
    if parsed_tokens:
        raise CadRefError("Selector refs require an explicit STEP target argument.")
    raw_target = str(target or "").strip()
    raw_file = _raw_step_path(raw_target)
    identity = _path_identity(raw_file) if raw_file is not None else _target_identity(raw_target)
    normalized = normalize_cad_path(identity)
    if normalized is None:
        raise CadRefError(f"Invalid CAD entry target: {target}")
    return EntryTarget(normalized)


def _is_path_shaped(raw_target: str) -> bool:
    """Does this target name a filesystem location rather than a logical cad path?

    Rooted, ``~``-spelled, or reaching upward. Everything else is already a
    cwd-relative cad path and is left ALONE: resolving it would rewrite the
    identity of any target that crosses a symlink, and this repo's development
    layout is built out of symlinks.

    ROOTED, not ``is_absolute()``. On Windows a path with a root and no drive
    ("/models/x") is drive-RELATIVE, so ``is_absolute()`` is False; ``resolve()``
    anchors it to the current drive, which is what it means there.
    """
    if not raw_target:
        return False
    if raw_target.startswith("~"):
        return True
    path = Path(raw_target)
    if path.is_absolute() or path.root or path.drive:
        return True
    return ".." in raw_target.replace("\\", "/").split("/")


def _native_path(raw_target: str) -> Path:
    """A target resolved the way every other cadgen path argument resolves.

    Relative against the process cwd, absolute anywhere, ``~`` expanded. Nothing
    is gated on where it lands: identity is a separate question, answered by
    :func:`_path_identity`.
    """
    return Path(raw_target).expanduser().resolve()


def _path_identity(path: Path) -> str:
    """The cadPath identity a resolved file reports itself under.

    The established fallback: relative when the file is inside the cwd — a report
    then reads as the workspace-relative path the caller typed — else its own
    parent is the reference root, which leaves the bare name. Same rule as
    ``snapshot_cli.reference_root_for_input`` (cwd when the input is inside it,
    else the input's parent) composed with
    ``step_topology_artifact._relative_to_base`` (relative under the root,
    else absolute).

    A bare name is a legal cad-path token; a path rooted somewhere else is not,
    which is why the token grammar (no '/', no '..') still describes LOGICAL
    names and is never asked to describe a foreign file's location.
    """
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.name


def _target_identity(raw_target: str) -> str:
    if not _is_path_shaped(raw_target):
        return raw_target
    return _path_identity(Path(raw_target))


def _names_a_foreign_path(raw_target: str) -> bool:
    """A path-shaped target that resolves OUTSIDE the cwd.

    Such a target names exactly one file and there is no cad-path namespace
    behind it: its identity is a bare name, and this workspace's catalog only
    ever scans the cwd, so consulting it could only ever match an unrelated
    same-named entry. Resolution for these goes straight to the filesystem.
    """
    if not _is_path_shaped(raw_target):
        return False
    resolved = _native_path(raw_target)
    try:
        resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        return True
    return False


def _path_target_document(raw_target: str) -> Path | None:
    """The STEP document a path-shaped target names, wherever it lives.

    The path itself when it carries a document suffix, else the document beside
    the stem it names (a generator suffix is stripped first, so ``/x/foo.py``
    asks about ``/x/foo.step`` exactly as the logical ``foo`` does). Unlike
    :func:`_direct_step_path` this is anchored to the target, not to the cwd,
    which is what lets an absolute target work from anywhere.
    """
    resolved = _native_path(raw_target)
    if resolved.suffix.lower() in STEP_SUFFIXES:
        return resolved if resolved.is_file() else None
    stem = resolved
    name = resolved.name
    for suffix in (".step.py", ".stp.py", ".py"):
        if name.lower().endswith(suffix):
            stem = resolved.with_name(name[: -len(suffix)])
            break
    for suffix in STEP_SUFFIXES:
        candidate = stem.with_name(stem.name + suffix)
        if candidate.is_file():
            return candidate
    return None


def _missing_document_error(raw_target: str) -> CadRefError:
    return CadRefError(f"STEP file not found: {_native_path(raw_target)}")


def step_path_from_target(target: str) -> Path:
    raw_target = str(target or "").strip()
    if _names_a_foreign_path(raw_target):
        document = _path_target_document(raw_target)
        if document is None:
            raise _missing_document_error(raw_target)
        return document

    raw_step_path = _raw_step_path(raw_target)
    if raw_step_path is not None:
        return raw_step_path

    entry_target = entry_target_from_target(target)
    lookup_cad_path = _lookup_cad_path(entry_target.cad_path)
    step_path = find_step_path(lookup_cad_path)
    if step_path is not None:
        return step_path

    direct_step_path = _direct_step_path(entry_target.cad_path)
    if direct_step_path is not None:
        return direct_step_path

    if _is_path_shaped(raw_target):
        raise _missing_document_error(raw_target)
    raise CadRefError(f"STEP file not found for target '{target}'.")


def resolve_step_target(target: str) -> ResolvedStepTarget:
    entry_target = entry_target_from_target(target)
    cad_path = entry_target.cad_path
    raw_target = str(target or "").strip()
    explicit_python = raw_target.lower().endswith(".py")

    if _names_a_foreign_path(raw_target):
        # Resolved straight from the filesystem, catalog untouched: see
        # _names_a_foreign_path for why a bare-name identity must never be
        # looked up in a catalog it cannot belong to.
        document = _path_target_document(raw_target)
        if document is None:
            raise _missing_document_error(raw_target)
        return ResolvedStepTarget(
            cad_path=cad_path,
            source_path=document,
            step_path=document,
            explicit_python=explicit_python,
        )

    raw_step_path = _raw_step_path(raw_target)
    if raw_step_path is not None:
        # A document path names the document. A door is a reader: it never opens
        # the scripts beside a document to learn which one wrote it, so a broken
        # or unrelated sibling script cannot fail the read (and the answer does
        # not change when the script is gone).
        return ResolvedStepTarget(
            cad_path=cad_path,
            source_path=raw_step_path,
            step_path=raw_step_path,
        )

    lookup_cad_path = _lookup_cad_path(cad_path)
    source = find_source_by_cad_ref(lookup_cad_path)
    if source is not None and source.step_path is not None:
        if source.step_path is None:
            raise CadRefError(f"STEP file not found for ref '{cad_path}'.")
        return ResolvedStepTarget(
            cad_path=cad_path,
            source_path=source.source_path,
            step_path=source.step_path.resolve(),
            explicit_python=explicit_python,
        )
    if source is not None:
        raise CadRefError(f"CAD target '{cad_path}' is not STEP-backed.")

    direct_step_path = _direct_step_path(cad_path)
    if direct_step_path is not None:
        return ResolvedStepTarget(
            cad_path=cad_path,
            source_path=direct_step_path,
            step_path=direct_step_path,
        )

    if _is_path_shaped(raw_target):
        # A path names a file, so the answer is about that file, not about a
        # cad path the caller never typed.
        raise _missing_document_error(raw_target)
    raise CadRefError(f"CAD STEP ref not found for '{cad_path}'.")


def _direct_step_path(cad_path: str) -> Path | None:
    for suffix in STEP_SUFFIXES:
        candidate = (Path.cwd().resolve() / f"{cad_path}{suffix}").resolve()
        if candidate.is_file():
            return candidate
    return None


def _raw_step_path(target: str) -> Path | None:
    if not target:
        return None
    path = Path(target).expanduser()
    if path.suffix.lower() not in STEP_SUFFIXES:
        return None
    resolved = path.resolve() if path.is_absolute() else (Path.cwd().resolve() / path).resolve()
    return resolved if resolved.is_file() else None


def _cad_path_lookup_candidates(cad_path: str) -> tuple[str, ...]:
    return (cad_path,) if cad_path else ()


def _lookup_cad_path(cad_path: str) -> str:
    for candidate in _cad_path_lookup_candidates(cad_path):
        if resolve_cad_source_path(candidate) is not None:
            return candidate
    return cad_path


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()
