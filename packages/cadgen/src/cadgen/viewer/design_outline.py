"""Read-only Python CAD source outlines. Never import or execute the generator.

This describes source operations, not evaluated feature history or face mappings.
"""
from __future__ import annotations

import ast
import math
import operator
import os
from hashlib import sha256
from pathlib import Path

from .backend import normalized_file_ref, require_contained

OPS = {"Box", "Cylinder", "Sphere", "Cone", "Torus", "Hole", "extrude", "revolve", "loft", "sweep", "fillet", "chamfer", "shell", "offset", "mirror", "split"}
SKETCHES = {"Rectangle", "RectangleRounded", "Circle", "Ellipse", "Polygon", "RegularPolygon", "SlotOverall", "SlotCenterToCenter", "Polyline", "Line", "Spline"}
ARG_NAMES = {"Box": ["length", "width", "height"], "Cylinder": ["radius", "height"], "Sphere": ["radius"], "Cone": ["bottom_radius", "top_radius", "height"], "Hole": ["radius", "depth"], "Rectangle": ["width", "height"], "RectangleRounded": ["width", "height", "radius"], "Circle": ["radius"], "SlotOverall": ["width", "height"], "fillet": ["edges", "radius"], "chamfer": ["edges", "length"]}
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def call_name(node):
    if not isinstance(node, ast.Call):
        return ""
    return node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""


def literal(node, env, depth=0):
    if depth > 12:
        return None
    if isinstance(node, ast.Constant) and type(node.value) in (int, float, bool, str):
        if type(node.value) in (int, float) and (abs(node.value) >= 1e12 or not math.isfinite(node.value)):
            return None
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = literal(node.operand, env, depth + 1)
        if type(value) in (int, float):
            return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
        a, b = literal(node.left, env, depth + 1), literal(node.right, env, depth + 1)
        if type(a) in (int, float) and type(b) in (int, float):
            try:
                value = BINARY[type(node.op)](a, b)
                return value if math.isfinite(value) and abs(value) < 1e12 else None
            except (ArithmeticError, OverflowError):
                pass
    return None


