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
    cadEdgeSegments: new Float32Array([
      0, 0, 0, 1, 0, 0,
      1, 0, 0, 1, 1, 0,
      1, 1, 0, 0, 1, 0,
      0, 1, 0, 0, 0, 0,
      0, 0, 0, 1, 1, 0
    ]),
    cadEdgeClassRanges: [
      { classId: "feature", segmentStart: 0, segmentCount: 3 },
      { classId: "tangent", segmentStart: 3, segmentCount: 1 },
      { classId: "degenerate", segmentStart: 4, segmentCount: 1 }
    ],
    bounds: { min: [0, 0, 0], max: [1, 1, 0] },
    parts: [{ id: "surf:0", vertexOffset: 0, vertexCount: 4, triangleOffset: 0, triangleCount: 2, bounds: { min: [0, 0, 0], max: [1, 1, 0] } }]
  };
}

function edgeLinesByClass(record) {
  return Object.fromEntries((record?.edges?.children || []).map((line) => [line.userData.cadEdgeClass, line]));
}

test("buildModel draws a surf component's CAD edges as one line object per edge class", () => {
  const scene = buildModel(THREE, surfComponentMeshData(), {
    theme: cloneThemePresetSettings("workbench-light"),
    displayMode: CAD_DISPLAY_MODE.SOLID,
    renderPartsIndividually: true,
    edgeRendering: { mode: "screen-space", LineSegments2, LineSegmentsGeometry, LineMaterial }
  });
  const record = scene.displayRecords[0];
  const lines = edgeLinesByClass(record);

  assert.equal(scene.edgesGroup.children.length, 1);
  assert.equal(record.edges.isGroup, true);
  // Degenerate edges default to zero thickness and are not drawn.
  assert.deepEqual(Object.keys(lines).sort(), ["feature", "tangent"]);
  assert.equal(lines.feature instanceof LineSegments2, true);
  assert.equal(lines.feature.geometry.attributes.instanceStart.count, 3);
  assert.equal(lines.tangent.geometry.attributes.instanceStart.count, 1);
  assert.equal(lines.feature.material.opacity, 1);
  assert.equal(lines.tangent.material.opacity, 0.5);
  assert.equal(lines.tangent.material.linewidth, 1.15);
  assert.equal(lines.feature.material.depthTest, true);
  assert.equal(lines.feature.material.polygonOffset, true, "CAD edge lines carry their own depth bias");
  assert.equal(record.edgeMaterials.length, 2);
  assert.equal(record.material.polygonOffset, true, "the surface is pushed back behind its edge lines");
  assert.equal(record.material.polygonOffsetFactor, 1);
  assert.equal(record.material.userData.cadSurfaceEdges, undefined);
  assert.equal(record.geometry.getAttribute("position").count, 4, "indexed geometry stays indexed");
  assert.equal(scene.runtime.screenSpaceLineMaterials.size, 2);

  // Selection recolours every class to edges.highlightColor; deselection restores each.
  scene.update({ selection: { selectedPartIds: ["surf:0"] } });
  assert.equal(lines.feature.material.color.getHexString(), "8dc5ff");
  assert.equal(lines.tangent.material.color.getHexString(), "8dc5ff");
  assert.equal(lines.tangent.material.opacity, 1);
  assert.equal(record.edges.renderOrder, 26);
  scene.update({ selection: { selectedPartIds: [] } });
  assert.equal(lines.tangent.material.opacity, 0.5);
  assert.equal(record.edges.renderOrder, 3);

  // Show-through modes drop the depth test on every class line.
  const transparent = buildModel(THREE, surfComponentMeshData(), {
    theme: cloneThemePresetSettings("workbench-light"),
    displayMode: CAD_DISPLAY_MODE.TRANSPARENT,
    renderPartsIndividually: true
  });
  for (const material of transparent.displayRecords[0].edgeMaterials) {
    assert.equal(material.depthTest, false);
  }
  assert.equal(transparent.displayRecords[0].material.polygonOffset, true);
  transparent.dispose();

  // Rendered mode draws no linework at all; wireframe draws the mesh wires instead.
  const rendered = buildModel(THREE, surfComponentMeshData(), { displayMode: CAD_DISPLAY_MODE.RENDERED, renderPartsIndividually: true });
  assert.equal(rendered.displayRecords[0].edges, null);
  rendered.dispose();
  const wire = buildModel(THREE, surfComponentMeshData(), { displayMode: CAD_DISPLAY_MODE.WIREFRAME, renderPartsIndividually: true });
  assert.equal(wire.displayRecords[0].edges.geometry.type, "WireframeGeometry");
  wire.dispose();

  scene.dispose();
  assert.equal(scene.runtime.screenSpaceLineMaterials.size, 0);
});

