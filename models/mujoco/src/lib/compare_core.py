"""The comparison itself: two loaded descriptions in, one JSON-ready dict of numbers out.

Nothing here trusts either description's world frame or joint zeros. The two worlds are tied by
registering the root link's shape (ICP); each joint's zero is found by turning (or sliding) THEIR
joint until their child link lies on ours, parent first, down the tree. Every later number --
axes, ranges, mass properties, gravity torques -- is taken in their world at that matched pose,
with ours carried over by the registration.
"""

from __future__ import annotations

import math
from collections import Counter

import mujoco
import numpy as np
from scipy.optimize import minimize_scalar

from lib.compare_geom import Surface, axis_rotation, line_distance, register, rms
from lib.compare_model import HINGE, Desc

CAP = 0.02  # m: closest-point distances are capped at this in the coarse scan (robust to extra parts)
CAP_FINE = 0.002  # m: and at this when refining, so geometry one side lacks cannot pull the match
COARSE_HINGE = 360  # samples over the full turn
COARSE_SLIDE = 301
COARSE_POINTS = 600
FINE_POINTS = 3000
EXACT_POINTS = 1500
GRAVITY_FLOOR = 0.05  # relative gravity errors are taken against at least 5% of the largest joint's torque


# --------------------------------------------------------------------------------------------
# 1. joint correspondence
# --------------------------------------------------------------------------------------------
def correspond(o: Desc, t: Desc) -> dict:
    on = {j.name.lower(): i for i, j in enumerate(o.joints)}
    tn = {j.name.lower(): i for i, j in enumerate(t.joints)}
    common = [n for n in on if n in tn]
    warnings = []
    if common and len(common) >= min(len(on), len(tn)) / 2:
        pairs, method = [(on[n], tn[n]) for n in common], "name"
    else:
        k = min(len(o.joints), len(t.joints))
        pairs, method = [(i, i) for i in range(k)], "chain order"
        warnings.append(f"joint names do not match ({len(common)} in common): paired by chain order")
    kept = []
    for io, it in pairs:
        if o.joints[io].type != t.joints[it].type:
            warnings.append(f"{o.joints[io].name} is a {o.joints[io].kind} in ours, "
                            f"{t.joints[it].name} a {t.joints[it].kind} in theirs: not compared")
        else:
            kept.append((io, it))
    o2t = dict(kept)
    parent_mismatch = []
    for io, it in kept:
        po, pt = o.joints[io].parent, t.joints[it].parent
        expect = o2t.get(po) if po is not None else None
        if (po is None) != (pt is None) or (po is not None and expect != pt):
            parent_mismatch.append(o.joints[io].name)
    paired_o = {io for io, _ in kept}
    paired_t = {it for _, it in kept}
    return {
        "method": method,
        "pairs": kept,
        "unmatched_ours": [j.name for i, j in enumerate(o.joints) if i not in paired_o],
        "unmatched_theirs": [j.name for i, j in enumerate(t.joints) if i not in paired_t],
        "parent_mismatch": parent_mismatch,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------------------------
# 3. pose matching
# --------------------------------------------------------------------------------------------
def _moved(pts, kind, anchor, axis, delta):
    """Our points carried by -delta about/along their joint: the same as moving their link by
    +delta, but the KD-tree over their link stays put."""
    if kind == HINGE:
        Rm = axis_rotation(axis, -delta)
        return (pts - anchor) @ Rm.T + anchor
    return pts - axis * delta


def _objective(surf: Surface, pts, kind, anchor, axis, theta0, exact=False, cap=CAP):
    def f(theta):
        d = surf.distance(_moved(pts, kind, anchor, axis, theta - theta0), exact=exact)
        return float(np.minimum(d, cap).mean())
    return f


def _hinge_repr(theta: float, rng: tuple[float, float] | None) -> float:
    """The 2-pi representative of theta nearest the joint's range (inside it if it can be)."""
    theta = math.remainder(theta, 2 * math.pi)
    if rng is None:
        return theta
    lo, hi = rng
    mid = 0.5 * (lo + hi)
    cands = [theta + 2 * math.pi * k for k in range(-2, 3)]
    return min(cands, key=lambda c: (max(lo - c, 0.0, c - hi), abs(c - mid)))


def match_joint(surf: Surface, ours_pts: np.ndarray, kind: int, anchor, axis, theta0: float,
                rng: tuple[float, float] | None) -> dict:
    """THEIR joint value that puts their child link on ours: a coarse scan, the best three local
    minima refined on the samples, the winner refined on the exact surface."""
    coarse = _objective(surf, ours_pts[:COARSE_POINTS], kind, anchor, axis, theta0)
    if kind == HINGE:
        grid = np.linspace(-math.pi, math.pi, COARSE_HINGE, endpoint=False)
        step = grid[1] - grid[0]
        vals = np.array([coarse(x) for x in grid])
        is_min = (vals <= np.roll(vals, 1)) & (vals <= np.roll(vals, -1))
        sep = math.radians(10)
    else:
        lo, hi = rng if rng is not None else (-0.1, 0.1)
        w = max(hi - lo, 0.01)
        grid = np.linspace(lo - w, hi + w, COARSE_SLIDE)
        step = grid[1] - grid[0]
        vals = np.array([coarse(x) for x in grid])
        is_min = np.r_[True, (vals[1:-1] <= vals[:-2]) & (vals[1:-1] <= vals[2:]), True]
        sep = 0.2 * w
    order = [int(i) for i in np.argsort(vals) if is_min[i]]
    seeds: list[float] = []
    for i in order:
        if all(abs(math.remainder(grid[i] - s, 2 * math.pi) if kind == HINGE else grid[i] - s) > sep
               for s in seeds):
            seeds.append(float(grid[i]))
        if len(seeds) == 3:
            break
    fine = _objective(surf, ours_pts[:FINE_POINTS], kind, anchor, axis, theta0)
    refined = []
    for s in seeds:
        r = minimize_scalar(fine, bounds=(s - 1.5 * step, s + 1.5 * step), method="bounded",
                            options={"xatol": 1e-7})
        refined.append((float(r.fun), float(r.x)))
    refined.sort()
    best_f, best = refined[0]
    span = math.radians(0.5) if kind == HINGE else 0.5 * step
    robust = _objective(surf, ours_pts[:FINE_POINTS], kind, anchor, axis, theta0, cap=CAP_FINE)
    best = float(minimize_scalar(robust, bounds=(best - span, best + span), method="bounded",
                                 options={"xatol": 1e-8}).x)
    span = math.radians(0.1) if kind == HINGE else 0.1 * step
    exact = _objective(surf, ours_pts[:EXACT_POINTS], kind, anchor, axis, theta0, exact=True, cap=CAP_FINE)
    r = minimize_scalar(exact, bounds=(best - span, best + span), method="bounded", options={"xatol": 1e-8})
    best = float(r.x)
    alt = refined[1] if len(refined) > 1 else None
    out = {"value": _hinge_repr(best, rng) if kind == HINGE else best, "score_mm": float(r.fun) * 1e3}
    if alt is not None:
        out["alt_value"] = _hinge_repr(alt[1], rng) if kind == HINGE else alt[1]
        out["alt_score_mm"] = alt[0] * 1e3
        out["ambiguous"] = bool(alt[0] <= 1.25 * best_f + 2e-4)
    else:
        out["ambiguous"] = False
    return out


# --------------------------------------------------------------------------------------------
# 5. mass properties
# --------------------------------------------------------------------------------------------
def _mass_cmp(mo, co, Io, mt, ct, It, R, t) -> dict:
    if mo > 0:
        co = R @ co + t
        Io = R @ Io @ R.T
    out = {"mass_ours_kg": mo, "mass_theirs_kg": mt,
           "mass_diff_pct": 100 * (mo - mt) / mt if mt > 0 else None}
    if mo > 0 and mt > 0:
        out["com_dist_mm"] = float(np.linalg.norm(co - ct)) * 1e3
        out["principal_ours_kgm2"] = np.sort(np.linalg.eigvalsh(Io)).tolist()
        out["principal_theirs_kgm2"] = np.sort(np.linalg.eigvalsh(It)).tolist()
        n = np.linalg.norm(It)
        out["inertia_rel_diff_pct"] = 100 * float(np.linalg.norm(Io - It) / n) if n > 0 else None
    return out


# --------------------------------------------------------------------------------------------
# 6. gravity torques
# --------------------------------------------------------------------------------------------
def gravity(o: Desc, t: Desc, pairs, joints_out, base_values: dict[int, float], R, n: int,
            seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    g_saved = o.model.opt.gravity.copy()
    o.model.opt.gravity[:] = R.T @ t.model.opt.gravity  # their gravity, in our world
    intervals = []
    notes = []
    for (io, it), jr in zip(pairs, joints_out):
        jo, jt = o.joints[io], t.joints[it]
        off, s = jr["offset"], jr["sign"]
        default = (-math.pi, math.pi) if jo.type == HINGE else (-0.02, 0.02)
        ro = jo.range or default
        if jt.range is not None:
            a, b = sorted(((jt.range[0] - off) / s, (jt.range[1] - off) / s))
        else:
            a, b = default
        lo, hi = max(ro[0], a), min(ro[1], b)
        if hi < lo:
            notes.append(f"{jo.name}: ranges do not overlap; sampled at our zero")
            lo = hi = 0.0
        intervals.append((lo, hi))
    tau_o, tau_t = [], []
    for _ in range(n):
        qo = [rng.uniform(lo, hi) for lo, hi in intervals]
        o.zero()
        o.data.qpos[[o.joints[io].qpos for io, _ in pairs]] = qo
        tv = dict(base_values)
        for (io, it), jr, q in zip(pairs, joints_out, qo):
            tv[it] = jr["offset"] + jr["sign"] * q
        t.zero()
        for i, v in tv.items():
            t.data.qpos[t.joints[i].qpos] = v
        for d in (o, t):
            d.data.qvel[:] = 0
            mujoco.mj_forward(d.model, d.data)
        tau_o.append([o.data.qfrc_bias[o.joints[io].dof] for io, _ in pairs])
        tau_t.append([jr["sign"] * t.data.qfrc_bias[t.joints[it].dof] for (io, it), jr in zip(pairs, joints_out)])
    o.model.opt.gravity[:] = g_saved
    o.zero()
    t.zero()
    To, Tt = np.array(tau_o), np.array(tau_t)
    err = To - Tt
    per = []
    # a joint's error is relative to its own RMS torque, floored at FLOOR of the largest joint's
    # (same unit): a vertical axis carries next to no gravity torque, and a ratio to ~0 says nothing
    rms_ref = {}
    for k, (io, _) in enumerate(pairs):
        rms_ref.setdefault(o.joints[io].type, []).append(rms(Tt[:, k]))
    for k, (io, it) in enumerate(pairs):
        e, ref = err[:, k], Tt[:, k]
        rr = rms(ref)
        scale = max(rr, GRAVITY_FLOOR * max(rms_ref[o.joints[io].type]))
        mscale = max(float(np.abs(ref).max()), scale)
        per.append({"joint": o.joints[io].name, "unit": "N·m" if o.joints[io].type == HINGE else "N",
                    "theirs_rms": rr, "err_rms": rms(e), "err_max": float(np.abs(e).max()),
                    "rel_rms_pct": 100 * rms(e) / scale if scale > 1e-12 else None,
                    "rel_max_pct": 100 * float(np.abs(e).max()) / mscale if mscale > 1e-12 else None,
                    "floored": bool(scale > rr),
                    "sample_range": list(intervals[k])})
    tot = float(np.sqrt((Tt ** 2).sum()))
    rel_max = [p["rel_max_pct"] for p in per if p["rel_max_pct"] is not None]
    return {"configs": n, "per_joint": per,
            "rel_rms_pct": 100 * float(np.sqrt((err ** 2).sum())) / tot if tot > 0 else None,
            "rel_max_pct": max(rel_max) if rel_max else None, "notes": notes,
            "gravity_note": "Our gravity is set to theirs, rotated into our world by the base registration"}


# --------------------------------------------------------------------------------------------
# 7. collision and the consumer's own
# --------------------------------------------------------------------------------------------
def _enum(e, v, prefix):
    try:
        return e(int(v)).name.removeprefix(prefix).lower()
    except ValueError:
        return str(int(v))


def consumer(d: Desc) -> dict:
    m = d.model
    coll = [g for g in range(m.ngeom) if (m.geom_contype[g] or m.geom_conaffinity[g]) or m.geom_group[g] == 3]
    by_type = Counter(_enum(mujoco.mjtGeom, m.geom_type[g], "mjGEOM_") for g in coll)
    params = Counter()
    for g in coll:
        params[(int(m.geom_condim[g]), tuple(np.round(m.geom_friction[g], 6)), tuple(np.round(m.geom_solref[g], 6)),
                tuple(np.round(m.geom_solimp[g], 6)), int(m.geom_priority[g]))] += 1
    contact = [{"count": c, "condim": k[0], "friction": list(k[1]), "solref": list(k[2]), "solimp": list(k[3]),
                "priority": k[4]} for k, c in params.most_common()]
    acts = []
    for a in range(m.nu):
        trn = int(m.actuator_trntype[a])
        target = (m.joint(int(m.actuator_trnid[a, 0])).name
                  if trn == int(mujoco.mjtTrn.mjTRN_JOINT) else _enum(mujoco.mjtTrn, trn, "mjTRN_"))
        gain = float(m.actuator_gainprm[a, 0])
        b1, b2 = float(m.actuator_biasprm[a, 1]), float(m.actuator_biasprm[a, 2])
        bt = int(m.actuator_biastype[a])
        if bt == int(mujoco.mjtBias.mjBIAS_AFFINE) and abs(b1 + gain) <= 1e-9 * max(1.0, abs(gain)):
            kind, gains = "position", {"kp": gain, "kv": -b2}
        elif bt == int(mujoco.mjtBias.mjBIAS_AFFINE) and b1 == 0 and abs(b2 + gain) <= 1e-9 * max(1.0, abs(gain)):
            kind, gains = "velocity", {"kv": gain}
        elif bt == int(mujoco.mjtBias.mjBIAS_NONE):
            kind, gains = "motor", {"gear": float(m.actuator_gear[a, 0])}
        else:
            kind, gains = "general", {"gainprm": m.actuator_gainprm[a, :3].tolist(),
                                      "biasprm": m.actuator_biasprm[a, :3].tolist()}
        acts.append({"name": m.actuator(a).name, "joint": target, "type": kind, **gains,
                     "ctrlrange": m.actuator_ctrlrange[a].tolist() if m.actuator_ctrllimited[a] else None,
                     "forcerange": m.actuator_forcerange[a].tolist() if m.actuator_forcelimited[a] else None})
    dyn = {j.name: {"armature": float(m.dof_armature[j.dof]), "damping": float(m.dof_damping[j.dof]),
                    "frictionloss": float(m.dof_frictionloss[j.dof]), "stiffness": float(m.jnt_stiffness[j.id])}
           for j in d.joints}
    eqs = []
    for e in range(m.neq):
        et = int(m.eq_type[e])
        names = (lambda i: m.joint(i).name) if et == int(mujoco.mjtEq.mjEQ_JOINT) else (lambda i: m.body(i).name)
        if et in (int(mujoco.mjtEq.mjEQ_JOINT), int(mujoco.mjtEq.mjEQ_CONNECT), int(mujoco.mjtEq.mjEQ_WELD)):
            objs = [names(int(m.eq_obj1id[e])), names(int(m.eq_obj2id[e])) if m.eq_obj2id[e] >= 0 else "world"]
        else:
            objs = [int(m.eq_obj1id[e]), int(m.eq_obj2id[e])]
        eqs.append({"type": _enum(mujoco.mjtEq, et, "mjEQ_"), "objects": objs,
                    "data": np.round(m.eq_data[e, :5], 6).tolist()})
    excl = [[m.body(int(s >> 16)).name, m.body(int(s & 0xFFFF)).name] for s in m.exclude_signature]
    return {
        "collision_geoms": len(coll), "collision_by_type": dict(by_type.most_common()),
        "contact_params": contact,
        "actuators": acts,
        "joint_dynamics": dyn,
        "equalities": eqs,
        "option": {"integrator": _enum(mujoco.mjtIntegrator, m.opt.integrator, "mjINT_"),
                   "cone": _enum(mujoco.mjtCone, m.opt.cone, "mjCONE_"),
                   "impratio": float(m.opt.impratio), "timestep": float(m.opt.timestep),
                   "iterations": int(m.opt.iterations)},
        "keyframes": [m.key(k).name or f"#{k}" for k in range(m.nkey)],
        "excludes": excl, "contact_pairs": int(m.npair),
        "cameras": int(m.ncam), "sensors": int(m.nsensor), "tendons": int(m.ntendon),
    }


# --------------------------------------------------------------------------------------------
# the whole comparison
# --------------------------------------------------------------------------------------------
def compare(o: Desc, t: Desc, configs: int = 20) -> dict:
    corr = correspond(o, t)
    warnings = [f"ours: {w}" for w in o.warnings] + [f"theirs: {w}" for w in t.warnings] + corr["warnings"]
    o.zero()
    t.zero()

    # 2. base alignment
    so, st = o.link_surface(-1), t.link_surface(-1)
    if len(so) == 0 or len(st) == 0:
        warnings.append("a root link has no geometry: worlds taken as the same (no registration)")
        R, tv = np.eye(3), np.zeros(3)
        base = {"rms_mm": None}
    else:
        base = register(so, st)
        R, tv = base.pop("R"), base.pop("t")
        ext_o, ext_t = np.ptp(so.samples, 0).max(), np.ptp(st.samples, 0).max()
        if not 0.5 < ext_o / ext_t < 2:
            warnings.append(f"root link sizes differ {ext_o / ext_t:.3g}x: a unit mismatch?")
    base["ours_link"], base["theirs_link"] = o.link_name(-1), t.link_name(-1)
    base["ours_rule"], base["theirs_rule"] = o.link_geoms(-1)[1], t.link_geoms(-1)[1]
    if base.get("alt_score_mm") is not None:
        base["ambiguous"] = bool(base["alt_score_mm"] <= 1.25 * base["score_mm"] + 0.05)
        if base["ambiguous"]:
            warnings.append(f"base registration is ambiguous: a solution {base['alt_rotation_from_best_deg']:.0f} deg "
                            f"away fits about as well ({base['alt_rms_mm']:.2f} vs {base['rms_mm']:.2f} mm)")

    # 3. pose matching, down their tree
    ours_surf = {io: o.link_surface(io, R, tv) for io, _ in corr["pairs"]}
    t2o = {it: io for io, it in corr["pairs"]}
    values: dict[int, float] = {}
    matches: dict[int, dict] = {}
    for it, jt in enumerate(t.joints):
        io = t2o.get(it)
        if io is None:
            continue
        t.zero()
        t.set(values)
        surf = t.link_surface(it)
        if len(surf) == 0 or len(ours_surf[io]) == 0:
            warnings.append(f"{jt.name}: a child link has no geometry; its zero is not matched (taken as 0)")
            matches[it] = {"value": 0.0, "score_mm": None, "ambiguous": None}
            values[it] = 0.0
            continue
        anchor, axis = t.joint_world(it)
        theta0 = float(t.data.qpos[jt.qpos])
        mt = match_joint(surf, ours_surf[io].samples, jt.type, anchor, axis, theta0, jt.range)
        matches[it] = mt
        values[it] = mt["value"]
        if mt["ambiguous"]:
            warnings.append(f"{jt.name}: pose match is ambiguous: their value "
                            f"{_fmt_val(mt['alt_value'], jt.type)} fits nearly as well as "
                            f"{_fmt_val(mt['value'], jt.type)}")

    # the matched pose: everything below is measured here
    t.zero()
    t.set(values)
    o.zero()
    joints_out = []
    for io, it in corr["pairs"]:
        jo, jt = o.joints[io], t.joints[it]
        scale = 180 / math.pi if jo.type == HINGE else 1e3
        unit = "deg" if jo.type == HINGE else "mm"
        co, ao = o.joint_world(io)
        co, ao = R @ co + tv, R @ ao
        ct, at = t.joint_world(it)
        dot = float(np.dot(ao, at))
        sign = 1.0 if dot >= 0 else -1.0
        mt = matches[it]
        theirs_surf = t.link_surface(it)
        ours_s = ours_surf[io]
        res = {}
        if len(theirs_surf) and len(ours_s):
            d1 = theirs_surf.distance(ours_s.query_points())
            d2 = ours_s.distance(theirs_surf.query_points())
            res = {"resid_ours_to_theirs_rms_mm": rms(d1) * 1e3,
                   "resid_ours_to_theirs_median_mm": float(np.median(d1)) * 1e3,
                   "within_1mm_pct": 100 * float((d1 <= 1e-3).mean()),
                   "resid_theirs_to_ours_rms_mm": rms(d2) * 1e3,
                   "within_1mm_back_pct": 100 * float((d2 <= 1e-3).mean())}
        jr = {"joint": jo.name, "theirs_joint": jt.name, "type": jo.kind, "unit": unit,
              "ours_link": o.link_name(io), "theirs_link": t.link_name(it),
              "ours_rule": o.link_geoms(io)[1], "theirs_rule": t.link_geoms(it)[1],
              "offset": mt["value"], "offset_display": mt["value"] * scale, "sign": sign,
              "ambiguous": mt["ambiguous"], "match_score_mm": mt["score_mm"],
              "axis_angle_deg": math.degrees(math.acos(min(1.0, abs(dot)))),
              "axis_offset_mm": line_distance(co, ao, ct, at) * 1e3 if jo.type == HINGE else None,
              **res}
        # 4. ranges, ours carried into their coordinate
        if jo.range is not None and jt.range is not None:
            a, b = sorted((jr["offset"] + sign * jo.range[0], jr["offset"] + sign * jo.range[1]))
            lo_t, hi_t = jt.range
            inter = max(0.0, min(b, hi_t) - max(a, lo_t))
            union = max(b, hi_t) - min(a, lo_t)
            jr["range"] = {"ours_mapped": [a * scale, b * scale], "theirs": [lo_t * scale, hi_t * scale],
                           "d_lo": (a - lo_t) * scale, "d_hi": (b - hi_t) * scale,
                           "overlap_pct": 100 * inter / union if union > 0 else None}
        else:
            jr["range"] = {"ours_mapped": None if jo.range is None else
                           sorted([(jr["offset"] + sign * x) * scale for x in jo.range]),
                           "theirs": None if jt.range is None else [x * scale for x in jt.range],
                           "note": "unlimited on " + ("both sides" if jo.range is None and jt.range is None
                                                      else "ours" if jo.range is None else "theirs")}
        jr["mass"] = _mass_cmp(*o.link_mass(io), *t.link_mass(it), R, tv)
        joints_out.append(jr)

    root_mass = _mass_cmp(*o.link_mass(-1), *t.link_mass(-1), R, tv)
    total = _mass_cmp(*o.bodies_mass(list(range(1, o.model.nbody))),
                      *t.bodies_mass(list(range(1, t.model.nbody))), R, tv)
    unpaired = {it: 0.0 for it in range(len(t.joints)) if it not in t2o}
    grav = gravity(o, t, corr["pairs"], joints_out, unpaired, R, configs) if corr["pairs"] else None

    result = {
        "ours": _summary(o), "theirs": _summary(t),
        "correspondence": {k: v for k, v in corr.items() if k != "pairs"} | {
            "pairs": [[o.joints[io].name, t.joints[it].name] for io, it in corr["pairs"]]},
        "base": base | {"R": R.tolist(), "t_m": tv.tolist()},
        "joints": joints_out,
        "root_mass": root_mass, "total_mass": total,
        "gravity": grav,
        "consumer": {"ours": consumer(o), "theirs": consumer(t)},
        "warnings": warnings,
    }
    result["verdict"] = verdict(result)
    return result


def _summary(d: Desc) -> dict:
    m = d.model
    return {"path": str(d.path), "kind": d.kind, "bodies": int(m.nbody - 1), "geoms": int(m.ngeom),
            "joints": [{"name": j.name, "type": j.kind} for j in d.joints],
            "links": int(len(d.joints) + 1), "visual_rule": d.visual_rule}


def _fmt_val(v: float, kind: int) -> str:
    return f"{math.degrees(v):.1f} deg" if kind == HINGE else f"{v * 1e3:.1f} mm"


# --------------------------------------------------------------------------------------------
# 8. verdict
# --------------------------------------------------------------------------------------------
def verdict(r: dict) -> dict:
    c = r["correspondence"]
    J = r["joints"]
    n_o, n_t = len(r["ours"]["joints"]), len(r["theirs"]["joints"])
    topo_ok = not c["unmatched_ours"] and not c["unmatched_theirs"] and not c["parent_mismatch"] and n_o == n_t

    def mx(key, rows=J):
        v = [x[key] for x in rows if x.get(key) is not None]
        return max(v) if v else None

    massrows = [j["mass"] for j in J] + [r["root_mass"]]
    mass_pcts = [abs(m["mass_diff_pct"]) for m in massrows if m.get("mass_diff_pct") is not None]
    g = r["gravity"] or {}
    out = {
        "topology": ("match" if topo_ok else "differs") + f" ({len(c['pairs'])} of {n_o} ours / {n_t} theirs "
                                                          f"joints paired by {c['method']})",
        "topology_ok": topo_ok,
        "max_axis_angle_deg": mx("axis_angle_deg"),
        "max_axis_offset_mm": mx("axis_offset_mm"),
        "base_rms_mm": r["base"].get("rms_mm"),
        "max_link_resid_mm": mx("resid_ours_to_theirs_rms_mm"),
        "max_link_resid_back_mm": mx("resid_theirs_to_ours_rms_mm"),
        "total_mass_diff_pct": r["total_mass"].get("mass_diff_pct"),
        "max_link_mass_diff_pct": max(mass_pcts) if mass_pcts else None,
        "max_com_dist_mm": max([m["com_dist_mm"] for m in massrows if m.get("com_dist_mm") is not None], default=None),
        "gravity_rel_rms_pct": g.get("rel_rms_pct"),
        "gravity_rel_max_pct": g.get("rel_max_pct"),
        "max_abs_offset": max(J, key=lambda j: abs(j["offset_display"]) if j["type"] == "hinge" else 0,
                              default=None),
    }
    if out["max_abs_offset"] is not None:
        j = out["max_abs_offset"]
        out["max_abs_offset"] = {"joint": j["joint"], "value": j["offset_display"], "unit": j["unit"]}
    out["discrepancies"] = _ranked(r)
    return out


def _ranked(r: dict, top: int = 8) -> list[dict]:
    items = []
    add = lambda score, text: items.append({"score": float(score), "text": text})
    c = r["correspondence"]
    for n in c["unmatched_ours"]:
        add(10, f"joint {n} only in ours")
    for n in c["unmatched_theirs"]:
        add(10, f"joint {n} only in theirs")
    for n in c["parent_mismatch"]:
        add(10, f"joint {n} hangs from a different parent joint")
    b = r["base"]
    if b.get("rms_mm") is not None:
        add(b["rms_mm"] / 1.0, f"root link shape: ICP residual {b['rms_mm']:.2f} mm")
    for j in r["joints"]:
        n = j["joint"]
        add(j["axis_angle_deg"] / 1.0, f"{n}: axis {j['axis_angle_deg']:.2f} deg off")
        if j.get("axis_offset_mm") is not None:
            add(j["axis_offset_mm"] / 1.0, f"{n}: axis line {j['axis_offset_mm']:.2f} mm off")
        if j.get("resid_ours_to_theirs_rms_mm") is not None:
            a, bk = j["resid_ours_to_theirs_rms_mm"], j["resid_theirs_to_ours_rms_mm"]
            add(max(a, bk) / 1.0, f"{n} link shape: residual {a:.2f} mm ours→theirs, {bk:.2f} mm theirs→ours")
        if j.get("ambiguous"):
            add(3, f"{n}: zero match ambiguous (near-symmetric link)")
        rg = j["range"]
        if rg.get("d_lo") is not None:
            s = 5.0 if j["type"] == "hinge" else 2.0
            worst = max(abs(rg["d_lo"]), abs(rg["d_hi"]))
            add(worst / s, f"{n}: range ends differ by {rg['d_lo']:+.1f} / {rg['d_hi']:+.1f} {j['unit']}")
        m = j["mass"]
        if m.get("mass_diff_pct") is not None:
            add(abs(m["mass_diff_pct"]) / 5, f"{n} link mass {m['mass_diff_pct']:+.1f}% "
                                           f"({m['mass_ours_kg'] * 1e3:.1f} vs {m['mass_theirs_kg'] * 1e3:.1f} g)")
        if m.get("com_dist_mm") is not None:
            add(m["com_dist_mm"] / 5, f"{n} link COM {m['com_dist_mm']:.1f} mm apart")
        if m.get("inertia_rel_diff_pct") is not None:
            add(m["inertia_rel_diff_pct"] / 25, f"{n} link inertia differs {m['inertia_rel_diff_pct']:.0f}% (Frobenius)")
    rm = r["root_mass"]
    if rm.get("mass_diff_pct") is not None:
        add(abs(rm["mass_diff_pct"]) / 5, f"root link mass {rm['mass_diff_pct']:+.1f}%")
    g = r["gravity"]
    if g:
        for p in g["per_joint"]:
            if p["rel_rms_pct"] is not None:
                add(p["rel_rms_pct"] / 5, f"{p['joint']}: gravity torque error {p['rel_rms_pct']:.1f}% RMS "
                                          f"({p['err_rms']:.3g} {p['unit']})")
    items.sort(key=lambda x: -x["score"])
    return [x for x in items if x["score"] >= 1][:top]
