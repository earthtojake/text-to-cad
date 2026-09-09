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
  createCadEdgeLineSegments,
  createDisplayEdgeObject,
  createScreenSpaceLineSegments,
  createTopologyDisplayEdgeObject,
  lineSegmentPositionsFromGeometry,
  screenSpaceLineDeviceResolution,
  syncLineMaterialOpacity,
  syncRecordEdgeMaterials,
  syncScreenSpaceLineMaterialResolution,
  topologyLineDepthBiasForWidth
} from "./renderEdges.js";
import { CAD_EDGE_FEATHER_PIXELS } from "./cadEdgeInstances.js";

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
        feature: { color: "#101010", opacity: 1, thickness: 1 },
        tangent: { color: "#224466", opacity: 0.32, thickness: 0.75 },
        seam: { color: "#6688aa", opacity: 0.7, thickness: 1 },
        degenerate: { color: "#aa8844", opacity: 1, thickness: 0 }
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
  assert.equal(group.children[0].material.color.getHexString(), "101010");
  assert.equal(group.children[0].material.opacity, 1);
  assert.equal(group.children[1].material.linewidth, 0.75);
  assert.equal(group.children[1].material.color.getHexString(), "224466");
  assert.equal(group.children[1].material.opacity, 0.32);
  assert.equal(group.children[1].material.polygonOffsetUnits, -6);
  assert.equal(group.children[2].material.linewidth, 1);
  assert.equal(group.children[2].material.color.getHexString(), "6688aa");
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

test("CAD edge line segments wrap a shared vertex-coloured geometry", () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0]), 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(new Uint16Array(8), 4, true));
  geometry.setIndex(new THREE.BufferAttribute(new Uint32Array([0, 1]), 1));
  const line = createCadEdgeLineSegments(THREE, geometry, { depthTest: false, depthBias: TOPOLOGY_LINE_DEPTH_BIAS });
  assert.equal(line.isLineSegments, true);
  assert.equal(line.geometry, geometry);
  assert.equal(line.userData.disposeGeometry, false);
  assert.equal(line.material.vertexColors, true);
  assert.equal(line.material.transparent, true);
  assert.equal(line.material.depthTest, false);
  assert.equal(line.material.polygonOffsetUnits, -5);
  assert.equal(line.material.userData.cadEdgeVertexColors, true);
});

test("record edge materials: uniform overrides, scaled restores, per material kind", () => {
  const plain = new THREE.LineBasicMaterial({ color: "#000000", transparent: true, opacity: 1 });
  const based = new THREE.LineBasicMaterial({ color: "#000000", transparent: true, opacity: 1 });
  based.userData.cadEdgeBaseColor = "#111111";
  based.userData.cadEdgeBaseOpacity = 0.25;
  const classed = createCadEdgeLineSegments(THREE, new THREE.BufferGeometry()).material;
  const record = { edgeMaterials: [plain, based, classed] };

  // Scaled pass (no highlight): plain takes the fallback, based its base style,
  // the vertex-coloured material keeps its classes and scales them.
  syncRecordEdgeMaterials(record, { opacityScale: 0.5, fallbackColor: "#abcdef", fallbackOpacity: 0.84 });
  assert.equal(plain.color.getHexString(), "abcdef");
  assert.equal(plain.opacity, 0.42);
  assert.equal(based.color.getHexString(), "111111");
  assert.equal(based.opacity, 0.125);
  assert.equal(classed.vertexColors, true);
  assert.equal(classed.color.getHexString(), "ffffff");
  assert.equal(classed.opacity, 0.5);
  assert.equal(classed.transparent, true);

  // Uniform pass (highlight): every material takes the colour and opacity.
  syncRecordEdgeMaterials(record, { color: "#ff0000", opacity: 1, fallbackColor: "#abcdef" });
  for (const material of record.edgeMaterials) {
    assert.equal(material.color.getHexString(), "ff0000");
    assert.equal(material.opacity, 1);
  }
  assert.equal(classed.vertexColors, false);

  // An effect edge colour in a scaled pass recolours the classes too.
  syncRecordEdgeMaterials(record, { color: "#00ff00", opacityScale: 0.5, fallbackColor: "#abcdef", fallbackOpacity: 0.84 });
  assert.equal(classed.vertexColors, false);
  assert.equal(classed.color.getHexString(), "00ff00");
  assert.equal(classed.opacity, 0.5);
  assert.equal(based.opacity, 0.125);
  syncRecordEdgeMaterials({ edgeMaterials: null }, { fallbackColor: "#abcdef" });
});

