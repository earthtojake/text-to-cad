"""``mesh``: a GSL model meshed on request into a GLB, judged before it is handed over, and kept, as ``cad omega
mesh FILE [OUT]`` does.

A model is its field. What a person or an agent asks of it while it is being written -- how big, how heavy, how
thin, what it looks like -- the field answers without a mesh (``cad run gsl eval``, ``cad run gsl render``), in
the time a mesh takes to start. A mesh is a translation of the field for something that needs triangles: a
slicer, a renderer, another program. So it is made when one is wanted, here, and not on every edit.

Three things make the mesh one that can be trusted and is not paid for twice:

- **The model's own values.** ``define`` gives its top-level names other values (``r=6.5``), as omega's
  evaluator takes them (a request's ``defs``): the mesh and the volume it is held to are of that part.
- **The check.** ``gsl`` writes a mesh it got wrong as readily as a right one, so what it wrote is read back and
  judged exactly as ``check`` judges an STL (``_check``: empty, open, non-manifold, inside-out, cut off at the
  ``@scene`` box, a volume outside the bracket the evaluator proves for the field). A mesh that fails is not
  written to ``out`` and not kept.
- **The key.** A mesh that passed is kept in cad's cache (``cad.engine.places.cache_dir``, under ``omega``) by
  what made it: the model's bytes, the bytes of the files it imports, the values, the depth and the ``gsl``.
  Asked for again with nothing changed, it is copied, not meshed.

Meshing is ``gsl eval``'s ``mesh`` (omega-core 0.1.2 or later): one indexed GLB, a node for each of the model's
returns, a normal at every vertex from the field's gradient. A ``gsl`` that has no such question is said so, with
what to do.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

from cad.results import CheckResult

__all__ = ["DEFAULT_DEPTH", "key", "mesh", "read_glb", "statements"]

#: The octree depth ``gsl`` meshes at when none is named (its ``--subdivision``).
DEFAULT_DEPTH = 9
#: What a kept mesh is keyed with besides its inputs: raised when what is kept, or how it is judged, changes.
_KEPT = 1

_DEFINE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\S+)\s*")
_SCENE = re.compile(r"^\s*@scene\s*\(\s*([-+0-9.eE]+)", flags=re.M)
#: The files a model reads beside itself: ``importMesh 0 "scan.stl";``, ``part = importStep "part.step";``.
_IMPORTED = re.compile(r"\bimport(?:Mesh|Step)\b[^\"\n;]*\"([^\"\n]+)\"")


def statements(define: tuple[str, ...]) -> str:
    """``define``'s values as the GSL statements omega's evaluator takes (``defs``), one a line, in the order
    given: ``("r=6.5",)`` is ``r = 6.5;``. Each is a name and a number; anything else is a ``ValueError``
    naming it, so a value never carries a statement of its own into the model."""
    lines = []
    for given in define:
        found = _DEFINE.fullmatch(given)
        try:
            number = float(found.group(2)) if found else math.nan
        except ValueError:
            number = math.nan
        if found is None or not math.isfinite(number):
            raise ValueError(f"a value is given as name=number (r=6.5), not {given!r}")
        lines.append(f"{found.group(1)} = {found.group(2)};\n")
    return "".join(lines)


def key(model: Path, defs: str, depth: int | None, gsl: str) -> str:
    """What a mesh is kept under: a digest of the model's bytes, the bytes of each file it imports (or that it
    is missing), the values, the depth and the ``gsl`` that meshes -- and not of where the model is."""
    data = Path(model).read_bytes()
    reads = []
    for name in sorted(set(_IMPORTED.findall(data.decode("utf-8", errors="replace")))):
        try:
            reads.append([name, hashlib.sha256((Path(model).parent / name).read_bytes()).hexdigest()])
        except OSError:
            reads.append([name, None])
    made_of = {"kept": _KEPT, "model": hashlib.sha256(data).hexdigest(), "reads": reads, "defs": defs,
               "depth": depth or DEFAULT_DEPTH, "gsl": gsl}
    return hashlib.sha256(json.dumps(made_of, sort_keys=True).encode()).hexdigest()


def read_glb(path: Path):
    """The triangles of every mesh in a binary glTF, as one ``(n, 3, 3)`` float64 array: what ``measure`` reads.
    Positions are as stored (omega writes each body in the model's own millimetres, with no node transform)."""
    import numpy as np

    from cad.engine.export.glb import MAGIC  # the container's magic, declared once, in the engine's writer

    data = Path(path).read_bytes()
    try:
        if len(data) < 28 or int.from_bytes(data[:4], "little") != MAGIC:
            raise ValueError
        size = int.from_bytes(data[12:16], "little")
        document = json.loads(data[20:20 + size])
        binary = data[20 + size + 8:]
        kinds = {5126: "<f4", 5125: "<u4", 5123: "<u2", 5121: "u1"}

        def values(index: int, width: int):
            accessor = document["accessors"][index]
            view = document["bufferViews"][accessor["bufferView"]]
            start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            return np.frombuffer(binary, kinds[accessor["componentType"]], accessor["count"] * width,
                                 start).reshape(-1, width)

        found = []
        for body in document.get("meshes", ()):
            for primitive in body["primitives"]:
                positions = values(primitive["attributes"]["POSITION"], 3).astype(np.float64)
                found.append(positions[values(primitive["indices"], 1).reshape(-1, 3).astype(np.int64)])
    except (ValueError, KeyError, IndexError, TypeError):
        raise ValueError("not a GLB of triangle meshes") from None
    return np.concatenate(found) if found else np.zeros((0, 3, 3))


def _meshed(gsl: Path, target: Path, defs: str, depth: int | None, half: float, out: Path) -> dict[str, Any]:
    """``gsl eval``'s ``mesh`` of ``target`` with ``defs`` over its ``@scene`` box, written to ``out``: its
    answer (the bodies and what their triangles say). Raises ``omega_core.EvalError`` in gsl's words."""
    import omega_core

    request: dict[str, Any] = {"op": "mesh", "source": str(target), "out": str(out),
                               "region": [-half, -half, -half, half, half, half]}
    if defs:
        request["defs"] = defs
    if depth:
        request["subdivision"] = int(depth)
    with omega_core.Session(source_paths=(target.parent,), program=str(gsl)) as session:
        return dict(session.request(request))


def _bracket(gsl: Path, target: Path, defs: str, half: float) -> tuple[float, float]:
    """The bracket omega's evaluator proves for the volume of the model, with ``defs``, over its ``@scene`` box."""
    import omega_core

    from cad.omega._check import VOLUME_TOLERANCE

    request: dict[str, Any] = {"op": "volume", "source": str(target), "relativeTolerance": VOLUME_TOLERANCE,
                               "region": [-half, -half, -half, half, half, half]}
    if defs:
        request["defs"] = defs
    with omega_core.Session(source_paths=(target.parent,), program=str(gsl)) as session:
        answer = session.request(request)
    return float(answer["lowerMm3"]), float(answer["upperMm3"])


def mesh(path: Path, out: Path | None = None, *, define: tuple[str, ...] = (), depth: int | None = None,
         strict: bool = False, verbose: bool = False) -> CheckResult:
    import importlib.util
    import shutil

    from cad._internal.atomic_replace import replace_atomic
    from cad._internal.findings import FindingsReport
    from cad._internal.validation_door import blocks, display_path, failed, resolved_target, result_from_findings
    from cad.engine.places import cache_dir
    from cad.omega._check import SUFFIXES, _judge, _judge_volume, measure
    from cad.omega._program import EXTRA, GSL, OmegaMissingError, find_gsl

    target = resolved_target(path, label="omega")
    if verbose:
        print(f"[omega] meshing {target}", file=sys.stderr)
    if target.suffix.lower() not in SUFFIXES:
        return failed(target, f"target must be a {' or '.join(SUFFIXES)} file")
    if not target.is_file():
        return failed(target, "file not found")
    if depth is not None and depth < 1:
        return failed(target, f"depth is the mesher's octree depth, 1 or more (gsl's own is {DEFAULT_DEPTH}), "
                              f"not {depth}")
    where = display_path(target)
    findings = FindingsReport()

    def refused(measurements: dict | None = None) -> CheckResult:
        result = result_from_findings(target, findings.deduplicated(), strict=strict, summary="")
        return CheckResult(ok=result.ok, path=result.path, findings=result.findings, summary=result.summary,
                           measurements=measurements or {})

    try:
        defs = statements(tuple(define))
    except ValueError as error:
        findings.add("error", "bad_define", str(error), path=where,
                     hint="give each value as name=number, the name one the model declares at its top level")
        return refused()
    scene = _SCENE.search(target.read_text(encoding="utf-8", errors="replace"))
    try:
        half = float(scene.group(1)) / 2.0 if scene else 0.0
    except ValueError:
        half = 0.0
    if not half > 0:
        findings.add("error", "no_scene", "the model has no @scene, so there is no box to mesh it in: gsl's own "
                     "guess of one cuts off features thinner than its search's cells", path=where,
                     hint="add @scene(size) as the first line: an edge of size mm, centred on the origin, that "
                          "holds the whole part")
        return refused()

    if importlib.util.find_spec("omega_core") is None:
        raise ModuleNotFoundError(f"omega_core comes with cad's omega integration: install {EXTRA}, or run the script "
                                  f"with cad run (add `{EXTRA}` to its header)", name="omega_core")
    import omega_core

    from cad._internal import programs

    try:
        gsl = find_gsl()
    except OmegaMissingError as error:
        return failed(target, str(error), code="program_missing")
    kept_under = key(target, defs, depth, programs.version(GSL, gsl) or "")
    kept = cache_dir() / "omega"
    glb, record = kept / f"{kept_under}.glb", kept / f"{kept_under}.json"

    measurements: Any = None
    if glb.is_file() and record.is_file():
        try:
            measurements = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            measurements = None
    cached = measurements is not None
    if cached:
        # What was kept passed; its warnings are said again, and under ``strict`` they refuse it as they would have.
        _judge(findings, measurements, half, where)
        if blocks(findings, strict=strict):
            return refused(measurements)
    else:
        kept.mkdir(parents=True, exist_ok=True)
        making = kept / f"{kept_under}.{os.getpid()}.making.glb"
        try:
            try:
                answer = _meshed(gsl, target, defs, depth, half, making)
            except omega_core.EvalError as error:
                said = str(error)
                if 'op "mesh"' in said and "one of" in said:
                    findings.add("error", "gsl_cannot_mesh", f"this gsl's eval has no mesh ({gsl}): it is older "
                                 "than the one cad gsl mesh needs", path=where,
                                 hint="set CAD_GSL to the gsl of omega-core 0.1.2 or later; `cad gsl validate` meshes "
                                      "with this one")
                else:
                    findings.add("error", "compile_failed", f"gsl refused the model: {said}", path=where)
                return refused()
            try:
                triangles = read_glb(making)
            except (OSError, ValueError) as error:
                findings.add("error", "unreadable_mesh", f"gsl's mesh does not read: {error}", path=where)
                return refused()
            measurements = measure(triangles)
            measurements.update(scene_half_mm=half, depth=depth or DEFAULT_DEPTH, defs=defs,
                                bodies=[{"name": body.get("name"), "triangles": body.get("triangles"),
                                         "volume_mm3": body.get("volumeMm3")} for body in answer.get("bodies") or ()])
            _judge(findings, measurements, half, where)
            if not findings.errors:
                try:
                    bracket = _bracket(gsl, target, defs, half)
                except omega_core.EvalError as error:
                    findings.add("error", "volume_not_measured", "omega's evaluator measured no volume, so a lost "
                                 f"wall cannot be ruled out: {error}", path=where)
                else:
                    measurements["field_volume_mm3"] = list(bracket)
                    _judge_volume(findings, measurements["volume_mm3"], bracket, where)
            if blocks(findings, strict=strict):
                return refused(measurements)
            # Kept only once it has passed, the mesh before its record: a record names a mesh that is there.
            replace_atomic(making, glb)
            record.write_text(json.dumps(measurements), encoding="utf-8")
        finally:
            making.unlink(missing_ok=True)

    written = glb
    if out is not None:
        written = Path(out).expanduser().absolute()
        written.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(glb, written)
    measurements = dict(measurements, glb=str(written), cached=cached)
    low, high = measurements["bbox_min"], measurements["bbox_max"]
    size = " x ".join(f"{b - a:.4g}" for a, b in zip(low, high))
    summary = (f"OK {where} -> {display_path(written)}: {measurements['triangles']} triangles, "
               f"{measurements['volume_mm3']:.6g} mm3, {size} mm, in @scene({2 * half:g})"
               + (" (kept from an earlier mesh)" if cached else ""))
    result = result_from_findings(target, findings.deduplicated(), strict=strict, summary=summary)
    return CheckResult(ok=result.ok, path=result.path, findings=result.findings, summary=result.summary,
                       measurements=measurements)
