// Stellated icosahedron — twenty spikes, and the source model for the CAD
// Viewer / docs favicon.
//
// Same construction as the twelve-spike small stellated dodecahedron, moved onto
// an icosahedral core: a stellation extends the ORIGINAL face planes, so every
// face lies in one of the core's own twenty planes and no new plane appears.
//
// With unit face normals n_i, let g_i = dot(p, n_i). A point is in the core when
// every g_i <= size, and in the spike raised on face i when g_i > size while
// every OTHER plane still contains it. So with g1 the largest g and g2 the
// second largest:
//
//   core  = g1 - size
//   spike = max(size - g1, g2 - size)
//   solid = min(core, spike)
//
// which needs only the two largest plane distances — no per-face neighbour
// table. Each icosahedron face has three neighbours, so the spikes are
// triangular in section and their flat tips are triangles.
//
// Two stylistic knobs extend that:
//
// * `sharpness` TILTS the side planes rather than offsetting them. Offsetting
//   only fattens a spike until the constraint stops binding and it degenerates
//   into a prism; the taper is set by the angle between a side plane and the
//   spike axis. A plane tilted away from the axis has normal n_j - k*n_i, whose
//   distance is the linear combination g2 - k*g1 (divided by that normal's
//   length). Larger k lays the sides closer to parallel with the axis, so the
//   spike narrows and runs out further.
//
//   Adjacent icosahedron face normals sit at cos = 0.745, much closer together
//   than the dodecahedron's 0.447, so the untilted stellation is only a shallow
//   bump (tips at 1.34 * size). Twenty spikes therefore NEED a high sharpness to
//   read as spikes at all. At k -> cos(theta) the sides become parallel and the
//   tip escapes to infinity, so k is capped safely below it.
//
// * `tipFlat` intersects everything with a large icosahedron (g1 <= tipCut).
//   Because the cut plane for each spike is that spike's OWN plane, it is
//   perpendicular to the spike axis — so every tip loses its point to a flat
//   triangular face, all twenty at the same height. 1.0 leaves them sharp.
//
// With either knob off its default the shape is a stylized stellation rather
// than the exact solid.

const PHI = (1 + Math.sqrt(5)) / 2;

function unit(v) {
  const length = Math.hypot(v[0], v[1], v[2]);
  return v.map((component) => component / length);
}

function directionKey(v) {
  // -0 and 0 must not read as distinct directions.
  return v.map((component) => (Math.abs(component) < 1e-12 ? 0 : component).toFixed(9)).join(",");
}

// The twenty icosahedron face normals are the dodecahedron vertex directions:
// the cube corners (±1, ±1, ±1) plus the cyclic rotations of (0, ±1/PHI, ±PHI).
function icosahedronFaceNormals() {
  const seen = new Map();
  const add = (v) => {
    const normal = unit(v);
    const key = directionKey(normal);
    if (!seen.has(key)) {
      seen.set(key, normal);
    }
  };

  for (const sx of [1, -1]) {
    for (const sy of [1, -1]) {
      for (const sz of [1, -1]) {
        add([sx, sy, sz]);
      }
    }
  }
  for (let rotation = 0; rotation < 3; rotation += 1) {
    const base = [0, 1 / PHI, PHI];
    const rotated = [base[rotation % 3], base[(rotation + 1) % 3], base[(rotation + 2) % 3]];
    // Sign every slot: the zero lands in a different slot each rotation, and
    // flipping only two fixed slots would silently halve two of the three sets.
    for (const sx of [1, -1]) {
      for (const sy of [1, -1]) {
        for (const sz of [1, -1]) {
          add([rotated[0] * sx, rotated[1] * sy, rotated[2] * sz]);
        }
      }
    }
  }
  return [...seen.values()];
}

const FACE_NORMALS = icosahedronFaceNormals();

if (FACE_NORMALS.length !== 20) {
  throw new Error(`expected 20 icosahedron face normals, built ${FACE_NORMALS.length}`);
}

