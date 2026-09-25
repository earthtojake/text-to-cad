// Explode separates a model's parts: with one part (or none that can be placed)
// there is nothing to separate, and the Explode tool is unavailable.
export function explodablePartCount(meshData) {
  const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  return parts.filter((part) => part && (part.bounds || part.sourceBounds) &&
    String(part.id || part.occurrenceId || "").trim()).length;
}
