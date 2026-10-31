import { CAD_EDGE_COVERAGE_GLSL, CAD_EDGE_FEATHER_PIXELS } from "./cadEdgeCoverage.js";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

const DEFAULT_LINE_DEPTH_BIAS = 0;
// Keep topology edges slightly above coplanar faces without letting nearby solids lose the depth test.
export const TOPOLOGY_LINE_DEPTH_BIAS = 0.0045;
const TOPOLOGY_LINE_DEPTH_BIAS_PER_EXTRA_PIXEL = 0.00025;
const MAX_TOPOLOGY_LINE_DEPTH_BIAS = 0.006;
const COPLANAR_TOPOLOGY_EDGE_CLASSES = new Set(["tangent", "seam"]);
const COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS = 0.006;
const COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS_PER_EXTRA_PIXEL = 0.00025;
const MAX_COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS = 0.008;

export function topologyLineDepthBiasForWidth(lineWidth = 1, { visibilityClass = "" } = {}) {
  const width = Number.isFinite(Number(lineWidth))
    ? Math.max(1, Number(lineWidth))
    : 1;
  const normalizedClass = String(visibilityClass || "").trim().toLowerCase();
  const baseBias = COPLANAR_TOPOLOGY_EDGE_CLASSES.has(normalizedClass)
    ? COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS
    : TOPOLOGY_LINE_DEPTH_BIAS;
  const biasPerExtraPixel = COPLANAR_TOPOLOGY_EDGE_CLASSES.has(normalizedClass)
    ? COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS_PER_EXTRA_PIXEL
    : TOPOLOGY_LINE_DEPTH_BIAS_PER_EXTRA_PIXEL;
  const maxBias = COPLANAR_TOPOLOGY_EDGE_CLASSES.has(normalizedClass)
    ? MAX_COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS
    : MAX_TOPOLOGY_LINE_DEPTH_BIAS;
  return clamp(
    baseBias + Math.max(0, width - 1) * biasPerExtraPixel,
    baseBias,
    maxBias
  );
}

export function syncLineMaterialOpacity(material, opacity) {
  if (!material) {
    return;
  }
  const nextOpacity = clamp(Number(opacity) || 0, 0, 1);
  // A screen-space line carries its antialiasing in ALPHA (the analytic feather
  // below), so it has to blend even at full class opacity — an opaque material
  // throws the ramp away and paints the whole padded quad solid. The retired
  // surface shader did not need this: it mixed coverage into the fragment's
  // COLOUR, so it softened edges on an opaque surface.
  const nextTransparent = nextOpacity < 0.999 ||
    material.userData?.cadEdgeAnalyticCoverage === true;
  material.opacity = nextOpacity;
  material.depthWrite = false;
  if (material.transparent !== nextTransparent) {
    material.transparent = nextTransparent;
    material.needsUpdate = true;
  }
}

// A screen-space line's width is measured in DEVICE pixels, and `resolution` is
// what decides that.
//
// Three's LineMaterial extrudes with `offset *= lineWidth; offset /= resolution.y`,
// which lands in NDC. NDC y spans the whole DRAWING BUFFER, so the ink a fragment sees is
// `lineWidth * drawingBufferHeight / resolution.y` device pixels: whatever unit
// `resolution` is in is the unit the resolved class width is in.
//
// It must be the drawing buffer, because that is the unit the retired surface
// shader measured in (its `pixelDistance = barycentric / fwidth(barycentric)`
// was a per-fragment derivative, so a device pixel) and therefore the unit the fixed
// CAD ink policy uses. Syncing the CSS size instead — the
// same numbers handed to `renderer.setSize(w, h, false)` — leaves the buffer's
// pixel ratio uncancelled and makes every configured thickness
// `devicePixelRatio` times wider on screen: 2x on a Retina Mac, 3x at dpr 3.
//
// CAD classes, topology overlays, annotation strokes and highlights share this
// device-pixel resolution contract. Their resolved widths can differ without
// an accidental extra devicePixelRatio multiplier in any one path.
export function screenSpaceLineDeviceResolution(renderer, width, height) {
  const pixelRatio = Number(renderer?.getPixelRatio?.());
  const scale = Number.isFinite(pixelRatio) && pixelRatio > 0 ? pixelRatio : 1;
  return {
    width: Math.max(1, Math.floor((Number(width) || 1) * scale)),
    height: Math.max(1, Math.floor((Number(height) || 1) * scale))
  };
}

function registerLineMaterial(context = {}, material, materials = null) {
  materials?.add?.(material);
  context.registerScreenSpaceLineMaterial?.(material);
}

function unregisterLineMaterial(context = {}, material, materials = null) {
  materials?.delete?.(material);
  context.unregisterScreenSpaceLineMaterial?.(material);
}

