from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from pathlib import Path


class InvalidModelScriptError(ValueError):
    """A script whose model DECLARATION is malformed in a way directory
    discovery should skip-with-a-note rather than abort on (e.g. two models in
    one file). Contract violations inside a single model (a dict return,
    bad decorator arguments) stay plain ValueErrors and DO abort, because an
    explicitly-targeted build must fail loudly."""


@dataclass(frozen=True)
class GeneratorMetadata:
    script_path: Path
    display_name: str | None
    generator_names: tuple[str, ...]
    # The decorator kind this model script declares: "step" (@step) or "dxf" (@dxf).
    format: str
    mesh_tolerance: float | None
    mesh_angular_tolerance: float | None
    # Library-first fields (design/library-first-generation.md): the @step/@dxf
    # decorated entry function and its statically-declared output target.
    entry_function: str | None = None
    out_target: str | None = None
    is_decorated: bool = False
    # Declared mesh serializations (@stl/@glb/@threemf stacked on the @step
    # function). Statically parsed like out=; resolved to paths at spec time.
    mesh_exports: "tuple[MeshExportDecl, ...]" = ()
    # False for a MESH-ONLY model (mesh decorators, no @step): a model like any
    # other whose .step is not among its outputs and is never written.
    step_output: bool = True


@dataclass(frozen=True)
class MeshExportDecl:
    """One declared mesh export: `@stl(out=..., mesh_tolerance=...)` etc.

    ``fmt`` is the FORMAT name ("stl" | "3mf" | "glb"); the 3MF decorator is
    spelled ``@threemf`` (identifiers cannot start with a digit). ``out``
    is the raw script-relative target, ``None`` meaning the sibling of the
    logical STEP artifact. Tolerances ``None`` inherit the model's policy."""

    fmt: str
    out: str | None = None
    mesh_tolerance: float | None = None
    mesh_angular_tolerance: float | None = None
    # Runtime-only (never parsed from AST): the declaration's OWN kinematics.
    # Each mesh declaration stands alone — it never reads @step's kinematics.
    kinematics: object | None = None



