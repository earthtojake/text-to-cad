#!/usr/bin/env python3
"""Build and render ONE part module, in the context of the airframe.

    python render/part.py nozzles --views rq,tail,side
    python render/part.py nozzles --solo            # the part on its own
    python render/part.py wings,empennage --views top

Writes a throwaway `@step` model under `tmp/review/<name>/` that composes only
the system MODELS asked for (`src/<name>.py`), so a builder can iterate without
waiting for the whole aeroplane: a current system loads from the store, only
the one being worked on rebuilds.  The
airframe skin is included by default because a part judged out of context is
judged wrong -- a perfect nozzle at the wrong scale relative to the nacelle
still fails.

The generated entry lives OUTSIDE `src/` on purpose: every `.py` directly under
`src/` is a real model of this project, and a scratch composition is not one.
That is also why it carries the one `sys.path.insert` in the project -- it has
to reach `src/` from `tmp/`, which the real models never have to do.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
SRC = PROJECT / "src"
PY = sys.executable

TEMPLATE = '''"""Auto-generated review entry -- do not edit; see render/part.py."""
import sys

sys.path.insert(0, {src!r})

from cadgen import build123d as bd, step

{imports}


@step(out="{name}.step", kind="assembly")
def {name}():
    # Each system is a sibling model of the project: current ones load from
    # the store, stale ones build -- a review composition costs only what
    # actually changed.
    return bd.Compound(children=[{calls}], label="review")


if __name__ == "__main__":
    {name}()
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

    d = PROJECT / "tmp" / "review" / name
    d.mkdir(parents=True, exist_ok=True)
    entry = d / f"{name}.py"
    imports = "\n".join(f"from {m} import {m}" for m in full)
    calls = ", ".join(f"{m}()" for m in full)
    entry.write_text(TEMPLATE.format(src=str(SRC), imports=imports, calls=calls, name=name))

    r = subprocess.run([PY, str(entry)],  # its __main__ builds the model
                       cwd=str(d), capture_output=True, text=True)
    sys.stderr.write(r.stderr)
    if r.returncode != 0:
        print(r.stdout)
        return r.returncode

    stem = args.stem or name
    # shot.py takes the BUILT DOCUMENT, never the script.
    return subprocess.run(
        [PY, str(HERE / "shot.py"), str(d / f"{name}.step"), stem,
         "--views", args.views, "--size", args.size, "--mode", args.mode,
         "--outdir", str(d)], cwd=str(PROJECT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
