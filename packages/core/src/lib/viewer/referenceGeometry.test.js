import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import {
  buildEdgeLinePositionsFromProxy,
  buildFallbackFaceFanGeometry,
  buildFaceBoundaryLinePositions,
  buildFaceFillGeometryFromDisplayMeshes,
  buildFaceFillGeometryFromProxy,
  buildVertexMarkerMesh,
  createReferenceEdgeGeometryFromPoints,
  createReferenceFaceBoundaryGeometry,
  createReferenceFaceFillGeometry,
  displayRecordForReference,
  faceFillOffset,
  referenceExplodedViewMatrix,
  REFERENCE_CORNER_COLOR,
  REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER,
  REFERENCE_HOVER_HIGHLIGHT_WIDTH_MULTIPLIER
} from "./referenceGeometry.js";

const EPSILON = 1e-6;

function assertNear(actual, expected, message = "") {
  assert.ok(Math.abs(actual - expected) < EPSILON, `${message} expected ${expected}, received ${actual}`);
}

function assertArrayNear(actual, expected, message = "") {
  assert.equal(actual.length, expected.length, `${message} length`);
  for (let index = 0; index < expected.length; index += 1) {
    assertNear(actual[index], expected[index], `${message}[${index}]`);
  }
}

function createRuntime({
  cameraPosition = [0, 0, 10],
  modelPosition = [0, 0, 0],
  modelRadius = 10,
  displayRecords = []
} = {}) {
  const camera = new THREE.PerspectiveCamera();
  camera.position.set(...cameraPosition);
  const modelGroup = new THREE.Group();
  modelGroup.position.set(...modelPosition);
  return {
    camera,
    modelGroup,
    modelRadius,
    displayRecords
  };
}

function geometryPositions(geometry) {
  return [...geometry.getAttribute("position").array];
}

test("reference face fill offsets follow the visible face normal", () => {
  const reference = {
    pickData: {
      center: [0, 0, 0],
      normal: [0, 0, 2]
    }
  };

  assertArrayNear(faceFillOffset(createRuntime({ cameraPosition: [0, 0, 10] }), reference), [0, 0, 0.015], "front offset");
  assertArrayNear(faceFillOffset(createRuntime({ cameraPosition: [0, 0, -10] }), reference), [0, 0, -0.015], "back offset");
  assertArrayNear(faceFillOffset(createRuntime({ modelRadius: 40 }), reference), [0, 0, 0.03], "scaled offset");
  assert.deepEqual(faceFillOffset({}, reference), [0, 0, 0]);
  assert.deepEqual(faceFillOffset(createRuntime(), {
    pickData: {
      surfaceType: "cylinder",
      center: [0, 0, 0],
      normal: [1, 0, 0]
    }
  }), [0, 0, 0]);
});

test("reference edge geometry builds line segment buffers from point paths", () => {
  const geometry = createReferenceEdgeGeometryFromPoints(THREE, [
    [0, 0, 0],
    [1, 0, 0],
    [1, 1, 0]
  ]);

  assertArrayNear(geometryPositions(geometry), [
    0, 0, 0,
    1, 0, 0,
    1, 0, 0,
    1, 1, 0
  ], "edge geometry");
  assert.equal(createReferenceEdgeGeometryFromPoints(THREE, [[0, 0, 0]]), null);
});

test("reference face boundary geometry prefers loop metadata and falls back to pick loops", () => {
  const fromMeta = createReferenceFaceBoundaryGeometry(THREE, {
    pickData: {
      loopsMeta: [
        { points: [[0, 0, 0], [1, 0, 0]] }
      ],
      loops: [
        [[9, 0, 0], [10, 0, 0]]
      ]
    }
  });
  assertArrayNear(geometryPositions(fromMeta), [
    0, 0, 0,
    1, 0, 0,
    1, 0, 0,
    0, 0, 0
  ], "metadata boundary");

  const fromLoops = createReferenceFaceBoundaryGeometry(THREE, {
    pickData: {
      loops: [
        [[2, 0, 0], [3, 0, 0]]
      ]
    }
  });
  assertArrayNear(geometryPositions(fromLoops), [
    2, 0, 0,
    3, 0, 0,
    3, 0, 0,
    2, 0, 0
  ], "fallback boundary");
});

