import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";

import {
  applyPartVisualState,
  buildModel,
  CAD_DISPLAY_MODE,
  normalizeDisplayMode
} from "./cadScene.js";
import {
  DEFAULT_DISPLAY_EDGE_SETTINGS
} from "./displaySettings.js";
import {
  cloneThemePresetSettings
} from "./themeSettings.js";
import {
  PART_SELECTED_HIGHLIGHT_BLEND,
  partHighlightSurfaceColor
} from "../lib/viewer/partHighlight.js";
import { applyRecordTubeDeformation, normalizeTubeDeformation } from "./tubeDeformation.js";

function sampleMeshData() {
  return {
    vertices: new Float32Array([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0,
      2, 0, 0,
      3, 0, 0,
      2, 1, 0
    ]),
    indices: new Uint32Array([0, 1, 2, 3, 4, 5]),
    normals: new Float32Array([
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1
    ]),
    bounds: {
      min: [0, 0, 0],
      max: [3, 1, 0]
    },
    parts: [
      {
        id: "left",
        vertexOffset: 0,
        vertexCount: 3,
        triangleOffset: 0,
        triangleCount: 1,
        bounds: { min: [0, 0, 0], max: [1, 1, 0] }
      },
      {
        id: "right",
        vertexOffset: 3,
        vertexCount: 3,
        triangleOffset: 1,
        triangleCount: 1,
        bounds: { min: [2, 0, 0], max: [3, 1, 0] }
      }
    ]
  };
}

function nestedAssemblyMeshData() {
  return {
    vertices: new Float32Array([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0,
      2, 0, 0,
      3, 0, 0,
      2, 1, 0,
      10, 0, 0,
      11, 0, 0,
      10, 1, 0
    ]),
    indices: new Uint32Array([0, 1, 2, 3, 4, 5, 6, 7, 8]),
    normals: new Float32Array([
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1
    ]),
    bounds: {
      min: [0, 0, 0],
      max: [11, 1, 0]
    },
    parts: [
      {
        id: "o1.2.1",
        occurrenceId: "o1.2.1",
        vertexOffset: 0,
        vertexCount: 3,
        triangleOffset: 0,
        triangleCount: 1,
        bounds: { min: [0, 0, 0], max: [1, 1, 0] }
      },
      {
        id: "o1.2.2",
        occurrenceId: "o1.2.2",
        vertexOffset: 3,
        vertexCount: 3,
        triangleOffset: 1,
        triangleCount: 1,
        bounds: { min: [2, 0, 0], max: [3, 1, 0] }
      },
      {
        id: "o1.3",
        occurrenceId: "o1.3",
        vertexOffset: 6,
        vertexCount: 3,
        triangleOffset: 2,
        triangleCount: 1,
        bounds: { min: [10, 0, 0], max: [11, 1, 0] }
      }
    ]
  };
}

function createDisplayRecord(partId, {
  baseOpacity = 1
} = {}) {
  const material = new THREE.MeshStandardMaterial({
    color: "#aaaaaa",
    emissive: "#000000",
    transparent: false,
    opacity: 1
  });
  const edgeMaterial = new THREE.LineBasicMaterial({
    color: "#222222",
    transparent: true,
    opacity: 1
  });
  return {
    partId,
    mesh: { visible: true, renderOrder: 2 },
    edges: { visible: true, renderOrder: 3 },
    material,
    edgeMaterials: [edgeMaterial],
    baseOpacity,
    baseColor: new THREE.Color("#aaaaaa"),
    baseEmissiveColor: new THREE.Color("#000000"),
    baseEmissiveIntensity: 0
  };
}

function squareMeshData() {
  return {
    vertices: new Float32Array([
      0, 0, 0,
      1, 0, 0,
      1, 1, 0,
      0, 1, 0
    ]),
    indices: new Uint32Array([0, 1, 2, 0, 2, 3]),
    normals: new Float32Array([
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1
    ]),
    bounds: {
      min: [0, 0, 0],
      max: [1, 1, 0]
    },
    parts: []
  };
}

function edgeSegmentCount(record) {
  return Math.floor((record?.edges?.geometry?.getAttribute("position")?.count || 0) / 2);
}

test("applyPartVisualState keeps dimmed context from depth-occluding highlights", () => {
  const dimmed = createDisplayRecord("dimmed");
  const selected = createDisplayRecord("selected");

  applyPartVisualState(THREE, [dimmed, selected], {
    baseTheme: {
      edge: "#111111",
      edgeOpacity: 0.5
    },
    edgeSettings: {
      opacity: 0.5
    },
    hiddenPartIds: [],
    hoveredPartId: "",
    focusedPartId: ["selected"],
    selectedPartIds: ["selected"],
    showEdges: true
  });

  assert.equal(dimmed.material.transparent, true);
  assert.equal(dimmed.material.depthWrite, false);
  assert.equal(dimmed.mesh.renderOrder, 2);
  assert.equal(dimmed.edges.renderOrder, 3);
  assert.equal(selected.material.transparent, true);
  assert.equal(selected.material.depthWrite, true);
  assert.equal(selected.mesh.renderOrder, 23);
  assert.equal(selected.edges.renderOrder, 26);

  applyPartVisualState(THREE, [selected], {
    baseTheme: {},
    edgeSettings: {},
    hiddenPartIds: [],
    hoveredPartId: "",
    focusedPartId: [],
    selectedPartIds: [],
    showEdges: true
  });

  assert.equal(selected.material.transparent, false);
  assert.equal(selected.material.depthWrite, true);
  assert.equal(selected.mesh.renderOrder, 2);
  assert.equal(selected.edges.renderOrder, 3);
});

test("applyPartVisualState highlights and ghosts identically to the viewer path", () => {
  const selected = createDisplayRecord("selected");
  const children = [];
  selected.mesh = { visible: true, renderOrder: 2, add: (child) => children.push(child) };
  selected.geometry = new THREE.BufferGeometry();

  applyPartVisualState(THREE, [selected], {
    baseTheme: {},
    edgeSettings: {},
    hiddenPartIds: [],
    hoveredPartId: "",
    focusedPartId: [],
    selectedPartIds: ["selected"],
    showEdges: true
  });

  // Headless renders must use the same blended surface highlight as the viewer
  // so snapshots and docs GIFs match what the CAD Viewer shows.
  const expected = partHighlightSurfaceColor(
    THREE,
    new THREE.Color("#aaaaaa"),
    new THREE.Color("#4f9dff"),
    PART_SELECTED_HIGHLIGHT_BLEND
  );
  assert.equal(selected.material.color.getHexString(), expected.getHexString());
  assert.equal(selected.material.emissive.getHexString(), new THREE.Color("#4f9dff").getHexString());
  assert.ok(selected.ghostMesh, "headless selection attaches the occlusion ghost");
  assert.equal(selected.ghostMesh.visible, true);
  assert.equal(selected.ghostMaterial.depthFunc, THREE.GreaterDepth);
});

