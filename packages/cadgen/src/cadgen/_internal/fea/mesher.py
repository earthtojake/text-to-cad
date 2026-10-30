"""netgen in a process of its own: a BREP file in, the mesh's arrays out.

The ``netgen-mesher`` wheel brings its own OpenCascade (``netgen_occt``, 7.8) and cadgen runs on OCP's
OpenCascade 8. Loaded into one process, the two builds share symbols: a Boolean in OCP can crash after
netgen is imported, and the interpreter aborts on exit even when nothing crashed. So netgen is never
imported in cadgen's process. Each mesh is a child interpreter (``python -m cadgen._internal.fea.mesher
JOB RESULT``) that imports netgen and none of OCP: it reads the BREP the parent wrote, matches netgen's
faces to the parent's fingerprints (:func:`~cadgen._internal.fea.mesh.match_faces`), meshes
(:func:`~cadgen._internal.fea.mesh.generate_mesh`) and pickles copies of the arrays back.

One job: a solid's volume mesh (:func:`volume`, the part and assembly meshers'). A mesher error (a face
that does not match, no elements) is a RuntimeError in the parent with the child's message; a child that dies says so with the
end of what it printed.
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

__all__ = ["volume"]

#: The longest one mesh may take (s): past it the child is stopped and the study says so, rather than a
#: mesher that never returns holding ``cadgen fea solve`` (and the engine or MCP server it runs in) for good.
TIMEOUT_S = 3600.0


def volume(brep: Path, prints: list, diagonal: float, h: float, refine: float, size_field: dict | None,
           *, count_domains: bool = False):
    """netgen's mesh of the solid in ``brep``: the verified face mapping (netgen face index -> fingerprint
    ordinal), the nodes, the volume and surface elements, and (``count_domains``) the number of volumes."""
    found = _run({"brep": str(brep), "prints": prints, "diagonal": diagonal, "h": h, "refine": refine,
                  "size_field": size_field, "count_domains": count_domains})
    return found["mapping"], found["coordinates"], found["e3"], found["e2"], found["domains"]


def _run(job: dict) -> dict:
    import cadgen

    with tempfile.TemporaryDirectory(prefix="cadgen-mesher-") as tmp:
        job_path, result_path = Path(tmp) / "job.pickle", Path(tmp) / "result.pickle"
        job_path.write_bytes(pickle.dumps(job))
        try:
            done = subprocess.run([sys.executable, "-P", "-m", "cadgen._internal.fea.mesher", str(job_path),
                                   str(result_path)], env=_child_env(Path(cadgen.__file__).resolve().parents[1]),
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
    """The child's environment: this one, with the folder this cadgen was imported from first on its
    PYTHONPATH where the interpreter would not find it by itself (a source checkout, a test's path). Never
    a site-packages folder: on PYTHONPATH it would come before the standard library."""
    import site

    sites = {Path(p).resolve() for p in [*site.getsitepackages(), site.getusersitepackages()]}
    if source in sites:
        return dict(os.environ)
    return {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(source), os.environ.get("PYTHONPATH")]))}


def _volume(job: dict) -> dict:
    import netgen.meshing as ngmesh
    import netgen.occ as ngocc
    import numpy as np

    from cadgen._internal.fea.mesh import generate_mesh, match_faces

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
        from cadgen._internal.fea.mesh import kernel_messages_on_stderr

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
