import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
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
