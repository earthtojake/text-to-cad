export function viewerBendGuidesForRenderPane({ bendAxisX = null, drawingBendLines = null } = {}) {
  // Display style preserves the drawing's bend geometry and guide settings.
  return { bendAxisX, drawingBendLines };
}
