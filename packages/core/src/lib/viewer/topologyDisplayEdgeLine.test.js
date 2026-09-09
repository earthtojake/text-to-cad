import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";

import {
  createRecordTopologyDisplayEdgeGroup,
  syncTopologyDisplayEdgeLine
} from "./topologyDisplayEdgeLine.js";

function displayEdgeRuntime(xOffset = 0) {
  return {
    edges: [{ occurrenceId: "part-a", segmentStart: 0, segmentCount: 1 }],
    proxy: {
      edgePositions: new Float32Array([
        xOffset, 0, 0,
        xOffset + 1, 0, 0
      ]),
      edgeIndices: new Uint32Array([0, 1]),
      edgeIds: new Uint32Array([0])
    }
  };
}

function createRuntime() {
  const materials = new Set();
  return {
    THREE,
    Line2,
    LineGeometry,
    LineSegments2,
    LineSegmentsGeometry,
    LineMaterial,
    edgesGroup: new THREE.Group(),
    displayRecords: [
      { partId: "part-a", material: new THREE.MeshBasicMaterial() }
    ],
    requestCount: 0,
    materials,
    registerScreenSpaceLineMaterial: (material) => materials.add(material),
    unregisterScreenSpaceLineMaterial: (material) => materials.delete(material),
    requestRender() {
      this.requestCount += 1;
    }
  };
}

function instanceStartX(line) {
  const instanceStart = line.geometry.attributes.instanceStart?.data?.array;
  if (instanceStart) {
    return instanceStart[0];
  }
  return line.geometry.attributes.position.array[0];
}

test("syncTopologyDisplayEdgeLine updates edge overlays immediately and skips delayed duplicate syncs", () => {
  const runtime = createRuntime();
  let clipSyncCount = 0;
  const syncClip = () => {
    clipSyncCount += 1;
  };
  const firstRuntime = displayEdgeRuntime(0);

  assert.equal(syncTopologyDisplayEdgeLine(runtime, firstRuntime, {
    visible: true,
    edgeSettings: { color: "#111111", opacity: 0.8, thickness: 1 },
    focusedPartIds: [],
    viewerTheme: { edge: "#111111", edgeOpacity: 0.8, edgeThickness: 1 },
    syncClip
  }), true);

  const firstLine = runtime.topologyDisplayEdgeLine;
  assert.equal(runtime.edgesGroup.children.length, 1);
  assert.equal(instanceStartX(firstLine), 0);
  assert.equal(runtime.displayRecords[0].material.polygonOffset, false);
  assert.equal(runtime.displayRecords[0].material.polygonOffsetFactor, 0);
  assert.equal(runtime.displayRecords[0].material.polygonOffsetUnits, 0);
  assert.equal(runtime.requestCount, 1);
  assert.equal(clipSyncCount, 1);

  assert.equal(syncTopologyDisplayEdgeLine(runtime, firstRuntime, {
    visible: true,
    edgeSettings: { color: "#111111", opacity: 0.8, thickness: 1 },
    focusedPartIds: [],
    viewerTheme: { edge: "#111111", edgeOpacity: 0.8, edgeThickness: 1 },
    syncClip
  }), false);

  assert.equal(runtime.topologyDisplayEdgeLine, firstLine);
  assert.equal(runtime.edgesGroup.children.length, 1);
  assert.equal(runtime.requestCount, 1);
  assert.equal(clipSyncCount, 1);

  const nextRuntime = displayEdgeRuntime(5);
  assert.equal(syncTopologyDisplayEdgeLine(runtime, nextRuntime, {
    visible: true,
    edgeSettings: { color: "#111111", opacity: 0.8, thickness: 1 },
    focusedPartIds: [],
    viewerTheme: { edge: "#111111", edgeOpacity: 0.8, edgeThickness: 1 },
    syncClip
  }), true);

  assert.notEqual(runtime.topologyDisplayEdgeLine, firstLine);
  assert.equal(runtime.edgesGroup.children.length, 1);
  assert.equal(instanceStartX(runtime.topologyDisplayEdgeLine), 5);
  assert.equal(runtime.materials.size, 0);
  assert.equal(runtime.requestCount, 2);
  assert.equal(clipSyncCount, 2);
});

