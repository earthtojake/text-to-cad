const GLSL = `
float sdf(vec3 p) {
  float z = clamp(p.z, -height * 0.5, height * 0.5);
  float profile = neckRadius * cosh(z / max(neckRadius, 0.1));
  float surface = abs(length(p.xy) - profile) - wallThickness;
  float clip = abs(p.z) - height * 0.5;
  float catenoid = max(surface, clip);
  float topRing = implicit_torus(p - vec3(0.0, 0.0, height * 0.5), profile + ringRadius * 0.25, ringRadius);
  float bottomRing = implicit_torus(p - vec3(0.0, 0.0, -height * 0.5), profile + ringRadius * 0.25, ringRadius);
  return implicit_union_round(implicit_union_round(catenoid, topRing, 1.8), bottomRing, 1.8);
}

vec3 color(vec3 p, vec3 normal) {
  float ring = smoothstep(height * 0.36, height * 0.52, abs(p.z));
  float contour = 0.5 + 0.5 * sin(p.z * 0.48);
  return mix(mix(baseColor * 0.65, baseColor, contour), accentColor, ring);
}
`;

export default {
  schema: "implicit.js/0.1.0",
  name: "catenoid ring bridge",
  description: "Prompt 11: catenoid minimal surface between two rings with controllable neck.",
  units: "mm",
  params: {
    neckRadius: { type: "number", label: "Neck radius", min: 7, max: 24, step: 0.25, default: 13, unit: "mm" },
    height: { type: "number", label: "Ring spacing", min: 22, max: 72, step: 1, default: 46, unit: "mm" },
    wallThickness: { type: "number", label: "Wall thickness", min: 0.8, max: 5, step: 0.1, default: 2, unit: "mm" },
    ringRadius: { type: "number", label: "Ring radius", min: 2, max: 8, step: 0.25, default: 4.5, unit: "mm" },
    baseColor: { type: "color", label: "Neck color", default: "#ffb703" },
    accentColor: { type: "color", label: "Ring color", default: "#00d1ff" }
  },
  animations: {
    neckPulse: {
      label: "Neck pulse",
      duration: 5.4,
      loop: true,
      update({ progress, set }) {
        const wave = Math.sin(progress * Math.PI * 2);
        set("neckRadius", 11 + (wave * 0.5 + 0.5) * 8);
        set("height", 38 + wave * 12);
      }
    }
  },
  // Derived, not guessed. The literal this replaced ([-42,-42,-46]..[42,42,46]) was 2.75mm
  // too small in X/Y, so the flared rims crossed the sampling box and marching cubes capped
  // them with flat vertical slices. The neck flares as neckRadius*cosh(z/neckRadius), which
  // reaches its widest at the end plates, and the torus rings then sit outside that -- none
  // of which the constant tracked when the params moved. It was also over-generous in Z
  // (46 against a real 27.25), spending a third of the sampling budget on empty space.
  bounds: ({ params }) => {
    const neck = Math.max(params.neckRadius, 0.1);
    const flare = neck * Math.cosh(params.height / (2 * neck));
    const extent = flare + params.ringRadius * 1.25 + params.wallThickness + 2;
    const z = params.height * 0.5 + params.ringRadius + 2;
    return [[-extent, -extent, -z], [extent, extent, z]];
  },
  render: { steps: 270, epsilon: 0.004, normalEpsilon: 0.045 },
  glsl: GLSL
};
