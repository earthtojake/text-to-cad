"""Verify the .anim.js clips against the built geometry.

  crank    sample the clip at 48 times (15 deg steps over 720 deg), evaluate
           w16.anim.js headlessly (anim_eval.mjs, same matrix semantics as the
           viewer), apply the resulting matrices to the parts and run the
           SAME collision table as lib.collide (piston-valve, rod-block,
           rod-crank, rod-rod, valve-valve, ...) on those positions.
  explode  sample 0..1 at 0.05 (21 samples), apply the matrices to EVERY part,
           and test all pairs (AABB prefilter + distance + boolean common);
           at 1.0 also check no part's box is enclosed by another's.

Run from src/:
  python -m lib.anim_check crank   --json ../tmp/anim_crank.json
  python -m lib.anim_check explode --json ../tmp/anim_explode.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from cadgen import build123d as bd

from lib import collide, spec as S

HERE = Path(__file__).resolve().parent
EVAL = HERE / "anim_eval.mjs"

# w16.py group order (empty groups are skipped there; every module is populated now)
GROUP_MODULES = [
    ("block", "block"), ("crank", "bottom_end"), ("pistons", "pistons"), ("heads", "heads"),
    ("valvetrain", "valvetrain"), ("cams", "cams"), ("camdrive", "camdrive"), ("covers", "covers"),
    ("oil_system", "oil_system"), ("turbos", "turbos"), ("exhaust", "exhaust"),
    ("induction", "induction"), ("ancillaries", "ancillaries"),
]


def build_all(verbose=True):
    """Every leaf part with its label and group id (o1.k)."""
    import importlib

    parts = []
    groups = {}
    t0 = time.time()
    k = 0
    for gname, mod in GROUP_MODULES:
        m = importlib.import_module(f"lib.{mod}")
        leaves = m.build(True) if mod != "pistons" and mod != "valvetrain" else m.build()
        leaves = [p for p in leaves if p is not None]
        if not leaves:
            continue
        k += 1
        gid = f"o1.{k}"
        groups[gid] = [p.label for p in leaves]
        for p in leaves:
            parts.append((p.label, gid, p))
        if verbose:
            print(f"[anim_check] {gname} -> {gid}: {len(leaves)} parts ({time.time() - t0:.0f}s)", file=sys.stderr)
    labels = [lab for lab, _, _ in parts]
    dup = {l for l in labels if labels.count(l) > 1}
    if dup:
        print(f"[anim_check] WARNING duplicate labels: {sorted(dup)[:10]}", file=sys.stderr)
    return parts, groups


def evaluate(clip: str, times: list[float], groups: dict, labels: list[str]) -> dict:
    tmpl = HERE.parent.parent / "tmp" / "anim_labels.json"
    tmpl.write_text(json.dumps({"__labels__": labels, **groups}))
    arg = ",".join(f"{t:.6f}" for t in times)
    out = subprocess.run(["node", str(EVAL), clip, arg, str(tmpl)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def as_location(m16):
    from OCP.gp import gp_Trsf

    t = gp_Trsf()
    # column-major three.js layout -> row-major 3x4
    t.SetValues(m16[0], m16[4], m16[8], m16[12],
                m16[1], m16[5], m16[9], m16[13],
                m16[2], m16[6], m16[10], m16[14])
    return bd.Location(t)


def placed(parts, matrices):
    out = {}
    for lab, gid, shape in parts:
        m = matrices.get(lab)
        out[lab] = shape.moved(as_location(m)) if m else shape
    return out


def check_crank(out_json=None, samples=48, verbose=True, shard=None):
    parts, groups = build_all(verbose)
    labels = [lab for lab, _, _ in parts]
    times = [6.0 * i / samples for i in range(samples)]          # CRANK_SECONDS = 6
    if shard:
        k, n = shard
        times = [t for i, t in enumerate(times) if i % n == k]
    ev = evaluate("crank", times, groups, labels)
    # same pair set as the gate
    shapes = {lab: sh for lab, _, sh in parts}
    pairs = []
    labs = list(shapes)
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            cat = collide.category(labs[i], labs[j])
            if cat is None:
                continue
            if cat == "rod-rod" and collide._same_cylinder(labs[i], labs[j]):
                continue
            if cat == "piston-piston" and collide._same_cylinder(labs[i], labs[j]):
                continue
            if cat in ("follower-follower", "roller-roller") and labs[i].split(":")[1] == labs[j].split(":")[1]:
                continue
            pairs.append((labs[i], labs[j], cat))
    # rest-box envelope prefilter (generous: 100 mm)
    rest = {lab: collide._bbox(sh) for lab, sh in shapes.items()}
    grow = lambda b, e: (b[0]-e, b[1]-e, b[2]-e, b[3]+e, b[4]+e, b[5]+e)
    pairs = [(a, b, c) for a, b, c in pairs if collide._bbox_overlap(grow(rest[a], 100), grow(rest[b], 100))]
    if verbose:
        print(f"[anim_check] {len(pairs)} candidate pairs", file=sys.stderr)
    # Localise the big bodies exactly as the gate does (collide.run): a rod
    # against the WHOLE block per sample is what made this 15 min/sample. For
    # each pair with a big body, carve once the piece of the big body's REST
    # shape inside the small part's motion envelope (its rest box + 100 mm);
    # per sample the chunk rides the big body's own animation matrix, so the
    # test is exact for everything the small part can reach.
    big = {"block", "head:1", "head:2", "crankshaft", "camshaft:1_intake", "camshaft:1_exhaust",
           "camshaft:2_intake", "camshaft:2_exhaust"}
    chunks = {}

    def chunk_of(big_lab, small_lab):
        key = (big_lab, small_lab)
        if key in chunks:
            return chunks[key]
        b = grow(rest[small_lab], 100)
        if big_lab.startswith(("crankshaft", "camshaft")):
            box = bd.Box(b[3] - b[0], 4000.0, 4000.0, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER)).moved(bd.Location((b[0], 0.0, 0.0)))
        else:
            box = bd.Box(b[3] - b[0], b[4] - b[1], b[5] - b[2], align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN)).moved(bd.Location((b[0], b[1], b[2])))
        try:
            piece = shapes[big_lab].intersect(box)
            solids = list(piece.solids())
        except Exception:
            solids = [shapes[big_lab]]
        piece = None if not solids else (solids[0] if len(solids) == 1 else bd.Compound(children=solids))
        chunks[key] = piece
        return piece

    local = []
    for a, b, cat in pairs:
        ca = chunk_of(a, b) if a in big and b not in big else None
        cb = chunk_of(b, a) if b in big and a not in big else None
        if (a in big and b not in big and ca is None) or (b in big and a not in big and cb is None):
            continue                      # nothing of the big body near the small part
        local.append((a, b, cat, ca, cb))
    pairs = local
    if verbose:
        print(f"[anim_check] {len(chunks)} local chunks carved; {len(pairs)} pairs to test", file=sys.stderr)
    table, offenders = [], {}
    t0 = time.time()
    for s in ev["samples"]:
        theta = 720.0 * s["t"] / 6.0
        pl = placed(parts, s["matrices"])
        boxes = {lab: collide._bbox(pl[lab]) for lab in pl}
        counts = {}
        for a, b, cat, ca, cb in pairs:
            sa = ca.moved(as_location(s["matrices"][a])) if (ca is not None and s["matrices"].get(a)) else (ca if ca is not None else pl[a])
            sb = cb.moved(as_location(s["matrices"][b])) if (cb is not None and s["matrices"].get(b)) else (cb if cb is not None else pl[b])
            if not collide._bbox_overlap(collide._bbox(sa) if ca is not None else boxes[a], collide._bbox(sb) if cb is not None else boxes[b]):
                continue
            v = collide.clash_volume(sa, sb)
            if v > collide.TOL_MM3:
                counts[cat] = counts.get(cat, 0) + 1
                offenders.setdefault(cat, []).append((theta, a, b, round(v, 3)))
            elif v < 0:
                counts["unknown"] = counts.get("unknown", 0) + 1
        table.append((theta, counts))
        if verbose:
            print(f"[anim_check] crank theta {theta:6.1f}: {counts or 'clean'} ({time.time() - t0:.0f}s)", file=sys.stderr)
    _report("crank", table, offenders, out_json)
    return sum(sum(c.values()) for _, c in table)


def check_explode(out_json=None, step=0.05, verbose=True):
    parts, groups = build_all(verbose)
    labels = [lab for lab, _, _ in parts]
    n = int(round(1.0 / step))
    times = [12.0 * i / n for i in range(n + 1)]                 # EXPLODE_SECONDS = 12
    ev = evaluate("explode", times, groups, labels)
    shapes = {lab: sh for lab, _, sh in parts}
    table, offenders = [], {}
    t0 = time.time()
    for s in ev["samples"]:
        p = s["t"] / 12.0
        pl = placed(parts, s["matrices"])
        boxes = {lab: collide._bbox(pl[lab]) for lab in pl}
        labs = list(pl)
        counts = {}
        for i in range(len(labs)):
            for j in range(i + 1, len(labs)):
                a, b = labs[i], labs[j]
                if not collide._bbox_overlap(boxes[a], boxes[b], eps=-0.05):
                    continue
                v = collide.clash_volume(pl[a], pl[b])
                if v > collide.TOL_MM3:
                    counts["clash"] = counts.get("clash", 0) + 1
                    offenders.setdefault("clash", []).append((round(p, 3), a, b, round(v, 3)))
        if abs(p - 1.0) < 1e-9:
            enclosed = []
            for a in labs:
                ba = boxes[a]
                for b in labs:
                    if a == b:
                        continue
                    bb = boxes[b]
                    if bb[0] <= ba[0] and bb[1] <= ba[1] and bb[2] <= ba[2] and bb[3] >= ba[3] and bb[4] >= ba[4] and bb[5] >= ba[5]:
                        enclosed.append((a, b))
                        break
            counts["enclosed_at_1"] = len(enclosed)
            offenders["enclosed_at_1"] = enclosed
        table.append((p, counts))
        if verbose:
            print(f"[anim_check] explode {p:4.2f}: {counts or 'clean'} ({time.time() - t0:.0f}s)", file=sys.stderr)
    _report("explode", table, offenders, out_json)
    return sum(sum(c.values()) for _, c in table)


def _report(name, table, offenders, out_json):
    cats = sorted({c for _, counts in table for c in counts})
    print(f"== {name} ==")
    print("param   " + "  ".join(f"{c:>18}" for c in cats))
    for p, counts in table:
        print(f"{p:7.2f} " + "  ".join(f"{counts.get(c, 0):>18d}" for c in cats))
    total = sum(sum(c.values()) for _, c in table)
    print(f"TOTAL findings: {total}")
    for cat, lst in offenders.items():
        print(f"  {cat}: {len(lst)} e.g. {lst[:6]}")
    if out_json:
        Path(out_json).write_text(json.dumps({"table": table, "offenders": offenders}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", choices=["crank", "explode"])
    ap.add_argument("--json", default="")
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--shard", default="", help="k/n: run only samples i with i %% n == k")
    a = ap.parse_args()
    if a.clip == "crank":
        shard = tuple(int(v) for v in a.shard.split("/")) if a.shard else None
        total = check_crank(a.json or None, a.samples, shard=shard)
    else:
        total = check_explode(a.json or None, a.step)
    sys.exit(0 if total == 0 else 1)
