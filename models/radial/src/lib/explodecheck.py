"""Verify the exploded view: continuous interpenetration check, floor, visibility.

    cd src && python -m lib.explodecheck [--workers 2] [--json ../tmp/kin/explodecheck.json]
                                         [--plan ../tmp/kin/explode_plan.json] [--no-visibility]

1. EQUIVALENCE: the embedded `explode` clip, evaluated by the viewer's own runtime
   (lib/anim_eval.mjs) at 1/4 s steps, equals the plan (max |translation diff|).
2. INTERPENETRATION, continuously in t. Every leaf moves by a sum of eased
   straight translations, and each eased segment is monotonic, so over a time
   interval [ta, tb] a leaf's displacement lies in a box computable exactly
   (explodeplan.offset_range). For every pair of leaves that ever moves
   relative to the other and whose clip-long swept boxes meet, [0, T] is
   subdivided adaptively:
     * CLEAR if box_a and box_b + (relative-displacement box) do not overlap;
     * CLEAR if the surfaces' distance lower bound at ta (surface samples,
       minus twice the sampling radius) exceeds the largest relative travel
       possible within the interval (distance is 1-Lipschitz in travel);
     * otherwise, once the relative travel in the interval is <= H mm, the
       pair is tested at both ends (sample penetration screen, then the exact
       OCC boolean on anything reading deeper than PEN_TOL): common volume
       > 0.5 mm^3 is a violation. An interpenetration hiding strictly between
       two clean samples H = 1 mm of travel apart would be at most 0.5 mm deep along
       the motion (below the screen's resolution) - that is the guard.
   Pairs already interpenetrating in the built model at rest are reported
   separately (baseline, a builder issue) and are not explode violations.
3. FLOOR: the lowest point over the clip (tight boxes + offsets, every 0.05 s)
   against the rest pose's lowest point (the render envelope's
   groundPlacement "lowest" puts the floor at the lowest point of the pose or,
   for a video, of the whole clip).
4. VISIBILITY at full explode from the front three-quarter camera: surface
   samples splatted into an orthographic depth buffer; a leaf with no front-most
   pixel is fully hidden.
"""

from __future__ import annotations

import argparse
import json
import os
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parent.parent
ROOT = SRC.parent
PLAN = ROOT / "tmp" / "kin" / "explode_plan.json"
STEP_FILE = ROOT / "STEP" / "radial.step"
H = 1.0                 # mm of relative travel between tested samples of a close pair
CLASH_MM3 = 0.5
CAMERA_DIR = (0.9, -1.0, 0.45)          # from the model toward the camera (front three-quarter)


def leaf_moves(plan):
    out = {}
    for name, u in plan["units"].items():
        for lab in u["leaves"]:
            out[lab] = [tuple(m) for m in u["moves"]]
    return out


def _rng(moves, ta, tb):
    from lib import explodeplan as ep
    return ep.offset_range(moves, ta, tb)


# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------
_W = {}


def _init(step_file, plan_path):
    sys.path.insert(0, str(SRC))
    import threading
    from lib import gate
    threading.Thread(target=gate._watch_parent, args=(os.getppid(),), daemon=True).start()
    from lib import explodegeo as xg
    _W["g"] = xg.Geo(step_file, refine=True)
    _W["ex"] = xg.Exact(step_file)
    _W["xg"] = xg
    plan = json.loads(Path(plan_path).read_text())
    lm = leaf_moves(plan)
    _W["moves"] = [lm[lf["label"]] for lf in _W["g"].leaves]
    _W["T"] = plan["motion"]


