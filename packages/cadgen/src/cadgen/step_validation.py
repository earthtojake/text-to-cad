"""Conformance and geometry validation for STEP/STP documents.

Runs topology error analysis (BRepCheck), manifoldness/closure checks,
boolean soundness verification, and mass property checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cadgen.findings import FindingsReport


def validate_step_document(path: Path) -> tuple[FindingsReport, dict[str, Any]]:
    """Validate one STEP document for geometry, topology, and manifold soundness.

    Heavy CAD dependencies (OCP, build123d) are imported lazily inside this
    function so module import remains fast.
    """
    findings = FindingsReport()
    stats: dict[str, Any] = {
        "solids": 0,
        "shells": 0,
        "faces": 0,
        "edges": 0,
        "vertices": 0,
        "volume": 0.0,
    }

    try:
        from cadgen.step_scene import read_step

        shape = read_step(path)
    except Exception as exc:  # noqa: BLE001
        findings.add(
            "error",
            "unparsable_step",
            f"Could not parse STEP document: {exc}",
            path=str(path),
        )
        return findings, stats

    if shape is None:
        findings.add(
            "error",
            "empty_geometry",
            "STEP document contains no geometry",
            path=str(path),
        )
        return findings, stats

    from cadgen.geometry import boundary_edges, is_sound, topology_errors

    # 1. Enumerate sub-shapes
    try:
        solids = list(shape.solids()) if hasattr(shape, "solids") else []
    except Exception:  # noqa: BLE001
        solids = []

    try:
        shells = list(shape.shells()) if hasattr(shape, "shells") else []
    except Exception:  # noqa: BLE001
        shells = []

    try:
        faces = list(shape.faces()) if hasattr(shape, "faces") else []
    except Exception:  # noqa: BLE001
        faces = []

    try:
        edges = list(shape.edges()) if hasattr(shape, "edges") else []
    except Exception:  # noqa: BLE001
        edges = []

    try:
        vertices = list(shape.vertices()) if hasattr(shape, "vertices") else []
    except Exception:  # noqa: BLE001
        vertices = []

    stats["solids"] = len(solids)
    stats["shells"] = len(shells)
    stats["faces"] = len(faces)
    stats["edges"] = len(edges)
    stats["vertices"] = len(vertices)

    if not faces and not solids and not edges and not vertices:
        findings.add(
            "error",
            "empty_geometry",
            "STEP document contains no faces, solids, or topological entities",
            path=str(path),
        )
        return findings, stats

    # 2. Topology errors via BRepCheck
    try:
        issues = topology_errors(shape)
        for issue in issues:
            findings.add(
                "error",
                f"topology_{issue.code.lower()}",
                f"Topology fault ({issue.code}) detected on geometry",
                path=str(path),
            )
    except Exception as exc:  # noqa: BLE001
        findings.add(
            "error",
            "topology_check_failed",
            f"Topology analysis failed: {exc}",
            path=str(path),
        )

    # 3. Boolean argument soundness
    try:
        sound = is_sound(shape)
        if not sound and not findings.errors:
            findings.add(
                "error",
                "unsound_geometry",
                "Kernel boolean argument check failed (self-intersection, invalid type, or degenerate edge)",
                path=str(path),
            )
    except Exception as exc:  # noqa: BLE001
        findings.add(
            "error",
            "soundness_check_failed",
            f"Soundness verification failed: {exc}",
            path=str(path),
        )

    # 4. Shell closure / boundary edges
    # For solids, every shell should be closed (manifold/watertight).
    shells_to_check = shells
    if solids:
        for i, solid in enumerate(solids, 1):
            solid_shells = list(solid.shells()) if hasattr(solid, "shells") else []
            for j, shell in enumerate(solid_shells, 1):
                try:
                    free_edges = boundary_edges(shell)
                    if free_edges:
                        findings.add(
                            "warning",
                            "open_shell",
                            f"Solid {i} shell {j} has {len(free_edges)} free boundary edge(s); shape is not closed/watertight",
                            path=str(path),
                            hint="Ensure all faces join along shared edges to form a closed, manifold shell.",
                        )
                except Exception as exc:  # noqa: BLE001
                    findings.add(
                        "warning",
                        "boundary_check_failed",
                        f"Could not verify boundary edges for solid {i}: {exc}",
                        path=str(path),
                    )
    elif shells_to_check:
        for j, shell in enumerate(shells_to_check, 1):
            try:
                free_edges = boundary_edges(shell)
                if free_edges:
                    findings.add(
                        "info",
                        "surface_boundary",
                        f"Surface shell {j} has {len(free_edges)} boundary edge(s)",
                        path=str(path),
                    )
            except Exception:  # noqa: BLE001
                pass

    # 5. Volume and mass properties
    total_volume = 0.0
    for i, solid in enumerate(solids, 1):
        try:
            from cadgen.geometry import _properties

            props = _properties(solid.wrapped)
            vol = float(props.Mass())
            total_volume += vol
            if vol <= 0:
                findings.add(
                    "error",
                    "non_positive_volume",
                    f"Solid {i} has non-positive or inverted volume ({vol:g})",
                    path=str(path),
                    hint="Check face orientation or verify solid closure.",
                )
        except Exception as exc:  # noqa: BLE001
            findings.add(
                "warning",
                "volume_evaluation_failed",
                f"Could not compute volume for solid {i}: {exc}",
                path=str(path),
            )

    stats["volume"] = total_volume
    return findings, stats
