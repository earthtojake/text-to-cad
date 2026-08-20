#!/usr/bin/env python3
"""Render the F-14D exploded-view teardown from `f14d.params.js`.

Companion to shot.py, which renders the built aircraft.  This one drives the
sidecar's ``exploded`` parameter instead:

    python render/explode.py f14d.step.py teardown              # animated GIF
    python render/explode.py f14d.step.py stills --at 0,0.5,1   # still frames

A STEP model has no declared `animate` render mode -- that is for implicit
models.  It is swept by giving the job an ANIMATED PARAMETER VALUE
(``stepParameters.animate``) while staying in ``view`` mode, and the output
extension is what selects GIF over PNG.

Theme and display come from the same two JSON files shot.py uses, so an
exploded frame and a gauntlet frame are lit and edged identically and can sit
next to each other in a review packet.
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
PY = str(REPO / ".venv" / "bin" / "python")
SNAPSHOT = REPO / "skills" / "cad" / "scripts" / "snapshot"
THEME = HERE / "presentation_theme.json"
DISPLAY = HERE / "presentation_display.json"

# A three-quarter view from high and forward.  The teardown separates mostly on
# Z (skin up, gear and inlets down) with the nozzles drawing aft, so a camera
# that is well above the waterline and off the bow sees the vertical stack
# without the wings hiding what drops out from under them -- a level side view
# collapses the whole explode into one line.
#
# Zoom is TIGHTER than 1 crops in, and the values are lower than the ~3.2 that
# fills the frame with the assembled aircraft: the teardown roughly doubles the
# bounding sphere (skin +5.2 m up, gear -2.3 m down, nozzles +4.4 m aft), and
# framing is by bounding sphere, so a zoom that suits the built jet throws the
# skin out of frame before it stops travelling. These fill the frame at
# exploded = 1 and simply leave air around the aircraft at exploded = 0.
VIEWS = {
    "hi34": {"direction": [-0.85, -0.55, 0.62], "up": [0, 0, 1], "zoom": 2.5},
    "fq": {"direction": [-1, -0.62, 0.20], "up": [0, 0, 1], "zoom": 2.5},
    "side": {"direction": [0, -1, 0], "up": [0, 0, 1], "zoom": 2.6},
}


def _display(mode="solid"):
    display = json.loads(DISPLAY.read_text())
    display.pop("_comment", None)
    display["mode"] = mode
    return display


def _base(target, view, size):
    cam = VIEWS.get(view)
    if cam is None:
        raise SystemExit(f"unknown view {view!r}; known: {', '.join(VIEWS)}")
    return {
        "input": str(target),
        "mode": "view",
        "theme": str(THEME),
        "display": _display(),
        "render": {"sizeProfile": size, "padding": 0.06, "viewLabels": False},
    }, cam


def job_gif(target, outdir, stem, view, size, seconds, fps):
    job, cam = _base(target, view, size)
    job["outputs"] = [{"path": str(Path(outdir) / f"{stem}.gif"), "camera": dict(cam)}]
    # The sidecar's own `teardown` animation is an out-and-back sine, but a
    # parameter SWEEP is linear from -> to, so the GIF is authored here as a
    # straight 0 -> 1 separation and left to loop.  Sweeping 0 -> 1 -> 0 would
    # need the sweep to accept a keyframe list, which it does not.
    # fps / durationSeconds are read off the PARAMETER VALUES object, beside
    # `animate` -- not off `render`, where they are silently ignored and you get
    # the default 18 fps x 4 s = 72 frames whatever you asked for.
    job["stepParameters"] = {
        "animate": {"exploded": {"from": 0.0, "to": 1.0}},
        "durationSeconds": seconds,
        "fps": fps,
    }
    return job


def job_stills(target, outdir, stem, view, size, values):
    """One JOB per explode value, not one output per value.

    ``stepParameters`` is a job-level key -- the renderer rejects it inside an
    output, which only takes camera/size/label keys.  So a multi-pose packet is
    a ``{"jobs": [...]}`` array, each entry carrying its own parameter values
    and its own single output.  The artifact is built once and reused across
    them; it is the pose that differs, not the model.
    """
    jobs = []
    for value in values:
        job, cam = _base(target, view, size)
        tag = f"{value:.2f}".replace(".", "")
        job["outputs"] = [{
            "path": str(Path(outdir) / f"{stem}_e{tag}.png"),
            "camera": dict(cam),
        }]
        job["stepParameters"] = {"exploded": value}
        jobs.append(job)
    return {"jobs": jobs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("stem")
    ap.add_argument("--view", default="hi34")
    ap.add_argument("--size", default="assembly-large")
    ap.add_argument("--at", default=None,
                    help="comma-separated exploded values -> stills instead of a GIF")
    ap.add_argument("--seconds", type=float, default=9.0)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    outdir = Path(args.outdir) if args.outdir else (PROJECT / "render" / "out")
    outdir.mkdir(parents=True, exist_ok=True)

    if args.at:
        values = [float(v) for v in args.at.split(",")]
        job = job_stills(args.target, outdir, args.stem, args.view, args.size, values)
    else:
        job = job_gif(args.target, outdir, args.stem, args.view, args.size,
                      args.seconds, args.fps)

    jobfile = outdir / f"{args.stem}_explode_job.json"
    jobfile.write_text(json.dumps(job, indent=2))
    result = subprocess.run([PY, str(SNAPSHOT), "--job", str(jobfile)],
                            cwd=str(REPO), capture_output=True, text=True)
    sys.stderr.write(result.stderr)
    print(result.stdout.strip())
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