def _pair(task):
    """Continuous check of one leaf pair over [0, T]."""
    from lib import explodeplan as ep
    i, j = task
    t_start = time.time()
    g, ex, xg = _W["g"], _W["ex"], _W["xg"]
    mi, mj = _W["moves"][i], _W["moves"][j]
    T = _W["T"]
    bi, bj = g.box[i], g.box[j]
    pad = xg.NEAR
    out = {"pair": (i, j), "violations": [], "baseline": None, "evals": 0, "exact": 0, "intervals": 0}
    z = np.zeros(3)
    # baseline at rest
    d0 = g.depth(i, z, j, z)
    if d0 is not None and d0 > xg.PEN_TOL:
        v = ex.volume(i, z, j, z)
        out["exact"] += 1
        if v > CLASH_MM3:
            out["baseline"] = v
    cache = {}

    def test(t):
        oi, oj = ep.offset(mi, t), ep.offset(mj, t)
        rel = tuple(np.round(oj - oi, 3))
        if rel in cache:
            return cache[rel]
        out["evals"] += 1
        d = g.depth(i, oi, j, oj)
        v = 0.0
        if d is not None and d > xg.PEN_TOL:
            out["exact"] += 1
            v = ex.volume(i, oi, j, oj)
        cache[rel] = v
        return v

    stack = [(0.0, T)]
    while stack:                    # depth-first, earliest interval first
        ta, tb = stack.pop()
        out["intervals"] += 1
        li, hi_i = _rng(mi, ta, tb)
        lj, hj = _rng(mj, ta, tb)
        rlo, rhi = lj - hi_i, hj - li            # relative displacement of j w.r.t. i
        if np.any(bj[:3] + rlo > bi[3:] + pad) or np.any(bi[:3] > bj[3:] + rhi + pad):
            continue
        oi_a, oj_a = ep.offset(mi, ta), ep.offset(mj, ta)
        span = float(np.linalg.norm(rhi - rlo))
        if span <= H:
            for t in (ta, tb):
                v = test(t)
                if v > CLASH_MM3 and (out["baseline"] is None or v > out["baseline"] + CLASH_MM3):
                    out["violations"].append((round(t, 4), round(v, 2)))
            if out["violations"]:
                break               # one confirmed clash condemns the pair; the first time is what we report
            continue
        if span <= 60.0:
            gap = g.gap(i, oi_a, j, oj_a, reach=span + 5)
            if gap > span:
                continue
        tm = 0.5 * (ta + tb)
        stack.append((tm, tb))
        stack.append((ta, tm))
    out["seconds"] = round(time.time() - t_start, 2)
    return out


# ---------------------------------------------------------------------------
def candidate_pairs(g, moves, T):
    """Leaf pairs with relative motion whose clip-long swept boxes (inflated) meet."""
    from lib import explodeplan as ep
    n = g.n
    sw = np.zeros((n, 6))
    for i in range(n):
        lo, hi = ep.offset_range(moves[i], 0.0, T)
        sw[i, :3] = g.box[i, :3] + lo
        sw[i, 3:] = g.box[i, 3:] + hi
    key = [json.dumps(m) for m in moves]
    pairs = []
    pad = 3.2
    for i in range(n):
        hit = np.nonzero(np.all(sw[i + 1:, :3] <= sw[i, 3:] + pad, axis=1) & np.all(sw[i + 1:, 3:] >= sw[i, :3] - pad, axis=1))[0]
        for jj in hit:
            j = i + 1 + int(jj)
            if key[i] != key[j]:
                pairs.append((i, j))
    return pairs


def floor_check(g, moves, T):
    from lib import explodeplan as ep
    rest = float(g.box[:, 2].min())
    worst = (rest, 0.0)
    for t in np.arange(0.0, T + 1e-9, 0.05):
        z = min(g.box[i, 2] + ep.offset(moves[i], t)[2] for i in range(g.n))
        if z < worst[0]:
            worst = (z, t)
    return rest, worst


def visibility(g, moves, T, cam=CAMERA_DIR, px=2400):
    from lib import explodeplan as ep
    c = np.asarray(cam, float)
    c /= np.linalg.norm(c)
    up = np.array([0, 0, 1.0])
    x = np.cross(up, c)
    x /= np.linalg.norm(x)
    y = np.cross(c, x)
    pts, ids, dep = [], [], []
    for i in range(g.n):
        P, _ = g.world_samples(i, ep.offset(moves[i], T))
        pts.append(np.stack([P @ x, P @ y], axis=1))
        dep.append(P @ c)
        ids.append(np.full(len(P), i))
    Q, D, I = np.concatenate(pts), np.concatenate(dep), np.concatenate(ids)
    lo, hi = Q.min(0), Q.max(0)
    s = (px - 1) / max(hi - lo)
    ij = np.floor((Q - lo) * s).astype(np.int64)
    W = int(ij[:, 0].max()) + 1
    flat = ij[:, 1] * W + ij[:, 0]
    order = np.lexsort((-D, flat))                # per pixel, nearest to the camera first
    first = np.ones(len(order), bool)
    first[1:] = flat[order][1:] != flat[order][:-1]
    winners = I[order][first]
    counts = np.bincount(winners, minlength=g.n)
    return counts, 1.0 / s


