"""Galatea as the CAD viewer draws it, as frames for the film: no studio, no lens, the viewer's own display modes.

    cad run src/views.py            120 frames, 1600 x 900, into tmp/film/views/ (five seconds at 24 a second)
    cad run src/views.py 12         every 12th frame: a quick look

Three passes, the camera going round the robot through the first two:

    solid     the model on the measuring grid;
    parts     every part its own colour, and the viewer's Explode drawn out;
    x-ray     one gait cycle of the `walk` motion, the mechanism showing through the skins. The pelvis is the
              mechanism's fixed link, so the feet tread under it, as they do when the viewer plays the motion.

Every frame is one `cad model snapshot` job: the engine draws it with the renderer and the display modes of the
viewer's page, from the document it holds. `film.py`'s cut takes the frames as they are.
"""

import json
import math
import subprocess
import sys
from pathlib import Path

import build123d  # noqa: F401  (the model needs cad's build123d integration)

from galatea import galatea
from lib.poses import CYCLE, walk

OUT = Path(__file__).resolve().parents[1] / "tmp" / "film" / "views"
SIZE = (1600, 900)
FPS = 24
LENS = {"projection": "perspective", "focalLength": 50}
TARGET = (0.0, 20.0, 880.0)


def camera(azimuth, elevation, distance):
    """A camera `distance` from the robot's middle, `azimuth` round from its front toward its left."""
    a, e = math.radians(azimuth), math.radians(elevation)
    eye = [TARGET[0] + distance * math.sin(a) * math.cos(e), TARGET[1] - distance * math.cos(a) * math.cos(e),
           TARGET[2] + distance * math.sin(e)]
    return {"position": eye, "target": list(TARGET), "up": [0, 0, 1]}


def eased(u):
    return u * u * (3.0 - 2.0 * u)


def frame(k):
    """The job of frame k: (camera, display, pose)."""
    if k < 36:                                              # solid, on the grid: across the front
        return camera(-25 + 50 * k / 36, 12, 4900), {"mode": "solid", "grid": True}, None
    if k < 72:                                              # parts, coming apart: on round to a three-quarter view
        u = (k - 36) / 36
        apart = 0.3 * eased(min(1.0, u / 0.6))
        return camera(25 + 40 * u, 12, 4900 + 2600 * apart / 0.3), {"mode": "parts", "exploded": {"enabled": True, "amount": apart}}, None
    t = (k - 72) / FPS                                      # x-ray, walking: on to its side
    return camera(65 + 45 * (k - 72) / 48, 8, 4900), {"mode": "xray"}, walk(t % CYCLE)


def main(arguments):
    step = int(arguments[0]) if arguments else 1
    OUT.mkdir(parents=True, exist_ok=True)
    document = galatea().id
    jobs = []
    for k in range(0, 120, step):
        view, display, pose = frame(k)
        job = {"input": document, "camera": view, "display": {**display, "camera": LENS}, "output": {"padding": 0.0},
               "outputs": [{"path": str(OUT / f"{k:04d}.png"), "width": SIZE[0], "height": SIZE[1]}]}
        if pose:
            job["jointValues"] = pose
        jobs.append(job)
    for first in range(0, len(jobs), 12):                   # a dozen at a time: a packet's pictures are drawn in one go
        packet = OUT / ".jobs.json"
        packet.write_text(json.dumps(jobs[first:first + 12]))
        done = subprocess.run(["cad", "model", "snapshot", "--job", str(packet), "--json"], capture_output=True, text=True)
        if done.returncode:
            raise SystemExit(f"snapshot failed: {done.stdout.strip()[-400:] or done.stderr.strip()[-400:]}")
        print(f"frames {first * step} to {min(len(jobs), first + 12) * step - 1}", flush=True)
        packet.unlink()
    print(f"wrote {len(jobs)} frames into {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
