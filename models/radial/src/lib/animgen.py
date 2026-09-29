"""Generate the embedded viewer animation (`lib/anim_js.py`) from lib/kin.py.

    cd src && python -m lib.animgen [--step ../STEP/radial.step] [--synthetic]

The render module cannot import Python, so this re-describes every motion in
JavaScript with every number from spec.py / kin.py baked in as a literal. The
motion laws are transcribed operation-for-operation from kin.py (same Newton
solve for the rockers, same floored modulo, same Rodrigues matrix), and
`lib.animcheck` proves the two agree to < 1e-6 at 73 crank angles.

Which parts move is decided by LABEL (BUILDING.md, "Moving parts: labels are
the contract"): every leaf label `<prefix>:<part>` whose prefix is a motion
group gets that group's pose. The label list comes from the BUILT assembly
(read_scene over STEP/radial.step), so the module only ever names labels that
exist; at run time it additionally skips any baked label the viewer's model
does not carry (`m.labels()`), so a stale module can never throw while a
builder renames a part. Rerun this after systems land, then
`python tools/engine.py build` (an annotation change).

Clip `running`: one full 720 deg four-stroke cycle in 8 s, theta = 90 t deg.
Clip `exploded-running`: the same cycle (the same `runAt`), with every part's
constant exploded offset from lib/explodedrun.py composed on top; some systems
are hidden. Clip `explode`: the teardown planned by lib/explodeplan.py.
Valvetrain parts are authored at zero lift and placed with their theta = 0
pose, so their motion is pose(theta) o pose(0)^-1; crank-train parts are
authored at theta = 0 where their pose is the identity. The valve springs are
tube deformations: rest = kin.spring_path(0), path = kin.spring_path(theta).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from lib import kin, spec as S

SRC = Path(__file__).resolve().parent.parent
ROOT = SRC.parent
OUT = Path(__file__).resolve().parent / "anim_js.py"
DEFAULT_STEP = ROOT / "STEP" / "radial.step"
LABELS_JSON = ROOT / "tmp" / "kin" / "labels.json"

CYCLE_S = 8.0                  # one 720 deg cycle
DEG_PER_S = 720.0 / CYCLE_S    # theta = 90 t
SPRING_MAX_SEGMENT = 2.0       # deformTube maxSegmentLength (mm)

SYSTEM_NAMES = {
    "crankcase", "crankshaft", "rods", "pistons", "barrels", "heads", "valvetrain", "cam",
    "pushrods", "nose", "reduction", "propeller", "blower", "intake", "accessory", "ignition",
    "exhaust", "mount",
}

# ---------------------------------------------------------------------------
# The label contract (BUILDING.md). prefix regex -> motion kind
# ---------------------------------------------------------------------------
_CONTRACT = [
    ("crank", re.compile(r"crank")),
    ("master", re.compile(r"master")),
    ("artrod", re.compile(r"artrod([2-9])")),
    ("piston", re.compile(r"piston([1-9])")),
    ("camring", re.compile(r"camring")),
    ("camidler", re.compile(r"camidler")),
    ("tappet", re.compile(r"tappet([1-9])([IE])")),
    ("pushrod", re.compile(r"pushrod([1-9])([IE])")),
    ("rocker", re.compile(r"rocker([1-9])([IE])")),
    ("valve", re.compile(r"valve([1-9])([IE])")),
    ("spring", re.compile(r"spring([1-9])([IE])")),
    ("planet", re.compile(r"planet([1-6])")),
    ("propshaft", re.compile(r"propshaft")),
    ("prop", re.compile(r"prop")),
    ("impeller", re.compile(r"impeller")),
    ("blowergear", re.compile(r"blowergear([1-3])")),
]
_MOTION_STEM = re.compile(r"^(crank|master|art|conrod|rod\d|piston|cam|idler|tappet|lifter|follower|push|rocker|"
                          r"valve|spring|planet|carrier|prop|impel|blowergear|intermediate)", re.I)
SPRING_PARTS = ("outer", "inner")


def classify(label: str):
    """(kind, args) for a moving label, ("static", None) for a static one, or
    ("suspect", reason) when the label breaks the contract in a way that looks
    like a moving part that will NOT move."""
    if ":" not in label:
        return ("suspect", "no '<group>:' prefix")
    prefix, part = label.split(":", 1)
    for kind, rx in _CONTRACT:
        mt = rx.fullmatch(prefix)
        if not mt:
            continue
        args = mt.groups()
        if kind in ("artrod", "piston", "planet", "blowergear"):
            return (kind, (int(args[0]),))
        if kind in ("tappet", "pushrod", "rocker", "valve", "spring"):
            k, v = int(args[0]), args[1]
            if kind == "tappet" and part == "roller":
                return ("roller", (k, v))
            if kind == "spring":
                if part not in SPRING_PARTS:
                    return ("suspect", f"spring part must be one of {SPRING_PARTS} (tube deformation)")
                return ("spring", (k, v, part))
            return (kind, (k, v))
        return (kind, ())
    if prefix in SYSTEM_NAMES:
        return ("static", None)
    if _MOTION_STEM.match(prefix):
        return ("suspect", "prefix looks like a motion group but matches no contract group")
    return ("static", None)


# ---------------------------------------------------------------------------
# Labels from the built assembly
# ---------------------------------------------------------------------------
def leaf_records(scene):
    """One dict per geometry leaf: ref, label, owner (the leaf's own label, or for an
    unlabelled child of a nested compound the nearest '<group>:' ancestor label),
    system (the assembly's second-level occurrence label)."""
    out = []

    def walk(o, owner, system, depth):
        lab = o.label or ""
        if ":" in lab:
            owner = lab
        if depth == 1:
            system = lab
        if o._node.prototype_key is not None:
            out.append({"ref": o.ref, "label": lab, "owner": owner, "system": system or "?"})
        for c in o.children:
            walk(c, owner, system, depth + 1)

    for r in scene.roots:
        walk(r, "", "", 0)
    return out


def scene_labels(step_path: Path):
    """[(occurrence ref, label, owner)] for every geometry leaf of the built document."""
    from cadgen import read_scene
    return [(r["ref"], r["label"], r["owner"]) for r in leaf_records(read_scene(step_path))]


def classify_leaf(label: str, owner: str):
    """classify() for a leaf; an unlabelled child of a nested compound inherits its owner's
    kind if static, and is flagged when the owner should move (it cannot be targeted)."""
    if ":" in label or not owner:
        return classify(label)
    kind, args = classify(owner)
    if kind in ("static", "suspect"):
        return ("static", None)
    return ("suspect", f"child of the MOVING nested compound {owner!r}: an unlabelled leaf cannot be "
                       "animated by label - make every moving leaf a flat, labelled solid")


def synthetic_labels():
    """One label per contract group instance: exercises every formula without geometry."""
    out = ["crank:shaft", "master:rod", "camring:ring", "camidler:gear", "propshaft:shaft", "prop:hub",
           "impeller:wheel"]
    out += [f"artrod{k}:rod" for k in range(2, 10)]
    out += [f"piston{k}:piston" for k in range(1, 10)]
    out += [f"planet{j}:gear" for j in range(1, 7)]
    out += [f"blowergear{j}:gear" for j in range(1, 4)]
    for k in range(1, 10):
        for v in "IE":
            out += [f"tappet{k}{v}:body", f"tappet{k}{v}:roller", f"pushrod{k}{v}:rod", f"rocker{k}{v}:arm",
                    f"valve{k}{v}:valve", f"spring{k}{v}:outer", f"spring{k}{v}:inner"]
    out += ["crankcase:case", "heads:head_1"]
    return [(f"#s{i}", lab, lab) for i, lab in enumerate(out)]


def group_labels(pairs):
    """Bucket labels by motion group; returns (groups dict for the JS, report dict)."""
    g = {"crank": [], "master": [], "camring": [], "camidler": [], "propshaft": [], "prop": [], "impeller": [],
         "artrod": {}, "piston": {}, "planet": {}, "blowergear": {}, "vt": {}}
    suspects, static, dup = [], {}, {}
    seen = set()
    for ref, lab, owner in pairs:
        if lab in seen:
            dup[lab] = dup.get(lab, 1) + 1
            continue
        seen.add(lab)
        kind, args = classify_leaf(lab, owner)
        if kind == "static":
            pre = (lab if ":" in lab else owner).split(":", 1)[0] or "(unlabelled)"
            static[pre] = static.get(pre, 0) + 1
        elif kind == "suspect":
            suspects.append((lab, args))
        elif kind in ("artrod", "piston", "planet", "blowergear"):
            g[kind].setdefault(str(args[0]), []).append(lab)
        elif kind in ("tappet", "roller", "pushrod", "rocker", "valve", "spring"):
            key = f"{args[0]}{args[1]}"
            slot = g["vt"].setdefault(key, {})
            if kind == "spring":
                slot.setdefault("spring", []).append([lab, args[2]])
            else:
                slot.setdefault(kind, []).append(lab)
        else:
            g[kind].append(lab)
    for key in g:
        if isinstance(g[key], list):
            g[key].sort()
    return g, {"suspects": suspects, "static": static, "duplicates": dup}


# ---------------------------------------------------------------------------
# Constants baked into the JS (every one from spec.py / kin.py)
# ---------------------------------------------------------------------------
def constants():
    return {
        "PITCH": S.CYL_PITCH_DEG,
        "R_CRANK": S.R_CRANK, "L_MASTER": S.L_MASTER, "RHO": S.RHO_KNUCKLE, "L_ART": S.L_ART,
        "ROT": list(S.ROT_AXIS),
        "CAM_RATIO": S.CAM_RATIO, "CAM_LOBES": S.CAM_LOBES,
        "INCL": S.VALVE_INCLINE_DEG, "SEAT_H": S.VALVE_SEAT_H, "SEAT_T": S.VALVE_SEAT_T,
        "VLEN": S.VALVE_LENGTH, "PAD_R": kin.ROCKER_PAD_R,
        "RP": list(S.ROCKER_PIVOT), "RAXIS": list(kin.ROCKER_AXIS), "PS": list(S.PUSHROD_SOCKET),
        "DELTA": S.TAPPET_DELTA_DEG, "SOCKET_R": S.TAPPET_SOCKET_R, "TY": dict(S.TAPPET_Y),
        "BASE_R": S.CAM_BASE_R, "ROLLER_R": S.TAPPET_ROLLER_R, "LIFT": dict(S.TAPPET_LIFT),
        "OPEN": dict(S.VALVE_OPEN), "DUR": dict(S.VALVE_DURATION),
        "IDLER_RATIO": kin.cam_idler_ratio(), "IDLER_PT": list(kin.cam_idler_axis_point()),
        "RED_RATIO": S.RED_RATIO, "SUN_T": S.RED_SUN_T, "PLANET_T": S.RED_PLANET_T,
        "PLANET_R": S.RED_PLANET_R, "PLANET_Y": sum(S.RED_FACE_Y) / 2.0,
        "BLOWER_RATIO": S.BLOWER_RATIO, "BGEAR_RATIO": -S.BLOWER_CRANK_GEAR[0] / S.BLOWER_INTERMEDIATE[0][0],
        "BGEAR_ANG": list(S.BLOWER_INTERMEDIATE_ANGLES), "BGEAR_R": S.BLOWER_INTERMEDIATE_R,
        "SP_SEAT": kin.SPRING_SEAT_FROM_TIP, "SP_TOP": kin.SPRING_TOP_FROM_TIP,
        "SPRINGS": {k: list(v) for k, v in kin.SPRINGS.items()},
        "SP_PHASE": {"outer": 90.0, "inner": 270.0},
    }


JS = r"""// Nine-cylinder radial: the running choreography. GENERATED by src/lib/animgen.py
// from lib/spec.py + lib/kin.py (edit the generator, never this text). Every number
// is the number kin.py used to place the parts at theta = 0, transcribed
// operation for operation; lib/animcheck.py proves agreement to < 1e-6.
//
// running: one 720 deg four-stroke cycle in 8 s (theta = 90 t deg). Crank train
// authored at theta = 0 (pose = identity there); valvetrain authored at zero lift
// and placed at pose(0), so it moves by pose(theta) o pose(0)^-1. Valve springs
// compress by tube deformation along kin.spring_path.

const K = __CONST__;
const L = __LABELS__;
const DEG_PER_S = __DEG_PER_S__;
const SPRING_SEG = __SPRING_SEG__;

const D = Math.PI / 180;
const O = [0, 0, 0];
const fmod = (a, p) => { let r = a % p; if (r !== 0 && (r < 0) !== (p < 0)) r += p; return r; };  // Python %
const add = (a, b, s = 1) => [a[0] + s * b[0], a[1] + s * b[1], a[2] + s * b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mul = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => Math.sqrt(dot(a, a));
const unit = (a) => { const n = norm(a); return [a[0] / n, a[1] / n, a[2] / n]; };
const inplane = (b, r = 1, y = 0) => [-r * Math.sin(b * D), y, r * Math.cos(b * D)];
const ALPHA = (k) => K.PITCH * (k - 1);
const lp = (k, h, y, t) => {   // spec.cyl_point / kin.local_dir
  const u = inplane(ALPHA(k)), a = ALPHA(k) * D, tt = [Math.cos(a), 0, Math.sin(a)];
  return [h * u[0] + t * tt[0], y, h * u[2] + t * tt[2]];
};
function rotM(axis, deg) {
  const n = Math.sqrt(axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2]);
  const x = axis[0] / n, y = axis[1] / n, z = axis[2] / n;
  const c = Math.cos(deg * D), s = Math.sin(deg * D), C = 1 - c;
  return [[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
          [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
          [z * x * C - y * s, z * y * C + x * s, c + z * z * C]];
}
const rotAbout = (p, axis, deg, o) => {
  const R = rotM(axis, deg), d = sub(p, o);
  return add(o, [R[0][0] * d[0] + R[0][1] * d[1] + R[0][2] * d[2],
                 R[1][0] * d[0] + R[1][1] * d[1] + R[1][2] * d[2],
                 R[2][0] * d[0] + R[2][1] * d[1] + R[2][2] * d[2]]);
};

// ---- crank train (in-plane 2D points are (x, z)) -------------------------------
const dir2 = (b) => [-Math.sin(b * D), Math.cos(b * D)];
const angleOf = (v) => Math.atan2(-v[0], v[1]) / D;
const crankpin = (th) => { const d = dir2(th); return [K.R_CRANK * d[0], K.R_CRANK * d[1]]; };
const masterH = (th) => { const c = crankpin(th); return c[1] + Math.sqrt(K.L_MASTER ** 2 - c[0] ** 2); };
const masterAngle = (th) => { const c = crankpin(th); return angleOf([0 - c[0], masterH(th) - c[1]]); };
const knuckle = (th, k) => {
  const c = crankpin(th), d = dir2(masterAngle(th) + K.PITCH * (k - 1));
  return [c[0] + K.RHO * d[0], c[1] + K.RHO * d[1]];
};
const pistonH = (th, k) => {
  if (k === 1) return masterH(th);
  const kx = knuckle(th, k), u = dir2(ALPHA(k));
  const d = kx[0] * u[0] + kx[1] * u[1], perp2 = kx[0] ** 2 + kx[1] ** 2 - d * d;
  return d + Math.sqrt(K.L_ART ** 2 - perp2);
};
const rodAngle = (th, k) => {
  const kx = knuckle(th, k), u = dir2(ALPHA(k)), h = pistonH(th, k);
  return angleOf([h * u[0] - kx[0], h * u[1] - kx[1]]);
};
const spin = (deg, o = O, axis = K.ROT) => [["r", axis, deg, o]];
const poseMaster = (th) => {
  const c0 = crankpin(0), c = crankpin(th);
  return [["r", K.ROT, masterAngle(th) - masterAngle(0), [c0[0], 0, c0[1]]], ["t", [c[0] - c0[0], 0, c[1] - c0[1]]]];
};
const poseArt = (th, k) => {
  const k0 = knuckle(0, k), k1 = knuckle(th, k);
  return [["r", K.ROT, rodAngle(th, k) - rodAngle(0, k), [k0[0], 0, k0[1]]], ["t", [k1[0] - k0[0], 0, k1[1] - k0[1]]]];
};
const posePiston = (th, k) => {
  const u = dir2(ALPHA(k)), dh = pistonH(th, k) - pistonH(0, k);
  return [["t", [u[0] * dh, 0, u[1] * dh]]];
};
const posePlanet = (th, j) => {
  const c = K.RED_RATIO * th;
  return [["r", K.ROT, c * (K.SUN_T / K.PLANET_T), inplane(60 * (j - 1), K.PLANET_R, K.PLANET_Y)], ["r", K.ROT, c, O]];
};

// ---- valvetrain (v = "I" intake +t, "E" exhaust -t) ----------------------------
const side = (v) => (v === "I" ? 1 : -1);
const VT = {};   // per "kv": fixed geometry, from kin's rest definitions
const tappetAngle = (k, v) => ALPHA(k) - side(v) * K.DELTA;
const lobePhase = (v) => {
  const thc = ALPHA(1) + K.OPEN[v] + K.DUR[v] / 2;   // firing_tdc(1) = 0
  return fmod(tappetAngle(1, v) - K.CAM_RATIO * thc, 360 / K.CAM_LOBES);
};
const PHASE = { I: lobePhase("I"), E: lobePhase("E") };
const pushrodLength = (v) => norm(sub(lp(1, K.PS[0], K.PS[1], side(v) * K.PS[2]),
                                      inplane(tappetAngle(1, v), K.SOCKET_R, K.TY[v])));
const PRLEN = { I: pushrodLength("I"), E: pushrodLength("E") };
for (let k = 1; k <= 9; k++) {
  for (const v of ["I", "E"]) {
    const s = side(v), c = Math.cos(K.INCL * D), sn = Math.sin(K.INCL * D);
    const axis = lp(k, c, 0, s * sn);
    const seat = lp(k, K.SEAT_H, 0, s * K.SEAT_T);
    const tip = add(seat, axis, K.VLEN);
    const ta = tappetAngle(k, v);
    const xr = unit(cross(axis, [0, 1, 0]));
    VT[`${k}${v}`] = {
      k, v, axis, tip,
      pivot: lp(k, K.RP[0], 0, s * K.RP[1]),
      top0: lp(k, K.PS[0], K.PS[1], s * K.PS[2]),
      ta, tdir: inplane(ta), bottom0: inplane(ta, K.SOCKET_R, K.TY[v]),
      roller0: inplane(ta, K.BASE_R + K.ROLLER_R, K.TY[v]),
      pad0: add(tip, axis, K.PAD_R),
      base: add(tip, axis, -K.SP_SEAT), xr, yr: cross(axis, xr),
    };
  }
}
const tappetLift = (th, g) => {
  const P = 360 / K.CAM_LOBES, rho = fmod(g.ta - (PHASE[g.v] + K.CAM_RATIO * th) + P / 2, P) - P / 2;
  const w = K.DUR[g.v] * Math.abs(K.CAM_RATIO);
  if (Math.abs(rho) >= w / 2) return 0;
  return K.LIFT[g.v] * Math.sin(Math.PI * (rho / w + 0.5)) ** 2;
};
const rockerAngleFor = (g, lift) => {   // kin._rocker_angle_for: Newton, central difference
  const B = add(g.bottom0, g.tdir, lift), Lp = PRLEN[g.v];
  const f = (a) => norm(sub(rotAbout(g.top0, K.RAXIS, a, g.pivot), B)) - Lp;
  let a = 0;
  for (let i = 0; i < 50; i++) {
    const fa = f(a);
    if (Math.abs(fa) < 1e-11) break;
    const d = (f(a + 1e-5) - f(a - 1e-5)) / 2e-5;
    a -= fa / d;
  }
  return a;
};
const valveLift = (g, ang) => dot(sub(g.pad0, rotAbout(g.pad0, K.RAXIS, ang, g.pivot)), g.axis);
const vtState = (th, g) => {
  const lift = tappetLift(th, g), ang = rockerAngleFor(g, lift);
  return { lift, ang, vlift: valveLift(g, ang) };
};
const vtPoses = (th, g) => {
  const st = vtState(th, g);
  const B = add(g.bottom0, g.tdir, st.lift);
  const T = rotAbout(g.top0, K.RAXIS, st.ang, g.pivot);
  const d0 = unit(sub(g.top0, g.bottom0)), d1 = unit(sub(T, B)), ax = cross(d0, d1), s = norm(ax);
  const pushrod = [];
  if (s > 1e-12) pushrod.push(["r", unit(ax), Math.atan2(s, dot(d0, d1)) / D, g.bottom0]);
  pushrod.push(["t", sub(B, g.bottom0)]);
  return {
    st,
    tappet: [["t", mul(g.tdir, st.lift)]],
    roller: [["r", K.ROT, -(K.CAM_RATIO * th) * K.BASE_R / K.ROLLER_R, g.roller0], ["t", mul(g.tdir, st.lift)]],
    pushrod,
    rocker: [["r", K.RAXIS, st.ang, g.pivot]],
    valve: [["t", mul(g.axis, -st.vlift)]],
  };
};
// inverse of a step list: reversed, each step undone
const inv = (steps) => steps.slice().reverse().map((s) => (s[0] === "r" ? ["r", s[1], -s[2], s[3]] : ["t", mul(s[1], -1)]));
const REST = {};
for (const key of Object.keys(VT)) {
  const p = vtPoses(0, VT[key]);
  REST[key] = { tappet: inv(p.tappet), roller: inv(p.roller), pushrod: inv(p.pushrod), rocker: inv(p.rocker), valve: inv(p.valve) };
}

// ---- valve springs: kin.spring_path as cubic Beziers (quarter turns) -----------
const springPath = (g, vlift, which) => {
  const [R, wire, turns] = K.SPRINGS[which];
  const len = K.SP_SEAT - K.SP_TOP - vlift - wire, z0 = wire / 2;
  const nseg = Math.round(turns * 4), dz = len / nseg, kk = 4 / 3 * Math.tan(Math.PI / 8) * R, ph = K.SP_PHASE[which];
  const P = (a, z) => add(add(add(g.base, g.xr, R * Math.cos(a * D)), g.yr, R * Math.sin(a * D)), g.axis, z);
  const T = (a) => add(mul(g.xr, -Math.sin(a * D)), g.yr, Math.cos(a * D));
  const segments = [];
  for (let i = 0; i < nseg; i++) {
    const a0 = ph + 90 * i, a1 = ph + 90 * (i + 1), p0 = P(a0, z0 + dz * i), p3 = P(a1, z0 + dz * (i + 1));
    segments.push({ kind: "bezier", points: [p0, add(add(p0, T(a0), kk), g.axis, dz / 3),
                                             add(add(p3, T(a1), -kk), g.axis, -dz / 3), p3] });
  }
  return { normal: g.axis, segments };
};
const SPRING_REST = {};
for (const key of Object.keys(VT)) {
  const vl0 = vtState(0, VT[key]).vlift;
  SPRING_REST[key] = { outer: springPath(VT[key], vl0, "outer"), inner: springPath(VT[key], vl0, "inner") };
}

// ---- the clip -------------------------------------------------------------------
function play(get, labels, steps) {
  for (const label of labels || []) {
    const h = get(label);
    if (!h) continue;
    for (const s of steps) {
      if (s[0] === "r") h.rotate(s[1], s[2], s[3]); else h.translate(s[1]);
    }
  }
}

// name only parts this model carries (a stale bake can never throw)
function getter(m) {
  const have = typeof m.labels === "function" ? new Set(m.labels()) : null;
  return (label) => (have === null || have.has(label) ? m.get(label) : null);
}

// every running motion at crank angle th (shared by `running` and `exploded-running`)
function runAt(th, get) {
  play(get, L.crank, spin(th));
  play(get, L.master, poseMaster(th));
  for (const k in L.artrod) play(get, L.artrod[k], poseArt(th, Number(k)));
  for (const k in L.piston) play(get, L.piston[k], posePiston(th, Number(k)));
  play(get, L.camring, spin(K.CAM_RATIO * th));
  play(get, L.camidler, spin(K.IDLER_RATIO * th, K.IDLER_PT));
  for (const j in L.planet) play(get, L.planet[j], posePlanet(th, Number(j)));
  play(get, L.propshaft, spin(K.RED_RATIO * th));
  play(get, L.prop, spin(K.RED_RATIO * th));
  play(get, L.impeller, spin(K.BLOWER_RATIO * th));
  for (const j in L.blowergear) {
    play(get, L.blowergear[j], spin(K.BGEAR_RATIO * th, inplane(K.BGEAR_ANG[Number(j) - 1], K.BGEAR_R)));
  }
  for (const key in L.vt) {
    const g = VT[key], parts = L.vt[key], p = vtPoses(th, g), r = REST[key];
    for (const kind of ["tappet", "roller", "pushrod", "rocker", "valve"]) {
      if (parts[kind]) play(get, parts[kind], r[kind].concat(p[kind]));
    }
    for (const [label, which] of parts.spring || []) {
      const h = get(label);
      if (h) h.deformTube({ rest: SPRING_REST[key][which], path: springPath(g, p.st.vlift, which), maxSegmentLength: SPRING_SEG });
    }
  }
}
__XR_LIB__
export const clips = {
  running: {
    label: "Running (720 deg cycle)",
    duration: 8,
    loop: true,
    update(t, m) {
      runAt(DEG_PER_S * t, getter(m));
    },
  },__EXPLODE_CLIP____XR_CLIP__
};
"""

EXPLODE_JS = r"""
  explode: {
    label: "Exploded view (teardown)",
    duration: __X_DURATION__,
    loop: false,
    update(t, m) {
      // A designed teardown from the theta = 0 rest pose, a pure function of t:
      // every part moves by eased straight translations (lib/explodeplan.py).
      const have = typeof m.labels === "function" ? new Set(m.labels()) : null;
      const offs = explodeOffsets(t);
      for (const g of X.groups) {
        const o = offs[g[0]];
        if (o[0] === 0 && o[1] === 0 && o[2] === 0) continue;
        for (let i = 1; i < g.length; i++) {
          if (have === null || have.has(g[i])) m.get(g[i]).translate(o);
        }
      }
    },
  },"""

EXPLODE_LIB = r"""
// ---- exploded view: tracks of eased translations; a fastener's track = its own
// exit + its host's track (the parent, listed first). smoothstep easing.
const X = __X_DATA__;
const easeX = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
function explodeOffsets(t) {
  const out = new Array(X.tracks.length);
  for (let i = 0; i < X.tracks.length; i++) {
    const tr = X.tracks[i];
    const o = tr[0] >= 0 ? out[tr[0]].slice() : [0, 0, 0];
    for (const [t0, t1, dx, dy, dz] of tr[1]) {
      if (t <= t0) continue;
      const e = t >= t1 ? 1 : easeX((t - t0) / (t1 - t0));
      o[0] += e * dx; o[1] += e * dy; o[2] += e * dz;
    }
    out[i] = o;
  }
  return out;
}
"""


XR_JS = r"""
  "exploded-running": {
    label: "Exploded, running (720 deg cycle)",
    duration: 8,
    loop: true,
    update(t, m) {
      // The running cycle exactly as `running` (kin.py), with each part's constant
      // exploded offset composed on top in world space (lib/explodedrun.py): offsets
      // never change, so the loop is as seamless as `running`.
      const get = getter(m);
      runAt(DEG_PER_S * t, get);
      for (const g of XR.groups) {
        const o = XR.offsets[g[0]];
        for (let i = 1; i < g.length; i++) {
          const h = get(g[i]);
          if (h) h.translate(o);
        }
      }
      for (const label of XR.hidden) {
        const h = get(label);
        if (h) h.visible(false);
      }
    },
  },"""

XR_LIB = r"""
// ---- exploded-running: constant per-group offsets over the running cycle (lib/explodedrun.py)
const XR = __XR_DATA__;
"""


def xr_data(labels):
    """The exploded-running layout for the JS: offsets, [offset index, labels...] groups (zero
    offsets omitted: those parts just run), hidden labels."""
    from lib import explodedrun
    groups, offs, hidden = explodedrun.layout(labels)
    offsets, out = [], []
    for name in sorted(groups):
        o = [round(float(x), 9) for x in offs[name]]
        if not any(o):
            continue
        out.append([len(offsets)] + groups[name])
        offsets.append(o)
    return {"offsets": offsets, "groups": out, "hidden": sorted(hidden)}


def explode_data(plan, labels):
    """Compact tracks for the JS: parents (hosts) before children (fasteners)."""
    units = plan["units"]
    have = set(labels)
    tracks, index, groups = [], {}, []

    def add(name):
        if name in index:
            return index[name]
        u = units[name]
        parent = -1
        own = u["moves"]
        h = u.get("host")
        if h and h in units:
            parent = add(h)
            hm = units[h]["moves"]
            own = u["moves"][:len(u["moves"]) - len(hm)] if hm else u["moves"]
        index[name] = len(tracks)
        tracks.append([parent, own])
        return index[name]

    for name in sorted(units, key=lambda n: (units[n].get("host") is not None, n)):
        labs = [l for l in units[name]["leaves"] if l in have]
        if not labs:
            continue
        ti = add(name)
        groups.append([ti] + labs)
    return {"tracks": tracks, "groups": groups}


def render_js(groups, explode=None, xr=None) -> str:
    js = JS
    if xr is None:
        js = js.replace("__XR_CLIP__", "").replace("__XR_LIB__", "")
    else:
        js = js.replace("__XR_CLIP__", XR_JS).replace("__XR_LIB__", XR_LIB.replace(
            "__XR_DATA__", json.dumps(xr, separators=(",", ":"))))
    if explode is None:
        js = js.replace("__EXPLODE_CLIP__", "")
    else:
        js = js.replace("__EXPLODE_CLIP__", EXPLODE_JS.replace("__X_DURATION__", repr(explode["duration"])))
        js = js.replace("export const clips", EXPLODE_LIB.replace("__X_DATA__", json.dumps(explode["data"], separators=(",", ":")))
                        + "\nexport const clips", 1)
    for key, val in (("__CONST__", json.dumps(constants())), ("__LABELS__", json.dumps(groups, sort_keys=True)),
                     ("__DEG_PER_S__", repr(DEG_PER_S)), ("__SPRING_SEG__", repr(SPRING_MAX_SEGMENT))):
        js = js.replace(key, val)
    assert "'''" not in js
    return js


def write_labels_json(pairs, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"parts": [{"id": ref.lstrip("#"), "label": lab, "owner": owner}
                                          for ref, lab, owner in pairs]}))


