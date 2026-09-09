
// A render module may export only what the renderer knows — an unknown export
// is a load error, not something ignored — so everything below is private and
// `clips` is the one export.

// --- 4x4 rigid transforms, row-major, flat 16 -------------------------------
const I4 = () => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

function mul(a, b) {
  const m = new Array(16);
  for (let r = 0; r < 4; r += 1) {
    for (let c = 0; c < 4; c += 1) {
      m[r * 4 + c] = a[r * 4] * b[c] + a[r * 4 + 1] * b[4 + c] + a[r * 4 + 2] * b[8 + c] + a[r * 4 + 3] * b[12 + c];
    }
  }
  return m;
}

// The inverse of a rigid transform, by transposing its 3x3. The actuator
// placement's 3x3 is diag(sign, 1, sign) — a REFLECTION when sign is -1 — and
// the transpose is still its inverse, so this holds for those too.
function inverse(m) {
  const t = [m[3], m[7], m[11]];
  return [
    m[0], m[4], m[8], -(m[0] * t[0] + m[4] * t[1] + m[8] * t[2]),
    m[1], m[5], m[9], -(m[1] * t[0] + m[5] * t[1] + m[9] * t[2]),
    m[2], m[6], m[10], -(m[2] * t[0] + m[6] * t[1] + m[10] * t[2]),
    0, 0, 0, 1
  ];
}

function translation(point) {
  return [1, 0, 0, point[0], 0, 1, 0, point[1], 0, 0, 1, point[2], 0, 0, 0, 1];
}

// lib.layout.rotation_matrix: a world-datum rotation about `axis` through `origin`.
function rotationMatrix(axis, deg, origin) {
  const n = Math.hypot(axis[0], axis[1], axis[2]);
  const [x, y, z] = [axis[0] / n, axis[1] / n, axis[2] / n];
  const th = deg * Math.PI / 180;
  const c = Math.cos(th);
  const s = Math.sin(th);
  const t = 1 - c;
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

// A rigid transform as the two calls the handle API takes: rotate about the
// world origin, then translate. Exact — R*x + t IS the matrix.
function axisAngle(m) {
  const trace = m[0] + m[5] + m[10];
  const angle = Math.acos(Math.min(1, Math.max(-1, (trace - 1) / 2)));
  if (angle < 1e-9) {
    return null;
  }
  let axis;
  if (Math.PI - angle > 1e-4) {
    axis = [m[9] - m[6], m[2] - m[8], m[4] - m[1]];
  } else {
    // A half turn: the skew part vanishes, so read the axis off (R + I)/2,
    // whose columns are all parallel to it — take the longest.
    const columns = [[m[0] + 1, m[4], m[8]], [m[1], m[5] + 1, m[9]], [m[2], m[6], m[10] + 1]];
    axis = columns.reduce((best, col) => (Math.hypot(...col) > Math.hypot(...best) ? col : best), columns[0]);
  }
  const n = Math.hypot(axis[0], axis[1], axis[2]);
  return n > 1e-12
    ? { axis: [axis[0] / n, axis[1] / n, axis[2] / n], degrees: angle * 180 / Math.PI }
    : null;
}

function applyMatrix(handle, m) {
  const rotation = axisAngle(m);
  if (rotation) {
    handle.rotate(rotation.axis, rotation.degrees, [0, 0, 0]);
  }
  const t = [m[3], m[7], m[11]];
  if (Math.hypot(t[0], t[1], t[2]) > 1e-9) {
    handle.translate(t);
  }
}

function isMoving(m) {
  return axisAngle(m) !== null || Math.hypot(m[3], m[7], m[11]) > 1e-9;
}

// --- forward kinematics -----------------------------------------------------

// lib.layout.assembled_transforms. The artifact is written at pose zero, so a
// frame's transform at a pose IS its delta from rest.
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
    const conjugate = mul(mul(parent, f), inverse(parent));
    const unfan = inverse(f);
    for (const joint of JOINTS) {
      if (joint.system === finger) {
        result[joint.name] = mul(mul(conjugate, original[joint.name]), unfan);
      }
    }
  }
  return result;
}

function applyPose(m, pose) {
  const transforms = assembledTransforms(pose);
  for (const [frame, names] of Object.entries(FRAME_BODIES)) {
    const matrix = transforms[frame];
    if (!isMoving(matrix)) {
      continue;
    }
    for (const name of names) {
      applyMatrix(m.get(name), matrix);
    }
  }
}

