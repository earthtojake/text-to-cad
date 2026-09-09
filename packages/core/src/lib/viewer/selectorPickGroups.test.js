import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import {
  buildEdgePickLines,
  buildFacePickMesh,
  buildGlbFaceIdsForMesh,
  buildGlbFaceIdsForPart,
  buildVertexPickPoints,
  syncDisplayMeshFaceIds,
  syncSelectorPickGroups,
  TOPOLOGY_FACE_ID_NONE
} from "./selectorPickGroups.js";

function sampleSelectorRuntime() {
  return {
    proxy: {
      facePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0
      ]),
      faceIndices: new Uint32Array([0, 1, 2]),
      faceIds: new Uint32Array([7]),
      edgePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0
      ]),
      edgeIndices: new Uint32Array([0, 1]),
      edgeIds: new Uint32Array([11]),
      vertexPositions: new Float32Array([
        0, 0, 0
      ]),
      vertexIds: new Uint32Array([13])
    }
  };
}

test("selector pick builders create invisible face, edge, and vertex pick objects", () => {
  const selectorRuntime = sampleSelectorRuntime();
  const faceMesh = buildFacePickMesh(THREE, selectorRuntime);
  const edgeLines = buildEdgePickLines(THREE, selectorRuntime);
  const vertexPoints = buildVertexPickPoints(THREE, selectorRuntime);

  assert.equal(faceMesh.type, "Mesh");
  assert.equal(faceMesh.material.opacity, 0);
  assert.equal(faceMesh.material.colorWrite, false);
  assert.equal(faceMesh.frustumCulled, false);
  assert.deepEqual([...faceMesh.userData.faceIds], [7]);
  assert.equal(faceMesh.geometry.getAttribute("position").count, 3);
  assert.equal(faceMesh.geometry.getIndex().count, 3);

  assert.equal(edgeLines.type, "LineSegments");
  assert.equal(edgeLines.material.opacity, 0);
  assert.equal(edgeLines.frustumCulled, false);
  assert.deepEqual([...edgeLines.userData.edgeIds], [11]);

  assert.equal(vertexPoints.type, "Points");
  assert.equal(vertexPoints.material.opacity, 0);
  assert.equal(vertexPoints.material.size, 1.5);
  assert.equal(vertexPoints.frustumCulled, false);
  assert.deepEqual([...vertexPoints.userData.vertexIds], [13]);

  assert.equal(buildFacePickMesh(THREE, { proxy: {} }), null);
  assert.equal(buildEdgePickLines(THREE, { proxy: {} }), null);
  assert.equal(buildVertexPickPoints(THREE, { proxy: {} }), null);
});

test("selector face id helpers map GLB face runs to parts and whole meshes", () => {
  const selectorRuntime = {
    occurrenceIdByRowIndex: new Map([
      [0, "part-a"],
      [1, "part-b"]
    ]),
    proxy: {
      faceRuns: new Uint32Array([
        0, 0, 1, 2, 7,
        1, 0, 0, 1, 9
      ])
    }
  };

  const partAFaceIds = buildGlbFaceIdsForPart({
    id: "part-a",
    triangleCount: 4
  }, selectorRuntime);
  assert.deepEqual([...partAFaceIds], [TOPOLOGY_FACE_ID_NONE, 7, 7, TOPOLOGY_FACE_ID_NONE]);

  const meshFaceIds = buildGlbFaceIdsForMesh({
    indices: new Uint32Array(new Array(7 * 3).fill(0)),
    parts: [
      {
        id: "part-a",
        triangleOffset: 0,
        triangleCount: 4
      },
      {
        id: "part-b",
        triangleOffset: 4,
        triangleCount: 3
      }
    ]
  }, selectorRuntime);
  assert.deepEqual([...meshFaceIds], [
    TOPOLOGY_FACE_ID_NONE,
    7,
    7,
    TOPOLOGY_FACE_ID_NONE,
    9,
    TOPOLOGY_FACE_ID_NONE,
    TOPOLOGY_FACE_ID_NONE
  ]);
  assert.equal(buildGlbFaceIdsForPart({ id: "missing", triangleCount: 1 }, selectorRuntime), null);
});

test("selector face id helpers honor source part ranges", () => {
  const selectorRuntime = {
    occurrenceIdByRowIndex: new Map([[0, "source-a"]]),
    proxy: {
      faceRuns: new Uint32Array([
        0, 2, 1, 2, 21
      ])
    }
  };
  const faceIds = buildGlbFaceIdsForPart({
    id: "display-a",
    triangleCount: 5,
    sourcePartRanges: [
      {
        occurrenceId: "source-a",
        primitiveIndex: 2,
        triangleOffset: 2,
        triangleCount: 3
      }
    ]
  }, selectorRuntime);

  assert.deepEqual([...faceIds], [
    TOPOLOGY_FACE_ID_NONE,
    TOPOLOGY_FACE_ID_NONE,
    TOPOLOGY_FACE_ID_NONE,
    21,
    21
  ]);
});

