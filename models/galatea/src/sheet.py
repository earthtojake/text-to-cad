# /// script
# dependencies = ["pillow"]
# ///
"""Galatea from five sides in one picture: the sheet a look is judged on.

    cad run src/sheet.py                      the whole robot, into tmp/sheets/body.png
    cad run src/sheet.py waist 1040 1300      a region, by the heights it lies between
    cad run src/sheet.py bow 800 1600 '{"waist_pitch": 34}'      the same at a pose

The views go round the model: front, front quarter, side, back quarter, back. A restyle
judged only from in front passed every check here with bare drives still showing behind
the waist and the hips; the back and the side are on the sheet so that cannot happen
again. `review.py` is the same idea link by link, with the skins left off.
"""

import json
import math
import subprocess
import sys
from pathlib import Path

import build123d  # noqa: F401  (the model needs cad's build123d integration)
from PIL import Image

from galatea import galatea

OUT = Path(__file__).resolve().parents[1] / "tmp" / "sheets"
VIEWS = ((0, 4), (38, 8), (90, 2), (142, 8), (180, 4))      # azimuth from the front, elevation
PAPER = (233, 234, 236)                                     # pearl and black both read on it
LENS = {"projection": "perspective", "focalLength": 85}
AXIS_Y = 30.0                                               # the trunk's middle, behind the hips' line


def camera(azimuth, elevation, span):
    """A preset for the whole robot; for a region, a camera that stays one distance from its middle."""
    if span is None:
        return {"preset": f"{azimuth}:{elevation}"}, (560, 1040)
    low, high = span
    a, e, middle, away = math.radians(azimuth), math.radians(elevation), (low + high) / 2, (high - low) * 4.2
    eye = [away * math.sin(a) * math.cos(e), AXIS_Y - away * math.cos(a) * math.cos(e), middle + away * math.sin(e)]
    return {"position": eye, "target": [0, AXIS_Y, middle], "up": [0, 0, 1]}, (760, 760)


def main(arguments):
    name = arguments[0] if arguments else "body"
    span = (float(arguments[1]), float(arguments[2])) if len(arguments) > 2 else None
    pose = json.loads(arguments[3]) if len(arguments) > 3 else None
    OUT.mkdir(parents=True, exist_ok=True)
    document = galatea().id
    tiles = []
    for k, (azimuth, elevation) in enumerate(VIEWS):
        view, size = camera(azimuth, elevation, span)
        path = OUT / f".{name}_{k}.png"
        job = {"input": document, "camera": view, "display": {"mode": "shaded", "camera": LENS},
               "output": {"transparent": True, "padding": 0.04}, "outputs": [{"path": str(path), "width": size[0], "height": size[1]}]}
        if pose:
            job["jointValues"] = pose
        done = subprocess.run(["cad", "model", "snapshot", "--job", json.dumps(job), "--json"], capture_output=True, text=True)
        if done.returncode:
            raise SystemExit(f"snapshot failed for {name}: {done.stdout.strip() or done.stderr.strip()}")
        shot = Image.open(path).convert("RGBA")
        tile = Image.new("RGBA", shot.size, (*PAPER, 255))
        tile.alpha_composite(shot)
        tiles.append(tile.convert("RGB"))
        path.unlink()
    sheet = Image.new("RGB", (sum(tile.width for tile in tiles), tiles[0].height), PAPER)
    x = 0
    for tile in tiles:
        sheet.paste(tile, (x, 0))
        x += tile.width
    sheet.save(OUT / f"{name}.png")
    print(f"wrote {OUT / f'{name}.png'}")


if __name__ == "__main__":
    main(sys.argv[1:])
