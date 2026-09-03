from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from pathlib import Path


class InvalidModelScriptError(ValueError):
    """A script whose model DECLARATION is malformed in a way directory
    discovery should skip-with-a-note rather than abort on (e.g. two models in
    one file). Contract violations inside a single model (bad envelope fields,
    bad decorator arguments) stay plain ValueErrors and DO abort, because an
    explicitly-targeted build must fail loudly."""


@dataclass(frozen=True)
class GeneratorMetadata:
    script_path: Path
    kind: str
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
    # Runtime-only (never parsed from AST): the declaration's OWN kinematics
    # and the resolved {dof: value} bake pose. Each mesh declaration stands
    # alone — it never reads @step's kinematics.
    kinematics: object | None = None
    bake_pose: dict | None = None


STEP_ENVELOPE_FIELDS = {
    "shape",
    "stl",
    "3mf",
    "mesh_tolerance",
    "mesh_angular_tolerance",
}


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


def resolve_model_output_path(script_path: Path, *, fmt: str, explicit_out: str | None = None) -> Path:
    """Where a model's primary artifact goes. cadgen is deliberately
    UNOPINIONATED about layout (design/library-first-generation.md): an explicit
    ``out=`` resolves relative to the script's own folder (absolute allowed);
    otherwise the artifact is the sibling ``<stem>.<fmt>``. Project structure
    conventions live in the cad-project skill as guidance, not in code."""
    script = Path(script_path).resolve()
    if explicit_out:
        target = Path(explicit_out)
        return (target if target.is_absolute() else script.parent / target).resolve()
    return (script.parent / f"{script.stem}.{fmt}").resolve()


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


def _match_mesh_export_decorators(
    function: ast.FunctionDef,
    names: dict[str, str],
    module_aliases: set[str],
    *,
    script_path: Path,
) -> "tuple[MeshExportDecl, ...]":
    """The function's stacked ``@stl``/``@glb``/``@threemf`` declarations.

    AST scanning sees the whole ``decorator_list``, so stacking order (above
    or below ``@step``) is irrelevant here by construction. Duplicate formats
    fail loudly."""
    declarations: list[MeshExportDecl] = []
    for decorator in function.decorator_list:
        call_kwargs: dict[str, ast.expr] = {}
        target = decorator
        if isinstance(decorator, ast.Call):
            target = decorator.func
            for keyword in decorator.keywords:
                if keyword.arg is not None:
                    call_kwargs[keyword.arg] = keyword.value
        deco_name: str | None = None
        if isinstance(target, ast.Name):
            resolved = names.get(target.id)
            if resolved in _MESH_DECORATOR_NAMES:
                deco_name = resolved
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            if target.value.id in module_aliases and target.attr in _MESH_DECORATOR_NAMES:
                deco_name = target.attr
        if deco_name is None:
            continue
        fmt = _MESH_DECORATOR_FMT[deco_name]
        out = _decorator_string_kwarg(call_kwargs, "out", script_path=script_path)
        # Variants are allowed: the same format may be declared repeatedly at
        # different destinations (e.g. a draft and a print-quality STL). Only
        # ambiguous duplicates fail: two bare declarations collide at the
        # sibling default, and two identical out= targets collide outright.
        if out is None and any(d.fmt == fmt and d.out is None for d in declarations):
            raise ValueError(
                f"{_display_path(script_path)} declares bare @{deco_name} more than once; "
                "at most one declaration per format may omit out= (the sibling default)"
            )
        if out is not None and any(d.fmt == fmt and d.out == out for d in declarations):
            raise ValueError(
                f"{_display_path(script_path)} declares @{deco_name} twice for the same "
                f"target {out!r}"
            )
        if out is not None and not out.lower().endswith(f".{fmt}" if fmt != "3mf" else ".3mf"):
            raise ValueError(
                f"{_display_path(script_path)} @{deco_name} out= must end with "
                f"'.{fmt}': {out!r}"
            )
        declarations.append(
            MeshExportDecl(
                fmt=fmt,
                out=out,
                mesh_tolerance=_decorator_numeric_kwarg(
                    call_kwargs, "mesh_tolerance", script_path=script_path
                ),
                mesh_angular_tolerance=_decorator_numeric_kwarg(
                    call_kwargs, "mesh_angular_tolerance", script_path=script_path
                ),
            )
        )
    return tuple(declarations)


def _match_model_decorator(
    function: ast.FunctionDef,
    names: dict[str, str],
    module_aliases: set[str],
) -> tuple[str, dict[str, ast.expr]] | None:
    """(fmt, decorator kwargs) when the function carries a cadgen @step/@dxf."""
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
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            if target.value.id in module_aliases and target.attr in {"step", "dxf"}:
                fmt = target.attr
        if fmt is not None:
            return fmt, call_kwargs
    return None


