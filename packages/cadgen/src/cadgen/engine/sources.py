"""What a model body is made of: the symbols its code reaches, and where a reference cannot
be followed, the bytes of the module it is in.

``Symbols(...).key(function)`` follows a body's function through what it references --
the global names its code (and the code nested in it) loads, read through module
attributes, its defaults and closure cells, and from there every first-party function,
class, model and value they reach -- and stops at what is not first-party (the standard
library, build123d, OCP, numpy: the engine's version covers those). Each symbol reached
counts by a hash of what it is: a function by its code -- the instructions with their
constants and names, its variables and flags -- and not by where it sits (its file, its
line, its docstring); a class by its bases and the hashes of its attributes; a value by a
canonical form of it. Each global binding the code reads counts as what it is bound to,
by the module that binds it, so rebinding a name is an edit. The key is the sorted set of
those pairs.

A reference that cannot be followed by its value -- a computed ``getattr``, ``globals()``,
``locals()``, ``vars()``, ``eval``/``exec``, ``__import__`` or ``importlib`` in reached
code, a ``from x import *``, a first-party module held as a value or imported inside a
function that the script's load did not import, a value with no canonical form -- falls
back, per module, to the module's bytes: ``closure(path, module)``, a digest of every file
its code can come from: its file and, followed through their import statements -- every
``import`` and ``from ... import`` anywhere in a file, a function's own included -- each
first-party module and package they name, as the module search path finds it. A module
is first-party as the trace counts a frame (not the standard library, not an installed
package, not cadgen).

Files are read by their bytes, hashed once per version of the file (its stat); their
imports and dynamic spots are parsed once per digest; a code object is read once per
value of it. All in this process's memory.
"""

from __future__ import annotations

import ast
import bisect
import builtins
import copy
import dis
import enum
import functools
import hashlib
import inspect
import os
import sys
import types
from collections import OrderedDict
from pathlib import Path, PurePath
from typing import Any

__all__ = ["Symbols", "assigned", "closure", "closure_files", "digest", "returning", "skeleton"]

_HELD = 4096
# (device, inode, size, mtime) -> the file's digest; digest -> the imports its source makes.
_DIGESTS: "OrderedDict[tuple, str]" = OrderedDict()
_IMPORTS: "OrderedDict[str, tuple]" = OrderedDict()


def digest(path: Path) -> str:
    """A file's bytes, hashed once per version of the file."""
    stat = os.stat(path)
    version = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    found = _DIGESTS.get(version)
    if found is None:
        found = _DIGESTS[version] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        while len(_DIGESTS) > _HELD:
            _DIGESTS.popitem(last=False)
    return found


