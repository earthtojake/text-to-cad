from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cadgen.selector_types import SelectorBundle


class CadRefError(RuntimeError):
    pass


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
class StepArtifact:
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


class StepArtifactError(CadRefError):
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


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()