test("selector pick helpers sync display mesh face ids", () => {
  const selectorRuntime = {
    occurrenceIdByRowIndex: new Map([[0, "part-a"]]),
    proxy: {
      faceRuns: new Uint32Array([0, 0, 0, 1, 5])
    }
  };
  const partMesh = { userData: {} };
  const modelMesh = { userData: {} };
  const missingMesh = { userData: { faceIds: new Uint32Array([99]) } };
  const runtime = {
    displayRecords: [
      { partId: "part-a", mesh: partMesh },
      { partId: "__model__", mesh: modelMesh },
      { partId: "missing", mesh: missingMesh }
    ]
  };

  syncDisplayMeshFaceIds(runtime, {
    indices: new Uint32Array([0, 1, 2]),
    parts: [
      {
        id: "part-a",
        triangleOffset: 0,
        triangleCount: 1
      }
    ]
  }, selectorRuntime);

  assert.deepEqual([...partMesh.userData.faceIds], [5]);
  assert.deepEqual([...modelMesh.userData.faceIds], [5]);
  assert.equal("faceIds" in missingMesh.userData, false);
});

test("selector pick helpers sync display mesh face ids from display record source parts", () => {
  const selectorRuntime = {
    occurrenceIdByRowIndex: new Map([[0, "part-a"]]),
    proxy: {
      faceRuns: new Uint32Array([0, 0, 0, 1, 5])
    }
  };
  const partMesh = { userData: {} };
  const runtime = {
    displayRecords: [
      {
        partId: "part-a",
        sourcePart: {
          id: "part-a",
          triangleCount: 1
        },
        mesh: partMesh
      }
    ]
  };

  syncDisplayMeshFaceIds(runtime, {
    indices: new Uint32Array([0, 1, 2]),
    parts: null
  }, selectorRuntime);

  assert.deepEqual([...partMesh.userData.faceIds], [5]);
});

test("selector pick helpers sync pick groups and preserve caller-owned clearing", () => {
  const runtime = {
    THREE,
    facePickGroup: new THREE.Group(),
    edgePickGroup: new THREE.Group(),
    vertexPickGroup: new THREE.Group()
  };
  runtime.facePickGroup.add(new THREE.Object3D());
  runtime.edgePickGroup.add(new THREE.Object3D());
  runtime.vertexPickGroup.add(new THREE.Object3D());
  const cleared = [];
  const modelOffset = new THREE.Vector3(1, 2, 3);

  syncSelectorPickGroups(runtime, sampleSelectorRuntime(), modelOffset, {
    clearSceneGroup(group) {
      cleared.push(group);
      while (group.children.length) {
        group.remove(group.children[0]);
      }
    }
  });

  assert.deepEqual(cleared, [runtime.facePickGroup, runtime.edgePickGroup, runtime.vertexPickGroup]);
  assert.equal(runtime.facePickGroup.children.length, 1);
  assert.equal(runtime.edgePickGroup.children.length, 1);
  assert.equal(runtime.vertexPickGroup.children.length, 1);
  assert.equal(runtime.facePickMesh, runtime.facePickGroup.children[0]);
  assert.equal(runtime.edgePickLines, runtime.edgePickGroup.children[0]);
  assert.deepEqual(runtime.edgePickObjects, [runtime.edgePickLines]);
  assert.equal(runtime.vertexPickPoints, runtime.vertexPickGroup.children[0]);
  assert.deepEqual(runtime.facePickGroup.position.toArray(), [1, 2, 3]);
  assert.deepEqual(runtime.edgePickGroup.position.toArray(), [1, 2, 3]);
  assert.deepEqual(runtime.vertexPickGroup.position.toArray(), [1, 2, 3]);

  syncSelectorPickGroups(runtime, { proxy: {} }, null, {
    clearSceneGroup(group) {
      while (group.children.length) {
        group.remove(group.children[0]);
      }
    }
  });
  assert.equal(runtime.facePickMesh, null);
  assert.equal(runtime.edgePickLines, null);
  assert.equal(runtime.vertexPickPoints, null);
  assert.deepEqual(runtime.edgePickObjects, []);
  assert.deepEqual(runtime.facePickGroup.position.toArray(), [0, 0, 0]);
});
