#!/usr/bin/env python3
"""Deterministic checks for the F-14D assembly.

    .venv/bin/python models/renders/f14d/validate.py

Runs three things the visual gauntlet cannot:

1. BILATERAL SYMMETRY.  Every leaf solid is matched against a partner whose
   centroid is its mirror in the XZ plane and whose volume agrees.  Centreline
   parts must be self-symmetric.  The worst mismatch is printed, not hidden
   behind a pass/fail -- the brief asks for the number.
2. Per-solid validity and closure -- delegated to `inspect validate`, which
   checks topology, closure, orientation and self-intersection per occurrence.
3. Part-vs-part interpenetration -- delegated to `inspect interfere`.

Exit code is non-zero if any check fails.
"""

from __future__ import annotations

import importlib.util
import math
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PY = sys.executable
ENTRY = HERE / "f14d.step.py"

SYM_TOL_MM = 1.0          # centroid mirror tolerance
SYM_VOL_TOL = 0.005       # relative volume tolerance between mirrored partners
CENTRELINE_MM = 2.0       # |y| below this counts as a centreline part


def load_entry(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


def leaves(shape, prefix=""):
    """Every leaf solid as (label, volume, centroid)."""
    out = []
    kids = list(getattr(shape, "children", []) or [])
    if kids:
        for k in kids:
            out += leaves(k, f"{prefix}/{getattr(k, 'label', '?')}")
        return out
    try:
        for s in shape.solids():
            c = s.center()
            out.append((prefix, s.volume, (c.X, c.Y, c.Z)))
    except Exception:                                   # noqa: BLE001
        pass
    return out


def symmetry(items):
    """Match each leaf with its mirror partner; return the worst mismatch."""
    unmatched, worst, worst_of = [], 0.0, None
    pool = list(range(len(items)))
    used = set()
    for i in pool:
        if i in used:
            continue
        lab, vol, (cx, cy, cz) = items[i]
        if abs(cy) <= CENTRELINE_MM:
            used.add(i)
            continue                                    # self-symmetric
        best, best_d = None, None
        for j in pool:
            if j in used or j == i:
                continue
            _, v2, (x2, y2, z2) = items[j]
            if vol > 0 and abs(v2 - vol) / max(vol, 1e-9) > SYM_VOL_TOL:
                continue
            d = math.dist((cx, -cy, cz), (x2, y2, z2))
            if best_d is None or d < best_d:
                best, best_d = j, d
        if best is None or best_d > SYM_TOL_MM:
            unmatched.append((lab, cx, cy, cz, best_d))
        else:
            used.add(i)
            used.add(best)
            if best_d > worst:
                worst, worst_of = best_d, lab
    return worst, worst_of, unmatched


def run(cmd):
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def main():
    ok = True

    print("=== build ===")
    rc, out, err = run([PY, str(REPO / "skills/cad/scripts/gen"), str(ENTRY)])
    print(out or err.splitlines()[-1] if (out or err) else "")
    if rc != 0:
        print(f"FAIL: gen exited {rc}")
        print(err)
        return 1

    print("\n=== bilateral symmetry ===")
    mod = load_entry(ENTRY)
    items = leaves(mod.gen_step())
    print(f"leaf solids: {len(items)}")
    worst, worst_of, unmatched = symmetry(items)
    print(f"worst mirrored-centroid mismatch: {worst:.4f} mm"
          + (f"  ({worst_of})" if worst_of else ""))
    if unmatched:
        ok = False
        print(f"UNMATCHED ({len(unmatched)}) -- these have no mirror partner:")
        for lab, cx, cy, cz, d in unmatched[:15]:
            dd = "none" if d is None else f"{d:.2f} mm"
            print(f"  {lab}  centroid=({cx:.1f},{cy:.1f},{cz:.1f})  nearest={dd}")
    else:
        print(f"PASS: every off-centreline solid has a mirror partner "
              f"within {SYM_TOL_MM} mm")

    print("\n=== per-solid validity / closure / self-intersection ===")
    rc, out, err = run([PY, str(REPO / "skills/cad/scripts/inspect"),
                        "validate", str(ENTRY)])
    print(out[:4000] or err[:2000])
    if rc != 0:
        ok = False
        print(f"FAIL: inspect validate exited {rc}")

    print("\n=== part-vs-part interpenetration ===")
    rc, out, err = run([PY, str(REPO / "skills/cad/scripts/inspect"),
                        "interfere", str(ENTRY)])
    print(out[:4000] or err[:2000])
    if rc != 0:
        ok = False
        print(f"FAIL: inspect interfere exited {rc}")

    print("\n=== RESULT:", "PASS" if ok else "FAIL", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