export function createScreenSpaceLineSegments(context = {}, positions, {
  color,
  opacity = 1,
  lineWidth = 1,
  renderOrder = 3,
  depthTest = true,
  depthWrite = false,
  depthBias = DEFAULT_LINE_DEPTH_BIAS
} = {}, materials = null) {
  const LineSegments2 = context.LineSegments2;
  const LineSegmentsGeometry = context.LineSegmentsGeometry;
  const LineMaterial = context.LineMaterial;
  if (
    !LineSegments2 ||
    !LineSegmentsGeometry ||
    !LineMaterial ||
    !(Array.isArray(positions) || ArrayBuffer.isView(positions)) ||
    !positions.length
  ) {
    return null;
  }

  const lineGeometry = new LineSegmentsGeometry();
  lineGeometry.setPositions(positions);
  const lineMaterial = createScreenSpaceLineMaterial(LineMaterial, {
    color,
    opacity,
    lineWidth,
    depthTest,
    depthWrite,
    depthBias
  });
  registerLineMaterial(context, lineMaterial, materials);
  const line = useDevicePixelLineResolution(new LineSegments2(lineGeometry, lineMaterial));
  line.renderOrder = renderOrder;
  line.frustumCulled = false;
  line.userData.beforeDispose = () => {
    unregisterLineMaterial(context, lineMaterial, materials);
  };
  line.userData.disposeGeometry = true;
  line.userData.disposeMaterial = true;
  return line;
}

// three's LineSegments2/Line2 REWRITE `material.uniforms.resolution` on every
// draw, from `renderer.getViewport()` (LineSegments2.js onBeforeRender) — which
// reports CSS pixels. A resolution synced from outside is therefore thrown away
// one frame later, and a configured thickness silently becomes a CSS-pixel
// width: devicePixelRatio times wider on screen than the device-pixel width the
// rest of the edge pass measures in. Take the hook over and write the CURRENT
// viewport instead, which three already keeps in device pixels (the viewport
// times the pixel ratio, or a render target's own viewport).
//
// `getCurrentViewport` copies into anything with x/y/z/w, so this needs neither
// a Vector4 nor THREE. One shared sink: onBeforeRender runs synchronously
// inside the draw.
const CURRENT_VIEWPORT = {
  x: 0,
  y: 0,
  z: 1,
  w: 1,
  copy(source) {
    this.x = source.x;
    this.y = source.y;
    this.z = source.z;
    this.w = source.w;
    return this;
  }
};

function useDevicePixelLineResolution(line) {
  line.onBeforeRender = function onBeforeRender(renderer) {
    const resolution = this.material?.uniforms?.resolution?.value;
    if (!resolution || typeof renderer?.getCurrentViewport !== "function") {
      // No live viewport to read: keep whatever
      // syncScreenSpaceLineMaterialResolution last wrote, which is already the
      // drawing-buffer size.
      return;
    }
    renderer.getCurrentViewport(CURRENT_VIEWPORT);
    resolution.set(Math.max(1, CURRENT_VIEWPORT.z), Math.max(1, CURRENT_VIEWPORT.w));
  };
  return line;
}

function replaceShaderAnchor(source, anchor, replacement, stage) {
  const first = source.indexOf(anchor);
  if (first === -1 || source.indexOf(anchor, first + anchor.length) !== -1) {
    // Loud failure: a three upgrade that moves or duplicates the anchor must not
    // silently ship hard-edged, double-width lines.
    throw new Error(
      `renderEdges: the screen-space line ${stage} shader has no unique \`${anchor}\` to patch. ` +
      "three's LineMaterial changed; re-derive the feather against the new source."
    );
  }
  return source.replace(anchor, replacement);
}