// --- actuators --------------------------------------------------------------

// A port of lib.actuator_kinematics.actuator_transform. The fixed-ring 12/12/36
// planetary has a sun/carrier ratio of 4, and a planet orbits with the carrier
// while spinning at -3 times the carrier rate about its own pin. ACTUATOR_SAMPLES
// pins this port against the Python it was ported from, checked at load.
const OUTPUT_ROLES = new Set([
  "gearbox_carrier", "gearbox_spindle", "capstan", "terminal_ferrule",
  "capstan_terminal_bond_line", "capstan_retainer_screw"
]);
const INPUT_ROLES = new Set(["gearbox_sun", "motor_shaft"]);

function rotationZ(q) {
  const c = Math.cos(q);
  const s = Math.sin(q);
  return [c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
}

function actuatorPlacement(tendon) {
  const placement = translation(tendon.center);
  placement[0] = tendon.sign;
  placement[10] = tendon.sign;
  return placement;
}

function actuatorTransform(tendon, role, q) {
  let local;
  if (OUTPUT_ROLES.has(role) || role.startsWith("gearbox_planet_pin_")) {
    local = rotationZ(q);
  } else if (INPUT_ROLES.has(role)) {
    local = rotationZ(4 * q);
  } else if (role.startsWith("gearbox_planet_")) {
    const index = Number(role.slice(role.lastIndexOf("_") + 1)) - 1;
    const angle = index * 2 * Math.PI / 3;
    const center = [3 * Math.cos(angle), 3 * Math.sin(angle), 0];
    local = mul(mul(mul(rotationZ(q), translation(center)), rotationZ(-3 * q)),
      translation([-center[0], -center[1], -center[2]]));
  } else {
    return null;
  }
  const placement = actuatorPlacement(tendon);
  return mul(mul(placement, local), inverse(placement));
}

for (const sample of ACTUATOR_SAMPLES) {
  const ported = actuatorTransform(TENDONS[sample.tendon], sample.role, sample.q);
  const worst = Math.max(...sample.m.map((value, index) => Math.abs(value - ported[index])));
  if (!(worst < 1e-7)) {
    throw new Error(`actuator transform port disagrees with the generator for `
      + `${sample.role} at q=${sample.q}: worst element differs by ${worst}`);
  }
}

function applyActuators(m, rotations) {
  for (const [name, [index, role]] of Object.entries(ACTUATOR_BODIES)) {
    const q = rotations[index];
    if (Math.abs(q) < 1e-9) {
      continue;
    }
    const matrix = actuatorTransform(TENDONS[index], role, q);
    if (matrix) {
      applyMatrix(m.get(name), matrix);
    }
  }
}

// --- the baked timeline -----------------------------------------------------
// Poses, capstan angles and posed route geometry all sit on ONE grid, so a
// frame between two keyframes interpolates every one of them together and the
// cords cannot drift out of step with the fingers.

function bracket(t) {
  const last = KEYFRAMES.length - 1;
  const clamped = Math.min(KEYFRAMES[last].t, Math.max(0, t));
  let high = 1;
  while (high < last && KEYFRAMES[high].t < clamped) {
    high += 1;
  }
  const low = high - 1;
  const span = KEYFRAMES[high].t - KEYFRAMES[low].t;
  return { low: KEYFRAMES[low], high: KEYFRAMES[high], alpha: span > 0 ? (clamped - KEYFRAMES[low].t) / span : 0 };
}

function blendedPose(low, high, alpha) {
  const pose = {};
  for (const key of new Set([...Object.keys(low.pose), ...Object.keys(high.pose)])) {
    pose[key] = (low.pose[key] || 0) * (1 - alpha) + (high.pose[key] || 0) * alpha;
  }
  return pose;
}

// One rope's analytic centerline, poured back into the segment kinds the
// generator flattened the solved route into. Only Beziers and lines reach here:
// an arc's center/axis/start/sweep do not survive a blend between two keyframes
// (see arc_to_beziers in the generator), while a Bezier's explicit endpoints
// blend to the same place from either side of a join and keep the chain sealed.
function pathFromNumbers(index, numbers) {
  const segments = [];
  let at = 0;
  for (const kind of ROPE_TEMPLATES[index]) {
    if (kind === "bezier") {
      segments.push({
        kind,
        points: [
          [numbers[at], numbers[at + 1], numbers[at + 2]],
          [numbers[at + 3], numbers[at + 4], numbers[at + 5]],
          [numbers[at + 6], numbers[at + 7], numbers[at + 8]],
          [numbers[at + 9], numbers[at + 10], numbers[at + 11]]
        ]
      });
      at += 12;
    } else if (kind === "line") {
      segments.push({
        kind,
        start: [numbers[at], numbers[at + 1], numbers[at + 2]],
        end: [numbers[at + 3], numbers[at + 4], numbers[at + 5]]
      });
      at += 6;
    } else {
      throw new Error(`unexpected segment kind ${kind}: the generator flattens arcs`);
    }
  }
  return { normal: ROPE_NORMALS[index], segments: sealTangents(segments) };
}

// Blending two solved routes number by number keeps every JOIN exact — a shared
// endpoint is one number blended once — but not every TANGENT: two segments
// meeting in line at both keyframes generally meet at a slight angle in
// between, and `compileTubePath` refuses a turn of more than about 1e-7. So the
// blend is followed by a seal that turns the two handles at each join back onto
// their bisector, keeping the shared point and both handle lengths. The
// correction is the misalignment itself — thousandths of a degree at this
// keyframe rate — and it moves a control point, never an endpoint.
const sub3 = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add3 = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scale3 = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const norm3 = (a) => Math.hypot(a[0], a[1], a[2]);

function endTangent(segment) {
  return segment.kind === "bezier"
    ? sub3(segment.points[3], segment.points[2])
    : sub3(segment.end, segment.start);
}

function startTangent(segment) {
  return segment.kind === "bezier"
    ? sub3(segment.points[1], segment.points[0])
    : sub3(segment.end, segment.start);
}

function sealTangents(segments) {
  for (let i = 1; i < segments.length; i += 1) {
    const before = segments[i - 1];
    const after = segments[i];
    // A line's direction is its endpoints, which are joins and must not move.
    // Two lines in a row therefore cannot be sealed — and never occur in these
    // routes, so the compile complaining would be the right outcome.
    if (before.kind !== "bezier" && after.kind !== "bezier") {
      continue;
    }
    const incoming = endTangent(before);
    const outgoing = startTangent(after);
    const inLength = norm3(incoming);
    const outLength = norm3(outgoing);
    if (!(inLength > 0) || !(outLength > 0)) {
      continue;
    }
    const iu = scale3(incoming, 1 / inLength);
    const ou = scale3(outgoing, 1 / outLength);
    let direction;
    if (before.kind !== "bezier") {
      direction = iu;
    } else if (after.kind !== "bezier") {
      direction = ou;
    } else {
      const bisector = add3(iu, ou);
      const length = norm3(bisector);
      if (!(length > 0)) {
        continue;
      }
      direction = scale3(bisector, 1 / length);
    }
    if (before.kind === "bezier") {
      before.points[2] = sub3(before.points[3], scale3(direction, inLength));
    }
    if (after.kind === "bezier") {
      after.points[1] = add3(after.points[0], scale3(direction, outLength));
    }
  }
  return segments;
}

// The neutral centerline each rope's swept solid was built on. Deformation maps
// normalized arc length from this to the posed one.
const REST_PATHS = ROPE_BASE.map((numbers, index) => pathFromNumbers(index, numbers));

// Where each rope's moving numbers start inside a keyframe's flat `v`.
const ROPE_OFFSETS = ROPE_VARYING.reduce((offsets, positions) => {
  offsets.push(offsets[offsets.length - 1] + positions.length);
  return offsets;
}, [0]);

// Longitudinal refinement, in mm. A tendon bends only where it crosses a joint,
// but refinement is one-time and covers the whole tube, so this trades vertices
// on the straight runs for a smooth bend at the knuckles.
//
// It is also the lever that decides whether a morph bake fits on a GPU. Every
// refined vertex costs one RGBA32F texel per morph target per attribute, so at
// 3 mm the 48 cords came to 697,924 refined vertices and 694.6 MiB of morph
// texture for one 6 s clip — past cadgen's 512 MiB playback ceiling, and the
// export refuses. 9 mm cuts the vertex count by a third, and it is the RIGHT
// lever: chord and angular tolerance shrink a cord's circumference, which is
// what the morph texture is priced on, so tightening them makes cord FIDELITY
// worse, not better. Longitudinal facets barely show on a 0.6 mm tube; a path
// error of a few mm shows as the cord sinking through a drum. Trade the first
// for the second and keep the path
// tolerance at 1 mm, which is the right way round: a cord's SHAPE error is far
// more visible than its facet count, since the tube is only 0.6 mm across.
const TUBE_REFINEMENT = 9;
const BRAID = { pitch: 0.8, depth: 0.022, strands: 8 };

function applyTendons(m, low, high, alpha) {
  for (let index = 0; index < ROPE_NAMES.length; index += 1) {
    const numbers = ROPE_BASE[index].slice();
    const positions = ROPE_VARYING[index];
    const offset = ROPE_OFFSETS[index];
    for (let i = 0; i < positions.length; i += 1) {
      numbers[positions[i]] = low.v[offset + i] * (1 - alpha) + high.v[offset + i] * alpha;
    }
    m.get(ROPE_NAMES[index]).deformTube({
      rest: REST_PATHS[index],
      path: pathFromNumbers(index, numbers),
      maxSegmentLength: TUBE_REFINEMENT,
      braid: BRAID
    });
  }
}

// --- clips ------------------------------------------------------------------

// A guide that bridges two frames is placed by the routing, so the generator
// fits the rigid motion of the span it guides (Kabsch) and bakes it here. The
// blend of two rotations element by element is not itself a rotation, so the
// 3x3 is re-orthogonalized before it is handed over — a hair at this keyframe
// rate, and a squashed pulley without it.
function applyGuides(m, low, high, alpha) {
  for (let index = 0; index < GUIDE_BODIES.length; index += 1) {
    const at = index * 12;
    const blended = new Array(12);
    for (let i = 0; i < 12; i += 1) {
      blended[i] = low.g[at + i] * (1 - alpha) + high.g[at + i] * alpha;
    }
    const rows = [blended.slice(0, 3), blended.slice(4, 7), blended.slice(8, 11)];
    // Gram-Schmidt the three rows back onto an orthonormal basis.
    const r0 = scale3(rows[0], 1 / (norm3(rows[0]) || 1));
    let r1 = sub3(rows[1], scale3(r0, r0[0] * rows[1][0] + r0[1] * rows[1][1] + r0[2] * rows[1][2]));
    r1 = scale3(r1, 1 / (norm3(r1) || 1));
    const r2 = [r0[1] * r1[2] - r0[2] * r1[1], r0[2] * r1[0] - r0[0] * r1[2], r0[0] * r1[1] - r0[1] * r1[0]];
    applyMatrix(m.get(GUIDE_BODIES[index]), [
      r0[0], r0[1], r0[2], blended[3],
      r1[0], r1[1], r1[2], blended[7],
      r2[0], r2[1], r2[2], blended[11],
      0, 0, 0, 1
    ]);
  }
}

// Sealed inside their gearbox housings and therefore never visible, while
// costing 59% of the model's triangles. Marked hidden every frame so an export
// asked for `drop: ["visible"]` leaves them out of the file, and so a renderer
// is not paying to draw geometry behind an opaque wall.
function hideInternals(m) {
  for (const name of HIDDEN_BODIES) {
    m.get(name).visible(false);
  }
}

function applyAt(m, t) {
  hideInternals(m);
  const { low, high, alpha } = bracket(t);
  applyPose(m, blendedPose(low, high, alpha));
  applyActuators(m, low.q.map((value, index) => value * (1 - alpha) + high.q[index] * alpha));
  applyGuides(m, low, high, alpha);
  applyTendons(m, low, high, alpha);
}

const TOUR_SECONDS = MOTIONS.reduce((sum, motion) => sum + motion.seconds, 0);

function motionStart(id) {
  let start = 0;
  for (const motion of MOTIONS) {
    if (motion.id === id) {
      return start;
    }
    start += motion.seconds;
  }
  return 0;
}

export const clips = {
  showcase: {
    label: "Showcase — the tendons driving every motion",
    duration: TOUR_SECONDS,
    loop: true,
    update(t, m) {
      applyAt(m, t);
    }
  },
  ...Object.fromEntries(MOTIONS.map((motion) => {
    const start = motionStart(motion.id);
    return [motion.id, {
      label: motion.label,
      duration: motion.seconds,
      loop: true,
      update(t, m) {
        applyAt(m, start + Math.min(motion.seconds, Math.max(0, t)));
      }
    }];
  })),
  presentation: {
    label: "Braided routing at rest",
    duration: 1,
    loop: false,
    update(t, m) {
      applyAt(m, 0);
    }
  }
};
