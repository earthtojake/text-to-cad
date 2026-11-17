"""``check``: a GSL model meshed by omega's ``gsl`` and the mesh judged against the model's field, as ``cad omega
check FILE`` does.

``gsl compile -t stl`` exits 0 on a mesh it got wrong: an empty one when every wall is thinner than a cell, one
that keeps a floor and loses the walls standing on it, one cut off where the part leaves the box it was meshed in,
holes and edges shared by four or more triangles where its dual contouring met a field it could not resolve. A
person sees none of it in a viewer. So the mesh is measured here, from the STL's own triangles (numpy alone), and
held to the field through omega's own evaluator (``omega_core.Session``, the extra's client):

- ``compile_failed``: ``gsl`` refused the model, in its words.
- ``no_scene``: the model has no ``@scene``. Without one ``gsl`` searches for the box the field fills
  (``--bbox auto``), and that search misses features thinner than its cells, so the mesh is cut off with no word.
  ``@scene(size)`` names the box: an edge of ``size`` mm centred on the origin.
- ``empty_mesh``: no triangles at all.
- ``open_edges`` and ``non_manifold``: an edge of one triangle, or of three and more. A solid's every edge is
  shared by exactly two.
- ``inside_out``: the triangles enclose a negative volume, so their faces point inward.
- ``cut_off``: the mesh reaches a face of the ``@scene`` box, so the part goes on past it (or the field never
  ends: a floor plane).
- ``volume_mismatch``: the mesh's volume lies outside the bracket omega's evaluator proves for the field over
  the box, beyond a margin of its own, so something the field holds was not meshed (a wall thinner than a cell)
  or the mesh holds what the field does not.
- ``degenerate_triangles`` (a warning): triangles of zero area, which a slicer drops and a B-rep sewer cannot.

Every measurement is a row of ``measurements`` (``--json``).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cad.results import CheckResult

__all__ = ["SUFFIXES", "VOLUME_MARGIN", "VOLUME_TOLERANCE", "check", "measure", "queryable", "read_stl"]

SUFFIXES = (".gsl",)
#: The relative tolerance the evaluator's volume bracket is asked for, and the margin a mesh's volume may lie
#: outside it: a mesh's facets cut a curved surface's chords, so a fine mesh of a sphere holds a little less than
#: the field does.
VOLUME_TOLERANCE = 0.01
VOLUME_MARGIN = 0.02
#: The longest one ``gsl`` run may take (s).
TIMEOUT_S = 900.0


def check(path: Path, *, mesh: Path | None = None, strict: bool = False, verbose: bool = False) -> CheckResult:
    from cad._internal.findings import FindingsReport
    from cad._internal.validation_door import blocks, display_path, failed, resolved_target, result_from_findings
    from cad.omega._program import EXTRA, OmegaMissingError, find_gsl

    target = resolved_target(path, label="omega")
    if verbose:
        print(f"[omega] checking {target}", file=sys.stderr)
    if target.suffix.lower() not in SUFFIXES:
        return failed(target, f"target must be a {' or '.join(SUFFIXES)} file")
    if not target.is_file():
        return failed(target, "file not found")
    given = None if mesh is None else Path(mesh).expanduser().absolute()
    if given is not None and not given.is_file():
        return failed(target, f"mesh not found: {given}")
    import importlib.util

    if importlib.util.find_spec("omega_core") is None:
        raise ModuleNotFoundError(f"omega_core comes with cad's omega integration: install {EXTRA}, or run the script "
                                  f"with cad run (add `{EXTRA}` to its header)", name="omega_core")
    try:
        gsl = find_gsl()
    except OmegaMissingError as error:
        return failed(target, str(error), code="program_missing")

    where = display_path(target)
    findings = FindingsReport()
    measurements: dict = {}
    summary = ""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cad-omega-", ignore_cleanup_errors=True) as scratch:
        out = Path(scratch) / (target.stem + (".stl" if given is None else ".ast.json"))
        meta = Path(scratch) / "meta.json"
        # A model that names no box is refused below without running gsl's own guess of one.
        said = _compile(gsl, target, out, meta, mesh=given is None) if _names_scene(target) else None
        if said is not None:
            findings.add("error", "compile_failed", f"gsl refused the model: {said}", path=where)
        else:
            scene = (json.loads(meta.read_text(encoding="utf-8")) or {}).get("scene") if meta.is_file() else None
            if not scene or not scene.get("size"):
                findings.add("error", "no_scene", "the model has no @scene, so gsl guessed the box it meshes in, and "
                             "its guess cuts off features thinner than its search's cells", path=where,
                             hint="add @scene(size) as the first line: an edge of size mm, centred on the origin, "
                                  "that holds the whole part")
            else:
                half = float(scene["size"]) / 2.0
                stl = given if given is not None else out
                try:
                    triangles = read_stl(stl)
                except ValueError as error:
                    findings.add("error", "unreadable_mesh", f"{display_path(stl)}: {error}", path=where)
                else:
                    measurements = measure(triangles)
                    measurements["scene_half_mm"] = half
                    _judge(findings, measurements, half, where)
                    if not findings.errors:
                        bracket = _volume(gsl, target, half, findings, where)
                        if bracket is not None:
                            measurements["field_volume_mm3"] = list(bracket)
                            _judge_volume(findings, measurements["volume_mm3"], bracket, where)
                    if not blocks(findings, strict=strict):
                        low, high = measurements["bbox_min"], measurements["bbox_max"]
                        size = " x ".join(f"{b - a:.4g}" for a, b in zip(low, high))
                        summary = (f"OK {where}: {measurements['triangles']} triangles, "
                                   f"{measurements['volume_mm3']:.6g} mm3, {size} mm, in @scene({scene['size']:g})")
    result = result_from_findings(target, findings.deduplicated(), strict=strict, summary=summary)
    return CheckResult(ok=result.ok, path=result.path, findings=result.findings, summary=result.summary,
                       measurements=measurements)


def _names_scene(target: Path) -> bool:
    """Whether the model names the box it is meshed in: a line that starts ``@scene(``."""
    import re

    return re.search(r"^\s*@scene\s*\(", target.read_text(encoding="utf-8", errors="replace"), flags=re.M) is not None


def _compile(gsl: Path, target: Path, out: Path, meta: Path, *, mesh: bool) -> str | None:
    """Run ``gsl compile`` on ``target`` with gsl's own defaults (``-t stl``: mdc at its default depth, in the
    ``@scene`` box), or ``-t ast`` where a mesh was given and only the scene is read; None, or gsl's words when it
    refuses."""
    from cad._internal.programs import private_run

    command = [str(gsl), "compile", "-t", "stl" if mesh else "ast", "-o", str(out), "-m", str(meta), str(target)]
    with private_run("cad-gsl-") as (_folder, env):
        try:
            done = subprocess.run(command, cwd=target.parent, env=env, capture_output=True, text=True,
                                  errors="replace", timeout=TIMEOUT_S, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return f"gsl compile took longer than {TIMEOUT_S:.0f} s"
        except OSError as error:
            return f"gsl does not run: {error.strerror or error}"
    if done.returncode == 0:
        return None
    return _said(done.stderr) or f"gsl compile exited {done.returncode}"


def _said(stderr: str) -> str:
    """gsl's own words for a refusal: its error lines, without its progress lines (``mdc phase``, ``[mesh]``)."""
    lines = [line.strip() for line in stderr.splitlines()
             if line.strip() and "mdc phase" not in line and not line.lstrip().startswith("[mesh]")]
    return " ".join(lines[-3:])


