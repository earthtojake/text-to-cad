import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { resolveSceneSettings } from "./sceneSettings.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";

import {
  applyDisplayRecordTransform,
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
import { loadTubeDeformation } from "./tubeDeformationChunk.js";

// `deformTube` needs the lazy tube runtime, which production loads through
// compileAnimationSource. These clips are built by hand, so load it here.
await loadTubeDeformation();
import { applySceneState } from "./applySceneState.js";
import { applyPartVisualState as applyViewerPartVisualState } from "../lib/viewer/partVisualState.js";
import { syncRuntimeStepClipPlane } from "../lib/viewer/modelRuntime.js";
import { applyMaterialSettingsToRecord as applyViewerMaterialSettings } from "../lib/viewer/surfaceMaterials.js";
import { buildComposedPackageMeshData } from "../lib/assembly/meshData.js";
import { applyUrdfPoseToMeshData, buildUrdfMeshGeometry } from "../lib/urdf/kinematics.js";

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

test("Render shadow receivers update in place for opaque meshes and surface instances", () => {
  const scene = buildModel(THREE, composedPackage(surfComponentMeshData(), 4), {
    renderPartsIndividually: true,
    receiveShadows: true
  });
  const record = scene.displayRecords[0];
  const mesh = record.mesh;
  const geometry = record.geometry;
  const instanceSet = record.surfaceInstance.set;

  assert.equal(mesh.castShadow, true);
  assert.equal(mesh.receiveShadow, true);
  assert.equal(instanceSet.object.castShadow, true);
  assert.equal(instanceSet.object.receiveShadow, true);

  scene.update({ receiveShadows: false });
  assert.equal(scene.displayRecords[0], record, "shadow policy does not rebuild the record");
  assert.equal(record.geometry, geometry, "shadow policy does not rebuild geometry");
  assert.equal(record.surfaceInstance.set, instanceSet, "shadow policy retains the shared draw");
  assert.equal(mesh.castShadow, true, "normal CAD preserves its existing casting policy");
  assert.equal(mesh.receiveShadow, false);
  assert.equal(instanceSet.object.castShadow, true);
  assert.equal(instanceSet.object.receiveShadow, false);

  scene.update({ receiveShadows: true });
  assert.equal(record.surfaceInstance.set, instanceSet);
  assert.equal(mesh.receiveShadow, true);
  assert.equal(instanceSet.object.receiveShadow, true);
  scene.dispose();
});

test("buildModel honors zero-valued source-color grading without rebuilding records", () => {
  const theme = cloneThemePresetSettings("workbench-light");
  const meshData = sampleMeshData();
  meshData.sourceColor = "#336699";
  const scene = buildModel(THREE, meshData, {
    theme,
    materialSettings: {
      ...theme.materials,
      brightness: 0
    },
    renderPartsIndividually: true
  });
  const record = scene.displayRecords[0];
  const mesh = record.mesh;

  assert.equal(record.material.color.getHexString(), "000000", "zero brightness makes the source color black");

  scene.update({
    materialSettings: {
      ...theme.materials,
      saturation: 0,
      contrast: 1,
      brightness: 1
    }
  });

  assert.equal(record.mesh, mesh, "grading remains a mutable material update");
  assertClose(
    record.material.color.toArray(),
    [record.material.color.r, record.material.color.r, record.material.color.r],
    "zero saturation removes the source hue"
  );
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

  assert.equal(record.rawColors, sourceColors, "the immutable color baseline shares the component allocation");
  assert.notEqual(colorAttribute.array, sourceColors);
  assert.deepEqual(Array.from(sourceColors), originalColors);

  scene.update({
    materialSettings: {
      ...theme.materials,
      brightness: 0
    }
  });

  assert.ok(
    Array.from(colorAttribute.array).every((channel) => Math.abs(channel) < 1e-6),
    "zero brightness is applied to the live vertex-color buffer"
  );

  scene.update({
    materialSettings: {
      ...theme.materials,
      saturation: 0,
      contrast: 1,
      brightness: 1
    }
  });

  for (let index = 0; index < colorAttribute.array.length; index += 3) {
    assertClose(
      Array.from(colorAttribute.array.subarray(index, index + 3)),
      [colorAttribute.array[index], colorAttribute.array[index], colorAttribute.array[index]],
      `zero saturation removes vertex ${index / 3}'s hue`
    );
  }

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
    displayMode: CAD_DISPLAY_MODE.SHADED_EDGES,
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
  assertClose(classColor.slice(0, 3), linearRgb("#253443"), "feature class colour (linear)");
  assert.equal(classColor[3], 1, "feature opacity");
  assertClose(classColor[7], 1, "tangent opacity");
  // Class widths in pixels for the classes this component carries (no seams here); degenerate is off.
  assert.deepEqual(set.uniforms.cadClassWidth.value.toArray(), [1, 0.65, 0, 0], "per-class thickness in pixels");
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
  const rendered = buildModel(THREE, surfComponentMeshData(), { displayMode: CAD_DISPLAY_MODE.SHADED, renderPartsIndividually: true });
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

test("a component's occurrences share one surface draw and one instanced edge draw", () => {
  const sourceMesh = surfComponentMeshData();
  const first = buildModel(THREE, composedPackage(sourceMesh, 4), { renderPartsIndividually: true });
  const geometries = new Set();
  const buffers = new Set();
  let drawables = 0;
  first.root.traverse((object) => {
    if (!object.geometry || object.userData.cadEdgeInstancesHighlight || object.material?.visible === false) return;
    drawables += 1;
    geometries.add(object.geometry);
    for (const buffer of geometryBuffers(object.geometry)) buffers.add(buffer);
  });
  assert.equal(drawables, 2, "four occurrences collapse to one surface draw plus one edge draw");
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

test("surface instances follow transforms and keep the unaffected majority instanced through hover/selection", () => {
  const sourceMesh = surfComponentMeshData();
  const scene = buildModel(THREE, composedPackage(sourceMesh, 4), { renderPartsIndividually: true });
  const record = scene.displayRecords[2];
  const { set, slot } = record.surfaceInstance;
  assert.equal(scene.runtime.cadSurfaceInstanceSets.size, 1);
  assert.equal(scene.modelGroup.children.filter((object) => object.material?.visible !== false).length, 1);

  record.explodedViewMatrix = new THREE.Matrix4().makeTranslation(0, 6, 0);
  applyDisplayRecordTransform(THREE, record);
  const matrix = new THREE.Matrix4();
  set.object.getMatrixAt(slot, matrix);
  assert.equal(matrix.elements[12], 20);
  assert.equal(matrix.elements[13], 6);

  scene.update({ clip: { enabled: true, axis: "x", offsets: { x: 0.5 } } });
  assert.equal(set.object.material.clippingPlanes.length, 1, "shared surface pass receives clipping");
  const originalRecords = [...scene.displayRecords];
  const originalMaterials = scene.displayRecords.map((item) => item.material);
  const object = set.object;
  scene.update({ selection: { hoveredPartId: "o2" } });
  assert.equal(scene.runtime.cadSurfaceInstanceSets.size, 1);
  assert.equal(scene.runtime.cadSurfaceInstanceSets.values().next().value.object, object, "hover reuses the instance buffer");
  assert.deepEqual(scene.displayRecords, originalRecords, "hover does not rebuild display records");
  assert.deepEqual(scene.displayRecords.map((item) => item.material), originalMaterials, "hover reuses materials");
  assert.equal(record.material.visible, true, "hovered record uses its ordinary transparent highlight pass");
  assert.ok(scene.displayRecords.filter((item) => item !== record).every((item) => item.material.visible === false));

  scene.update({ selection: { selectedPartIds: ["o2"] } });
  assert.equal(scene.runtime.cadSurfaceInstanceSets.size, 1, "the unaffected three records stay instanced");
  assert.equal(scene.runtime.cadSurfaceInstanceSets.values().next().value.object, object);
  assert.equal(record.material.visible, true);
  assert.equal(scene.displayRecords.find((item) => item.partId === "o2").mesh.userData.partId, "o2");
  scene.update({ selection: { selectedPartIds: [], hoveredPartId: "" } });
  assert.equal(record.material.visible, false, "cleared transient state rejoins the same instance slot");
  assert.equal(scene.runtime.cadSurfaceInstanceSets.values().next().value.object, object);
  scene.dispose();
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
  // Each basic-only class has private segment positions and a mutable material;
  // the component's shared points stay put.
  assert.equal(record.edgeInstance, null);
  assert.equal(set.liveCount, 0);
  assert.equal(set.geometry.instanceCount, 0);
  assert.equal(record.edges.isGroup, true);
  assert.equal(record.edgeMaterials.length, 2);
  assert.ok(record.edges.children.every((line) => line.isLineSegments));
  const bentEdge = record.edges.children[0].geometry.getAttribute("position");
  assert.notEqual(bentEdge.array, sourceMesh.cadEdgePositions);
  assert.notDeepEqual(Array.from(bentEdge.array).slice(0, 3), [0, 0, 0]);
  assert.equal(record.edges.children[0].geometry.index, null);
  const basicGeometries = record.edges.children.map((line) => line.geometry);
  const basicMaterials = [...record.edgeMaterials];
  const otherScene = buildModel(THREE, meshData, { appearance: "light", renderPartsIndividually: true });
  const otherColors = [...otherScene.displayRecords[0].edgeInstance.set.uniforms.cadClassColor.value.elements];
  scene.update({ appearance: "dark" });
  assert.equal(scene.displayRecords[0], record);
  assert.deepEqual(record.edges.children.map((line) => line.geometry), basicGeometries);
  assert.deepEqual(record.edgeMaterials, basicMaterials);
  assert.deepEqual(record.edgeMaterials.map((material) => material.color.getHexString()), ["253443", "667788"]);
  scene.update({ selection: { selectedPartIds: ["tube"] } });
  assert.ok(record.edgeMaterials.every((material) => material.color.getHexString() === "8dc5ff"));
  scene.update({ selection: { selectedPartIds: [] }, appearance: "light" });
  assert.deepEqual(record.edgeMaterials.map((material) => material.color.getHexString()), ["253443", "667788"]);
  assert.deepEqual(otherScene.displayRecords[0].edgeInstance.set.uniforms.cadClassColor.value.elements, otherColors);
  otherScene.dispose();
  assert.deepEqual(sourceMesh.cadEdgePositions, savedEdgePositions);
  assert.deepEqual(record.edges.matrix.elements, record.mesh.matrix.elements);
  scene.dispose();
});

test("appearance preserves CAD ink, geometry, instance slots and segment textures", () => {
  const source = surfComponentMeshData();
  const scene = buildModel(THREE, source, {
    appearance: "light", displayMode: CAD_DISPLAY_MODE.SHADED_EDGES, renderPartsIndividually: true
  });
  const original = scene.displayRecords[0];
  const { set, slot } = original.edgeInstance;
  const segments = set.segments;
  const geometry = original.geometry;
  const second = buildModel(THREE, source, { appearance: "dark", renderPartsIndividually: true });
  assert.equal(second.displayRecords[0].edgeInstance.set.segments, segments, "separate themes share geometric segment texture");
  for (const appearance of ["dark", "light"]) {
    scene.update({ appearance });
    const record = scene.displayRecords[0];
    assert.equal(record, original);
    assert.equal(record.geometry, geometry);
    assert.equal(record.edgeInstance.set, set);
    assert.equal(record.edgeInstance.slot, slot);
    assert.equal(set.segments, segments);
    assertClose(set.uniforms.cadClassColor.value.elements.slice(0, 3), linearRgb("#253443"), "current palette");
    assert.deepEqual(set.uniforms.cadClassWidth.value.toArray(), [1, 0.65, 0, 0]);
  }
  second.dispose();
  scene.dispose();
});

test("wireframe appearance preserves fixed ink and geometry", () => {
  const scene = buildModel(THREE, sampleMeshData(), {
    appearance: "light", displayMode: CAD_DISPLAY_MODE.WIREFRAME,
    edgeRendering: { mode: "screen-space", LineSegments2, LineSegmentsGeometry, LineMaterial }
  });
  const record = scene.displayRecords[0];
  const geometry = record.edges.geometry;
  scene.update({ appearance: "dark", edgeRendering: { mode: "screen-space", LineSegments2, LineSegmentsGeometry, LineMaterial } });
  assert.equal(scene.displayRecords[0], record);
  assert.equal(record.edges.geometry, geometry);
  assert.equal(record.edges.material.color.getHexString(), "253443");
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
    displayMode: CAD_DISPLAY_MODE.SHADED,
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

test("hidden_lines_removed surfaces are a depth mask, so an occluded line is occluded", () => {
  const theme = cloneThemePresetSettings("workbench-light");
  const scene = buildModel(THREE, sampleMeshData(), {
    theme,
    displayMode: CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED,
    renderPartsIndividually: true
  });
  const record = scene.displayRecords[0];
  // The near-invisible fill is the whole mechanism of the mode: the edges depth-test,
  // and this surface is what an occluded line tests AGAINST. Deciding the write from
  // opacity alone left the mask unwritten and drew every hidden line.
  assert.equal(record.material.opacity, 0.045);
  assert.equal(record.material.transparent, true);
  assert.equal(record.material.depthWrite, true, "the ghost fill must write depth");
  assert.equal(record.edgeMaterials[0].depthTest, true, "and the lines must test it");
  // The mask has to be drawn before the lines that test it. Both are in three's
  // transparent list, so renderOrder is the only thing that keeps them apart.
  assert.ok(
    (record.mesh.renderOrder || 0) < record.edges.renderOrder,
    "surfaces render before the edge lines"
  );
  scene.dispose();
});

test("wireframe keeps its see-through fill: every triangle stays visible", () => {
  const theme = cloneThemePresetSettings("workbench-light");
  const scene = buildModel(THREE, sampleMeshData(), {
    theme,
    displayMode: CAD_DISPLAY_MODE.WIREFRAME,
    renderPartsIndividually: true
  });
  const record = scene.displayRecords[0];
  assert.equal(record.material.depthWrite, false);
  scene.dispose();
});

test("buildModel applies source part opacity from GLB material metadata", () => {
  const meshData = sampleMeshData();
  meshData.parts = meshData.parts.map((part, index) => index === 0
    ? { ...part, color: "#ff0000", opacity: 0.2, hasSourceColors: true }
    : part
  );
  const scene = buildModel(THREE, meshData, {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: true,
    receiveShadows: true
  });

  const left = scene.displayRecords.find((record) => record.partId === "left");
  const right = scene.displayRecords.find((record) => record.partId === "right");

  assert.equal(left.baseOpacity, 0.2);
  assert.equal(left.material.opacity, 0.2);
  assert.equal(left.material.transparent, true);
  assert.equal(left.material.depthWrite, false);
  assert.equal(left.mesh.castShadow, false, "translucent source parts do not cast solid silhouettes in Render");
  assert.equal(left.mesh.receiveShadow, false, "translucent source parts stay out of the opaque receiver pass");
  assert.equal(right.mesh.castShadow, true);
  assert.equal(right.mesh.receiveShadow, true);
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
    theme: baseTheme,
    edgeSettings: DEFAULT_DISPLAY_EDGE_SETTINGS,
    displayMode: CAD_DISPLAY_MODE.SHADED_EDGES
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
    displayMode: CAD_DISPLAY_MODE.SHADED_EDGES,
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
    theme,
    edgeSettings: {
      ...DEFAULT_DISPLAY_EDGE_SETTINGS,
      enabled: false,
      silhouette: true,
      silhouetteScale: 0.004
    },
    displayMode: CAD_DISPLAY_MODE.SHADED,
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

// A camera is grounded on the model's zero pose, so the scene has to keep that
// box available while `bounds` follows whatever a mate, a parameter or an
// animation frame has done to the records.
test("buildModel keeps restBounds at the zero pose while bounds follow the parameter pose", () => {
  const scene = buildModel(THREE, sampleMeshData(), {
    theme: cloneThemePresetSettings("workbench-light"),
    renderPartsIndividually: true,
    parameterSetup: false,
    stepParameters: {
      definition: {
        module: {
          render(ctx) {
            ctx.effects.transform("right", { translate: [12, 0, 0] });
          }
        },
        manifest: {},
        cadPath: "part.step"
      }
    }
  });

  assert.deepEqual(scene.bounds.max, [15, 1, 0], "bounds follow the posed record");
  assert.deepEqual(scene.restBounds.min, [0, 0, 0]);
  assert.deepEqual(scene.restBounds.max, [3, 1, 0]);

  scene.update({
    stepParameters: {
      definition: {
        module: {
          render(ctx) {
            ctx.effects.transform("right", { translate: [40, 0, 0] });
          }
        },
        manifest: {},
        cadPath: "part.step"
      }
    }
  });
  assert.deepEqual(scene.bounds.max, [43, 1, 0], "a new pose moves bounds");
  assert.deepEqual(scene.restBounds.max, [3, 1, 0], "and never moves restBounds");
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

test("static revision adoption touches only changed immutable rows and preserves picking and resource ownership", () => {
  const componentA = surfComponentMeshData();
  const componentB = surfComponentMeshData();
  const descriptor = (moved = -1, material = null) => {
    const occurrences = Array.from({ length: 24 }, (_, index) => ({
      id: `o${index}`,
      name: `part ${index}`,
      component: index % 2 ? "b" : "a",
      transform: [1, 0, 0, index === moved ? 80 : index * 2, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
      ...(index === moved && material ? { material } : {})
    }));
    return { kind: "assembly-package", entryKind: "assembly", components: { a: {}, b: {} }, occurrences,
      assembly: { root: { id: "root", name: "root", nodeType: "assembly",
        children: occurrences.map(({ id, name }) => ({ id, name, nodeType: "part", children: [] })) } } };
  };
  const components = { a: componentA, b: componentB };
  let source = buildComposedPackageMeshData(descriptor(), components);
  const selection = { selectedPartIds: ["o0"], hoveredPartId: "o1" };
  let faceIdBuilds = 0;
  const faceIdsForPart = (part) => { faceIdBuilds += 1; return [`face:${part.id}`]; };
  const scene = buildModel(THREE, source, {
    renderPartsIndividually: true,
    selection,
    callbacks: { faceIdsForPart }
  });
  assert.equal(faceIdBuilds, 24);
  const unchanged = scene.displayRecords[2];
  const changed = scene.displayRecords[7];
  const unchangedPart = source.parts[2];
  const unchangedMatrix = unchanged.mesh.matrix.clone();
  const unchangedFaceIds = unchanged.mesh.userData.faceIds;
  const unchangedSet = unchanged.surfaceInstance.set;
  const ownedBefore = scene.runtime.ownedGeometries.size;
  let unchangedColorWrites = 0;
  const copy = unchanged.material.color.copy.bind(unchanged.material.color);
  unchanged.material.color.copy = (...args) => { unchangedColorWrites += 1; return copy(...args); };

  const placedDescriptor = descriptor(7);
  const placed = buildComposedPackageMeshData(placedDescriptor, components, { previous: source });
  assert.equal(placed.parts[2], unchangedPart);
  scene.update({ source: placed, selection, callbacks: { faceIdsForPart } });
  source = placed;
  assert.equal(scene.displayRecords[2], unchanged);
  assert.equal(scene.displayRecords[7], changed, "placement keeps the occurrence record and its picking identity");
  assert.equal(changed.mesh.matrix.elements[12], 80);
  assert.equal(unchanged.mesh.userData.faceIds, unchangedFaceIds);
  assert.equal(faceIdBuilds, 24, "placement-only adoption rebuilds no picking records");
  assert.deepEqual(unchanged.mesh.matrix.elements, unchangedMatrix.elements);
  assert.equal(unchangedColorWrites, 0, "unchanged material and visual passes are skipped");
  assert.equal(unchanged.surfaceInstance.set, unchangedSet);
  assert.equal(scene.runtime.ownedGeometries.size, ownedBefore);

  const appeared = buildComposedPackageMeshData(descriptor(7, { roughness: 0.17, metalness: 0.83 }), components, { previous: source });
  scene.update({ source: appeared, selection });
  source = appeared;
  assert.equal(scene.displayRecords[7], changed);
  assert.equal(changed.material.roughness, 0.17);
  assert.equal(changed.material.metalness, 0.83);
  assert.equal(unchangedColorWrites, 0);

  const replacementA = { ...componentA, vertices: new Float32Array(componentA.vertices),
    parts: componentA.parts.map((part) => ({ ...part })) };
  const replaced = buildComposedPackageMeshData(descriptor(7, { roughness: 0.17, metalness: 0.83 }),
    { a: replacementA, b: componentB }, { previous: source });
  const retainedB = scene.displayRecords[1];
  scene.update({ source: replaced, selection });
  assert.equal(scene.displayRecords[1], retainedB, "the untouched component keeps its record and resources");
  assert.notEqual(scene.displayRecords[0], unchanged, "the replaced component receives exact new geometry");
  assert.equal(scene.displayRecords[0].geometry.attributes.position.array, replacementA.vertices);
  assert.equal(faceIdBuilds, 36, "only the replaced component's occurrences rebuild picking records");
  assert.equal(scene.runtime.ownedGeometries.size, 2, "replacement retires the old component owner without growth");
  assert.equal(scene.runtime.cadSurfaceInstanceSets.size, 2);

  // A simultaneous contextual change cannot take the selective path.
  let contextualWrites = 0;
  const retainedColor = retainedB.material.color.copy.bind(retainedB.material.color);
  retainedB.material.color.copy = (...args) => { contextualWrites += 1; return retainedColor(...args); };
  const sameRows = buildComposedPackageMeshData(structuredClone(descriptor(7, { roughness: 0.17, metalness: 0.83 })),
    { a: replacementA, b: componentB }, { previous: replaced });
  scene.update({ source: sameRows, selection: { selectedPartIds: ["o1"] } });
  assert.ok(contextualWrites > 0, "selection changes remain observable on exact retained rows");
  scene.dispose();
  assert.equal(scene.runtime.ownedGeometries.size, 0);
  assert.equal(scene.runtime.cadSurfaceInstanceSets.size, 0);
});

test("exact source-part identity skips work only for rows owned by the current composer result", () => {
  const component = surfComponentMeshData();
  const descriptor = {
    kind: "assembly-package",
    entryKind: "assembly",
    components: { a: {} },
    occurrences: [{
      id: "o1",
      component: "a",
      transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    }],
    assembly: { root: { id: "root", nodeType: "assembly", children: [{ id: "o1", nodeType: "part", children: [] }] } }
  };
  const composed = buildComposedPackageMeshData(descriptor, { a: component });
  const scene = buildModel(THREE, composed, { renderPartsIndividually: true });
  const record = scene.displayRecords[0];
  const sameMutablePart = composed.parts[0];
  sameMutablePart.transform[3] = 37;
  sameMutablePart.material = { roughness: 0.14, metalness: 0.72 };
  // A spread object is ordinary public mesh data. It has the same row identity
  // but no composer ownership proof for that row in this exact source context.
  const rawReplacement = { ...composed, parts: composed.parts };
  scene.update({ source: rawReplacement });
  assert.equal(scene.displayRecords[0], record);
  assert.equal(record.mesh.matrix.elements[12], 37);
  assert.equal(record.material.roughness, 0.14);
  assert.equal(record.material.metalness, 0.72);
  scene.dispose();
});

test("Inspect preserves authored finish and alpha through selection and source reuse", () => {
  for (const appearance of ["light", "dark"]) {
    const inspect = resolveSceneSettings({ appearance });
    const source = sampleMeshData();
    source.parts = source.parts.map((part, index) => ({
      ...part, color: "#234567", opacity: 0.4,
      material: index === 0 ? { roughness: 0.17, metalness: 0.83, clearcoat: 0.35, clearcoatRoughness: 0.12 } : null
    }));
    const scene = buildModel(THREE, source, {
      renderPartsIndividually: true,
      materialSettings: inspect.theme.materials,
      materialOverrides: inspect.materialOverrides
    });
    try {
      const record = scene.displayRecords[0];
      const authoredColor = record.material.color.clone();
      assert.equal(record.material.roughness, 0.17);
      assert.equal(record.material.metalness, 0.83);
      assert.equal(record.material.clearcoat, 0.35);
      assert.equal(record.material.clearcoatRoughness, 0.12);
      assert.equal(record.material.opacity, 0.4);
      assert.equal(scene.displayRecords[1].material.roughness, inspect.theme.materials.roughness);
      for (const apply of [applyPartVisualState, applyViewerPartVisualState]) {
        apply(THREE, scene.displayRecords, { selectedPartIds: [record.partId] });
        apply(THREE, scene.displayRecords, { selectedPartIds: [] });
        assert.equal(record.material.roughness, 0.17);
        assert.equal(record.material.metalness, 0.83);
        assert.equal(record.material.opacity, 0.4);
        assert.ok(record.material.color.equals(authoredColor));
      }
      scene.update({ source: { ...source } });
      assert.equal(scene.displayRecords[0].material.roughness, 0.17);
      assert.equal(scene.displayRecords[0].material.opacity, 0.4);
    } finally {
      scene.dispose();
    }
  }
});

test("explicit caller PBR overrides remain supported while scene values supply fallbacks", () => {
  const source = sampleMeshData();
  source.parts = source.parts.map((part, index) => ({
    ...part,
    material: index === 0 ? { roughness: 0.17, metalness: 0.83 } : null
  }));
  const materialSettings = {
    defaultColor: "#b6c4ce",
    roughness: 0.58,
    metalness: 0.04,
    clearcoat: 0.12,
    clearcoatRoughness: 0.35,
    opacity: 1
  };
  const authored = buildModel(THREE, source, { renderPartsIndividually: true, materialSettings });
  assert.equal(authored.displayRecords[0].material.roughness, 0.17);
  assert.equal(authored.displayRecords[0].material.metalness, 0.83);
  assert.equal(authored.displayRecords[1].material.roughness, 0.58);
  assert.equal(authored.displayRecords[1].material.metalness, 0.04);
  authored.dispose();

  const customized = buildModel(THREE, source, {
    renderPartsIndividually: true,
    materialSettings,
    materialOverrides: { roughness: 0.08, metalness: 0.92 }
  });
  for (const record of customized.displayRecords) {
    assert.equal(record.material.roughness, 0.08);
    assert.equal(record.material.metalness, 0.92);
  }
  customized.dispose();
});

test("mutable public mesh rows observe replacement parent geometry and topology", () => {
  const source = sampleMeshData();
  const scene = buildModel(THREE, source, { renderPartsIndividually: true });
  const firstRecord = scene.displayRecords[0];
  const vertices = new Float32Array(source.vertices);
  vertices[0] = 0.25;
  const indices = new Uint32Array(source.indices);
  [indices[0], indices[1]] = [indices[1], indices[0]];
  const replacement = { ...source, vertices, indices, parts: source.parts };
  scene.update({ source: replacement });
  assert.notEqual(scene.displayRecords[0], firstRecord, "same part objects do not prove immutable parent buffers");
  assert.equal(scene.displayRecords[0].geometry.attributes.position.array[0], 0.25);
  assert.deepEqual([...scene.displayRecords[0].geometry.index.array], [1, 0, 2]);
  scene.dispose();
});

test("in-place mutable settings changes are compared with the last applied snapshot", () => {
  const component = surfComponentMeshData();
  const descriptor = {
    kind: "assembly-package",
    entryKind: "assembly",
    components: { a: {} },
    occurrences: [{ id: "o1", component: "a", transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] }],
    assembly: { root: { id: "root", nodeType: "assembly", children: [{ id: "o1", nodeType: "part", children: [] }] } }
  };
  const materialSettings = { roughness: 0.22, metalness: 0.1, opacity: 1, defaultColor: "#445566" };
  const source = buildComposedPackageMeshData(descriptor, { a: component });
  const scene = buildModel(THREE, source, { renderPartsIndividually: true, materialSettings });
  const record = scene.displayRecords[0];
  assert.equal(record.material.roughness, 0.22);
  materialSettings.roughness = 0.81;
  materialSettings.defaultColor = "#bb6633";
  const retained = buildComposedPackageMeshData(structuredClone(descriptor), { a: component }, { previous: source });
  assert.equal(retained.parts[0], source.parts[0]);
  scene.update({ source: retained, materialSettings });
  assert.equal(scene.displayRecords[0], record);
  assert.equal(record.material.roughness, 0.81);
  assert.equal(record.material.color.getHexString(), "bb6633");
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

test("LOD publication preserves unaffected surface sets and retires only replaced geometry", () => {
  const componentA = surfComponentMeshData();
  const componentB = surfComponentMeshData();
  const order = [0, 1, 2, 3, 4, 5];
  const scene = buildModel(THREE, twoComponentPackage(componentA, componentB, order), { renderPartsIndividually: true });
  const a = scene.displayRecords[0];
  const aSet = a.surfaceInstance.set;
  const aCenter = a.partCenter;
  const bSet = scene.displayRecords[1].surfaceInstance.set;
  const aMatrix = aSet.object.instanceMatrix;
  let aDisposes = 0;
  let bDisposes = 0;
  aSet.object.addEventListener("dispose", () => { aDisposes += 1; });
  bSet.object.addEventListener("dispose", () => { bDisposes += 1; });
  const matrixVersion = aMatrix.version;

  for (let revision = 0; revision < 4; revision += 1) {
    const replacement = surfComponentMeshData();
    const next = twoComponentPackage(componentA, replacement, [...order].reverse());
    scene.update({ source: next });
    assert.deepEqual(scene.displayRecords.map((item) => item.partId), [...order].reverse().map((id) => `o${id}`));
    assert.equal(scene.displayRecords.find((item) => item.partId === "o0"), a);
    assert.equal(a.surfaceInstance.set, aSet);
    assert.equal(a.surfaceInstance.slot, 0, "unchanged occurrences keep their original slots despite source order");
    assert.equal(a.partCenter, aCenter, "adoption reuses the center vector");
    assert.equal(aSet.object.instanceMatrix, aMatrix);
    assert.equal(aMatrix.version, matrixVersion, "unchanged placements schedule no instance upload");
    assert.equal(aDisposes, 0);
    assert.equal(scene.runtime.cadSurfaceInstanceSets.size, 2);
    assert.equal(scene.displayRecords.find((item) => item.partId === "o1").geometry.attributes.position.array, replacement.vertices);
  }
  assert.equal(bDisposes, 1, "the departed LOD set is released once");
  assert.equal(bSet.disposed, true);
  scene.dispose();
  assert.equal(aDisposes, 1, "the retained set releases its buffers at final scene disposal");
});

test("selection slots remain inactive across source publications and reactivate without rebuilding", () => {
  const component = surfComponentMeshData();
  const scene = buildModel(THREE, composedPackage(component, 4), { renderPartsIndividually: true });
  const selected = scene.displayRecords[0];
  const { set, slot } = selected.surfaceInstance;
  scene.update({ selection: { selectedPartIds: [selected.partId] } });
  const zero = new THREE.Matrix4().makeScale(0, 0, 0);
  const actual = new THREE.Matrix4();
  for (let revision = 0; revision < 3; revision += 1) {
    const next = composedPackage(component, 4);
    next.parts[0].transform[3] = 40 + revision;
    scene.update({ source: next });
    assert.equal(selected.surfaceInstance.set, set);
    assert.equal(selected.material.visible, true);
    set.object.getMatrixAt(slot, actual);
    assert.deepEqual(actual.elements, zero.elements, "ordinary selection mesh has no duplicate instanced surface");
    assert.equal(selected.mesh.matrix.elements[12], 40 + revision);
  }
  scene.update({ selection: { selectedPartIds: [] } });
  assert.equal(selected.surfaceInstance.set, set);
  assert.equal(selected.material.visible, false);
  set.object.getMatrixAt(slot, actual);
  assert.deepEqual(actual.elements, selected.mesh.matrix.elements);
  scene.update({ selection: { hiddenPartIds: [selected.partId] } });
  scene.update({ source: composedPackage(component, 4) });
  assert.equal(selected.surfaceInstance.set, set);
  assert.equal(selected.material.transparent, true);
  assert.equal(selected.material.visible, true, "the existing hidden/dimmed state uses its ordinary pass");
  set.object.getMatrixAt(slot, actual);
  assert.deepEqual(actual.elements, zero.elements, "hidden part remains absent from the shared draw");
  scene.update({ selection: { hiddenPartIds: [] } });
  assert.equal(selected.surfaceInstance.set, set);
  assert.equal(selected.mesh.visible, true);
  scene.dispose();
});

test("a deformed occurrence leaves its surface slot inactive through progressive publications", () => {
  const component = surfComponentMeshData();
  const scene = buildModel(THREE, composedPackage(component, 4), { renderPartsIndividually: true });
  const bent = scene.displayRecords[0];
  const { set, slot } = bent.surfaceInstance;
  bent.gpuTubeDeformationAllowed = false;
  const spec = normalizeTubeDeformation({
    rest: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [3, 0, 0] }] },
    path: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 2], end: [0, 3, 2] }] },
    maxSegmentLength: 1000
  });
  applyRecordTubeDeformation(THREE, bent, spec);
  const privateGeometry = bent.geometry;
  const zero = new THREE.Matrix4().makeScale(0, 0, 0);
  const actual = new THREE.Matrix4();
  for (let revision = 0; revision < 3; revision += 1) {
    scene.update({ source: composedPackage(component, 4) });
    assert.equal(bent.surfaceInstance.set, set, "the other occurrences retain their shared draw");
    assert.equal(bent.geometry, privateGeometry);
    assert.equal(bent.material.visible, true);
    set.object.getMatrixAt(slot, actual);
    assert.deepEqual(actual.elements, zero.elements, "the rest surface cannot duplicate the private deformation");
    applyRecordTubeDeformation(THREE, bent, spec);
    applyDisplayRecordTransform(THREE, bent);
    set.object.getMatrixAt(slot, actual);
    assert.deepEqual(actual.elements, zero.elements);
  }
  scene.dispose();
});

test("source appearance and mirror changes invalidate only their surface pass membership", () => {
  const component = surfComponentMeshData();
  const scene = buildModel(THREE, composedPackage(component, 4), { renderPartsIndividually: true });
  const initialSet = scene.displayRecords[0].surfaceInstance.set;
  const next = composedPackage(component, 4);
  next.parts[0].material = { roughness: 0.123, metalness: 0.876 };
  next.parts[1].transform[0] = -1;
  scene.update({ source: next });
  assert.equal(initialSet.disposed, true, "a changed pass breaks compatibility");
  assert.equal(scene.displayRecords[0].material.roughness, 0.123);
  assert.equal(scene.displayRecords[0].material.metalness, 0.876);
  assert.equal(scene.displayRecords[0].surfaceInstance, null);
  assert.equal(scene.displayRecords[1].surfaceInstance, null, "mirrored placement uses the ordinary mesh");
  assert.equal(scene.displayRecords[1].mesh.matrix.determinant(), -1);
  assert.equal(scene.displayRecords[2].surfaceInstance.set, scene.displayRecords[3].surfaceInstance.set);
  assert.deepEqual(scene.displayRecords[2].surfaceInstance.set.object.userData.partIds, ["o2", "o3"]);
  scene.dispose();
});

test("direct viewer effects and clip passes synchronize shared surfaces without a source update", () => {
  const source = composedPackage(surfComponentMeshData(), 4);
  const theme = cloneThemePresetSettings("workbench-light");
  theme.materials.emissiveIntensity = 0;
  const scene = buildModel(THREE, source, { renderPartsIndividually: true, theme });
  const runtime = { ...scene.runtime, THREE, cadScene: scene };
  const record = scene.displayRecords[0];
  const { set, slot } = record.surfaceInstance;
  const matrix = new THREE.Matrix4();
  const zero = new THREE.Matrix4().makeScale(0, 0, 0);
  const pass = ({ visible = true, opacity = 1, color = "#123abc", mirror = false, selection = {}, deform = false } = {}) => {
    applySceneState(THREE, {
      runtime, meshData: source,
      stepParameterRuntime: { definition: { manifest: {}, module: { update(ctx) {
        ctx.effects.style("o0", { color });
        if (mirror) ctx.effects.transform("o0", { scale: [-1, 2, 1] });
      } } } },
      animation: { elapsedSec: 0, clip: { duration: 1, update(t, model) {
        const handle = model.get("o0").visible(visible).opacity(opacity).translate([4, 2, 1]);
        if (deform) handle.deformTube({
          rest: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [3, 0, 0] }] },
          path: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 2], end: [0, 3, 2] }] },
          maxSegmentLength: 1000
        });
      } } }
    });
    for (const item of runtime.displayRecords) applyDisplayRecordTransform(THREE, item);
    applyViewerPartVisualState(THREE, runtime.displayRecords, { showEdges: true, ...selection });
    scene.syncSurfaceInstances();
    assert.equal(record.surfaceInstance.set, set, "the unaffected majority and original slots survive direct passes");
    set.object.getMatrixAt(slot, matrix);
  };
  pass();
  assert.deepEqual(matrix.elements, record.mesh.matrix.elements);
  assert.equal(record.material.visible, false);
  const color = new THREE.Color();
  set.object.getColorAt(slot, color);
  assert.equal(color.getHexString(), "123abc", "pose color reaches the instance upload");
  for (const settings of [{ visible: false }, { opacity: 0.4 }, { mirror: true }, { selection: { selectedPartIds: ["o0"] } }, { selection: { hiddenPartIds: ["o0"] } }]) {
    pass(settings);
    assert.deepEqual(matrix.elements, zero.elements);
    assert.equal(record.material.visible, true);
    pass();
    assert.deepEqual(matrix.elements, record.mesh.matrix.elements, "reactivation uploads the current pose");
  }
  for (const item of runtime.displayRecords) {
    applyViewerMaterialSettings(THREE, item, { ...scene.runtime.materialSettings, envMapIntensity: 3.25 });
  }
  scene.syncSurfaceInstances();
  assert.equal(record.surfaceInstance.set, set);
  assert.equal(set.object.material.envMapIntensity, 3.25, "material-only reflection changes reach the shared pass");

  syncRuntimeStepClipPlane(runtime, { enabled: true, axis: "x", offsets: { x: 0.25 } });
  assert.equal(set.object.material.clippingPlanes.length, 1, "clip-only update reaches the shared draw");
  assert.equal(set.object.material.clippingPlanes[0].constant, record.material.clippingPlanes[0].constant);
  syncRuntimeStepClipPlane(runtime, { enabled: false });
  assert.equal(set.object.material.clippingPlanes, null);

  record.gpuTubeDeformationAllowed = false;
  pass({ deform: true });
  assert.ok(record.tubeDeformationState.active);
  assert.deepEqual(matrix.elements, zero.elements);
  assert.equal(record.material.visible, true);
  pass();
  assert.deepEqual(matrix.elements, zero.elements, "a previously bent record stays on its private geometry");
  scene.dispose();
  scene.syncSurfaceInstances();
  assert.equal(scene.runtime.cadSurfaceInstanceSets.size, 0, "late external sync cannot revive a disposed scene");
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

test("shared component GPU resources survive another scene's removal and disposal", () => {
  const componentA = surfComponentMeshData();
  const componentB = surfComponentMeshData();
  const source = twoComponentPackage(componentA, componentB, [0, 1, 3]);
  const first = buildModel(THREE, source, { renderPartsIndividually: true });
  const second = buildModel(THREE, source, { renderPartsIndividually: true });
  const geometry = first.displayRecords[1].geometry;
  const segments = first.displayRecords[1].edgeInstance.set.segments;
  assert.equal(second.displayRecords[1].geometry, geometry);
  assert.equal(second.displayRecords[1].edgeInstance.set.segments, segments);
  const bvh = geometry.boundsTree = { shared: true };
  let geometryDisposals = 0;
  let textureDisposals = 0;
  geometry.addEventListener("dispose", () => { geometryDisposals += 1; });
  segments.texture.addEventListener("dispose", () => { textureDisposals += 1; });

  first.update({ source: twoComponentPackage(componentA, componentB, [0]) });
  first.dispose();
  assert.equal(geometryDisposals, 0);
  assert.equal(textureDisposals, 0);
  assert.equal(geometry.boundsTree, bvh, "the second scene still owns its picking structure");
  assert.equal(second.displayRecords[1].edgeInstance.set.disposed, false);
  second.dispose();
  assert.equal(geometryDisposals, 1, "the last scene frees the shared upload once");
  assert.equal(textureDisposals, 1);
  assert.equal(geometry.boundsTree, null);
  second.dispose();
  assert.equal(geometryDisposals, 1);
});

test("shared wireframe geometry is freed only after its last scene, and retained uploads can be released later", () => {
  const component = surfComponentMeshData();
  const source = twoComponentPackage(component, component, [0, 1]);
  const settings = { renderPartsIndividually: true, displayMode: CAD_DISPLAY_MODE.WIREFRAME };
  const first = buildModel(THREE, source, settings);
  const second = buildModel(THREE, source, settings);
  const geometry = first.displayRecords[0].geometry;
  const edges = first.displayRecords[0].edges.geometry;
  assert.equal(second.displayRecords[0].edges.geometry, edges);
  let geometryDisposals = 0;
  let edgeDisposals = 0;
  geometry.addEventListener("dispose", () => { geometryDisposals += 1; });
  edges.addEventListener("dispose", () => { edgeDisposals += 1; });
  first.dispose();
  assert.equal(geometryDisposals, 0);
  assert.equal(edgeDisposals, 0);
  second.dispose({ releaseGpu: false });
  assert.equal(geometryDisposals, 0);
  assert.equal(edgeDisposals, 0);
  const replacement = buildModel(THREE, source, settings);
  replacement.dispose();
  assert.equal(geometryDisposals, 1);
  assert.equal(edgeDisposals, 1);
});

test("a deformed tube's private edges keep per-class thickness", () => {
  const sourceMesh = surfComponentMeshData();
  const meshData = {
    vertices: new Float32Array(0), indices: new Uint32Array(0),
    bounds: sourceMesh.bounds,
    parts: [{ id: "tube", sourceMeshKey: "tube", sourceMesh, vertexCount: 4, triangleCount: 2, bounds: sourceMesh.bounds }]
  };
  const scene = buildModel(THREE, meshData, {
    renderPartsIndividually: true,
    edgeRendering: { LineSegments2, LineSegmentsGeometry, LineMaterial },
    appearance: "light"
  });
  const record = scene.displayRecords[0];
  const set = record.edgeInstance.set;
  assert.equal(set.uniforms.cadClassWidth.value.x, 1, "instanced feature edges take the class width");
  record.gpuTubeDeformationAllowed = false;
  const rest = { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [3, 0, 0] }] };
  const path = { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 2], end: [0, 3, 2] }] };
  applyRecordTubeDeformation(THREE, record, normalizeTubeDeformation({ rest, path, maxSegmentLength: 1000 }));

  // The private draw is one screen-space fat line PER DRAWN CLASS, at that
  // class's width — the thing a single vertex-coloured GL_LINES cannot do.
  assert.equal(record.edgeInstance, null);
  assert.equal(record.edges.isGroup, true);
  assert.deepEqual(record.edges.children.map((line) => line instanceof LineSegments2), [true, true]);
  assert.deepEqual(record.edgeMaterials.map((material) => material.linewidth), [1, 0.65]);
  assert.ok(
    record.edgeMaterials.every((material) => scene.runtime.screenSpaceLineMaterials.has(material)),
    "both are resolution-synced with the viewport"
  );
  applyPartVisualState(THREE, [record], { edgeSettings: scene.runtime.edgeSettings });
  assert.deepEqual(record.edgeMaterials.map((material) => material.color.getHexString()), ["253443", "667788"], "ordinary visual updates preserve class colours");
  const privateGeometry = record.edges.children.map((line) => line.geometry);
  // Deformation moves the fat lines' own endpoint attributes.
  const bent = record.edges.children[0].geometry.attributes.instanceStart;
  assert.ok(bent, "screen-space geometry carries instanceStart/instanceEnd");
  assert.notDeepEqual(Array.from(bent.data.array).slice(0, 3), [0, 0, 0]);

  // Back at rest the private lines stay (see attachCadEdgeInstance: a publish
  // resets the pose, so rejoining there would rebuild them every publish) and
  // return to the component's own points at their class widths.
  applyRecordTubeDeformation(THREE, record, null);
  assert.equal(record.edges.isGroup, true);
  assert.deepEqual(record.edgeMaterials.map((material) => material.linewidth), [1, 0.65]);
  assert.deepEqual(Array.from(record.edges.children[0].geometry.attributes.instanceStart.data.array).slice(0, 3), [0, 0, 0]);
  scene.update({ appearance: "dark" });
  assert.deepEqual(record.edges.children.map((line) => line.geometry), privateGeometry);
  assert.deepEqual(record.edgeMaterials.map((material) => material.color.getHexString()), ["253443", "667788"]);
  scene.dispose();
});

