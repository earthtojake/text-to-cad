"""Verify the animation clips (lib/animation.py) against the built geometry.

  crank    sample the clip at 48 times (15 deg steps over 720 deg), evaluate
           it in-process the way the build samples it (every sample from rest,
           later calls premultiplying), apply the resulting transforms to the
           parts and run the SAME collision table as lib.collide (piston-valve,
           rod-block, rod-crank, rod-rod, valve-valve, ...) on those positions.
  explode  sample 0..1 at 0.05 (21 samples), apply the transforms to EVERY part,
           and test all pairs (AABB prefilter + distance + boolean common);
           at 1.0 also check no part's box is enclosed by another's.

Run from src/:
  python -m lib.anim_check crank   --json ../tmp/anim_crank.json
  python -m lib.anim_check explode --json ../tmp/anim_explode.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

from cadgen import build123d as bd

from lib import animation, collide, spec as S

# w16.py group order (empty groups are skipped there; every module is populated now)
GROUP_MODULES = [
    ("block", "block"), ("crank", "bottom_end"), ("pistons", "pistons"), ("heads", "heads"),
    ("valvetrain", "valvetrain"), ("cams", "cams"), ("camdrive", "camdrive"), ("covers", "covers"),
    ("oil_system", "oil_system"), ("turbos", "turbos"), ("exhaust", "exhaust"),
    ("induction", "induction"), ("ancillaries", "ancillaries"),
]


def build_all(verbose=True):
    """Every leaf part with its label and group id (o1.k), and each group's
    labels by id and by system name (the names the clips target)."""
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
        groups[gid] = groups[gname] = [p.label for p in leaves]
        for p in leaves:
            parts.append((p.label, gid, p))
        if verbose:
            print(f"[anim_check] {gname} -> {gid}: {len(leaves)} parts ({time.time() - t0:.0f}s)", file=sys.stderr)
    labels = [lab for lab, _, _ in parts]
    dup = {l for l in labels if labels.count(l) > 1}
    if dup:
        print(f"[anim_check] WARNING duplicate labels: {sorted(dup)[:10]}", file=sys.stderr)
    return parts, groups


# --- the clips, evaluated per part label ---------------------------------------
#
# A transform is a 12-tuple: the rotation row-major, then the translation.

_IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


def _compose(a, b):
    """`a` after `b`."""
    return (
        a[0] * b[0] + a[1] * b[3] + a[2] * b[6], a[0] * b[1] + a[1] * b[4] + a[2] * b[7],
        a[0] * b[2] + a[1] * b[5] + a[2] * b[8],
        a[3] * b[0] + a[4] * b[3] + a[5] * b[6], a[3] * b[1] + a[4] * b[4] + a[5] * b[7],
        a[3] * b[2] + a[4] * b[5] + a[5] * b[8],
        a[6] * b[0] + a[7] * b[3] + a[8] * b[6], a[6] * b[1] + a[7] * b[4] + a[8] * b[7],
        a[6] * b[2] + a[7] * b[5] + a[8] * b[8],
        a[0] * b[9] + a[1] * b[10] + a[2] * b[11] + a[9],
        a[3] * b[9] + a[4] * b[10] + a[5] * b[11] + a[10],
        a[6] * b[9] + a[7] * b[10] + a[8] * b[11] + a[11],
    )


def _rotation(axis, degrees, origin):
    """The turn by `degrees` about `axis` through `origin`."""
    n = math.sqrt(axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2])
    x, y, z = axis[0] / n, axis[1] / n, axis[2] / n
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    k = 1.0 - c
    r = (c + x * x * k, x * y * k - z * s, x * z * k + y * s,
         y * x * k + z * s, c + y * y * k, y * z * k - x * s,
         z * x * k - y * s, z * y * k + x * s, c + z * z * k)
    ox, oy, oz = origin
    return r + (ox - (r[0] * ox + r[1] * oy + r[2] * oz),
                oy - (r[3] * ox + r[4] * oy + r[5] * oz),
                oz - (r[6] * ox + r[7] * oy + r[8] * oz))


class _Handle:
    def __init__(self, matrices: dict, labels: list[str]):
        self._matrices = matrices
        self._labels = labels

    def _apply(self, op):
        for label in self._labels:
            current = self._matrices.get(label)
            self._matrices[label] = op if current is None else _compose(op, current)
        return self

    def rotate(self, axis, degrees, origin=(0.0, 0.0, 0.0)):
        return self._apply(_rotation(axis, degrees, origin))

    def translate(self, vector):
        return self._apply(_IDENTITY[:9] + tuple(float(c) for c in vector))

    def opacity(self, value):         # appearance never collides
        return self

    def visible(self, flag):
        return self


class _Model:
    """The `m` a clip's update receives, over part labels: a target is a label,
    or a system's group name or id (o1.k), or `w16`, every part."""

    def __init__(self, table: dict, known: set, names: list[str]):
        self.matrices: dict = {}
        self._table = table
        self._known = known
        self._names = names

    def labels(self):
        return self._names

    def get(self, *targets):
        labels = []
        for target in targets:
            name = target[1:]
            found = self._table.get(name) or ([name] if name in self._known else [])
            if not found:
                raise ValueError(f"animation target {target!r} names no part or group")
            labels.extend(found)
        return _Handle(self.matrices, list(dict.fromkeys(labels)))


def evaluate(clip: str, times: list[float], groups: dict, labels: list[str]) -> dict:
    """Each sample's transform per part label, the clip evaluated as the build
    samples it: every sample starts from rest and later calls premultiply. A
    time past the clip's end wraps if it loops and holds the end if not."""
    entry = animation.ANIMATION[clip]
    table = {**groups, "w16": list(labels)}
    known = set(labels)
    names = sorted(known | set(table))
    samples = []
    for t in times:
        model = _Model(table, known, names)
        entry.update(t % entry.duration if entry.loop and t > entry.duration else min(t, entry.duration), model)
        samples.append({"t": t, "matrices": model.matrices})
    return {"clip": clip, "duration": entry.duration, "samples": samples}


def as_location(m):
    """A transform (row-major 3x3, then the translation) as a Location."""
    from OCP.gp import gp_Trsf

    t = gp_Trsf()
    t.SetValues(m[0], m[1], m[2], m[9],
                m[3], m[4], m[5], m[10],
                m[6], m[7], m[8], m[11])
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
    times = [animation.CRANK_SECONDS * i / samples for i in range(samples)]
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
        theta = 720.0 * s["t"] / animation.CRANK_SECONDS
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
    times = [animation.EXPLODE_SECONDS * i / n for i in range(n + 1)]
    ev = evaluate("explode", times, groups, labels)
    shapes = {lab: sh for lab, _, sh in parts}
    table, offenders = [], {}
    t0 = time.time()
    for s in ev["samples"]:
        p = s["t"] / animation.EXPLODE_SECONDS
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
