"""The integrations of cad's a program uses, worked out from its source without running any of it: a
static scan with ``ast`` of the script (or a module's file, or ``-c`` code) and of the local modules it
imports -- in its folder, its package, or its project -- following each absolute and relative import that
names a local file, the imports inside functions too (a model's body imports its kernel there).

Each module a program imports is looked up in the library's table of integrations
(``cad._internal.integrations``: ``build123d`` and ``OCP`` are the build123d integration's, ``kicode`` the
kicad integration's), by its top level; and so is each of cad's names it imports or uses, by the dotted name
it spells (``from cad.step import read``, ``step.read`` with ``step`` imported from cad, ``cad.read_step``):
an earlier spelling is read as the name it is now, by the alias table, and a name needs what the registry
says it does -- an integration's namespace that integration, a document type's reader its
``reader_integration`` (a STEP's: build123d), an operation the calling process runs its integration (a
STEP's, an xbf's, a model's and a DXF's ``dfm``: build123d; a mesh's: trimesh), one the engine runs none, an edit its
integration (``kicad_pcb.edit``: kicad; ``for_name``), and an operation also what its integration's operations need
beside it (``cad.step.solve``: calculix, with build123d and netgen; ``needs``). A verb's call (``cad.dfm``) needs
what the operation it runs of its source's type does, the source's suffix read where the call spells it
(``cad.dfm("part.stl")``, ``cad.dfm(HERE / "part.step")``: trimesh, build123d; ``cad.inspect(src, ranges=True)``
build123d; ``cad.export(board, "fab/", as_=kind)`` a KiCad file's, kicad; ``needs_call``), and a verb by its name alone
what every type it takes needs alike (``cad.fea``: calculix, with build123d and netgen). A type alone
(``from cad import step``) needs nothing. Nothing is imported, and a module of no local file is passed over.
An import made by name at run time (``importlib.import_module``) is not seen: the program's run says which
extra it lacks, in one line, and its header names it.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

__all__ = ["LIMIT", "scan"]

# The most local files one scan reads: a project's own tree, never a vendored world.
LIMIT = 2000
# The names cad is imported under, whose decorators the table names.
LIBRARY = ("cad", "cadgen")
# What a KiCad file's export alone writes, by its destination's suffix: no model's export is a .zip, a .csv, a
# netlist or a PDF.
_KICAD_DESTINATIONS = (".zip", ".csv", ".net", ".pdf")


def _module_file(root: Path, dotted: str) -> Path | None:
    """The local file of module ``dotted`` under ``root``: ``a/b.py``, else ``a/b/__init__.py``; None."""
    parts = dotted.split(".")
    if not all(part.isidentifier() for part in parts):
        return None
    base = root.joinpath(*parts)
    for found in (base.with_suffix(".py"), base / "__init__.py"):
        if found.is_file():
            return found
    return None


def _package_root(folder: Path) -> Path:
    """The folder that holds the topmost package ``folder`` is in (each folder up holding an
    ``__init__.py``), else ``folder`` itself: where its package's absolute imports resolve."""
    found = folder
    while (found / "__init__.py").is_file() and found.parent != found:
        found = found.parent
    return found


def _package_of(path: Path) -> Path:
    """The folder a relative import of the file ``path`` counts from: its own."""
    return path.parent


def _verb(dotted: str) -> str | None:
    """The verb a call of the library's name ``dotted`` is (``cad.dfm``: ``dfm``), or None."""
    from cad._internal.aliases import current
    from cad.registry import VERBS

    parts = current(dotted).split(".")
    return parts[1] if len(parts) == 2 and parts[0] in LIBRARY and parts[1] in VERBS else None


def _suffix(node: ast.expr | None) -> str | None:
    """The suffix of the path an expression spells, where it ends in a literal (``"part.stl"``, ``HERE /
    "part.stl"``, ``Path("part.stl")``, ``f"{name}.stl"``), or None."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        node = node.right
    elif isinstance(node, ast.Call) and node.args and not node.keywords:
        called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        node = node.args[-1] if called in ("Path", "PurePath") else None
    fragment = isinstance(node, ast.JoinedStr)
    if fragment and node.values:
        node = node.values[-1]
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return None
    name = node.value.replace("\\", "/").rsplit("/", 1)[-1]
    dot = name.rfind(".")
    return name[dot:] if dot > 0 or (dot == 0 and fragment) else None


def _call(verb: str, node: ast.Call) -> tuple[str | None, str | None]:
    """What a verb's call says of its source: its suffix where it spells one (``_suffix``) and ``inspect``'s mode
    (``ranges=True``); an export of a source it cannot read is a KiCad file's (a board's or a schematic's, the kicad
    integration's) where the call says what only a KiCad file's says (``_kicad_export``)."""
    from cad.registry import MODES

    keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
    suffix = _suffix(node.args[0] if node.args else keywords.get("source"))
    if suffix is None and verb == "export" and _kicad_export(node, keywords):
        suffix = ".kicad_pcb"
    mode = next((name for name in MODES if isinstance(keywords.get(name), ast.Constant)
                 and keywords[name].value is True), None)
    return suffix, mode


def _kicad_export(node: ast.Call, keywords: dict[str, ast.expr]) -> bool:
    """Whether a ``cad.export`` call says what a KiCad file's export alone does: an ``as_`` that is no model's kind
    (``as_="gerbers"``, or one the scan cannot read, which a model's export never needs: its destination says it),
    or a destination that is a folder (``"fab/"``) or a file no model's export writes (``_KICAD_DESTINATIONS``)."""
    from cad._internal.verbs import MODEL_KINDS

    kind = node.args[2] if len(node.args) > 2 else keywords.get("as_")
    if kind is not None and not (isinstance(kind, ast.Constant) and (kind.value is None or kind.value in MODEL_KINDS)):
        return True
    dst = node.args[1] if len(node.args) > 1 else keywords.get("dst")
    if isinstance(dst, ast.Constant) and isinstance(dst.value, str) and dst.value.endswith(("/", "\\")):
        return True
    return _suffix(dst) in _KICAD_DESTINATIONS


def _dotted(node: ast.expr, bound: dict[str, str]) -> str | None:
    """The library's dotted name an expression spells (``step.read`` with ``step`` bound to ``cad.step``:
    ``cad.step.read``), or None for one rooted at no name bound to cad."""
    attributes: list[str] = []
    while isinstance(node, ast.Attribute):
        attributes.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name) or node.id not in bound:
        return None
    return ".".join([bound[node.id], *reversed(attributes)])


