import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";

import {
  TOPOLOGY_LINE_DEPTH_BIAS,
  applyLineDepthBias,
  createDisplayEdgeObject,
  createTopologyDisplayEdgeObject,
  lineSegmentPositionsFromGeometry,
  syncLineMaterialOpacity,
  syncScreenSpaceLineMaterialResolution,
  topologyLineDepthBiasForWidth
} from "./renderEdges.js";

function edgeContext(materials = new Set()) {
  return {
    THREE,
    Line2,
    LineGeometry,
    LineSegments2,
    LineSegmentsGeometry,
    LineMaterial,
    registerScreenSpaceLineMaterial: (material) => materials.add(material),
    unregisterScreenSpaceLineMaterial: (material) => materials.delete(material)
  };
}

function twoPointGeometry() {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([
    0, 0, 0,
    1, 0, 0
  ]), 3));
  return geometry;
}

test("line segment extraction uses the geometry position buffer unchanged", () => {
  const geometry = twoPointGeometry();
  const positions = geometry.getAttribute("position").array;

  assert.equal(lineSegmentPositionsFromGeometry(geometry), positions);
});

test("screen-space display edge creation registers material settings", () => {
  const materials = new Set();
  const { edgeMesh, edgeMaterial } = createDisplayEdgeObject(edgeContext(materials), {
    geometry: twoPointGeometry(),
    edgeSettings: {
      color: "#123456",
      opacity: 0.42,
      thickness: 2
    },
    baseTheme: {
      edge: "#000000",
      edgeOpacity: 0.84
    },
    partId: "part-a",
    displayMode: "solid",
    thickness: 2
  }, materials);

  assert.equal(edgeMesh.userData.partId, "part-a");
  assert.equal(edgeMaterial.opacity, 0.42);
  assert.equal(edgeMaterial.linewidth, 2);
  assert.equal(edgeMaterial.polygonOffset, true);
  assert.equal(edgeMaterial.polygonOffsetFactor, 0);
  assert.equal(edgeMaterial.polygonOffsetUnits, -5);
  assert.equal(materials.has(edgeMaterial), true);

  syncScreenSpaceLineMaterialResolution(materials, 640, 480);
  assert.equal(edgeMaterial.resolution.x, 640);
  assert.equal(edgeMaterial.resolution.y, 480);
});

test("screen-space display edges can render through surfaces", () => {
  const { edgeMaterial } = createDisplayEdgeObject(edgeContext(), {
    geometry: twoPointGeometry(),
    edgeSettings: {
      color: "#123456",
      opacity: 0.42,
      thickness: 2,
      depthTest: false
    },
    baseTheme: {
      edge: "#000000",
      edgeOpacity: 0.84
    },
    partId: "part-a",
    displayMode: "hidden_edges",
    thickness: 2
  });

  assert.equal(edgeMaterial.depthTest, false);
});

test("wireframe display edges preserve high opacity and basic line material", () => {
  const { edgeMesh, edgeMaterial } = createDisplayEdgeObject(edgeContext(), {
    geometry: twoPointGeometry(),
    edgeSettings: {
      color: "#123456",
      opacity: 0.2
    },
    baseTheme: {
      edge: "#000000",
      edgeOpacity: 0.84
    },
    partId: "wire-a",
    displayMode: "wireframe",
    wireframeEdgeColor: "#abcdef"
  });

  assert.equal(edgeMesh.userData.partId, "wire-a");
  assert.equal(edgeMaterial.isLineBasicMaterial, true);
  assert.equal(edgeMaterial.opacity, 0.9);
  assert.equal(edgeMaterial.depthTest, false);
});

