"""What the ``cadgen.fea`` verbs do, end to end."""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from cadgen.results import FeaFace, FeaFacesResult, FeaResult

if TYPE_CHECKING:
    from cadgen.step_scene import Occurrence, Selection, StepScene

__all__ = ["list_faces", "solve_study"]

_AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def _log(verbose: bool):
    started = time.perf_counter()

    def emit(message: str) -> None:
        if verbose:
            print(f"[cadgen fea] {time.perf_counter() - started:6.1f}s {message}", file=sys.stderr)

    return emit


def _open(target: Path) -> "StepScene":
    from cadgen._internal.doors import STEP_SUFFIXES, document_target
    from cadgen.step_scene import read_scene

    return read_scene(document_target(target, suffixes=STEP_SUFFIXES))


def _single_occurrence(scene: "StepScene", refs: "tuple[str, ...]") -> tuple["Occurrence", dict[str, "Selection"]]:
    """The one leaf occurrence every face ref belongs to, and each ref resolved."""
    resolved: dict[str, Selection] = {}
    owners: set[str] = set()
    for ref in refs:
        selection = scene.resolve(ref)
        if selection.kind != "face":
            raise ValueError(f"{ref} is a {selection.kind} reference; fixtures and loads take faces (#o1.f17)")
        resolved[ref] = selection
        owners.add(selection.occurrence_ref)
    if len(owners) > 1:
        raise ValueError(
            f"the study's faces span {len(owners)} occurrences ({', '.join(sorted(owners))}); "
            "a study solves one part, so every face must be on the same occurrence"
        )
    owner = next(iter(owners))
    occurrence = scene.resolve(owner)
    return occurrence, resolved  # type: ignore[return-value]


def _axis_word(normal: tuple[float, float, float] | None) -> str:
    if normal is None:
        return ""
    for name, axis in _AXES.items():
        dot = sum(a * b for a, b in zip(normal, axis))
        if dot > math.cos(math.radians(5)):
            return f"+{name}"
        if dot < -math.cos(math.radians(5)):
            return f"-{name}"
    return f"({normal[0]:.2f}, {normal[1]:.2f}, {normal[2]:.2f})"


def _rank_word(rank: int) -> str:
    if rank == 1:
        return "largest"
    suffix = "th" if 10 <= rank % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix} largest"


def list_faces(target: Path, *, occurrence: str | None = None, verbose: bool = False) -> FeaFacesResult:
    log = _log(verbose)
    scene = _open(Path(target))
    if occurrence:
        owner = scene.resolve(occurrence)
        if owner.kind != "occurrence":
            raise ValueError(f"{occurrence} is not an occurrence reference")
    else:
        leaves = list(scene.leaves())
        if len(leaves) != 1:
            raise ValueError(
                f"the document has {len(leaves)} part occurrences; pass --occurrence "
                f"{' or '.join(leaf.ref for leaf in leaves[:4])}{' ...' if len(leaves) > 4 else ''}"
            )
        owner = leaves[0]
    log(f"listing faces of {owner.ref}")

    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    rows = []
    for selection in owner.entities("face"):
        face = selection.shape()
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        centre = props.CentreOfMass()
        surface = str(getattr(face.geom_type, "name", face.geom_type)).lower()
        normal = None
        if surface == "plane":
            n = face.normal_at()
            normal = (float(n.X), float(n.Y), float(n.Z))
        rows.append((selection.ref, float(props.Mass()), (centre.X(), centre.Y(), centre.Z()), surface, normal))
    by_area = sorted(range(len(rows)), key=lambda i: -rows[i][1])
    rank = {index: position + 1 for position, index in enumerate(by_area)}
    faces = []
    for index, (ref, area, centre, surface, normal) in enumerate(rows):
        words = [surface]
        if normal is not None:
            words.append(f"normal {_axis_word(normal)}")
        words.append(_rank_word(rank[index]))
        faces.append(FeaFace(
            ref=ref,
            area_mm2=round(area, 4),
            center_mm=tuple(round(c, 4) for c in centre),
            surface=surface,
            normal=None if normal is None else tuple(round(c, 6) for c in normal),
            hint=", ".join(words),
        ))
    return FeaFacesResult(ok=True, document=Path(target), occurrence=owner.ref, faces=tuple(faces))


