import {
  buildPartTransformMatrix
} from "./stepModuleEffects.js";
import { syncCadSurfaceInstanceTransform } from "./cadSurfaceInstances.js";

function applyObjectMatrix(THREE, object3d, matrix) {
  if (!object3d || !(matrix instanceof THREE.Matrix4)) {
    return;
  }
  object3d.matrixAutoUpdate = false;
  const targetMatrix = object3d.matrix instanceof THREE.Matrix4 ? object3d.matrix : new THREE.Matrix4();
  targetMatrix.copy(matrix);
  object3d.matrix = targetMatrix;
  object3d.matrixWorldNeedsUpdate = true;
}

export function composeDisplayRecordEffectMatrix(THREE, record) {
  if (!record || !THREE?.Matrix4) {
    return null;
  }
  const matrices = [
    record.effectMatrix,
    record.explodedViewMatrix
  ].filter((matrix) => matrix instanceof THREE.Matrix4);
  if (!matrices.length) {
    return null;
  }
  const combined = new THREE.Matrix4();
  for (const matrix of matrices) {
    combined.premultiply(matrix);
  }
  return combined;
}

export function composeDisplayRecordObjectMatrix(THREE, record, target) {
  const matrix = buildPartTransformMatrix(THREE, record?.baseTransform, target);
  if (record?.effectMatrix instanceof THREE.Matrix4) matrix.premultiply(record.effectMatrix);
  if (record?.explodedViewMatrix instanceof THREE.Matrix4) matrix.premultiply(record.explodedViewMatrix);
  return matrix;
}

export function applyDisplayRecordTransform(THREE, record) {
  if (!record) {
    return;
  }
  // The mesh already owns the result. Recompute its values (effects and source
  // transforms may mutate in place) without allocating a matrix per occurrence
  // on every scene publish or animation frame.
  const combinedMatrix = composeDisplayRecordObjectMatrix(THREE, record, record.mesh?.matrix);
  applyObjectMatrix(THREE, record.mesh, combinedMatrix);
  applyObjectMatrix(THREE, record.edges, combinedMatrix);
  applyObjectMatrix(THREE, record.silhouette, combinedMatrix);
  if (record.edgeInstance && !record.edgeInstance.set.disposed) {
    record.edgeInstance.set.setMatrix(record.edgeInstance.slot, combinedMatrix);
  }
  // Inactive slots must stay zero while their ordinary mesh handles selection,
  // transparency or deformation. Sync also avoids uploading unchanged matrices.
  syncCadSurfaceInstanceTransform(record);
}