test("failed surface-instance disposal retains reachability and retries only unfinished resources", () => {
  const component = surfComponentMeshData();
  const scene = buildModel(THREE, twoComponentPackage(component, component, [0, 1, 2]), { renderPartsIndividually: true });
  const set = [...scene.runtime.cadSurfaceInstanceSets][0];
  assert.ok(set);
  let objectDisposals = 0, materialDisposals = 0;
  set.object.addEventListener("dispose", () => { objectDisposals++; });
  const fail = () => { materialDisposals++; throw new Error("instance material cleanup"); };
  set.object.material.addEventListener("dispose", fail);
  assert.throws(() => scene.dispose(), /instance material cleanup/);
  assert.equal(set.disposed, false); assert.equal(set.object.parent, scene.modelGroup);
  assert.ok(set.records.every(record => record.surfaceInstance?.set === set));
  set.object.material.removeEventListener("dispose", fail);
  scene.dispose();
  assert.equal(objectDisposals, 1, "successful instance GPU disposal is not repeated");
  assert.equal(materialDisposals, 1); assert.equal(set.disposed, true); assert.equal(set.object.parent, null);
  assert.ok(set.records.every(record => !record.surfaceInstance));
  assert.equal(scene.runtime.ownedGeometries.size, 0);
});

test("failed edge-instance disposal retains its set and another scene's shared segment texture", () => {
  const component = surfComponentMeshData(), input = twoComponentPackage(component, component, [0, 1]);
  const scene = buildModel(THREE, input, { renderPartsIndividually: true });
  const other = buildModel(THREE, input, { renderPartsIndividually: true });
  const set = scene.displayRecords[0].edgeInstance.set;
  let textureDisposals = 0, instanceDisposals = 0;
  set.segments.texture.addEventListener("dispose", () => { textureDisposals++; });
  set.instanceTexture.addEventListener("dispose", () => { instanceDisposals++; });
  const fail = () => { throw new Error("edge material cleanup"); };
  set.material.addEventListener("dispose", fail);
  assert.throws(() => scene.dispose(), /edge material cleanup/);
  assert.equal(set.disposed, false); assert.equal(set.object.parent, scene.edgesGroup);
  assert.ok(scene.runtime.cadEdgeInstanceSets.has(set));
  set.material.removeEventListener("dispose", fail);
  scene.dispose(); assert.equal(instanceDisposals, 1); assert.equal(textureDisposals, 0);
  other.dispose(); assert.equal(textureDisposals, 1);
});

