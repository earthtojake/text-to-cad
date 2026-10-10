from __future__ import annotations

import ast
import math
import time
from dataclasses import dataclass
from pathlib import Path

from cadgen.coordination.kinds import DRAWING_PACKAGE, HARNESS_PACKAGE, PCB_PACKAGE, STEP_PACKAGE, ArtifactKind
from cadgen.render import relative_to_cwd as _display_path
from cadgen.file_types import extension_of


@dataclass(frozen=True)
class ModelFormat:
    """What a model's format -- the decorator that declares it -- is to the rest of cadgen.

    A format with ``tree_less`` has no geometry tree: its record's tree is null, its
    document is its output, and called inside another build it is just its body. A
    board with a 3D export is not one: it is format "step", its tree the populated board.
    """

    name: str  # the decorator: "step", "dxf", "pcb", "harness"
    suffix: str  # its document's: ``<name>.step``, ``.dxf``, ``.kicad_pcb``, ``.harness.yml``
    kind: str  # its document's format, as the viewer, snapshots and telemetry name it
    tree_less: bool
    spec_path: str  # the CadSource/EntrySpec field that holds the document
    package: ArtifactKind  # the phase set its build reports over
    document: str  # what its document is, as a refusal names it ("not a CAD DXF output path")
    wrote: str  # what its build's summary line names ("wrote DXF: ...")
    # A tree-less build's record entryKind and its JSON result's "kind".
    record_kind: str = ""


MODEL_FORMATS = {
    fmt.name: fmt
    for fmt in (
        ModelFormat("step", ".step", "step", False, "step_path", STEP_PACKAGE, "STEP", "STEP"),
        ModelFormat("dxf", ".dxf", "dxf", True, "dxf_path", DRAWING_PACKAGE, "CAD DXF", "DXF", "drawing"),
        ModelFormat("pcb", ".kicad_pcb", "kicad_pcb", True, "pcb_path", PCB_PACKAGE, "KiCad board", "KiCad project", "pcb"),
        ModelFormat(
            "harness", ".harness.yml", "harness", True, "harness_path", HARNESS_PACKAGE, "harness document", "harness", "harness"
        ),
    )
}
TREE_LESS_FORMATS = frozenset(name for name, fmt in MODEL_FORMATS.items() if fmt.tree_less)


def format_named(name: str | None) -> ModelFormat:
    """The format ``name``; a mesh-only model, or no name, is a STEP model's."""
    return MODEL_FORMATS.get(str(name or ""), MODEL_FORMATS["step"])


@dataclass(frozen=True)
class DocumentWritten:
    """What a tree-less model's writer wrote: its document and every file beside it."""

    paths: tuple[Path, ...]

    @property
    def facts(self) -> dict[Path, dict[str, object]]:
        """What a door reads off an output's record entry beside its hash, by path."""
        return {}


class InvalidModelScriptError(ValueError):
    """A script whose model DECLARATION is malformed in a way directory
    discovery should skip-with-a-note rather than abort on (e.g. a file holding
    several models named without its ``::function``). Contract violations inside a single model (a dict return,
    bad decorator arguments) stay plain ValueErrors and DO abort, because an
    explicitly-targeted build must fail loudly."""


@dataclass(frozen=True)
class GeneratorMetadata:
    script_path: Path
    display_name: str | None
    generator_names: tuple[str, ...]
    # The decorator kind this model script declares: "step" (@step), "dxf" (@dxf), "pcb" (@pcb)
    # or "harness" (@harness).
    format: str
    mesh_tolerance: float | None
    mesh_angular_tolerance: float | None
    # Library-first fields: the @step/@dxf decorated entry function and its
    # statically-declared output target.
    entry_function: str | None = None
    out_target: str | None = None
    is_decorated: bool = False
    # Declared mesh serializations (@stl/@glb/@threemf stacked on the @step
    # function). Statically parsed like out=; resolved to paths at spec time.
    mesh_exports: "tuple[MeshExportDecl, ...]" = ()
    # False for a MESH-ONLY model (mesh decorators, no @step): a model like any
    # other whose .step is not among its outputs and is never written.
    step_output: bool = True
    materials: object | None = None
    animation: object | None = None
    # A @pcb board (see cadgen.authoring.ModelDef.board): its KiCad project is among
    # the outputs, at ``pcb_out_target`` (else the sibling ``<name>.kicad_pcb``).
    board: bool = False
    pcb_out_target: str | None = None
    # Declared manufacturing exports: a board's @pcb(gerber=, bom=, pos=), a harness's @harness(bom=).
    fab_exports: "tuple[FabExportDecl, ...]" = ()


