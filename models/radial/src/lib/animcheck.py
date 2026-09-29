"""Prove the embedded animation IS lib/kin.py, and that its loop is seamless.

    cd src && python -m lib.animcheck [--file ../STEP/radial.step] [--step-deg 10] [--clip running|exploded-running|all]
    cd src && python -m lib.animcheck --module ../tmp/kin/anim_js_synth.py --labels ../tmp/kin/labels_synth.json

(a) EQUIVALENCE. The viewer's own runtime (lib/anim_eval.mjs) evaluates the clip
    at crank angles 0..720 (default 10 deg steps, 73 samples); for every label the
    JS moved, the Python reference is pose_matrix(pose(theta)) . pose_matrix(pose(0))^-1
    from kin.py. Every label the contract says moves must have a JS matrix, every
    static label must have none, and the max |difference| must be < 1e-6 (matrix
    entries, mm for translations). Springs: every Bezier control point of the
    deformed path against kin.spring_path(theta), and the rest path against
    kin.spring_path(0).
(b) SEAMLESS LOOP. update(0) vs update(8 s) (theta 720, unwrapped): per group,
    identical, or displaced by a rigid rotation that the part's symmetry must
    absorb (listed with the angle, which is expected: e.g. cam ring 90 deg on 4
    lobes, propeller 120 deg on 3 blades).

(c) exploded-running (checked by default with running): every label is T(its
    lib/explodedrun.py group offset) . (its running motion (a)); a spring's tube
    path is (a)'s and its matrix the pure offset; exactly the layout's hidden
    labels are hidden; the seam as (b).

Exit 1 when (a) or (c) fails. `check(...)` is importable (the gate calls it).
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

from lib import animgen, kin

HERE = Path(__file__).resolve().parent
EVAL = HERE / "anim_eval.mjs"
TOL = 1e-6


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


def js_eval(times, labels_json, module=None, raw=True, deg=False, clip="running"):
    cmd = ["node", str(EVAL), clip, ",".join(repr(float(t)) for t in times),
           str(labels_json)]
    if raw:
        cmd.append("--raw")
    if deg:
        cmd.append("--deg")
    if module:
        cmd.append(f"--module={module}")
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(f"anim_eval failed:\n{out.stderr}")
    return json.loads(out.stdout)


def colmajor(m16):
    return np.array(m16, dtype=float).reshape(4, 4).T


def _labels(labels_json):
    data = json.loads(Path(labels_json).read_text())
    return sorted({p["label"] for p in data["parts"]})


def _kinds(labels_json):
    data = json.loads(Path(labels_json).read_text())
    return {p["label"]: animgen.classify_leaf(p["label"], p.get("owner", p["label"])) for p in data["parts"]}


def _translation(o):
    T = np.eye(4)
    T[:3, 3] = o
    return T


def check(labels_json, module=None, step_deg=10.0, verbose=True, thetas=None, clip="running"):
    """Returns (ok, report dict, {theta: {label: 4x4}}) — the JS matrices by angle.

    clip "running": every moving label's matrix is kin's pose(theta) o pose(0)^-1 and no
    static label has one. clip "exploded-running" (lib/explodedrun.py): every label's matrix
    is T(its group offset) . (that running motion), the springs' tube paths are kin's, and
    exactly the layout's hidden labels are hidden. The report's "hidden" lists them."""
    labels = _labels(labels_json)
    kinds = _kinds(labels_json)
    xr = clip == "exploded-running"
    offs, hidden = ({}, set())
    if xr:
        from lib import explodedrun
        offs, hidden = explodedrun.label_offsets(labels)
    if thetas is None:
        thetas = [i * step_deg for i in range(int(round(720 / step_deg)) + 1)]
    data = js_eval(thetas, labels_json, module, raw=True, deg=True, clip=clip)
    worst = (0.0, None, None)
    worst_spring = (0.0, None, None)
    problems = []
    by_theta = {}
    for theta, sample in zip(thetas, data["samples"]):
        mats = sample["matrices"]
        defs = sample["deformations"]
        styles = sample.get("styles", {})
        by_theta[theta] = {lab: colmajor(m) for lab, m in mats.items()}
        shown_hidden = {lab for lab, st in styles.items() if st.get("visible") is False}
        if shown_hidden != hidden:
            problems.append(f"@ {theta}: hidden {len(shown_hidden)} labels, the layout hides {len(hidden)} "
                            f"(e.g. {sorted(shown_hidden ^ hidden)[:3]})")
        for lab in labels:
            kind, args = kinds[lab]
            off = offs.get(lab, (0.0, 0.0, 0.0))
            T = _translation(off)
            if kind in ("static", "suspect") or (kind == "spring" and xr):
                if not any(off):
                    if lab in mats:
                        problems.append(f"{lab}: static (or unshifted) but the JS moves it")
                elif lab not in mats:
                    problems.append(f"{lab} @ {theta}: offset {off} but the JS has no matrix")
                else:
                    d = float(np.max(np.abs(colmajor(mats[lab]) - T)))
                    if d > worst[0]:
                        worst = (d, lab, theta)
                if kind != "spring":
                    continue
            if kind == "spring":
                if lab not in defs:
                    problems.append(f"{lab} @ {theta}: no tube deformation")
                    continue
                k, v, which = args
                for key, th in (("path", theta), ("rest", 0.0)):
                    ref = kin.spring_path(th, k, v, which)
                    got = defs[lab][key]
                    if len(got["segments"]) != len(ref["segments"]):
                        problems.append(f"{lab}: segment count {len(got['segments'])} != {len(ref['segments'])}")
                        continue
                    a = np.array([s["points"] for s in got["segments"]], dtype=float)
                    b = np.array([s["points"] for s in ref["segments"]], dtype=float)
                    d = float(np.max(np.abs(a - b)))
                    d = max(d, float(np.max(np.abs(np.array(got["normal"]) - np.array(ref["normal"])))))
                    if d > worst_spring[0]:
                        worst_spring = (d, lab, theta)
                continue
            if lab not in mats:
                problems.append(f"{lab} @ {theta}: moving ({kind}) but the JS has no matrix")
                continue
            d = float(np.max(np.abs(colmajor(mats[lab]) - T @ python_matrix(kind, args, theta))))
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


def seam(labels_json, module=None, verbose=True, clip="running"):
    labels = _labels(labels_json)
    data = js_eval([0.0, 8.0], labels_json, module, raw=True, clip=clip)
    s0, s1 = data["samples"]
    groups = {}
    kinds = _kinds(labels_json)
    for lab in labels:
        kind, args = kinds[lab]
        if kind in ("static", "suspect"):
            continue
        prefix = lab.split(":", 1)[0]
        g = groups.setdefault(prefix, {"kind": kind, "diff": 0.0, "motion": None})
        if kind == "spring":
            a = np.array([s["points"] for s in s0["deformations"][lab]["path"]["segments"]])
            b = np.array([s["points"] for s in s1["deformations"][lab]["path"]["segments"]])
            g["diff"] = max(g["diff"], float(np.max(np.abs(a - b))))
            continue
        M0 = colmajor(s0["matrices"].get(lab, np.eye(4).T.ravel()))
        M1 = colmajor(s1["matrices"].get(lab, np.eye(4).T.ravel()))
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
        print(f"[animcheck] {clip}: SEAM t=0 vs t=8 s: {len(identical)} groups identical: {', '.join(identical)}")
        for p in sorted(differ):
            print(f"[animcheck]   {p}: {differ[p]}  (symmetry must absorb this)")
    return {"identical": identical, "symmetric": differ}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(animgen.DEFAULT_STEP), help="built assembly whose labels are checked")
    ap.add_argument("--labels", default=None, help="a label table instead of --file (e.g. animgen --synthetic's)")
    ap.add_argument("--module", default=None, help="generated anim_js file (default lib/anim_js.py)")
    ap.add_argument("--step-deg", type=float, default=10.0)
    ap.add_argument("--clip", default="all", help="running, exploded-running, or all (both)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    if a.labels is None:           # the CURRENT build's labels, never a stale table
        a.labels = str(animgen.ROOT / "tmp" / "kin" / f"animcheck_labels_{Path(a.file).stem}.json")
        animgen.write_labels_json(animgen.scene_labels(Path(a.file)), Path(a.labels))
    clips = ["running", "exploded-running"] if a.clip == "all" else [a.clip]
    reps, all_ok = {}, True
    for clip in clips:
        ok, rep, _ = check(a.labels, a.module, a.step_deg, clip=clip)
        if not ok and any("no matrix" in p or "no tube" in p for p in rep["problems"]):
            print("[animcheck] the module is STALE for this build: run `python -m lib.animgen` then "
                  "`python tools/engine.py build`")
        rep["seam"] = seam(a.labels, a.module, clip=clip)
        rep.pop("hidden", None)
        reps[clip] = rep
        all_ok = all_ok and ok
    if a.json:
        Path(a.json).write_text(json.dumps(reps if len(reps) > 1 else reps[clips[0]], indent=1))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