def equivalence(plan, step_file, module=None, dt=0.25):
    """Max |translation difference| between the embedded explode clip (viewer runtime)
    and the plan, over t = 0, dt, ..., duration."""
    import subprocess
    from lib import animgen, explodeplan as ep
    pairs = animgen.scene_labels(Path(step_file))
    lj = ROOT / "tmp" / "kin" / "explodecheck_labels.json"
    animgen.write_labels_json(pairs, lj)
    times = [round(k * dt, 4) for k in range(int(plan["duration"] / dt) + 1)]
    cmd = ["node", str(SRC / "lib" / "anim_eval.mjs"), "explode", ",".join(f"{t:.4f}" for t in times), str(lj)]
    if module:
        cmd.append(f"--module={module}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])
    data = json.loads(r.stdout)
    lm = leaf_moves(plan)
    worst = (0.0, None, None)
    missing = 0
    for t, smp in zip(times, data["samples"]):
        mats = smp["matrices"]
        for lab, moves in lm.items():
            want = ep.offset(moves, t)
            if lab in mats:
                M = np.array(mats[lab]).reshape(4, 4).T
                got = M[:3, 3]
                if np.max(np.abs(M[:3, :3] - np.eye(3))) > 1e-9:
                    worst = max(worst, (1.0, lab, t))
            else:
                got = np.zeros(3)
                if np.any(np.abs(want) > 1e-9):
                    missing += 1
            dlt = float(np.max(np.abs(got - want)))
            if dlt > worst[0]:
                worst = (dlt, lab, t)
    return worst, missing, len(times)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(PLAN))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--json", default=str(ROOT / "tmp" / "kin" / "explodecheck.json"))
    ap.add_argument("--no-visibility", action="store_true")
    ap.add_argument("--no-equivalence", action="store_true")
    ap.add_argument("--module", default=None, help="generated animation file (default lib/anim_js.py)")
    ap.add_argument("--limit", type=int, default=0, help="check only the first N candidate pairs (debug)")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(SRC))
    from lib import explodegeo as xg
    g = xg.Geo(STEP_FILE)
    g.ensure_triangles()
    plan = json.loads(Path(a.plan).read_text())
    lm = leaf_moves(plan)
    moves = [lm[lf["label"]] for lf in g.leaves]
    T = plan["motion"]
    if not a.no_equivalence:
        (dmax, dl, dt_), missing, nt = equivalence(plan, STEP_FILE, a.module)
        print(f"[explodecheck] EQUIVALENCE embedded clip vs plan at {nt} times: max |diff| {dmax:.2e} mm "
              f"({dl} @ {dt_} s); {missing} leaf-samples missing -> {'PASS' if dmax < 1e-6 and not missing else 'FAIL'}",
              flush=True)
    t0 = time.time()
    pairs = candidate_pairs(g, moves, T)
    if a.limit:
        pairs = pairs[:a.limit]
    print(f"[explodecheck] {len(pairs)} leaf pairs move relative to each other within reach ({time.time() - t0:.0f}s)",
          flush=True)
    t0 = time.time()
    # pair results are cached on (both leaves' labels, geometry and placement, both move lists): a
    # rebuild or a changed plan re-checks only the pairs whose shape or motion changed
    import hashlib
    cache_path = ROOT / "tmp" / "kin" / "xcheck_pairs.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    need = sorted({i for p in pairs for i in p})
    psig = {}
    for i in need:
        pk = g.proto[i]
        if pk not in psig:
            psig[pk] = hashlib.sha1(np.ascontiguousarray(g._z[f"V_{pk}"]).tobytes()).hexdigest()[:16]
    gsig = {i: [psig[g.proto[i]], np.round(g.L[i], 4).tolist()] for i in need}
    def pkey(i, j):
        h = hashlib.sha1(json.dumps([g.leaves[i]["label"], gsig[i], moves[i], g.leaves[j]["label"], gsig[j], moves[j],
                                     H, CLASH_MM3, "first-clash"]).encode())
        return h.hexdigest()
    keys = {p: pkey(*p) for p in pairs}
    todo = [p for p in pairs if keys[p] not in cache]
    results = [dict(cache[keys[p]], pair=p) for p in pairs if keys[p] in cache]
    print(f"[explodecheck] {len(results)} pairs from cache, {len(todo)} to check", flush=True)
    ctx = mp.get_context("spawn")
    with ctx.Pool(a.workers, initializer=_init, initargs=(str(STEP_FILE), a.plan)) as pool:
        for k, r in enumerate(pool.imap_unordered(_pair, todo, chunksize=1)):
            results.append(r)
            cache[keys[tuple(r["pair"])]] = {kk: v for kk, v in r.items() if kk != "pair"}
            if k % 500 == 499:
                cache_path.write_text(json.dumps(cache))
            if r.get("seconds", 0) > 60:
                i, j = r["pair"]
                print(f"[explodecheck]   slow pair {g.leaves[i]['label']} x {g.leaves[j]['label']}: "
                      f"{r['seconds']}s, {r['evals']} tests, {r['exact']} exact", flush=True)
            if r["violations"]:
                i, j = r["pair"]
                print(f"[explodecheck]   VIOLATION {g.leaves[i]['label']} x {g.leaves[j]['label']}: "
                      f"{r['violations'][:4]}", flush=True)
            if k % 2000 == 1999:
                print(f"[explodecheck]   {k + 1}/{len(pairs)} pairs ({time.time() - t0:.0f}s)", flush=True)
    cache_path.write_text(json.dumps(cache))
    viol = [r for r in results if r["violations"]]
    base = [r for r in results if r["baseline"]]
    lab = lambda r: (g.leaves[r["pair"][0]]["label"], g.leaves[r["pair"][1]]["label"])
    print(f"\n[explodecheck] INTERPENETRATION over [0, {T}] s: {len(viol)} violating pairs "
          f"({sum(r['evals'] for r in results)} pose tests, {sum(r['exact'] for r in results)} exact booleans, "
          f"{sum(r['intervals'] for r in results)} intervals, {time.time() - t0:.0f}s)")
    for r in sorted(viol, key=lambda r: -max(v for _, v in r["violations"]))[:40]:
        a_, b_ = lab(r)
        print(f"   {a_} x {b_}: first at t={r['violations'][0][0]} s, worst {max(v for _, v in r['violations']):.1f} mm^3")
    if base:
        print(f"[explodecheck] baseline (already interpenetrating in the built model at rest, not the explode's): {len(base)}")
        for r in base[:20]:
            print(f"   {lab(r)[0]} x {lab(r)[1]}: {r['baseline']:.1f} mm^3")
    rest, (zmin, tz) = floor_check(g, moves, T)
    print(f"[explodecheck] FLOOR: rest lowest z {rest:.1f}; clip lowest {zmin:.1f} at t={tz:.2f} s -> "
          f"{'OK' if zmin >= rest - 0.5 else 'BELOW REST FLOOR'}")
    out = {"violations": [[*lab(r), r["violations"]] for r in viol], "baseline": [[*lab(r), r["baseline"]] for r in base],
           "pairs": len(pairs), "floor": [rest, zmin, tz]}
    if not a.no_visibility:
        counts, mm = visibility(g, moves, T)
        hidden = [g.leaves[i]["label"] for i in range(g.n) if counts[i] == 0]
        faint = [g.leaves[i]["label"] for i in range(g.n) if 0 < counts[i] < 6]
        print(f"[explodecheck] VISIBILITY at full explode ({mm:.2f} mm/px, camera {CAMERA_DIR}): "
              f"{g.n - len(hidden)}/{g.n} leaves visible; fully hidden {len(hidden)}; under 6 px {len(faint)}")
        for h in hidden[:40]:
            print(f"   hidden: {h}")
        out["hidden"] = hidden
        out["faint"] = faint
    Path(a.json).write_text(json.dumps(out, indent=1))
    ok = not viol
    print(f"[explodecheck] {'CLEAN' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