def read_stl(path: Path):
    """The triangles of a binary or ASCII STL, as an ``(n, 3, 3)`` float64 array."""
    import numpy as np

    data = Path(path).read_bytes()
    if len(data) >= 84:
        count = int.from_bytes(data[80:84], "little")
        if len(data) == 84 + 50 * count:
            record = np.dtype([("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
            return np.frombuffer(data, dtype=record, count=count, offset=84)["vertices"].astype(np.float64)
    text = data.decode("ascii", errors="replace")
    if not text.lstrip().startswith("solid"):
        raise ValueError("not an STL")
    values = [line.split()[1:4] for line in text.splitlines() if line.strip().startswith("vertex")]
    if len(values) % 3:
        raise ValueError("an ASCII STL whose vertices are not in threes")
    return np.asarray(values, dtype=np.float64).reshape(-1, 3, 3)


def measure(triangles) -> dict:
    """What a mesh is, from its triangles alone: how many, the edges shared by one triangle and by three or more
    (vertices welded where they are equal), the zero-area triangles, the signed volume and the box."""
    import numpy as np

    count = len(triangles)
    if count == 0:
        return {"triangles": 0, "open_edges": 0, "non_manifold_edges": 0, "degenerate_triangles": 0,
                "volume_mm3": 0.0, "bbox_min": [0.0, 0.0, 0.0], "bbox_max": [0.0, 0.0, 0.0]}
    points = triangles.reshape(-1, 3)
    _unique, index = np.unique(points, axis=0, return_inverse=True)
    faces = index.reshape(-1, 3)
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _edges, uses = np.unique(edges, axis=0, return_counts=True)
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    cross = np.cross(b - a, c - a)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    volume = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
    return {"triangles": int(count), "open_edges": int((uses == 1).sum()), "non_manifold_edges": int((uses > 2).sum()),
            "degenerate_triangles": int((area <= 1e-12).sum()), "volume_mm3": volume,
            "bbox_min": [float(v) for v in points.min(axis=0)], "bbox_max": [float(v) for v in points.max(axis=0)]}


def _judge(findings, measured: dict, half: float, where: str) -> None:
    """The findings a mesh's own measurements make (``measure``), against its ``@scene`` box's half-edge."""
    if measured["triangles"] == 0:
        findings.add("error", "empty_mesh", "gsl wrote no triangles: every wall is thinner than a mesh cell, or the "
                     "field is empty inside @scene", path=where,
                     hint="thicken the walls or mesh finer (gsl compile --subdivision)")
        return
    if measured["open_edges"]:
        findings.add("error", "open_edges", f"{measured['open_edges']} edges belong to one triangle: the mesh has "
                     "holes, so it is no solid", path=where)
    if measured["non_manifold_edges"]:
        findings.add("error", "non_manifold", f"{measured['non_manifold_edges']} edges are shared by three or more "
                     "triangles: the mesh is no single solid there (bodies touching along an edge, or a mesher "
                     "fault)", path=where)
    if measured["volume_mm3"] <= 0:
        findings.add("error", "inside_out", f"the triangles enclose {measured['volume_mm3']:.6g} mm3: their faces "
                     "point inward", path=where)
    reach = half * (1.0 - 1e-4)
    sides = [f"{'-' if bound == 'min' else '+'}{axis}"
             for bound, values in (("min", measured["bbox_min"]), ("max", measured["bbox_max"]))
             for axis, value in zip("xyz", values) if abs(value) >= reach]
    if sides:
        findings.add("error", "cut_off", f"the mesh reaches the @scene box at {', '.join(sides)} ({half:g} mm from "
                     "the origin): the part goes on past it, or the field never ends there", path=where,
                     hint="make @scene's size larger than the part, centred on the origin, or bound the field")
    if measured["degenerate_triangles"]:
        findings.add("warning", "degenerate_triangles", f"{measured['degenerate_triangles']} triangles have no "
                     "area", path=where)


def _volume(gsl: Path, target: Path, half: float, findings, where: str) -> tuple[float, float] | None:
    """The bracket omega's evaluator proves for the volume where the field is negative over the ``@scene`` box,
    as ``(lower, upper)`` mm3; None, with an error naming why, where it answers none."""
    import omega_core

    try:
        with omega_core.Session(source_paths=(target.parent,), program=str(gsl)) as session:
            answer = session.code(queryable(target.read_text(encoding="utf-8"))).volume(
                region=(-half, -half, -half, half, half, half), relative_tolerance=VOLUME_TOLERANCE)
    except omega_core.EvalError as error:
        findings.add("error", "volume_not_measured", f"omega's evaluator measured no volume, so a lost wall cannot "
                     f"be ruled out: {error}", path=where)
        return None
    return float(answer.lower_mm3), float(answer.upper_mm3)


def queryable(text: str) -> str:
    """A model's text as omega-core 0.1.1's evaluator can assemble a query of it: without its ``@scene`` line and
    its whole-line comments. The evaluator rebuilds the model around a ``return`` of its own, and in 0.1.1 that
    rebuild fails on a whole-line comment just above the model's ``return`` and on a ``return`` just below
    ``@scene`` (``failed to assemble query: return // ...``), so a model ``gsl compile`` meshes would be refused
    here. Neither line changes the field, and the region a check asks about is given outright. omega-core #46 fixes
    the rebuild; this stays until the pin moves to a release that carries it."""
    import re

    kept = [line for line in text.splitlines()
            if not line.lstrip().startswith("//") and not re.fullmatch(r"\s*@scene\s*\([^)]*\)\s*;?\s*", line)]
    return "\n".join(kept) + "\n"


def _judge_volume(findings, volume: float, bracket: tuple[float, float], where: str) -> None:
    low, high = bracket
    if low * (1.0 - VOLUME_MARGIN) <= volume <= high * (1.0 + VOLUME_MARGIN):
        return
    findings.add("error", "volume_mismatch", f"the mesh holds {volume:.6g} mm3 and the field {low:.6g} to "
                 f"{high:.6g} mm3: {'something the field holds was not meshed (a wall thinner than a mesh cell)' if volume < low else 'the mesh holds more than the field'}",
                 path=where, hint="mesh finer (gsl compile --subdivision) or thicken the thin walls")