@dataclass(frozen=True)
class FabExportDecl:
    """One declared manufacturing export: ``@pcb(gerber=, bom=, pos=)`` or ``@harness(bom=)``.

    ``out`` is the raw script-relative target, ``None`` meaning the sibling of the
    board file (``board.gerbers.zip``, ``board.bom.csv``, ``board.pos.csv``)."""

    fmt: str
    out: str | None = None


#: The file a manufacturing export writes beside its board by default.
FAB_SUFFIX = {"gerber": ".gerbers.zip", "bom": ".bom.csv", "pos": ".pos.csv"}


def fab_output_path(script_path: Path | str, decl: "FabExportDecl", board_file: Path) -> Path:
    """Where a declared manufacturing export lands (``out=`` resolves against the script)."""
    if decl.out:
        target = Path(decl.out)
        return (target if target.is_absolute() else Path(script_path).resolve().parent / target).resolve()
    return fab_sibling(board_file, decl.fmt).resolve()


def fab_sibling(document: Path, fmt: str) -> Path:
    """The ``fmt`` export's default file: beside the document, named by its stem
    (``board.kicad_pcb`` -> ``board.bom.csv``, ``cable.harness.yml`` -> ``cable.bom.csv``)."""
    return document.with_name(document.name[: -len(extension_of(document)) or None] + FAB_SUFFIX[fmt])


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



# The largest chord tolerance the tessellator honours. The value is RELATIVE --
# a fraction of each component's bounding diagonal -- so 0.05 already lets a
# facet sit a twentieth of the whole part away from the true surface. Past it the
# tessellator's base grid collapses to a cell or two while its fixed angular
# criterion keeps bisecting the slivers that leaves: a 10x20 cylinder comes out
# with MORE triangles and a worse volume than at the default (464 triangles at
# 1.5e-3; 13 000 at 0.2; 20% of the volume missing at 1.0), at exit 0. A number
# that large is, in practice, an absolute millimetre deflection carried over from
# a mesher that took one.
MESH_TOLERANCE_MAX = 0.05