def parse_design_outline(source, model_name=None):
    tree = ast.parse(source)
    if sum(1 for _ in ast.walk(tree)) > 20000:
        raise ValueError("Source is too large to outline")
    functions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    env, constants = {}, []

    def text(node):
        return (ast.get_source_segment(source, node) or ast.unparse(node))[:240]

    def assign(statement, scope, record=False):
        if not isinstance(statement, ast.Assign):
            return
        for target in statement.targets:
            pairs = zip(target.elts, statement.value.elts) if isinstance(target, (ast.Tuple, ast.List)) and isinstance(statement.value, (ast.Tuple, ast.List)) else [(target, statement.value)]
            for name, value_node in pairs:
                if not isinstance(name, ast.Name):
                    continue
                value = literal(value_node, scope)
                scope[name.id] = value  # invalidate a previous constant too
                if record and type(value) in (int, float):
                    constants.append({"name": name.id, "value": value, "expression": text(value_node)})

    for statement in tree.body:
        assign(statement, env, True)

    def parameters(call, scope):
        name = call_name(call)
        names = [a.arg for a in functions[name].args.args] if name in functions else ARG_NAMES.get(name, [])
        values = [(names[i] if i < len(names) else f"argument_{i+1}", arg) for i, arg in enumerate(call.args)]
        values += [(k.arg or "arguments", k.value) for k in call.keywords]
        return [{"name": name, "value": literal(value, scope), "expression": text(value)} for name, value in values if name not in ("edges", "objects", "argument_1") or literal(value, scope) is not None]

    def operation(call, scope, mode="", target=""):
        name = call_name(call)
        op = name
        template = call
        helper = functions.get(name)
        if helper:
            # Describe the helper only when it has one unambiguous CAD operation.
            calls = [n for n in ast.walk(helper) if isinstance(n, ast.Call) and call_name(n) in OPS]
            if len(calls) != 1:
                return None
            template, op = calls[0], call_name(calls[0])
        if op not in OPS | SKETCHES:
            return None
        mode_kw = next((text(k.value) for k in call.keywords if k.arg == "mode"), "")
        cut = mode == "cut" or mode_kw.endswith("SUBTRACT")
        label = ("Cut " if cut else "") + op.capitalize()
        if target:
            label += " · " + target.replace("_", " ")
        children = []
        child_scope = dict(scope)
        if helper:
            child_scope = dict(env)
            for arg in helper.args.args:
                child_scope[arg.arg] = None
            for arg, default in zip(helper.args.args[-len(helper.args.defaults):], helper.args.defaults):
                child_scope[arg.arg] = literal(default, env)
            for param in parameters(call, scope):
                child_scope[param['name']] = param['value']
            for node in ast.walk(helper):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    child_scope[node.id] = None
        for child in ast.walk(template):
            if child is template or not isinstance(child, ast.Call) or call_name(child) not in SKETCHES:
                continue
            children.append({"id": f"sketch:{call.lineno}:{child.lineno}:{child.col_offset}", "label": call_name(child), "type": "sketch", "line": child.lineno, "parameters": parameters(child, child_scope), "children": []})
        return {"id": f"source:{call.lineno}:{call.col_offset}", "label": label, "type": "sketch" if op in SKETCHES else op.lower(), "line": call.lineno, "parameters": parameters(call, scope), "children": children}

    def collect(statements, scope):
        nodes, pending_sketch = [], None
        for statement in statements:
            if len(nodes) >= 200:
                raise ValueError("Source exceeds the 200 operation outline limit")
            if isinstance(statement, ast.With):
                name = call_name(statement.items[0].context_expr) if statement.items else ""
                children = collect(statement.body, dict(scope))
                if name == "BuildSketch":
                    pending_sketch = {"id": f"sketch:{statement.lineno}", "label": "Sketch", "type": "sketch", "line": statement.lineno, "parameters": [], "children": children}
                    nodes.append(pending_sketch)
                else:
                    nodes.extend(children)
                # With blocks share Python scope; don't claim old constants
                # still apply after assignments we haven't evaluated.
                for n in ast.walk(statement):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                        scope[n.id] = None
                continue
            if isinstance(statement, (ast.For, ast.If, ast.While)):
                control_scope = dict(scope)
                for n in ast.walk(statement):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                        control_scope[n.id] = None
                        scope[n.id] = None
                children = collect(statement.body, dict(control_scope)) + collect(statement.orelse, dict(control_scope))
                if children:
                    nodes.append({"id": f"control:{statement.lineno}", "label": "Repeat" if isinstance(statement, (ast.For, ast.While)) else "Conditional features", "type": "pattern", "line": statement.lineno, "parameters": [{"name": "source", "value": None, "expression": text(statement.iter if isinstance(statement, ast.For) else statement.test)}], "children": children})
                continue
            value = getattr(statement, "value", None)
            target = statement.targets[0].id if isinstance(statement, ast.Assign) and isinstance(statement.targets[0], ast.Name) else ""
            mode = "cut" if isinstance(statement, ast.AugAssign) and isinstance(statement.op, ast.Sub) else ""
            # Walk the expression outside-in. A recognized helper/operation owns
            # its nested sketch, so don't list that sketch a second time.
            found = []
            def visit(node):
                if node is None:
                    return
                item = operation(node, scope, mode, target) if isinstance(node, ast.Call) else None
                if item:
                    found.append(item)
                    return
                for child in ast.iter_child_nodes(node):
                    visit(child)
            visit(value)
            for item in found:
                if pending_sketch and item["type"] in ("extrude", "revolve", "loft", "sweep"):
                    nodes.remove(pending_sketch)
                    item["children"].insert(0, pending_sketch)
                    pending_sketch = None
                nodes.append(item)
            if not found and isinstance(statement, ast.AugAssign) and isinstance(statement.op, (ast.Add, ast.Sub, ast.BitAnd)):
                nodes.append({"id": f"boolean:{statement.lineno}", "label": {ast.Add: "Union", ast.Sub: "Cut", ast.BitAnd: "Intersect"}[type(statement.op)], "type": "boolean", "line": statement.lineno, "parameters": [{"name": "operand", "value": None, "expression": text(value)}], "children": []})
            assign(statement, scope)
            if isinstance(statement, ast.AugAssign) and isinstance(statement.target, ast.Name):
                scope[statement.target.id] = None
        return nodes

    roots = [fn for fn in functions.values() if any((d.id if isinstance(d, ast.Name) else call_name(d) if isinstance(d, ast.Call) else getattr(d, 'attr', '')) == "step" for d in fn.decorator_list)]
    if roots:
        matching = [fn for fn in roots if model_name and fn.name == model_name.replace('-', '_')]
        if matching:
            roots = matching
        elif len(roots) > 1:
            return {"features": [], "parameters": [], "status": "ambiguous"}
        features = [item for fn in roots for item in collect(fn.body, dict(env))]
    else:
        features = collect(tree.body, dict(env))
    return {"features": features, "parameters": constants}


def read_design_outline(root, file_ref):
    root = os.path.abspath(root)
    raw = normalized_file_ref(file_ref)
    path = Path(require_contained(root, os.path.abspath(os.path.join(root, raw))))
    require_contained(os.path.realpath(root), os.path.realpath(path))
    if any(part.startswith('.') for part in path.relative_to(root).parts):
        return {"status": "unavailable", "features": [], "parameters": []}
    if path.suffix.lower() not in (".step", ".stp") or not path.is_file():
        return {"status": "unavailable", "features": [], "parameters": []}
    candidates = [path.with_suffix('.py'), Path(str(path) + '.py')]
    if path.parent.name.lower() == 'step' and path.parent != Path(root):
        candidates.append(path.parent.parent / 'src' / (path.stem + '.py'))
    sources = []
    for candidate in candidates:
        contained = Path(require_contained(root, os.path.abspath(candidate)))
        require_contained(os.path.realpath(root), os.path.realpath(contained))
        if contained.is_file() and contained not in sources:
            sources.append(contained)
    if len(sources) != 1:
        return {"status": "ambiguous" if sources else "unavailable", "features": [], "parameters": []}
    source_path = sources[0]
    with source_path.open('rb') as stream:
        data = stream.read(512 * 1024 + 1)
    if len(data) > 512 * 1024:
        raise ValueError('Source exceeds the 512 KB outline limit')
    parsed = parse_design_outline(data.decode('utf-8'), path.stem)
    if parsed.get('status') == 'ambiguous':
        return parsed
    return {"status": "ready", "source": str(source_path.relative_to(root)).replace(os.sep, '/'), "sourceHash": sha256(data).hexdigest(), **parsed}
