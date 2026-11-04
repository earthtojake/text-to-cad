// The selection/hover highlight every scene lights a part with (`sceneHighlight.js`, a robot's
// scene), in the viewer and on the parity page alike.

const PART_OCCLUSION_GHOST_RENDER_ORDER = 30;
// A plain blend, not a dither: an ordered dither's pattern read as grain on
// the hidden surface. This is the dither's old mean (0.9 opacity over 60% of
// the pixels).
const PART_OCCLUSION_GHOST_OPACITY = 0.54;

// How far the highlighted surface is pulled toward the highlight color. A blend
// (rather than a full replace) keeps the part recognizable while still shifting
// its hue enough to read as selected against same-colored neighbours. Edges and
// emissive stay at the full highlight color so the cue never depends on the
// part's own hue.
export const PART_SELECTED_HIGHLIGHT_BLEND = 0.55;
export const PART_HOVER_HIGHLIGHT_BLEND = 0.35;

// Hover is a transient "this is what you would pick" affordance; selection is
// persistent state that several parts can hold at once. Both are visible at the
// same time — you hover one part while others stay selected — so they differ in
// hue, and hover stays subordinate: weaker glow, and no occlusion ghost. Ghosting
// on hover would strobe as the cursor sweeps an assembly and would allocate a
// ghost mesh for every part the cursor touches.
export const PART_SELECTED_EMISSIVE_INTENSITY = 0.12;
export const PART_HOVER_EMISSIVE_INTENSITY = 0.05;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function partHighlightSurfaceColor(THREE, baseColor, highlightColor, blend) {
  if (!highlightColor?.isColor) {
    return null;
  }
  if (!baseColor?.isColor) {
    return highlightColor;
  }
  const amount = clamp(Number.isFinite(Number(blend)) ? Number(blend) : 1, 0, 1);
  return baseColor.clone().lerp(highlightColor, amount);
}

// The stencil value a ghost marks the pixels it has drawn with: past the 1-251
// an annotation's once-only strokes cycle through (`annotation.js`), and drawn
// after the section caps, which leave the stencil 0 (`sectionCaps.js`).
const PART_OCCLUSION_GHOST_STENCIL = 255;

export function createPartOcclusionGhostMaterial(THREE, {
  color = null,
  opacity = PART_OCCLUSION_GHOST_OPACITY
} = {}) {
  // A built-in material (rather than a from-scratch ShaderMaterial) so the ghost
  // inherits three's logarithmic depth buffer, clipping planes, and output color
  // space. Writing raw fragments would put the ghost on a different depth
  // encoding than every other material in the scene, which breaks the
  // GreaterDepth occlusion test outright.
  const material = new THREE.MeshBasicMaterial({
    color: color?.isColor ? color.clone() : new THREE.Color("#4f9dff"),
    transparent: true,
    opacity,
    depthTest: true,
    // FrontSide + Greater: the ghost draws ONLY where this part's front face is
    // behind something else. The part's own back faces never self-ghost, and
    // front-most fragments fail the Greater test so nothing paints over the
    // unobscured surface.
    depthFunc: THREE.GreaterDepth,
    depthWrite: false,
    side: THREE.FrontSide,
    // The ghost is a UI affordance, not lit geometry: skip tone mapping so it
    // lands on the theme's highlight color instead of an ACES-rolled version.
    toneMapped: false,
    // Once per pixel: where hidden layers stack (a ring's inner and outer walls,
    // several selected parts) the ghost blends once, so it is one even tint
    // rather than darker wherever more of the part is behind something.
    stencilWrite: true,
    stencilRef: PART_OCCLUSION_GHOST_STENCIL,
    stencilFunc: THREE.NotEqualStencilFunc,
    stencilFail: THREE.KeepStencilOp,
    stencilZFail: THREE.KeepStencilOp,
    stencilZPass: THREE.ReplaceStencilOp
  });
  return material;
}

// Built lazily on first selection: a ghost per display record would otherwise
// double the scene's object count on every model for a cue only the selected
// part ever uses.
export function ensurePartOcclusionGhost(THREE, record) {
  if (record?.ghostMesh) {
    return record.ghostMesh;
  }
  const geometry = record?.geometry || record?.mesh?.geometry;
  if (!geometry || typeof record?.mesh?.add !== "function") {
    return null;
  }
  const material = createPartOcclusionGhostMaterial(THREE, { color: record.baseColor });
  material.clippingPlanes = record.material?.clippingPlanes || null;
  const mesh = new THREE.Mesh(geometry, material);
  mesh.renderOrder = PART_OCCLUSION_GHOST_RENDER_ORDER;
  mesh.visible = false;
  mesh.castShadow = false;
  mesh.receiveShadow = false;
  mesh.userData.partId = record.partId;
  mesh.userData.isOcclusionGhost = true;
  record.mesh.add(mesh);
  record.ghostMesh = mesh;
  record.ghostMaterial = material;
  return mesh;
}

export function syncPartOcclusionGhost(THREE, record, { visible = false, color = null } = {}) {
  if (!record) {
    return null;
  }
  if (!visible) {
    if (record.ghostMesh) {
      record.ghostMesh.visible = false;
    }
    return record.ghostMesh || null;
  }
  const mesh = ensurePartOcclusionGhost(THREE, record);
  if (!mesh) {
    return null;
  }
  mesh.visible = true;
  if (color?.isColor && record.ghostMaterial?.color?.copy) {
    record.ghostMaterial.color.copy(color);
  }
  return mesh;
}