test("buildModel renders solid part records and updates theme without rebuilding geometry", () => {
  const theme = cloneThemePresetSettings("workbench-light");
  const scene = buildModel(THREE, sampleMeshData(), {
    theme,
    renderPartsIndividually: true
  });
  const firstMesh = scene.displayRecords[0].mesh;
  const firstGeometry = firstMesh.geometry;

  assert.equal(scene.displayRecords.length, 2);
  assert.equal(scene.displayRecords[0].partId, "left");
  assert.equal(scene.displayRecords[0].edges.visible, true);
  assert.equal(scene.displayRecords[0].mesh.castShadow, true);
  assert.equal(scene.displayRecords[0].mesh.receiveShadow, false);

  scene.update({
    theme: {
      ...theme,
      materials: {
        ...theme.materials,
        defaultColor: "#ff0000",
        fillColors: ["#ff0000"]
      }
    }
  });

  assert.equal(scene.displayRecords[0].mesh, firstMesh);
  assert.equal(scene.displayRecords[0].mesh.geometry, firstGeometry);
  assert.equal(scene.displayRecords[0].material.color.getHexString(), "ff0000");
  scene.dispose();
});

test("buildModel keeps source-mesh color buffers immutable across material refreshes", () => {
  const sourceColors = new Float32Array([
    0.2, 0.4, 0.6,
    0.8, 0.45, 0.2,
    0.55, 0.3, 0.75
  ]);
  const originalColors = Array.from(sourceColors);
  const sourceMesh = {
    vertices: new Float32Array([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0
    ]),
    indices: new Uint32Array([0, 1, 2]),
    normals: new Float32Array([
      0, 0, 1,
      0, 0, 1,
      0, 0, 1
    ]),
    colors: sourceColors
  };
  const meshData = {
    vertices: new Float32Array(0),
    indices: new Uint32Array(0),
    normals: new Float32Array(0),
    bounds: { min: [0, 0, 0], max: [1, 1, 0] },
    parts: [
      {
        id: "camera-source",
        sourceMeshKey: "camera-source",
        sourceMesh,
        hasSourceColors: true,
        vertexCount: 3,
        triangleCount: 1,
        bounds: { min: [0, 0, 0], max: [1, 1, 0] }
      }
    ]
  };
  const theme = cloneThemePresetSettings("workbench-light");
  const scene = buildModel(THREE, meshData, {
    theme,
    renderPartsIndividually: true
  });
  const record = scene.displayRecords[0];
  const colorAttribute = record.geometry.getAttribute("color");

  assert.notEqual(record.rawColors, sourceColors);
  assert.notEqual(colorAttribute.array, sourceColors);
  assert.deepEqual(Array.from(sourceColors), originalColors);

  scene.update({
    theme: {
      ...theme,
      materials: {
        ...theme.materials,
        brightness: 0.72,
        saturation: 1.8
      }
    }
  });

  assert.deepEqual(Array.from(sourceColors), originalColors);
  assert.deepEqual(Array.from(record.rawColors), originalColors);
  scene.dispose();
});

test("buildModel selection can focus and hide subassembly occurrence descendants", () => {
  const focused = buildModel(THREE, nestedAssemblyMeshData(), {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: true,
    selection: {
      focus: ["#o1.2"]
    }
  });

  assert.deepEqual(focused.displayRecords.map((record) => record.partId), ["o1.2.1", "o1.2.2"]);
  assert.deepEqual(focused.bounds, {
    min: [0, 0, 0],
    max: [3, 1, 0]
  });
  focused.dispose();

  const hidden = buildModel(THREE, nestedAssemblyMeshData(), {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: true,
    selection: {
      hide: ["o1.2"]
    }
  });

  assert.deepEqual(hidden.displayRecords.map((record) => record.partId), ["o1.3"]);
  assert.deepEqual(hidden.bounds, {
    min: [10, 0, 0],
    max: [11, 1, 0]
  });
  hidden.dispose();
});

// A surf component: indexed triangles plus CAD edge segments grouped by class.
function surfComponentMeshData() {
  return {
    vertices: new Float32Array([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0]),
    indices: new Uint32Array([0, 1, 2, 0, 2, 3]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]),
    // Three polylines: a 4-point feature outline, a 2-point tangent edge and a
    // 2-point degenerate edge (points 0-3, 4-5, 6-7).
    cadEdgePositions: new Float32Array([
      0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0,
      0, 1, 0, 0, 0, 0,
      0, 0, 0, 1, 1, 0
    ]),
    cadEdgeIndices: new Uint32Array([0, 1, 1, 2, 2, 3, 4, 5, 6, 7]),
    cadEdgeClassRanges: [
      { classId: "feature", pointStart: 0, pointCount: 4, segmentStart: 0, segmentCount: 3 },
      { classId: "tangent", pointStart: 4, pointCount: 2, segmentStart: 3, segmentCount: 1 },
      { classId: "degenerate", pointStart: 6, pointCount: 2, segmentStart: 4, segmentCount: 1 }
    ],
    bounds: { min: [0, 0, 0], max: [1, 1, 0] },
    parts: [{ id: "surf:0", vertexOffset: 0, vertexCount: 4, triangleOffset: 0, triangleCount: 2, bounds: { min: [0, 0, 0], max: [1, 1, 0] } }]
  };
}

function edgeColorAt(record, point) {
  const color = record.edges.geometry.getAttribute("color");
  return [0, 1, 2, 3].map((component) => color.array[point * 4 + component] / 65535);
}

function linearRgb(hex) {
  const color = new THREE.Color(hex);
  return [color.r, color.g, color.b];
}

function assertClose(actual, expected, message, epsilon = 1e-3) {
  const actualList = Array.isArray(actual) ? actual : [actual];
  const expectedList = Array.isArray(expected) ? expected : [expected];
  assert.equal(actualList.length, expectedList.length, message);
  for (let index = 0; index < actualList.length; index += 1) {
    assert.ok(Math.abs(actualList[index] - expectedList[index]) < epsilon, `${message}: ${actualList} vs ${expectedList}`);
  }
}

