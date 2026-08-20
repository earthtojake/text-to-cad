"""Bridge to cadgen for the heavy STEP build/export ops.

OCP/OpenCascade is kept OUT of the long-lived server process (crash/memory
isolation, same as the Node backend). Two execution paths share one contract,
``run_cadgen(module, args, repo_root) -> dict``:

* warm worker (default): a persistent :mod:`server_py.worker` subprocess imports
  OCP once and services every build/export in-process — no per-request cold start.
* cold subprocess (fallback): a fresh ``python -m <module>`` per request, used when
  the worker is disabled (``VIEWER_CAD_WORKER=0``) or a worker transport fault
  occurs. Always available, fully isolated.

Both call the SAME general cadgen callables; only warmth/lifetime differ.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

_PYTHONPATH_REL_CANDIDATES = [
    os.path.join("scripts", "packages", "cadgen", "src"),
    os.path.join("viewer", "packages", "cadgen", "src"),
    os.path.join("packages", "cadgen", "src"),
]
_CAD_BACKEND_PROBE = (
    "import OCP\n"
    "import build123d\n"
    "import cadgen.step_artifact_cli\n"
)
_CAD_BACKEND_PROBE_TIMEOUT_SECONDS = 30


def _find_up_dir(rel: str, start: str) -> str:
    cur = os.path.abspath(start or ".")
    while True:
        candidate = os.path.join(cur, rel)
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(cur)
        if parent == cur:
            return ""
        cur = parent


def cadgen_pythonpath(repo_root: str) -> str:
    entries = []
    for env_name in ("VIEWER_CAD_PYTHONPATH", "CAD_PYTHONPATH", "VIEWER_CADPY_PYTHONPATH"):
        value = str(os.environ.get(env_name) or "").strip()
        if value:
            entries.append(value)
    for rel in _PYTHONPATH_REL_CANDIDATES:
        found = _find_up_dir(rel, repo_root) or _find_up_dir(rel, os.getcwd())
        if found:
            entries.append(found)
    existing = str(os.environ.get("PYTHONPATH") or "").strip()
    if existing:
        entries.append(existing)
    deduped = []
    seen = set()
    for entry in entries:
        if entry not in seen:
            seen.add(entry)
            deduped.append(entry)
    return os.pathsep.join(deduped)


def probe_cadgen_runtime(repo_root: str) -> dict:
    """Validate the current interpreter in an isolated child process.

    The long-lived HTTP server intentionally does not import OpenCascade. This
    probe exercises the exact interpreter and PYTHONPATH that artifact workers
    inherit, while keeping OCP out of the server process itself.
    """
    env = dict(os.environ)
    pythonpath = cadgen_pythonpath(repo_root)
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CAD_BACKEND_PROBE],
            cwd=repo_root if repo_root and os.path.isdir(repo_root) else None,
            env=env,
            capture_output=True,
            text=True,
            timeout=_CAD_BACKEND_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "python": sys.executable,
            "error": f"CAD backend validation timed out after {_CAD_BACKEND_PROBE_TIMEOUT_SECONDS}s.",
        }
    except OSError as exc:
        return {"ok": False, "python": sys.executable, "error": str(exc)}
    if proc.returncode == 0:
        return {"ok": True, "python": sys.executable, "error": ""}
    detail = (proc.stderr or proc.stdout or f"probe exited with code {proc.returncode}").strip()
    if len(detail) > 4000:
        detail = detail[-4000:]
    return {"ok": False, "python": sys.executable, "error": detail}


def require_cadgen_runtime(repo_root: str) -> dict:
    result = probe_cadgen_runtime(repo_root)
    if result.get("ok"):
        return result
    python = result.get("python") or sys.executable
    detail = result.get("error") or "Unknown CAD backend validation error."
    raise RuntimeError(
        "CAD Viewer requires a working CAD Python backend before startup.\n"
        f"Selected interpreter: {python}\n"
        "Required imports: OCP, build123d, cadgen.step_artifact_cli\n"
        f"{detail}\n"
        "Set VIEWER_CAD_PYTHON to an absolute Python path with the viewer CAD requirements installed."
    )


def run_cadgen(module: str, args, repo_root: str) -> dict:
    """Run a cadgen build/export op and return its payload dict (``{ok:false,error}``
    on failure). Prefers the warm worker; falls back to a cold subprocess on any
    worker spawn/transport fault so the path is always available."""
    try:
        from . import worker_client

        return worker_client.run_cadgen(module, args, repo_root)
    except worker_client._WorkerError:
        pass  # worker disabled or faulted -> cold subprocess below
    return run_cadgen_cold(module, args, repo_root)


def run_cadgen_cold(module: str, args, repo_root: str) -> dict:
    """Run `python -m <module> <args>` in a fresh subprocess and return the last
    stdout JSON line as a dict, or {ok:false,error} on failure."""
    env = dict(os.environ)
    pythonpath = cadgen_pythonpath(repo_root)
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    # Byte-deterministic artifacts (drawing packages are content-addressed):
    # ezdxf's object ordering depends on Python hash randomization.
    env.setdefault("PYTHONHASHSEED", "0")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", module, *args],
            cwd=repo_root, env=env, capture_output=True, text=True,
        )
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    for line in reversed(proc.stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except ValueError:
                break
    message = (proc.stderr or proc.stdout or f"cadgen {module} exited with code {proc.returncode}").strip()
    return {"ok": False, "exitCode": proc.returncode, "error": message}
