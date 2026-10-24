"""The radial's two exploded clips as GLB animations: `explode` and `exploded-running`.

The original played them as JavaScript that translated parts by label. Their data is
`explode_plan.json`, kept verbatim from the original's generated `lib/anim_js.py`:

- `explode`, the teardown `lib/explodeplan.py` planned: 1,360 units (a part, or parts
  that leave together), each with a track of smoothstep-eased straight moves
  `[t0, t1, dx, dy, dz]`, a fastener's track its own moves after its host's (`[host
  track, moves]`); every part is in one unit (`groups`: `[track, label, ...]`). It runs
  24 s from the rest pose (crank angle 0), nothing turning.
- `exploded-running`, the layout `lib/explodedrun.py` made: the running cycle with each
  group of parts at a constant offset (`offsets`, `groups`), some parts hidden.

Here both are GLB animations (`cadgen.gltf`), the plan's moves exactly: each unit's
translation, its track (its host's and its own) sampled every `KEY_STEP` as LINEAR keys,
after the pose; `exploded-running` poses the running cycle at every key, holds each group
at its offset, and hides the parts the original hid (a GLB has no visibility channel:
`.hide` scales a part to 0). The mechanism takes no part in either: every part is a
reference of its own in the engine's tree, so each moves by its own track alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from cadgen.gltf import animation

PLAN = Path(__file__).with_name("explode_plan.json")
KEY_STEP = 0.05    # s between an explode track's sampled keys
POSE_STEP = 0.02   # s between exploded-running's poses of the running cycle (1.8 deg of crank)


def load() -> dict:
    return json.loads(PLAN.read_text())


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def _times(duration: float, step: float) -> list[float]:
    count = round(duration / step)
    return [duration * i / count for i in range(count + 1)]


def _tracks(data: dict) -> list[list[tuple[float, float, tuple[float, float, float]]]]:
    """Every unit's whole track: its host's moves, then its own."""
    tracks = data["explode"]["tracks"]
    full: dict[int, list] = {}

    def track(i: int) -> list:
        if i not in full:
            parent, moves = tracks[i]
            own = [(float(t0), float(t1), (float(dx), float(dy), float(dz))) for t0, t1, dx, dy, dz in moves]
            full[i] = (track(parent) if parent >= 0 else []) + own
        return full[i]

    return [track(i) for i in range(len(tracks))]


def _offset(track, t: float) -> tuple[float, float, float]:
    found = [0.0, 0.0, 0.0]
    for t0, t1, v in track:
        k = ease((t - t0) / (t1 - t0))
        for axis in range(3):
            found[axis] += k * v[axis]
    return tuple(found)


def explode(engine, path_of: dict[str, str]) -> None:
    """`explode`: every unit along its track over the plan's 24 s, from the rest pose."""
    data = load()
    duration = float(data["explode"]["duration"])
    tracks = _tracks(data)
    show = animation(engine, "explode", duration=duration)
    times = _times(duration, KEY_STEP)
    last = len(times) - 1
    for index, *labels in data["explode"]["groups"]:
        refs = [path_of[label] for label in labels if label in path_of]
        offsets = [_offset(tracks[index], t) for t in times]
        if not refs or not any(any(offset) for offset in offsets):
            continue
        keys = [(times[i], offsets[i]) for i in range(len(times))
                if i in (0, last) or not offsets[i - 1] == offsets[i] == offsets[i + 1]]
        show.channel(refs, path="translation", keys=keys, interpolation="LINEAR")


def exploded_running(engine, path_of: dict[str, str], duration: float, values_at) -> None:
    """`exploded-running`: the running cycle (``values_at(t)``, every joint's value) posed
    every ``POSE_STEP``, each group held at its offset and the hidden parts hidden."""
    data = load()["exploded_running"]
    show = animation(engine, "exploded-running", duration=duration)
    show.pose(at={t: values_at(t) for t in _times(duration, POSE_STEP)}, interpolation="LINEAR")
    for index, *labels in data["groups"]:
        offset = tuple(float(c) for c in data["offsets"][index])
        refs = [path_of[label] for label in labels if label in path_of]
        if refs and any(offset):
            show.channel(refs, path="translation", keys=[(0.0, offset)], interpolation="LINEAR")
    hidden = [path_of[label] for label in data["hidden"] if label in path_of]
    if hidden:
        show.hide(hidden, at=0.0)
