"""A decomposed collision's convex hulls (``collision(part, "decomposed")``), kept in the engine's cache:
meshes in, each one's hulls out, made by the coacd integration's decomposer in a process of its own.

**Why a process of its own.** CoACD's wheel is one native library loaded with ``ctypes`` that carries its own
build of TBB (its symbols exported) beside the TBB OCCT runs on, which is the clash netgen's OpenCascade has
with OCP's; it logs from native code to file descriptor 1, which is a worker's protocol; and it can die on a
mesh it cannot repair. So the process that holds the kernel never imports it: each decomposition is a child
interpreter (``python -m cad.coacd._decomposer JOB RESULT``, the integration's code, which imports coacd and
numpy alone; this environment's Python or the coacd integration's, **Where coacd is**), handed every mesh the
cache does not hold at once. A child that dies, or stops past ``TIMEOUT_S``, fails the decomposition in one line
with the end of what it printed. As each mesh is done the child says so on its stderr (``DONE``), and the part is
said on this process's stderr by its name, its hulls and its seconds: a first export decomposes for minutes.

**What it is asked.** Each mesh is ``(positions, triangles, options)``: positions ``(n, 3)``, triangles ``(m,
3)``, and ``options`` the declaration's (``maxHulls``: CoACD's ``max_convex_hull``, at most that many hulls,
merged down to it, 16 unless the declaration says otherwise; ``threshold``: its concavity threshold, 0.01 to 1,
smaller cutting finer), each absent for CoACD's own default (no limit; 0.05). The child welds the corners a
tessellation repeats on each face and runs CoACD with seed 0 (``cad.coacd._decomposer``), so the same mesh and
options make the same hulls.

**The cache.** A decomposition takes CoACD seconds to minutes, and a model is exported again on every
change, so each mesh's hulls are kept in the engine's cache folder, never beside the model:
``places.cache_dir()/hulls/<digest>.npz``, the digest of the recipe (``RECIPE``: the CoACD release line the
extra pins, the weld and the seed), the options and the mesh's own bytes (its positions as little-endian
float32, its triangles as little-endian uint32). A hit reads the hulls back with no coacd here at all, and
a changed part, a changed option or another release line is a new key. A file that does not read is
decomposed again and written over. It is a cache: wiping it costs a decomposition, never a document.

**Where coacd is.** An integration runs where its extra is installed: the child runs this interpreter where this
environment holds coacd (one installed with ``cad[coacd]``, or a model's whose header names it), else the Python
of the coacd integration's environment, ``cad[coacd]`` at the installation's release, which the device's engine
makes once, outside any sandbox, on first need and keeps (``{"op": "integration", "integration": "coacd"}``
over its door, as the ``cad`` command's ``solve`` has netgen's and CalculiX's: ``cad_server._internal.
integration_env``), each line of its making said on stderr as it comes -- a worker's, which its caller is
shown -- offline first, from uv's cache, and the network for what that lacks; one that cannot reach it says
so in a line. So no model names ``cad[coacd]`` in its header, and an ``.xbf`` or a STEP the documents worker
exports decomposes too. ``Unavailable`` says, naming the extra, why no environment can hold it: CoACD
publishes no wheel for this platform (``PLATFORMS``: none for an Intel Mac, Windows on ARM or a musl Linux),
no engine answers to make it (a model's own process with none running), or its making failed (uv's words).
``PROVIDE`` stands in for the engine (a test's provisioner).
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import subprocess
import sys
import tempfile
import threading
import zipfile
import zlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["DONE", "EXTRA", "PLATFORMS", "PROVIDE", "RECIPE", "TIMEOUT_S", "Failed", "Unavailable", "digest", "hulls",
           "published"]

EXTRA = "cad[coacd]"
#: The coacd integration's decomposer, run as a module in the child (never imported here).
CHILD = "cad.coacd._decomposer"
#: What the hulls are a function of beside the mesh and the options: the CoACD release line the extra pins
#: (``coacd>=1.0.14,<1.1``), the weld and the seed. A change here is a new key for every mesh.
RECIPE = "coacd 1.0; welded; seed 0; v1"
#: Where CoACD publishes wheels, and so where ``cad[coacd]`` installs it (its marker in ``pyproject.toml``;
#: manylinux wheels, so a Linux of glibc's): it has no sdist, so anywhere else no environment can hold it.
PLATFORMS = "macOS arm64, Linux x86_64 and aarch64 (glibc) and Windows x86_64"
#: The Python of the coacd integration's environment, for a process whose own lacks coacd: ``PROVIDE(told)``,
#: made first where it is not, each line of its making said to ``told``; None where nothing answers to make
#: it; ``Unavailable`` in its maker's words where it cannot be made. None: the device's engine's (``_engine``).
PROVIDE: Callable[[Callable[[str], None]], str | None] | None = None
#: The longest one child may take (s): past it the child is stopped and the decomposition says so, rather
#: than a decomposition that never returns holding an export (and the engine or the worker it runs in).
TIMEOUT_S = 3600.0
#: The line the child says on stderr as each mesh is done (``cad.coacd._decomposer.DONE``): ``<DONE> <index>
#: <hulls> <seconds>``.
DONE = "cad-coacd-done"
#: The lines of the child's own output kept, to say why it stopped where it stops.
TAIL = 12

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


def hulls(meshes: Sequence[Mesh], names: Sequence[str] | None = None) -> list[list[Hull]]:
    """Each mesh's hulls (the module docstring), each ``(positions float32 (n, 3), triangles uint32 (m, 3))``:
    the cache's where it holds them, else CoACD's, all the misses in one child, and kept. Misses are said in a
    line on stderr before CoACD starts, by ``names`` (each mesh's part) where given, and each in a line as it is
    done, its hulls (and ``the cap`` where it made as many as its ``maxHulls``: CoACD merged hulls to fit) and its
    seconds: a first decomposition takes minutes, a later one none and says nothing."""
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
        named = [names[at] for at in missing] if names is not None else []
        shown = ""
        if named:
            shown = ": " + ", ".join(named[:4]) + (f" and {len(named) - 4} more" if len(named) > 4 else "")
        print(f"decomposing {len(missing)} part{'s' if len(missing) != 1 else ''} into convex hulls with CoACD{shown} "
              "(seconds to minutes each, once: the hulls are kept for the exports after)", file=sys.stderr, flush=True)

        def done(index: int, made: int, seconds: float) -> None:
            if made < 0:
                return  # its failure is said once the child is done, in CoACD's words
            name = named[index] if index < len(named) else f"part {index + 1}"
            # At its cap, CoACD merged hulls to fit: said, so the hulls are looked at against the part.
            cap = meshes[missing[index]][2].get("maxHulls")
            capped = f", the cap (max_hulls={cap})" if cap is not None and made >= int(cap) else ""
            print(f"decomposed {name}: {made} hull{'s' if made != 1 else ''}{capped} in {seconds:.1f} s "
                  f"({index + 1} of {len(missing)})", file=sys.stderr, flush=True)

        made = _decompose([meshes[at] for at in missing], done)
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
    except (OSError, ValueError, KeyError, EOFError, TypeError, zipfile.BadZipFile, zlib.error):
        # Each is a damaged cache file: empty (EOFError), not a zip or truncated (BadZipFile), a corrupt
        # compressed member (zlib.error), a count that is not a scalar (TypeError), a wrong-shaped array (ValueError).
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


def _decompose(meshes: Sequence[Mesh],
               done: Callable[[int, int, float], None] = lambda _index, _made, _seconds: None) -> list[list[Hull]]:
    """CoACD's hulls of ``meshes``, made in one child process (the module's **Why a process of its own**);
    ``done`` hears each mesh's index, its hulls (-1 where it failed) and its seconds as the child finishes it."""
    python, own = _python()
    jobs = [{"positions": np.asarray(p, dtype=np.float64).reshape(-1, 3), "triangles": np.asarray(t).reshape(-1, 3),
             "options": dict(options)} for p, t, options in meshes]
    with tempfile.TemporaryDirectory(prefix="cad-coacd-") as tmp:
        job_path, result_path = Path(tmp) / "job.pickle", Path(tmp) / "result.pickle"
        job_path.write_bytes(pickle.dumps(jobs))
        returncode, said = _child([python, "-P", "-m", CHILD, str(job_path), str(result_path)],
                                  _child_env(Path(__file__).resolve().parents[2]) if own else _foreign_env(), done)
        if not result_path.is_file():
            raise Failed(f"CoACD stopped (exit {returncode}) before it wrote its hulls"
                         + ("".join(f"\n  {line}" for line in said) if said else ""))
        results = pickle.loads(result_path.read_bytes())
    found = []
    for at, result in enumerate(results):
        if "error" in result:
            raise Failed(result["error"], at)
        found.append([(np.asarray(p, dtype=np.float32).reshape(-1, 3), np.asarray(t, dtype=np.uint32).reshape(-1, 3))
                      for p, t in result["hulls"]])
    return found


