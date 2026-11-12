# /// script
# dependencies = ["pillow"]
# ///
"""Galatea's presentation stills and clips: `cad run src/renders.py [name ...]` writes them to tmp/renders/.

Each still is one `cad model snapshot` of a document the server holds (the robot, or one
of the standing models of `stances.py`), drawn shaded through a long lens on a clear
background at twice its size, then set on a pale studio backdrop with a contact shadow.
A clip is a motion drawn frame by frame, the robot posed by its joint values under a
camera that stays put, and joined by ffmpeg (an MP4, and a GIF of it). The pictures are
review media: the project's .gitignore keeps them out of Git.
"""

import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import build123d  # noqa: F401  (the models need cad's build123d integration)
from PIL import Image, ImageDraw, ImageFilter

import actuators
import stances
from galatea import galatea
from lib.hand import HAND_LINKS
from lib.poses import CYCLE, walk

OUT = Path(__file__).resolve().parents[1] / "tmp" / "renders"
LENS = {"projection": "perspective", "focalLength": 85}

# name: (model, camera, size, extras). A camera is "azimuth:elevation" (fitted to the
# model) or a camera object in millimetres; extras are a pose, or parts to isolate.
LEFT_HAND = [f"l_{link}" for link in ("forearm", "forearm_distal", "wrist_link", *HAND_LINKS)]
HAND_OUT = {"l_shoulder_roll": 24, "l_elbow": 30}          # the left hand held clear of the hip
# The skins by label (or its beginning): what the undressed stills leave out.
SKINS = ("panel_", "liner_", "helmet", "face_shield", "head_liner", "face_fascia", "foot_shell", "toe_cap", "hand_back",
         "trim_", "wordmark")
STILLS = {
    "hero": (stances.galatea_contrapposto, "24:5", (1600, 2400), {}),
    "front": (galatea, "0:2", (1400, 2400), {}),
    "three_quarter": (galatea, "32:8", (1400, 2400), {}),
    "side": (galatea, "90:2", (1400, 2400), {}),
    "undressed": (galatea, "32:8", (1400, 2400), {"without": SKINS}),
    "undressed_back": (galatea, "152:8", (1400, 2400), {"without": SKINS}),
    "back": (galatea, "152:8", (1400, 2400), {}),
    "stride": (stances.galatea_stride, "58:4", (1800, 2400), {}),
    "reach": (stances.galatea_reach, "40:6", (1700, 2400), {}),
    "wave": (stances.galatea_wave, "-18:4", (1700, 2400), {}),
    "present": (stances.galatea_present, "0:8", (1700, 2400), {}),
    "poise": (stances.galatea_poise, "28:6", (1700, 2400), {}),
    "crouch": (stances.galatea_crouch, "48:8", (2000, 2000), {}),
    "bow": (stances.galatea_bow, "64:6", (2000, 2200), {}),
    "head": (galatea, {"position": [430, -800, 1700], "target": [0, -5, 1632], "up": [0, 0, 1]}, (1800, 1700), {}),
    "face": (galatea, {"position": [0, -900, 1668], "target": [0, 0, 1640], "up": [0, 0, 1]}, (1700, 1700), {}),
    "head_back": (galatea, {"position": [-470, 700, 1745], "target": [0, 20, 1640], "up": [0, 0, 1]}, (1800, 1700), {}),
    "torso": (galatea, {"position": [520, -1150, 1420], "target": [0, 10, 1300], "up": [0, 0, 1]}, (2000, 1800), {}),
    "waist": (galatea, {"position": [420, -620, 1210], "target": [0, 20, 1110], "up": [0, 0, 1]}, (2000, 1500), {}),
    "hip": (galatea, {"position": [640, -560, 1010], "target": [100, 0, 880], "up": [0, 0, 1]}, (2000, 1600),
            {"pose": {"l_shoulder_roll": 40, "l_elbow": 20}}),
    "knee_drive": (galatea, {"position": [520, 760, 820], "target": [82, 20, 640], "up": [0, 0, 1]}, (1800, 2000), {"without": SKINS}),
    "calf_drive": (galatea, {"position": [430, 640, 380], "target": [82, 10, 230], "up": [0, 0, 1]}, (1800, 2000), {"without": SKINS}),
    "foot": (galatea, {"position": [520, -520, 250], "target": [82, -40, 70], "up": [0, 0, 1]}, (2000, 1400), {}),
    "shoulder": (galatea, {"position": [650, 420, 1560], "target": [212, 10, 1390], "up": [0, 0, 1]}, (2000, 1600), {}),
    "hand": (galatea, {"position": [-100, -600, 975], "target": [440, -170, 885], "up": [0, 0, 1]}, (1800, 1800),
             {"isolated": LEFT_HAND, "pose": {**HAND_OUT, "l_index_curl": 0.25, "l_middle_curl": 0.4, "l_ring_curl": 0.55,
                                              "l_little_curl": 0.7, "l_thumb_opp": 40, "l_thumb_curl": 0.3}}),
    "hand_back": (galatea, {"position": [965, -551, 1147], "target": [440, -170, 880], "up": [0, 0, 1]}, (1800, 1800),
                  {"isolated": LEFT_HAND, "pose": {**HAND_OUT, "l_index_curl": 0.2, "l_middle_curl": 0.28, "l_ring_curl": 0.28,
                                                   "l_little_curl": 0.36, "l_thumb_opp": 24, "l_thumb_curl": 0.25}}),
    "back_detail": (galatea, {"position": [-420, 980, 1420], "target": [0, 60, 1240], "up": [0, 0, 1]}, (2000, 1800), {}),
    # The five drive models on their bench, from the output side and from behind.
    "actuators": (actuators.galatea_actuators, "28:22", (2400, 900), {}),
    "actuators_back": (actuators.galatea_actuators, "152:22", (2400, 900), {}),
}