test("buildModel draws a surf component's CAD edges as ONE instanced screen-space draw with per-class colour, opacity and thickness", () => {
  const scene = buildModel(THREE, surfComponentMeshData(), {
    theme: cloneThemePresetSettings("workbench-light"),
    displayMode: CAD_DISPLAY_MODE.SOLID,
    renderPartsIndividually: true,
    edgeRendering: { mode: "screen-space", LineSegments2, LineSegmentsGeometry, LineMaterial }
  });
  const record = scene.displayRecords[0];
  assert.equal(record.edges, null, "no per-occurrence line object");
  const { set, slot } = record.edgeInstance;

  assert.equal(scene.edgesGroup.children.length, 1);
  assert.equal(scene.edgesGroup.children[0], set.object);
  assert.equal(set.object.isMesh, true);
  assert.equal(set.object.geometry.isInstancedBufferGeometry, true);
  // Degenerate edges default to zero thickness and are not drawn: 3 + 1 segments x 1 occurrence.
  assert.equal(set.segments.segmentCount, 4);
  assert.equal(set.object.geometry.instanceCount, 4);
  const segmentData = set.segments.texture.image.data;
  assert.deepEqual(Array.from(segmentData.subarray(0, 8)), [0, 0, 0, 0, 1, 0, 0, 0], "segment 0: start + feature class, end");
  assert.deepEqual(Array.from(segmentData.subarray(24, 32)), [0, 1, 0, 1, 0, 0, 0, 0], "segment 3: the tangent edge (class 1)");
  const classColor = set.uniforms.cadClassColor.value.elements;
  assertClose(classColor.slice(0, 3), linearRgb("#132232"), "feature class colour (linear)");
  assert.equal(classColor[3], 1, "feature opacity");
  assertClose(classColor[7], 0.5, "tangent opacity");
  // Class widths in pixels for the classes this component carries (no seams here); degenerate is off.
  assert.deepEqual(set.uniforms.cadClassWidth.value.toArray(), [1.15, 1.15, 0, 0], "per-class thickness in pixels");
  assert.equal(set.material.glslVersion, THREE.GLSL3);
  assert.equal(set.material.transparent, true);
  assert.equal(set.material.depthTest, true);
  assert.equal(set.material.depthWrite, false);
  assert.equal(set.material.polygonOffset, true, "CAD edge lines carry their own depth bias");
  assert.equal(set.material.clipping, false, "clip planes toggle the shader's clipping like every other material (none active)");
  assert.deepEqual(record.edgeMaterials, []);
  assert.equal(record.material.polygonOffset, true, "the surface is pushed back behind its edge lines");
  assert.equal(record.material.polygonOffsetFactor, 1);
  assert.equal(record.geometry.getAttribute("position").count, 4, "indexed geometry stays indexed");
  assert.equal(scene.runtime.screenSpaceLineMaterials.size, 2, "main and highlight pass resync their resolution");
  assert.equal(set.object.renderOrder, 3);
  assert.equal(set.highlightObject.renderOrder, 26);
  assert.equal(set.highlightObject.visible, false);
  assert.deepEqual(set.readSlot(slot), { matrix: new THREE.Matrix4().toArray(), color: null, opacity: 1, visible: true, highlighted: false });

  // Selection recolours every class to edges.highlightColor at full opacity and
  // moves the occurrence to the highlight pass; deselection restores the class styles.
  scene.update({ selection: { selectedPartIds: ["surf:0"] } });
  let state = set.readSlot(slot);
  assertClose(state.color, linearRgb("#8dc5ff"), "selected edge colour");
  assert.equal(state.opacity, 1);
  assert.equal(state.highlighted, true);
  assert.equal(set.highlightObject.visible, true);
  scene.update({ selection: { selectedPartIds: [] } });
  state = set.readSlot(slot);
  assert.equal(state.color, null);
  assert.equal(state.opacity, 1);
  assert.equal(state.highlighted, false);
  assert.equal(set.highlightObject.visible, false);
  // Focus dims the others to the surface's dimmed opacity in the base edge colour; hide makes them invisible.
  scene.update({ selection: { focusedPartId: ["nothing"] } });
  state = set.readSlot(slot);
  assertClose(state.opacity, 0.035, "dimmed edge opacity");
  assert.ok(state.color, "dimmed edges lose their class colours for the base edge colour");
  scene.update({ selection: { focusedPartId: [], showEdges: false } });
  assert.equal(set.readSlot(slot).visible, false);
  scene.update({ selection: { showEdges: true } });
  assert.equal(set.readSlot(slot).visible, true);

  // Show-through modes drop the depth test on the edge draw.
  const transparent = buildModel(THREE, surfComponentMeshData(), {
    theme: cloneThemePresetSettings("workbench-light"),
    displayMode: CAD_DISPLAY_MODE.TRANSPARENT,
    renderPartsIndividually: true
  });
  assert.equal(transparent.displayRecords[0].edgeInstance.set.material.depthTest, false);
  assert.equal(transparent.displayRecords[0].material.polygonOffset, true);
  transparent.dispose();

  // Rendered mode draws no linework at all; wireframe draws the mesh wires instead.
  const rendered = buildModel(THREE, surfComponentMeshData(), { displayMode: CAD_DISPLAY_MODE.RENDERED, renderPartsIndividually: true });
  assert.equal(rendered.displayRecords[0].edges, null);
  assert.equal(rendered.displayRecords[0].edgeInstance, null);
  rendered.dispose();
  const wire = buildModel(THREE, surfComponentMeshData(), { displayMode: CAD_DISPLAY_MODE.WIREFRAME, renderPartsIndividually: true });
  assert.equal(wire.displayRecords[0].edges.geometry.type, "WireframeGeometry");
  assert.equal(wire.displayRecords[0].edgeInstance, null);
  wire.dispose();
  scene.dispose();
  assert.equal(set.disposed, true, "disposing the scene disposes its instance sets");
});

// GPU buffers a geometry owns: its index plus one per distinct attribute array.
function geometryBuffers(geometry) {
  const buffers = new Set();
  if (geometry.index) buffers.add(geometry.index);
  for (const attribute of Object.values(geometry.attributes)) {
    buffers.add(attribute.isInterleavedBufferAttribute ? attribute.data : attribute);
  }
  return buffers;
}

