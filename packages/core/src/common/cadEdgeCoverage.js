// Device-pixel radius of a compact, symmetric smoothing kernel. The difference
// of its two cumulative ramps is a filtered box, whose integrated coverage is
// exactly the nominal line width, including subpixel lines.
export const CAD_EDGE_FEATHER_PIXELS = 0.75;
const FEATHER_GLSL = CAD_EDGE_FEATHER_PIXELS.toFixed(4);
export const CAD_EDGE_COVERAGE_GLSL = /* glsl */`
float cadEdgeCoverage(float distancePixels, float halfWidth) {
  return smoothstep(-${FEATHER_GLSL}, ${FEATHER_GLSL}, distancePixels + halfWidth)
    - smoothstep(-${FEATHER_GLSL}, ${FEATHER_GLSL}, distancePixels - halfWidth);
}
`;
