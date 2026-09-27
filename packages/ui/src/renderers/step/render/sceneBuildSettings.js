export function sceneBuildStructuralKey({
  displayMode,
  applyDisplayModeEdgePolicy,
  sceneScaleMode,
  edgeSettings,
  recomputeNormals,
  silhouette
} = {}) {
  return JSON.stringify({
    displayMode,
    applyDisplayModeEdgePolicy,
    scale: sceneScaleMode,
    edgeSettings: {
      enabled: edgeSettings?.enabled,
      silhouette: edgeSettings?.silhouette,
      depthTest: edgeSettings?.depthTest
    },
    recomputeNormals,
    silhouette
  });
}