function composedPackage(sourceMesh, count) {
  return {
    vertices: new Float32Array(0), indices: new Uint32Array(0),
    bounds: { min: [0, 0, 0], max: [count * 10 + 1, 1, 0] },
    partTransformsBaked: false,
    parts: Array.from({ length: count }, (_, index) => ({
      id: `o${index}`, occurrenceId: `o${index}`, sourceMeshKey: "cid:flat", sourceMesh, vertexCount: 4, triangleCount: 2,
      transform: [1, 0, 0, index * 10, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
      bounds: { min: [index * 10, 0, 0], max: [index * 10 + 1, 1, 0] }
    }))
  };
}

test("a component's occurrences share one surface geometry and one instanced edge draw: 5 buffers + 2 textures, draw calls = occurrences + 1", () => {
  const sourceMesh = surfComponentMeshData();
  const first = buildModel(THREE, composedPackage(sourceMesh, 4), { renderPartsIndividually: true });
  const geometries = new Set();
  const buffers = new Set();
  let drawables = 0;
  first.root.traverse((object) => {
    if (!object.geometry || object.userData.cadEdgeInstancesHighlight) return;
    drawables += 1;
    geometries.add(object.geometry);
    for (const buffer of geometryBuffers(object.geometry)) buffers.add(buffer);
  });
  assert.equal(drawables, 5, "one mesh per occurrence and one edge draw for the component");
  assert.equal(geometries.size, 2, "one surface geometry and one edge quad for the component");
  assert.equal(buffers.size, 5, "position, normal, index + quad position, quad index");
  const [a, b] = first.displayRecords;
  assert.equal(a.edgeInstance.set, b.edgeInstance.set, "occurrences are slots of one set");
  assert.notEqual(a.edgeInstance.slot, b.edgeInstance.slot);
  assert.equal(a.edgeInstance.set.object.geometry.instanceCount, 4 * 4, "segments x occurrences");
  assert.equal(b.edgeInstance.set.readSlot(b.edgeInstance.slot).matrix[12], 10);
  assert.deepEqual(b.edgeInstance.set.readSlot(b.edgeInstance.slot).matrix, Array.from(b.mesh.matrix.elements), "edge instances ride the occurrence matrix");
  const set = a.edgeInstance.set;
  const textures = new Set([set.segments.texture, set.instanceTexture]);
  assert.equal(textures.size, 2, "one segment texture and one instance texture per component");

  // A progressive publish re-composes the package: the next model must find
  // the component's geometry AND segment texture in the cache instead of uploading them again.
  first.dispose();
  const second = buildModel(THREE, composedPackage(sourceMesh, 5), { renderPartsIndividually: true });
  assert.equal(second.displayRecords.length, 5);
  assert.equal(second.displayRecords[0].geometry, a.geometry, "surface geometry reused");
  assert.equal(second.displayRecords[4].edgeInstance.set.segments, set.segments, "segment texture reused");
  second.dispose();
});

// A component large enough for the budget to mean something: a 60x60 vertex
// grid (6,962 triangles) outlined by its four boundary polylines (236 segments).
function gridComponent(side = 60) {
  const vertices = new Float32Array(side * side * 3);
  const normals = new Float32Array(side * side * 3);
  for (let y = 0; y < side; y += 1) {
    for (let x = 0; x < side; x += 1) {
      const index = (y * side + x) * 3;
      vertices[index] = x;
      vertices[index + 1] = y;
      normals[index + 2] = 1;
    }
  }
  const indices = new Uint32Array((side - 1) * (side - 1) * 6);
  let cursor = 0;
  for (let y = 0; y + 1 < side; y += 1) {
    for (let x = 0; x + 1 < side; x += 1) {
      const a = y * side + x;
      indices.set([a, a + 1, a + side, a + 1, a + side + 1, a + side], cursor);
      cursor += 6;
    }
  }
  const boundary = [];
  for (let x = 0; x < side; x += 1) boundary.push(x);
  for (let y = 1; y < side; y += 1) boundary.push(y * side + side - 1);
  for (let x = side - 2; x >= 0; x -= 1) boundary.push((side - 1) * side + x);
  for (let y = side - 2; y >= 1; y -= 1) boundary.push(y * side);
  const cadEdgePositions = new Float32Array(boundary.length * 3);
  boundary.forEach((vertex, point) => cadEdgePositions.set(vertices.subarray(vertex * 3, vertex * 3 + 3), point * 3));
  const cadEdgeIndices = new Uint32Array(boundary.length * 2);
  for (let point = 0; point < boundary.length; point += 1) {
    cadEdgeIndices[point * 2] = point;
    cadEdgeIndices[point * 2 + 1] = (point + 1) % boundary.length;
  }
  return {
    vertices, normals, indices, cadEdgePositions, cadEdgeIndices,
    cadEdgeClassRanges: [{ classId: "feature", pointStart: 0, pointCount: boundary.length, segmentStart: 0, segmentCount: boundary.length }],
    bounds: { min: [0, 0, 0], max: [side - 1, side - 1, 0] },
    parts: [{ id: "grid", vertexCount: side * side, triangleCount: (side - 1) * (side - 1) * 2, bounds: { min: [0, 0, 0], max: [side - 1, side - 1, 0] } }]
  };
}

test("instanced edge GPU budget: edge bytes stay under 10% of surface bytes and a component holds 4 GPU objects for its edges", () => {
  const component = gridComponent();
  const meshData = {
    vertices: new Float32Array(0), indices: new Uint32Array(0), bounds: component.bounds, partTransformsBaked: false,
    parts: Array.from({ length: 40 }, (_, index) => ({
      id: `g${index}`, occurrenceId: `g${index}`, sourceMeshKey: "grid:flat", sourceMesh: component,
      vertexCount: 3600, triangleCount: 6962, transform: [1, 0, 0, index * 100, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], bounds: component.bounds
    }))
  };
  const scene = buildModel(THREE, meshData, { renderPartsIndividually: true });
  const record = scene.displayRecords[0];
  const set = record.edgeInstance.set;
  const surfaceBytes = [...geometryBuffers(record.geometry)].reduce((sum, buffer) => sum + buffer.array.byteLength, 0);
  const edgeBytes = set.segments.byteLength + set.instanceByteLength
    + [...geometryBuffers(set.geometry)].reduce((sum, buffer) => sum + buffer.array.byteLength, 0);
  assert.equal(set.segments.segmentCount, 236);
  assert.equal(set.slotCount, 40);
  assert.equal(set.geometry.instanceCount, 236 * 40);
  assert.ok(edgeBytes / surfaceBytes <= 0.10, `edge bytes ${edgeBytes} exceed 10% of surface bytes ${surfaceBytes}`);
  assert.equal(geometryBuffers(set.geometry).size, 2, "quad position + index");
  assert.equal(new Set([set.segments.texture, set.instanceTexture]).size, 2, "segment + instance texture");
  assert.equal(scene.edgesGroup.children.length, 1, "one edge draw object for 40 occurrences");
  // Slots are recycled: a departed occurrence's slot goes to the next arrival, the draw shrinks with a trailing release.
  scene.update({ source: { ...meshData, parts: meshData.parts.slice(0, 39) } });
  assert.equal(set.slotCount, 39);
  assert.equal(set.geometry.instanceCount, 236 * 39);
  scene.update({ source: { ...meshData, parts: [...meshData.parts.slice(1, 39), meshData.parts[0]] } });
  assert.equal(set.slotCount, 39, "o0 re-enters in the slot the trailing release freed or o0's own");
  assert.equal(set.liveCount, 39);
  scene.dispose();
});

test("a deformed tube leaves the instanced edge draw for a private, bendable line object; the component buffers stay shared", () => {
  const sourceMesh = surfComponentMeshData();
  const savedPositions = sourceMesh.vertices.slice();
  const savedNormals = sourceMesh.normals.slice();
  const meshData = {
    vertices: new Float32Array(0), indices: new Uint32Array(0),
    bounds: sourceMesh.bounds,
    parts: [{ id: "tube", sourceMeshKey: "tube", sourceMesh, vertexCount: 4, triangleCount: 2, bounds: sourceMesh.bounds }]
  };
  const scene = buildModel(THREE, meshData, { renderPartsIndividually: true });
  const record = scene.displayRecords[0];
  assert.equal(record.geometry.getAttribute("normal").array, sourceMesh.normals);
  assert.equal(record.geometry.getAttribute("position").array, sourceMesh.vertices);
  assert.equal(record.geometry.index.array, sourceMesh.indices);
  const set = record.edgeInstance.set;
  assert.equal(set.liveCount, 1);
  const savedEdgePositions = sourceMesh.cadEdgePositions.slice();
  record.gpuTubeDeformationAllowed = false;
  const rest = { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [3, 0, 0] }] };
  const path = { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 2], end: [0, 3, 2] }] };
  applyRecordTubeDeformation(THREE, record, normalizeTubeDeformation({ rest, path, maxSegmentLength: 1000 }));
  assert.notEqual(record.geometry.getAttribute("normal").array, sourceMesh.normals);
  assert.notDeepEqual(record.geometry.getAttribute("position").array, savedPositions);
  assert.deepEqual(sourceMesh.vertices, savedPositions);
  assert.deepEqual(sourceMesh.normals, savedNormals);
  // The record left the instanced draw and bends a private, flattened GL_LINES
  // copy that keeps the class colours; the shared points stay put.
  assert.equal(record.edgeInstance, null);
  assert.equal(set.liveCount, 0);
  assert.equal(set.geometry.instanceCount, 0);
  assert.equal(record.edges.isLineSegments, true);
  assert.equal(record.edgeMaterials.length, 1);
  assert.equal(record.edgeMaterials[0].vertexColors, true);
  const bentEdge = record.edges.geometry.getAttribute("position");
  assert.notEqual(bentEdge.array, sourceMesh.cadEdgePositions);
  assert.equal(record.edges.geometry.index, null);
  assert.equal(record.edges.geometry.getAttribute("color").count, bentEdge.count);
  assert.deepEqual(sourceMesh.cadEdgePositions, savedEdgePositions);
  assert.deepEqual(record.edges.matrix.elements, record.mesh.matrix.elements);
  scene.dispose();
});

