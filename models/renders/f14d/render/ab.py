#!/usr/bin/env python3
"""Compose a BLIND A/B sheet: our render against a reference photograph.

    python render/ab.py ours.png reference.jpg out.png [--seed N]

Writes ``out.png`` with the two images side by side, unlabeled except for A and
B, in RANDOM order, and writes ``out.key.json`` recording which is which.  The
critic is shown only the sheet; the key is for the caller.

Both images are converted to greyscale and matched in height.  Greyscale is not
cosmetic: a grey aircraft on a dark render stage against a colour photograph in
daylight is separable on colour and background alone, which would make the test
measure the backdrop instead of the aeroplane.  Removing colour and matching
scale pushes the judgement back toward silhouette, proportion, surface and
detail -- which is what is actually being judged.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

H = 900
PAD = 28
BG = (26, 26, 28)


def prep(path):
    im = Image.open(path).convert("RGB")
    im = ImageOps.grayscale(im).convert("RGB")
    im = ImageOps.autocontrast(im, cutoff=1)
    w = max(1, int(im.width * H / im.height))
    return im.resize((w, H), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ours")
    ap.add_argument("reference")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    a_is_ours = rng.random() < 0.5
    left, right = ((args.ours, args.reference) if a_is_ours
                   else (args.reference, args.ours))
    li, ri = prep(left), prep(right)

    sheet = Image.new("RGB", (li.width + ri.width + 3 * PAD, H + 2 * PAD + 34), BG)
    sheet.paste(li, (PAD, PAD))
    sheet.paste(ri, (2 * PAD + li.width, PAD))
    d = ImageDraw.Draw(sheet)
    d.text((PAD + li.width // 2 - 6, H + PAD + 8), "A", fill=(235, 235, 235))
    d.text((2 * PAD + li.width + ri.width // 2 - 6, H + PAD + 8), "B",
           fill=(235, 235, 235))
    out = Path(args.out)
    sheet.save(out)
    key = {"A": "ours" if a_is_ours else "reference",
           "B": "reference" if a_is_ours else "ours",
           "ours": args.ours, "reference": args.reference}
    out.with_suffix(".key.json").write_text(json.dumps(key, indent=2))
    print(out)


if __name__ == "__main__":
    main()