def _imports(path: Path, file_digest: str) -> tuple:
    """Each import statement of a file: ``(level, module, names)``."""
    found = _IMPORTS.get(file_digest)
    if found is None:
        rows = []
        try:
            tree = ast.parse(Path(path).read_bytes(), filename=str(path))
        except SyntaxError:
            tree = ast.Module(body=[], type_ignores=[])
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                rows.extend((0, alias.name, ()) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                rows.append((node.level, node.module or "", tuple(alias.name for alias in node.names)))
        found = _IMPORTS[file_digest] = tuple(rows)
        while len(_IMPORTS) > _HELD:
            _IMPORTS.popitem(last=False)
    return found


def _first_party(path: Path) -> bool:
    from cadgen.engine.kernel.trace import first_party_file

    return first_party_file(str(path))


def _files(name: str) -> list[tuple[str, Path]]:
    """The first-party files importing ``name`` runs, each with its module name: every
    package ``__init__`` on the way, then the module -- as the first search-path entry
    holding its top level finds them. Nothing for a module that is not first-party."""
    parts = name.split(".")
    for entry in sys.path:
        root = Path(entry or os.getcwd())
        top = root / parts[0]
        if not (top.with_suffix(".py").is_file() or (top / "__init__.py").is_file()):
            continue
        found = []
        folder = root
        for depth, part in enumerate(parts, 1):
            package = folder / part / "__init__.py"
            module = (folder / part).with_suffix(".py")
            dotted = ".".join(parts[:depth])
            if package.is_file():
                found.append((dotted, package))
                folder = folder / part
            elif module.is_file():
                found.append((dotted, module))
                break
            else:
                break
        return [(dotted, path.resolve()) for dotted, path in found if _first_party(path)]
    return []


def closure(path: Path, module: str, resolved: dict[str, list] | None = None) -> str:
    """The digest of a body's code: the file it is defined in (as module ``module``) and
    every first-party module it imports, transitively, by path and bytes. ``resolved``
    keeps what each module name resolved to, for the bodies of one build to share."""
    seen = closure_files(path, module, resolved)
    hasher = hashlib.sha256()
    for file in sorted(seen):
        hasher.update(f"{file}\0{seen[file]}\n".encode())
    return hasher.hexdigest()


def closure_files(path: Path, module: str, resolved: dict[str, list] | None = None) -> dict[Path, str]:
    """``closure``'s files, each with the digest of its bytes."""
    resolved = {} if resolved is None else resolved
    seen: dict[Path, str] = {}
    pending = [(module, Path(path).resolve())]
    while pending:
        name, file = pending.pop()
        if file in seen:
            continue
        seen[file] = file_digest = digest(file)
        package = name if file.name == "__init__.py" else name.rpartition(".")[0]
        for level, target, names in _imports(file, file_digest):
            if level:
                base = package.split(".") if package else []
                base = base[:len(base) - (level - 1)] if level > 1 else base
                target = ".".join([*base, target] if target else base)
            if not target:
                continue
            candidates = [target, *(f"{target}.{item}" for item in names if item != "*")]
            for candidate in candidates:
                found = resolved.get(candidate)
                if found is None:
                    found = resolved[candidate] = _files(candidate)
                pending.extend(found)
    return seen


# --- symbols -------------------------------------------------------------------------------

# Calls whose reach the walk cannot follow by value; the attribute builtins only with a
# name computed at run time.
_DYNAMIC_CALLS = frozenset({"eval", "exec", "globals", "locals", "vars", "__import__", "compile"})
_ATTRIBUTE_CALLS = frozenset({"getattr", "setattr", "delattr", "hasattr"})
# file digest -> (its dynamic spots by (name, first line), the reason the module itself
# cannot be followed or None).
_FACTS: "OrderedDict[str, tuple[dict, str | None]]" = OrderedDict()


def _reads_dict(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "__dict__"


def _facts(path: Path, file_digest: str) -> tuple[dict, str | None, tuple, dict, tuple]:
    """What of a file the walk cannot follow by value: per function or lambda, keyed as its
    code object names it -- ``(name, first line)``, the line of its first decorator -- the
    first dynamic reference in it or in what it nests; and a ``from x import *`` at the
    module's top, which binds names the source does not spell. With them, from the same
    pass, the file's assignments (``_assignment_site``), what names a feature
    (``assigned``), each target named as ``_named_sites`` names it; per function, the
    skeleton of those names (``skeleton``); and the spans of its ``return`` statements
    (``returning``)."""
    found = _FACTS.get(file_digest)
    if found is None:
        try:
            tree = ast.parse(Path(path).read_bytes(), filename=str(path))
        except (SyntaxError, ValueError, OSError):
            tree = ast.Module(body=[], type_ignores=[])
        spots: dict[tuple[str, int], str] = {}
        star = None
        sites: list[tuple] = []
        returns: list[tuple] = []
        functions: set[str] = {"<module>"}
        pending: list[tuple[ast.AST, tuple]] = [(tree, ())]
        while pending:
            node, scopes = pending.pop()
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                site = _assignment_site(node)
                if site is not None:
                    sites.append((*site, scopes[-1][0] if scopes else "<module>", _statement_tag(node)))
            elif isinstance(node, ast.Return) and node.value is not None:
                returns.append(_span(node))
            reason = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                first = min([decorator.lineno for decorator in node.decorator_list] + [node.lineno])
                scopes = (*scopes, (node.name, first))
                functions.add(node.name)
            elif isinstance(node, ast.Lambda):
                scopes = (*scopes, ("<lambda>", node.lineno))
                functions.add("<lambda>")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                name = node.func.id
                if name in _DYNAMIC_CALLS:
                    reason = f"{name}()"
                elif name in _ATTRIBUTE_CALLS and len(node.args) >= 2 and not (
                        isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
                    reason = f"{name} with a computed name"
            elif isinstance(node, ast.Name) and node.id == "importlib":
                reason = "importlib"
            elif isinstance(node, ast.Attribute) and node.attr == "modules" and isinstance(node.value, ast.Name) \
                    and node.value.id == "sys":
                reason = "sys.modules"
            elif isinstance(node, ast.Subscript) and _reads_dict(node.value) and not isinstance(node.slice, ast.Constant):
                reason = "__dict__ with a computed name"
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and _reads_dict(node.func.value) \
                    and node.func.attr in ("get", "items", "keys", "values", "copy") and not (
                        node.args and isinstance(node.args[0], ast.Constant)):
                reason = f"__dict__.{node.func.attr}"
            elif isinstance(node, ast.Import) and any(alias.name.split(".")[0] == "importlib" for alias in node.names):
                reason = "importlib"
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "importlib" and not node.level:
                    reason = "importlib"
                elif any(alias.name == "*" for alias in node.names) and not scopes and star is None:
                    star = f"from {'.' * node.level}{node.module or ''} import * (line {node.lineno})"
            if reason is not None:
                for scope in scopes:
                    spots.setdefault(scope, f"{reason} (line {node.lineno})")
            pending.extend((child, scopes) for child in ast.iter_child_nodes(node))
        sites = _named_sites(sorted(sites, key=lambda site: site[0]))
        returns.sort()
        # Per function name, what its features are named from: the targets of its
        # assignments in source order, as named (``skeleton``).
        targets: dict[str, list] = {name: [] for name in functions}
        for site in sites:
            targets.setdefault(site[4], []).append(site[2])
        skeleton = {name: hashlib.blake2b(repr(found).encode(), digest_size=8).hexdigest()
                    for name, found in targets.items()}
        found = _FACTS[file_digest] = (spots, star, tuple(sites), skeleton, tuple(returns))
        while len(_FACTS) > _HELD:
            _FACTS.popitem(last=False)
    return found


def skeleton(path: Path) -> dict[str, str]:
    """Per function name of a file (``<module>`` its top level), a digest of what its
    features' names are made of: the targets its assignments name, in order, as
    ``_named_sites`` names them. A part whose shape a warm build hands back unchanged keeps
    its names while the functions its names come from have the same skeleton; a renamed
    variable or function, an assignment added, a statement whose shape changed, is a new
    one (``build``)."""
    return _facts(Path(path), digest(Path(path)))[3]


# --- a statement's shape, its literals aside ---------------------------------------------

# The letters a statement's tag is spelled in: hex digits as letters, so the count a name
# takes after it (``target_<tag>2``) is never read as part of it.
_TAG_LETTERS = str.maketrans("0123456789abcdef", "abcdefghijklmnop")


class _Literals(ast.NodeTransformer):
    """A statement with every literal one placeholder: a number (signed too), a string,
    a bytes, a constant of any kind."""

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        return ast.Constant(value=...)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        if isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(node.operand, ast.Constant):
            return ast.Constant(value=...)
        return self.generic_visit(node)


def _statement_tag(node: ast.AST) -> str:
    """The statement's skeleton -- its syntax tree with every literal masked -- as six
    letters: equal for two statements that differ only in their numbers and strings, so a
    dimension edit keeps it, and different for a statement of another shape."""
    masked = _Literals().visit(copy.deepcopy(node))
    text = ast.dump(masked, annotate_fields=False, include_attributes=False)
    return hashlib.blake2b(text.encode(), digest_size=3).hexdigest().translate(_TAG_LETTERS)


def _named_sites(sites: list[tuple]) -> list[tuple]:
    """Each assignment site as ``assigned`` reads it, ``(start, end, names, elements,
    function)``, each name the author's name for the feature it stores: the first
    statement in a function to assign a target names it as it is (``relief``); every
    later one -- a reassignment -- by the target and its statement's tag
    (``relief_kdpgac``), so a reassignment is identified by its skeleton and counted
    (``trace``) only among the statements of that skeleton in the function. Inserting a
    statement of another shape renames none of them; two statements of one skeleton still
    count in order."""
    first: dict[tuple[str, str], tuple] = {}
    for start, _end, names, _elements, function, _tag in sites:
        for name in names:
            first.setdefault((function, name), start)
    named = []
    for start, end, names, elements, function, tag in sites:
        names = tuple(name if first[(function, name)] == start else f"{name}_{tag}" for name in names)
        named.append((start, end, names, elements, function))
    return named


# --- what a call's result is assigned to ---------------------------------------------------


def _target_name(node: ast.AST) -> str | None:
    """The author's name for what an assignment target holds: a variable's name, an
    attribute's (``self.body`` is ``body``), the container's for an item (``parts[i]`` is
    ``parts``), the starred name's."""
    while True:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, (ast.Subscript, ast.Starred)):
            node = node.value
            continue
        return None


def _span(node: ast.AST) -> tuple[tuple[int, int], tuple[int, int]]:
    return (node.lineno, node.col_offset), (node.end_lineno or node.lineno, node.end_col_offset or 0)


def _assignment_site(node: ast.AST) -> tuple | None:
    """An assignment as ``assigned`` reads it: ``(start, end, names, elements)`` -- its span
    as (line, column) pairs, the names its first target assigns (one, or a tuple target's
    each), and, where a tuple target is given a tuple of as many values, each value's span,
    so a call in one of them is named by its own target."""
    if isinstance(node, ast.Assign):
        target, value = node.targets[0], node.value
    elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        target, value = node.target, node.value
    else:
        return None
    if value is None:
        return None
    if isinstance(target, (ast.Tuple, ast.List)):
        names = tuple(_target_name(element) for element in target.elts)
        if not names or any(name is None for name in names):
            return None
        elements = None
        if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(names) \
                and not any(isinstance(element, ast.Starred) for element in value.elts):
            elements = tuple(_span(element) for element in value.elts)
        start, end = _span(node)
        return start, end, names, elements
    name = _target_name(target)
    if name is None:
        return None
    start, end = _span(node)
    return start, end, (name,), None


# id(code) -> (code, its instructions' positions, per instruction offset the names it assigns).
_SITES: "OrderedDict[int, tuple]" = OrderedDict()
_UNSEEN = object()


def assigned(code: types.CodeType, offset: int) -> tuple[tuple[int, int], tuple[str, ...]] | None:
    """The assignment running instruction ``offset`` (``frame.f_lasti``) of ``code``: where
    the statement starts, ``(line, column)``, and the names it assigns its value to --
    ``relief = cut(...)`` is ``("relief",)``, ``a, b = split(...)`` is ``("a", "b")``, a
    call in the second of ``a, b = box(), cylinder()`` is ``("b",)`` -- or None where it is
    no assignment (a return, an expression, a loop's header). Read from the file's source
    by the instruction's position, parsed once per digest (``_facts``) and looked up once
    per instruction."""
    held = _SITES.get(id(code))
    if held is None or held[0] is not code:
        held = _SITES[id(code)] = (code, [None], {})
        while len(_SITES) > _HELD * 4:
            _SITES.popitem(last=False)
    else:
        _SITES.move_to_end(id(code))
    found = held[2].get(offset, _UNSEEN)
    if found is _UNSEEN:
        found = held[2][offset] = _assigned(code, offset, held[1])
    return found


def _assigned(code: types.CodeType, offset: int, positions: list) -> tuple[tuple[int, int], tuple[str, ...]] | None:
    filename = code.co_filename
    if not filename or filename.startswith("<"):
        return None
    if positions[0] is None:
        positions[0] = list(code.co_positions())
    at = offset // 2
    if not 0 <= at < len(positions[0]):
        return None
    line, _end_line, column, _end_column = positions[0][at]
    if line is None:
        return None
    try:
        sites = _facts(Path(filename), digest(Path(filename)))[2]
    except OSError:
        return None
    point = (line, column if column is not None else 0)
    index = bisect.bisect_right(sites, point, key=lambda site: site[0]) - 1
    if index < 0:
        return None
    start, end, names, elements, _function = sites[index]
    if not start <= point <= end:
        return None
    if elements is not None:
        for name, (first, last) in zip(names, elements):
            if first <= point <= last:
                return start, (name,)
    return start, names


# id(code) -> (code, its instructions' positions, per instruction offset whether it returns).
_RETURNS: "OrderedDict[int, tuple]" = OrderedDict()


def returning(code: types.CodeType, offset: int) -> bool:
    """Whether instruction ``offset`` of ``code`` runs in a ``return`` statement's value: a
    helper handing back what it makes, unassigned (``return bd.Pos(...) * bd.Cylinder(...)``),
    whose calls its caller's assignment names (``trace``)."""
    held = _RETURNS.get(id(code))
    if held is None or held[0] is not code:
        held = _RETURNS[id(code)] = (code, [None], {})
        while len(_RETURNS) > _HELD * 4:
            _RETURNS.popitem(last=False)
    else:
        _RETURNS.move_to_end(id(code))
    found = held[2].get(offset)
    if found is None:
        found = held[2][offset] = _returning(code, offset, held[1])
    return found


def _returning(code: types.CodeType, offset: int, positions: list) -> bool:
    filename = code.co_filename
    if not filename or filename.startswith("<"):
        return False
    if positions[0] is None:
        positions[0] = list(code.co_positions())
    at = offset // 2
    if not 0 <= at < len(positions[0]):
        return False
    line, _end_line, column, _end_column = positions[0][at]
    if line is None:
        return False
    try:
        spans = _facts(Path(filename), digest(Path(filename)))[4]
    except OSError:
        return False
    point = (line, column if column is not None else 0)
    index = bisect.bisect_right(spans, (point, (1 << 62, 0))) - 1
    return index >= 0 and spans[index][0] <= point <= spans[index][1]


_HASCONST = frozenset(dis.hasconst)
_HASJUMP = frozenset(getattr(dis, "hasjump", ())) | frozenset(dis.hasjrel) | frozenset(dis.hasjabs)
_HASNAME = frozenset(dis.hasname) | frozenset(dis.haslocal) | frozenset(dis.hasfree)
# Instructions that do nothing (and the prefix that only widens the next one's argument,
# whose presence follows a constant's index in the table, not the code).
_SKIPPED_OPS = frozenset({"EXTENDED_ARG", "CACHE", "NOP"})
_DOCSTRING_FLAG = getattr(inspect, "CO_HAS_DOCSTRING", 0)
_CHAIN_OPS = frozenset({"LOAD_ATTR", "LOAD_METHOD"})
_GLOBAL_OPS = frozenset({"LOAD_GLOBAL", "LOAD_NAME"})
_STORE_OPS = frozenset({"STORE_FAST", "STORE_DEREF", "STORE_FAST_LOAD_FAST"})


class _Code:
    """What a code object is, apart from where it sits: the digest of its instructions;
    the global names it loads with the attributes read off them (``("parts", "GAP")``,
    ending ``"=name"`` when the global is stored in local ``name`` as it is); the imports
    it makes (``(level, module, names)``); each local's attribute reads, the locals used
    other than to read an attribute (``escapes``), and the locals an import is stored in
    (``stores``: ``(level, dotted)`` -> names); and each code object it is or nests as
    ``(name, first line)``, its own first. Locals of nested code count with their
    parent's, by name."""

    __slots__ = ("digest", "chains", "imports", "local_chains", "escapes", "stores", "codes")

    def __init__(self) -> None:
        self.digest = ""
        self.chains: Any = []
        self.imports: Any = []
        self.local_chains: dict[str, set[tuple]] = {}
        self.escapes: set[str] = set()
        self.stores: dict[tuple, set[str]] = {}
        self.codes: Any = []


# Per code object, compared by value (a module loaded again makes equal code objects).
_CODES: "OrderedDict[Any, _Code]" = OrderedDict()
_CODES_HELD = 1 << 16


def _code(code: types.CodeType) -> _Code:
    found = _CODES.get(code)
    if found is None:
        found = _Code()
        found.digest = _code_digest(code, found)
        found.chains = tuple(dict.fromkeys(found.chains))
        found.imports = tuple(dict.fromkeys(found.imports))
        found.codes = tuple(found.codes)
        _CODES[code] = found
        while len(_CODES) > _CODES_HELD:
            _CODES.popitem(last=False)
    return found


def _stored(instructions: list, at: int) -> str | None:
    """The local the next instruction stores what the one at ``at`` made in, if it does."""
    if at + 1 < len(instructions) and instructions[at + 1].opname in _STORE_OPS:
        name = instructions[at + 1].argval
        return name[0] if isinstance(name, tuple) else name
    return None


def _attributes(instructions: list, at: int) -> tuple:
    """The attribute names read in a row off what the instruction at ``at`` loads."""
    chain = []
    follow = at + 1
    while follow < len(instructions) and instructions[follow].opname in _CHAIN_OPS:
        chain.append(instructions[follow].argval)
        follow += 1
    return tuple(chain)


def _code_digest(code: types.CodeType, scan: _Code) -> str:
    """A code object's instructions, each by its operation and its argument read through
    the tables -- a constant by its value, a name by its name, a jump by the instruction
    it lands on -- with its exception table, signature, variables and flags. Not its file,
    its lines, its columns or its docstring (a constant no instruction loads)."""
    scan.codes.append((code.co_name, code.co_firstlineno))
    instructions = [ins for ins in dis.get_instructions(code) if ins.opname not in _SKIPPED_OPS]
    offsets = [ins.offset for ins in instructions]
    hasher = hashlib.sha256(repr((
        code.co_name, getattr(code, "co_qualname", code.co_name), code.co_argcount, code.co_posonlyargcount,
        code.co_kwonlyargcount, code.co_flags & ~_DOCSTRING_FLAG, code.co_varnames, code.co_freevars,
        code.co_cellvars)).encode())
    importing: tuple | None = None
    # A cell is loaded as a fast local only to hand it to a closure (``LOAD_CLOSURE``,
    # which is what 3.13 compiles it to): the nested code's own reads are scanned.
    cells = frozenset(code.co_cellvars) | frozenset(code.co_freevars)
    for at, ins in enumerate(instructions):
        op, name = ins.opcode, ins.opname
        if op in _HASCONST:
            argument: Any = _const(ins.argval, scan)
        elif op in _HASJUMP and isinstance(ins.argval, int):
            argument = bisect.bisect_left(offsets, ins.argval)
        elif op in _HASNAME:
            argument = ins.argrepr
        else:
            argument = (ins.arg, ins.argrepr)
        hasher.update(f"{name}\0{argument!r}\n".encode())
        if name in _GLOBAL_OPS:
            chain = (ins.argval, *_attributes(instructions, at))
            local = _stored(instructions, at) if len(chain) == 1 else None
            scan.chains.append(chain if local is None else (*chain, "=" + local))
        elif (name.startswith("LOAD_FAST") and name != "LOAD_FAST_AND_CLEAR") or name == "LOAD_DEREF":
            loaded = ins.argval if isinstance(ins.argval, tuple) else (ins.argval,)
            if name != "LOAD_DEREF" and cells.intersection(loaded):
                continue
            scan.escapes.update(loaded[:-1])
            chain = _attributes(instructions, at)
            if chain:
                scan.local_chains.setdefault(loaded[-1], set()).add(chain)
            else:
                scan.escapes.add(loaded[-1])
        elif name == "IMPORT_NAME":
            level = instructions[at - 2].argval if at >= 2 else 0
            names = instructions[at - 1].argval if at >= 1 else None
            level = level if isinstance(level, int) else 0
            names = tuple(names) if isinstance(names, tuple) else ()
            scan.imports.append((level, ins.argval, names))
            # ``from m import x`` takes x off m; ``import a.b`` binds a, and ``import a.b
            # as c`` takes b off it.
            importing = (level, ins.argval, bool(names), ins.argval if names else ins.argval.split(".")[0])
            local = _stored(instructions, at)
            if local is not None:
                scan.stores.setdefault((level, importing[3]), set()).add(local)
        elif name == "IMPORT_FROM" and importing is not None:
            level, module, listed, current = importing
            dotted = (f"{module}.{ins.argval}" if module else ins.argval) if listed else f"{current}.{ins.argval}"
            if not listed:
                importing = (level, module, listed, dotted)
            local = _stored(instructions, at)
            if local is not None:
                scan.stores.setdefault((level, dotted), set()).add(local)
    for entry in dis.Bytecode(code).exception_entries:
        hasher.update(f"X{bisect.bisect_left(offsets, entry.start)},{bisect.bisect_left(offsets, entry.end)},"
                      f"{bisect.bisect_left(offsets, entry.target)},{entry.depth},{entry.lasti}\n".encode())
    return hasher.hexdigest()


def _const(value: Any, scan: _Code) -> str:
    if isinstance(value, types.CodeType):
        return "code:" + _code_digest(value, scan)
    if isinstance(value, tuple):
        return "(" + ",".join(_const(item, scan) for item in value) + ")"
    if isinstance(value, frozenset):
        return "{" + ",".join(sorted(_const(item, scan) for item in value)) + "}"
    return f"{type(value).__name__}:{value!r}"


class _Unhashable(Exception):
    """A value with no canonical form."""


_MISSING = object()
_ATOMS = (bool, int, float, complex, str, bytes, type(None), type(Ellipsis), type(NotImplemented))
_BUILTIN_CALLABLES = (types.BuiltinFunctionType, types.WrapperDescriptorType, types.MethodDescriptorType,
                      types.ClassMethodDescriptorType, types.MethodWrapperType, types.MemberDescriptorType,
                      types.GetSetDescriptorType)
# Class attributes that say where a class is written or what its source annotates, not
# what it does (a dataclass's fields are its ``__dataclass_fields__``).
_CLASS_SKIPPED = frozenset({"__module__", "__qualname__", "__doc__", "__dict__", "__weakref__", "__annotations__",
                            "__firstlineno__", "__static_attributes__", "__orig_bases__", "__parameters__",
                            "__annotate__", "__annotate_func__", "__annotations_cache__"})
_DEPTH = 48
# A key no later build repeats: a body reaching what nothing can key always runs.
_UNKEYABLE = iter(range(1 << 62))


def _identity(obj: Any) -> str:
    return f"{getattr(obj, '__module__', None)}.{getattr(obj, '__qualname__', getattr(obj, '__name__', '?'))}"


def _hash(parts: list[str]) -> str:
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:32]


class _Node:
    """One function or class reached: the ``(symbol, hash)`` pairs it contributes (its own
    and each global binding its code reads), the functions and classes it reaches, and the
    modules that fall back to their bytes, each with the reason."""

    __slots__ = ("pairs", "children", "fallbacks", "content", "owners")

    def __init__(self) -> None:
        self.pairs: set[tuple] = set()
        self.children: list[Any] = []
        self.fallbacks: list[tuple[tuple[str, Path], str]] = []
        self.content = ""
        # Per pair, the module whose binding or code it is: what a build closure lists it under.
        self.owners: dict[tuple, str | None] = {}

    def add(self, pair: tuple, owner: str | None) -> None:
        self.pairs.add(pair)
        self.owners.setdefault(pair, owner)


class Symbols:
    """One build's resolution of body keys, shared by the build's bodies: what each object
    reached hashes to is worked out once a build, against the namespaces as they are when
    the first body asks. ``loaded`` names the first-party modules the script's load
    imported: a module a function imports inside itself is followed by value only if the
    load imported it (otherwise whether it is in memory would depend on which bodies ran)."""

    def __init__(self, resolved: dict[str, list] | None = None, loaded: set[str] | None = None,
                 base: Path | None = None) -> None:
        self.resolved = {} if resolved is None else resolved
        # The build's folder (the script's): a path value inside it counts relative to it, so
        # a model moved with its folder keeps its key.
        self.base = None if base is None else str(Path(base).resolve())
        self.loaded = set(sys.modules) if loaded is None else loaded
        self._nodes: dict[int, _Node] = {}
        self._held: list[Any] = []
        self._building: set[int] = set()
        self._first_party_modules: dict[str, bool] = {}
        self._closures: dict[tuple[str, Path], str] = {}
        self._stars: dict[str, str | None] = {}
        self._reached: dict[int, tuple] = {}
        self._files: dict[str, str | None] = {}  # per module name, ``_module_file``

    # --- the key -------------------------------------------------------------------------

    def _reach(self, function: Any) -> tuple[set[tuple], dict[tuple, str | None], dict[tuple[str, Path], str]]:
        """What a body's function reaches: its ``(symbol, hash)`` pairs, the module each
        pair is owned by, and the modules that fall back to their bytes, with why. Once a
        build per function."""
        found = self._reached.get(id(function))
        if found is not None:
            return found
        pairs: set[tuple] = set()
        owners: dict[tuple, str | None] = {}
        fallbacks: dict[tuple[str, Path], str] = {}
        seen: set[int] = set()
        pending = [function]
        while pending:
            obj = pending.pop()
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            node = self._node(obj)
            pairs |= node.pairs
            for pair, owner in node.owners.items():
                owners.setdefault(pair, owner)
            for target, reason in node.fallbacks:
                fallbacks.setdefault(target, reason)
            pending.extend(node.children)
        self._held.append(function)
        found = self._reached[id(function)] = (pairs, owners, fallbacks)
        return found

    def key(self, function: Any) -> tuple[str, list[str]]:
        """A body's key and, sorted, the reasons any module of its reach fell back to its
        bytes (or, where no module holds what cannot be keyed, why it always runs)."""
        pairs, _owners, fallbacks = self._reach(function)
        rows = sorted(repr(pair) for pair in pairs)
        for target in sorted(fallbacks):
            found = self._closures.get(target)
            if found is None:
                found = self._closures[target] = closure(target[1], target[0], self.resolved)
            rows.append(f"bytes {target[0]} {found}")
        reasons = sorted(f"{target[0]}: {reason}" for target, reason in fallbacks.items())
        reasons += sorted(f"always runs: {pair[1]}" for pair in pairs if pair[0] == "unkeyable")
        return hashlib.sha256("\n".join(rows).encode()).hexdigest(), reasons

    def modules(self, function: Any) -> tuple[dict[str, str], bool]:
        """A body's closure by file: per first-party module file the script's load imported
        or the body reaches, a digest of what the body reaches in it -- its functions' code
        objects (no lines, no docstrings), its classes, the values its bindings hold -- and,
        for a module that falls back, each file of its import closure by its bytes. A module
        the load imported and the body does not reach holds nothing (the empty digest). And
        whether anything the body reaches cannot be keyed (it always runs). The files
        partition the key (``key``): the key is the same exactly when every file's digest is."""
        from cadgen.engine.kernel.trace import first_party_file

        pairs, owners, fallbacks = self._reach(function)
        root = self._module_file(getattr(function, "__module__", None)) or str(
            Path(function.__code__.co_filename).resolve())
        buckets: dict[str, list[str]] = {}
        for name in self.loaded:
            file = self._module_file(name)
            if file is not None:
                buckets.setdefault(file, [])
        unkeyable = False
        for pair in pairs:
            if pair[0] == "unkeyable":
                unkeyable = True
            file = self._module_file(owners.get(pair)) or root
            buckets.setdefault(file, []).append(repr(pair))
        for target in sorted(fallbacks):
            for file, file_digest in closure_files(target[1], target[0], self.resolved).items():
                buckets.setdefault(str(file), []).append(f"bytes {file_digest}")
        found = {}
        for file, rows in buckets.items():
            if not first_party_file(file):
                continue
            found[file] = hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()[:32]
        return found, unkeyable

    def symbols(self, function: Any) -> dict[str, dict[str, str]]:
        """What ``modules`` digests per file, by name: each binding the body reaches
        (``_CACHE``, a value or what it is bound to) and each function and class of its code
        (``plate``), a short digest of each -- what a build's closure names when a file changed
        (``previous.again``)."""
        from cadgen.engine.kernel.trace import first_party_file

        pairs, owners, _fallbacks = self._reach(function)
        root = self._module_file(getattr(function, "__module__", None)) or str(
            Path(function.__code__.co_filename).resolve())
        # A name is every pair it stands for: a model's binding (``kit:peg``) and its code
        # (``kit.peg``) are one ``peg``, digested together, in an order no hash seed sets.
        rows: dict[str, dict[str, list[str]]] = {}
        for pair in pairs:
            if pair[0] == "unkeyable":
                continue
            owner = owners.get(pair)
            file = self._module_file(owner) or root
            if not first_party_file(file):
                continue
            name = str(pair[0])
            for prefix in ((f"{owner}:", f"{owner}.") if owner else ()):
                if name.startswith(prefix):
                    name = name[len(prefix):]
                    break
            rows.setdefault(file, {}).setdefault(name, []).append(repr(pair))
        return {file: {name: hashlib.sha256("\n".join(sorted(found)).encode()).hexdigest()[:12]
                       for name, found in named.items()} for file, named in rows.items()}

    def _module_file(self, name: str | None) -> str | None:
        """The file a first-party module was loaded from, or None; once per name (a resolution
        is made against one load)."""
        if not name:
            return None
        if name in self._files:
            return self._files[name]
        found = None
        if self._first_party_module(name):
            file = getattr(sys.modules.get(name), "__file__", None)
            found = str(Path(file).resolve()) if file else None
        self._files[name] = found
        return found

    # --- what is first-party ---------------------------------------------------------------

    def _first_party_module(self, name: str | None) -> bool:
        if not name:
            return False
        found = self._first_party_modules.get(name)
        if found is None:
            from cadgen.engine.kernel.trace import first_party_file

            module = sys.modules.get(name)
            found = self._first_party_modules[name] = bool(
                module is not None and first_party_file(getattr(module, "__file__", None) or ""))
        return found

    def _walkable(self, function: types.FunctionType) -> bool:
        """A function whose code is the model's: written in a first-party file, or made at
        run time (a dataclass's ``__init__``) in a first-party module."""
        from cadgen.engine.kernel.trace import first_party_file

        filename = function.__code__.co_filename
        if first_party_file(filename):
            return True
        return filename.startswith("<") and self._first_party_module(function.__module__)

    def _module_target(self, name: str | None, filename: str | None = None) -> tuple[str, Path] | None:
        from cadgen.engine.kernel.trace import first_party_file

        if name:
            module = sys.modules.get(name)
            file = getattr(module, "__file__", None)
            if file and first_party_file(file):
                return name, Path(file).resolve()
            found = self.resolved.get(name)
            if found is None:
                found = self.resolved[name] = _files(name)
            if found:
                return found[-1]
        if filename and first_party_file(filename):
            return name or Path(filename).stem, Path(filename).resolve()
        return None

    def _fallback(self, node: _Node, module: str | None, reason: str, filename: str | None = None) -> None:
        target = self._module_target(module, filename)
        if target is None:
            node.add(("unkeyable", f"{module}: {reason}", next(_UNKEYABLE)), module)
        else:
            node.fallbacks.append((target, reason))

    def _star(self, module: str) -> str | None:
        if module not in self._stars:
            target = self._module_target(module)
            self._stars[module] = None if target is None else _facts(target[1], digest(target[1]))[1]
        return self._stars[module]

    # --- nodes ---------------------------------------------------------------------------

    def _node(self, obj: Any) -> _Node:
        found = self._nodes.get(id(obj))
        if found is not None:
            return found
        self._held.append(obj)  # its id stays its own while the build holds this
        node = _Node()
        self._building.add(id(obj))
        try:
            if isinstance(obj, types.FunctionType):
                self._function(obj, node)
            else:
                self._class(obj, node)
        finally:
            self._building.discard(id(obj))
        self._nodes[id(obj)] = node
        return node

    def _function(self, function: types.FunctionType, node: _Node) -> None:
        from cadgen.engine.kernel.trace import first_party_file

        code = function.__code__
        info = _code(code)
        module = function.__module__
        where = _identity(function)
        parts = [info.digest]
        for label, value in (("defaults", function.__defaults__), ("keyword defaults", function.__kwdefaults__),
                             ("attributes", dict(function.__dict__))):
            parts.append(self._value(value, node, module, f"{where}: {label}", code.co_filename))
        for name, cell in zip(code.co_freevars, function.__closure__ or ()):
            try:
                value = cell.cell_contents
            except ValueError:
                value = _MISSING
            parts.append(name + "=" + self._value(value, node, module, f"{where}: closure variable {name}",
                                                  code.co_filename))
        node.content = _hash(parts)
        node.add((where, node.content), module)
        if first_party_file(code.co_filename):
            path = Path(code.co_filename)
            spots = _facts(path, digest(path))[0]
            for scope in info.codes:
                reason = spots.get(scope)
                if reason is not None:
                    self._fallback(node, module, f"{where}: {reason}", code.co_filename)
                    break
        namespace = function.__globals__
        for chain in info.chains:
            self._bind(namespace, chain, node, where, info)
        for level, name, names in info.imports:
            self._import(namespace, level, name, names, node, where, info)

    def _class(self, cls: type, node: _Node) -> None:
        where = _identity(cls)
        parts = [self._value(base, node, cls.__module__, f"{where}: a base") for base in cls.__bases__]
        if type(cls) is not type:
            parts.append("meta " + self._value(type(cls), node, cls.__module__, f"{where}: its metaclass"))
        for name, value in cls.__dict__.items():
            if name not in _CLASS_SKIPPED:
                parts.append(f"{name}=" + self._value(value, node, cls.__module__, f"{where}.{name}"))
        node.content = _hash(parts)
        node.add((where, node.content), cls.__module__)

    # --- bindings --------------------------------------------------------------------------

    def _bind(self, namespace: dict, chain: tuple, node: _Node, where: str, info: _Code | None = None) -> None:
        """A global name a function's code loads and the attributes it reads off it, while
        what it names is a first-party module: the binding it lands on, by the module that
        holds it, as what it is bound to."""
        local = None
        if chain[-1].startswith("="):
            local, chain = chain[-1][1:], chain[:-1]
        holder = namespace.get("__name__")
        name = chain[0]
        if name in namespace:
            value = namespace[name]
        else:
            holder, value = "builtins", getattr(builtins, name, _MISSING)
        path = f"{holder}:{name}"
        rest = chain[1:]
        while rest and isinstance(value, types.ModuleType) and self._first_party_module(value.__name__):
            holder, attribute, rest = value.__name__, rest[0], rest[1:]
            path = f"{holder}:{attribute}"
            found = value.__dict__.get(attribute, _MISSING)
            if found is _MISSING and "__getattr__" in value.__dict__:
                self._fallback(node, holder, f"{where} reads {path} through the module's __getattr__")
            value = found
        if holder != "builtins" and holder is not None:
            star = self._star(holder)
            if star is not None:
                self._fallback(node, holder, star)
        if isinstance(value, types.ModuleType) and self._first_party_module(value.__name__):
            # The module itself, not an attribute read off it.
            self._module_value(value, path, node, where, info, {local} if local else set())
            return
        node.add((path, self._value(value, node, holder, f"{where} reads {path}")),
                 namespace.get("__name__") if holder == "builtins" else holder)

    def _module_value(self, module: types.ModuleType, path: str, node: _Node, where: str, info: _Code | None,
                      locals_: set[str]) -> None:
        """A first-party module a function holds itself, stored in ``locals_``: followed by
        the attributes the code reads off those locals when that is all it does with them;
        else what is read of it is not seen, and the module falls back."""
        if info is not None and locals_ and not locals_ & info.escapes:
            for local in sorted(locals_):
                for chain in sorted(info.local_chains.get(local, ())):
                    self._bind(module.__dict__, chain, node, where)
        else:
            self._fallback(node, module.__name__, f"{where} holds module {module.__name__} as a value")
        node.add((path, "module:" + module.__name__), module.__name__)

    def _loaded(self, name: str) -> types.ModuleType | None:
        """A module the script's load imported (what a function imports when it runs is in
        memory, for the key, only if it is one)."""
        return sys.modules.get(name) if name in self.loaded else None

    def _import(self, namespace: dict, level: int, name: str, names: tuple, node: _Node, where: str,
                info: _Code) -> None:
        """An import a function makes when it runs: a module the script's load imported is
        followed by the names taken from it, or by the attributes read off the local it is
        stored in; any other first-party one falls back."""
        def absolute(dotted: str) -> str:
            if not level:
                return dotted
            package = namespace.get("__package__") or str(namespace.get("__name__") or "").rpartition(".")[0]
            base = package.split(".") if package else []
            base = base[:len(base) - (level - 1)] if level > 1 else base
            return ".".join([*base, dotted] if dotted else base)

        target = absolute(name)
        if not target or self._module_target(target) is None:
            return
        module = self._loaded(target)
        if "*" in names:
            self._fallback(node, target, f"{where} imports * from {target}")
        elif module is None:
            self._fallback(node, target, f"{where} imports {target} inside a function, and the script's load does not")
        elif names:
            for item in names:
                value = module.__dict__.get(item, _MISSING)
                dotted = f"{name}.{item}" if name else item
                if value is _MISSING and self._module_target(f"{target}.{item}") is not None:
                    self._fallback(node, f"{target}.{item}", f"{where} imports {target}.{item} inside a function, "
                                                             "and the script's load does not")
                elif isinstance(value, types.ModuleType) and self._first_party_module(value.__name__):
                    if self._loaded(value.__name__) is None:
                        self._fallback(node, value.__name__, f"{where} imports {value.__name__} inside a function, "
                                                             "and the script's load does not")
                    else:
                        self._module_value(value, f"{target}:{item}", node, where, info,
                                           info.stores.get((level, dotted), set()))
                else:
                    self._bind(module.__dict__, (item,), node, where)
        else:
            # ``import a.b`` stores a, ``import a.b as c`` stores a.b: each by what is read off it.
            stored = [(dotted, locals_) for (at_level, dotted), locals_ in info.stores.items()
                      if at_level == level and (dotted == name or name.startswith(dotted + "."))]
            if not stored:
                self._fallback(node, target, f"{where} imports {target} inside a function")
            for dotted, locals_ in stored:
                held = self._loaded(absolute(dotted))
                if held is None:
                    self._fallback(node, absolute(dotted), f"{where} imports {target} inside a function, "
                                                           "and the script's load does not")
                else:
                    self._module_value(held, f"import:{held.__name__}", node, where, info, locals_)

    # --- values ----------------------------------------------------------------------------

    def _value(self, value: Any, node: _Node, module: str | None, where: str, filename: str | None = None) -> str:
        """A value's canonical form; one that has none falls its holder's module back."""
        try:
            return self._canonical(value, node, where, 0)
        except _Unhashable as error:
            self._fallback(node, module, f"{where}: {error}", filename)
        except Exception as error:  # noqa: BLE001 - a value that cannot be read is one that cannot be keyed
            self._fallback(node, module, f"{where}: {type(error).__name__} reading it", filename)
        return "?"

    def _canonical(self, value: Any, node: _Node, where: str, depth: int) -> str:
        kind = type(value)
        if kind in _ATOMS:
            return f"{kind.__name__}:{value!r}"
        if value is _MISSING:
            return "missing"
        if depth > _DEPTH:
            raise _Unhashable("nested too deeply")
        depth += 1
        if kind is tuple or kind is list:
            return kind.__name__ + "(" + ",".join(self._canonical(item, node, where, depth) for item in value) + ")"
        if kind is set or kind is frozenset:
            # Sorted: a set's order is its members' hashes', and a string's hash is another in
            # each process, so a key read in another process (``previous``) would differ.
            return kind.__name__ + "{" + ",".join(sorted(self._canonical(item, node, where, depth)
                                                        for item in value)) + "}"
        if kind is dict:
            return "dict{" + ",".join(self._canonical(k, node, where, depth) + ":" + self._canonical(v, node, where, depth)
                                      for k, v in value.items()) + "}"
        if isinstance(value, enum.Enum):
            self._reach_class(kind, node)
            return f"enum:{_identity(kind)}.{value._name_}=" + self._canonical(value._value_, node, where, depth)
        if kind is types.FunctionType:
            return self._function_token(value, node)
        if isinstance(value, type):
            return ("class:" if self._reach_class(value, node) else "ext:") + _identity(value)
        if kind is types.ModuleType:
            if self._first_party_module(value.__name__):
                self._fallback(node, value.__name__, f"{where} holds module {value.__name__} as a value")
            return "module:" + value.__name__
        if getattr(value, "__xbf_model__", False) is True and isinstance(getattr(value, "function", None),
                                                                          types.FunctionType):
            node.children.append(value.function)
            return "model:" + _identity(value.function)
        if isinstance(value, _BUILTIN_CALLABLES) or kind is types.BuiltinMethodType:
            owner = getattr(value, "__self__", None)
            if owner is None or isinstance(owner, (types.ModuleType, type)):
                return "ext:" + _identity(value)
            return f"bound:{_identity(value)}@" + self._canonical(owner, node, where, depth)
        if kind is types.MethodType:
            return ("method:" + self._canonical(value.__func__, node, where, depth) + "@"
                    + self._canonical(value.__self__, node, where, depth))
        if kind is functools.partial:
            return "partial:" + self._canonical((value.func, value.args, value.keywords), node, where, depth)
        if isinstance(value, (staticmethod, classmethod)):
            return kind.__name__ + ":" + self._canonical(value.__func__, node, where, depth)
        if isinstance(value, property):
            return "property:" + self._canonical((value.fget, value.fset, value.fdel), node, where, depth)
        if isinstance(value, functools.cached_property):
            return "cached_property:" + self._canonical(value.func, node, where, depth)
        module = getattr(kind, "__module__", "") or ""
        if module == "dataclasses":
            if kind.__name__ == "Field":
                return "field:" + self._canonical(
                    (value.name, value.default, value.default_factory, value.init, value.repr, value.hash,
                     value.compare, getattr(value, "kw_only", None), str(getattr(value, "_field_type", None))),
                    node, where, depth)
            if kind.__name__ == "_DataclassParams":
                return f"dataclasses:{value!r}"
            if not getattr(value, "__dict__", None) and not callable(value):
                return "dataclasses:" + kind.__name__  # a sentinel (MISSING, a default factory's mark)
        if callable(value) and "__wrapped__" in getattr(value, "__dict__", {}) and not self._first_party_class(kind):
            # A library's wrapper of a function (``functools.cache``): what it wraps.
            return f"wrapped:{_identity(kind)}:" + self._canonical(value.__wrapped__, node, where, depth)
        if isinstance(value, PurePath):
            text = str(value)
            if self.base is not None and value.is_absolute() and (text + os.sep).startswith(self.base + os.sep):
                text = "@" + text[len(self.base):].replace(os.sep, "/")
            return f"path:{kind.__name__}:{text}"
        if kind is types.SimpleNamespace:
            return "namespace:" + self._canonical(dict(vars(value)), node, where, depth)
        top = module.split(".")[0]
        if top == "typing" or kind in (types.GenericAlias, types.UnionType):
            return f"typing:{value!r}"
        if top == "build123d":
            return "build123d:" + _build123d(value)
        if module == "cadgen.engine.materials" and kind.__name__ == "Material":
            return "material:" + repr(value)  # a frozen value of strings and floats
        if top == "numpy":
            return "numpy:" + _numpy(value)
        if self._reach_class(kind, node):
            return f"obj:{_identity(kind)}:" + self._state(value, kind, node, where, depth)
        if top in getattr(sys, "stdlib_module_names", ()) or top == "builtins":
            reduced = value.__reduce_ex__(4)
            if isinstance(reduced, tuple) and 2 <= len(reduced) <= 3:
                return "reduce:" + self._canonical(tuple(reduced), node, where, depth)
        raise _Unhashable(f"a {_identity(kind)}")

    def _state(self, value: Any, kind: type, node: _Node, where: str, depth: int) -> str:
        """An instance of a first-party class: what a built-in base holds (a named tuple's
        items), its attributes and its slots."""
        parts = []
        for base in kind.__mro__[1:]:
            if base is object or self._first_party_class(base):
                continue
            if base in (tuple, list, dict, set, frozenset, int, float, complex, str, bytes):
                parts.append(self._canonical(base(value), node, where, depth))
                break
            raise _Unhashable(f"a {_identity(kind)}, which is a {_identity(base)}")
        attributes = getattr(value, "__dict__", None)
        if attributes:
            parts.append(self._canonical(dict(attributes), node, where, depth))
        for cls in kind.__mro__:
            slots = cls.__dict__.get("__slots__", ())
            for slot in ((slots,) if isinstance(slots, str) else slots):
                if slot not in ("__dict__", "__weakref__"):
                    parts.append(slot + "=" + self._canonical(getattr(value, slot, _MISSING), node, where, depth))
        return "(" + ",".join(parts) + ")"

    def _first_party_class(self, cls: type) -> bool:
        return self._first_party_module(getattr(cls, "__module__", None))

    def _reach_class(self, cls: type, node: _Node) -> bool:
        if self._first_party_class(cls):
            node.children.append(cls)
            return True
        return False

    def _function_token(self, function: types.FunctionType, node: _Node) -> str:
        identity = _identity(function)
        if not self._walkable(function):
            return "ext:" + identity
        node.children.append(function)
        if "<locals>" in identity or "<lambda>" in identity:
            # A name more than one function can have (a factory's): by what it is, too.
            if id(function) in self._building:
                return "fn:" + identity
            return f"fn:{identity}#{self._node(function).content}"
        return "fn:" + identity


def _build123d(value: Any) -> str:
    """A build123d value that is a few numbers; a shape (or anything else) has no
    canonical form."""
    name = type(value).__name__
    if name in ("Vector", "Color"):
        return f"{name}{tuple(value)!r}"
    if name == "Location":
        matrix = value.wrapped.Transformation()
        return f"Location{tuple(matrix.Value(row, column) for row in (1, 2, 3) for column in (1, 2, 3, 4))!r}"
    if name == "Axis":
        return f"Axis{(tuple(value.position), tuple(value.direction))!r}"
    if name == "Plane":
        return f"Plane{(tuple(value.origin), tuple(value.x_dir), tuple(value.z_dir))!r}"
    raise _Unhashable(f"a build123d {name}")


def _numpy(value: Any) -> str:
    name = type(value).__name__
    if name == "ndarray" and not value.dtype.hasobject:
        return f"ndarray:{value.dtype.str}:{value.shape}:{hashlib.sha256(value.tobytes()).hexdigest()}"
    if getattr(value, "shape", None) == () and hasattr(value, "dtype"):
        return f"{name}:{value!r}"
    raise _Unhashable(f"a numpy {name}")
