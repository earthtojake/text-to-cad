"""Blind A/B packet builder for the gauntlet critics.

Copies our render and one reference photo into a fresh directory as `a.png`
and `b.png` in random order, records which is which in a JSON the critic
never sees, and prints the packet path. Run from src/:

    python -m lib.critic_pack tmp/turbos_a.png --bucket D --name turbos_r1
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REFS = ROOT / "tmp" / "refs"


def make_packet(ours: Path, bucket: str, name: str, seed: int | None = None) -> Path:
    rng = random.Random(seed)
    refs = sorted(p for p in REFS.glob(f"{bucket}_*.jpg"))
    if not refs:
        raise SystemExit(f"no references for bucket {bucket} in {REFS}")
    ref = rng.choice(refs)
    packet = ROOT / "tmp" / "critic" / name
    if packet.exists():
        shutil.rmtree(packet)
    packet.mkdir(parents=True)
    ours_first = rng.random() < 0.5
    a, b = (ours, ref) if ours_first else (ref, ours)
    # both sides land as .png at the same long edge so neither the suffix nor
    # the pixel size gives away which one is the render
    from PIL import Image
    for src, dst in ((a, packet / "a.png"), (b, packet / "b.png")):
        im = Image.open(src).convert("RGB")
        k = 1600.0 / max(im.size)
        if k < 1.0:
            im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        im.save(dst, "PNG")
    key = {"a": str(a), "b": str(b), "ours": "a" if ours_first else "b", "reference": ref.name}
    (ROOT / "tmp" / "critic" / f"{name}.key.json").write_text(json.dumps(key, indent=1))
    return packet


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ours")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    p = make_packet(Path(args.ours).resolve(), args.bucket, args.name, args.seed)
    print(p)
    for f in sorted(p.iterdir()):
        print("  ", f.name)
