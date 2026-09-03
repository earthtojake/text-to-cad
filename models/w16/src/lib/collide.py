"""Kinematic collision gate.

Builds every moving part ONCE at theta = 0, then for each sampled crank angle
applies the same rigid transforms the .anim.js applies (crank spin, rod
swing, piston slide, cam spin, valve lift, follower rock) and tests the
required pairs for interpenetration:

  piston-valve, rod-block, rod-crank, rod-rod, valve-valve   (the brief's gate)
  + piston-head, valve-head, follower-head, cam-head, cam-follower/roller,
    spring-cup, piston-block, piston-piston (extra, same machinery)

A pair "collides" when the boolean common volume exceeds TOL_MM3 (touching
contacts — roller on lobe, pad on tip, ball in socket — yield ~0).

Run from the project's src/:   python -m lib.collide [--step 15] [--json out]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time

from cadgen import build123d as bd

from lib import kin, spec as S

TOL_MM3 = 0.05
DIST_SKIP = 0.05      # mm; pairs farther apart than this are not booleaned


def _bbox(shape):
    """World AABB without tessellating (bounding_box() meshes and mutates)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape.wrapped, box, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (xmin, ymin, zmin, xmax, ymax, zmax)


def _bbox_overlap(a, b, eps=0.2):
    return not (a[3] + eps < b[0] or b[3] + eps < a[0] or a[4] + eps < b[1] or b[4] + eps < a[1]
                or a[5] + eps < b[2] or b[5] + eps < a[2])


def _distance(a, b):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    d.Perform()
    return d.Value() if d.IsDone() else 0.0


def _common_volume(a, b):
    """Boolean common volume; a failed exact boolean is retried fuzzy, and a
    pair whose booleans both fail is reported as -1 ("unknown"), NOT as a clash."""
    try:
        c = a.intersect(b)
        if c is None:                      # build123d: empty common
            return 0.0
        # build123d returns a ShapeList when the common has several solids
        if isinstance(c, (list, tuple)):
            return sum(abs(x.volume) for x in c)
        return abs(c.volume)
    except Exception:
        pass
    try:
        from lib import geo
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
        from OCP.TopTools import TopTools_ListOfShape
        args = TopTools_ListOfShape(); args.Append(a.wrapped)
        tools = TopTools_ListOfShape(); tools.Append(b.wrapped)
        op = BRepAlgoAPI_Common(); op.SetArguments(args); op.SetTools(tools)
        op.SetFuzzyValue(1e-3); op.Build()
        if op.IsDone():
            return abs(bd.Compound(op.Shape()).volume)
    except Exception:
        pass
    return -1.0


def clash_volume(a, b):
    if not _bbox_overlap(_bbox(a), _bbox(b)):
        return 0.0
    if _distance(a, b) > DIST_SKIP:
        return 0.0
    return _common_volume(a, b)


# ---------------------------------------------------------------------------
# Motion: rest shapes + a transform per theta (mirrors the .anim.js exactly)
# ---------------------------------------------------------------------------

class Mover:
    """A part authored at theta = 0 plus the rule that moves it."""

    def __init__(self, label, shape, rule, **kw):
        self.label = label
        self.rest = shape
        self.rule = rule
        self.kw = kw

    def at(self, theta):
        s = self.rest
        r = self.rule
        if r == "static":
            return s
        if r == "crank":
            return s.rotate(bd.Axis((0, 0, 0), (1, 0, 0)), theta)
        if r == "cam":
            y, z = self.kw["axis"]
            return s.rotate(bd.Axis((0, y, z), (1, 0, 0)), kin.cam_angle(theta))
        if r == "piston":
            c = S.CYLINDERS[self.kw["cyl"] - 1]
            ds = kin.piston(c.number, theta).s - kin.piston(c.number, 0.0).s
            return s.translate(bd.Vector(0, c.axis[1] * ds, c.axis[2] * ds))
        if r == "rod":
            c = S.CYLINDERS[self.kw["cyl"] - 1]
            st0 = kin.piston(c.number, 0.0)
            st = kin.piston(c.number, theta)
            out = s.rotate(bd.Axis((c.x, st0.pin[0], st0.pin[1]), (1, 0, 0)), st.rod_tilt - st0.rod_tilt)
            return out.translate(bd.Vector(0, st.pin[0] - st0.pin[0], st.pin[1] - st0.pin[1]))
        if r == "valve":
            # the rest shape is the TRUE theta = 0 state (some valves are open
            # there), so motion is relative to lift(0)
            g = self.kw["g"]
            lift = kin.valve_lift(g.cyl, g.kind, theta) - kin.valve_lift(g.cyl, g.kind, 0.0)
            return s.translate(bd.Vector(0, -g.v[0] * lift, -g.v[1] * lift))
        if r == "follower":
            g = self.kw["g"]
            _, eps, _, _ = kin.follower_state(g, theta)
            _, eps0, _, _ = kin.follower_state(g, 0.0)
            return s.rotate(bd.Axis((g.x, g.pivot[0], g.pivot[1]), (1, 0, 0)), eps - eps0)
        raise ValueError(r)