test("tube deformation writes indexed component geometry per shared vertex on the CPU and GPU paths", () => {
  // Four shared vertices, two triangles: the indexed surf shape.
  const component = () => ({
    vertices: new Float32Array([0, 0, 1, 5, 0, 1, 10, 0, 1, 5, 1, 0]),
    indices: new Uint32Array([0, 1, 3, 1, 2, 3]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 0]),
    bounds: { min: [0, 0, 0], max: [10, 1, 1] }
  });
  const meshDataFor = (sourceMesh) => ({
    vertices: new Float32Array(0), indices: new Uint32Array(0),
    bounds: sourceMesh.bounds,
    parts: [{ id: "tube", sourceMeshKey: "tube", sourceMesh, vertexCount: 4, triangleCount: 2, bounds: sourceMesh.bounds }]
  });
  const rest = { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [10, 0, 0] }] };
  const path = { normal: [0, 0, 1], segments: [{ kind: "arc", center: [0, 5, 0], axis: [0, 0, 1], start: [0, 0, 0], sweepDeg: 90 }] };
  const spec = normalizeTubeDeformation({ rest, path, maxSegmentLength: 1000 });

  const cpuScene = buildModel(THREE, meshDataFor(component()), { renderPartsIndividually: true });
  const cpu = cpuScene.displayRecords[0];
  cpu.gpuTubeDeformationAllowed = false;
  applyRecordTubeDeformation(THREE, cpu, spec);
  assert.equal(cpu.geometry.attributes.position.count, 4, "CPU path writes one position per shared vertex");
  assert.equal(cpu.geometry.index.count, 6, "index buffer keeps the two triangles");
  assert.equal(cpu.tubeDeformationState.mapping.indices.length, 4);

  const gpuScene = buildModel(THREE, meshDataFor(component()), { renderPartsIndividually: true });
  const gpu = gpuScene.displayRecords[0];
  gpu.mesh.updateMatrixWorld();
  applyRecordTubeDeformation(THREE, gpu, spec);
  assert.ok(gpu.tubeGpuState?.active, "GPU transport engaged");
  assert.equal(gpu.geometry.attributes.cadTubeMappingIndex.count, 4, "GPU mapping attribute is per vertex");
  // Materialized (pick) positions on the GPU record equal the CPU path's.
  gpu.mesh.userData.cadBeforeRaycast(new THREE.Raycaster(new THREE.Vector3(3.5, 1.5, 10), new THREE.Vector3(0, 0, -1)));
  assert.deepEqual(
    Array.from(gpu.geometry.attributes.position.array),
    Array.from(cpu.geometry.attributes.position.array),
    "CPU and GPU pick positions agree"
  );
  cpuScene.dispose();
  gpuScene.dispose();
});

test("buildModel rebuilds the instanced edge draw when edge class settings change", () => {
  const theme = cloneThemePresetSettings("workbench-light");
  const scene = buildModel(THREE, surfComponentMeshData(), {
    theme,
    displayMode: CAD_DISPLAY_MODE.SOLID,
    renderPartsIndividually: true
  });
  const originalSet = scene.displayRecords[0].edgeInstance.set;
  const originalSegments = originalSet.segments;

  scene.update({
    displayMode: CAD_DISPLAY_MODE.SOLID,
    theme: {
      ...theme,
      edges: {
        ...DEFAULT_DISPLAY_EDGE_SETTINGS,
        color: "#0055ff",
        classes: {
          ...DEFAULT_DISPLAY_EDGE_SETTINGS.classes,
          tangent: {
            ...DEFAULT_DISPLAY_EDGE_SETTINGS.classes.tangent,
            thickness: 0
          },
          feature: {
            ...DEFAULT_DISPLAY_EDGE_SETTINGS.classes.feature,
            thickness: 2.5
          }
        }
      }
    }
  });

  const set = scene.displayRecords[0].edgeInstance.set;
  assert.notEqual(set, originalSet);
  assert.equal(originalSet.disposed, true, "the previous style's set is disposed with its records");
  assert.notEqual(set.segments, originalSegments, "a new class style is a new segment texture");
  assert.equal(set.segments.segmentCount, 3, "tangent switched off: only the three feature segments remain");
  assert.equal(set.uniforms.cadClassWidth.value.x, 2.5, "feature thickness follows the class setting");
  assert.equal(scene.edgesGroup.children.length, 1);
  scene.update({ theme });
  assert.equal(scene.displayRecords[0].edgeInstance.set.segments, originalSegments, "the previous style's segment texture is cached");
  scene.dispose();
});

test("buildModel reuses cached geometry for posed wrappers with the same geometry source", () => {
  const geometrySource = sampleMeshData();
  const posedMeshData = {
    ...geometrySource,
    geometrySource,
    parts: geometrySource.parts.map((part) => ({
      ...part,
      transform: [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1
      ]
    }))
  };
  const movedMeshData = {
    ...geometrySource,
    geometrySource,
    parts: geometrySource.parts.map((part, index) => ({
      ...part,
      bounds: {
        min: [part.bounds.min[0] + index, part.bounds.min[1], part.bounds.min[2]],
        max: [part.bounds.max[0] + index, part.bounds.max[1], part.bounds.max[2]]
      },
      transform: [
        1, 0, 0, index,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1
      ]
    }))
  };
  const scene = buildModel(THREE, posedMeshData, {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: true
  });
  const firstGeometry = scene.displayRecords[0].mesh.geometry;
  const movedScene = buildModel(THREE, movedMeshData, {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: true
  });

  assert.equal(movedScene.displayRecords[0].mesh.geometry, firstGeometry);
  scene.dispose();
  movedScene.dispose();
});

