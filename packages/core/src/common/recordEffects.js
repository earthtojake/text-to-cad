// The effect records: where a pose and a playing clip meet.
//
// Every display record carries one effect — a world matrix that premultiplies its rest
// placement, a style, a visibility, a highlight, a tube skin — written by one pass per
// frame (applySceneState.js): the articulation player writes the pose, the animation
// runtime plays the clip's keys on top. This module holds the record side: building a
// placement matrix from a part's transform, and writing or clearing a pass's effects.

import { applyRecordTubeSkin } from "./tubeSkin.js";

export function buildPartTransformMatrix(THREE, transform, matrix = new THREE.Matrix4()) {
  if (!Array.isArray(transform) || transform.length !== 16) {
    matrix.identity();
    return matrix;
  }
  matrix.set(
    Number(transform[0]) || 0,
    Number(transform[1]) || 0,
    Number(transform[2]) || 0,
    Number(transform[3]) || 0,
    Number(transform[4]) || 0,
    Number(transform[5]) || 0,
    Number(transform[6]) || 0,
    Number(transform[7]) || 0,
    Number(transform[8]) || 0,
    Number(transform[9]) || 0,
    Number(transform[10]) || 0,
    Number(transform[11]) || 0,
    Number(transform[12]) || 0,
    Number(transform[13]) || 0,
    Number(transform[14]) || 0,
    Number(transform[15]) || 0
  );
  return matrix;
}

export function displayTransformForPart(meshData, part) {
  // Composed packages declare partTransformsBaked: false — their shared component
  // geometry is occurrence-local, so the occurrence transform must be applied no
  // matter which render mode is active. Baked meshDatas (partTransformsBaked: true)
  // carry world-space vertices, so parts place with no extra transform.
  if (meshData?.partTransformsBaked === false) {
    return part?.transform || null;
  }
  return null;
}

export function resetRecordEffects(records, THREE = null) {
  for (const record of Array.isArray(records) ? records : []) {
    if (THREE) applyRecordTubeSkin(THREE, record, null);
    record.effectMatrix = null;
    record.effectStyle = null;
    record.effectVisible = null;
    record.effectHighlighted = false;
  }
}

function sameEffectStyle(previous, next) {
  if (previous === next) return true;
  if (!previous || !next) return false;
  const keys = Object.keys(next);
  return keys.length === Object.keys(previous).length && keys.every((key) => previous[key] === next[key]);
}

/**
 * Write this pass's effects onto the display records.
 *
 * Returns whether anything but a transform changed since the last pass: style,
 * visibility or highlight. A routine that only moves parts — nearly every frame
 * of nearly every routine — changes none of them, and its caller can then skip
 * reconciling materials and instance membership, which a transform cannot affect.
 */
export function applyEffectsToRecords(THREE, records, effectsByPartId) {
  let appearanceChanged = false;
  for (const record of Array.isArray(records) ? records : []) {
    const effect = effectsByPartId.get(String(record?.partId || "").trim());
    applyRecordTubeSkin(THREE, record, effect?.deformation || null);
    const style = effect?.style && typeof effect.style === "object" ? { ...effect.style } : null;
    const visible = effect ? effect.visible : null;
    const highlighted = effect?.highlighted === true;
    if (!sameEffectStyle(record.effectStyle || null, style) || (record.effectVisible ?? null) !== (visible ?? null) ||
        (record.effectHighlighted === true) !== highlighted) {
      appearanceChanged = true;
    }
    record.effectMatrix = effect?.matrix instanceof THREE.Matrix4 ? effect.matrix.clone() : null;
    record.effectStyle = style;
    record.effectVisible = visible;
    record.effectHighlighted = highlighted;
  }
  return { appearanceChanged };
}