test("syncTopologyDisplayEdgeLine can move per-record topology edges with solid effect matrices", () => {
  const runtime = createRuntime();
  const sourceRuntime = displayEdgeRuntime(0);
  const firstMatrix = new THREE.Matrix4().makeTranslation(3, 0, 0);
  runtime.displayRecords = [
    {
      partId: "part-a",
      effectMatrix: firstMatrix,
      material: new THREE.MeshBasicMaterial(),
      mesh: { visible: true }
    }
  ];

  assert.equal(syncTopologyDisplayEdgeLine(runtime, sourceRuntime, {
    visible: true,
    edgeSettings: { color: "#111111", opacity: 0.8, thickness: 1 },
    viewerTheme: { edge: "#111111", edgeOpacity: 0.8, edgeThickness: 1 },
    transformByRecord: true,
    displayRecords: runtime.displayRecords
  }), true);

  const group = runtime.topologyDisplayEdgeLine;
  const line = group.children[0];
  assert.equal(group.children.length, 1);
  assert.equal(instanceStartX(line), 0);
  assert.equal(line.matrix.elements[12], 3);
  assert.equal(runtime.requestCount, 1);

  runtime.displayRecords[0].effectMatrix = new THREE.Matrix4().makeTranslation(7, 0, 0);
  assert.equal(syncTopologyDisplayEdgeLine(runtime, sourceRuntime, {
    visible: true,
    edgeSettings: { color: "#111111", opacity: 0.8, thickness: 1 },
    viewerTheme: { edge: "#111111", edgeOpacity: 0.8, edgeThickness: 1 },
    transformByRecord: true,
    displayRecords: runtime.displayRecords
  }), true);

  assert.equal(runtime.topologyDisplayEdgeLine, group);
  assert.equal(group.children[0], line);
  assert.equal(line.matrix.elements[12], 7);
  assert.equal(instanceStartX(line), 0);
  assert.equal(runtime.requestCount, 2);
});

test("createRecordTopologyDisplayEdgeGroup transforms highlighted node edges", () => {
  const runtime = createRuntime();
  const sourceRuntime = {
    edges: [
      { occurrenceId: "assembly.part-a", segmentStart: 0, segmentCount: 1 },
      { occurrenceId: "assembly.part-b", segmentStart: 1, segmentCount: 1 }
    ],
    proxy: {
      edgePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0,
        10, 0, 0,
        11, 0, 0
      ]),
      edgeIndices: new Uint32Array([0, 1, 2, 3]),
      edgeIds: new Uint32Array([0, 1])
    }
  };
  runtime.displayRecords = [
    {
      partId: "assembly.part-a",
      effectMatrix: new THREE.Matrix4().makeTranslation(3, 0, 0),
      material: new THREE.MeshBasicMaterial(),
      mesh: { visible: true }
    },
    {
      partId: "assembly.part-b",
      effectMatrix: new THREE.Matrix4().makeTranslation(7, 0, 0),
      material: new THREE.MeshBasicMaterial(),
      mesh: { visible: true }
    }
  ];

  const group = createRecordTopologyDisplayEdgeGroup(runtime, sourceRuntime, {
    edgeSettings: {
      color: "#111111",
      opacity: 0.8,
      thickness: 1,
      highlightPartIds: ["assembly.part-b"],
      highlightColor: "#4090ff",
      highlightRenderOrder: 26
    },
    viewerTheme: { edge: "#111111", edgeOpacity: 0.8, edgeThickness: 1 },
    displayRecords: runtime.displayRecords
  });

  assert.equal(group.children.length, 1);
  const line = group.children[0];
  assert.equal(line.userData.cadTopologyDisplayRecordPartId, "assembly.part-b");
  assert.equal(instanceStartX(line), 10);
  assert.equal(line.matrix.elements[12], 7);
  assert.equal(line.renderOrder, 26);
});
