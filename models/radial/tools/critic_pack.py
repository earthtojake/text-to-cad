#!/usr/bin/env python3
"""Blind A/B packet for a gauntlet critic.

  tools/critic_pack.py OURS.png --ref tmp/refs/P_head_04.jpg --name heads_r1 [--seed N]
  tools/critic_pack.py OURS.png --bucket A --name front_r1          (random ref from bucket A_*)

Copies our render and one reference photograph into tmp/critic/<name>/ as
a.png and b.png in random order, both re-encoded as plain RGB PNG at the same
long edge (so neither suffix, size nor metadata tells which is the render), and
records the key in tmp/critic/keys/<name>.json — a path the critic is never shown.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "tmp" / "refs"
LONG_EDGE = 1600


def make_packet(ours: Path, ref: Path, name: str, seed=None) -> Path:
    rng = random.Random(seed)
    packet = ROOT / "tmp" / "critic" / name
    if packet.exists():
        shutil.rmtree(packet)
    packet.mkdir(parents=True)
    ours_first = rng.random() < 0.5
    a, b = (ours, ref) if ours_first else (ref, ours)
    for src, dst in ((a, packet / "a.png"), (b, packet / "b.png")):
        im = Image.open(src).convert("RGB")
        k = LONG_EDGE / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        im.save(dst, "PNG")
    keys = ROOT / "tmp" / "critic" / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    (keys / f"{name}.json").write_text(json.dumps(
        {"a": str(a), "b": str(b), "ours": "a" if ours_first else "b", "reference": ref.name}, indent=1))
    return packet


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ours")
    ap.add_argument("--ref")
    ap.add_argument("--bucket")
    ap.add_argument("--name", required=True)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    if a.ref:
        ref = Path(a.ref).resolve()
    else:
        refs = sorted(REFS.glob(f"{a.bucket}_*.jpg"))
        ref = random.Random(a.seed).choice(refs)
    p = make_packet(Path(a.ours).resolve(), ref, a.name, a.seed)
    print(p)
