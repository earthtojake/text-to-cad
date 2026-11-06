"""netgen, always in a process of its own: a BREP file in, the mesh's arrays out.

The ``netgen-mesher`` wheel brings its own OpenCascade (``netgen_occt``, 7.8) and cad runs on OCP's
OpenCascade 8. Loaded into one process, the two builds share symbols: a Boolean in OCP can crash after
netgen is imported, and the interpreter aborts on exit even when nothing crashed. So netgen is never
imported in cad's process. Each mesh is a child interpreter (``python -m cad.netgen._mesher
JOB RESULT``) that imports netgen and none of OCP: it reads the BREP the parent wrote, matches netgen's
faces to the parent's fingerprints (:func:`match_faces`), meshes (:func:`generate_mesh`) and pickles copies of the arrays back.

One job: a solid's volume mesh (:func:`volume`, the part and assembly meshers'). A mesher error (a face
that does not match, no elements) is a RuntimeError in the parent with the child's message; a child that dies says so with the
end of what it printed.
"""

from __future__ import annotations

import contextlib
import os
import pickle
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cad._internal.fea.mesh import FaceFingerprint

__all__ = ["NETGEN_EDGES", "NETGEN_PLATFORMS", "volume"]

#: Where netgen publishes wheels, and so where cad installs it (its marker in ``pyproject.toml``).
NETGEN_PLATFORMS = "macOS, Linux x86_64 and Windows x86_64"
#: netgen's: its tetrahedron's mid-edge nodes 5-10 sit on these corner pairs.
NETGEN_EDGES = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))

#: The longest one mesh may take (s): past it the child is stopped and the study says so, rather than a
#: mesher that never returns holding ``cad fea solve`` (and the engine or MCP server it runs in) for good.
TIMEOUT_S = 3600.0


def volume(brep: Path, prints: list, diagonal: float, h: float, refine: float, size_field: dict | None,
           *, count_domains: bool = False):
    """netgen's mesh of the solid in ``brep``: the verified face mapping (netgen face index -> fingerprint
    ordinal), the nodes, the volume and surface elements, and (``count_domains``) the number of volumes."""
    found = _run({"brep": str(brep), "prints": prints, "diagonal": diagonal, "h": h, "refine": refine,
                  "size_field": size_field, "count_domains": count_domains})
    return found["mapping"], found["coordinates"], found["e3"], found["e2"], found["domains"]


def _run(job: dict) -> dict:
    import cad

    with tempfile.TemporaryDirectory(prefix="cad-mesher-") as tmp:
        job_path, result_path = Path(tmp) / "job.pickle", Path(tmp) / "result.pickle"
        job_path.write_bytes(pickle.dumps(job))
        try:
            done = subprocess.run([sys.executable, "-P", "-m", "cad.netgen._mesher", str(job_path),
                                   str(result_path)], env=_child_env(Path(cad.__file__).resolve().parents[1]),
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"the mesher did not finish in {TIMEOUT_S:.0f} s and was stopped; a coarser mesh "
                               "(mesh.size_mm) or a simpler part meshes sooner") from error
        if not result_path.is_file():
            said = (done.stderr or done.stdout).strip().splitlines()[-12:]
            raise RuntimeError(f"the mesher stopped (exit {done.returncode}) before it wrote a mesh"
                               + ("".join(f"\n  {line}" for line in said) if said else ""))
        found = pickle.loads(result_path.read_bytes())
    if "error" in found:
        raise RuntimeError(found["error"])
    return found


def _child_env(source: Path) -> dict[str, str]:
    """The child's environment: this one, with the folder this cad was imported from first on its
    PYTHONPATH where the interpreter would not find it by itself (a source checkout, a test's path). Never
    a site-packages folder: on PYTHONPATH it would come before the standard library."""
    import site

    sites = {Path(p).resolve() for p in [*site.getsitepackages(), site.getusersitepackages()]}
    if source in sites:
        return dict(os.environ)
    return {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(source), os.environ.get("PYTHONPATH")]))}


