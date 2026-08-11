const GLSL = `
float sdf(vec3 p) {
  // Sweep angle around +Z and the cross-section plane at that angle.
  float u = atan(p.y, p.x);
  vec2 section = vec2(length(p.xy) - ringRadius, p.z);

  // Half a turn of section twist per full turn of sweep — the Mobius half-twist.
  float c = cos(0.5 * u);
  float s = sin(0.5 * u);
  vec2 q = vec2(c * section.x + s * section.y, -s * section.x + c * section.y);

  // Rounded-rectangle section. Deliberately NOT circular: a circular section is
  // invariant under the twist, which would erase the Mobius read entirely.
  // Note: "half" is a reserved word in GLSL, so the local below is halfSection.
  float corner = min(cornerRadius, 0.5 * min(sectionWidth, sectionHeight));
  vec2 halfSection = vec2(sectionWidth * 0.5, sectionHeight * 0.5) - corner;
  vec2 d = abs(q) - halfSection;
  return min(max(d.x, d.y), 0.0) + length(max(d, 0.0)) - corner;
}

vec3 color(vec3 p, vec3 normal) {
  // Neon blue: deep indigo in the shade, electric cyan on the lit faces.
  vec3 n = normalize(normal);
  vec3 key = normalize(vec3(-0.32, -0.48, 0.82));
  float facing = clamp(dot(n, key) * 0.5 + 0.5, 0.0, 1.0);

  vec3 body = mix(shadeColor, coreColor, smoothstep(0.06, 0.70, facing));
  return mix(body, glowColor, smoothstep(0.74, 1.0, facing) * 0.85);
}
`;

export default {
  schema: "implicit.js/0.1.0",
  name: "mobius donut band",
  description:
    "A one-half-twist Mobius band with a chunky rounded-rectangle section — the source model for the CAD Viewer and docs favicon.",
  units: "mm",
  params: {
    ringRadius: { type: "number", label: "Ring radius", min: 12, max: 34, step: 0.25, default: 21, unit: "mm" },
    sectionWidth: { type: "number", label: "Section width", min: 4, max: 26, step: 0.25, default: 14, unit: "mm" },
    sectionHeight: { type: "number", label: "Section height", min: 2, max: 20, step: 0.25, default: 12, unit: "mm" },
    cornerRadius: { type: "number", label: "Corner radius", min: 0, max: 8, step: 0.1, default: 3.2, unit: "mm" },
    coreColor: { type: "color", label: "Core color", default: "#1e7bff" },
    shadeColor: { type: "color", label: "Shade color", default: "#03104a" },
    glowColor: { type: "color", label: "Glow color", default: "#5ff0ff" }
  },
  bounds: ({ params }) => {
    const reach = 0.5 * Math.max(params.sectionWidth, params.sectionHeight);
    const radial = params.ringRadius + reach + 4;
    const height = reach + 4;
    return [[-radial, -radial, -height], [radial, radial, height]];
  },
  render: ({ params }) => ({
    steps: 224,
    stepScale: 0.75,
    epsilon: Math.max(params.sectionHeight * 0.0015, 0.004),
    normalEpsilon: Math.max(params.sectionHeight * 0.01, 0.03)
  }),
  glsl: GLSL
};
