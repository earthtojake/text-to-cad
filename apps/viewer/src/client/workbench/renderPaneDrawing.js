export function viewerBendGuidesForRenderPane({ renderMode = false, bendAxisX = null, drawingBendLines = null } = {}) {
  // Zero bend angles flatten a sheet but still draw its crease guides. Render
  // excludes the guide inputs too, while keeping authored score/text markings.
  return renderMode ? { bendAxisX: null, drawingBendLines: null } : { bendAxisX, drawingBendLines };
}