def solve_study(
    target: Path,
    out: Path | None,
    *,
    study,
    mesh_size: float | None = None,
    vtu: bool = False,
    verbose: bool = False,
) -> FeaResult:
    from cadgen._internal.fea.study import parse_study

    parsed = parse_study(study)  # stdlib, before any heavy import
    log = _log(verbose)
    document = Path(target)
    glb_path = Path(out) if out is not None else document.with_name(f"{document.stem}.fea.glb")
    if glb_path.suffix.lower() != ".glb":
        raise ValueError(f"OUT names the result GLB and must end in .glb: {out}")
    sidecar_path = glb_path.with_suffix(".json")
    vtu_path = glb_path.with_suffix(".vtu") if vtu else None

    from cadgen._internal.fea.mesh import mesh_occurrence, require_fea_stack

    require_fea_stack()
    scene = _open(document)
    occurrence, resolved = _single_occurrence(scene, parsed.face_refs)
    ordinal_of = {ref: int(selection._ordinal) for ref, selection in resolved.items()}
    log(f"meshing {occurrence.ref}")
    volume = mesh_occurrence(scene, occurrence, max_h=mesh_size or parsed.mesh_size, verbose=verbose)
    log(f"meshed: {len(volume.tets)} tets, {len(volume.nodes)} nodes, size {volume.max_h:.3g} mm in {volume.seconds:.1f}s")

    import numpy as np

    from cadgen._internal.fea.outputs import auto_deformation_scale, write_glb, write_vtu
    from cadgen._internal.fea.solve import solve_linear_static

    outcome = solve_linear_static(volume, parsed.material, parsed.fixtures, parsed.loads, ordinal_of, log=log)

    magnitude = np.linalg.norm(outcome.displacement, axis=1)
    max_disp_index = int(magnitude.argmax())
    max_vm_index = int(outcome.von_mises.argmax())
    # Rounded once, here, so the summary, the sidecar's legend and the GLB's
    # extras all carry the same number.
    max_vm = round(float(outcome.von_mises[max_vm_index]), 4)
    scale = parsed.deformation_scale or auto_deformation_scale(float(magnitude.max()), volume.bbox_diagonal)
    material = parsed.material
    safety = material.yield_strength / max_vm if max_vm > 0 else math.inf
    warnings = list(outcome.warnings)
    if outcome.von_mises_gauss_max > 1.5 * max_vm > 0:
        warnings.append(
            f"the Gauss-point peak ({outcome.von_mises_gauss_max:.1f} MPa) is well above the nodal peak "
            f"({max_vm:.1f} MPa): a stress concentration at a fixed edge or sharp corner is not resolved; "
            "refine mesh.size_mm once and compare, and read the peak away from the fixture"
        )
    reaction_total = tuple(sum(r[c] for r in outcome.reactions) for c in range(3))
    balance = max(abs(a + r) for a, r in zip(outcome.applied, reaction_total))
    if balance > 1e-3 * max(1.0, max(abs(a) for a in outcome.applied)):
        warnings.append(f"reactions do not balance the applied load (mismatch {balance:.3g} N)")

    extras = {
        "name": f"{document.stem} von Mises",
        "generator": "cadgen fea",
        "field": "von_mises",
        "units": "MPa",
        "min": 0.0,
        "max": max_vm,
        "deformation_scale": scale,
        "document": document.name,
        "occurrence": occurrence.ref,
        # One entry per raw attribute the GLB carries, for a viewer's field
        # switch. `attribute_scale` turns the stored value into the units named:
        # the displacement vector is stored in glTF metres.
        "fields": [
            {"attribute": "_VON_MISES", "name": "von Mises stress", "units": "MPa", "min": 0.0, "max": max_vm,
             "attribute_scale": 1.0},
            {"attribute": "_DISPLACEMENT", "name": "displacement", "units": "mm", "min": 0.0,
             "max": round(float(magnitude.max()), 6), "attribute_scale": 1000.0},
        ],
    }
    vertex_count = outcome.vertices
    write_glb(
        glb_path,
        positions=outcome.dof_locations,
        displacement=outcome.displacement,
        values=outcome.von_mises,
        triangles6=outcome.boundary_quadratic,
        scale=scale,
        value_range=(0.0, max_vm),
        extras=extras,
    )
    if vtu_path is not None:
        write_vtu(
            vtu_path,
            positions=outcome.dof_locations[:vertex_count],
            tets=outcome.tets,
            displacement=outcome.displacement[:vertex_count],
            values=outcome.von_mises[:vertex_count],
        )

    summary = {
        "max_von_mises_MPa": max_vm,
        "max_von_mises_gauss_MPa": round(outcome.von_mises_gauss_max, 4),
        "max_von_mises_at_mm": [round(float(c), 3) for c in outcome.dof_locations[max_vm_index]],
        "yield_MPa": material.yield_strength,
        "safety_factor": None if math.isinf(safety) else round(safety, 3),
        "max_displacement_mm": round(float(magnitude.max()), 6),
        "max_displacement_at_mm": [round(float(c), 3) for c in outcome.dof_locations[max_disp_index]],
        "applied_force_N": [round(x, 4) for x in outcome.applied],
        "reaction_force_N": [round(x, 4) for x in reaction_total],
        "deformation_scale": scale,
    }
    mesh_info = {
        "elements": int(len(volume.tets)),
        "nodes": int(len(volume.nodes)),
        "dofs": outcome.dofs,
        "size_mm": round(volume.max_h, 4),
        "order": 2,
        "mesher": "netgen",
        "solver": outcome.solver,
    }
    timings = {"mesh_s": round(volume.seconds, 3), **{k: round(v, 3) for k, v in outcome.timings.items()}}
    sidecar = {
        "generator": "cadgen fea",
        "document": str(document),
        "occurrence": occurrence.ref,
        "study": parsed.source,
        "material": material.as_dict(),
        "faces": {ref: volume.faces[ordinal].__dict__ for ref, ordinal in ordinal_of.items()},
        "summary": summary,
        "fixtures": [
            {"faces": list(fixture.faces), "type": fixture.type, "reaction_N": [round(x, 4) for x in reaction]}
            for fixture, reaction in zip(parsed.fixtures, outcome.reactions)
        ],
        "mesh": mesh_info,
        "timings": timings,
        "warnings": warnings,
        "files": {"glb": glb_path.name, "vtu": vtu_path.name if vtu_path else None},
        "legend": {"field": "von_mises", "units": "MPa", "min": 0.0, "max": max_vm},
    }
    sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    log(f"wrote {glb_path.name}, {sidecar_path.name}" + (f", {vtu_path.name}" if vtu_path else ""))
    return FeaResult(
        ok=True,
        document=document,
        occurrence=occurrence.ref,
        glb=glb_path,
        sidecar=sidecar_path,
        vtu=vtu_path,
        summary=summary,
        mesh=mesh_info,
        timings=timings,
        warnings=tuple(warnings),
    )