@contextlib.contextmanager
def kernel_messages_on_stderr() -> Iterator[None]:
    """netgen's C++ messages to stderr while it reads and meshes: it prints to file descriptor 1, which is where a
    command's result belongs (``--json``'s line). The redirect is at the descriptor, as the kernel does not write
    through Python's ``sys.stdout``."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        saved = os.dup(1)
    except OSError:
        yield
        return
    try:
        os.dup2(2, 1)
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)


# netgen's defaults (curvature safety 2, grading 0.3) refine to a fillet's or chamfer's own size, however large the
# element size asked for: the 4-part rover cut came to 155k tets at any ``mesh.size_mm``. Grading 0.5 lets the size grow
# faster away from small features, and a curvature safety of 1.5 keeps elements under about a radius: 1 put one element
# across a 6 mm rod's radius at the default size and read its bending stress 20% high (test_fea.DefaultSizeAccuracy).
_MESHING = {"curvaturesafety": 1.5, "grading": 0.5}


def _meshing(refine: float) -> dict:
    """netgen's settings for a mesh ``refine`` times finer than the default at curved features.

    ``maxh`` alone does not refine a fillet or a hole: there the curvature safety
    sets the size, so a finer solve scales it with the ratio it shrinks ``maxh`` by.
    """
    return {**_MESHING, "curvaturesafety": _MESHING["curvaturesafety"] * max(refine, 1.0)}


def match_faces(fingerprints: list[FaceFingerprint], ng_faces, scale: float) -> dict[int, int]:
    """``{netgen face index (0-based): cad ordinal}`` for EVERY face, verified.

    Order is the fast path (netgen face i <-> ordinal i+1); a face that does not agree there is matched by area and
    centre against all of netgen's faces, and an ambiguous or missing match is an error rather than a guess.
    """
    import numpy as np

    ng = [(float(f.mass), np.array([f.center.x, f.center.y, f.center.z], dtype=float)) for f in ng_faces]
    if len(ng) != len(fingerprints):
        raise RuntimeError(
            f"the mesher sees {len(ng)} faces but the document has {len(fingerprints)}; "
            "the geometry did not survive the BREP hand-off intact"
        )
    area_tol = 1e-4
    centre_tol = 1e-4 * max(scale, 1.0)

    def agrees(fp: FaceFingerprint, index: int) -> bool:
        area, centre = ng[index]
        return abs(area - fp.area) <= area_tol * max(fp.area, 1.0) and np.linalg.norm(centre - fp.center) <= centre_tol

    mapping: dict[int, int] = {}
    unresolved = []
    for fp in fingerprints:
        index = fp.ordinal - 1
        if 0 <= index < len(ng) and agrees(fp, index):
            mapping[index] = fp.ordinal
        else:
            unresolved.append(fp)
    for fp in unresolved:
        candidates = [i for i in range(len(ng)) if i not in mapping and agrees(fp, i)]
        if len(candidates) != 1:
            raise RuntimeError(
                f"face {fp.ref} (area {fp.area:.4g} mm^2 at {tuple(round(c, 3) for c in fp.center)}) has "
                f"{len(candidates)} geometric matches in the mesher's faces; cannot place loads on it"
            )
        mapping[candidates[0]] = fp.ordinal
    return mapping


def _offsets(radius: float) -> list[tuple[float, float, float]]:
    """The six points ``radius`` from a centre along the axes."""
    return [tuple(radius * sign if axis == k else 0.0 for k in range(3)) for axis in range(3) for sign in (-1.0, 1.0)]


def generate_mesh(geometry, h: float, refine: float, size_field: dict | None):
    """netgen's second-order mesh at size ``h``; ``size_field`` adds local sizes.

    ``size_field`` is ``{"points": [[x, y, z, size_mm], ...], "radius_mm": r}``: a point holds its size within
    ``radius_mm`` of it (its centre and six points at that distance, netgen grading the rest).
    """
    import netgen.meshing as ngmesh

    if not size_field:
        mesh = geometry.GenerateMesh(maxh=h, **_meshing(refine))
    else:
        parameters = ngmesh.MeshingParameters(maxh=h, **_meshing(refine))
        radius = float(size_field.get("radius_mm") or 0.0)
        offsets = [(0.0, 0.0, 0.0)] + ([] if radius <= 0 else _offsets(radius))
        for x, y, z, size in size_field.get("points") or ():
            for dx, dy, dz in offsets:
                parameters.RestrictH(x=float(x) + dx, y=float(y) + dy, z=float(z) + dz, h=float(size))
        mesh = geometry.GenerateMesh(mp=parameters)
    mesh.SecondOrder()
    return mesh


def _volume(job: dict) -> dict:
    import netgen.meshing as ngmesh
    import netgen.occ as ngocc
    import numpy as np

    ngmesh.SetMessageImportance(0)
    geometry = ngocc.OCCGeometry(job["brep"])
    mapping = match_faces(job["prints"], list(geometry.faces), job["diagonal"])
    mesh = generate_mesh(geometry, job["h"], job["refine"], job["size_field"])
    # Copies, deliberately: netgen hands out views into the mesh object's own memory.
    e3 = mesh.Elements3D().NumPy().copy()
    domains = None
    if job["count_domains"]:
        domains = int(mesh.GetNDomains()) if hasattr(mesh, "GetNDomains") else int(e3["index"].max())
    return {"mapping": mapping, "coordinates": np.array(mesh.Coordinates(), dtype=float, copy=True), "e3": e3,
            "e2": mesh.Elements2D().NumPy().copy(), "domains": domains}


def main(argv: list[str]) -> int:
    job_path, result_path = Path(argv[0]), Path(argv[1])
    job = pickle.loads(job_path.read_bytes())
    try:
        with kernel_messages_on_stderr():
            found = _volume(job)
    except RuntimeError as error:
        found = {"error": str(error)}
    except Exception as error:  # noqa: BLE001 -- said in the parent, with where it came from
        found = {"error": f"the mesher failed: {type(error).__name__}: {error}\n{traceback.format_exc()}"}
    result_path.write_bytes(pickle.dumps(found))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
