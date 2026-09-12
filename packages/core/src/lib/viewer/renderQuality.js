export function resolveInteractionPixelRatioCap({
  idlePixelRatioCap = 2,
  interactionPixelRatioCap = 1,
  preservePixelRatio = false,
  screenSpaceLineMaterialCount = null,
  screenSpaceLineMaterials = null
} = {}) {
  if (preservePixelRatio) {
    return idlePixelRatioCap;
  }
  const materialCount = screenSpaceLineMaterialCount != null && Number.isFinite(Number(screenSpaceLineMaterialCount))
    ? Number(screenSpaceLineMaterialCount)
    : Number(screenSpaceLineMaterials?.size || 0);
  return materialCount > 0
    ? idlePixelRatioCap
    : interactionPixelRatioCap;
}
