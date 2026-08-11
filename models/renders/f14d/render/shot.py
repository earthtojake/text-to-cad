#!/usr/bin/env python3
"""Write and run a JSON render job for the F-14D.

Always JSON jobs, never shortcut flags -- the shortcut flags cannot express the
theme file plus display mode plus size profile combination the critic
comparisons need, and they silently ignore unknown keys.

    python render/shot.py <target> <stem> --views fq,top,side,head --size assembly-large

Views are named for the four gauntlet angles plus a few build-time helpers.
Camera directions are given as explicit vectors so a view means the same thing
every time, whatever the model's bounding box does.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parents[2]
PY = "/Users/jakefitzgerald/robots/text-to-cad/.venv/bin/python"
SNAPSHOT = REPO / "skills" / "cad" / "scripts" / "snapshot"
THEME = HERE / "presentation_theme.json"
DISPLAY = HERE / "presentation_display.json"

# +X aft, +Y port, +Z up.  A camera "direction" points FROM the model TOWARD
# the camera.
# Framing is by BOUNDING SPHERE, and `render.padding` is clamped to a 0.1
# minimum, so a long thin fuselage is framed by its diagonal and ends up small
# in frame however tight the padding.  Per-view `zoom` is the only lever that
# actually crops in; the values below fill the frame for a 19.5 m span aircraft.
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
    # presentation theme (models/renders/hypercar/render/presentation_theme.json)
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
    if focus:
        job["focus"] = focus
    if hide:
        job["hide"] = hide
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

    outdir = Path(args.outdir) if args.outdir else (PROJECT / "render" / "out")
    outdir.mkdir(parents=True, exist_ok=True)
    job = build_job(args.target, outdir, args.stem, args.views.split(","),
                    args.size, args.mode,
                    focus=args.focus.split(",") if args.focus else None,
                    hide=args.hide.split(",") if args.hide else None,
                    theme=args.theme)
    jobfile = outdir / f"{args.stem}_job.json"
    jobfile.write_text(json.dumps(job, indent=2))
    r = subprocess.run([PY, str(SNAPSHOT), "--job", str(jobfile)],
                       cwd=str(REPO), capture_output=True, text=True)
    sys.stderr.write(r.stderr)
    print(r.stdout.strip())
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
