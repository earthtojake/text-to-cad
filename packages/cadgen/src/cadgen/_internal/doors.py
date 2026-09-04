"""What every CLI door does before it touches a document.

DOCUMENTS-ONLY CLI INPUTS (design/pose-animation-split.md, CLI/doors
follow-on). A model script is a PROGRAM: ``python model.py`` is the one source
door, and running it writes the document, its sidecar and its declared exports.
Every command therefore takes the DOCUMENT — a ``.step``/``.stp``/``.stl``/
``.dxf`` file — and refuses a ``.py`` by naming the run.

A door asks ONE question of a document (:func:`document_tree`, STORE.md §9):
does the store have a tree for this file's bytes? Yes → use it. No → a compile
job in the pool builds one from the bytes, exactly as for an imported STEP,
whether or not the file has a script. A door never refuses a document and never
runs a model body: whether the source has moved on since the document was
written is the model's record's business (``cadgen store why`` and the build
tree answer it), never a door's and never the viewer's.

:func:`announce_rebuild` remains for the one path that is not a door — a
caller handing a SCRIPT to the export pipeline (the viewer's export ABI), which
runs the generator and says so on stderr before it starts.

Stdlib-light: these run before any CAD import, on the ``--help`` path and on a
model script's pre-gate path.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "ScriptTargetError",
    "announce_rebuild",
    "document_target",
    "document_tree",
    "script_target_message",
]


class ScriptTargetError(ValueError):
    """A CLI door was handed a model script instead of a document."""


def document_tree(document: Path) -> str:
    """The tree for THIS document's bytes — a door's one question (STORE.md §9).

    Yes, the store has one — ``index/document/<sha256(bytes)>`` → tree (STORE.md
    §2, the law: artifact → artifact; no record is opened) → it is used. Source
    changes are the model's record's business, never the door's: a document is
    never refused and no body ever runs here. No → a **compile job** in the pool
    builds a tree from the file's bytes, exactly as for an imported STEP,
    whether or not the file has a script, and the lookup is repeated.
    """
    from cadgen.catalog import result_tree_for

    document = Path(document).expanduser().resolve()
    tree = result_tree_for(document)
    if tree:
        return tree
    from cadgen.daemon.executors import submit_compile

    job = submit_compile(document)
    if job.wait() != 0:
        said = job.output().rstrip()
        raise RuntimeError(f"compiling {_display(document)} failed" + (f":\n{said}" if said else ""))
    tree = result_tree_for(document)
    if not tree:
        raise RuntimeError(f"no tree for {_display(document)} after its compile")
    return tree


def _display(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except (OSError, ValueError):
        return str(path)


def script_target_message(script: Path | str) -> str:
    """The one teaching error at every door that used to accept a ``.py``."""
    return (
        f"a model script is a program — run it: python {_display(Path(script))} "
        "(building writes the document, sidecar, and declared exports); "
        "this command takes the document"
    )


def document_target(target: Path | str, *, suffixes: tuple[str, ...]) -> Path:
    """Resolve TARGET as a document, or raise the teaching error.

    ``suffixes`` is the door's own accepted set (``.step``/``.stp`` for STEP,
    ``.stl`` for the STL door, ...). A ``.py`` is refused by naming the run; any
    other suffix is refused by naming what the door takes.
    """
    path = Path(target).expanduser()
    suffix = path.suffix.lower()
    if suffix == ".py":
        raise ScriptTargetError(script_target_message(path))
    if suffix not in suffixes:
        accepted = "/".join(suffixes)
        raise ValueError(f"this command takes a {accepted} document: {target}")
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"document does not exist: {target}")
    return resolved


def announce_rebuild(
    door: str, document: Path | str, *, reason: str, source: Path | str, verb: str
) -> None:
    """The ONE line a rebuilding door prints, on stderr, when it decides to rebuild.

    ``<door>: <document> is stale (<reason>); rebuilding from <source> before <verb>``

    Printed at the decision, before the generator runs, so the wait that follows
    is attributed. Every door that can rebuild routes here; there is no second
    wording. Written to the CURRENT ``sys.stderr`` so a warm worker's redirect
    carries it to the client like the rest of the narration.
    """
    import sys

    print(
        f"{door}: {_display(Path(document))} is stale ({reason}); "
        f"rebuilding from {_display(Path(source))} before {verb}",
        file=sys.stderr,
        flush=True,
    )