def normalize_mesh_numeric(value: object, *, field_name: str) -> float | None:
    """The ONE validator of a mesh tolerance, wherever it enters: a decorator
    argument, a model run's flag, a format door's flag or keyword."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if normalized <= 0.0:
        raise ValueError(f"{field_name} must be greater than 0")
    if field_name == "mesh_tolerance" and normalized > MESH_TOLERANCE_MAX:
        raise ValueError(
            f"mesh_tolerance {normalized:g} is too large: the value is RELATIVE to each "
            "component's bounding diagonal, not millimetres, so it must be at most "
            f"{MESH_TOLERANCE_MAX:g} (default 1.5e-3). For an "
            "absolute chord deviation of X mm on a part whose bounding diagonal is D mm, "
            f"pass X/D -- {normalized:g} mm on a 200 mm part is {normalized / 200.0:g}"
        )
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
    # A board's primary document is its KiCad board file; a mesh's, its own format.
    suffix = MODEL_FORMATS[fmt].suffix if fmt in MODEL_FORMATS else f".{fmt}"
    # A file's sole model writes `<file>.<fmt>` (what `python bracket.py` is expected
    # to leave beside it, whatever the function is called); models SHARING a file
    # each write `<function>.<fmt>`, so two models never collide on one default.
    stem = script.stem
    if function and function != stem and len(model_function_names(script)) > 1:
        stem = function
    return (script.parent / f"{stem}{suffix}").resolve()


# A board's project is four files (the last its custom design rules, empty
# when it has none); the board file is its primary document.
PCB_PROJECT_SUFFIXES = (".kicad_pcb", ".kicad_sch", ".kicad_pro", ".kicad_dru")

_MESH_DECORATOR_NAMES = ("stl", "glb", "threemf")
#: Every decorator that declares a model: a format's, or a mesh export's alone.
MODEL_DECORATORS = frozenset({*MODEL_FORMATS, *_MESH_DECORATOR_NAMES})
_MESH_DECORATOR_FMT = {"stl": "stl", "glb": "glb", "threemf": "3mf"}
_MESH_SUFFIX = {"stl": ".stl", "3mf": ".3mf", "glb": ".glb"}


def declared_output_paths(script_path: Path | str, *, function: str | None = None) -> list[Path]:
    """Every file the models in ``script_path`` declare they will write.

    The primary document (``out=``, else the sibling ``<stem>.<fmt>``) plus each
    declared mesh export, resolved exactly as the build resolves them. A
    mesh-only model contributes its meshes and no ``.step``. ``function`` narrows
    it to one model in a file that holds several. Never raises: a script that
    cannot be parsed declares nothing.
    """
    try:
        script = Path(script_path).resolve()
        models = (
            (parse_generator_metadata(script, function=function),)
            if function
            else parse_all_generator_metadata(script)
        )
        outputs: list[Path] = []
        for metadata in models:
            if metadata is None:
                continue
            fmt = format_named(metadata.format).name
            if metadata.board:
                board_file = resolve_model_output_path(
                    script, fmt="pcb", explicit_out=metadata.pcb_out_target, function=metadata.entry_function
                )
                outputs.extend(board_file.with_suffix(suffix) for suffix in PCB_PROJECT_SUFFIXES)
                outputs.extend(fab_output_path(script, decl, board_file) for decl in metadata.fab_exports)
            if fmt == "pcb":
                continue
            if fmt in TREE_LESS_FORMATS:
                # One document, and the BOM a harness's bom= writes beside it.
                document = resolve_model_output_path(
                    script, fmt=fmt, explicit_out=metadata.out_target, function=metadata.entry_function
                )
                outputs.append(document)
                outputs.extend(fab_output_path(script, decl, document) for decl in metadata.fab_exports)
                continue
            primary = resolve_model_output_path(
                script, fmt=fmt, explicit_out=metadata.out_target, function=metadata.entry_function
            )
            if metadata.step_output:
                outputs.append(primary)
            for decl in metadata.mesh_exports:
                if decl.out is not None:
                    outputs.append(
                        resolve_model_output_path(
                            script, fmt=decl.fmt, explicit_out=decl.out, function=metadata.entry_function
                        )
                    )
                else:
                    outputs.append(primary.with_suffix(_MESH_SUFFIX.get(decl.fmt, f".{decl.fmt}")))
        return list(dict.fromkeys(outputs))
    except Exception:  # noqa: BLE001 - declarations are best-effort; a build still runs
        return []


def _cadgen_decorator_aliases(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    """Local names bound to cadgen's model/export decorators, and local
    names bound to the cadgen module itself (for ``@cadgen.step(...)``)."""
    names: dict[str, str] = {}
    module_aliases: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in {"cadgen", "cadgen.authoring"}:
            for alias in node.names:
                if alias.name in MODEL_DECORATORS:
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
    format "step" — the same tree and record — whose .step is never written.
    ``@pcb`` alone is format "pcb" (a tree-less board); ``@pcb`` with a 3D export
    (``@step`` or a mesh decorator) is format "step": the board's tree is its
    populated 3D board. ``@harness`` is format "harness" whatever else is stacked on
    it (the decorators refuse a harness that carries any other model decorator).
    Stacking order never changes the answer."""
    seen: list[tuple[str, dict[str, ast.expr]]] = []
    for decorator in function.decorator_list:
        call_kwargs: dict[str, ast.expr] = {}
        target = decorator
        if isinstance(decorator, ast.Call):
            target = decorator.func
            for keyword in decorator.keywords:
                if keyword.arg is not None:
                    call_kwargs[keyword.arg] = keyword.value
        resolved: str | None = None
        if isinstance(target, ast.Name):
            resolved = names.get(target.id)
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            if target.value.id in module_aliases and target.attr in MODEL_DECORATORS:
                resolved = target.attr
        if resolved is not None:
            seen.append((resolved, call_kwargs))
    kinds = [kind for kind, _kwargs in seen]
    if not kinds:
        return None
    meshes = any(kind in _MESH_DECORATOR_NAMES for kind in kinds)
    if "harness" in kinds:
        return "harness", next(kwargs for kind, kwargs in seen if kind == "harness"), False
    if "pcb" in kinds:
        board_kwargs = next(kwargs for kind, kwargs in seen if kind == "pcb")
        if "step" in kinds or meshes:
            return "step", board_kwargs, "step" not in kinds
        return "pcb", board_kwargs, False
    for kind, kwargs in seen:
        # The first MODEL format top-down wins; a mesh decorator stacked above
        # @step must not be taken for the model's format.
        if kind in ("step", "dxf"):
            return kind, kwargs, False
    return "step", {}, True


