#!/usr/bin/env python3
"""Serialised engine builds and renders (many builders share one assembly).

  tools/engine.py build            rebuild STEP/radial.step (forces when the set of ready systems changed)
  tools/engine.py system NAME      build one system model (its own lock only: systems build in parallel)
  tools/engine.py render JOB.json  snapshot job(s) against STEP/radial.step, under the same lock
  tools/engine.py build-render JOB.json   both, holding the lock throughout

build / build-render first bring every ready system current OUTSIDE the shared lock, one at
a time (a current system returns in ~1 s; a per-system lock stops two builders rebuilding
the same one), and stop at the first system that fails, naming it. The shared lock is then
held only for the assembly (~1-2 min) and the render, not for a 25 min heads rebuild.

Run from anywhere; paths in JOB files are relative to models/radial.
The lock is tmp/engine.lock (fcntl). Waits are printed so a builder knows why it paused.
"""

from __future__ import annotations

import fcntl
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable                                  # run with the project interpreter
CADGEN = shutil.which("cadgen") or str(Path(sys.executable).with_name("cadgen"))
LOCK = ROOT / "tmp" / "engine.lock"
READY_STAMP = ROOT / "tmp" / "ready_systems.json"


class Lock:
    def __enter__(self):
        LOCK.parent.mkdir(exist_ok=True)
        self.f = open(LOCK, "w")
        t0 = time.time()
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[engine] waiting for another builder's assembly build/render ...", flush=True)
            fcntl.flock(self.f, fcntl.LOCK_EX)
            print(f"[engine] lock acquired after {time.time() - t0:.0f}s", flush=True)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def _run(cmd):
    print("[engine] $", " ".join(cmd), flush=True)
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT)
    print(f"[engine] exit {r.returncode} in {time.time() - t0:.0f}s", flush=True)
    return r.returncode


def _ready():
    sys.path.insert(0, str(ROOT / "src"))
    from lib.systems import ready
    return ready()


def build_system(name, extra=()):
    """One system build under its own lock (never two builds of one system at once)."""
    locks = ROOT / "tmp" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    with open(locks / f"{name}.lock", "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"[engine] waiting for another builder's {name} build ...", flush=True)
            fcntl.flock(f, fcntl.LOCK_EX)
        return _run([PY, f"src/{name}.py", *extra])


def prebuild():
    """Bring every ready system current before the assembly takes the shared lock."""
    for name in _ready():
        rc = build_system(name)
        if rc:
            print(f"[engine] system {name} FAILED to build: fix src/lib/{name}.py (or wait for "
                  f"its builder) before the assembly can build", flush=True)
            return rc
    return 0


def build():
    sys.path.insert(0, str(ROOT / "src"))
    from lib.systems import ready
    now = ready()
    before = json.loads(READY_STAMP.read_text()) if READY_STAMP.exists() else None
    cmd = [PY, "src/radial.py"] + (["--force"] if now != before else [])
    rc = _run(cmd)
    if rc == 0:
        READY_STAMP.write_text(json.dumps(now))
    return rc


def render(job):
    """A job whose "render" is the string "presentation" gets render/presentation.json
    (the presentation theme) substituted, so every critic render uses one envelope."""
    path = Path(job).resolve()
    data = json.loads(path.read_text())
    envelope = json.loads((ROOT / "render" / "presentation.json").read_text())
    jobs = data["jobs"] if isinstance(data, dict) and "jobs" in data else (data if isinstance(data, list) else [data])
    for j in jobs:
        if j.get("render") == "presentation":
            j["render"] = envelope
        j.setdefault("input", "STEP/radial.step")
    resolved = ROOT / "tmp" / "jobs" / path.name
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps({"jobs": jobs}, indent=1))
    return _run([CADGEN, "step", "snapshot", "--job", str(resolved)])


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "system":
        return build_system(argv[1], argv[2:])
    if cmd in ("build", "build-render"):
        rc = prebuild()
        if rc:
            return rc
    with Lock():
        if cmd == "build":
            return build()
        if cmd == "render":
            return render(argv[1])
        if cmd == "build-render":
            rc = build()
            return rc if rc else render(argv[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