def _decorator_string_kwarg(
    kwargs: dict[str, ast.expr], key: str, *, script_path: Path
) -> str | None:
    node = kwargs.get(key)
    if node is None:
        return None
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or not node.value.strip():
        raise ValueError(
            f"{_display_path(script_path)} @step/@dxf {key}= must be a non-empty string literal"
        )
    if "\\" in node.value:
        raise ValueError(
            f"{_display_path(script_path)} @step/@dxf {key}= must use POSIX '/' separators"
        )
    return node.value.strip()


def _decorator_numeric_kwarg(
    kwargs: dict[str, ast.expr], key: str, *, script_path: Path
) -> float | None:
    node = kwargs.get(key)
    if node is None:
        return None
    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError) as exc:
        raise ValueError(
            f"{_display_path(script_path)} @step {key}= must be a numeric literal"
        ) from exc
    return normalize_mesh_numeric(value, field_name=key)


def parse_generator_metadata(script_path: Path) -> GeneratorMetadata | None:
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
    decorated: list[tuple[ast.FunctionDef, str, dict[str, ast.expr]]] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        match = _match_model_decorator(node, decorator_names, module_aliases)
        if match is not None:
            decorated.append((node, match[0], match[1]))

    if not decorated:
        return None
    if len(decorated) > 1:
        joined = ", ".join(f"{fn.name}()" for fn, _, _ in decorated)
        raise InvalidModelScriptError(
            f"{_display_path(script_path)} defines more than one CAD model ({joined}); "
            "a model file defines exactly one @step or @dxf entry"
        )

    function, fmt, call_kwargs = decorated[0]
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

    out_target = _decorator_string_kwarg(call_kwargs, "out", script_path=script_path)
    kind: str | None = None
    # A @dxf return carries no static metadata: the drawing IS its geometry, and
    # what a layer map holds is only knowable at run time (design/dxf-build123d.md).
    # @step still parses its return, because `kind` must be known before the build.
    if fmt == "step":
        kind = _decorator_string_kwarg(call_kwargs, "kind", script_path=script_path)
        if kind is not None and kind not in {"part", "assembly"}:
            raise ValueError(
                f"{_display_path(script_path)} @step kind= must be 'part' or 'assembly'"
            )
        if kind is None:
            try:
                kind = _parse_step_return_metadata(script_path=script_path, function=function)
            except ValueError as exc:
                # A return shape the inference cannot read needs an explicit kind;
                # a genuinely invalid envelope keeps its own pointed error.
                if "must return one value" not in str(exc):
                    raise
                raise ValueError(
                    f"{_display_path(script_path)} {function.name}() kind could not be "
                    "inferred from its return; declare it explicitly: @step(kind=...)"
                ) from exc

    mesh_exports = _match_mesh_export_decorators(
        function, decorator_names, module_aliases, script_path=script_path
    )
    if fmt == "dxf" and mesh_exports:
        raise ValueError(
            f"{_display_path(script_path)} stacks a mesh export decorator on a @dxf "
            "drawing; STL/3MF/GLB derive from a @step model's geometry"
        )
    return GeneratorMetadata(
        script_path=script_path.resolve(),
        kind=kind,
        display_name=display_name,
        generator_names=(function.name,),
        format=fmt,
        mesh_tolerance=_decorator_numeric_kwarg(call_kwargs, "mesh_tolerance", script_path=script_path),
        mesh_angular_tolerance=_decorator_numeric_kwarg(
            call_kwargs, "mesh_angular_tolerance", script_path=script_path
        ),
        entry_function=function.name,
        out_target=out_target,
        is_decorated=True,
        mesh_exports=mesh_exports,
    )


def _parse_step_return_metadata(
    *,
    script_path: Path,
    function: ast.FunctionDef,
) -> str:
    return_node = _single_return_value(script_path=script_path, function=function)
    local_assignments = _function_local_assignments(function)
    if not isinstance(return_node, ast.Dict):
        return _parse_bare_step_return(
            script_path=script_path,
            function=function,
            return_node=return_node,
            local_assignments=local_assignments,
        )

    envelope = _parse_literal_return_envelope(script_path=script_path, function=function)
    _reject_unsupported_fields(
        script_path=script_path,
        function_name=function.name,
        envelope=envelope,
        allowed_fields=STEP_ENVELOPE_FIELDS,
    )
    if "shape" not in envelope:
        raise ValueError(
            f"{_display_path(script_path)} @step envelope must define 'shape'"
        )
    return (
        "assembly"
        if _is_compound_assembly_expression(
            envelope["shape"],
            local_assignments=local_assignments,
        )
        else "part"
    )


