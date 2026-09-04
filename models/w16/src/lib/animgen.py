"""Generate STEP/w16.step.js (the render module beside the engine's STEP) from lib/spec + lib/kin.

The render module must re-describe the motion on its own (it knows nothing about
mates or Python), so this bakes every constant it needs: the cylinder table,
pin angles, valve axes, follower pivots and the nonlinear follower-angle
tables, cam axes, chain layouts. Run from src/:  python -m lib.animgen
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from lib import kin, spec as S
from lib.valvetrain import valve_tag

OUT = Path(__file__).resolve().parent.parent.parent / "STEP" / "w16.step.js"

CRANK_SECONDS = 6.0        # one 720 deg cycle

# Accessory pulleys as built by lib/ancillaries.py (axis y, z; speed ratio vs crank,
# negative = opposite sense). Bodies of revolution, so any angle loops seamlessly.
PULLEYS = [
    {"label": "pulley:water_pump_1", "y": 190.0, "z": 0.0, "ratio": 1.651},
    {"label": "pulley:water_pump_2", "y": -190.0, "z": 0.0, "ratio": 1.651},
    {"label": "pulley:alternator", "y": 278.0, "z": -30.0, "ratio": 2.917},
    {"label": "pulley:idler", "y": -270.0, "z": -100.0, "ratio": 2.586},
    {"label": "pulley:tensioner", "y": 170.0, "z": -130.0, "ratio": 2.586},
]
EXPLODE_SECONDS = 12.0     # 0..1 staged explode
EXPLODE_RUN_SECONDS = 24.0 # explode + crank together: 4 crank cycles (24 / 6), ramp out and back
REFS = Path(__file__).resolve().parent.parent.parent / "tmp" / "refs.json"   # cadgen step inspect refs --json

# Assembly group order in w16.py (o1.N): systems the explode moves per bank need
# their part labels, which only the built document knows.
GROUP_INDEX = {"heads": 4, "covers": 8, "turbos": 10, "exhaust": 11}
BLOCK_GROUP = 1                      # o1.1: the crankcase casting + its cast skins, cross bolts and ID pads


def _walk(obj):
    """(occurrence id, part label) pairs from `inspect refs --json`: each resolved
    occurrence selection carries `normalizedSelector` (o1.10.3) and `summary` (the label)."""
    if isinstance(obj, dict):
        if obj.get("selectorType") == "occurrence" and obj.get("status") == "resolved":
            yield obj["normalizedSelector"], obj["summary"]
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _bank_of_label(label: str):
    tag = label.split(":", 1)[1] if ":" in label else ""
    head = tag.split("_")[0]
    if head in ("1", "2") and (tag == head or "_" in tag and tag.split("_")[1] in ("front", "rear", "intake", "exhaust")):
        return int(head)
    if head.isdigit():
        n = int(head)
        return 1 if n <= 8 else 2          # cylinder-numbered parts
    return None


def block_ghost_labels():
    """The o1.1 occurrences that stand between the camera and the running gear:
    the crankcase casting and its cast face skins. The cross bolts and ID pads
    are left alone — 'some but not all of o1.1'."""
    pairs = list(_walk(json.loads(REFS.read_text())))
    out = [lab for ref, lab in pairs
           if ref.split(".")[1] == str(BLOCK_GROUP) and (lab == "block" or lab.startswith("block_face"))]
    if not out:
        raise SystemExit(f"no block occurrences under o1.{BLOCK_GROUP} in {REFS}")
    return sorted(set(out))


def explode_sets():
    """{turbos_1: [...], turbos_2, exhaust_1, exhaust_2, covers_1, covers_2} from the
    built document's refs table. Downpipes ride with their turbo."""
    if not REFS.exists():
        raise SystemExit(f"{REFS} missing: run `cadgen step inspect refs STEP/w16.step --json > tmp/refs.json` first")
    pairs = list(_walk(json.loads(REFS.read_text())))
    by_group = {}
    for ref, label in pairs:
        parts = ref.lstrip("#").split(".")
        if len(parts) < 3 or parts[0] != "o1" or not parts[1].isdigit():
            continue
        by_group.setdefault(int(parts[1]), {})[label] = True
    out = {}
    for name, gi in GROUP_INDEX.items():
        labels = sorted(by_group.get(gi, {}))
        if not labels:
            raise SystemExit(f"no parts under o1.{gi} ({name}) in {REFS}")
        for bank in (1, 2):
            key = f"{name}_{bank}"
            out[key] = []
        for lab in labels:
            b = _bank_of_label(lab)
            if b is None:
                raise SystemExit(f"cannot place {lab} (o1.{gi}) on a bank")
            target = name
            if name == "exhaust" and lab.split(":")[0] in ("downpipe", "downpipe_vband"):
                target = "turbos"
            out[f"{target}_{b}"].append(lab)
    return out