def build_world(sectioned=True, cylinders=range(1, 17), verbose=True):
    from lib import block, bottom_end, cams, heads, pistons, valvetrain

    t0 = time.time()
    world = {"static": [], "movers": []}

    def log(msg):
        if verbose:
            print(f"[collide] {msg} ({time.time() - t0:.0f}s)", file=sys.stderr)

    blk = block.build_block(sectioned)
    world["static"].append(Mover("block", blk, "static"))
    log("block")
    for h in heads.build(sectioned):
        world["static"].append(Mover(h.label, h, "static"))
    log("heads")
    crank = bottom_end.build_crank()
    world["movers"].append(Mover("crankshaft", crank, "crank"))
    log("crank")
    for cyl in cylinders:
        for p in pistons.build_cylinder_set(cyl, 0.0):
            lab = p.label
            if lab.startswith(("piston", "wrist_pin", "circlip")):
                world["movers"].append(Mover(lab, p, "piston", cyl=cyl))
            else:
                world["movers"].append(Mover(lab, p, "rod", cyl=cyl))
    log("pistons+rods")
    for cyl in cylinders:
        for kind in ("intake", "exhaust"):
            for side in (-1, 1):
                g = kin.valve_geom(cyl, kind, side)
                for p in valvetrain.build_valve(g, 0.0):
                    lab = p.label
                    if lab.startswith(("valve:", "valve_spring", "retainer", "collet")):
                        world["movers"].append(Mover(lab, p, "valve", g=g))
                    elif lab.startswith(("follower", "roller")):
                        world["movers"].append(Mover(lab, p, "follower", g=g))
                    else:
                        world["static"].append(Mover(lab, p, "static"))
    log("valvetrain")
    for bank in (1, 2):
        for kind in ("intake", "exhaust"):
            cam = cams.build_cam(bank, kind)
            world["movers"].append(Mover(cam.label, cam, "cam", axis=cams.cam_axis(bank, kind)))
    log("cams")
    return world


def category(a: str, b: str):
    """Map a label pair to the report category (None = not required)."""
    def kind(l):
        head = l.split(":")[0]
        return {
            "piston": "piston", "piston_ring": "piston", "wrist_pin": "piston", "circlip": "piston",
            "rod": "rod", "rod_cap": "rod", "rod_bolt": "rod", "rod_shell": "rod", "rod_bush": "rod",
            "valve": "valve", "valve_spring": "spring", "retainer": "valve", "collet": "valve",
            "follower": "follower", "roller": "roller", "roller_axle": "follower",
            "spring_cup": "cup", "valve_guide": "guide", "lash_adjuster": "hla",
            "camshaft": "cam", "crankshaft": "crank", "block": "block", "head": "head",
        }.get(head, head)

    ka, kb = sorted((kind(a), kind(b)))
    pair = f"{ka}-{kb}"
    wanted = {
        "piston-valve", "block-rod", "crank-rod", "rod-rod", "valve-valve",
        "head-piston", "head-valve", "follower-head", "cam-head", "cam-roller", "cam-follower",
        "cup-spring", "block-piston", "piston-piston", "follower-valve", "follower-hla",
        "roller-roller", "follower-follower", "crank-piston", "block-crank", "spring-spring",
        "guide-valve", "block-valve", "cup-valve",
    }
    return pair if pair in wanted else None


def _same_cylinder(a, b):
    def cyl_of(l):
        try:
            return int(l.split(":")[1].split("_")[0])
        except Exception:
            return None
    return cyl_of(a) == cyl_of(b)


_SAMPLE = {}


def _sample_global(theta):
    return _SAMPLE["fn"](theta)