# name: (pose at a time, seconds in a loop, views as (azimuth, elevation) from the front, frame size, frames a second).
CLIPS = {
    "walk": (walk, CYCLE, ((32, 6), (146, 8)), (720, 1080), 15),
}
AIM = (0.0, -10.0, 890.0)        # what a clip's camera looks at, and from how far
REACH = 5200.0


def snapshot(document, camera, size, extras, path):
    display = {"mode": "shaded", "camera": LENS, **{k: v for k, v in extras.items() if k in ("isolated", "hidden")}}
    job = {"input": document, "camera": {"preset": camera} if isinstance(camera, str) else camera, "display": display,
           "output": {"transparent": True, "renderScale": 2, "padding": 0.05},
           "outputs": [{"path": str(path), "width": size[0], "height": size[1]}]}
    if "pose" in extras:
        job["jointValues"] = extras["pose"]
    done = subprocess.run(["cad", "model", "snapshot", "--job", json.dumps(job), "--json"], capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"snapshot failed for {path.name}: {done.stdout.strip() or done.stderr.strip()}")


def without(shape, labels, keep=()):
    """Refs of the parts whose labels begin so, link by link (but in the links to `keep`): an
    occurrence's path, numbered among the siblings that share its label."""
    refs = []
    for link in shape.children:
        names = [part.label for part in link.children]
        seen = {}
        for name in names:
            seen[name] = seen.get(name, 0) + 1
            if name.startswith(tuple(labels)) and link.label not in keep:
                refs.append(f"{shape.label}/{link.label}/{name}" + (f".{seen[name]}" if names.count(name) > 1 else ""))
    return refs


def backdrop(size, top=(246, 247, 249), bottom=(196, 199, 204), pool=(252, 252, 253)):
    """A pale studio sweep, lighter behind the subject: the pearl panels and the black under-body both read on it."""
    w, h = size
    strip = Image.new("RGB", (1, h))
    strip.putdata([tuple(int(top[i] + (bottom[i] - top[i]) * y / (h - 1)) for i in range(3)) for y in range(h)])
    image = strip.resize((w, h))
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((w * 0.1, h * 0.02, w * 0.9, h * 0.84), fill=96)
    return Image.composite(Image.new("RGB", (w, h), pool), image, glow.filter(ImageFilter.GaussianBlur(w * 0.2)))