test("occurrences of one component share its CAD edge line geometry and follow their own transforms", () => {
  const sourceMesh = surfComponentMeshData();
  const meshData = {
    vertices: new Float32Array(0), indices: new Uint32Array(0),
    bounds: { min: [0, 0, 0], max: [11, 1, 0] },
    partTransformsBaked: false,
    parts: ["a", "b"].map((id, index) => ({
      id, occurrenceId: id, sourceMeshKey: "cid:flat", sourceMesh, vertexCount: 4, triangleCount: 2,
      transform: [1, 0, 0, index * 10, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
      bounds: { min: [index * 10, 0, 0], max: [index * 10 + 1, 1, 0] }
    }))
  };
  const scene = buildModel(THREE, meshData, { renderPartsIndividually: true });
  const [a, b] = scene.displayRecords;
  assert.equal(edgeLinesByClass(a).feature.geometry, edgeLinesByClass(b).feature.geometry, "one geometry per component and class");
  assert.notEqual(edgeLinesByClass(a).feature.material, edgeLinesByClass(b).feature.material, "materials are per occurrence");
  assert.equal(a.edges.matrix.elements[12], 0);
  assert.equal(b.edges.matrix.elements[12], 10);
  assert.deepEqual(b.edges.matrix.elements, b.mesh.matrix.elements, "edge lines ride the occurrence matrix");
  scene.dispose();
});

test("component mesh buffers stay shared until a deformation needs writable attributes", () => {
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
  const savedEdgeSegments = sourceMesh.cadEdgeSegments.slice();
  assert.equal(edgeLinesByClass(record).feature.geometry.getAttribute("position").array.buffer, sourceMesh.cadEdgeSegments.buffer);
  record.gpuTubeDeformationAllowed = false;
  const rest = { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [3, 0, 0] }] };
  const path = { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 2], end: [0, 3, 2] }] };
  applyRecordTubeDeformation(THREE, record, normalizeTubeDeformation({ rest, path, maxSegmentLength: 1000 }));
  assert.notEqual(record.geometry.getAttribute("normal").array, sourceMesh.normals);
  assert.notDeepEqual(record.geometry.getAttribute("position").array, savedPositions);
  assert.deepEqual(sourceMesh.vertices, savedPositions);
  assert.deepEqual(sourceMesh.normals, savedNormals);
  // The CAD edge lines bend with the surface on a private copy; the shared segments stay put.
  const bentEdge = edgeLinesByClass(record).feature.geometry.getAttribute("position");
  assert.notEqual(bentEdge.array.buffer, sourceMesh.cadEdgeSegments.buffer);
  assert.deepEqual(sourceMesh.cadEdgeSegments, savedEdgeSegments);
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

test("buildModel rebuilds CAD edge lines when edge class settings change", () => {
  const theme = cloneThemePresetSettings("workbench-light");
  const scene = buildModel(THREE, surfComponentMeshData(), {
    theme,
    displayMode: CAD_DISPLAY_MODE.SOLID,
    renderPartsIndividually: true,
    edgeRendering: { mode: "screen-space", LineSegments2, LineSegmentsGeometry, LineMaterial }
  });
  const originalEdges = scene.displayRecords[0].edges;
  const originalGeometry = edgeLinesByClass(scene.displayRecords[0]).tangent.geometry;

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
            thickness: 2.5
          }
        }
      }
    }
  });

  const lines = edgeLinesByClass(scene.displayRecords[0]);
  assert.notEqual(scene.displayRecords[0].edges, originalEdges);
  assert.equal(lines.tangent.material.linewidth, 2.5);
  // Class colours are explicit in the default class settings, so the edge
  // colour does not recolour them (the shader read them the same way).
  assert.equal(lines.tangent.material.color.getHexString(), "132232");
  assert.equal(lines.tangent.geometry, originalGeometry, "line geometry is cached across rebuilds");
  assert.equal(scene.edgesGroup.children.length, 1);
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