test("topology display edge helper builds filtered screen-space edges", () => {
  const materials = new Set();
  const line = createTopologyDisplayEdgeObject(
    edgeContext(materials),
    {
      proxy: {
        edgePositions: new Float32Array([0, 0, 0, 1, 0, 0]),
        edgeIndices: new Uint32Array([0, 1])
      }
    },
    {
      color: "#654321",
      opacity: 0.66,
      thickness: 1.5
    },
    {
      edge: "#000000",
      edgeOpacity: 0.84,
      edgeThickness: 1
    },
    materials
  );

  assert.equal(line.name, "TopologyDisplayEdges");
  assert.equal(line.userData.partId, "__topology__");
  assert.equal(line.material.opacity, 0.66);
  assert.equal(line.material.linewidth, 1.5);
  assert.equal(line.material.polygonOffset, true);
  assert.equal(line.material.polygonOffsetUnits, -5);
});

test("topology display edge helper renders feature-class edges by default", () => {
  const line = createTopologyDisplayEdgeObject(
    edgeContext(),
    {
      edges: [
        { visibilityClass: "feature", segmentStart: 0, segmentCount: 1 },
        { visibilityClass: "tangent", segmentStart: 1, segmentCount: 1 },
        { visibilityClass: "seam", segmentStart: 2, segmentCount: 1 }
      ],
      proxy: {
        edgePositions: new Float32Array([
          0, 0, 0,
          1, 0, 0,
          2, 0, 0,
          3, 0, 0,
          4, 0, 0,
          5, 0, 0
        ]),
        edgeIndices: new Uint32Array([0, 1, 2, 3, 4, 5]),
        edgeIds: new Uint32Array([0, 1, 2])
      }
    },
    {},
    {
      edge: "#000000",
      edgeOpacity: 0.84,
      edgeThickness: 1
    }
  );

  assert.equal(line.isLine, true);
  assert.equal(line.geometry.getAttribute("position").count, 2);
});

test("topology display edge helper renders row-backed CAD edges as continuous strips", () => {
  const line = createTopologyDisplayEdgeObject(
    edgeContext(),
    {
      edges: [
        { visibilityClass: "feature", segmentStart: 0, segmentCount: 2 }
      ],
      proxy: {
        edgePositions: new Float32Array([
          0, 0, 0,
          1, 0, 0,
          2, 0, 0
        ]),
        edgeIndices: new Uint32Array([0, 1, 1, 2]),
        edgeIds: new Uint32Array([0, 0])
      }
    },
    {},
    {
      edge: "#000000",
      edgeOpacity: 0.84,
      edgeThickness: 1
    }
  );

  assert.equal(line.isLine, true);
  assert.equal(line.geometry.getAttribute("position").count, 3);
});

test("topology display edge helper keeps large edge sets batched", () => {
  const edgeCount = 1201;
  const points = new Float32Array((edgeCount + 1) * 3);
  const edgeIndices = new Uint32Array(edgeCount * 2);
  const edgeIds = new Uint32Array(edgeCount);
  const edges = [];
  for (let index = 0; index < edgeCount; index += 1) {
    points[index * 3] = index;
    points[(index + 1) * 3] = index + 1;
    edgeIndices[index * 2] = index;
    edgeIndices[(index * 2) + 1] = index + 1;
    edgeIds[index] = index;
    edges.push({ visibilityClass: "feature", segmentStart: index, segmentCount: 1 });
  }

  const line = createTopologyDisplayEdgeObject(
    edgeContext(),
    {
      edges,
      proxy: {
        edgePositions: points,
        edgeIndices,
        edgeIds
      }
    },
    {},
    {
      edge: "#000000",
      edgeOpacity: 0.84,
      edgeThickness: 1
    }
  );

  assert.equal(line.type, "LineSegments2");
  assert.notEqual(line.isLine2, true);
  assert.equal(line.geometry.attributes.instanceStart.count, edgeCount);
});