// three's LineMaterial hard-discards at the quad boundary and cannot be talked
// out of it with `alphaToCoverage`.
//
// In screen-space mode (worldUnits false) its whole coverage story lives inside
// `if (abs(vUv.y) > 1.0)`, the round endcap region: without USE_ALPHA_TO_COVERAGE
// that block is `if (len2 > 1.0) discard;`, and with it the block becomes a
// smoothstep — but it is still only the caps. The body's long edges, which is
// what a CAD drawing is made of, get no coverage term either way, so the ink
// stops dead at the quad boundary and only the context's 4x MSAA softens it.
// Turning alphaToCoverage on would also actively cost us: sample-alpha-to-
// coverage converts alpha into a sample mask, so a class opacity of 0.5
// (tangent) or 0.85 (seam) would be quantised to quarters of a 4-sample target
// — it would damage exactly the per-class opacity this pass exists to honour,
// on materials that are already `transparent: true` and alpha-blending
// correctly. (Verified against three 0.185.1 LineMaterial.js, not assumed.)
//
// So the feather is analytic here, as it is in the instanced shader: widen the
// quad by CAD_EDGE_FEATHER_PIXELS on each side and apply a symmetric filtered
// box. Unlike an opaque centre with a clamped inner feather, subpixel lines
// retain their nominal integrated weight. vUv.x is the
// cross coordinate (+-1 at the quad edge) and vUv.y runs along the segment with
// the caps beyond +-1, so one radial distance covers body and caps alike.
function applyScreenSpaceLineFeather(shader) {
  const feather = CAD_EDGE_FEATHER_PIXELS.toFixed(4);
  shader.vertexShader = replaceShaderAnchor(
    shader.vertexShader,
    "offset *= linewidth;",
    `offset *= linewidth + ${feather} * 2.0;`,
    "vertex"
  );
  shader.fragmentShader = CAD_EDGE_COVERAGE_GLSL + shader.fragmentShader;
  shader.fragmentShader = replaceShaderAnchor(
    shader.fragmentShader,
    "gl_FragColor = vec4( diffuseColor.rgb, alpha );",
    `#ifndef WORLD_UNITS
	float cadEdgeInkHalfWidth = linewidth * 0.5;
	float cadEdgeCapX = vUv.x;
	float cadEdgeCapY = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
	float cadEdgeCross = ( abs( vUv.y ) > 1.0 )
		? sqrt( cadEdgeCapX * cadEdgeCapX + cadEdgeCapY * cadEdgeCapY )
		: abs( cadEdgeCapX );
	float cadEdgeDistance = cadEdgeCross * ( cadEdgeInkHalfWidth + ${feather} );
	alpha *= cadEdgeCoverage( cadEdgeDistance, cadEdgeInkHalfWidth );
#endif
		gl_FragColor = vec4( diffuseColor.rgb, alpha );`,
    "fragment"
  );
}

function createScreenSpaceLineMaterial(LineMaterial, {
  color,
  opacity = 1,
  lineWidth = 1,
  depthTest = true,
  depthWrite = false,
  depthBias = DEFAULT_LINE_DEPTH_BIAS
} = {}) {
  const lineMaterial = new LineMaterial({
    color,
    // The FULL on-screen width of the ink, in device pixels — the material's
    // `resolution` is the drawing buffer, so this stays a device-pixel width at
    // every devicePixelRatio.
    linewidth: lineWidth,
    opacity,
    depthTest,
    depthWrite,
    toneMapped: false,
    worldUnits: false
  });
  // One module-level callback for every line material, so three's default
  // program cache key (onBeforeCompile.toString()) keeps them sharing a program.
  lineMaterial.onBeforeCompile = applyScreenSpaceLineFeather;
  lineMaterial.userData.cadEdgeAnalyticCoverage = true;
  syncLineMaterialOpacity(lineMaterial, opacity);
  applyLineDepthBias(lineMaterial, depthBias);
  return lineMaterial;
}

export function applyLineDepthBias(material, depthBias = DEFAULT_LINE_DEPTH_BIAS) {
  const bias = clamp(Number(depthBias) || 0, 0, 0.01);
  if (!material || bias <= 0) {
    return material;
  }
  material.polygonOffset = true;
  material.polygonOffsetFactor = 0;
  material.polygonOffsetUnits = -clamp(Math.round(bias * 1000), 1, 10);
  material.needsUpdate = true;
  return material;
}

export function createScreenSpaceLineStrip(context = {}, positions, {
  color,
  opacity = 1,
  lineWidth = 1,
  renderOrder = 3,
  depthTest = true,
  depthWrite = false,
  depthBias = DEFAULT_LINE_DEPTH_BIAS
} = {}, materials = null) {
  const Line2 = context.Line2;
  const LineGeometry = context.LineGeometry;
  const LineMaterial = context.LineMaterial;
  if (
    !Line2 ||
    !LineGeometry ||
    !LineMaterial ||
    !(Array.isArray(positions) || ArrayBuffer.isView(positions)) ||
    positions.length < 6
  ) {
    return null;
  }

  const lineGeometry = new LineGeometry();
  lineGeometry.setPositions(positions);
  const lineMaterial = createScreenSpaceLineMaterial(LineMaterial, {
    color,
    opacity,
    lineWidth,
    depthTest,
    depthWrite,
    depthBias
  });
  registerLineMaterial(context, lineMaterial, materials);
  const line = useDevicePixelLineResolution(new Line2(lineGeometry, lineMaterial));
  line.renderOrder = renderOrder;
  line.frustumCulled = false;
  line.userData.beforeDispose = () => {
    unregisterLineMaterial(context, lineMaterial, materials);
  };
  line.userData.disposeGeometry = true;
  line.userData.disposeMaterial = true;
  return line;
}