def cylinders():
    out = []
    for c in S.CYLINDERS:
        st0 = kin.piston(c.number, 0.0)
        out.append({
            "n": c.number, "bank": c.bank, "pin": c.pin, "x": c.x,
            "foot": [c.foot[1], c.foot[2]], "axis": [c.axis[1], c.axis[2]],
            "lat": [c.toward_centre[1], c.toward_centre[2]],
            "pinAngle": S.pin_angle(c.pin), "tdc": c.tdc,
            "s0": st0.s, "pin0": list(st0.pin), "tilt0": st0.rod_tilt,
        })
    return out


def valves():
    out = []
    for cyl in range(1, 17):
        for kind in ("intake", "exhaust"):
            for side in (-1, 1):
                g = kin.valve_geom(cyl, kind, side)
                c = S.CYLINDERS[cyl - 1]
                lift0 = kin.valve_lift(cyl, kind, 0.0)
                _, eps0, _, _ = kin.follower_state(g, 0.0)
                out.append({
                    "tag": valve_tag(g), "cyl": cyl, "kind": kind, "x": g.x,
                    "v": list(g.v), "pivot": list(g.pivot),
                    "lift0": lift0, "eps0": eps0,           # the built (theta = 0) state; motion is relative to it
                    "cls": f"{c.bank}_{c.row}_{kind}",
                    "centre": c.tdc + (S.INTAKE_CENTRE if kind == "intake" else S.EXHAUST_CENTRE),
                    "dur": S.INTAKE_DURATION if kind == "intake" else S.EXHAUST_DURATION,
                })
    return out


def chains():
    out = {}
    for bank in (1, 2):
        L = kin.chain_layout(bank)
        segs = []
        for k0, k1, kind, data in L.segments:
            if kind == "straight":
                segs.append({"k0": k0, "k1": k1, "kind": "straight", "a": list(data[0]), "b": list(data[1])})
            else:
                segs.append({"k0": k0, "k1": k1, "kind": "wrap", "c": list(data.centre), "r": data.radius,
                             "aIn": data.a_in, "teeth": data.teeth})
        rest = []
        for k in range(L.links):
            p0, _ = kin.chain_point(L, k)
            p1, _ = kin.chain_point(L, k + 1)
            rest.append([p0[0], p0[1], math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))])
        out[str(bank)] = {"links": L.links, "x": S.CHAIN_X[bank], "segments": segs, "rest": rest,
                          "cams": {sp.name: list(sp.centre) for sp in L.sprockets if sp.name != "crank"}}
    return out


def cam_axes():
    from lib import cams
    return {f"{b}_{k}": list(cams.cam_axis(b, k)) for b in (1, 2) for k in ("intake", "exhaust")}


