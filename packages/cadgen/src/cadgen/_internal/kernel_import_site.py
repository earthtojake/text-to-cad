"""Who imported the CAD kernel first, for the eager-import hint.

``@step`` wants a model's module body to stay kernel-free so a current build
can be skipped, or handed to the warm daemon, before OCP's ~2.5 s import is
paid. When the kernel IS loaded by the time the decorator runs, the useful
message is not "you imported it" but WHERE: a ``from build123d import ...``
at module top is one cause, and ``from cadgen import build123d as bd`` does
not prevent the other -- a module-level ``bd.Align.CENTER`` default or a
palette constant built from a kernel type resolves an attribute at import
time and triggers the real import through the lazy proxy.

A ``sys.meta_path`` finder that never finds anything: it only notes the first
request for ``build123d`` or ``OCP`` and the innermost frame outside cadgen's
own package -- the lazy proxy is one route in, but any other cadgen-internal
module that happens to import the kernel at its own top level (e.g. a module
under ``cadgen/_internal`` reached transitively from a model's own import) is
just as much cadgen's business, not the model author's; naming that internal
file instead of the causal project import leaves the hint with nothing
actionable to fix. Installed by ``cadgen``'s package ``__init__`` so it is in
place before any model module body runs.

One route the finder can never see is the kernel imported BEFORE cadgen --
exactly what an import sorter writes for a model that reaches for the kernel
directly, since ``import build123d`` sorts above ``from cadgen import step``.
There is no frame left to read by then, so ``install`` parses the file that
was importing cadgen and names the kernel import statement written there.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_KERNEL_TOP_LEVEL = ("build123d", "OCP")
_SITE: tuple[str, int, str] | None = None
_CADGEN_PACKAGE_DIR = Path(__file__).resolve().parent.parent


class _KernelImportRecorder:
    """Records the first kernel import request; finds nothing, ever."""

    def find_spec(self, fullname, path=None, target=None):
        global _SITE
        if _SITE is None and fullname.partition(".")[0] in _KERNEL_TOP_LEVEL and fullname.partition(".")[0] not in sys.modules:
            _SITE = _caller_site()
        return None


def _is_cadgen_internal(filename: str) -> bool:
    try:
        resolved = Path(filename).resolve()
    except OSError:
        return False
    return resolved == _CADGEN_PACKAGE_DIR or _CADGEN_PACKAGE_DIR in resolved.parents


def _caller_site() -> tuple[str, int, str] | None:
    for frame in reversed(traceback.extract_stack()):
        filename = frame.filename
        if "importlib" in filename or filename.startswith("<frozen") or _is_cadgen_internal(filename):
            continue
        return (filename, frame.lineno, frame.line or "")
    return None


def _kernel_import_statement(filename: str) -> tuple[str, int, str] | None:
    """The first ``import build123d`` / ``import OCP`` statement written in
    ``filename``, by parsing it.

    Used for the one route the recorder cannot observe: the kernel imported
    BEFORE cadgen, which is what an import sorter produces from a model whose
    author reached for the kernel directly (``import build123d`` sorts above
    ``from cadgen import step``). The finder is installed by cadgen's package
    body, so by then the import is already done and there is no frame left to
    read -- but the statement is still in the file, and naming it is the whole
    point of the hint.
    """
    import ast

    try:
        source = Path(filename).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
        return None
    lines = source.splitlines()
    hits: list[int] = []
    for node in ast.walk(tree):  # walk is breadth-first, so collect and take the earliest
        roots: tuple[str, ...] = ()
        if isinstance(node, ast.Import):
            roots = tuple(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots = (node.module.partition(".")[0],)
        if any(root in _KERNEL_TOP_LEVEL for root in roots):
            hits.append(node.lineno)
    if not hits:
        return None
    lineno = min(hits)
    return (filename, lineno, lines[lineno - 1] if 0 < lineno <= len(lines) else "")


def _preloaded_site() -> tuple[str, int, str] | None:
    """Where the kernel came from when it was already loaded at ``install()``."""
    caller = _caller_site()
    if caller is None:
        return None
    return _kernel_import_statement(caller[0])


def install() -> None:
    global _SITE
    if not any(isinstance(finder, _KernelImportRecorder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _KernelImportRecorder())
    if _SITE is None and any(name in sys.modules for name in _KERNEL_TOP_LEVEL):
        _SITE = _preloaded_site()


def first_import_site() -> tuple[str, int, str] | None:
    """``(file, line, source)`` of the statement that first pulled the kernel
    in, or None when it is not loaded (or was loaded before cadgen by a file
    that does not name the kernel itself)."""
    return _SITE
