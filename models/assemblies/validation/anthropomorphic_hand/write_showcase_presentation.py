"""Write the hand's showcase render module: exact FK choreography + braided tendons.

The module this writes is `STEP/anthropomorphic_hand/<name>.step.js`, loaded by
the viewer and by `cadgen step snapshot --animation`. It carries three things:

1. The authored joint datums (`lib.layout.JOINTS`) and the fixed neutral finger
   fan, so the module can evaluate `lib.layout.assembled_transforms` itself, in
   JavaScript, at any time t. The artifact is written at pose zero, so a frame's
   transform at a pose IS its delta from rest — no rest-pose bookkeeping.
2. Which bodies ride which frame, from the build's own
   `mechanical_candidate_r13_frames.json`, plus the 170 guide bodies, whose
   frames come from the route group each guide belongs to.
3. The 48 neutral tendon routes, unchanged from the static presentation, and the
   122 compensating guide bodies that re-seat with them.

THE TENDONS DO NOT BEND. A posed tendon route is a routing solve (guide wraps
re-seat, arc sweeps change), not a transform of the neutral one: moving each
route group rigidly with its own frame tears the centerline apart by up to
100 mm, because a group spans from the previous guide to its own, and
`deformTube` rightly refuses a centerline that is not tangent-continuous to
1e-5 mm. So the tendons keep their neutral geometry and braided finish, and the
choreography shows the drive a different way — each tendon's opacity follows the
excursion it is taking, so the antagonist pair driving a joint lights up as that
joint moves and fades as it returns. Re-solving all 48 routes per keyframe is
the follow-up that would let them bend.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'src/anthropomorphic_hand'
sys.path.insert(0, str(SOURCE))

from lib.layout import FINGERS, JOINTS, NEUTRAL_FINGER_FAN, TENDONS  # noqa: E402
from lib.neutral_routes import NEUTRAL_ROUTES  # noqa: E402

# Only the document whose body list this generator reads. A clip's targets are
# checked against the compiled tree at LOAD — a label the document does not
# carry is an error, not a silent no-op — and the earlier revisions are
# different body sets, so they keep the static presentation they already have.
TARGETS = ('hand_mechanical_candidate_r13',)


def frame_bodies():
    """(frame -> body names, bodies that re-solve rather than ride a frame).

    The build records a frame for every body it places, and every body it calls
    `variable` is one whose placement is a ROUTING result: the 48 tendons and the
    guides that carry them across a joint. A guide named after a route group in a
    real frame is bolted to that link and rides it. A guide named after a group
    whose own frame is `variable` is a compensating span BRIDGING two frames — a
    wrist guide, a joint reaction — and re-seats as the joint moves. Riding it on
    either neighbouring frame swings it out of the hand; it is faded with the
    tendons instead.
    """
    rows = json.loads((HERE / 'mechanical_candidate_r13_frames.json').read_text())
    guide_frame = {group['label']: group['frame']
                   for route in NEUTRAL_ROUTES for group in route['groups']}
    tendons = {tendon['name'] for tendon in TENDONS}
    by_frame = {}
    unsolved = []
    unresolved = []
    for row in rows:
        name, frame = row['name'], row['frame']
        if name in tendons:
            continue
        if frame == 'variable':
            frame = guide_frame.get(name)
            if frame is None:
                unresolved.append(name)
                continue
            if frame == 'variable':
                unsolved.append(name)
                continue
        if frame == 'forearm':
            # Ground. Nothing moves it, so the module never names it.
            continue
        by_frame.setdefault(frame, []).append(name)
    assert not unresolved, f'bodies with no route group: {unresolved[:8]}'
    moved = sum(len(names) for names in by_frame.values())
    grounded = len(rows) - moved - len(unsolved) - len(tendons)
    assert grounded == 2093, grounded
    return ({frame: sorted(names) for frame, names in sorted(by_frame.items())}, sorted(unsolved))


def joint_table():
    return [{'name': j.name, 'parent': j.parent, 'origin': list(j.origin),
             'axis': list(j.axis), 'limits': list(j.limits), 'system': j.system}
            for j in JOINTS]


def fan_table():
    return {f.name: {'deg': NEUTRAL_FINGER_FAN[f.name],
                     'origin': [f.x, f.base_y, 0.],
                     'parent': 'palm_cup' if f.name == 'little' else 'wrist_flexion'}
            for f in FINGERS}


def rope_table():
    return [{'name': route['name'], 'joint': route['joint'], 'sign': tendon['sign'],
             'normal': [tendon['sign'], 0, 0], 'segments': route['path']}
            for route, tendon in zip(NEUTRAL_ROUTES, TENDONS)]


RUNTIME = r'''
// --- 4x4 rigid transforms, row-major, flat 16 -------------------------------
const I4 = () => [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
function mul(a, b) {
  const m = new Array(16);
  for (let r = 0; r < 4; r += 1) {
    for (let c = 0; c < 4; c += 1) {
      m[r * 4 + c] = a[r * 4] * b[c] + a[r * 4 + 1] * b[4 + c] + a[r * 4 + 2] * b[8 + c] + a[r * 4 + 3] * b[12 + c];
    }
  }
  return m;
}
// The inverse of a rigid transform, by transposing the rotation.
function inverse(m) {
  const t = [m[3], m[7], m[11]];
  return [
    m[0], m[4], m[8], -(m[0] * t[0] + m[4] * t[1] + m[8] * t[2]),
    m[1], m[5], m[9], -(m[1] * t[0] + m[5] * t[1] + m[9] * t[2]),
    m[2], m[6], m[10], -(m[2] * t[0] + m[6] * t[1] + m[10] * t[2]),
    0, 0, 0, 1
  ];
}
// lib.layout.rotation_matrix: a world-datum rotation about `axis` through `origin`.
function rotationMatrix(axis, deg, origin) {
  const n = Math.hypot(axis[0], axis[1], axis[2]);
  const [x, y, z] = [axis[0] / n, axis[1] / n, axis[2] / n];
  const th = deg * Math.PI / 180, c = Math.cos(th), s = Math.sin(th), t = 1 - c;
  const r = [
    t * x * x + c, t * x * y - s * z, t * x * z + s * y,
    t * x * y + s * z, t * y * y + c, t * y * z - s * x,
    t * x * z - s * y, t * y * z + s * x, t * z * z + c
  ];
  const [ox, oy, oz] = origin;
  return [
    r[0], r[1], r[2], ox - (r[0] * ox + r[1] * oy + r[2] * oz),
    r[3], r[4], r[5], oy - (r[3] * ox + r[4] * oy + r[5] * oz),
    r[6], r[7], r[8], oz - (r[6] * ox + r[7] * oy + r[8] * oz),
    0, 0, 0, 1
  ];
}

// lib.layout.assembled_transforms: every frame's world transform at a pose.
// Zero is the artifact as written, so this IS the delta from rest.
function assembledTransforms(pose) {
  const original = { forearm: I4() };
  for (const joint of JOINTS) {
    const raw = Number(pose[joint.name]) || 0;
    const q = Math.min(joint.limits[1], Math.max(joint.limits[0], raw));
    original[joint.name] = mul(original[joint.parent], rotationMatrix(joint.axis, q, joint.origin));
  }
  const result = { ...original };
  // Bodies are already placed in the fixed neutral fan, so a finger joint's
  // authored (unfanned) motion is conjugated by that fan.
  for (const [finger, fan] of Object.entries(FAN)) {
    const parent = original[fan.parent];
    const f = rotationMatrix([0, 0, 1], fan.deg, fan.origin);
    const conj = mul(mul(parent, f), inverse(parent));
    const unfan = inverse(f);
    for (const joint of JOINTS) {
      if (joint.system === finger) {
        result[joint.name] = mul(mul(conj, original[joint.name]), unfan);
      }
    }
  }
  return result;
}

// A rigid transform as the two calls the handle API takes: rotate about the
// world origin, then translate. Exact — R*x + t is the matrix itself.
function axisAngle(m) {
  const trace = m[0] + m[5] + m[10];
  const cos = Math.min(1, Math.max(-1, (trace - 1) / 2));
  const angle = Math.acos(cos);
  if (angle < 1e-9) {
    return null;
  }
  let axis;
  if (Math.PI - angle > 1e-4) {
    axis = [m[9] - m[6], m[2] - m[8], m[4] - m[1]];
  } else {
    // A half turn: the skew part vanishes, so read the axis off (R + I)/2,
    // whose columns are all parallel to it — take the longest.
    const d = [[m[0] + 1, m[4], m[8]], [m[1], m[5] + 1, m[9]], [m[2], m[6], m[10] + 1]];
    axis = d.reduce((best, col) => (Math.hypot(...col) > Math.hypot(...best) ? col : best), d[0]);
  }
  const n = Math.hypot(axis[0], axis[1], axis[2]);
  if (!(n > 1e-12)) {
    return null;
  }
  return { axis: [axis[0] / n, axis[1] / n, axis[2] / n], degrees: angle * 180 / Math.PI };
}

// Move every body of every frame the pose actually moves. A frame at rest is
// skipped whole, which is why the 2,045 forearm bodies cost nothing.
function applyPose(m, pose) {
  const transforms = assembledTransforms(pose);
  for (const [frame, names] of Object.entries(FRAME_BODIES)) {
    const matrix = transforms[frame];
    const rotation = axisAngle(matrix);
    const t = [matrix[3], matrix[7], matrix[11]];
    const moved = Math.hypot(t[0], t[1], t[2]) > 1e-9;
    if (!rotation && !moved) {
      continue;
    }
    for (const name of names) {
      const handle = m.get(name);
      if (rotation) {
        handle.rotate(rotation.axis, rotation.degrees, [0, 0, 0]);
      }
      if (moved) {
        handle.translate(t);
      }
    }
  }
}

// How far the pose is from rest, 0..1, as the largest excursion any joint is
// taking against its own travel. Drives the tendon fade below.
function poseExcursion(pose) {
  let most = 0;
  for (const joint of JOINTS) {
    const q = Number(pose[joint.name]) || 0;
    const span = q >= 0 ? joint.limits[1] : -joint.limits[0];
    if (span > 1e-9) {
      most = Math.max(most, Math.abs(q) / span);
    }
  }
  return Math.min(1, most);
}

// The tendons keep their neutral centerline — a posed route is a routing solve,
// not a transform (see this file's generator) — so they are shown where they
// are TRUE and faded where they would lie. At rest the full braided routing is
// on display; as the hand moves the cords drop away rather than trailing off
// the moved fingers claiming an attachment they no longer have. Through the
// fade, the pair driving each joint stays the brightest thing left, so which
// cords are pulling is still legible.
function applyTendons(m, pose, { braid = true } = {}) {
  const fade = 1 - 0.9 * poseExcursion(pose);
  // The guides that carry a tendon across a joint re-seat with the route, so
  // they are shown and faded on the same terms as the cords they carry.
  for (const name of UNSOLVED_BODIES) {
    if (fade < 0.12) {
      m.get(name).visible(false);
    } else {
      m.get(name).opacity(fade);
    }
  }
  for (const rope of ROPES) {
    const rest = { normal: rope.normal, segments: rope.segments };
    const handle = m.get(rope.name).deformTube({
      rest, path: rest, maxSegmentLength: 1000000,
      ...(braid ? { braid: { pitch: 0.8, depth: 0.022, strands: 8 } } : {})
    });
    const joint = JOINT_BY_NAME[rope.joint];
    const q = Number(pose[joint.name]) || 0;
    const span = q >= 0 ? joint.limits[1] : -joint.limits[0];
    const pull = span > 1e-9 ? Math.max(0, rope.sign * q) / span : 0;
    const opacity = fade * (0.3 + 0.7 * Math.min(1, pull * 1.6));
    // Below this it contributes nothing but a transparent draw, and 48 of them
    // sort every frame.
    if (opacity < 0.04) {
      handle.visible(false);
    } else {
      handle.opacity(opacity);
    }
  }
}

// --- choreography -----------------------------------------------------------
const FINGER_NAMES = ["index", "middle", "ring", "little"];
const clamp01 = (v) => Math.min(1, Math.max(0, v));
// Smooth start and stop, so a joint never snaps into or out of a hold.
const ease = (v) => { const u = clamp01(v); return u * u * (3 - 2 * u); };
// A ramp that rises over `rise`, holds, and falls over `fall`, within [0, 1].
function pulse(u, rise = 0.3, fall = 0.3) {
  const t = clamp01(u);
  if (t < rise) return ease(t / rise);
  if (t > 1 - fall) return ease((1 - t) / fall);
  return 1;
}
// One finger's curl: the three flexion joints in the ratio a real tendon-driven
// finger takes, so a full curl closes the fingertip onto the palm.
function curl(pose, finger, amount) {
  const a = clamp01(amount);
  pose[`${finger}_mcp_flexion`] = 88 * a;
  pose[`${finger}_pip`] = 105 * a;
  pose[`${finger}_dip`] = 72 * a;
}
function spread(pose, amount) {
  pose.index_mcp_abduction = -18 * amount;
  pose.middle_mcp_abduction = -4 * amount;
  pose.ring_mcp_abduction = 12 * amount;
  pose.little_mcp_abduction = 23 * amount;
}
function thumbOppose(pose, amount) {
  const a = clamp01(amount);
  pose.thumb_cmc_abduction = 40 * a;
  pose.thumb_cmc_flexion = 52 * a;
  pose.thumb_mcp_flexion = 40 * a;
  pose.thumb_ip = 30 * a;
}
'''

CLIPS = r'''
// Each clip is a pure function of t: every frame rebuilds the pose from
// scratch, so scrubbing, looping and a snapshot at any --time all agree.
const MOTIONS = [
  {
    id: "fist", label: "Make a fist", seconds: 6,
    pose(u) {
      const p = {};
      const close = pulse(u, 0.35, 0.35);
      // The little finger leads and the index trails, as a real hand closes.
      FINGER_NAMES.forEach((finger, i) => curl(p, finger, clamp01(close * 1.25 - (3 - i) * 0.08)));
      thumbOppose(p, Math.max(0, close - 0.25) / 0.75);
      spread(p, -0.35 * close);
      return p;
    }
  },
  {
    id: "wave", label: "Finger roll", seconds: 7,
    pose(u) {
      const p = {};
      // A travelling wave: each finger curls a fifth of a cycle after the last.
      FINGER_NAMES.forEach((finger, i) => {
        const phase = clamp01(u * 1.5 - i * 0.11);
        curl(p, finger, Math.sin(Math.PI * clamp01(phase * 1.4)) ** 2);
      });
      thumbOppose(p, 0.15 * pulse(u));
      return p;
    }
  },
  {
    id: "pinch", label: "Thumb-to-index pinch", seconds: 6,
    pose(u) {
      const p = {};
      const close = pulse(u, 0.4, 0.4);
      curl(p, "index", 0.42 * close);
      curl(p, "middle", 0.12 * close);
      thumbOppose(p, close);
      p.thumb_mcp_abduction = -10 * close;
      p.index_mcp_abduction = -14 * close;
      return p;
    }
  },
  {
    id: "spread", label: "Splay and gather", seconds: 5,
    pose(u) {
      const p = {};
      spread(p, pulse(u, 0.35, 0.35));
      FINGER_NAMES.forEach((finger) => curl(p, finger, 0.06 * pulse(u)));
      thumbOppose(p, 0.1 * pulse(u));
      return p;
    }
  },
  {
    id: "wrist", label: "Wrist flex and deviate", seconds: 6,
    pose(u) {
      const p = {};
      p.wrist_flexion = 52 * Math.sin(Math.PI * clamp01(u * 2));
      p.wrist_abduction = 16 * Math.sin(2 * Math.PI * u);
      p.palm_cup = 18 * pulse(u, 0.4, 0.4);
      FINGER_NAMES.forEach((finger) => curl(p, finger, 0.18 * pulse(u)));
      return p;
    }
  }
];

const TOTAL_SECONDS = MOTIONS.reduce((sum, motion) => sum + motion.seconds, 0);

// The pose at a time within the whole tour, with a short rest between motions
// so each one reads separately.
function tourPose(t) {
  let start = 0;
  for (const motion of MOTIONS) {
    if (t < start + motion.seconds) {
      return motion.pose((t - start) / motion.seconds);
    }
    start += motion.seconds;
  }
  return {};
}

export const clips = {
  showcase: {
    label: "Showcase — every motion the tendons drive",
    duration: TOTAL_SECONDS,
    loop: true,
    update(t, m) {
      const pose = tourPose(t);
      applyPose(m, pose);
      applyTendons(m, pose);
    }
  },
  ...Object.fromEntries(MOTIONS.map((motion) => [motion.id, {
    label: motion.label,
    duration: motion.seconds,
    loop: true,
    update(t, m) {
      const pose = motion.pose(t / motion.seconds);
      applyPose(m, pose);
      applyTendons(m, pose);
    }
  }])),
  presentation: {
    label: "Braided surface study",
    duration: 1,
    loop: false,
    update(t, m) {
      applyTendons(m, {});
    }
  }
};
'''


def write_module(path: Path, joints, fan, frames, unsolved, ropes) -> int:
    dumps = lambda value: json.dumps(value, separators=(',', ':'))  # noqa: E731
    text = (
        '// Generated by validation/anthropomorphic_hand/write_showcase_presentation.py.\n'
        '// Authored joint datums and body frames from the build; edit the generator.\n'
        f'const JOINTS = {dumps(joints)};\n'
        'const JOINT_BY_NAME = Object.fromEntries(JOINTS.map((j) => [j.name, j]));\n'
        f'const FAN = {dumps(fan)};\n'
        f'const FRAME_BODIES = {dumps(frames)};\n'
        f'const UNSOLVED_BODIES = {dumps(unsolved)};\n'
        f'const ROPES = {dumps(ropes)};\n'
        + RUNTIME + CLIPS
    )
    path.write_text(text)
    return len(text)


def main() -> None:
    joints, fan, ropes = joint_table(), fan_table(), rope_table()
    frames, unsolved = frame_bodies()
    folder = ROOT / 'STEP/anthropomorphic_hand'
    for name in TARGETS:
        size = write_module(folder / f'{name}.step.js', joints, fan, frames, unsolved, ropes)
    print(f'wrote {len(TARGETS)} render modules, {size} bytes each: '
          f'{len(joints)} joints, {sum(len(v) for v in frames.values())} moved bodies '
          f'over {len(frames)} frames, {len(ropes)} tendons, {len(unsolved)} faded guides')


if __name__ == '__main__':
    main()