JS_TEMPLATE = r"""// W16 — choreography. GENERATED by src/lib/animgen.py from lib/spec.py + lib/kin.py;
// edit the generator, not this file. Every number here is the same number the
// Python kinematics used to place the parts at theta = 0, so the viewer's
// motion is byte-for-byte the motion the collision gate verified.
//
// Clips
//   crank    one full 720 deg cycle: 16 pistons/rods with the published firing
//            order, 4 cams at half speed, 64 valves + roller followers, the
//            two chain drives (every link), sprockets. Exactly periodic.
//   explode  staged 0..1: covers/induction, then heads + valvetrain bank by
//            bank, then the rotating assembly.

const CRANK_SECONDS = %(crank_seconds)s;
const EXPLODE_SECONDS = %(explode_seconds)s;
const EXPL = %(explode_sets)s;   // per-bank label sets for the systems the explode moves
const EXPLODE_RUN_SECONDS = %(explode_run_seconds)s;   // off, hold, back on -- while the crank never stops
const BLOCK_GHOST = %(block_ghost)s;   // what hides to expose the running gear
const THROW = %(throw)s;
const ROD_LEN = %(rod_len)s;
const VALVE_LIFT = %(valve_lift)s;
const CRANK_TEETH = %(crank_teeth)s;
const OIL_PUMP_AXIS = %(oil_pump_axis)s;   // [x, y, z] point on the pump axis
const OIL_PUMP_RATIO = %(oil_pump_ratio)s;
const PULLEYS = %(pulleys)s;
const TURBOS = %(turbos)s;
const TURBO_TURNS_PER_CYCLE = 12;

const CYL = %(cyl)s;
const VALVES = %(valves)s;
const EPS_TABLES = %(eps_tables)s;
const CAM_AXES = %(cam_axes)s;
const CHAINS = %(chains)s;

const DEG = Math.PI / 180;
const X = [1, 0, 0];

function rotYZ(v, deg) {
  const c = Math.cos(deg * DEG), s = Math.sin(deg * DEG);
  return [v[0] * c - v[1] * s, v[0] * s + v[1] * c];
}
function pinYZ(pinAngle, theta) {
  const a = (pinAngle + theta) * DEG;
  return [-THROW * Math.sin(a), THROW * Math.cos(a)];
}
function pistonState(c, theta) {
  const P = pinYZ(c.pinAngle, theta);
  const ey = P[0] - c.foot[0], ez = P[1] - c.foot[1];
  const a = ey * c.axis[0] + ez * c.axis[1];
  const h = ey * c.lat[0] + ez * c.lat[1];
  const s = a + Math.sqrt(ROD_LEN * ROD_LEN - h * h);
  const Q = [c.foot[0] + c.axis[0] * s, c.foot[1] + c.axis[1] * s];
  const ry = Q[0] - P[0], rz = Q[1] - P[1];
  const tilt = Math.atan2(c.axis[0] * rz - c.axis[1] * ry, c.axis[0] * ry + c.axis[1] * rz) / DEG;
  return { s, P, tilt };
}
function liftProfile(x) {
  if (x <= 0 || x >= 1) return 0;
  return 0.5 - 0.5 * Math.cos(2 * Math.PI * x);
}
function valveLift(v, theta) {
  let rel = (theta - v.centre + 360) %% 720;
  if (rel < 0) rel += 720;
  rel -= 360;
  return VALVE_LIFT * liftProfile(rel / v.dur + 0.5);
}
function followerEps(v, theta) {
  let rel = (theta - v.centre + 360) %% 720;
  if (rel < 0) rel += 720;
  rel -= 360;
  const t = EPS_TABLES[v.cls];
  const r = t.rel, e = t.eps;
  if (rel <= r[0] || rel >= r[r.length - 1]) return 0;
  const step = r[1] - r[0];
  const i = Math.min(r.length - 2, Math.max(0, Math.floor((rel - r[0]) / step)));
  const u = (rel - r[i]) / step;
  return e[i] + (e[i + 1] - e[i]) * u;
}
function chainPoint(ch, k) {
  k = ((k %% ch.links) + ch.links) %% ch.links;
  for (const sg of ch.segments) {
    if (k >= sg.k0 - 1e-9 && k <= sg.k1 + 1e-9) {
      if (sg.kind === "straight") {
        const u = sg.k1 === sg.k0 ? 0 : (k - sg.k0) / (sg.k1 - sg.k0);
        return [sg.a[0] + (sg.b[0] - sg.a[0]) * u, sg.a[1] + (sg.b[1] - sg.a[1]) * u];
      }
      const a = sg.aIn + (k - sg.k0) * 2 * Math.PI / sg.teeth;
      return [sg.c[0] + sg.r * Math.cos(a), sg.c[1] + sg.r * Math.sin(a)];
    }
  }
  return ch.segments[0].a;
}

// --- the engine turning ------------------------------------------------------

function turn(m, theta) {
  const camDeg = theta / 2;
  // crank + everything bolted to it
  m.get("crankshaft").rotate(X, theta);
  for (const lab of ["crank_damper", "damper_washer", "damper_bolt", "crank_sprocket_hub",
                     "crank_sprocket:1", "crank_sprocket:2", "flywheel",
                     "crank_pulley_hub", "crank_oil_pulley"]) {
    m.get(lab).rotate(X, theta);
  }
  for (let k = 1; k <= 8; k += 1) m.get(`flywheel_bolt:${k}`).rotate(X, theta);
  for (let k = 1; k <= 6; k += 1) m.get(`crank_pulley_bolt:${k}`).rotate(X, theta);
  // oil pump: belt-driven off the Ø72 crank pulley onto its Ø90 pulley (0.8:1), axis along X
  m.get("oil_pump_pulley").rotate(X, theta * OIL_PUMP_RATIO, OIL_PUMP_AXIS);
  m.get("oil_pump_shaft").rotate(X, theta * OIL_PUMP_RATIO, OIL_PUMP_AXIS);
  // turbochargers: both wheels + shaft nut spin about the turbo axis (integer turns per cycle => seamless loop)
  for (const t of TURBOS) {
    for (const lab of [`turbine_wheel:${t.tag}`, `compressor_wheel:${t.tag}`, `compressor_shaft_nut:${t.tag}`]) {
      try { m.get(lab).rotate(X, theta * TURBO_TURNS_PER_CYCLE * 360 / 720, [0, t.y, t.z]); } catch (e) { /* not built */ }
    }
  }
  // accessory drive: every pulley spins about its own X axis at its belt ratio
  // (all pulleys are bodies of revolution, so non-integer turns still loop seamlessly)
  for (const p of PULLEYS) {
    try { m.get(p.label).rotate(X, theta * p.ratio, [0, p.y, p.z]); } catch (e) { /* not built */ }
  }
  // pistons + rods
  for (const c of CYL) {
    const st = pistonState(c, theta);
    const ds = st.s - c.s0;
    const slide = [0, c.axis[0] * ds, c.axis[1] * ds];
    for (const lab of [`piston:${c.n}`, `piston_ring:${c.n}_1`, `piston_ring:${c.n}_2`, `piston_ring:${c.n}_3`,
                       `wrist_pin:${c.n}`, `circlip:${c.n}_f`, `circlip:${c.n}_r`]) {
      m.get(lab).translate(slide);
    }
    const dTilt = st.tilt - c.tilt0;
    const origin = [c.x, c.pin0[0], c.pin0[1]];
    const shift = [0, st.P[0] - c.pin0[0], st.P[1] - c.pin0[1]];
    for (const lab of [`rod:${c.n}`, `rod_cap:${c.n}`, `rod_bolt:${c.n}_1`, `rod_bolt:${c.n}_2`,
                       `rod_shell:${c.n}_upper`, `rod_shell:${c.n}_lower`, `rod_bush:${c.n}`]) {
      m.get(lab).rotate(X, dTilt, origin).translate(shift);
    }
  }
  // cams + sprockets
  for (const key of Object.keys(CAM_AXES)) {
    const [y, z] = CAM_AXES[key];
    const [bank, kind] = key.split("_");
    for (const lab of [`camshaft:${key}`, `cam_sprocket:${bank}_${kind}`, `cam_sprocket_bolt:${bank}_${kind}`,
                       `cam_sprocket_washer:${bank}_${kind}`]) {
      m.get(lab).rotate(X, camDeg, [0, y, z]);
    }
  }
  // valves + followers
  // the STEP is the true theta = 0 state (some valves are open there), so every
  // valve/follower move is RELATIVE to its built lift0 / eps0
  for (const v of VALVES) {
    const lift = valveLift(v, theta) - v.lift0;
    if (Math.abs(lift) > 1e-9) {
      const d = [0, -v.v[0] * lift, -v.v[1] * lift];
      for (const lab of [`valve:${v.tag}`, `valve_spring:${v.tag}`, `retainer:${v.tag}`, `collet:${v.tag}_a`, `collet:${v.tag}_b`]) {
        m.get(lab).translate(d);
      }
    }
    const eps = followerEps(v, theta) - v.eps0;
    if (Math.abs(eps) > 1e-9) {
      const piv = [v.x, v.pivot[0], v.pivot[1]];
      for (const lab of [`follower:${v.tag}`, `roller:${v.tag}`, `roller_axle:${v.tag}`]) {
        m.get(lab).rotate(X, eps, piv);
      }
    }
  }
  // chains: link k rides from rollers (k, k+1) to (k+f, k+1+f)
  const f = theta / 360 * CRANK_TEETH;
  for (const bank of ["1", "2"]) {
    const ch = CHAINS[bank];
    for (let k = 0; k < ch.links; k += 1) {
      const p0 = chainPoint(ch, k + f);
      const p1 = chainPoint(ch, k + 1 + f);
      const ang = Math.atan2(p1[1] - p0[1], p1[0] - p0[0]) / DEG;
      const r = ch.rest[k];
      const kind = k %% 2 === 0 ? "inner" : "outer";
      m.get(`chain_link:${bank}_${k + 1}_${kind}`)
        .rotate(X, ang - r[2], [ch.x, r[0], r[1]])
        .translate([0, p0[0] - r[0], p0[1] - r[1]]);
    }
  }
}

// --- explode -------------------------------------------------------------------

function clamp01(v) { return Math.min(1, Math.max(0, v)); }
function smooth(t) { const x = clamp01(t); return x * x * (3 - 2 * x); }
function stage(p, a, b) { return smooth((p - a) / (b - a)); }

// Exploded-and-running progress: apart over 0..OUT, held apart to HOLD, back
// together by the end.  The clip length is a whole number of crank cycles and
// the ramp returns to 0, so t = 0 and t = EXPLODE_RUN_SECONDS are identical
// states and the clip loops seamlessly with the rotating assembly still turning.
const EXPLODE_RUN_OUT = 8.0;
const EXPLODE_RUN_HOLD = 16.0;
function explodeRunProgress(t) {
  if (t <= EXPLODE_RUN_OUT) return smooth(t / EXPLODE_RUN_OUT);
  if (t <= EXPLODE_RUN_HOLD) return 1;
  return smooth((EXPLODE_RUN_SECONDS - t) / (EXPLODE_RUN_SECONDS - EXPLODE_RUN_HOLD));
}

const BANK_UP = { 1: [0, Math.SQRT1_2, Math.SQRT1_2], 2: [0, -Math.SQRT1_2, Math.SQRT1_2] };
function scaled(v, k) { return [v[0] * k, v[1] * k, v[2] * k]; }

// The display floor sits under the engine at rest, so anything that separates
// DOWNWARD would sink through it. The deepest fall is a main bolt: 420 mm with the
// crank group plus its own 600 mm, so 1 020 mm, and the rotating parts add their
// own swing on top. The whole assembly therefore rises 1 150 mm as the sequence
// runs: every part's net z displacement then stays >= 0 and nothing ever
// goes below where it started. Pure translation, so it simply adds to each part's
// own offset (and to the parts that do not otherwise move).
const FLOOR_LIFT = 1150.0;
function floorLift(m, p) {
  const lift = FLOOR_LIFT * stage(p, 0.0, 0.16);
  if (lift <= 0) return;
  for (let g = 1; g <= 13; g += 1) {
    try { m.get(`o1.${g}`).translate([0, 0, lift]); } catch (e) { /* group not built */ }
  }
}

function explode(m, p) {
  floorLift(m, p);
  // Stage 1a (0.02-0.16): the low systems drop first -- ancillaries (belt drive,
  // starter, mounts, dipstick) and the oil system (pan, pump, filter, tray).
  const sA = stage(p, 0.02, 0.16);
  if (sA > 0) {
    m.get("o1.13").translate([0, 0, -700 * sA]);
    m.get("o1.9").translate([0, 0, -550 * sA]);
  }
  // Stage 1b (0.14-0.30): induction straight up; cam covers along each bank's
  // axis (beyond where the cams and caps will end); exhaust manifolds outboard
  // along the head face normal; turbos (with their downpipes) outboard and down;
  // the cam drive forward once the belt drive is out of its way.
  const sB = stage(p, 0.14, 0.30);
  if (sB > 0) {
    m.get("o1.12").translate([0, 0, 500 * sB]);
    m.get("o1.7").translate([260 * sB, 0, 0]);
    for (const bank of [1, 2]) {
      const sgn = bank === 1 ? 1 : -1;
      const up = BANK_UP[bank];
      const out = [0, sgn * Math.SQRT1_2, -Math.SQRT1_2];
      for (const lab of EXPL[`covers_${bank}`]) m.get(lab).translate(scaled(up, 1200 * sB));
      for (const lab of EXPL[`exhaust_${bank}`]) m.get(lab).translate(scaled(out, 280 * sB));
      for (const lab of EXPL[`turbos_${bank}`]) m.get(lab).translate([0, sgn * 150 * sB, -400 * sB]);
    }
  }
  // Stage 2 (0.33-0.66): heads, cams, valvetrain -- bank 1 then bank 2, along
  // each bank's own axis. Order along the axis at p = 1 (pistons come later, to
  // 220): head 420..552, valves 750, followers 850, cams 950, caps 1000, bolts 1050.
  for (const bank of [1, 2]) {
    const s2 = bank === 1 ? stage(p, 0.33, 0.5) : stage(p, 0.48, 0.66);
    if (s2 <= 0) continue;
    const up = BANK_UP[bank];
    const camKeys = [`${bank}_intake`, `${bank}_exhaust`];
    for (const key of camKeys) {
      m.get(`camshaft:${key}`).translate(scaled(up, 950 * s2));
      const [b, kind] = key.split("_");
      for (let k = 1; k <= 5; k += 1) {
        for (const suf of ["", "_a", "_b"]) {
          const lab = suf === "" ? `cam_cap:${b}_${kind}_${k}` : `cam_cap_bolt:${b}_${kind}_${k}${suf}`;
          try { m.get(lab).translate(scaled(up, (suf === "" ? 1000 : 1050) * s2)); } catch (e) { /* cut away in the section */ }
        }
      }
    }
    for (const v of VALVES) {
      if (CYL[v.cyl - 1].bank !== bank) continue;
      for (const lab of [`follower:${v.tag}`, `roller:${v.tag}`, `roller_axle:${v.tag}`]) m.get(lab).translate(scaled(up, 850 * s2));
      for (const lab of [`valve:${v.tag}`, `valve_spring:${v.tag}`, `retainer:${v.tag}`, `collet:${v.tag}_a`, `collet:${v.tag}_b`,
                         `spring_cup:${v.tag}`, `valve_guide:${v.tag}`, `lash_adjuster:${v.tag}`]) {
        m.get(lab).translate(scaled(up, 750 * s2));
      }
    }
    for (const lab of EXPL[`heads_${bank}`]) {
      // the head casting, its face skins, head bolts, spark plugs and core plugs all ride together
      m.get(lab).translate(scaled(up, 420 * s2));
    }
  }
  // Stage 3 (0.68-0.85): pistons and rods out of the bores along the bank axis
  const s3 = stage(p, 0.68, 0.85);
  if (s3 > 0) {
    for (const c of CYL) {
      const out = [0, c.axis[0] * 220 * s3, c.axis[1] * 220 * s3];
      for (const lab of [`piston:${c.n}`, `piston_ring:${c.n}_1`, `piston_ring:${c.n}_2`, `piston_ring:${c.n}_3`,
                         `wrist_pin:${c.n}`, `circlip:${c.n}_f`, `circlip:${c.n}_r`,
                         `rod:${c.n}`, `rod_cap:${c.n}`, `rod_bolt:${c.n}_1`, `rod_bolt:${c.n}_2`,
                         `rod_shell:${c.n}_upper`, `rod_shell:${c.n}_lower`, `rod_bush:${c.n}`]) {
        m.get(lab).translate(out);
      }
    }
  }
  // Stage 4 (0.84-1.0): the crank down, main caps and shells below it
  const s4 = stage(p, 0.84, 1.0);
  if (s4 > 0) {
    m.get("o1.2").translate([0, 0, -420 * s4]);
    for (let k = 1; k <= 5; k += 1) {
      m.get(`main_shell:${k}_lower`).translate([0, 0, -470 * s4]);
      m.get(`main_shell:${k}_upper`).translate([0, 0, -80 * s4]);
      if (k === 1) continue;            // the front main runs in the front wall: no cap
      m.get(`main_cap:${k}`).translate([0, 0, -520 * s4]);
      m.get(`main_bolt:${k}_l`).translate([0, 0, -600 * s4]);
      m.get(`main_bolt:${k}_r`).translate([0, 0, -600 * s4]);
    }
  }
}

// --- reveal: take the obstruction away, never the moving parts ---------------
//
// Unlike explode(), this displaces NOTHING that moves. The crank, rods, pistons,
// cams, followers and valves stay exactly where they run; what comes off is the
// bodywork in front of them -- the outer systems move clear, the heads lift, and
// the crankcase casting and its cast skins fade out. The cross bolts and ID pads
// of o1.1 stay solid, so the block's bolt pattern still reads.
function reveal(m, p) {
  floorLift(m, p);
  // 1 (0.02-0.30): everything outboard of the working parts moves clear
  const s1 = stage(p, 0.02, 0.30);
  if (s1 > 0) {
    m.get("o1.13").translate([0, 0, -700 * s1]);          // ancillaries
    m.get("o1.9").translate([0, 0, -560 * s1]);           // oil system: pan, tray, pump, filter
    m.get("o1.12").translate([0, 0, 520 * s1]);           // induction
    m.get("o1.7").translate([300 * s1, 0, 0]);            // cam drive, forward off the nose
    for (const bank of [1, 2]) {
      const sgn = bank === 1 ? 1 : -1;
      const up = BANK_UP[bank];
      const out = [0, sgn * Math.SQRT1_2, -Math.SQRT1_2];
      for (const lab of EXPL[`covers_${bank}`]) m.get(lab).translate(scaled(up, 1200 * s1));
      for (const lab of EXPL[`exhaust_${bank}`]) m.get(lab).translate(scaled(out, 300 * s1));
      for (const lab of EXPL[`turbos_${bank}`]) m.get(lab).translate([0, sgn * 160 * s1, -420 * s1]);
    }
  }
  // 2 (0.26-0.55): the heads lift off along each bank's own axis. The cams,
  // followers and valves they enclosed DO NOT MOVE -- they keep running in air.
  const s2 = stage(p, 0.26, 0.55);
  if (s2 > 0) {
    for (const bank of [1, 2]) {
      for (const lab of EXPL[`heads_${bank}`]) m.get(lab).translate(scaled(BANK_UP[bank], 560 * s2));
    }
  }
  // 3 (0.5-0.8): the crankcase itself fades, so the crank, rods and pistons are
  // seen working inside the space it occupied.
  const s3 = stage(p, 0.5, 0.8);
  if (s3 > 0) {
    const o = 1 - 0.92 * s3;
    for (const lab of BLOCK_GHOST) m.get(lab).opacity(o);
  }
}

export const clips = {
  crank: {
    label: "Crank (720 deg)",
    description: "One full four-stroke cycle: pistons, rods, cams, valves, followers, chains. Loops exactly.",
    duration: CRANK_SECONDS,
    loop: true,
    update(t, m) {
      const theta = 720 * ((t / CRANK_SECONDS) %% 1);
      turn(m, theta);
    },
  },
  running_reveal: {
    label: "Running cutaway",
    description: "The engine runs while the bodywork comes off it: outer systems clear, heads lift, and the crankcase fades, so the crank, rods, pistons, cams and 64 valves are seen working IN PLACE -- nothing that moves is displaced. Off, held, back on; loops exactly.",
    duration: EXPLODE_RUN_SECONDS,
    loop: true,
    update(t, m) {
      // kinematics FIRST, then the reveal: handles premultiply, so a part that
      // is moved clear still carries its own motion, and a part that stays put
      // simply keeps running.
      turn(m, 720 * ((t / CRANK_SECONDS) %% 1));
      reveal(m, explodeRunProgress(t));
    },
  },
  explode: {
    label: "Explode (staged)",
    description: "0..1 by system, with the engine still running throughout: ancillaries and oil system, then induction, covers, exhaust, turbos and cam drive, then heads, cams and valvetrain bank by bank, then pistons out and the crank down. The whole sequence rises clear of the floor as it separates.",
    duration: EXPLODE_SECONDS,
    loop: false,
    update(t, m) {
      // the full crank loop keeps running as the assemblies come apart: crank,
      // rods, pistons, cams, 64 valves, both chains, the oil-pump drive, the
      // turbo rotors and every accessory pulley. 12 s is exactly 2 crank cycles.
      turn(m, 720 * ((t / CRANK_SECONDS) %% 1));
      explode(m, clamp01(t / EXPLODE_SECONDS));
    },
  },
};
"""


