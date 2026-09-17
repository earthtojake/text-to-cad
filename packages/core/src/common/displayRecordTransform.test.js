import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  applyDisplayRecordTransform,
  composeDisplayRecordEffectMatrix,
  composeDisplayRecordObjectMatrix
} from "./displayRecordTransform.js";

test("display record transforms compose module effects and exploded view effects", () => {
  const record = {
    baseTransform: [
      1, 0, 0, 3,
      0, 1, 0, 0,
      0, 0, 1, 0,
      0, 0, 0, 1
    ],
    effectMatrix: new THREE.Matrix4().makeTranslation(5, 0, 0),
    explodedViewMatrix: new THREE.Matrix4().makeTranslation(0, 7, 0)
  };

  const effectPoint = new THREE.Vector3(0, 0, 0).applyMatrix4(
    composeDisplayRecordEffectMatrix(THREE, record)
  );
  assert.deepEqual(effectPoint.toArray(), [5, 7, 0]);

  const objectPoint = new THREE.Vector3(0, 0, 0).applyMatrix4(
    composeDisplayRecordObjectMatrix(THREE, record)
  );
  assert.deepEqual(objectPoint.toArray(), [8, 7, 0]);
});

test("applying a transform reuses the mesh matrix and observes in-place source and effect changes", () => {
  const record = {
    mesh: new THREE.Mesh(), edges: new THREE.Group(), silhouette: new THREE.Mesh(),
    baseTransform: [1, 0, 0, 3, 0, 2, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1],
    effectMatrix: new THREE.Matrix4().makeRotationZ(Math.PI / 2),
    explodedViewMatrix: new THREE.Matrix4().makeTranslation(0, 7, 0)
  };
  const ownedMatrix = record.mesh.matrix;
  for (let iteration = 0; iteration < 3; iteration += 1) {
    record.baseTransform[3] += 2;
    record.effectMatrix.setPosition(iteration, 0, 0);
    const expected = composeDisplayRecordObjectMatrix(THREE, record);
    applyDisplayRecordTransform(THREE, record);
    assert.equal(record.mesh.matrix, ownedMatrix);
    assert.deepEqual(record.mesh.matrix.elements, expected.elements);
    assert.deepEqual(record.edges.matrix.elements, expected.elements);
    assert.deepEqual(record.silhouette.matrix.elements, expected.elements);
    assert.equal(record.mesh.matrixAutoUpdate, false);
    assert.equal(record.mesh.matrixWorldNeedsUpdate, true);
  }
});