test("topology display edge helper renders enabled classified edge styles", () => {
  const group = createTopologyDisplayEdgeObject(
    edgeContext(),
    {
      edges: [
        { visibilityClass: "feature", segmentStart: 0, segmentCount: 1 },
        { visibilityClass: "tangent", segmentStart: 1, segmentCount: 1 },
        { visibilityClass: "seam", segmentStart: 2, segmentCount: 1 },
        { visibilityClass: "degenerate", segmentStart: 3, segmentCount: 1 }
      ],
      proxy: {
        edgePositions: new Float32Array([
          0, 0, 0,
          1, 0, 0,
          2, 0, 0,
          3, 0, 0,
          4, 0, 0,
          5, 0, 0,
          6, 0, 0,
          7, 0, 0
        ]),
        edgeIndices: new Uint32Array([0, 1, 2, 3, 4, 5, 6, 7]),
        edgeIds: new Uint32Array([0, 1, 2, 3])
      }
    },
    {
      color: "#132232",
      opacity: 0.5,
      classes: {
        feature: { opacity: 1, thickness: 1 },
        tangent: { opacity: 0.32, thickness: 0.75 },
        seam: { opacity: 0.7, thickness: 1 },
        degenerate: { opacity: 1, thickness: 0 }
      }
    },
    {
      edge: "#000000",
      edgeOpacity: 0.84,
      edgeThickness: 1
    }
  );

  assert.equal(group.children.length, 3);
  assert.equal(group.children[0].material.linewidth, 1);
  assert.equal(group.children[0].material.opacity, 1);
  assert.equal(group.children[1].material.linewidth, 0.75);
  assert.equal(group.children[1].material.opacity, 0.32);
  assert.equal(group.children[1].material.polygonOffsetUnits, -6);
  assert.equal(group.children[2].material.linewidth, 1);
  assert.equal(group.children[2].material.opacity, 0.7);
  assert.equal(group.children[2].material.polygonOffsetUnits, -6);
});

test("thick topology display edges get stronger depth separation", () => {
  const line = createTopologyDisplayEdgeObject(
    edgeContext(),
    {
      proxy: {
        edgePositions: new Float32Array([0, 0, 0, 1, 0, 0]),
        edgeIndices: new Uint32Array([0, 1])
      }
    },
    {
      thickness: 6
    },
    {
      edge: "#000000",
      edgeOpacity: 0.84,
      edgeThickness: 1
    }
  );

  assert.equal(topologyLineDepthBiasForWidth(1), TOPOLOGY_LINE_DEPTH_BIAS);
  assert.equal(topologyLineDepthBiasForWidth(6), 0.00575);
  assert.equal(topologyLineDepthBiasForWidth(1, { visibilityClass: "tangent" }), 0.006);
  assert.equal(topologyLineDepthBiasForWidth(6, { visibilityClass: "seam" }), 0.00725);
  assert.equal(line.material.polygonOffsetUnits, -6);
});

test("topology display edge helper splits dimmed and focused inspection edges", () => {
  const materials = new Set();
  const group = createTopologyDisplayEdgeObject(
    edgeContext(materials),
    {
      edges: [
        { occurrenceId: "part-a", segmentStart: 0, segmentCount: 1 },
        { occurrenceId: "part-b", segmentStart: 1, segmentCount: 1 }
      ],
      proxy: {
        edgePositions: new Float32Array([
          0, 0, 0,
          1, 0, 0,
          2, 0, 0,
          3, 0, 0
        ]),
        edgeIndices: new Uint32Array([0, 1, 2, 3]),
        edgeIds: new Uint32Array([0, 1])
      }
    },
    {
      color: "#654321",
      opacity: 0.66,
      dimmedOpacity: 0.035,
      focusedPartIds: ["part-a"]
    },
    {
      edge: "#000000",
      edgeOpacity: 0.84,
      edgeThickness: 1
    },
    materials
  );

  assert.equal(group.name, "TopologyDisplayEdges");
  assert.equal(group.children.length, 2);
  assert.equal(group.children[0].material.opacity, 0.035);
  assert.equal(group.children[1].material.opacity, 0.66);
});

