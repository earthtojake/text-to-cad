# /// script
# dependencies = ["pillow"]
# ///
"""Galatea, link by link: `cad run src/review.py [group ...]` writes a sheet for each into tmp/review/.

A sheet shows one group of links alone (the parts that move together, or a joint's two
sides) from the front, the left, the back and the right, and again under it with the
skins left off. It is the picture to look at before the whole robot is: a plate that
comes through a skin, or a casing whose edge runs across what it covers, is plain on a
sheet and a few pixels on a beauty still. The left side stands for both.
"""

import json
import subprocess
import sys
from pathlib import Path

import build123d  # noqa: F401  (the model needs cad's build123d integration)
from PIL import Image

from galatea import galatea
from lib.hand import HAND_LINKS

OUT = Path(__file__).resolve().parents[1] / "tmp" / "review"
SKINS = ("panel_", "liner_", "helmet", "face_shield", "head_liner", "face_fascia", "foot_shell", "toe_cap", "hand_back",
         "trim_", "wordmark")
GROUPS = {
    "pelvis": ["pelvis"], "waist": ["lumbar_yoke", "waist_cross"], "chest": ["chest"], "neck": ["neck", "neck_stem"],
    "head": ["head"], "hip": ["l_hip_yoke", "l_hip_cradle"], "thigh": ["l_thigh", "l_knee_crank", "l_knee_rod"],
    "knee": ["l_thigh", "l_knee_crank", "l_knee_rod", "l_shin"], "shin": ["l_shin", "l_ankle_crank", "l_ankle_rods"],
    "foot": ["l_ankle_gimbal", "l_foot", "l_toe"], "shoulder": ["l_shoulder_yoke", "l_shoulder_block"],
    "upper_arm": ["l_upper_arm"], "forearm": ["l_forearm", "l_forearm_distal"],
    "hand": ["l_wrist_link", *[f"l_{link}" for link in HAND_LINKS]],
}
VIEWS = ("0:5", "90:5", "180:5", "-90:5")
SIDE = 640


def skins_of(tree, links):
    """Refs of the skins among `links`' parts: an occurrence's path, numbered among the siblings that share its label."""
    refs = []
    for link in tree.children:
        if link.label in links:
            names = [part.label for part in link.children]
            seen = {}
            for name in names:
                seen[name] = seen.get(name, 0) + 1
                if name.startswith(SKINS):
                    refs.append(f"{tree.label}/{link.label}/{name}" + (f".{seen[name]}" if names.count(name) > 1 else ""))
    return refs


def shot(document, isolated, hidden, camera, path):
    job = {"input": document, "camera": {"preset": camera}, "display": {"mode": "shaded", "isolated": isolated, "hidden": hidden},
           "outputs": [{"path": str(path), "width": SIDE, "height": SIDE}]}
    done = subprocess.run(["cad", "model", "snapshot", "--job", json.dumps(job)], capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"snapshot failed for {path.name}: {done.stdout.strip() or done.stderr.strip()}")


def main(names):
    OUT.mkdir(parents=True, exist_ok=True)
    handle = galatea()
    tree = handle.shape
    for name in names or GROUPS:
        links = GROUPS[name]
        isolated = [f"{tree.label}/{link}" for link in links]
        rows = [[]] + ([skins_of(tree, links)] if skins_of(tree, links) else [])
        sheet = Image.new("RGB", (SIDE * len(VIEWS), SIDE * len(rows)), "white")
        for j, hidden in enumerate(rows):
            for k, camera in enumerate(VIEWS):
                tile = OUT / f".{name}_{j}_{k}.png"
                shot(handle.id, isolated, hidden, camera, tile)
                sheet.paste(Image.open(tile).convert("RGB"), (k * SIDE, j * SIDE))
                tile.unlink()
        sheet.save(OUT / f"{name}.png")
        print(f"wrote {OUT / f'{name}.png'}")


if __name__ == "__main__":
    main(sys.argv[1:])