def _parse_bare_step_return(
    *,
    script_path: Path,
    function: ast.FunctionDef,
    return_node: ast.expr,
    local_assignments: dict[str, ast.expr] | None = None,
) -> str:
    if _is_compound_assembly_expression(
        return_node,
        local_assignments=local_assignments or {},
    ):
        return "assembly"
    if isinstance(return_node, ast.Constant) and return_node.value is None:
        raise ValueError(
            f"{_display_path(script_path)} {function.name}() must return a build123d shape "
            "or a {'shape': ...} envelope"
        )
    return "part"


def _function_local_assignments(function: ast.FunctionDef) -> dict[str, ast.expr]:
    assignments: dict[str, ast.expr] = {}
    for statement in function.body:
        if isinstance(statement, ast.Return):
            break
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            value = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.value, ast.expr):
            target = statement.target
            value = statement.value
        if isinstance(target, ast.Name) and value is not None:
            assignments[target.id] = value
    return assignments


def _is_compound_assembly_expression(
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
        return _is_compound_assembly_expression(
            target,
            local_assignments=local_assignments,
            seen_names=seen_names,
        )
    if not isinstance(expression, ast.Call) or _call_tail_name(expression.func) != "Compound":
        return False
    if expression.args and _is_multi_item_sequence_expression(
        expression.args[0],
        local_assignments=local_assignments,
    ):
        return True
    for keyword in expression.keywords:
        if keyword.arg == "children" and _is_nonempty_expression(keyword.value):
            return True
        if keyword.arg == "obj" and _is_multi_item_sequence_expression(
            keyword.value,
            local_assignments=local_assignments,
        ):
            return True
    return False


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


def _parse_literal_return_envelope(
    *,
    script_path: Path,
    function: ast.FunctionDef,
) -> dict[str, ast.expr]:
    value = _single_return_value(script_path=script_path, function=function)
    if not isinstance(value, ast.Dict):
        raise ValueError(
            f"{_display_path(script_path)} {function.name}() must return a generator envelope dict"
        )
    envelope: dict[str, ast.expr] = {}
    for key_node, value_node in zip(value.keys, value.values, strict=True):
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            raise ValueError(
                f"{_display_path(script_path)} {function.name}() envelope keys must be string literals"
            )
        key = key_node.value
        if key in envelope:
            raise ValueError(
                f"{_display_path(script_path)} {function.name}() envelope duplicate field: {key}"
            )
        envelope[key] = value_node
    return envelope


def _single_return_value(
    *,
    script_path: Path,
    function: ast.FunctionDef,
) -> ast.expr:
    returns = [statement for statement in function.body if isinstance(statement, ast.Return)]
    if len(returns) != 1 or returns[0].value is None:
        raise ValueError(
            f"{_display_path(script_path)} {function.name}() must return one value"
        )
    return returns[0].value


def _reject_unsupported_fields(
    *,
    script_path: Path,
    function_name: str,
    envelope: dict[str, ast.expr],
    allowed_fields: set[str],
) -> None:
    extra_fields = sorted(key for key in envelope if key not in allowed_fields)
    if extra_fields:
        joined = ", ".join(extra_fields)
        supported = ", ".join(sorted(allowed_fields))
        raise ValueError(
            f"{_display_path(script_path)} {function_name}() envelope has unsupported "
            f"field(s): {joined}; supported fields: {supported}"
        )


def _literal_field(
    *,
    script_path: Path,
    function_name: str,
    envelope: dict[str, ast.expr],
    field_name: str,
) -> object | None:
    if field_name not in envelope:
        return None
    try:
        return ast.literal_eval(envelope[field_name])
    except (ValueError, SyntaxError) as exc:
        raise ValueError(
            f"{_display_path(script_path)} {function_name}() envelope {field_name} must be a literal"
        ) from exc


def _parse_path_field(
    *,
    script_path: Path,
    function_name: str,
    envelope: dict[str, ast.expr],
    field_name: str,
) -> str | None:
    value = _literal_field(
        script_path=script_path,
        function_name=function_name,
        envelope=envelope,
        field_name=field_name,
    )
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{_display_path(script_path)} {function_name}() envelope {field_name} "
            "must be a non-empty string"
        )
    if "\\" in value:
        raise ValueError(
            f"{_display_path(script_path)} {function_name}() envelope {field_name} "
            "must use POSIX '/' separators"
        )
    return value.strip()
