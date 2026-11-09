"""``python -m cad.coacd._decomposer JOB RESULT``: CoACD's convex hulls of the meshes in ``JOB``, written to ``RESULT``.

The child process of the engine's decomposition (``cad.engine.hulls``, which says why it is a process of its
own and keeps the hulls in the engine's cache): it reads the meshes the parent wrote (a pickled list of
``{"positions", "triangles", "options"}``), welds each tessellation's repeated corners into one vertex
(exactly equal positions; a triangle that loses a corner goes), so a closed solid reaches CoACD as the
manifold it is and is decomposed as given rather than remeshed first, runs ``coacd.run_coacd`` with seed 0
(``max_convex_hull`` and ``threshold`` where the options give them, CoACD's defaults where not), and writes
each mesh's hulls, or its error in CoACD's words, back. CoACD's native log goes to stderr, and so does a line
as each mesh is done (``DONE``, its index, its hulls and its seconds), which the parent says as that part's progress.
"""

from __future__ import annotations

import os
import pickle
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["DONE", "main", "welded"]

#: The start of the line said on stderr as each mesh is done: ``<DONE> <index> <hulls> <seconds>`` (hulls -1 where it
#: failed). The parent (``cad.engine.hulls``) reads it; it is never shown as it is.
DONE = "cad-coacd-done"


def welded(positions: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A tessellation's repeated corners made one vertex each (exactly equal positions), and the triangles
    that lose a corner to it gone."""
    points, inverse = np.unique(np.asarray(positions, dtype=np.float64).reshape(-1, 3), axis=0, return_inverse=True)
    corners = inverse.reshape(-1)[np.asarray(triangles, dtype=np.int64).reshape(-1, 3)]
    kept = (corners[:, 0] != corners[:, 1]) & (corners[:, 1] != corners[:, 2]) & (corners[:, 0] != corners[:, 2])
    return points, corners[kept].astype(np.int32)


def _one(coacd: Any, job: dict[str, Any]) -> dict[str, Any]:
    points, corners = welded(job["positions"], job["triangles"])
    if not len(corners):
        return {"error": "the mesh has no triangles to decompose"}
    options = job["options"]
    given: dict[str, Any] = {"seed": 0}
    if options.get("maxHulls") is not None:
        given["max_convex_hull"] = int(options["maxHulls"])
    if options.get("threshold") is not None:
        given["threshold"] = float(options["threshold"])
    parts = coacd.run_coacd(coacd.Mesh(points, corners), **given)
    if not parts:
        return {"error": "CoACD made no hulls of the mesh"}
    return {"hulls": [(np.asarray(p, dtype=np.float64), np.asarray(t, dtype=np.int64)) for p, t in parts]}


def main(argv: list[str]) -> int:
    job_path, result_path = Path(argv[0]), Path(argv[1])
    jobs = pickle.loads(job_path.read_bytes())
    sys.stdout.flush()
    os.dup2(2, 1)  # CoACD's native log goes to stderr, never to what reads this process's output
    import coacd

    coacd.set_log_level("error")
    found = []
    for index, job in enumerate(jobs):
        started = time.perf_counter()
        try:
            found.append(_one(coacd, job))
        except Exception as error:  # noqa: BLE001 -- said in the parent, with the part it was
            found.append({"error": f"CoACD failed: {type(error).__name__}: {error}\n{traceback.format_exc()}"})
        made = len(found[-1].get("hulls") or ()) if "error" not in found[-1] else -1
        print(f"{DONE} {index} {made} {time.perf_counter() - started:.3f}", file=sys.stderr, flush=True)
    result_path.write_bytes(pickle.dumps(found))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