class _Reader:
    """One scan: the files read, the integrations found, and the roots absolute imports resolve in."""

    def __init__(self, roots: list[Path]) -> None:
        self.roots = roots
        self.seen: set[Path] = set()
        self.queue: list[Path] = []
        self.found: set[str] = set()

    def module(self, dotted: str) -> None:
        """An absolute import: its integration, and each local file of it and of its parents."""
        from cad._internal.integrations import needs

        keys = needs(dotted)
        if keys:
            self.found.update(keys)
            return
        parts = dotted.split(".")
        if parts[0] in LIBRARY:
            return  # the library itself, never a project's file of its name (the program's folder is last)
        for size in range(1, len(parts) + 1):
            for root in self.roots:
                local = _module_file(root, ".".join(parts[:size]))
                if local is not None:
                    self.add(local)
                    break

    def relative(self, path: Path, level: int, name: str | None, names: list[str]) -> None:
        """A relative import of the file ``path``: each local file it names."""
        folder = _package_of(path)
        for _up in range(level - 1):
            folder = folder.parent
        targets = [name] if name else []
        targets += [f"{name}.{each}" if name else each for each in names]
        for dotted in targets:
            local = _module_file(folder, dotted)
            if local is not None:
                self.add(local)

    def add(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved in self.seen or len(self.seen) >= LIMIT:
            return
        self.seen.add(resolved)
        self.queue.append(resolved)

    def read(self, source: str, path: Path) -> None:
        """One file's imports, its uses of cad's names and its decorators (see the module); a file that does
        not parse is passed over: Python says what is wrong with it when it runs."""
        from cad._internal.integrations import needs, needs_call

        try:
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, ValueError):
            return
        bound: dict[str, str] = {}  # a name bound here to one of cad's own, and that name's dotted path
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.module(alias.name)
                    top = alias.name.split(".")[0]
                    if top in LIBRARY:  # ``import cad.step`` binds ``cad``; ``import cad.step as s``, ``s``
                        bound[alias.asname or top] = alias.name if alias.asname else top
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    self.relative(path, node.level, node.module, [alias.name for alias in node.names])
                elif node.module:
                    self.module(node.module)
                    for alias in node.names:  # ``from cad import read_step``; ``from pkg import module``: local too
                        self.module(f"{node.module}.{alias.name}")
                        if node.module.split(".")[0] in LIBRARY:
                            bound[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):  # ``step.read``, ``cad.read_step``, ``c.step.dfm``
                dotted = _dotted(node, bound)
                if dotted:
                    self.found.update(needs(dotted))
            elif isinstance(node, ast.Call):  # ``cad.dfm("part.stl")``: the verb's source decides what it needs
                dotted = _dotted(node.func, bound)
                verb = _verb(dotted) if dotted else None
                if verb is not None:
                    self.found.update(needs_call(verb, *_call(verb, node)))

    def drain(self) -> None:
        while self.queue:
            path = self.queue.pop()
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            self.read(source, path)


def scan(*, script: str | os.PathLike | None = None, module: str | None = None, code: str | None = None,
         cwd: str | os.PathLike | None = None, roots: list[str | os.PathLike] | tuple = ()) -> set[str]:
    """The integrations (the library's table's keys) the program uses, by a static scan of its source and
    the local modules it imports (see the module): a ``script``'s file, a ``module`` found under the working
    folder ``cwd``, or ``code`` run there. ``roots``: more folders absolute imports resolve in (a project's,
    its ``src``)."""
    here = Path(cwd or os.getcwd()).resolve()
    if script is not None:
        path = Path(script).resolve()
        folder = path.parent
        found = [folder, _package_root(folder)]
    else:
        path = None
        found = [here]
    reader = _Reader([*dict.fromkeys([*found, *(Path(root).resolve() for root in roots)])])
    if path is not None:
        reader.add(path)
    elif module is not None:
        reader.module(module)
    elif code is not None:
        reader.read(code, here / "<string>")
    reader.drain()
    return reader.found
