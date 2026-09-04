from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cadgen.cad_ref_syntax import normalize_cad_path, parse_cad_tokens
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
            "document": _display_path(self.step_path),
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


def _is_path_shaped(raw_target: str) -> bool:
    """Rooted, ``~``-spelled, drive-lettered or reaching upward: a filesystem
    location rather than a cwd-relative name."""
    text = raw_target.replace("\\", "/")
    return (
        text.startswith(("/", "~", "../", "./"))
        or text in {"..", "."}
        or Path(raw_target).is_absolute()
        or (len(text) > 1 and text[1] == ":")
    )


def _target_identity(raw_target: str) -> str:
    if not _is_path_shaped(raw_target):
        return raw_target
    return _path_identity(Path(raw_target))


def _missing_document_error(raw_target: str) -> CadRefError:
    return CadRefError(f"STEP file not found: {_native_path(raw_target)}")


def step_path_from_target(target: str) -> Path:
    """The document a door target names. A door takes the DOCUMENT -- a ``.step``
    or ``.stp`` path, with its extension, wherever it lives -- and nothing else:
    no bare stem, no script. It never opens the scripts beside a document to learn
    which one wrote it."""
    raw_target = str(target or "").strip()
    document = _raw_step_path(raw_target)
    if document is not None:
        return document
    if Path(raw_target).expanduser().suffix.lower() in STEP_SUFFIXES:
        raise _missing_document_error(raw_target)
    raise CadRefError(
        f"not a STEP document path: {raw_target or target!r} -- a door takes the document itself "
        "(a .step or .stp path with its extension)"
    )


def resolve_step_target(target: str) -> ResolvedStepTarget:
    document = step_path_from_target(target)
    return ResolvedStepTarget(
        cad_path=entry_target_from_target(target).cad_path,
        source_path=document,
        step_path=document,
    )


def _raw_step_path(target: str) -> Path | None:
    if not target:
        return None
    path = Path(target).expanduser()
    if path.suffix.lower() not in STEP_SUFFIXES:
        return None
    resolved = path.resolve() if path.is_absolute() else (Path.cwd().resolve() / path).resolve()
    return resolved if resolved.is_file() else None


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()