// --- The screen-space line pass: device-pixel width, and the analytic feather.
//
// A configured `thickness` is a FULL width in DEVICE pixels — the unit the
// retired surface-shader pass measured in (its `pixelDistance` was a per-fragment
// derivative) and therefore the unit every stored theme value is authored in.
// Two things decide whether that still holds: the `resolution` a line material is
// given, and what the shader does with it.

function screenSpaceLine(lineWidth = 1.15, options = {}) {
  return createScreenSpaceLineSegments(edgeContext(), [0, 0, 0, 1, 0, 0], {
    color: "#132232",
    opacity: 1,
    lineWidth,
    ...options
  });
}

// A renderer whose CSS viewport and drawing buffer disagree, i.e. any Retina one.
// `getViewport` reports the CSS size (three's own hook reads this one);
// `getCurrentViewport` reports the drawing buffer, which is what a width means.
function retinaRenderer(cssWidth, cssHeight, pixelRatio) {
  return {
    getPixelRatio: () => pixelRatio,
    getViewport: (target) => target.set(0, 0, cssWidth, cssHeight),
    getCurrentViewport: (target) => target.copy({
      x: 0,
      y: 0,
      z: cssWidth * pixelRatio,
      w: cssHeight * pixelRatio
    })
  };
}

// The coverage ramp a line shader paints, read back OUT of the shader source so a
// changed ramp changes the numbers these tests integrate.
function featherRamp(source, halfWidthName) {
  const match = source.match(new RegExp(
    `1\\.0 - smoothstep\\(\\s*max\\(\\s*${halfWidthName} - ([0-9.]+),\\s*0\\.0\\s*\\),\\s*${halfWidthName} \\+ ([0-9.]+),`
  ));
  assert.ok(match, `no analytic feather in the shader (looked for a smoothstep around ${halfWidthName})`);
  return { inner: Number(match[1]), outer: Number(match[2]) };
}

// Ink laid down by that ramp, in device pixels: twice the integral of coverage
// from the centreline out. A smoothstep integrates to its midpoint, so the total
// is `innerEdge + outerEdge` — the same closed form the retired surface shader
// had, which is why a feathered edge weighs what the old one did.
function featherInk(thickness, { inner, outer }) {
  const halfWidth = thickness / 2;
  return Math.max(halfWidth - inner, 0) + (halfWidth + outer);
}

test("screen-space line resolution is the drawing buffer, not the CSS size", () => {
  assert.deepEqual(
    screenSpaceLineDeviceResolution({ getPixelRatio: () => 2 }, 640, 480),
    { width: 1280, height: 960 }
  );
  assert.deepEqual(
    screenSpaceLineDeviceResolution({ getPixelRatio: () => 3 }, 640, 480),
    { width: 1920, height: 1440 }
  );
  assert.deepEqual(
    screenSpaceLineDeviceResolution({ getPixelRatio: () => 1 }, 640, 480),
    { width: 640, height: 480 }
  );
  // No renderer, or a nonsense ratio: the size as given, and never zero.
  assert.deepEqual(screenSpaceLineDeviceResolution(null, 640, 480), { width: 640, height: 480 });
  assert.deepEqual(screenSpaceLineDeviceResolution({ getPixelRatio: () => 0 }, 640, 480), { width: 640, height: 480 });
  // A degenerate size falls back to one CSS pixel, scaled like any other.
  assert.deepEqual(screenSpaceLineDeviceResolution({ getPixelRatio: () => 2 }, 0, 0), { width: 2, height: 2 });
});

