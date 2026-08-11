#!/usr/bin/env python3
"""Run the whole-aircraft gauntlet: render four views, compose four blind A/B sheets.

    python render/gauntlet.py <stem> [--seed N]

Renders top / head / side / fq of the full assembly with the presentation theme,
pairs each against the matching reference photograph, and writes the sheets plus
their keys. The keys are for the caller only -- the critic sees the sheet.
"""

from __future__ import annotations

import argparse
import glob
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parents[2]
PY = sys.executable
ENTRY = PROJECT / "f14d.step.py"
REFS = Path("/private/tmp/claude-501/-Users-jakefitzgerald-robots-text-to-cad-"
            "-claude-worktrees-f14d-tomcat-cad-b6e8ce/"
            "0c13a035-c570-4b9c-a8a9-02cccf8212db/scratchpad/refs")

# The C_ crops are the reference photographs cut down to the AIRCRAFT.  Judging
# against the uncropped frames would compare a render stage to a flight deck and
# a boneyard, so the verdict would turn on the backdrop rather than the
# aeroplane.  All four show gear down and wings spread -- the model's own
# configuration -- so the comparison is like for like.
PAIRS = [("top", "C_REF_top.jpg"), ("head", "C_REF_head.jpg"),
         ("side", "C_REF_side.jpg"), ("fq", "C_REF_fq.jpg")]


def newest(pattern):
    hits = sorted(glob.glob(pattern))
    return hits[-1] if hits else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stem")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    out = PROJECT / "render" / "gauntlet"
    out.mkdir(parents=True, exist_ok=True)

    rc = subprocess.run(
        [PY, str(HERE / "shot.py"), str(ENTRY), args.stem,
         "--views", ",".join(v for v, _ in PAIRS),
         "--size", "assembly-large", "--outdir", str(out)],
        cwd=str(REPO)).returncode
    if rc != 0:
        return rc

    for i, (view, ref) in enumerate(PAIRS):
        ours = newest(str(out / f"{args.stem}_{view}_*.png"))
        if not ours:
            print(f"MISSING render for {view}")
            continue
        sheet = out / f"AB_{args.stem}_{view}.png"
        subprocess.run([PY, str(HERE / "ab.py"), ours, str(REFS / ref),
                        str(sheet), "--seed", str(args.seed + i)],
                       cwd=str(REPO))
    print("\nsheets:")
    for view, _ in PAIRS:
        print("  ", out / f"AB_{args.stem}_{view}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
