"""Optional, disposable links from executed source operations to final faces.

Capture happens only during an ordinary model build, never when reading a STEP.
The viewer reads cached descriptors, keyed by exact source and document bytes.
No kernel imports at module scope. Unsupported/ambiguous cases stay unlinked.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import sys
import time
from cadgen._internal.atomic_replace import write_bytes_atomic

SCHEMA = 1


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _cache_path(source_hash, document_hash):
    from cadgen.store.paths import store_root
    key = hashlib.sha256(f'{SCHEMA}:{source_hash}:{document_hash}'.encode()).hexdigest()
    return store_root() / 'feature-links' / (key + '.json')


def read_links(source_hash, document):
    try:
        with _cache_path(source_hash, _digest(document)).open('rb') as stream:
            data = json.loads(stream.read(2 * 1024 * 1024))
        return data if isinstance(data, dict) and data.get('schema') == SCHEMA else None
    except (OSError, ValueError):
        return None


def publish_links(source, document, links):
    if not links or links['sourceHash'] != _digest(source):
        return
    path = _cache_path(links['sourceHash'], _digest(document))
    write_bytes_atomic(path, json.dumps(links, separators=(',', ':'), allow_nan=False).encode('utf-8'))


class FeatureTrace:
    """Bounded statement capture for single-solid algebraic build123d models.

    Tool variables inherit the faces created when the tool is actually placed
    and consumed. Modified faces with mixed ownership are deliberately omitted.
    """
    def __init__(self, source, function, *, enabled=True, source_hash=None):
        self.source = str(Path(source).resolve())
        self.source_names = {self.source, str(Path(source).absolute())}
        self.function = function
        self.events = []
        self.assembly_events = []
        self.origins = {}
        self.pending = None
        self.failed = False
        self.result_name = None
        self.statements = {}
        self.source_hash = ''
        self.previous = None
        self.active = False
        if not enabled:
            return
        try:
            data = Path(source).read_bytes()
            if len(data) > 512 * 1024:
                return
            self.source_hash = hashlib.sha256(data).hexdigest()
            if source_hash and self.source_hash != source_hash:
                return
            root = next(n for n in ast.parse(data).body if isinstance(n, ast.FunctionDef) and n.name == function)
            # Only returns in the entry function, not nested helper returns.
            returns = [n for n in root.body if isinstance(n, ast.Return)]
            if len(returns) != 1:
                return
            self.result_name = returns[0].value.id if isinstance(returns[0].value, ast.Name) else None
            for node in ast.walk(root):
                target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else node.target if isinstance(node, ast.AugAssign) else None
                if isinstance(target, ast.Name) or isinstance(node, ast.Expr):
                    if node.lineno in self.statements:
                        return  # Multiple statements on a line are ambiguous.
                    self.statements[node.lineno] = (node, target.id if target else None)
            self.active = True
        except (OSError, ValueError, SyntaxError, StopIteration):
            pass

    def __enter__(self):
        self.previous = sys.gettrace()
        if self.active and self.previous is None:
            sys.settrace(self._trace)
        else:
            self.active = False
        return self

    def __exit__(self, *_):
        if self.active:
            sys.settrace(self.previous)

    def _trace(self, frame, event, arg):
        if frame.f_code.co_filename not in self.source_names or frame.f_code.co_name != self.function:
            return None
        if self.failed:
            return None
        try:
            if event in ('line', 'return'):
                if self.pending:
                    node, target, before, list_before = self.pending
                    self.pending = None
                    owners = {node.lineno}
                    for name in ast.walk(node.value):
                        if isinstance(name, ast.Name) and name.id != self.result_name:
                            owners.update(self.origins.get(name.id, ()))
                    for value in frame.f_locals.values():
                        if isinstance(value, list):
                            for item in value:
                                if id(item) not in list_before and hasattr(item, 'wrapped'):
                                    self.assembly_events.append((set(owners), item))
                    if len(self.assembly_events) > 250:
                        self.failed = True
                        return None
                    shape = frame.f_locals.get(target)
                    if hasattr(shape, 'wrapped') and callable(getattr(shape, 'faces', None)):
                        faces = list(shape.faces())
                        if len(faces) > 250 or len(self.events) > 80:
                            self.failed = True
                            return None
                        if not isinstance(node, ast.AugAssign):
                            self.origins[target] = owners
                        if target == self.result_name:
                            self.events.append((owners, faces, before))
                    else:
                        self.origins.pop(target, None)
                statement = self.statements.get(frame.f_lineno) if event == 'line' else None
                if statement:
                    node, target = statement
                    old = frame.f_locals.get(target)
                    uses_previous = isinstance(node, ast.AugAssign) or any(isinstance(n, ast.Name) and n.id == target for n in ast.walk(node.value))
                    before = list(old.faces()) if uses_previous and callable(getattr(old, 'faces', None)) else []
                    if sum(len(value) for value in frame.f_locals.values() if isinstance(value, list)) > 1000:
                        self.failed = True
                        return None
                    list_before = {id(item) for value in frame.f_locals.values() if isinstance(value, list) for item in value}
                    self.pending = (node, target, before, list_before)
            elif event == 'exception':
                # Even a caught exception makes this statement trace ambiguous.
                self.failed = True
        except Exception:
            self.failed = True  # Inspection must not make a valid build fail.
        return self._trace

    def finish(self, shape):
        if not self.active or self.failed:
            return None
        try:
            if getattr(shape, 'children', ()):
                return self._finish_assembly(shape)
            if not self.events or len(shape.solids()) != 1:
                return None
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
            from OCP.BRepGProp import BRepGProp
            from OCP.GProp import GProp_GProps
            start = time.monotonic()
            final = list(shape.faces())
            from build123d import GeomType
            if (len(final) > 250 or any(f.geom_type not in (GeomType.PLANE, GeomType.CYLINDER) for f in final)
                    or sum(len(f.edges()) for f in final) > 2000):
                return None
            metric_cache = {}
            def metric(face):
                key = id(face)
                if key not in metric_cache:
                    from cadgen._internal.surface_extract import _face_metrics
                    metrics = _face_metrics(face.wrapped)
                    box = metrics['bbox']
                    metric_cache[key] = {**metrics, 'bbox': {'min': box[:3], 'max': box[3:]}}
                return metric_cache[key]
            def overlap(a, b):
                if time.monotonic() - start > 10:
                    raise TimeoutError('Feature link budget')
                if a.is_same(b):
                    return metric(a)['area']
                aa, bb = metric(a)['bbox'], metric(b)['bbox']
                if any(aa['max'][i] < bb['min'][i] - 1e-6 or bb['max'][i] < aa['min'][i] - 1e-6 for i in range(3)):
                    return 0
                if a.geom_type != b.geom_type:
                    return 0
                common = BRepAlgoAPI_Common(a.wrapped, b.wrapped)
                if not common.IsDone():
                    return 0
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(common.Shape(), props)
                return props.Mass()
            by_line = {}
            for owners, after, before in self.events:
                for index, face in enumerate(final):
                    area = metric(face)['area']
                    tolerance = max(1e-6, area * 1e-6)
                    if any(overlap(face, old) > tolerance for old in before):
                        continue
                    if any(abs(overlap(face, new) - area) <= tolerance for new in after):
                        for line in owners:
                            by_line.setdefault(str(line), set()).add(index)
            return {'schema': SCHEMA, 'sourceHash': self.source_hash, 'faces': [metric(f) for f in final], 'lines': {line: sorted(ids) for line, ids in by_line.items()}}
        except Exception:
            return None

    def _finish_assembly(self, shape):
        from cadgen._internal.surface_extract import _bnd_box
        def leaves(node):
            if getattr(node, 'children', ()):
                # Child-local placements under a moved group require explicit
                # world transforms; leave those cases unlinked for now.
                if node.location.position.length > 1e-8 or node.location.orientation.length > 1e-8:
                    raise ValueError('Moved assembly group')
                return [leaf for child in node.children for leaf in leaves(child)]
            return [node]
        final = leaves(shape)
        if len(final) > 250:
            return None
        lines = {}
        for owners, item in self.assembly_events:
            candidates = leaves(item)
            for index, leaf in enumerate(final):
                if any(leaf.is_same(candidate) for candidate in candidates):
                    for line in owners:
                        lines.setdefault(str(line), set()).add(index)
        parts = []
        for leaf in final:
            box = _bnd_box(leaf.wrapped)
            parts.append({'name': leaf.label, 'bbox': {'min': box[:3], 'max': box[3:]}})
        return {'schema': SCHEMA, 'sourceHash': self.source_hash, 'parts': parts, 'partLines': {line: sorted(ids) for line, ids in lines.items()}}
