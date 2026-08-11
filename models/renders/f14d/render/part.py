#!/usr/bin/env python3
"""Build and render ONE part module, in the context of the airframe.

    python render/part.py nozzles --views rq,tail,side
    python render/part.py nozzles --solo            # the part on its own
    python render/part.py wings,empennage --views top

Writes a throwaway entry under `.review/<name>/` that composes only the modules
asked for, so a builder can iterate without waiting for the whole aeroplane and
without their artifact cache colliding with anyone else's.  The airframe skin is
included by default because a part judged out of context is judged wrong -- a
perfect nozzle at the wrong scale relative to the nacelle still fails.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parents[2]
PY = "/Users/jakefitzgerald/robots/text-to-cad/.venv/bin/python"

TEMPLATE = '''"""Auto-generated review entry -- do not edit; see render/part.py."""
import sys
from pathlib import Path

sys.path.insert(0, {project!r})

from build123d import Compound

MODULES = {mods!r}


def _load(name):
    try:
        return __import__("f14_parts." + name, fromlist=["build"])
    except Exception as exc:  # noqa: BLE001
        print("[review] skip %s: %s" % (name, exc), file=sys.stderr)
        return None


_LOADED = [(n, _load(n)) for n in MODULES]


def gen_step():
    kids = []
    for name, mod in _LOADED:
        if mod is None:
            continue
        try:
            kids.append(mod.build())
        except Exception as exc:  # noqa: BLE001
            print("[review] build failed %s: %s" % (name, exc), file=sys.stderr)
    if not kids:
        raise RuntimeError("nothing built")
    return Compound(children=kids, label="review")
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mods", help="comma-separated part module names")
    ap.add_argument("--views", default="fq,top,side,rq")
    ap.add_argument("--size", default="assembly-large")
    ap.add_argument("--mode", default="solid")
    ap.add_argument("--solo", action="store_true",
                    help="omit the airframe skin context")
    ap.add_argument("--stem", default=None)
    args = ap.parse_args()

    mods = [m.strip() for m in args.mods.split(",") if m.strip()]
    name = "_".join(mods)
    full = mods if args.solo else (["airframe"] + [m for m in mods if m != "airframe"])

    d = PROJECT / ".review" / name
    d.mkdir(parents=True, exist_ok=True)
    entry = d / f"{name}.step.py"
    entry.write_text(TEMPLATE.format(project=str(PROJECT), mods=full))

    r = subprocess.run([PY, str(REPO / "skills/cad/scripts/gen"), str(entry)],
                       cwd=str(REPO), capture_output=True, text=True)
    sys.stderr.write(r.stderr)
    if r.returncode != 0:
        print(r.stdout)
        return r.returncode

    stem = args.stem or name
    return subprocess.run(
        [PY, str(HERE / "shot.py"), str(entry), stem,
         "--views", args.views, "--size", args.size, "--mode", args.mode,
         "--outdir", str(d)], cwd=str(REPO)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
