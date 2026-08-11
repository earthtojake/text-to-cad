// Pure helpers for framing an implicit model. Kept out of useImplicitRaymarch so
// they can be tested without standing up React or a WebGL context.

export function implicitModelBounds(model) {
  const min = model?.bounds?.min;
  const max = model?.bounds?.max;
  if (!Array.isArray(min) || !Array.isArray(max) || min.length < 3 || max.length < 3) {
    return null;
  }
  if (![...min.slice(0, 3), ...max.slice(0, 3)].every((value) => Number.isFinite(Number(value)))) {
    return null;
  }
  return {
    min: min.slice(0, 3).map(Number),
    max: max.slice(0, 3).map(Number)
  };
}

// Quantised envelope identity, used to decide whether a model change is worth a
// re-fit. Animation and most parameter edits advance the shader's uniforms
// without moving the envelope, and re-fitting on every frame would fight the
// user's camera — so anything inside 2% of the model radius reads as "same".
export function implicitBoundsKey(model) {
  const bounds = implicitModelBounds(model);
  if (!bounds) {
    return "";
  }
  const radius = Math.max(Number(model?.radius) || 1, 1e-6);
  const quantum = Math.max(radius * 0.02, 1e-6);
  return [...bounds.min, ...bounds.max]
    .map((value) => Math.round(value / quantum))
    .join(",");
}