test("a screen-space line draws its configured thickness in DEVICE pixels", () => {
  const line = screenSpaceLine(1.15);
  const renderer = retinaRenderer(400, 300, 2);

  // three's LineSegments2 rewrites `resolution` on every draw from the CSS
  // viewport; the CAD hook writes the drawing buffer instead.
  line.material.resolution.set(400, 300);
  line.onBeforeRender(renderer);
  assert.equal(line.material.resolution.x, 800);
  assert.equal(line.material.resolution.y, 600);

  // The shader extrudes `linewidth / resolution.y` into NDC, so the ink a
  // fragment ends up covering is linewidth * drawingBufferHeight / resolution.y.
  const inkCssPixels = (material, { cssHeight, dpr }) => (
    material.linewidth * (cssHeight * dpr) / material.resolution.y / dpr
  );
  assert.equal(inkCssPixels(line.material, { cssHeight: 300, dpr: 2 }), 1.15 / 2);

  // The same thickness at dpr 1: 1.15 device px there too, which is 1.15 CSS px.
  // One authored number, one on-screen weight, every ratio.
  const plainLine = screenSpaceLine(1.15);
  plainLine.onBeforeRender(retinaRenderer(400, 300, 1));
  assert.equal(plainLine.material.resolution.y, 300);
  assert.equal(inkCssPixels(plainLine.material, { cssHeight: 300, dpr: 1 }), 1.15);

  // What three's own hook does, stated in numbers: it writes the CSS viewport,
  // so the buffer's pixel ratio never cancels and the same 1.15 paints 1.15 CSS
  // px on the Retina viewport — twice the authored weight, 3x at dpr 3.
  const cssLine = screenSpaceLine(1.15);
  cssLine.material.resolution.set(400, 300);
  assert.equal(inkCssPixels(cssLine.material, { cssHeight: 300, dpr: 2 }), 1.15);

  // No live viewport (an off-screen pass): keep the synced drawing-buffer size
  // rather than falling back to something in CSS pixels.
  syncScreenSpaceLineMaterialResolution([line.material], 1280, 960);
  line.onBeforeRender({});
  assert.equal(line.material.resolution.x, 1280);
  assert.equal(line.material.resolution.y, 960);
});

test("screen-space lines antialias with an analytic feather, not a hard edge", () => {
  const material = screenSpaceLine(1.15).material;

  // Not alphaToCoverage: three only feathers the round ENDCAPS with it (the
  // `abs(vUv.y) > 1.0` block), never the body a CAD drawing is made of, and it
  // would quantise per-class opacity into sample counts. The feather is analytic.
  assert.equal(material.alphaToCoverage, false);
  assert.equal(material.userData.cadEdgeAnalyticCoverage, true);
  assert.equal(typeof material.onBeforeCompile, "function");

  const shader = { vertexShader: material.vertexShader, fragmentShader: material.fragmentShader };
  material.onBeforeCompile(shader);

  // The quad is widened by the feather on each side so the ramp has room.
  const padding = shader.vertexShader.match(/offset \*= linewidth \+ ([0-9.]+) \* 2\.0;/);
  assert.ok(padding, "the patched vertex shader does not widen the quad");
  assert.equal(Number(padding[1]), CAD_EDGE_FEATHER_PIXELS);

  // And the fragment stage ramps coverage into ALPHA across the ink boundary.
  assert.match(shader.fragmentShader, /alpha \*= 1\.0 - smoothstep\(/);
  const ramp = featherRamp(shader.fragmentShader, "cadEdgeInkHalfWidth");
  assert.equal(ramp.inner, CAD_EDGE_FEATHER_PIXELS);
  assert.equal(ramp.outer, CAD_EDGE_FEATHER_PIXELS);
  assert.ok(Number(padding[1]) >= ramp.outer, "the quad is narrower than the ramp it has to hold");

  // The weight that ramp lays down is the retired surface shader's, to the digit:
  // 1.325 device px for the 1.15 default, and exactly `thickness` once the ink is
  // wider than the feather.
  assert.equal(featherInk(1.15, ramp), 1.325);
  assert.equal(featherInk(3, ramp), 3);
  assert.equal(featherInk(2, ramp), 2);
});

test("the screen-space line feather fails loudly if three's shader moves", () => {
  const material = screenSpaceLine().material;
  assert.throws(
    () => material.onBeforeCompile({ vertexShader: "void main() {}", fragmentShader: "void main() {}" }),
    /has no unique/
  );
});

test("screen-space line materials share one feather callback, so one program", () => {
  const first = screenSpaceLine(1.15).material;
  const second = screenSpaceLine(2).material;
  assert.equal(first.onBeforeCompile, second.onBeforeCompile);
  assert.equal(first.customProgramCacheKey(), second.customProgramCacheKey());
});

test("a CAD edge line keeps blending at full opacity so the feather survives", () => {
  const material = screenSpaceLine(1.15, { opacity: 1 }).material;
  assert.equal(material.opacity, 1);
  assert.equal(material.transparent, true);
  syncLineMaterialOpacity(material, 1);
  assert.equal(material.transparent, true);

  // A material with no analytic coverage still goes opaque at 1, as it should.
  const plain = new THREE.LineBasicMaterial({ opacity: 0.5, transparent: true });
  syncLineMaterialOpacity(plain, 1);
  assert.equal(plain.transparent, false);
});