test("buildModel wireframe mode keeps a translucent surface and wire edges", () => {
  const theme = cloneThemePresetSettings("workbench-light");
  const scene = buildModel(THREE, sampleMeshData(), {
    theme,
    displayMode: CAD_DISPLAY_MODE.WIREFRAME,
    renderPartsIndividually: true
  });

  assert.equal(normalizeDisplayMode("wireframe"), CAD_DISPLAY_MODE.WIREFRAME);
  assert.equal(scene.displayRecords.length, 2);
  assert.equal(scene.displayRecords[0].material.type, "MeshBasicMaterial");
  assert.equal(scene.displayRecords[0].material.opacity, 0.035);
  assert.equal(scene.displayRecords[0].edges.geometry.type, "WireframeGeometry");
  scene.dispose();
});

test("buildModel display modes control edges, transparency, and flat surfaces", () => {
  const theme = cloneThemePresetSettings("workbench-light");
  const renderedScene = buildModel(THREE, sampleMeshData(), {
    theme,
    displayMode: CAD_DISPLAY_MODE.RENDERED,
    renderPartsIndividually: true
  });
  assert.equal(renderedScene.displayRecords[0].edges, null);
  assert.equal(renderedScene.displayRecords[0].material.opacity, 1);

  const transparentScene = buildModel(THREE, sampleMeshData(), {
    theme,
    displayMode: CAD_DISPLAY_MODE.TRANSPARENT,
    renderPartsIndividually: true
  });
  assert.equal(transparentScene.displayRecords[0].material.opacity, 0.22);
  assert.equal(transparentScene.displayRecords[0].material.transparent, true);
  assert.equal(transparentScene.displayRecords[0].material.depthWrite, false);
  assert.equal(transparentScene.displayRecords[0].edgeMaterials[0].depthTest, false);

  const hiddenEdgeScene = buildModel(THREE, sampleMeshData(), {
    theme,
    displayMode: CAD_DISPLAY_MODE.HIDDEN_EDGES,
    renderPartsIndividually: true
  });
  assert.equal(hiddenEdgeScene.displayRecords[0].material.opacity, 1);
  assert.equal(hiddenEdgeScene.displayRecords[0].edgeMaterials[0].depthTest, false);

  const unshadedScene = buildModel(THREE, sampleMeshData(), {
    theme,
    displayMode: CAD_DISPLAY_MODE.UNSHADED,
    renderPartsIndividually: true
  });
  assert.equal(unshadedScene.displayRecords[0].material.type, "MeshBasicMaterial");
  assert.equal(unshadedScene.displayRecords[0].edges, null);

  renderedScene.dispose();
  transparentScene.dispose();
  hiddenEdgeScene.dispose();
  unshadedScene.dispose();
});

test("buildModel applies source part opacity from GLB material metadata", () => {
  const meshData = sampleMeshData();
  meshData.parts = meshData.parts.map((part, index) => index === 0
    ? { ...part, color: "#ff0000", opacity: 0.2, hasSourceColors: true }
    : part
  );
  const scene = buildModel(THREE, meshData, {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: true
  });

  const left = scene.displayRecords.find((record) => record.partId === "left");

  assert.equal(left.baseOpacity, 0.2);
  assert.equal(left.material.opacity, 0.2);
  assert.equal(left.material.transparent, true);
  assert.equal(left.material.depthWrite, false);
  scene.dispose();
});

test("buildModel uses part records when only source opacity differs", () => {
  const meshData = sampleMeshData();
  meshData.sourceColor = "#ff0000";
  meshData.has_source_colors = true;
  meshData.parts = meshData.parts.map((part) => ({
    ...part,
    color: "#ff0000",
    opacity: 0.2,
    hasSourceColors: true
  }));
  const scene = buildModel(THREE, meshData, {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: false
  });

  assert.equal(scene.displayRecords.length, 2);
  for (const record of scene.displayRecords) {
    assert.equal(record.baseOpacity, 0.2);
    assert.equal(record.material.opacity, 0.2);
    assert.equal(record.material.transparent, true);
    assert.equal(record.material.depthWrite, false);
  }
  scene.dispose();
});

test("buildModel ignores deprecated mesh edge detail and keeps wireframe all-edge mode", () => {
  const baseTheme = cloneThemePresetSettings("workbench-light");
  const deprecatedDetailScene = buildModel(THREE, squareMeshData(), {
    theme: {
      ...baseTheme,
      edges: {
        ...DEFAULT_DISPLAY_EDGE_SETTINGS,
        topologyFilter: "all"
      }
    },
    displayMode: CAD_DISPLAY_MODE.SOLID
  });
  const wireScene = buildModel(THREE, squareMeshData(), {
    theme: baseTheme,
    displayMode: CAD_DISPLAY_MODE.WIREFRAME
  });

  assert.equal(edgeSegmentCount(deprecatedDetailScene.displayRecords[0]), 4);
  assert.notEqual(deprecatedDetailScene.displayRecords[0].edges.geometry.type, "WireframeGeometry");
  assert.equal(edgeSegmentCount(wireScene.displayRecords[0]), 5);
  assert.equal(wireScene.displayRecords[0].edges.geometry.type, "WireframeGeometry");
  deprecatedDetailScene.dispose();
  wireScene.dispose();
});

test("buildModel creates screen-space edges from declarative edge rendering options", () => {
  const scene = buildModel(THREE, squareMeshData(), {
    theme: cloneThemePresetSettings("workbench-light"),
    displayMode: CAD_DISPLAY_MODE.SOLID,
    edgeRendering: {
      mode: "screen-space",
      LineSegments2,
      LineSegmentsGeometry,
      LineMaterial
    }
  });

  assert.equal(scene.runtime.edgeRendering.mode, "screen-space");
  assert.equal(scene.displayRecords[0].edges instanceof LineSegments2, true);
  assert.equal(scene.runtime.screenSpaceLineMaterials.size, 1);

  scene.dispose();
  assert.equal(scene.runtime.screenSpaceLineMaterials.size, 0);
});

test("buildModel can render silhouette contours without derived mesh edges", () => {
  const theme = cloneThemePresetSettings("workbench-light");
  const scene = buildModel(THREE, sampleMeshData(), {
    theme: {
      ...theme,
      edges: {
        ...DEFAULT_DISPLAY_EDGE_SETTINGS,
        enabled: false,
        silhouette: true,
        silhouetteScale: 0.004
      }
    },
    displayMode: CAD_DISPLAY_MODE.RENDERED,
    silhouette: true,
    renderPartsIndividually: true
  });

  assert.equal(scene.displayRecords.length, 2);
  assert.equal(scene.displayRecords[0].edges, null);
  assert.equal(scene.displayRecords[0].silhouette?.isMesh, true);
  scene.dispose();
});