def _cat_of(found, pairs):
    la, lb = found[1], found[2]
    return category(la, lb) or "?"


def run(step=15.0, sectioned=True, cylinders=range(1, 17), out_json=None, verbose=True, workers=1, thetas=None):
    world = build_world(sectioned, cylinders, verbose)
    allparts = world["static"] + world["movers"]
    # candidate pairs by category, decided on labels
    pairs = []
    for i in range(len(allparts)):
        for j in range(i + 1, len(allparts)):
            a, b = allparts[i], allparts[j]
            if a.rule == "static" and b.rule == "static":
                continue
            cat = category(a.label, b.label)
            if cat is None:
                continue
            # a rod's own shells/bolts/cap ride with it: same-cylinder rod-rod is one part
            if cat == "rod-rod" and _same_cylinder(a.label, b.label):
                continue
            if cat == "piston-piston" and _same_cylinder(a.label, b.label):
                continue
            if cat in ("follower-follower", "roller-roller") and a.label.split(":")[1] == b.label.split(":")[1]:
                continue
            pairs.append((a, b, cat))
    # prefilter: a pair whose REST boxes, grown by each part's motion envelope,
    # do not overlap can never meet. Envelopes: crank/cam spin -> its own radius;
    # pistons/rods -> the stroke + throw; valves/followers -> the lift.
    env = {"static": 0.0, "crank": 0.0, "cam": 0.0, "piston": S.STROKE + 2.0, "rod": S.STROKE + 2 * S.THROW + 2.0,
           "valve": S.VALVE_LIFT + 0.5, "follower": 12.0}
    rest_boxes = {}
    for m in allparts:
        b = _bbox(m.rest)
        if m.rule in ("crank", "cam"):
            # a spinning part sweeps a cylinder about its axis: grow y/z to the max radius
            cy, cz = (0.0, 0.0) if m.rule == "crank" else m.kw["axis"]
            r = max(math.hypot(b[1] - cy, b[2] - cz), math.hypot(b[4] - cy, b[5] - cz),
                    math.hypot(b[1] - cy, b[5] - cz), math.hypot(b[4] - cy, b[2] - cz))
            b = (b[0], cy - r, cz - r, b[3], cy + r, cz + r)
        e = env[m.rule]
        rest_boxes[m.label] = (b[0] - e, b[1] - e, b[2] - e, b[3] + e, b[4] + e, b[5] + e)
    pairs = [(a, b, cat) for a, b, cat in pairs if _bbox_overlap(rest_boxes[a.label], rest_boxes[b.label])]
    if verbose:
        print(f"[collide] {len(pairs)} candidate pairs after envelope prefilter", file=sys.stderr)
    # Localise the big bodies: testing a rod against the WHOLE block (hundreds
    # of faces) per sample is what makes this slow. For every pair involving a
    # big body, carve out once the piece of it inside the small part's motion
    # envelope box (plus margin) and test against that chunk instead. The
    # chunk moves with the big body's own rule (static, or crank spin), which
    # is exact because the chunk box for a rod spans the rod's full x-range.
    big = {"block", "head:1", "head:2", "crankshaft", "camshaft:1_intake", "camshaft:1_exhaust",
           "camshaft:2_intake", "camshaft:2_exhaust"}
    chunk_cache = {}

    def chunk_of(big_m, small_m):
        b = rest_boxes[small_m.label]
        key = (big_m.label, tuple(round(v, 1) for v in b))
        if key in chunk_cache:
            return chunk_cache[key]
        box = bd.Box(b[3] - b[0] + 4.0, b[4] - b[1] + 4.0, b[5] - b[2] + 4.0,
                     align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN)).moved(bd.Location((b[0] - 2.0, b[1] - 2.0, b[2] - 2.0)))
        if big_m.rule in ("crank", "cam"):
            # the big body spins: use a slab over the small part's x-range only, full y/z
            box = bd.Box(b[3] - b[0] + 4.0, 2000.0, 2000.0, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER)).moved(
                bd.Location((b[0] - 2.0, 0.0 if big_m.rule == "crank" else big_m.kw["axis"][0],
                             0.0 if big_m.rule == "crank" else big_m.kw["axis"][1])))
        try:
            piece = big_m.rest.intersect(box)
            solids = list(piece.solids()) if hasattr(piece, "solids") else [x for p_ in piece for x in p_.solids()]
        except Exception:
            solids = [big_m.rest]
        if not solids:
            chunk_cache[key] = None            # nothing of the big body near this part
            return None
        piece = solids[0] if len(solids) == 1 else bd.Compound(children=solids)
        mv = Mover(big_m.label, piece, big_m.rule, **big_m.kw)
        chunk_cache[key] = mv
        return mv

    localized = []
    for a, b, cat in pairs:
        if a.label in big and b.label not in big:
            a = chunk_of(a, b)
        elif b.label in big and a.label not in big:
            b = chunk_of(b, a)
        if a is None or b is None:
            continue
        localized.append((a, b, cat))
    pairs = localized
    if verbose:
        print(f"[collide] {len(chunk_cache)} local chunks carved from big bodies", file=sys.stderr)
    if thetas is None:
        thetas = [k * step for k in range(int(round(720.0 / step)))]
    table = []
    offenders = {}
    t0 = time.time()
    movers_by_id = {}
    for a, b, cat in pairs:
        movers_by_id[id(a)] = a
        movers_by_id[id(b)] = b
    pair_ids = [(id(a), id(b), cat) for a, b, cat in pairs]

    def sample(theta):
        placed = {}
        boxes = {}
        for mid, m in movers_by_id.items():
            sh = m.rest if m.rule == "static" else m.at(theta)
            placed[mid] = sh
            boxes[mid] = _bbox(sh)
        counts = {}
        found = []
        for ia, ib, cat in pair_ids:
            if not _bbox_overlap(boxes[ia], boxes[ib]):
                continue
            v = clash_volume(placed[ia], placed[ib])
            if v > TOL_MM3:
                counts[cat] = counts.get(cat, 0) + 1
                found.append((theta, movers_by_id[ia].label, movers_by_id[ib].label, round(v, 3)))
            elif v < 0:
                counts["unknown(boolean failed)"] = counts.get("unknown(boolean failed)", 0) + 1
                found.append((theta, movers_by_id[ia].label, movers_by_id[ib].label, -1.0))
        return theta, counts, found

    table = []
    offenders = {}
    t0 = time.time()
    if workers > 1:
        import multiprocessing as mp
        ctx = mp.get_context("fork")
        _SAMPLE["fn"] = sample
        with ctx.Pool(workers) as pool:
            results = pool.imap_unordered(_sample_global, thetas)
            for theta, counts, found in results:
                table.append((theta, counts))
                for f in found:
                    offenders.setdefault(_cat_of(f, pairs), []).append(f)
                if verbose:
                    print(f"[collide] theta {theta:6.1f}: {counts if counts else 'clean'} ({time.time() - t0:.0f}s)", file=sys.stderr)
        table.sort()
    else:
        for theta in thetas:
            theta, counts, found = sample(theta)
            table.append((theta, counts))
            for f in found:
                offenders.setdefault(_cat_of(f, pairs), []).append(f)
            if verbose:
                print(f"[collide] theta {theta:6.1f}: {counts if counts else 'clean'} ({time.time() - t0:.0f}s)", file=sys.stderr)
    cats = sorted({c for _, _, c in pairs})
    print("theta   " + "  ".join(f"{c:>16}" for c in cats))
    for theta, counts in table:
        print(f"{theta:6.1f} " + "  ".join(f"{counts.get(c, 0):>16d}" for c in cats))
    total = sum(sum(c.values()) for _, c in table)
    print(f"TOTAL colliding pair-samples: {total}")
    for cat, lst in offenders.items():
        print(f"  {cat}: {len(lst)} e.g. {lst[:6]}")
    if out_json:
        with open(out_json, "w") as f:
            json.dump({"step": step, "table": table, "offenders": offenders}, f, indent=1)
    return total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=float, default=15.0)
    ap.add_argument("--cyl", type=str, default="")
    ap.add_argument("--unsectioned", action="store_true")
    ap.add_argument("--json", type=str, default="")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--thetas", type=str, default="", help="explicit comma list of crank angles (one shard of a sweep)")
    args = ap.parse_args()
    cyls = [int(c) for c in args.cyl.split(",")] if args.cyl else list(range(1, 17))
    ths = [float(t) for t in args.thetas.split(",")] if args.thetas else None
    total = run(args.step, not args.unsectioned, cyls, args.json or None, workers=args.workers, thetas=ths)
    sys.exit(0 if total == 0 else 1)