// Derive the adjacent-face angle from the normals themselves rather than
// hardcoding it, so the constant can never drift from the geometry.
const ADJACENT_COS = FACE_NORMALS.reduce((best, a, index) => {
  for (let other = index + 1; other < FACE_NORMALS.length; other += 1) {
    const b = FACE_NORMALS[other];
    const dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    if (dot < 0.999 && dot > best) {
      return dot;
    }
  }
  return best;
}, -1);

const MAX_SHARPNESS = Number((ADJACENT_COS - 0.05).toFixed(3));

const PLANE_ACCUMULATORS = FACE_NORMALS
  .map((n) => `  accum(dot(p, vec3(${n.map((c) => c.toFixed(8)).join(", ")})), g1, g2);`)
  .join("\n");

const GLSL = `
const float ADJACENT_COS = ${ADJACENT_COS.toFixed(10)}; // cos between adjacent icosahedron face normals

// Track the two largest plane distances in one pass.
void accum(float g, inout float g1, inout float g2) {
  if (g > g1) {
    g2 = g1;
    g1 = g;
  } else if (g > g2) {
    g2 = g;
  }
}

float sdf(vec3 p) {
  float g1 = -1e9;
  float g2 = -1e9;
${PLANE_ACCUMULATORS}

  // Side planes tilted away from the spike axis: normal n_j - sharpness * n_i.
  float sideNorm = sqrt(1.0 + sharpness * sharpness - 2.0 * sharpness * ADJACENT_COS);
  float core = g1 - size;
  float spike = max(size - g1, (g2 - sharpness * g1) / sideNorm - size);
  float solid = min(core, spike);

  // Slice every tip at the same height. The cut plane for a spike is its own
  // face plane, so it lands square across the spike axis.
  float tipReach = size * sideNorm / max(ADJACENT_COS - sharpness, 1e-4);
  return max(solid, g1 - tipReach * tipFlat);
}

vec3 color(vec3 p, vec3 normal) {
  vec3 n = normalize(normal);
  vec3 key = normalize(vec3(-0.32, -0.48, 0.82));
  float facing = clamp(dot(n, key) * 0.5 + 0.5, 0.0, 1.0);

  vec3 body = mix(shadeColor, coreColor, smoothstep(0.06, 0.70, facing));
  return mix(body, glowColor, smoothstep(0.74, 1.0, facing) * 0.85);
}
`;

export default {
  schema: "implicit.js/0.1.0",
  name: "stellated icosahedron",
  description:
    "Twenty triangular spikes raised on an icosahedral core, bounded entirely by the core's own face planes.",
  units: "mm",
  params: {
    size: { type: "number", label: "Core inradius", min: 4, max: 24, step: 0.25, default: 10, unit: "mm" },
    sharpness: {
      type: "number",
      label: "Spike sharpness",
      description: "Tilt of the side planes away from the spike axis. 0 is the exact stellation; higher is pointier.",
      min: 0,
      max: MAX_SHARPNESS,
      step: 0.005,
      default: 0.69
    },
    tipFlat: {
      type: "number",
      label: "Tip flat",
      description: "Fraction of the spike kept. 1.0 leaves the points sharp; lower slices a flat face on each tip.",
      min: 0.35,
      max: 1,
      step: 0.01,
      default: 0.6
    },
    coreColor: { type: "color", label: "Core color", default: "#1e7bff" },
    shadeColor: { type: "color", label: "Shade color", default: "#03104a" },
    glowColor: { type: "color", label: "Glow color", default: "#5ff0ff" }
  },
  bounds: ({ params }) => {
    // The flat cut, not the virtual apex, is the real extent — sizing to the
    // apex would leave the model floating in a box far larger than the solid.
    const k = Math.min(params.sharpness, ADJACENT_COS - 1e-3);
    const sideNorm = Math.sqrt(1 + k * k - 2 * k * ADJACENT_COS);
    const tipReach = (params.size * sideNorm) / (ADJACENT_COS - k);
    const reach = tipReach * params.tipFlat * 1.06;
    return [[-reach, -reach, -reach], [reach, reach, reach]];
  },
  render: ({ params }) => ({
    steps: 256,
    stepScale: 0.8,
    epsilon: Math.max(params.size * 0.0004, 0.003),
    normalEpsilon: Math.max(params.size * 0.003, 0.02)
  }),
  glsl: GLSL
};