def stage(path, grounded):
    """Set a clear-backed still on the backdrop; a grounded one gets a contact shadow at its feet."""
    subject = Image.open(path).convert("RGBA")
    w, h = subject.size
    image = backdrop((w, h))
    box = subject.split()[3].getbbox()
    if grounded and box:
        x0, _, x1, y1 = box
        shadow = Image.new("L", (w, h), 0)
        spread = (x1 - x0) * 0.12
        ImageDraw.Draw(shadow).ellipse((x0 - spread, y1 - h * 0.02, x1 + spread, y1 + h * 0.028), fill=90)
        image = Image.composite(Image.new("RGB", (w, h), (60, 62, 66)), image, shadow.filter(ImageFilter.GaussianBlur(w * 0.02)))
    image.paste(subject, (0, 0), subject)
    image.save(path)


def film(name, document):
    """A motion as a looping clip: its views side by side, the feet treading on one floor."""
    pose_at, seconds, views, size, rate = CLIPS[name]
    count = round(seconds * rate)
    with tempfile.TemporaryDirectory() as folder:
        shots = {}
        for v, (azimuth, elevation) in enumerate(views):
            a, e = math.radians(azimuth), math.radians(elevation)
            away = (math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))
            camera = {"position": [AIM[k] + REACH * away[k] for k in range(3)], "target": list(AIM), "up": [0, 0, 1]}
            for k in range(count):
                path = Path(folder) / f"shot_{v}_{k:03d}.png"
                snapshot(document, camera, size, {"pose": pose_at(seconds * k / count)}, path)
                shots[v, k] = Image.open(path).convert("RGBA")
        w, h = shots[0, 0].size
        stage_image = backdrop((w * len(views), h))
        for v in range(len(views)):                       # one floor shadow a view, under everything its frames draw
            boxes = [shots[v, k].split()[3].getbbox() for k in range(count)]
            x0, x1, y1 = min(b[0] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)
            shadow = Image.new("L", stage_image.size, 0)
            ImageDraw.Draw(shadow).ellipse((v * w + x0 - 30, y1 - h * 0.022, v * w + x1 + 30, y1 + h * 0.03), fill=90)
            stage_image = Image.composite(Image.new("RGB", stage_image.size, (60, 62, 66)), stage_image,
                                          shadow.filter(ImageFilter.GaussianBlur(w * 0.03)))
        for k in range(count):
            frame = stage_image.copy()
            for v in range(len(views)):
                frame.paste(shots[v, k], (v * w, 0), shots[v, k])
            frame.resize((frame.width // 2 * 2, frame.height // 2 * 2)).save(Path(folder) / f"frame_{k:03d}.png")
        frames, clip = str(Path(folder) / "frame_%03d.png"), OUT / f"galatea_{name}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "3", "-framerate", str(rate), "-i", frames,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", str(clip)], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(rate), "-i", frames, "-filter_complex",
                        "scale=720:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer",
                        str(clip.with_suffix(".gif"))], check=True)
    print(f"wrote {clip} and {clip.with_suffix('.gif').name}")


def main(names):
    OUT.mkdir(parents=True, exist_ok=True)
    documents = {}
    for name in names or [*STILLS, *CLIPS]:
        if name in CLIPS:
            if shutil.which("ffmpeg") is None:
                raise SystemExit("a clip needs ffmpeg on the path")
            film(name, galatea().id)
            continue
        model, camera, size, extras = STILLS[name]
        if model not in documents:
            documents[model] = model()
        if "without" in extras:
            extras = {"hidden": without(documents[model].shape, extras["without"])}
        path = OUT / f"galatea_{name}.png"
        snapshot(documents[model].id, camera, size, extras, path)
        stage(path, grounded=isinstance(camera, str))
        print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