test("buildModel applies selection, clipping, and STEP parameter effects", () => {
  const scene = buildModel(THREE, sampleMeshData(), {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: true,
    selection: {
      selectedPartIds: ["left"],
      hiddenPartIds: ["right"]
    },
    clip: {
      enabled: true,
      axis: "x",
      offsets: { x: 0.5 }
    },
    stepParameters: {
      definition: {
        module: {
          render(ctx) {
            if (ctx.params.hideLeft) {
              ctx.effects.visible("left", false);
            }
          }
        },
        manifest: {},
        cadPath: "part.step"
      },
      parameterValues: {
        hideLeft: true
      }
    }
  });

  const left = scene.displayRecords.find((record) => record.partId === "left");
  const right = scene.displayRecords.find((record) => record.partId === "right");

  assert.equal(left.mesh.visible, false);
  assert.equal(right.mesh.visible, true);
  assert.equal(right.material.transparent, true);
  assert.equal(right.material.depthWrite, false);
  assert.equal(right.material.opacity, 0.035);
  assert.equal(left.material.clippingPlanes.length, 1);
  assert.equal(scene.bounds.min[0], 2);
  assert.equal(scene.bounds.max[0], 3);
  scene.dispose();
});

test("buildModel can apply STEP parameter effects while deferring setup lifecycle", () => {
  let setupCalls = 0;
  const scene = buildModel(THREE, sampleMeshData(), {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: true,
    parameterSetup: false,
    stepParameters: {
      definition: {
        module: {
          setup() {
            setupCalls += 1;
          },
          render(ctx) {
            ctx.effects.transform("left", { translate: [5, 0, 0] });
          }
        },
        manifest: {},
        cadPath: "part.step"
      }
    }
  });

  const left = scene.displayRecords.find((record) => record.partId === "left");

  assert.equal(setupCalls, 0);
  assert.equal(left.mesh.matrix.elements[12], 5);
  assert.equal(scene.bounds.min[0], 2);
  assert.equal(scene.bounds.max[0], 6);
  scene.dispose();
});

// Two components, six occurrences alternating between them, each placed 10 mm apart.
function twoComponentPackage(componentA, componentB, occurrenceIndexes) {
  const parts = occurrenceIndexes.map((index) => {
    const even = index % 2 === 0;
    return {
      id: `o${index}`, occurrenceId: `o${index}`, componentId: even ? "a" : "b",
      sourceMeshKey: even ? "a:flat" : "b:flat", sourceMesh: even ? componentA : componentB,
      vertexCount: 4, triangleCount: 2,
      transform: [1, 0, 0, index * 10, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
      bounds: { min: [index * 10, 0, 0], max: [index * 10 + 1, 1, 0] }
    };
  });
  const xs = occurrenceIndexes.map((index) => index * 10);
  return {
    vertices: new Float32Array(0), indices: new Uint32Array(0),
    bounds: { min: [Math.min(...xs), 0, 0], max: [Math.max(...xs) + 1, 1, 0] },
    partTransformsBaked: false,
    parts
  };
}

function materialSnapshot(material) {
  return {
    type: material.type,
    color: material.color?.getHexString?.() ?? null,
    opacity: material.opacity,
    transparent: material.transparent,
    depthWrite: material.depthWrite,
    depthTest: material.depthTest,
    vertexColors: material.vertexColors,
    roughness: material.roughness ?? null,
    metalness: material.metalness ?? null,
    emissive: material.emissive?.getHexString?.() ?? null,
    emissiveIntensity: material.emissiveIntensity ?? null,
    polygonOffset: material.polygonOffset,
    polygonOffsetFactor: material.polygonOffsetFactor,
    polygonOffsetUnits: material.polygonOffsetUnits
  };
}

function recordSnapshot(record) {
  return {
    partId: record.partId,
    fillIndex: record.fillIndex,
    matrix: Array.from(record.mesh.matrix.elements),
    meshVisible: record.mesh.visible,
    meshRenderOrder: record.mesh.renderOrder,
    material: materialSnapshot(record.material),
    baseColor: record.baseColor?.getHexString?.(),
    baseOpacity: record.baseOpacity,
    partBounds: record.partBounds,
    edgeSegments: record.edgeInstance?.set.segments ?? record.edges?.geometry ?? null,
    edgeState: record.edgeInstance ? record.edgeInstance.set.readSlot(record.edgeInstance.slot) : null,
    edgeMaterials: (record.edgeInstance?.set.materials || record.edgeMaterials || []).map(materialSnapshot),
    ghostVisible: record.ghostMesh?.visible ?? false
  };
}

test("update({ source }) reconciles records across publishes into the state a one-shot build produces", () => {
  const componentA = surfComponentMeshData();
  const componentB = surfComponentMeshData();
  const settings = {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: true,
    edgeRendering: { mode: "screen-space", LineSegments2, LineSegmentsGeometry, LineMaterial }
  };
  const selection = { selectedPartIds: ["o2"], hoveredPartId: "o4", focusedPartId: ["o0", "o2", "o4", "o5"] };

  const oneShot = buildModel(THREE, twoComponentPackage(componentA, componentB, [0, 1, 2, 3, 4, 5]), { ...settings, selection });

  // Publish 1: two occurrences. Publish 2: o1 departs, o2/o3 arrive. Publish 3: all six.
  const scene = buildModel(THREE, twoComponentPackage(componentA, componentB, [0, 1]), settings);
  const [firstO0, firstO1] = scene.displayRecords;
  const firstO1Objects = { mesh: firstO1.mesh, edgeInstance: firstO1.edgeInstance, material: firstO1.material, geometry: firstO1.geometry };
  const disposedMaterials = [];
  for (const record of scene.displayRecords) {
    const dispose = record.material.dispose.bind(record.material);
    record.material.dispose = () => { disposedMaterials.push(record.material); dispose(); };
  }
  scene.update({ source: twoComponentPackage(componentA, componentB, [0, 2, 3]), selection: { selectedPartIds: ["o2"] } });
  assert.deepEqual(scene.displayRecords.map((record) => record.partId), ["o0", "o2", "o3"]);
  assert.equal(scene.displayRecords[0], firstO0, "an occurrence already on screen keeps its record");
  assert.equal(firstO1Objects.mesh.parent, null, "a departed occurrence leaves the scene");
  assert.equal(firstO1Objects.edgeInstance.set.readSlot(firstO1Objects.edgeInstance.slot).visible, false, "its edge slot is released");
  assert.equal(firstO1Objects.edgeInstance.set.liveCount, 1, "the component's other occurrence keeps the set alive");
  assert.ok(disposedMaterials.includes(firstO1Objects.material), "its material is disposed");
  assert.ok(!disposedMaterials.includes(firstO0.material), "kept materials are not");
  assert.equal(firstO1Objects.geometry.attributes.position.array, componentB.vertices, "component geometry survives (cached)");
  const secondO2 = scene.displayRecords[1];

  scene.update({ source: twoComponentPackage(componentA, componentB, [0, 1, 2, 3, 4, 5]), selection });
  assert.deepEqual(scene.displayRecords.map((record) => record.partId), ["o0", "o1", "o2", "o3", "o4", "o5"]);
  assert.equal(scene.displayRecords[0], firstO0);
  assert.equal(scene.displayRecords[0].mesh, firstO0.mesh);
  assert.equal(scene.displayRecords[2], secondO2);
  assert.notEqual(scene.displayRecords[1], firstO1, "a returning occurrence gets a fresh record");

  // Final state equals the one-shot build: records, matrices, materials, edge objects, groups, bounds.
  assert.deepEqual(scene.displayRecords.map(recordSnapshot), oneShot.displayRecords.map(recordSnapshot));
  assert.equal(scene.modelGroup.children.length, oneShot.modelGroup.children.length);
  assert.equal(scene.edgesGroup.children.length, oneShot.edgesGroup.children.length);
  assert.deepEqual(new Set(scene.modelGroup.children), new Set(scene.displayRecords.map((record) => record.mesh)));
  assert.deepEqual(new Set(scene.edgesGroup.children), new Set(scene.displayRecords.map((record) => record.edgeInstance.set.object)));
  assert.equal(scene.edgesGroup.children.length, 2, "one instanced edge draw per component");
  assert.deepEqual(scene.bounds, oneShot.bounds);
  assert.equal(scene.radius, oneShot.radius);
  assert.equal(scene.meshData.parts.length, 6);

  // Selection state kept applying across the publish: o2 is highlighted exactly as in the one-shot.
  assert.equal(secondO2.edgeInstance.set.readSlot(secondO2.edgeInstance.slot).highlighted, true);
  assert.equal(secondO2.material.emissiveIntensity, oneShot.displayRecords[2].material.emissiveIntensity);
  oneShot.dispose();
  scene.dispose();
});

test("update({ source }) keeps a deformed tube's private geometry and deformation state", () => {
  const component = surfComponentMeshData();
  const scene = buildModel(THREE, twoComponentPackage(component, component, [0]), { renderPartsIndividually: true });
  const record = scene.displayRecords[0];
  record.gpuTubeDeformationAllowed = false;
  const rest = { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [3, 0, 0] }] };
  const path = { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 2], end: [0, 3, 2] }] };
  const spec = normalizeTubeDeformation({ rest, path, maxSegmentLength: 1000 });
  applyRecordTubeDeformation(THREE, record, spec);
  const state = record.tubeDeformationState;
  const privateGeometry = record.geometry;
  const edgeGeometry = record.edges.geometry;
  assert.ok(state.active);
  assert.equal(record.edgeInstance, null, "a deformed tube draws its own edges");

  scene.update({ source: twoComponentPackage(component, component, [0, 2]) });
  assert.equal(scene.displayRecords[0], record);
  assert.equal(record.tubeDeformationState, state, "deformation state survives the publish");
  assert.equal(record.geometry, privateGeometry, "so does its private geometry");
  assert.equal(record.edges.geometry, edgeGeometry);
  assert.equal(record.mesh.geometry, privateGeometry);
  // Without a scene module the publish resets the pose; re-applying the same
  // deformation reuses the retained state instead of refining the rest surface again.
  applyRecordTubeDeformation(THREE, record, spec);
  assert.equal(record.tubeDeformationState, state);
  assert.equal(record.geometry, privateGeometry);
  assert.ok(state.active);
  scene.dispose();
});