def _child(argv: list[str], env: dict[str, str], done: Callable[[int, int, float], None]) -> tuple[int, list[str]]:
    """Run the decomposer child: its exit status and the last ``TAIL`` lines of its own output. Its output is
    read as it comes, each ``DONE`` line handed to ``done`` (a line that does not parse is its own output), so the
    parts are said as they are done; past ``TIMEOUT_S`` it is stopped and ``Failed`` says so."""
    try:
        process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    except OSError as error:
        raise Failed(f"cannot run {argv[0]}: {error.strerror or error}") from None
    tail: list[str] = []

    def read() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            words = line.split()
            if len(words) == 4 and words[0] == DONE:
                try:
                    done(int(words[1]), int(words[2]), float(words[3]))
                    continue
                except ValueError:
                    pass
            tail.append(line.rstrip("\n"))
            del tail[:-TAIL]

    reader = threading.Thread(target=read, name="cad-coacd-output", daemon=True)
    reader.start()
    try:
        process.wait(timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.wait()
        raise Failed(f"CoACD did not finish in {TIMEOUT_S:.0f} s and was stopped; fewer hulls (max_hulls) or a "
                     "coarser threshold decomposes sooner") from error
    finally:
        reader.join(timeout=10.0)  # its output ends with it
    return process.returncode, [line for line in tail if line.strip()]


def published(system: str | None = None, machine: str | None = None, glibc: bool | None = None) -> bool:
    """Whether CoACD publishes a wheel for this platform (``PLATFORMS``), or the one given."""
    import platform

    system = platform.system() if system is None else system
    machine = (platform.machine() if machine is None else machine).lower()
    if system == "Darwin":
        return machine == "arm64"
    if system == "Windows":
        return machine in ("amd64", "x86_64")
    if system == "Linux":
        return machine in ("x86_64", "aarch64", "arm64") and (_glibc() if glibc is None else glibc)
    return False


def _glibc() -> bool:
    """Whether this Python runs on glibc (a manylinux wheel's), not musl."""
    import platform

    try:
        if os.confstr("CS_GNU_LIBC_VERSION"):
            return True
    except (AttributeError, OSError, ValueError):
        pass
    return platform.libc_ver()[0] == "glibc"


def _python() -> tuple[str, bool]:
    """The Python the child runs (the module's **Where coacd is**), and whether it is this one."""
    import importlib.util
    import platform

    if importlib.util.find_spec("coacd") is not None:
        return sys.executable, True
    if not published():
        raise Unavailable(f"coacd comes with cad's coacd integration, {EXTRA}, which installs it only where CoACD "
                          f"publishes wheels, {PLATFORMS}, and this is {platform.system()} {platform.machine()}")
    python = (PROVIDE or _engine)(_told)
    if python is None:
        raise Unavailable(f"coacd comes with cad's coacd integration, {EXTRA}, which this environment does not hold, "
                          "and no engine answered to make its environment: export through the cad command, which "
                          f"makes it on first need, or install {EXTRA} here")
    return python, False


def _told(line: str) -> None:
    print(f"cad: {line}", file=sys.stderr, flush=True)


def _engine(told: Callable[[str], None]) -> str | None:
    """The Python of the coacd integration's environment, made by the device's engine where it is not (``{"op":
    "integration"}``), its lines said to ``told``; None where no engine answers, or one that has no such request
    (another release's). ``Unavailable`` in the engine's words where it cannot be made."""
    from cad.engine import client

    try:
        answer = client.request({"op": "integration", "integration": "coacd"}, start=False,
                                on_log=lambda frame: told(str(frame.get("log", ""))))
    except (ConnectionError, OSError, ValueError):
        return None
    if not answer or str(answer.get("failed") or "").startswith("unknown request"):
        return None
    if answer.get("failed"):
        raise Unavailable(f"the engine could not make {EXTRA}'s environment: {answer['failed']}")
    python = answer.get("python")
    return python if isinstance(python, str) and python else None


def _foreign_env() -> dict[str, str]:
    """The child's environment where it runs another environment's Python: this one, without the import path
    this process was handed, so that Python imports its own cad and numpy."""
    return {name: value for name, value in os.environ.items() if name not in ("PYTHONPATH", "PYTHONHOME")}


def _child_env(source: Path) -> dict[str, str]:
    """The child's environment: this one, with the folder this cad was imported from first on its
    PYTHONPATH where the interpreter would not find it by itself (a source checkout, a test's path). Never
    a site-packages folder: on PYTHONPATH it would come before the standard library."""
    import site

    sites = {Path(p).resolve() for p in [*site.getsitepackages(), site.getusersitepackages()]}
    if source in sites:
        return dict(os.environ)
    return {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(source), os.environ.get("PYTHONPATH")]))}