def report(groups, rep, n_leaves):
    n_vt = sum(len(v) for slot in groups["vt"].values() for v in slot.values())
    counts = {k: (len(v) if isinstance(v, list) else sum(len(x) for x in v.values())) for k, v in groups.items() if k != "vt"}
    moving = sum(counts.values()) + n_vt
    print(f"[animgen] {n_leaves} leaves; {moving} moving labels: " +
          ", ".join(f"{k} {n}" for k, n in counts.items() if n) + f", valvetrain {n_vt} over {len(groups['vt'])} valves")
    if rep["static"]:
        print("[animgen] static prefixes: " + ", ".join(f"{k} {n}" for k, n in sorted(rep["static"].items())))
    for lab, why in rep["suspects"]:
        print(f"[animgen] WARNING {lab!r}: {why} -> NOT animated", file=sys.stderr)
    for lab, n in rep["duplicates"].items():
        print(f"[animgen] WARNING label {lab!r} is carried by {n} leaves (labels must be unique; all copies move together)",
              file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--step", default=str(DEFAULT_STEP), help="built assembly to read labels from")
    ap.add_argument("--synthetic", action="store_true", help="bake one label per contract group (no STEP needed)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--labels-json", default=str(LABELS_JSON), help="where to write the label table anim_eval reads")
    ap.add_argument("--plan", default=str(ROOT / "tmp" / "kin" / "explode_plan.json"), help="explode plan (lib.explodeplan)")
    ap.add_argument("--no-explode", action="store_true")
    ap.add_argument("--no-xr", action="store_true", help="omit the exploded-running clip")
    a = ap.parse_args(argv)
    if a.synthetic:
        pairs = synthetic_labels()
    else:
        step = Path(a.step)
        if not step.exists():
            raise SystemExit(f"[animgen] {step} does not exist: run `python tools/engine.py build` first (or --synthetic)")
        pairs = scene_labels(step)
    groups, rep = group_labels(pairs)
    report(groups, rep, len(pairs))
    explode = None
    plan_path = Path(a.plan)
    if not a.synthetic and not a.no_explode:
        if not plan_path.exists():
            print(f"[animgen] WARNING no explode plan at {plan_path}: run `python -m lib.explodeplan` (clip omitted)",
                  file=sys.stderr)
        else:
            plan = json.loads(plan_path.read_text())
            labels = [lab for _, lab, _ in pairs]
            planned = {l for u in plan["units"].values() for l in u["leaves"]}
            missing = sorted(set(labels) - planned)
            if missing:
                print(f"[animgen] WARNING the explode plan is stale: {len(missing)} built labels unplanned "
                      f"(e.g. {missing[:5]}); rerun `python -m lib.explodeplan`", file=sys.stderr)
            explode = {"duration": plan["duration"], "data": explode_data(plan, labels)}
    xr = None
    if not a.synthetic and not a.no_xr:
        xr = xr_data([lab for _, lab, _ in pairs])
        print(f"[animgen] exploded-running: {len(xr['groups'])} offset groups "
              f"({sum(len(g) - 1 for g in xr['groups'])} labels), {len(xr['hidden'])} hidden")
    js = render_js(groups, explode, xr)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(
        '"""GENERATED by lib/animgen.py from lib/kin.py + the built assembly\'s labels. Do not edit."""\n\n'
        f"ANIMATION_JS = r'''{js}'''\n")
    write_labels_json(pairs, Path(a.labels_json))
    print(f"[animgen] wrote {a.out} ({len(js)} chars) and {a.labels_json}")


if __name__ == "__main__":
    main()
