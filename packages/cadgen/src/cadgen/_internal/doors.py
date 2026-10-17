"""What every CLI door does before it touches a document.

DOCUMENTS-ONLY CLI INPUTS (README law 7). A model script is a PROGRAM:
``python model.py`` is the one source door, and running it writes the document,
its sidecar and its declared exports. Every command therefore takes the
DOCUMENT — a ``.step``/``.stp``/``.stl``/``.dxf`` file — and refuses any other
suffix by naming what it takes.

A door asks ONE question of a document (:func:`document_tree`, STORE.md §9):
does the store have a tree for this file's bytes? Yes → use it. No → a compile
job in the pool builds one from the bytes, exactly as for an imported STEP,
whether or not the file has a script. A door never refuses a document and never
runs a model body: whether the source has moved on since the document was
written is the model's record's business (``cadgen store why`` and the build
tree answer it), never a door's and never the viewer's.

Stdlib-light: these run before any CAD import, on the ``--help`` path and on a
model script's pre-gate path.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "STEP_SUFFIXES",
    "CompileFailed",
    "display_path",
    "document_target",
    "document_tree",
    "document_snapshot",
]


#: What a STEP document is called on disk. THE definition: every module that
#: asks "is this a STEP document?" imports this one.
STEP_SUFFIXES = (".step", ".stp")


class CompileFailed(RuntimeError):
    """The compile job for a document's bytes did not produce a tree.

    Its message is the compile's own error (the job's output), which is what a
    door reports verbatim -- a door never adds a "regenerate" instruction.
    """


def document_snapshot(document: Path) -> tuple[str, str]:
    """The tree for THIS document's bytes — a door's one question (STORE.md §9).

    Yes, the store has one — ``index/document/<sha256(bytes)>-v<schema>`` → tree (STORE.md
    §2, the law: artifact → artifact; no record is opened) → it is used, once the
    verify of an export's pending entry has answered (``store.exports.confirm_document``). Source
    changes are the model's record's business, never the door's: a document is
    never refused and no body ever runs here. No, or a pending entry whose verify could
    not answer → a **compile job** in the pool builds a tree from the file's bytes,
    exactly as for an imported STEP, whether or not the file has a script, and the
    lookup is repeated.
    """
    from cadgen.catalog import result_snapshot_for

    document = Path(document).expanduser().resolve()
    snapshot = result_snapshot_for(document)
    if snapshot:
        # An export's entry is pending until its verify answers: confirmed first
        # (store/exports.py), it names what the file shows; one no verify can settle is
        # compiled, as for a miss.
        from cadgen.store.exports import confirm_document

        tree = confirm_document(document, *snapshot)
        snapshot = (snapshot[0], tree) if tree else None
    if snapshot:
        return snapshot
    from cadgen.daemon.executors import submit_compile

    job = submit_compile(document)
    if job.wait() != 0:
        said = job.output().rstrip()
        raise CompileFailed(f"compiling {display_path(document)} failed" + (f":\n{said}" if said else ""))
    snapshot = result_snapshot_for(document)
    if not snapshot:
        raise CompileFailed(f"no tree for {display_path(document)} after its compile")
    return snapshot


def document_tree(document: Path) -> str:
    """The canonical tree from the same coherent lookup used by mesh exports."""
    return document_snapshot(document)[1]


def display_path(path: Path | str) -> str:
    """A path as a MESSAGE names it: relative to the cwd where that is
    meaningful, else as given. THE helper for door and result messages
    (``cadgen.results``, the STEP re-emit); never for a persisted path."""
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except (OSError, ValueError):
        return str(path)


def document_target(target: Path | str, *, suffixes: tuple[str, ...]) -> Path:
    """Resolve TARGET as a document, or say what this door takes.

    ``suffixes`` is the door's own accepted set (``.step``/``.stp`` for STEP,
    ``.stl`` for the STL door, ...); any other suffix is refused with the ones
    it takes.
    """
    path = Path(target).expanduser()
    suffix = path.suffix.lower()
    if suffix not in suffixes:
        accepted = "/".join(suffixes)
        raise ValueError(f"this command takes a {accepted} document: {target}")
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"document does not exist: {target}")
    return resolved
