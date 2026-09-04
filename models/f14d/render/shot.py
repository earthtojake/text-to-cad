#!/usr/bin/env python3
"""Write and run a JSON render job for the F-14D.

Always JSON jobs, never shortcut flags -- the shortcut flags cannot express the
theme file plus display mode plus size profile combination the critic
comparisons need, and they silently ignore unknown keys.

    python render/shot.py STEP/f14d.step <stem> --views fq,top,side,head --size assembly-large

The target is a BUILT DOCUMENT (`STEP/f14d.step`), not a model script -- the
snapshot door refuses a `.py`.  Build first: `python src/f14d.py`.

Views are named for the four gauntlet angles plus a few build-time helpers.
Camera directions are given as explicit vectors so a view means the same thing
every time, whatever the model's bounding box does.

Output lands in `tmp/` (gitignored scratch), never beside the code.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
PY = sys.executable
THEME = HERE / "presentation_theme.json"
DISPLAY = HERE / "presentation_display.json"

# +X aft, +Y port, +Z up.  A camera "direction" points FROM the model TOWARD
# the camera.
# Framing is by BOUNDING SPHERE, and `render.padding` is clamped to a 0.1
# minimum, so a long thin fuselage is framed by its diagonal and ends up small
# in frame however tight the padding.  Per-view `zoom` is the only lever that
# actually crops in; the values below fill the frame for a 19.5 m span aircraft.
#
# STALE, MEASURED 2026-08-31, LEFT AS IS.  These values no longer fill the
# frame: at `side`/1.45 the aircraft covers about half the image width, and a
# re-probe put the fill point near 2.70 (3.0 clips nose and tail).  The drift is
# in the snapshot engine's bounding-sphere fit, not in the model.  Do NOT
# "correct" this by scaling the table uniformly -- that was tried and it
# overshoots: at the side-derived 1.86x factor `top` (which runs the 19.2 m
# length down the SHORT axis of a 4:3 frame) clips nose and tail.  Every view
# has to be re-probed against the built jet on its own, one snapshot each.
VIEWS = {
    # --- the four whole-aircraft gauntlet views -------------------------
    "top":   {"direction": [0, 0, 1], "up": [-1, 0, 0], "zoom": 1.30},
    "head":  {"direction": [-1, 0, 0.07], "up": [0, 0, 1], "zoom": 1.55},
    "side":  {"direction": [0, -1, 0], "up": [0, 0, 1], "zoom": 1.45},
    "fq":    {"direction": [-1, -0.62, 0.20], "up": [0, 0, 1], "zoom": 1.35},
    # --- build helpers --------------------------------------------------
    "rq":    {"direction": [0.95, -0.60, 0.30], "up": [0, 0, 1], "zoom": 1.35},
    "belly": {"direction": [0, 0, -1], "up": [1, 0, 0], "zoom": 1.30},
    "tail":  {"direction": [1, 0, 0.10], "up": [0, 0, 1], "zoom": 1.55},
    "hi34":  {"direction": [-0.85, -0.55, 0.62], "up": [0, 0, 1], "zoom": 1.30},
    "topfwd": {"direction": [-0.35, 0, 0.94], "up": [-1, 0, 0], "zoom": 1.30},
}

# Framing a TEARDOWN is not the same problem as framing the built jet, and the
# CLI cannot drive one -- the staged separation lives in `STEP/f14d.step.js` and
# plays in the CAD Viewer's Animation tab (clips: `teardown`, `explodedHold`).
# Kept here because the camera knowledge outlived the retired render/explode.py
# that carried it: the separation is mostly on Z (skin up, gear and inlets
# down) with the nozzles drawing aft, so a camera well above the waterline and
# off the bow sees the vertical stack without the wings hiding what drops out
# from under them, while a level side view collapses the explode into one line.
# The teardown roughly doubles the bounding sphere (skin +5.2 m up, gear -2.3 m
# down, nozzles +4.4 m aft), and framing is by bounding sphere, so the built-jet
# zooms above throw the skin out of frame before it stops travelling. Use
# hi34 / fq / side pulled WIDER: the retired script's teardown zooms sat at
# roughly 0.8x of what filled the frame with the assembled aircraft under the
# same padding.  That is a RATIO, not a value -- see the staleness note above.


def build_job(target, outdir, stem, views, size, mode, focus=None, hide=None,
              theme=None, stamp=True):
    outs = []
    for v in views:
        cam = VIEWS.get(v)
        if cam is None:
            raise SystemExit(f"unknown view {v!r}; known: {', '.join(VIEWS)}")
        outs.append({"path": str(Path(outdir) / f"{stem}_{v}.png"), "camera": dict(cam)})
    # Edge styling lives in DISPLAY, not in the theme.  Passing an "edges" key
    # inside a theme JSON is rejected outright -- and the repo's own example
    # presentation theme (models/hypercar/render/presentation_theme.json)
    # still carries one, so copying it as a starting point fails.
    display = json.loads(DISPLAY.read_text())
    display.pop("_comment", None)
    display["mode"] = mode
    job = {
        "input": str(target),
        "mode": "view",
        "outputs": outs,
        "theme": str(theme or THEME),
        "display": display,
        "render": {"sizeProfile": size, "padding": 0.06, "viewLabels": False},
    }
    if focus or hide:
        selection = {}
        if focus:
            selection["focus"] = focus
        if hide:
            selection["hide"] = hide
        job["selection"] = selection
    return job


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("stem")
    ap.add_argument("--views", default="fq,top,side,head")
    ap.add_argument("--size", default="assembly-large")
    ap.add_argument("--mode", default="solid")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--focus", default=None)
    ap.add_argument("--hide", default=None)
    ap.add_argument("--theme", default=None)
    args = ap.parse_args()

    outdir = Path(args.outdir) if args.outdir else (PROJECT / "tmp")
    outdir.mkdir(parents=True, exist_ok=True)
    job = build_job(args.target, outdir, args.stem, args.views.split(","),
                    args.size, args.mode,
                    focus=args.focus.split(",") if args.focus else None,
                    hide=args.hide.split(",") if args.hide else None,
                    theme=args.theme)
    jobfile = outdir / f"{args.stem}_job.json"
    jobfile.write_text(json.dumps(job, indent=2))
    r = subprocess.run([PY, "-m", "cadgen.cli", "step", "snapshot",
                        "--job", str(jobfile)],
                       cwd=str(PROJECT), capture_output=True, text=True)
    sys.stderr.write(r.stderr)
    print(r.stdout.strip())
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