def main():
    js = JS_TEMPLATE % {
        "crank_seconds": CRANK_SECONDS,
        "explode_seconds": EXPLODE_SECONDS,
        "explode_run_seconds": EXPLODE_RUN_SECONDS,
        "block_ghost": json.dumps(block_ghost_labels()),
        "explode_sets": json.dumps(explode_sets()),
        "throw": S.THROW,
        "rod_len": S.ROD_LEN,
        "valve_lift": S.VALVE_LIFT,
        "crank_teeth": S.CRANK_SPROCKET_T,
        "oil_pump_axis": json.dumps(list(S.OIL_PUMP_CENTRE)),
        "oil_pump_ratio": 72.0 / 90.0,
        "pulleys": json.dumps(PULLEYS),
        "turbos": json.dumps([{"tag": f"{t['bank']}_{t['pos']}", "y": t["centre"][1], "z": t["centre"][2]} for t in S.TURBOS]),
        "cyl": json.dumps(cylinders()),
        "valves": json.dumps(valves()),
        "eps_tables": json.dumps(kin.tables()),
        "cam_axes": json.dumps(cam_axes()),
        "chains": json.dumps(chains()),
    }
    OUT.write_text(js)
    print(f"wrote {OUT} ({len(js)} bytes)")


if __name__ == "__main__":
    main()