test("topology display edge helper renders highlighted node edges with theme settings", () => {
  const materials = new Set();
  const line = createTopologyDisplayEdgeObject(
    edgeContext(materials),
    {
      edges: [
        { occurrenceId: "part-a", segmentStart: 0, segmentCount: 1 },
        { occurrenceId: "part-b", segmentStart: 1, segmentCount: 1 },
        { occurrenceId: "part-a.child", segmentStart: 2, segmentCount: 1 }
      ],
      proxy: {
        edgePositions: new Float32Array([
          0, 0, 0,
          1, 0, 0,
          2, 0, 0,
          3, 0, 0,
          4, 0, 0,
          5, 0, 0
        ]),
        edgeIndices: new Uint32Array([0, 1, 2, 3, 4, 5]),
        edgeIds: new Uint32Array([0, 1, 2])
      }
    },
    {
      color: "#222222",
      opacity: 0.48,
      thickness: 2.25,
      highlightPartIds: ["part-a"],
      highlightColor: "#4f9dff"
    },
    {
      edge: "#000000",
      edgeOpacity: 0.84,
      edgeThickness: 1
    },
    materials
  );

  assert.equal(line.name, "TopologyDisplayEdgeHighlights");
  assert.equal(line.userData.partId, "__topology_highlight__");
  assert.equal(line.material.color.getHexString(), "4f9dff");
  assert.equal(line.material.opacity, 0.48);
  assert.equal(line.material.linewidth, 2.25);
  assert.equal(line.renderOrder, 26);
  assert.doesNotMatch(line.material.customProgramCacheKey(), /lineDepthBias/);
  assert.equal(line.geometry.attributes.instanceStart.count, 2);
  assert.equal(line.geometry.attributes.instanceEnd.count, 2);
});

test("line depth bias uses fixed-function polygon offset", () => {
  const material = new THREE.LineBasicMaterial();
  applyLineDepthBias(material, 0.0003);
  const shader = {
    uniforms: {},
    vertexShader: "void main() {\n#include <logdepthbuf_vertex>\n}"
  };

  material.onBeforeCompile(shader, {});

  assert.equal(material.polygonOffset, true);
  assert.equal(material.polygonOffsetFactor, 0);
  assert.equal(material.polygonOffsetUnits, -1);
  assert.deepEqual(shader.uniforms, {});
  assert.doesNotMatch(shader.vertexShader, /lineDepthBias/);
});

test("topology display edge helper renders raw CAD edge segments as one object", () => {
  const materials = new Set();
  const line = createTopologyDisplayEdgeObject(
    edgeContext(materials),
    {
      proxy: {
        edgePositions: new Float32Array([
          0, 0, 0,
          1, 0, 0,
          2, 0, 0,
          3, 0, 0
        ]),
        edgeIndices: new Uint32Array([0, 1, 2, 3])
      }
    },
    {},
    {
      edge: "#000000",
      edgeOpacity: 0.84,
      edgeThickness: 1
    },
    materials
  );

  assert.equal(line.name, "TopologyDisplayEdges");
  assert.equal(line.userData.partId, "__topology__");
  assert.equal(materials.size, 1);
});

test("topology display edge helper falls back to basic line strips", () => {
  const context = edgeContext();
  delete context.Line2;
  delete context.LineGeometry;
  delete context.LineSegments2;
  delete context.LineSegmentsGeometry;
  const line = createTopologyDisplayEdgeObject(
    context,
    {
      edges: [
        {
          flags: 0,
          segmentStart: 0,
          segmentCount: 2
        }
      ],
      proxy: {
        edgePositions: new Float32Array([
          0, 0, 0,
          1, 0, 0,
          2, 0, 0
        ]),
        edgeIndices: new Uint32Array([0, 1, 1, 2]),
        edgeIds: new Uint32Array([0, 0])
      }
    },
    {},
    {
      edge: "#000000",
      edgeOpacity: 0.84,
      edgeThickness: 1
    }
  );

  assert.equal(line.isLine, true);
  assert.equal(line.geometry.getAttribute("position").count, 3);
});

test("line material opacity helper clamps transparency consistently", () => {
  const material = new THREE.LineBasicMaterial({ opacity: 1, transparent: false });

  syncLineMaterialOpacity(material, 0.25);
  assert.equal(material.opacity, 0.25);
  assert.equal(material.transparent, true);

  syncLineMaterialOpacity(material, 5);
  assert.equal(material.opacity, 1);
  assert.equal(material.transparent, false);
});