def model_function_formats(source: bytes | str, filename: str = "<model>") -> dict[str, str]:
    """``{function: "step" | "dxf" | "pcb" | "harness"}`` for every model a module's source declares,
    in file order; a mesh-only model reads as "step". A pure function of the
    bytes: ``{}`` for source that declares none or does not parse."""
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return {}
    decorator_names, module_aliases = _cadgen_decorator_aliases(tree)
    formats: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            match = _match_model_decorator(node, decorator_names, module_aliases)
            if match is not None:
                formats[node.name] = match[0]
    return formats


_FUNCTION_NAMES_CACHE: dict[str, tuple[tuple[int, int], tuple[str, ...]]] = {}
# A cached answer is kept only for a file whose mtime is older than this: a
# same-size rewrite inside one mtime tick is otherwise invisible to the stat key.
_FUNCTION_NAMES_SETTLE_NS = 2_000_000_000


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
    if time.time_ns() - stat.st_mtime_ns > _FUNCTION_NAMES_SETTLE_NS:
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
        materials=defn.materials,
        animation=defn.animation,
        board=defn.board,
        pcb_out_target=defn.pcb_out,
        fab_exports=defn.fab_exports,
    )


def _script_stamp(script_path: Path) -> tuple[int, int] | None:
    try:
        stat = Path(script_path).stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def imported_model(script_path: Path, function: str):
    """The ModelDef ``function`` registered when ``script_path`` was imported.

    The registry entry is reused when it was made from the bytes now on disk --
    the script's (same mtime and size) AND every file its import executed, since
    the declarations are evaluated from what the script imports; otherwise the
    module is imported by path -- under a loader name, so its ``__main__`` block
    does not run -- and read again. The module top must stay kernel-free, as the
    cad skill requires: this import is what every door pays to learn a model's
    declarations."""
    from cadgen._internal.generation_runner import _MODULE_LOAD_LOCK
    from cadgen.authoring import import_closure_current, registered_model

    resolved = Path(script_path).resolve()
    with _MODULE_LOAD_LOCK:
        stamp = _script_stamp(resolved)
        defn = registered_model(resolved, function)
        if defn is None or getattr(defn, "stamp", None) != stamp or not import_closure_current(resolved):
            from cadgen._internal.generation_runner import _load_generator_module, _first_party_from_source
            from cadgen._internal.source_hash import evict_first_party_modules

            # Like the build's own load: from a clean first-party module space (a helper a
            # warm worker still holds would feed the reload its OLD values) and with no
            # .pyc for the model or its helpers.
            evict_first_party_modules()
            with _first_party_from_source():
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


