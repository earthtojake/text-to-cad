"""Refresh decorator annotations while retaining verified geometry.

This is a narrow source optimization, not an alternate execution engine. Literal
metadata (including constants used exclusively by annotations) is removed from
the geometry fingerprint. Computed annotations remain in that fingerprint and
reuse their recorded value only while their source and dependencies are unchanged.
Reflection, changed child pins, and unavailable geometry use the ordinary build.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path

_ANNOTATIONS = frozenset({'materials', 'animation', 'kinematics'})
_REFLECTION = frozenset({'__file__', 'globals', 'locals', 'vars', 'eval', 'exec',
                         'inspect', '__globals__', '__code__', '__dict__', '__cadgen_model__', '__wrapped__'})
_COMPUTED = object()


def _source_parts(source: bytes, entry_name: str) -> tuple[str, dict] | None:
    from cadgen._internal.source_hash import _semantic_source_bytes

    try:
        module = ast.parse(source)
        if any(isinstance(node, ast.Name) and node.id in _REFLECTION
               or isinstance(node, ast.Attribute) and node.attr in _REFLECTION
               for node in ast.walk(module)):
            return None
        direct, namespaces = set(), set()
        constants, bindings = {}, {}
        for node in module.body:
            if isinstance(node, ast.ImportFrom) and node.module in {'cadgen', 'cadgen.authoring'}:
                direct.update(alias.asname or alias.name for alias in node.names if alias.name == 'step')
            elif isinstance(node, ast.Import):
                namespaces.update(alias.asname or alias.name for alias in node.names if alias.name == 'cadgen')
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name, value = node.targets[0].id, node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                name, value = node.target.id, node.value
            else:
                continue
            bindings[name] = bindings.get(name, 0) + 1
            constants[name] = (node, value)
        if any(name in bindings for name in direct | namespaces):
            return None
        functions = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == entry_name]
        if len(functions) != 1:
            return None
        used = set()

        def literal(node, visiting=frozenset()):
            if isinstance(node, ast.Name):
                if node.id in visiting or bindings.get(node.id) != 1:
                    raise ValueError('not an immutable literal declaration')
                used.add(node.id)
                return literal(copy.deepcopy(constants[node.id][1]), visiting | {node.id})
            if isinstance(node, (ast.List, ast.Tuple)):
                return [literal(item, visiting) for item in node.elts]
            if isinstance(node, ast.Dict):
                if any(key is None for key in node.keys):
                    raise ValueError('dictionary expansion')
                return {literal(key, visiting): literal(value, visiting) for key, value in zip(node.keys, node.values)}
            return ast.literal_eval(node)

        values = {name: None for name in _ANNOTATIONS}
        found = False
        for index, decorator in enumerate(functions[0].decorator_list):
            callee = decorator.func if isinstance(decorator, ast.Call) else decorator
            recognized = (isinstance(callee, ast.Name) and callee.id in direct) or (
                isinstance(callee, ast.Attribute) and callee.attr == 'step'
                and isinstance(callee.value, ast.Name) and callee.value.id in namespaces)
            if not recognized:
                continue
            if found:
                return None
            found = True
            if not isinstance(decorator, ast.Call):
                decorator = ast.Call(func=callee, args=[], keywords=[])
                functions[0].decorator_list[index] = decorator
            if decorator.args or any(keyword.arg is None for keyword in decorator.keywords):
                return None
            remaining = []
            for keyword in decorator.keywords:
                if keyword.arg not in _ANNOTATIONS:
                    remaining.append(keyword)
                    continue
                prior_used = set(used)
                try:
                    values[keyword.arg] = literal(keyword.value)
                except (ValueError, TypeError, KeyError):
                    # Keep computed metadata in the geometry fingerprint. A
                    # literal sibling may still refresh by reusing this field's
                    # recorded value while the retained expression is unchanged.
                    used.clear()
                    used.update(prior_used)
                    values[keyword.arg] = _COMPUTED
                    remaining.append(keyword)
            decorator.keywords = remaining
        if not found:
            return None
        # A constant read outside these annotations may be mutated or inspected
        # by Python before decoration. Its literal initializer is then insufficient
        # to reproduce the declaration, even if that other code did not change.
        removable = {name for name in used if bindings.get(name) == 1}
        skipped = {id(constants[name][0]) for name in removable}
        retained_loads = {node.id for statement in module.body if id(statement) not in skipped
                          for node in ast.walk(statement)
                          if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
        if removable & retained_loads:
            return None
        module.body = [node for node in module.body if id(node) not in skipped]
        normalized = ast.unparse(ast.fix_missing_locations(module)).encode('utf-8')
        return _semantic_source_bytes(normalized), values
    except (SyntaxError, ValueError, TypeError, KeyError, RecursionError, MemoryError):
        return None


def capture_geometry_closure(script: Path | str, closure: dict, *, entry_name: str) -> dict | None:
    """Attest the geometry fingerprint against the bytes consumed by a build."""
    from cadgen._internal.source_hash import _semantic_source_bytes
    from cadgen.store.closure import closure_hash

    script = Path(script)
    try:
        source = script.read_bytes()
    except OSError:
        return None
    shas = dict(closure.get('shas') or {})
    if shas.get(script.name) != _semantic_source_bytes(source):
        return None  # An edit during the build cannot attest geometry it did not run.
    parts = _source_parts(source, entry_name)
    if parts is None:
        return None
    shas[script.name] = parts[0]
    return {'hash': closure_hash(shas.items()), 'entry': entry_name}


def _literal_kinematics(raw: object, descriptor: dict) -> dict | None:
    if raw is None:
        return None
    from cadgen.kinematics import normalize_kinematics

    block = copy.deepcopy(normalize_kinematics(raw, where='kinematics=').block)
    nodes = {}
    names = {}

    def visit(node):
        identity = str(node.get('id') or '')
        if identity:
            nodes[identity] = node
            names.setdefault(str(node.get('name') or ''), []).append(identity)
        for child in node.get('children') or []:
            visit(child)

    visit((descriptor.get('assembly') or {}).get('root') or {})
    for occurrence in descriptor.get('occurrences') or []:
        if occurrence['id'] not in nodes:
            visit(occurrence)
    for mate in block['mates']:
        if mate['kind'] != 'fastened' and 'ref' in mate['axis']:
            raise LookupError('axis needs topology resolution')
        for key in ('parent', 'child'):
            target = mate[key][1:]
            candidates = [target] if target in nodes else names.get(target, [])
            if len(candidates) != 1:
                raise LookupError('occurrence needs ordinary source resolution')
            mate[key + 'Id'] = candidates[0]
    return block


def refresh_annotations(spec) -> str | None:
    """Return a refreshed authored tree, or None to use the ordinary build."""
    if spec.source != 'generated' or spec.script_path is None or not spec.step_output:
        return None
    from cadgen.store.index import resolve_model_ref
    from cadgen.store.records import read_record, write_record, note_output, forget_output
    from cadgen.store.gate import stale
    from cadgen.store.closure import current_closure_hash, closure_hash, changed_constant
    from cadgen._internal.source_hash import _semantic_source_hash, _semantic_source_bytes
    from cadgen.store.trees import get_tree, put_tree, flatten, tree_complete
    from cadgen.catalog import artifact_file_hash
    from cadgen._internal.source_sidecar import (
        normalize_materials, normalize_animation, resolve_materials, remap_appearance,
        write_source_sidecar, source_sidecar_path,
    )

    entry_name = getattr(spec.generator_metadata, 'entry_function', None)
    if not entry_name:
        return None
    script = Path(spec.script_path)
    model = resolve_model_ref(f'{script}::{entry_name}')
    record = read_record(model)
    if not record or not record.get('geometryClosure') or not record.get('unannotatedTree'):
        return None
    verdict = stale(model)
    if not verdict.stale or any(clause.get('stale') and clause['clause'] != 2 for clause in verdict.clauses):
        return None
    if changed_constant(script, record.get('constants') or {}) is not None:
        return None
    closure = record.get('closure') or {}
    try:
        source = script.read_bytes()
        parts = _source_parts(source, entry_name)
        shas = {name: (_semantic_source_bytes(source) if name == script.name else
                       _semantic_source_hash((script.parent / name).resolve()))
                for name in closure['files']}
    except (OSError, KeyError):
        return None
    if parts is None or script.name not in shas:
        return None
    full_hash = closure_hash(shas.items())
    geometry_shas = {**shas, script.name: parts[0]}
    if closure_hash(geometry_shas.items()) != record['geometryClosure']['hash']:
        return None
    baseline_hash = record['unannotatedTree']
    if not tree_complete(baseline_hash) or not tree_complete(record.get('documentTree') or ''):
        return None
    baseline = get_tree(baseline_hash)
    descriptor = flatten(baseline_hash)
    document_descriptor = flatten(record['documentTree'])
    if baseline is None or descriptor is None or document_descriptor is None:
        return None
    raw_materials = parts[1]['materials']
    material_declaration = (copy.deepcopy(record.get('materials')) if raw_materials is _COMPUTED
                            else normalize_materials(raw_materials, where='materials='))
    raw_animation = parts[1]['animation']
    animation = (copy.deepcopy(record.get('animation')) if raw_animation is _COMPUTED
                 else normalize_animation(raw_animation, where='animation='))
    raw_kinematics = parts[1]['kinematics']
    kinematics_is_document = raw_kinematics is _COMPUTED
    try:
        kinematics = (copy.deepcopy(record.get('kinematics')) if kinematics_is_document
                      else _literal_kinematics(raw_kinematics, descriptor))
    except LookupError:
        return None
    appearance = resolve_materials(descriptor, material_declaration, inherited=descriptor.get('appearance'))
    baseline.pop('appearance', None)
    if appearance is not None:
        baseline['appearance'] = appearance
    tree = put_tree(baseline)
    sidecar = {}
    if appearance is not None:
        sidecar['appearance'] = remap_appearance(appearance, record.get('documentOccurrenceMap') or {})
    if animation is not None:
        sidecar['animation'] = animation
    if kinematics is not None:
        if not kinematics_is_document:
            from cadgen._internal.kinematics_resolve import remap_document_kinematics
            kinematics = remap_document_kinematics(kinematics, record.get('documentOccurrenceMap') or {},
                                                 record.get('documentNodeMap') or {}, record['documentTree'])
        sidecar['kinematics'] = kinematics
    # Preserve the selected source, record, STEP and sidecar revision until
    # publication. A racing change retries via the ordinary build's safeguards.
    from cadgen._internal.generation import _document_pair_state
    pair = _document_pair_state(spec.step_path)
    if pair[0] != record.get('stepHash'):
        return None
    if current_closure_hash(script, closure['files']) != full_hash or read_record(model) != record:
        return None
    if _document_pair_state(spec.step_path) != pair:
        return None
    write_source_sidecar(spec.step_path, sidecar, document_hash=record['stepHash'])
    output = source_sidecar_path(spec.step_path).resolve()
    outputs = copy.deepcopy(record.get('outputs') or {})
    digest = artifact_file_hash(output)
    if digest:
        outputs[str(output)] = {'sha256': digest}
        note_output(output, model)
    else:
        outputs.pop(str(output), None)
        forget_output(output)
    updated = {**record, 'tree': tree, 'closure': {**closure, 'hash': full_hash, 'shas': shas},
               'outputs': outputs, 'materials': material_declaration, 'animation': animation,
               'appearance': sidecar.get('appearance'), 'kinematics': kinematics}
    # If source changed in this tiny publication interval the captured hashes
    # intentionally leave this record stale; no newer bytes are claimed.
    write_record(model, updated)
    return tree