test("reference fallback face fan geometry uses the supplied centroid", () => {
  const geometry = buildFallbackFaceFanGeometry(THREE, [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1]
  ], [0, 0, 0]);

  assertArrayNear(geometryPositions(geometry), [
    0, 0, 0,
    1, 0, 0,
    0, 1, 0,
    0, 0, 0,
    0, 1, 0,
    0, 0, 1,
    0, 0, 0,
    0, 0, 1,
    1, 0, 0
  ], "fallback fan");
  assert.equal(buildFallbackFaceFanGeometry(THREE, [[0, 0, 0], [1, 0, 0]]), null);
});

test("reference face fill geometry triangulates planar loops", () => {
  const geometry = createReferenceFaceFillGeometry(THREE, {
    pickData: {
      loops: [
        [
          [0, 0, 0],
          [1, 0, 0],
          [1, 1, 0],
          [0, 1, 0]
        ]
      ],
      surface: {
        type: "PLANE",
        origin: [0, 0, 0],
        xDir: [1, 0, 0],
        yDir: [0, 1, 0],
        normal: [0, 0, 1]
      }
    }
  });
  const positions = geometryPositions(geometry);
  assert.equal(positions.length, 18);
  for (let index = 2; index < positions.length; index += 3) {
    assertNear(positions[index], 0, `z ${index}`);
  }
  assert.equal(createReferenceFaceFillGeometry(THREE, {
    pickData: {
      loops: [
        [[0, 0, 0], [1, 0, 0]]
      ]
    }
  }), null);
});


test("reference proxy helpers build face fill and edge line buffers from selector data", () => {
  const runtime = createRuntime();
  const selectorRuntime = {
    proxy: {
      facePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0,
        0, 0, 1
      ]),
      faceIndices: new Uint32Array([0, 1, 2, 1, 2, 3]),
      edgePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0
      ]),
      edgeIndices: new Uint32Array([0, 1, 1, 2])
    }
  };

  const faceGeometry = buildFaceFillGeometryFromProxy(runtime, THREE, selectorRuntime, {
    pickData: {
      triangleStart: 1,
      triangleCount: 1,
      center: [0, 0, 0],
      normal: [0, 0, 1]
    }
  });
  assertArrayNear([...faceGeometry.getAttribute("position").array], [
    1, 0, 0.015,
    0, 1, 0.015,
    0, 0, 1.015
  ], "face fill");

  assertArrayNear([...buildEdgeLinePositionsFromProxy(selectorRuntime, {
    pickData: {
      segmentStart: 1,
      segmentCount: 1
    }
  })], [
    1, 0, 0,
    0, 1, 0
  ], "edge line");

  assert.equal(buildFaceFillGeometryFromProxy(runtime, THREE, { proxy: {} }, { pickData: { triangleCount: 1 } }), null);
  assert.equal(buildEdgeLinePositionsFromProxy({ proxy: {} }, { pickData: { segmentCount: 1 } }), null);
});

test("reference face boundaries resolve adjacent edge selectors", () => {
  const edgeReference = {
    pickData: {
      segmentStart: 0,
      segmentCount: 1
    }
  };
  const selectorRuntime = {
    proxy: {
      edgePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0
      ]),
      edgeIndices: new Uint32Array([0, 1])
    },
    referenceByDisplaySelector: new Map([["edge-a", edgeReference]]),
    referenceByNormalizedSelector: new Map()
  };

  assertArrayNear([...buildFaceBoundaryLinePositions(selectorRuntime, {
    pickData: {
      adjacentSelectors: ["edge-a"]
    }
  })], [
    0, 0, 0,
    1, 0, 0
  ], "boundary");
  assert.equal(buildFaceBoundaryLinePositions(selectorRuntime, { pickData: { adjacentSelectors: ["missing"] } }), null);
});

test("reference display mesh fill geometry follows matching face ids and mesh matrix", () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([
    0, 0, 0,
    1, 0, 0,
    0, 1, 0,
    0, 0, 1
  ]), 3));
  geometry.setIndex(new THREE.BufferAttribute(new Uint32Array([0, 1, 2, 0, 2, 3]), 1));
  const mesh = new THREE.Mesh(geometry);
  mesh.userData.faceIds = new Uint32Array([7, 8]);
  mesh.position.set(10, 0, 0);
  mesh.updateMatrix();

  const runtime = createRuntime({
    displayRecords: [{ mesh }]
  });
  const fillGeometry = buildFaceFillGeometryFromDisplayMeshes(runtime, THREE, {
    rowIndex: 8,
    pickData: {
      center: [0, 0, 0],
      normal: [0, 0, 1]
    }
  });
  assertArrayNear([...fillGeometry.getAttribute("position").array], [
    10, 0, 0.015,
    10, 1, 0.015,
    10, 0, 1.015
  ], "display fill");
  assert.equal(buildFaceFillGeometryFromDisplayMeshes({ displayRecords: [] }, THREE, { rowIndex: 8 }), null);
});