def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def normalize_mesh_numeric(value: object, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if normalized <= 0.0:
        raise ValueError(f"{field_name} must be greater than 0")
    return normalized


def resolve_model_output_path(
    script_path: Path, *, fmt: str, explicit_out: str | None = None, function: str | None = None
) -> Path:
    """Where a model's primary artifact goes. cadgen is deliberately
    UNOPINIONATED about layout: an explicit ``out=`` resolves relative to the
    script's own folder (absolute allowed); otherwise the artifact is the sibling
    ``<function>.<fmt>`` -- the model's own name, which for the one-model-per-file
    convention is the file's stem. Project structure conventions live in the cad
    skill's project-layout reference as guidance, not in code."""
    script = Path(script_path).resolve()
    if explicit_out:
        target = Path(explicit_out)
        return (target if target.is_absolute() else script.parent / target).resolve()
    # A file's sole model writes `<file>.<fmt>` (what `python bracket.py` is expected
    # to leave beside it, whatever the function is called); models SHARING a file
    # each write `<function>.<fmt>`, so two models never collide on one default.
    stem = script.stem
    if function and function != stem and len(model_function_names(script)) > 1:
        stem = function
    return (script.parent / f"{stem}.{fmt}").resolve()


_MESH_DECORATOR_NAMES = ("stl", "glb", "threemf")
_MESH_DECORATOR_FMT = {"stl": "stl", "glb": "glb", "threemf": "3mf"}


def _cadgen_decorator_aliases(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    """Local names bound to cadgen's model/export decorators, and local
    names bound to the cadgen module itself (for ``@cadgen.step(...)``)."""
    names: dict[str, str] = {}
    module_aliases: set[str] = set()
    tracked = {"step", "dxf", *_MESH_DECORATOR_NAMES}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in {"cadgen", "cadgen.authoring"}:
            for alias in node.names:
                if alias.name in tracked:
                    names[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "cadgen":
                    module_aliases.add(alias.asname or "cadgen")
    return names, module_aliases


def _match_model_decorator(
    function: ast.FunctionDef,
    names: dict[str, str],
    module_aliases: set[str],
) -> tuple[str, dict[str, ast.expr], bool] | None:
    """(fmt, decorator kwargs, mesh_only) when the function carries a cadgen model
    decorator. ``@step``/``@dxf`` name the format; mesh decorators alone
    (``@stl``/``@glb``/``@threemf`` with no ``@step``) declare a MESH-ONLY model:
    format "step" — the same tree and record — whose .step is never written."""
    mesh_only = False
    for decorator in function.decorator_list:
        call_kwargs: dict[str, ast.expr] = {}
        target = decorator
        if isinstance(decorator, ast.Call):
            target = decorator.func
            for keyword in decorator.keywords:
                if keyword.arg is not None:
                    call_kwargs[keyword.arg] = keyword.value
        fmt: str | None = None
        if isinstance(target, ast.Name):
            # Only MODEL formats may match here. `names` tracks all five
            # decorator aliases, so an unrestricted get() let the first
            # cadgen decorator top-down win — a mesh decorator stacked ABOVE
            # @step was mis-taken as the model format, breaking the
            # documented stacking-order neutrality (runtime was neutral, the
            # parser was not).
            resolved = names.get(target.id)
            if resolved in {"step", "dxf"}:
                fmt = resolved
            elif resolved in _MESH_DECORATOR_NAMES:
                mesh_only = True
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            if target.value.id in module_aliases and target.attr in {"step", "dxf"}:
                fmt = target.attr
            elif target.value.id in module_aliases and target.attr in _MESH_DECORATOR_NAMES:
                mesh_only = True
        if fmt is not None:
            return fmt, call_kwargs, False
    if mesh_only:
        return "step", {}, True
    return None


_FUNCTION_NAMES_CACHE: dict[str, tuple[tuple[int, int], tuple[str, ...]]] = {}


def model_function_names(script_path: Path | str) -> tuple[str, ...]:
    """The decorated model functions a script declares, in file order. Cached
    on (mtime, size); ``()`` for a script that declares none or cannot be read."""
    script = Path(script_path)
    try:
        stat = script.stat()
    except OSError:
        return ()
    stamp = (stat.st_mtime_ns, stat.st_size)
    key = str(script)
    cached = _FUNCTION_NAMES_CACHE.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    try:
        tree = ast.parse(script.read_text(), filename=str(script))
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
        return ()
    decorator_names, module_aliases = _cadgen_decorator_aliases(tree)
    names = tuple(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and _match_model_decorator(node, decorator_names, module_aliases) is not None
    )
    _FUNCTION_NAMES_CACHE[key] = (stamp, names)
    return names


def parse_all_generator_metadata(script_path: Path) -> tuple[GeneratorMetadata, ...]:
    """Every model a script declares, one GeneratorMetadata each, in file order."""
    return tuple(
        parse_generator_metadata(script_path, function=name) for name in model_function_names(script_path)
    )


def parse_generator_metadata(script_path: Path, function: str | None = None) -> GeneratorMetadata | None:
    """The model ``function`` declares in ``script_path`` -- or the file's sole
    model when ``function`` is None. A file may hold several models (each its own
    record, output and job); asking for "the" model of such a file names none, so
    it is an error: spell the model as ``script.py::function``."""
    try:
        tree = ast.parse(script_path.read_text(), filename=str(script_path))
    except (FileNotFoundError, SyntaxError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Failed to parse {_display_path(script_path)}") from exc

    display_name: str | None = None
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if isinstance(target, ast.Name) and value is not None:
            if target.id == "DISPLAY_NAME" and isinstance(value, ast.Constant) and isinstance(value.value, str):
                display_name = value.value.strip()

    decorator_names, module_aliases = _cadgen_decorator_aliases(tree)
    decorated: list[tuple[ast.FunctionDef, str, dict[str, ast.expr], bool]] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        match = _match_model_decorator(node, decorator_names, module_aliases)
        if match is not None:
            decorated.append((node, match[0], match[1], match[2]))

    if not decorated:
        return None
    if function is not None:
        chosen = [entry for entry in decorated if entry[0].name == function]
        if not chosen:
            declared = ", ".join(f"{fn.name}()" for fn, _, _, _ in decorated)
            raise InvalidModelScriptError(
                f"{_display_path(script_path)} declares no model {function}() (it declares {declared})"
            )
        decorated = chosen
    elif len(decorated) > 1:
        joined = ", ".join(f"{fn.name}()" for fn, _, _, _ in decorated)
        raise InvalidModelScriptError(
            f"{_display_path(script_path)} declares several models ({joined}); name one as "
            f"{_display_path(script_path)}::{decorated[0][0].name}"
        )

    function, fmt, _call_kwargs, mesh_only = decorated[0]
    params = [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
        *([function.args.vararg] if function.args.vararg else []),
        *([function.args.kwarg] if function.args.kwarg else []),
    ]
    if params:
        listed = ", ".join(p.arg for p in params)
        raise ValueError(
            f"{_display_path(script_path)} {function.name}() takes no parameters (got: "
            f"{listed}). A model is one configuration of one output: move the parameters "
            f"to a plain factory function and have {function.name}() call it with the "
            "values this model uses; a different configuration is a different model."
        )

    # A @dxf return carries no static metadata: the drawing IS its geometry, and
    # what a layer map holds is only knowable at run time. A @step return is
    # checked for SHAPE only (one bare value, never a dict): what it returns is
    # the geometry, and no decorator argument describes or changes it.
    if fmt == "step":
        _check_step_return(script_path=script_path, function=function)

    # The decorator's ARGUMENTS are ordinary Python, evaluated when the module is
    # imported: `out=NAME + ".step"`, an f-string, a constant from lib/. Nothing
    # is read off the source text; the imported model declares them.
    defn = imported_model(script_path, function.name)
    return GeneratorMetadata(
        script_path=script_path.resolve(),
        display_name=display_name,
        generator_names=(function.name,),
        format=defn.fmt,
        mesh_tolerance=defn.mesh_tolerance,
        mesh_angular_tolerance=defn.mesh_angular_tolerance,
        entry_function=function.name,
        out_target=defn.out,
        is_decorated=True,
        mesh_exports=tuple(defn.mesh_exports),
        step_output=bool(defn.step_output),
    )


def _script_stamp(script_path: Path) -> tuple[int, int] | None:
    try:
        stat = Path(script_path).stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def imported_model(script_path: Path, function: str):
    """The ModelDef ``function`` registered when ``script_path`` was imported.

    The registry entry is reused when it was made from the bytes now on disk
    (same mtime and size); otherwise the module is imported by path -- under a
    loader name, so its ``__main__`` block does not run -- and read again. The
    module top must stay kernel-free, as the cad skill requires: this import is
    what every door pays to learn a model's declarations."""
    from cadgen.authoring import registered_model

    resolved = Path(script_path).resolve()
    stamp = _script_stamp(resolved)
    defn = registered_model(resolved, function)
    if defn is None or getattr(defn, "stamp", None) != stamp:
        from cadgen._internal.generation_runner import _load_generator_module

        _load_generator_module(resolved)
        defn = registered_model(resolved, function)
    if defn is None:
        raise InvalidModelScriptError(
            f"{_display_path(resolved)} declares {function}() but importing it registered no such model"
        )
    return defn


def _check_step_return(
    *,
    script_path: Path,
    function: ast.FunctionDef,
) -> None:
    """A @step returns ONE build123d shape and nothing else.

    A dict return is refused here, statically, with the decorators that replaced
    the old ``{"shape": ..., "stl": ...}`` envelope named in the message; the
    runtime check in ``generation_runner`` says the same thing for a dict that
    only appears at run time. Nothing else about the return is inferred: how the
    build packages the geometry follows the shape it actually gets.
    """
    for node in ast.walk(function):
        if not isinstance(node, ast.Return):
            continue
        if node.value is None or (isinstance(node.value, ast.Constant) and node.value.value is None):
            raise ValueError(
                f"{_display_path(script_path)} {function.name}() must return a build123d shape"
            )
        if isinstance(node.value, ast.Dict):
            raise ValueError(
                f"{_display_path(script_path)} {function.name}() returns a dict; a @step "
                "model returns a build123d shape and nothing else. Declare mesh exports "
                "with @stl/@threemf/@glb stacked on the model and tolerances with "
                "@step(mesh_tolerance=..., mesh_angular_tolerance=...)."
            )


def _call_tail_name(function: ast.expr) -> str | None:
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def _is_nonempty_expression(expression: ast.expr) -> bool:
    if isinstance(expression, ast.Constant) and expression.value is None:
        return False
    if isinstance(expression, (ast.List, ast.Tuple, ast.Set)):
        return bool(expression.elts)
    return True


def _is_multi_item_sequence_expression(
    expression: ast.expr,
    *,
    local_assignments: dict[str, ast.expr],
    seen_names: set[str] | None = None,
) -> bool:
    if isinstance(expression, ast.Name):
        seen_names = set(seen_names or set())
        if expression.id in seen_names:
            return False
        target = local_assignments.get(expression.id)
        if target is None:
            return False
        seen_names.add(expression.id)
        return _is_multi_item_sequence_expression(
            target,
            local_assignments=local_assignments,
            seen_names=seen_names,
        )
    if isinstance(expression, (ast.List, ast.Tuple, ast.Set)):
        return len(expression.elts) > 1
    return False