test("update({ source }) rebuilds when the build settings change with it", () => {
  const component = surfComponentMeshData();
  const scene = buildModel(THREE, twoComponentPackage(component, component, [0, 1]), { renderPartsIndividually: true });
  const before = scene.displayRecords[0];
  scene.update({ source: twoComponentPackage(component, component, [0, 1, 2]), displayMode: CAD_DISPLAY_MODE.WIREFRAME });
  assert.notEqual(scene.displayRecords[0], before, "a display-mode change rebuilds every record");
  assert.equal(scene.displayRecords.length, 3);
  assert.equal(scene.displayRecords[0].edges.geometry.type, "WireframeGeometry");
  scene.dispose();
});

test("departed components free their GPU buffers, BVH and edge draw; a returning one re-uploads from the cache", () => {
  const componentA = surfComponentMeshData();
  const componentB = surfComponentMeshData();
  const scene = buildModel(THREE, twoComponentPackage(componentA, componentB, [0, 1, 3]), { renderPartsIndividually: true });
  const [o0, o1, o3] = scene.displayRecords;
  const geometryB = o1.geometry;
  assert.equal(o3.geometry, geometryB, "both B occurrences share the component geometry");
  geometryB.boundsTree = { fake: true };
  const disposedGeometries = [];
  geometryB.addEventListener("dispose", () => disposedGeometries.push(geometryB));
  const setB = o1.edgeInstance.set;
  const segmentTextureB = setB.segments.texture;
  const disposedTextures = [];
  segmentTextureB.addEventListener("dispose", () => disposedTextures.push(segmentTextureB));

  // Publish 2: every B occurrence departs.
  scene.update({ source: twoComponentPackage(componentA, componentB, [0, 2]) });
  assert.deepEqual(scene.displayRecords.map((record) => record.partId), ["o0", "o2"]);
  assert.deepEqual(disposedGeometries, [geometryB], "the component geometry's GPU buffers are released once");
  assert.equal(geometryB.boundsTree, null, "and its BVH");
  assert.equal(setB.disposed, true, "the component's edge draw is disposed");
  assert.equal(setB.object.parent, null);
  assert.deepEqual(disposedTextures, [segmentTextureB], "and its segment texture's GPU copy");
  assert.equal(scene.edgesGroup.children.length, 1, "one edge draw left, component A's");
  assert.equal(scene.runtime.cadEdgeInstanceSets.size, 1);
  assert.equal(o0.geometry.boundsTree, undefined, "A's geometry is untouched");

  // Publish 3: B returns. Same cached geometry object (three re-uploads it on
  // the next draw), a fresh edge draw over the cached segment texture.
  scene.update({ source: twoComponentPackage(componentA, componentB, [0, 1, 2, 3]) });
  const returned = scene.displayRecords.find((record) => record.partId === "o1");
  assert.equal(returned.geometry, geometryB);
  assert.equal(returned.edgeInstance.set.segments.texture, segmentTextureB);
  assert.notEqual(returned.edgeInstance.set, setB);
  assert.equal(scene.runtime.cadEdgeInstanceSets.size, 2);

  // Disposing the scene releases every component's GPU copy.
  const geometryA = o0.geometry;
  const disposedAtEnd = [];
  geometryA.addEventListener("dispose", () => disposedAtEnd.push("A"));
  geometryB.addEventListener("dispose", () => disposedAtEnd.push("B"));
  scene.dispose();
  assert.deepEqual(disposedAtEnd.sort(), ["A", "B"]);
  assert.equal(scene.displayRecords.length, 0);
});
