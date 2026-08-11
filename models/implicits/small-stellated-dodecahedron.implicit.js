// Small stellated dodecahedron — one of the four Kepler-Poinsot solids, and the
// source model for the CAD Viewer / docs favicon.
//
// Twelve pentagonal-pyramid spikes raised on a dodecahedral core. A stellation
// extends the ORIGINAL face planes, so every face of the solid lies in one of
// the twelve dodecahedron planes and no new plane is ever introduced.
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
// which needs only the two largest plane distances — no per-face neighbour table.
//
// Two stylistic knobs extend that:
//
// * `sharpness` TILTS the side planes rather than offsetting them. Offsetting
//   only fattens a spike until the constraint stops binding and it degenerates
//   into a prism; the taper is set by the angle between a side plane and the
//   spike axis. A plane tilted away from the axis has normal n_j - k*n_i, whose
//   distance is the linear combination g2 - k*g1 (divided by that normal's
//   length). Larger k lays the sides closer to parallel with the axis, so the
//   spike narrows and runs out further. At k = 0 this is the exact
//   Kepler-Poinsot solid; at k -> cos(theta) = 1/sqrt(5) the sides become
//   parallel and the tip escapes to infinity, so k is capped safely below it.
//
// * `tipFlat` intersects everything with a large dodecahedron (g1 <= tipCut).
//   Because the cut plane for each spike is that spike's OWN plane, it is
//   perpendicular to the spike axis — so every tip loses its point to a flat
//   pentagonal face, all twelve at the same height. 1.0 leaves them sharp.
//
// With either knob off its default the shape is a stylized stellation rather
// than the exact solid.

const PHI = (1 + Math.sqrt(5)) / 2;

function unit(v) {
  const length = Math.hypot(v[0], v[1], v[2]);
  return v.map((component) => component / length);
}

// The twelve dodecahedron face normals are the icosahedron vertex directions:
// every sign and cyclic rotation of (0, 1, PHI).
function dodecahedronFaceNormals() {
  const seen = new Map();
  for (let rotation = 0; rotation < 3; rotation += 1) {
    const base = [0, 1, PHI];
    const rotated = [base[rotation % 3], base[(rotation + 1) % 3], base[(rotation + 2) % 3]];
    for (const sx of [1, -1]) {
      for (const sy of [1, -1]) {
        for (const sz of [1, -1]) {
          const normal = unit([rotated[0] * sx, rotated[1] * sy, rotated[2] * sz]);
          // -0 and 0 must not read as distinct directions.
          const key = normal.map((component) => (Math.abs(component) < 1e-12 ? 0 : component).toFixed(9)).join(",");
          if (!seen.has(key)) {
            seen.set(key, normal);
          }
        }
      }
    }
  }
  return [...seen.values()];
}

const FACE_NORMALS = dodecahedronFaceNormals();

// A fixed, seeded jitter per face in [-1, 1]. Seeded rather than Math.random so
// the solid is identical on every load — an unseeded value would silently
// reshape the model (and the favicon built from it) on each regeneration.
function seededJitters(count, seed = 0x5eed1e) {
  const values = [];
  let state = seed >>> 0;
  for (let index = 0; index < count; index += 1) {
    // xorshift32
    state ^= state << 13; state >>>= 0;
    state ^= state >>> 17;
    state ^= state << 5; state >>>= 0;
    values.push((state / 0xffffffff) * 2 - 1);
  }
  return values;
}

const FACE_JITTERS = seededJitters(FACE_NORMALS.length);

const PLANE_ACCUMULATORS = FACE_NORMALS
  .map((n, index) => `  accum(dot(p, vec3(${n.map((c) => c.toFixed(8)).join(", ")})), ${FACE_JITTERS[index].toFixed(5)}, g1, g2, j1);`)
  .join("\n");

const GLSL = `
const float ADJACENT_COS = 0.4472135954999579; // 1/sqrt(5): cos between adjacent face normals

// Track the two largest plane distances in one pass, carrying the winning
// face's jitter so the tip cut can vary per spike.
void accum(float g, float j, inout float g1, inout float g2, inout float j1) {
  if (g > g1) {
    g2 = g1;
    g1 = g;
    j1 = j;
  } else if (g > g2) {
    g2 = g;
  }
}

float sdf(vec3 p) {
  float g1 = -1e9;
  float g2 = -1e9;
  float j1 = 0.0;
${PLANE_ACCUMULATORS}

  // Side planes tilted away from the spike axis: normal n_j - sharpness * n_i.
  float sideNorm = sqrt(1.0 + sharpness * sharpness - 2.0 * sharpness * ADJACENT_COS);
  float core = g1 - size;
  float spike = max(size - g1, (g2 - sharpness * g1) / sideNorm - size);
  float solid = min(core, spike);

  // Slice each tip square across its own spike axis, at a height nudged by that
  // face's fixed jitter so the twelve flats sit at slightly different distances.
  float tipReach = size * sideNorm / max(ADJACENT_COS - sharpness, 1e-4);
  float tipCut = tipReach * tipFlat * (1.0 + j1 * tipJitter);
  return max(solid, g1 - tipCut);
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
  name: "small stellated dodecahedron",
  description:
    "Kepler-Poinsot solid: twelve pentagonal-pyramid spikes raised on a dodecahedral core, bounded entirely by the core's own face planes.",
  units: "mm",
  params: {
    size: { type: "number", label: "Core inradius", min: 4, max: 24, step: 0.25, default: 10, unit: "mm" },
    sharpness: {
      type: "number",
      label: "Spike sharpness",
      description: "Tilt of the side planes away from the spike axis. 0 is the exact Kepler-Poinsot solid; higher is pointier.",
      min: 0,
      max: 0.42,
      step: 0.005,
      default: 0.3
    },
    tipFlat: {
      type: "number",
      label: "Tip flat",
      description: "Fraction of the spike kept. 1.0 leaves the points sharp; lower slices a flat face on each tip.",
      min: 0.35,
      max: 1,
      step: 0.01,
      default: 0.72
    },
    tipJitter: {
      type: "number",
      label: "Tip jitter",
      description: "Per-spike variation in cut height, as a fraction. 0 puts every flat at the same distance.",
      min: 0,
      max: 0.25,
      step: 0.005,
      default: 0.1
    },
    coreColor: { type: "color", label: "Core color", default: "#1e7bff" },
    shadeColor: { type: "color", label: "Shade color", default: "#03104a" },
    glowColor: { type: "color", label: "Glow color", default: "#5ff0ff" }
  },
  bounds: ({ params }) => {
    // The flat cut, not the virtual apex, is the real extent — sizing to the
    // apex would leave the model floating in a box far larger than the solid.
    const adjacentCos = 1 / Math.sqrt(5);
    const k = Math.min(params.sharpness, adjacentCos - 1e-3);
    const sideNorm = Math.sqrt(1 + k * k - 2 * k * adjacentCos);
    const tipReach = (params.size * sideNorm) / (adjacentCos - k);
    // Size to the LONGEST jittered spike, or the tallest ones get clipped.
    const reach = tipReach * params.tipFlat * (1 + params.tipJitter) * 1.06;
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
