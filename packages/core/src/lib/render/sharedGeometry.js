// A geometry over another geometry's buffers: what a SECOND scene of the same file (the viewer's
// Preview beside its editor) draws its meshes with. Its attributes ARE the source's
// attribute objects, so a renderer that draws both uploads each buffer once; an attribute the
// second scene rewrites for itself (a look's graded vertex colours) is its own copy.
//
// Release it with `releaseGeometry`, never `dispose()` alone: a renderer frees the GPU buffers of
// every attribute a disposed geometry holds, and the shared ones are still the source's. Release
// lets go of those first, so only the geometry's own attributes, and the renderer's per-geometry
// state (its vertex-array objects), are freed. The source stays its owner's to dispose.

const SHARED = Symbol("cadSharedGeometry");

/**
 * @param {typeof import("three")} THREE
 * @param {import("three").BufferGeometry} source
 * @param {{ own?: string[] }} [options]  Attributes copied rather than shared.
 */
export function shareGeometry(THREE, source, { own = [] } = {}) {
  const geometry = new THREE.BufferGeometry();
  geometry.name = source.name;
  const owned = new Set(own);
  if (source.index) geometry.setIndex(source.index);
  for (const [name, attribute] of Object.entries(source.attributes)) {
    geometry.setAttribute(name, owned.has(name) ? attribute.clone() : attribute);
  }
  for (const [name, list] of Object.entries(source.morphAttributes || {})) geometry.morphAttributes[name] = list;
  geometry.morphTargetsRelative = source.morphTargetsRelative;
  for (const group of source.groups) geometry.addGroup(group.start, group.count, group.materialIndex);
  geometry.drawRange.start = source.drawRange.start;
  geometry.drawRange.count = source.drawRange.count;
  if (source.boundingBox) geometry.boundingBox = source.boundingBox.clone();
  if (source.boundingSphere) geometry.boundingSphere = source.boundingSphere.clone();
  geometry.userData = { ...source.userData };
  geometry[SHARED] = { index: Boolean(source.index), attributes: Object.keys(source.attributes).filter(name => !owned.has(name)),
    morphs: Object.keys(source.morphAttributes || {}) };
  return geometry;
}

/** Whether `geometry` shares another's buffers (`shareGeometry`). */
export function isSharedGeometry(geometry) {
  return Boolean(geometry?.[SHARED]);
}

/** Dispose a geometry: a shared one frees only what is its own. */
export function releaseGeometry(geometry) {
  if (!geometry) return;
  const shared = geometry[SHARED];
  if (shared) {
    if (shared.index) geometry.setIndex(null);
    for (const name of shared.attributes) geometry.deleteAttribute(name);
    for (const name of shared.morphs) delete geometry.morphAttributes[name];
  }
  geometry.dispose();
}