test("reference vertex markers keep existing marker sizing and material settings", () => {
  const marker = buildVertexMarkerMesh(createRuntime({ modelRadius: 100 }), THREE, {
    pickData: {
      center: [1, 2, 3]
    }
  }, {
    color: REFERENCE_CORNER_COLOR,
    opacity: 0.75
  });
  assert.equal(marker.type, "Mesh");
  assert.equal(marker.position.x, 1);
  assert.equal(marker.position.y, 2);
  assert.equal(marker.position.z, 3);
  assert.equal(marker.renderOrder, 27);
  assert.equal(marker.material.color.getHexString(), "2563eb");
  assert.equal(marker.material.transparent, true);
  assert.equal(marker.material.opacity, 0.75);
  assertNear(marker.geometry.parameters.radius, 0.45, "marker radius");
  assert.equal(REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER, 3);
  assert.equal(REFERENCE_HOVER_HIGHLIGHT_WIDTH_MULTIPLIER, 3);
  assert.equal(buildVertexMarkerMesh(createRuntime(), THREE, { pickData: {} }), null);
});


function explodeRuntime(records) {
  return { displayRecords: records };
}

function movedRecord(partId, x) {
  return { partId, explodedViewMatrix: new THREE.Matrix4().makeTranslation(x, 0, 0) };
}

test("a reference resolves to the most specific display record that owns it", () => {
  const parent = movedRecord("o1", 5);
  const child = movedRecord("o1.3", 9);
  const runtime = explodeRuntime([parent, child, movedRecord("o1.30", 99)]);

  // o1.30 must NOT win on a string-prefix accident, and the deeper owner beats the shallower.
  assert.equal(displayRecordForReference(runtime, { occurrenceId: "o1.3" }), child);
  assert.equal(displayRecordForReference(runtime, { occurrenceId: "o1.3.1" }), child);
  assert.equal(displayRecordForReference(runtime, { occurrenceId: "o1.4" }), parent);
  assert.equal(displayRecordForReference(runtime, { occurrenceId: "o2.1" }), null);
  assert.equal(displayRecordForReference(runtime, { occurrenceId: "" }), null);
});

test("the whole-model record never owns a reference", () => {
  // `__model__` is the transform key for "move everything", not a part on screen; treating it
  // as an owner would give every highlight the model-level matrix on top of its own.
  const runtime = explodeRuntime([movedRecord("__model__", 7)]);
  assert.equal(displayRecordForReference(runtime, { occurrenceId: "o1.1" }), null);
});

test("the exploded offset is reported only for a part that actually moved", () => {
  const runtime = explodeRuntime([movedRecord("o1.1", 12), { partId: "o1.2", explodedViewMatrix: null }]);
  const matrix = referenceExplodedViewMatrix(runtime, { occurrenceId: "o1.1" });
  assert.equal(matrix.elements[12], 12);
  assert.equal(referenceExplodedViewMatrix(runtime, { occurrenceId: "o1.2" }), null);
  assert.equal(referenceExplodedViewMatrix(runtime, { occurrenceId: "o1.9" }), null);
  assert.equal(referenceExplodedViewMatrix({}, { occurrenceId: "o1.1" }), null);
});

test("the exploded offset is the record's own matrix, NOT its composed effect matrix", () => {
  // A parameter effect is already baked into the transformed selector runtime the highlight
  // slices its positions from. Returning effect * exploded here would apply the effect twice
  // and send the highlight to double the displacement.
  const record = {
    partId: "o1.1",
    effectMatrix: new THREE.Matrix4().makeTranslation(100, 0, 0),
    explodedViewMatrix: new THREE.Matrix4().makeTranslation(3, 0, 0)
  };
  const matrix = referenceExplodedViewMatrix(explodeRuntime([record]), { occurrenceId: "o1.1" });
  assert.equal(matrix.elements[12], 3);
});
