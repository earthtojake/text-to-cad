"""Prove the animation clips (lib/clips.py) ARE lib/kin.py, and that their loops are seamless.

    cd src && python -m lib.animcheck [--file ../STEP/radial.step] [--step-deg 10] [--clip running|exploded-running|all]
    cd src && python -m lib.animcheck --synthetic      # one label per contract group: `running` without a build

A clip is evaluated the way the build samples it: through cadgen's own bake
model and handle (cadgen._internal.animation_bake), over the BUILT document's
names and occurrence ids (its tree in the store, found from the sidecar's
documentHash), so a label resolves to exactly the leaves the keyframes move.

(a) EQUIVALENCE. The clip at crank angles 0..720 (default 10 deg steps, 73
    samples); for every label it moved, the Python reference is
    pose_matrix(pose(theta)) . pose_matrix(pose(0))^-1 from kin.py. Every label
    the contract says moves must have a matrix, every static label must have
    none, and the max |difference| must be < 1e-6 (matrix entries, mm for
    translations). Springs: every Bezier control point of the deformed path
    against kin.spring_path(theta), and the rest path against
    kin.spring_path(0); each path must join up and stay tangent-continuous
    within the viewer's tube-runtime tolerances, or the viewer refuses it.
(b) SEAMLESS LOOP. update(0) vs update(8 s) (theta 720): per group, identical,
    or displaced by a rigid rotation that the part's symmetry must absorb
    (listed with the angle, which is expected: e.g. cam ring 90 deg on 4 lobes,
    propeller 120 deg on 3 blades).

(c) exploded-running (checked by default with running): every label is T(its
    lib/explodedrun.py group offset) . (its running motion (a)); a spring's tube
    path is (a)'s and its matrix the pure offset; exactly the layout's hidden
    labels are hidden; the seam as (b).

With a build it first reports the label contract: moving labels by kind, static
prefixes, labels that look like moving parts but will not move, and labels more
than one leaf carries.

Exit 1 when (a) or (c) fails. `check(...)` and `sample(...)` are importable
(the gate and lib/explodecheck.py call them).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

from lib import clips, kin

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_STEP = ROOT / "STEP" / "radial.step"
TOL = 1e-6
# cadgen's tube engine (cadgen._internal.tube_deformation compile_tube_path)
# refuses a path whose segments are further apart than this (mm) or whose
# tangents meet at a dot product below 1 - TUBE_TANGENT.
TUBE_GAP = 1e-5
TUBE_TANGENT = 1e-7


def python_pose(kind, args, theta):
    k = args
    if kind == "crank":
        return kin.pose_crank(theta)
    if kind == "master":
        return kin.pose_master(theta)
    if kind == "artrod":
        return kin.pose_art_rod(theta, k[0])
    if kind == "piston":
        return kin.pose_piston(theta, k[0])
    if kind == "camring":
        return kin.pose_cam_ring(theta)
    if kind == "camidler":
        return kin.pose_cam_idler(theta)
    if kind == "tappet":
        return kin.pose_tappet(theta, k[0], k[1])
    if kind == "roller":
        return kin.pose_tappet_roller(theta, k[0], k[1])
    if kind == "pushrod":
        return kin.pose_pushrod(theta, k[0], k[1])
    if kind == "rocker":
        return kin.pose_rocker(theta, k[0], k[1])
    if kind == "valve":
        return kin.pose_valve(theta, k[0], k[1])
    if kind == "planet":
        return kin.pose_planet(theta, k[0])
    if kind == "propshaft":
        return kin.pose_propshaft(theta)
    if kind == "prop":
        return kin.pose_prop(theta)
    if kind == "impeller":
        return kin.pose_impeller(theta)
    if kind == "blowergear":
        return kin.pose_blower_gear(theta, k[0])
    raise ValueError(kind)


def python_matrix(kind, args, theta):
    """Rest-relative motion: pose(theta) o pose(0)^-1 (4x4 numpy, row-major)."""
    M = np.array(kin.pose_matrix(python_pose(kind, args, theta)), dtype=float)
    M0 = np.array(kin.pose_matrix(python_pose(kind, args, 0.0)), dtype=float)
    return M @ np.linalg.inv(M0)


# ---------------------------------------------------------------------------
# A clip, sampled as the build samples it
# ---------------------------------------------------------------------------
class Document:
    """The names and occurrence ids a clip resolves against (`targets`, the
    bake's own table) and the labels its leaves carry."""

    def __init__(self, by_id, by_name):
        from cadgen._internal.animation_bake import AnimationTargets
        self.targets = AnimationTargets(by_id, by_name)
        self.labels = sorted(name for name, nodes in by_name.items() if any(by_id.get(n) == [n] for n in nodes))
        self.leaves = {label: self.targets.resolve(f"#{label}") for label in self.labels}


def built_document(step_file):
    """The built assembly as the build baked its clips: the WRITTEN document's tree."""
    from cadgen._internal.source_sidecar import _descriptor_nodes
    from cadgen.store.records import tree_for_document_hash
    from cadgen.store.trees import flatten
    sidecar = Path(f"{step_file}.json")
    if not sidecar.exists():
        raise SystemExit(f"[animcheck] {sidecar} does not exist: run `python tools/engine.py build` first")
    tree = tree_for_document_hash(json.loads(sidecar.read_text())["documentHash"])
    descriptor = flatten(tree) if tree else None
    if descriptor is None:
        raise SystemExit(f"[animcheck] the cadgen store has no tree for {Path(step_file).name}: rebuild it")
    return Document(*_descriptor_nodes(descriptor))


def synthetic_document():
    """One leaf per contract group instance: exercises every formula without geometry."""
    labels = ["crank:shaft", "master:rod", "camring:ring", "camidler:gear", "propshaft:shaft", "prop:hub",
              "impeller:wheel"]
    labels += [f"artrod{k}:rod" for k in range(2, 10)]
    labels += [f"piston{k}:piston" for k in range(1, 10)]
    labels += [f"planet{j}:gear" for j in range(1, 7)]
    labels += [f"blowergear{j}:gear" for j in range(1, 4)]
    for k in range(1, 10):
        for v in "IE":
            labels += [f"tappet{k}{v}:body", f"tappet{k}{v}:roller", f"pushrod{k}{v}:rod", f"rocker{k}{v}:arm",
                       f"valve{k}{v}:valve", f"spring{k}{v}:outer", f"spring{k}{v}:inner"]
    labels += ["crankcase:case", "heads:head_1"]
    return Document({f"s{i}": [f"s{i}"] for i in range(len(labels))},
                    {label: [f"s{i}"] for i, label in enumerate(labels)})


class _Frame:
    """One sample's effects per document leaf: what the bake's handle writes."""

    def __init__(self):
        self.transform, self.opacity, self.visible, self.tube = {}, {}, {}, {}


def _matrix(t12):
    """The bake's 12-tuple (rotation row-major, then translation) as a 4x4."""
    return np.array([[t12[0], t12[1], t12[2], t12[9]], [t12[3], t12[4], t12[5], t12[10]],
                     [t12[6], t12[7], t12[8], t12[11]], [0.0, 0.0, 0.0, 1.0]])


def sample(clip, times, doc):
    """The clip at each time (seconds, never wrapped), per label: [{"matrices": {label:
    4x4}, "tubes": {label: tube spec}, "hidden": {labels}, "split": [labels whose leaves
    moved differently]}], evaluated by the bake's own model and handle."""
    from cadgen._internal.animation_bake import Model
    update = clips.ANIMATION[clip].update
    out = []
    for t in times:
        frame = _Frame()
        update(t, Model(frame, doc.targets))
        smp = {"matrices": {}, "tubes": {}, "hidden": set(), "split": []}
        for label, leaves in doc.leaves.items():
            first = leaves[0]
            if any(frame.transform.get(i) != frame.transform.get(first) or frame.tube.get(i) != frame.tube.get(first)
                   or frame.visible.get(i) != frame.visible.get(first) for i in leaves[1:]):
                smp["split"].append(label)
            if first in frame.transform:
                smp["matrices"][label] = _matrix(frame.transform[first])
            if first in frame.tube:
                smp["tubes"][label] = frame.tube[first]
            if frame.visible.get(first) is False:
                smp["hidden"].add(label)
        out.append(smp)
    return out


def _tube_breaks(path):
    """Where a Bezier centreline does not join up or turns a corner (the viewer's tolerances)."""
    out = []
    segs = path["segments"]
    for i in range(1, len(segs)):
        a, b = np.array(segs[i - 1]["points"], dtype=float), np.array(segs[i]["points"], dtype=float)
        gap = float(np.linalg.norm(a[3] - b[0]))
        ta, tb = a[3] - a[2], b[1] - b[0]
        dot = float(ta @ tb / (np.linalg.norm(ta) * np.linalg.norm(tb)))
        if gap > TUBE_GAP or dot < 1 - TUBE_TANGENT:
            out.append(f"segment {i}: gap {gap:.2e} mm, tangent dot {dot:.9f}")
    return out


def _translation(o):
    T = np.eye(4)
    T[:3, 3] = o
    return T


def check(doc, step_deg=10.0, verbose=True, thetas=None, clip="running"):
    """Returns (ok, report dict, {theta: {label: 4x4}}) — the clip's matrices by angle.

    clip "running": every moving label's matrix is kin's pose(theta) o pose(0)^-1 and no
    static label has one. clip "exploded-running" (lib/explodedrun.py): every label's matrix
    is T(its group offset) . (that running motion), the springs' tube paths are kin's, and
    exactly the layout's hidden labels are hidden. The report's "hidden" lists them."""
    labels = doc.labels
    kinds = {lab: clips.classify(lab) for lab in labels}
    xr = clip == "exploded-running"
    offs, hidden = ({}, set())
    if xr:
        from lib import explodedrun
        offs, hidden = explodedrun.label_offsets([lab for lab in labels if ":" in lab])
    if thetas is None:
        thetas = [i * step_deg for i in range(int(round(720 / step_deg)) + 1)]
    samples = sample(clip, [th / clips.DEG_PER_S for th in thetas], doc)
    worst = (0.0, None, None)
    worst_spring = (0.0, None, None)
    problems = []
    by_theta = {}
    for theta, smp in zip(thetas, samples):
        mats, tubes = smp["matrices"], smp["tubes"]
        by_theta[theta] = mats
        problems += [f"{lab} @ {theta}: its leaves move differently" for lab in smp["split"]]
        if smp["hidden"] != hidden:
            problems.append(f"@ {theta}: hidden {len(smp['hidden'])} labels, the layout hides {len(hidden)} "
                            f"(e.g. {sorted(smp['hidden'] ^ hidden)[:3]})")
        for lab in labels:
            kind, args = kinds[lab]
            off = offs.get(lab, (0.0, 0.0, 0.0))
            T = _translation(off)
            if kind in ("static", "suspect") or (kind == "spring" and xr):
                if not any(off):
                    if lab in mats:
                        problems.append(f"{lab}: static (or unshifted) but the clip moves it")
                elif lab not in mats:
                    problems.append(f"{lab} @ {theta}: offset {off} but the clip has no matrix")
                else:
                    d = float(np.max(np.abs(mats[lab] - T)))
                    if d > worst[0]:
                        worst = (d, lab, theta)
                if kind != "spring":
                    continue
            if kind == "spring":
                if lab not in tubes:
                    problems.append(f"{lab} @ {theta}: no tube deformation")
                    continue
                k, v, which = args
                for key, th in (("path", theta), ("rest", 0.0)):
                    ref = kin.spring_path(th, k, v, which)
                    got = tubes[lab][key]
                    if len(got["segments"]) != len(ref["segments"]):
                        problems.append(f"{lab}: segment count {len(got['segments'])} != {len(ref['segments'])}")
                        continue
                    problems += [f"{lab} @ {theta} {key}: {b}" for b in _tube_breaks(got)]
                    a = np.array([s["points"] for s in got["segments"]], dtype=float)
                    b = np.array([s["points"] for s in ref["segments"]], dtype=float)
                    d = float(np.max(np.abs(a - b)))
                    d = max(d, float(np.max(np.abs(np.array(got["normal"]) - np.array(ref["normal"])))))
                    if d > worst_spring[0]:
                        worst_spring = (d, lab, theta)
                continue
            if lab not in mats:
                problems.append(f"{lab} @ {theta}: moving ({kind}) but the clip has no matrix")
                continue
            d = float(np.max(np.abs(mats[lab] - T @ python_matrix(kind, args, theta))))
            if d > worst[0]:
                worst = (d, lab, theta)
    ok = not problems and worst[0] < TOL and worst_spring[0] < TOL
    rep = {"clip": clip, "samples": len(thetas), "labels": len(labels), "hidden": sorted(hidden),
           "moving": sum(1 for k, _ in kinds.values() if k not in ("static", "suspect")),
           "max_matrix_diff": worst[0], "worst": [worst[1], worst[2]],
           "max_spring_diff": worst_spring[0], "worst_spring": [worst_spring[1], worst_spring[2]],
           "problems": problems[:50], "ok": ok}
    if verbose:
        print(f"[animcheck] {clip}: EQUIVALENCE over {len(thetas)} crank angles, {rep['moving']} moving of {len(labels)} labels"
              + (f" ({len(offs) - len([o for o in offs.values() if not any(o)])} offset, {len(hidden)} hidden)" if xr else "") + ": "
              f"max matrix diff {worst[0]:.3e} ({worst[1]} @ {worst[2]} deg), "
              f"max spring-path diff {worst_spring[0]:.3e} ({worst_spring[1]} @ {worst_spring[2]} deg) -> "
              f"{'PASS' if ok else 'FAIL'}")
        for p in problems[:20]:
            print(f"[animcheck]   {p}")
    return ok, rep, by_theta


def _rotation_of(M):
    """(angle deg, unit axis, a point on the axis) of a rigid 4x4, or None if a pure translation."""
    R, t = M[:3, :3], M[:3, 3]
    c = max(-1.0, min(1.0, (np.trace(R) - 1) / 2))
    ang = math.degrees(math.acos(c))
    if ang < 1e-7:
        return None
    ax = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    if np.linalg.norm(ax) < 1e-9:      # 180 deg
        w, V = np.linalg.eig(R)
        ax = np.real(V[:, np.argmin(np.abs(w - 1))])
    ax = ax / np.linalg.norm(ax)
    # point on the axis: solve (I - R) p = t in the plane normal to the axis
    p, *_ = np.linalg.lstsq(np.eye(3) - R, t, rcond=None)
    p = p - ax * np.dot(p, ax)
    return ang, ax, p


def seam(doc, verbose=True, clip="running"):
    s0, s1 = sample(clip, [0.0, clips.CYCLE_S], doc)
    groups = {}
    for lab in doc.labels:
        kind, args = clips.classify(lab)
        if kind in ("static", "suspect"):
            continue
        prefix = lab.split(":", 1)[0]
        g = groups.setdefault(prefix, {"kind": kind, "diff": 0.0, "motion": None})
        if kind == "spring":
            a = np.array([s["points"] for s in s0["tubes"][lab]["path"]["segments"]])
            b = np.array([s["points"] for s in s1["tubes"][lab]["path"]["segments"]])
            g["diff"] = max(g["diff"], float(np.max(np.abs(a - b))))
            continue
        M0 = s0["matrices"].get(lab, np.eye(4))
        M1 = s1["matrices"].get(lab, np.eye(4))
        D = M1 @ np.linalg.inv(M0)
        diff = float(np.max(np.abs(D - np.eye(4))))
        g["diff"] = max(g["diff"], diff)
        if diff > TOL:
            rot = _rotation_of(D)
            if kind == "planet":
                c = np.array(kin.planet_centre0(args[0]) + (1.0,))
                c1 = (D @ c)[:3]
                j2 = min(range(1, 7), key=lambda j: np.linalg.norm(np.array(kin.planet_centre0(j)) - c1))
                g["motion"] = (f"orbits onto planet{j2}'s rest station, "
                               f"{'same' if rot is None else f'{rot[0]:.1f} deg rotated'} orientation "
                               "(seamless as a set: identical planets, 18T = 120 deg symmetric)")
                continue
            g["motion"] = (f"rotated {rot[0]:.3f} deg about axis {np.round(rot[1], 6).tolist()} through "
                           f"{np.round(rot[2], 3).tolist()}" if rot else f"translated {np.round(D[:3, 3], 4).tolist()}")
    identical = sorted(p for p, g in groups.items() if g["diff"] <= TOL)
    differ = {p: g["motion"] or f"differs by {g['diff']:.3g}" for p, g in groups.items() if g["diff"] > TOL}
    if verbose:
        print(f"[animcheck] {clip}: SEAM t=0 vs t={clips.CYCLE_S:g} s: {len(identical)} groups identical: "
              f"{', '.join(identical)}")
        for p in sorted(differ):
            print(f"[animcheck]   {p}: {differ[p]}  (symmetry must absorb this)")
    return {"identical": identical, "symmetric": differ}


def contract(doc):
    """What the label contract makes of the build's labels (BUILDING.md)."""
    moving, static, suspects = {}, {}, []
    for lab in doc.labels:
        kind, args = clips.classify(lab)
        if kind == "static":
            static[lab.split(":", 1)[0]] = static.get(lab.split(":", 1)[0], 0) + 1
        elif kind == "suspect":
            suspects.append((lab, args))
        else:
            kind = "valvetrain" if kind in ("tappet", "roller", "pushrod", "rocker", "valve", "spring") else kind
            moving[kind] = moving.get(kind, 0) + 1
    print(f"[animcheck] {len(doc.labels)} leaf labels; {sum(moving.values())} moving: "
          + ", ".join(f"{k} {n}" for k, n in moving.items()))
    print("[animcheck] static prefixes: " + ", ".join(f"{k} {n}" for k, n in sorted(static.items())))
    for lab, why in suspects:
        print(f"[animcheck] WARNING {lab!r}: {why} -> NOT animated", file=sys.stderr)
    for lab, leaves in doc.leaves.items():
        if len(leaves) > 1:
            print(f"[animcheck] WARNING label {lab!r} is carried by {len(leaves)} leaves (labels must be unique; "
                  "all copies move together)", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT_STEP), help="built assembly whose clips are checked")
    ap.add_argument("--synthetic", action="store_true", help="one label per contract group instead of a build "
                                                            "(`running` only)")
    ap.add_argument("--step-deg", type=float, default=10.0)
    ap.add_argument("--clip", default="all", help="running, exploded-running, or all (both)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    if a.synthetic:
        doc, ids = synthetic_document(), ["running"]
    else:
        doc = built_document(a.file)
        contract(doc)
        ids = ["running", "exploded-running"] if a.clip == "all" else [a.clip]
    reps, all_ok = {}, True
    for clip in ids:
        ok, rep, _ = check(doc, a.step_deg, clip=clip)
        rep["seam"] = seam(doc, clip=clip)
        rep.pop("hidden", None)
        reps[clip] = rep
        all_ok = all_ok and ok
    if a.json:
        Path(a.json).write_text(json.dumps(reps if len(reps) > 1 else reps[ids[0]], indent=1))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
