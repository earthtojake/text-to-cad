import { LOD_CHORD_LEVELS, LOD_TESSELLATION_LEVELS } from "cadgen-js/lib/surf/lodPolicy.js";

export const LOD_SELECTOR_AND_GPU_ESTIMATE_MULTIPLIER = 2.5;
export const LOD_WORKER_TEMP_ESTIMATE_MULTIPLIER = 2;

export function estimateViewportLodMemory({ meshBytes, currentLevel, level }) {
  const currentBytes = Math.max(1, Number(meshBytes) || 0);
  const toleranceRatio = LOD_CHORD_LEVELS[currentLevel] / LOD_CHORD_LEVELS[level];
  const angleRatio = LOD_TESSELLATION_LEVELS[currentLevel].angleTolerance / LOD_TESSELLATION_LEVELS[level].angleTolerance;
  // L0 also relaxes angular tolerance. Chord alone treated its canonical
  // refinement as just 1.33x even when the angular criterion drives density.
  const nextMeshBytes = Math.ceil(currentBytes * Math.max(0.2, toleranceRatio, angleRatio));
  const replacementBytes = nextMeshBytes * LOD_SELECTOR_AND_GPU_ESTIMATE_MULTIPLIER;
  const workerTemporaryBytes = nextMeshBytes * LOD_WORKER_TEMP_ESTIMATE_MULTIPLIER;
  // The previous payload remains available for full-scene recovery until
  // adoption is confirmed, including after the renderer accounts the new one.
  const heldPreviousBytes = Math.ceil(currentBytes * LOD_SELECTOR_AND_GPU_ESTIMATE_MULTIPLIER);
  return {
    currentBytes,
    nextMeshBytes,
    replacementBytes,
    workerTemporaryBytes,
    heldPreviousBytes,
    admissionBytes: replacementBytes + workerTemporaryBytes + heldPreviousBytes,
  };
}