function rounded(values) {
  return Array.from(values).map((value) => {
    const roundedValue = Math.round(value * 1e6) / 1e6;
    return Object.is(roundedValue, -0) ? 0 : roundedValue;
  });
}

function robotLinkMesh() {
  return {
    vertices: new Float32Array([0, 0, 0, 0.01, 0, 0, 0, 0.01, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
    indices: new Uint32Array([0, 1, 2]),
    colors: new Float32Array(0),
    bounds: { min: [0, 0, 0], max: [0.01, 0.01, 0] }
  };
}

// Two links, one revolute joint about +Y, the child 60mm above the parent: the
// smallest robot whose pose is visible in a record matrix.
function shoulderRobot() {
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  return {
    rootLink: "base",
    rootWorldTransform: identity,
    links: [
      { name: "base", visuals: [{ id: "base:v1", label: "base", partFileRef: "base-part", localTransform: identity }] },
      { name: "arm", visuals: [{ id: "arm:v1", label: "arm", partFileRef: "arm-part", localTransform: identity }] }
    ],
    joints: [{
      name: "shoulder",
      type: "revolute",
      parentLink: "base",
      childLink: "arm",
      originTransform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0.06, 0, 0, 0, 1],
      axisInJointFrame: [0, 1, 0],
      defaultValueDeg: 0,
      minValueDeg: -90,
      maxValueDeg: 90
    }]
  };
}

test("a robot pose republished on the same source moves its records without rebuilding geometry", () => {
  const urdfData = shoulderRobot();
  const meshesByUrl = new Map([["base-part", robotLinkMesh()], ["arm-part", robotLinkMesh()]]);
  const meshData = buildUrdfMeshGeometry(urdfData, meshesByUrl, { lightweight: true });
  applyUrdfPoseToMeshData(urdfData, meshData, { shoulder: 0 });

  const scene = buildModel(THREE, meshData, { renderPartsIndividually: true });
  const armRecord = scene.displayRecords.find((record) => record.sourcePart?.linkName === "arm");
  const baseRecord = scene.displayRecords.find((record) => record.sourcePart?.linkName === "base");
  assert.ok(armRecord && baseRecord, "both links render as their own records");
  const armGeometry = armRecord.geometry;
  const restMatrix = new THREE.Matrix4().makeTranslation(0, 0, 0.06);
  assert.deepEqual(rounded(armRecord.mesh.matrix.elements), rounded(restMatrix.elements));

  applyUrdfPoseToMeshData(urdfData, meshData, { shoulder: 45 });
  scene.update({ source: meshData, renderPartsIndividually: true });

  const posedArm = scene.displayRecords.find((record) => record.sourcePart?.linkName === "arm");
  const expected = new THREE.Matrix4().makeTranslation(0, 0, 0.06)
    .multiply(new THREE.Matrix4().makeRotationY(Math.PI / 4));
  assert.deepEqual(rounded(posedArm.mesh.matrix.elements), rounded(expected.elements));
  assert.equal(posedArm.geometry, armGeometry, "posing reuses the uploaded link geometry");
  assert.deepEqual(
    rounded(scene.displayRecords.find((record) => record.sourcePart?.linkName === "base").mesh.matrix.elements),
    rounded(new THREE.Matrix4().elements),
    "the root link does not move"
  );
  scene.dispose();
});
