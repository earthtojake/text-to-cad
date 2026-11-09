"""A decomposed collision's convex hulls (``collision(part, "decomposed")``), kept in the engine's cache:
meshes in, each one's hulls out, made by the coacd integration's decomposer in a process of its own.

**Why a process of its own.** CoACD's wheel is one native library loaded with ``ctypes`` that carries its own
build of TBB (its symbols exported) beside the TBB OCCT runs on, which is the clash netgen's OpenCascade has
with OCP's; it logs from native code to file descriptor 1, which is a worker's protocol; and it can die on a
mesh it cannot repair. So the process that holds the kernel never imports it: each decomposition is a child
interpreter of this environment (``python -m cad.coacd._decomposer JOB RESULT``, the integration's code, which
imports coacd and numpy alone), handed every mesh the cache does not hold at once. A child that dies, or stops
past ``TIMEOUT_S``, fails the decomposition in one line with the end of what it printed.

**What it is asked.** Each mesh is ``(positions, triangles, options)``: positions ``(n, 3)``, triangles ``(m,
3)``, and ``options`` the declaration's (``maxHulls``: CoACD's ``max_convex_hull``, at most that many hulls,
merged down to it; ``threshold``: its concavity threshold, 0.01 to 1, smaller cutting finer), each absent for
CoACD's own default (no limit; 0.05). The child welds the corners a tessellation repeats on each face and
runs CoACD with seed 0 (``cad.coacd._decomposer``), so the same mesh and options make the same hulls.

**The cache.** A decomposition takes CoACD seconds to minutes, and a model is exported again on every
change, so each mesh's hulls are kept in the engine's cache folder, never beside the model:
``places.cache_dir()/hulls/<digest>.npz``, the digest of the recipe (``RECIPE``: the CoACD release line the
extra pins, the weld and the seed), the options and the mesh's own bytes (its positions as little-endian
float32, its triangles as little-endian uint32). A hit reads the hulls back with no coacd here at all, and
a changed part, a changed option or another release line is a new key. A file that does not read is
decomposed again and written over. It is a cache: wiping it costs a decomposition, never a document.

**Where coacd is.** The child runs this interpreter, so a decomposition the cache does not hold needs coacd
in this environment: the extra, ``cad[coacd]`` (``cad run`` makes a model's environment with it where its
header names it). Without it, ``Unavailable`` says so, naming the extra.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["EXTRA", "RECIPE", "TIMEOUT_S", "Failed", "Unavailable", "digest", "hulls"]

EXTRA = "cad[coacd]"
#: The coacd integration's decomposer, run as a module in the child (never imported here).
CHILD = "cad.coacd._decomposer"
#: What the hulls are a function of beside the mesh and the options: the CoACD release line the extra pins
#: (``coacd>=1.0.14,<1.1``), the weld and the seed. A change here is a new key for every mesh.
RECIPE = "coacd 1.0; welded; seed 0; v1"
#: The longest one child may take (s): past it the child is stopped and the decomposition says so, rather
#: than a decomposition that never returns holding an export (and the engine or the worker it runs in).
TIMEOUT_S = 3600.0

Mesh = tuple[np.ndarray, np.ndarray, dict[str, Any]]
Hull = tuple[np.ndarray, np.ndarray]


class Unavailable(RuntimeError):
    """A decomposition the cache does not hold, asked for where coacd is not installed."""


class Failed(RuntimeError):
    """CoACD did not decompose mesh ``index`` (its own words), or its process stopped."""

    def __init__(self, text: str, index: int | None = None) -> None:
        super().__init__(text)
        self.index = index


def digest(positions: Any, triangles: Any, options: dict[str, Any]) -> str:
    """The cache key of one mesh's hulls (the module's **The cache**), as hex."""
    points = np.ascontiguousarray(np.asarray(positions, dtype="<f4").reshape(-1, 3))
    corners = np.ascontiguousarray(np.asarray(triangles, dtype="<u4").reshape(-1, 3))
    found = hashlib.sha256(RECIPE.encode("utf-8"))
    found.update(b"\0" + json.dumps(options, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    for array in (points, corners):
        found.update(b"\0" + str(len(array)).encode("ascii") + b"\0" + array.tobytes())
    return found.hexdigest()


def hulls(meshes: Sequence[Mesh]) -> list[list[Hull]]:
    """Each mesh's hulls (the module docstring), each ``(positions float32 (n, 3), triangles uint32 (m, 3))``:
    the cache's where it holds them, else CoACD's, all the misses in one child, and kept."""
    from cad.engine.places import cache_dir

    folder = cache_dir() / "hulls"
    found: list[list[Hull] | None] = []
    keys = []
    for positions, triangles, options in meshes:
        key = digest(positions, triangles, options)
        keys.append(key)
        found.append(_read(folder / f"{key}.npz"))
    missing = [at for at, held in enumerate(found) if held is None]
    if missing:
        made = _decompose([meshes[at] for at in missing])
        for at, held in zip(missing, made):
            found[at] = held
            _write(folder / f"{keys[at]}.npz", held)
    return [held or [] for held in found]


def _read(path: Path) -> list[Hull] | None:
    if not path.is_file():
        return None
    try:
        with np.load(path, allow_pickle=False) as held:
            count = int(held["count"])
            return [(np.asarray(held[f"p{at}"], dtype=np.float32).reshape(-1, 3),
                     np.asarray(held[f"t{at}"], dtype=np.uint32).reshape(-1, 3)) for at in range(count)]
    except (OSError, ValueError, KeyError):
        return None


def _write(path: Path, found: list[Hull]) -> None:
    from cad.engine.atomic_replace import put

    arrays: dict[str, np.ndarray] = {"count": np.array(len(found))}
    for at, (positions, triangles) in enumerate(found):
        arrays[f"p{at}"], arrays[f"t{at}"] = positions, triangles

    def write(staged: Path) -> None:
        with staged.open("wb") as handle:
            np.savez(handle, **arrays)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        put(path, write, compare=False)
    except OSError:
        pass  # a cache that cannot be written decomposes again next time


def _decompose(meshes: Sequence[Mesh]) -> list[list[Hull]]:
    """CoACD's hulls of ``meshes``, made in one child process (the module's **Why a process of its own**)."""
    import importlib.util

    if importlib.util.find_spec("coacd") is None:
        raise Unavailable(f"coacd comes with cad's coacd integration, {EXTRA}, which this environment does not hold")

    jobs = [{"positions": np.asarray(p, dtype=np.float64).reshape(-1, 3), "triangles": np.asarray(t).reshape(-1, 3),
             "options": dict(options)} for p, t, options in meshes]
    with tempfile.TemporaryDirectory(prefix="cad-coacd-") as tmp:
        job_path, result_path = Path(tmp) / "job.pickle", Path(tmp) / "result.pickle"
        job_path.write_bytes(pickle.dumps(jobs))
        try:
            done = subprocess.run([sys.executable, "-P", "-m", CHILD, str(job_path), str(result_path)],
                                  env=_child_env(Path(__file__).resolve().parents[2]), stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired as error:
            raise Failed(f"CoACD did not finish in {TIMEOUT_S:.0f} s and was stopped; fewer hulls (max_hulls) or a "
                         "coarser threshold decomposes sooner") from error
        if not result_path.is_file():
            said = (done.stderr or done.stdout).strip().splitlines()[-12:]
            raise Failed(f"CoACD stopped (exit {done.returncode}) before it wrote its hulls"
                         + ("".join(f"\n  {line}" for line in said) if said else ""))
        results = pickle.loads(result_path.read_bytes())
    found = []
    for at, result in enumerate(results):
        if "error" in result:
            raise Failed(result["error"], at)
        found.append([(np.asarray(p, dtype=np.float32).reshape(-1, 3), np.asarray(t, dtype=np.uint32).reshape(-1, 3))
                      for p, t in result["hulls"]])
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
