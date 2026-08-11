const GLSL = `
// First stellation of the rhombic dodecahedron ("Escher's solid").
//
// A stellation extends the ORIGINAL face planes, so the whole solid is bounded
// by nothing but the rhombic dodecahedron's own twelve planes. For the core
//   max(|x|+|y|, |y|+|z|, |z|+|x|) <= size
// the spike raised on face x+y=size is the cone cut by its four neighbouring
// planes (x±z=size, y±z=size), and those meet at exactly (size, size, 0) — the
// apex. So each spike is an exact convex pyramid, not a fitted approximation.
//
// Reflecting into the positive octant with abs() collapses the twelve spikes to
// three representatives, one per axis pair, because the solid carries the full
// symmetry of the octahedral group.

const float STELLATED_RD_PLANE_NORM = 0.7071067811865476; // 1/sqrt(2): plane normals are (1,1,0)

float sdf(vec3 p) {
  vec3 q = abs(p);

  // Convex core: the rhombic dodecahedron itself.
  float core = max(max(q.x + q.y, q.y + q.z), q.z + q.x) - size;

  // Spike over the (1,1,0) family: bounded by x+z and y+z, standing on x+y.
  float spikeXY = max(max(q.x + q.z - size, q.y + q.z - size), spikeBase * size - (q.x + q.y));
  // Over (0,1,1): bounded by y+x and z+x, standing on y+z.
  float spikeYZ = max(max(q.y + q.x - size, q.z + q.x - size), spikeBase * size - (q.y + q.z));
  // Over (1,0,1): bounded by x+y and z+y, standing on x+z.
  float spikeXZ = max(max(q.x + q.y - size, q.z + q.y - size), spikeBase * size - (q.x + q.z));

  float solid = min(min(core, spikeXY), min(spikeYZ, spikeXZ));

  // Planes carry a sqrt(2) gradient; rescale so the field reads as a distance.
  return solid * STELLATED_RD_PLANE_NORM;
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
  name: "stellated rhombic dodecahedron",
  description:
    "First stellation of the rhombic dodecahedron (Escher's solid): twelve four-sided spikes along the cube-edge directions.",
  units: "mm",
  params: {
    size: { type: "number", label: "Size", min: 8, max: 40, step: 0.5, default: 22, unit: "mm" },
    spikeBase: {
      type: "number",
      label: "Spike base",
      description: "1.0 is the true stellation; lower values sink the spikes back toward the core.",
      min: 0.4,
      max: 1,
      step: 0.01,
      default: 1
    },
    coreColor: { type: "color", label: "Core color", default: "#1e7bff" },
    shadeColor: { type: "color", label: "Shade color", default: "#03104a" },
    glowColor: { type: "color", label: "Glow color", default: "#5ff0ff" }
  },
  bounds: ({ params }) => {
    // Spike apexes sit at (size, size, 0) and its permutations.
    const reach = params.size * 1.05;
    return [[-reach, -reach, -reach], [reach, reach, reach]];
  },
  render: ({ params }) => ({
    steps: 256,
    stepScale: 0.8,
    epsilon: Math.max(params.size * 0.0002, 0.003),
    normalEpsilon: Math.max(params.size * 0.002, 0.02)
  }),
  glsl: GLSL
};
