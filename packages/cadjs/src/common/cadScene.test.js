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
  cloneThemeSettings
} from "./themeSettings.js";

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
    edgeMaterial,
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

test("buildModel renders solid part records and updates theme without rebuilding geometry", () => {
  const theme = cloneThemeSettings("workbench");
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

test("buildModel selection can focus and hide subassembly occurrence descendants", () => {
  const focused = buildModel(THREE, nestedAssemblyMeshData(), {
    theme: cloneThemeSettings("workbench"),
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
    theme: cloneThemeSettings("workbench"),
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

test("buildModel renders STEP surface-owned edges from mesh attributes without line objects", () => {
  const meshData = sampleMeshData();
  meshData.surfaceEdgeBarycentric = new Float32Array([
    1, 0, 0,
    0, 1, 0,
    0, 0, 1,
    1, 0, 0,
    0, 1, 0,
    0, 0, 1
  ]);
  meshData.surfaceEdgeClass = new Uint8Array([
    1, 1, 0,
    1, 1, 0,
    1, 1, 0,
    2, 3, 0,
    2, 3, 0,
    2, 3, 0
  ]);
  const scene = buildModel(THREE, meshData, {
    theme: cloneThemeSettings("workbench"),
    displayMode: CAD_DISPLAY_MODE.SOLID,
    renderPartsIndividually: true
  });

  assert.equal(scene.displayRecords.length, 2);
  assert.equal(scene.edgesGroup.children.length, 0);
  assert.equal(scene.displayRecords[0].edges, null);
  assert.equal(scene.displayRecords[0].material.userData.cadSurfaceEdges, true);
  assert.equal(scene.displayRecords[0].material.polygonOffset, false);
  assert.equal(scene.displayRecords[0].geometry.getAttribute("_cad_edge_barycentric").count, 3);
  assert.equal(scene.displayRecords[0].geometry.getAttribute("_cad_edge_class").count, 3);
  scene.dispose();
});

test("buildModel rebuilds surface edge shader materials when edge theme settings change", () => {
  const meshData = sampleMeshData();
  meshData.surfaceEdgeBarycentric = new Float32Array([
    1, 0, 0,
    0, 1, 0,
    0, 0, 1,
    1, 0, 0,
    0, 1, 0,
    0, 0, 1
  ]);
  meshData.surfaceEdgeClass = new Uint8Array([
    1, 2, 0,
    1, 2, 0,
    1, 2, 0,
    1, 2, 0,
    1, 2, 0,
    1, 2, 0
  ]);
  const theme = cloneThemeSettings("workbench");
  const scene = buildModel(THREE, meshData, {
    theme,
    displayMode: CAD_DISPLAY_MODE.SOLID,
    renderPartsIndividually: true
  });
  const originalMaterial = scene.displayRecords[0].material;

  scene.update({
    displayMode: CAD_DISPLAY_MODE.SOLID,
    theme: {
      ...theme,
      edges: {
        ...theme.edges,
        color: "#0055ff",
        classes: {
          ...theme.edges.classes,
          tangent: {
            ...theme.edges.classes.tangent,
            thickness: 2.5
          }
        }
      }
    }
  });

  assert.notEqual(scene.displayRecords[0].material, originalMaterial);
  assert.equal(scene.displayRecords[0].material.userData.cadSurfaceEdges, true);
  assert.equal(scene.edgesGroup.children.length, 0);
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
    theme: cloneThemeSettings("workbench"),
    renderPartsIndividually: true
  });
  const firstGeometry = scene.displayRecords[0].mesh.geometry;
  const movedScene = buildModel(THREE, movedMeshData, {
    theme: cloneThemeSettings("workbench"),
    renderPartsIndividually: true
  });

  assert.equal(movedScene.displayRecords[0].mesh.geometry, firstGeometry);
  scene.dispose();
  movedScene.dispose();
});

test("buildModel wireframe mode keeps a translucent surface and wire edges", () => {
  const theme = cloneThemeSettings("workbench");
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
  const theme = cloneThemeSettings("workbench");
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
  assert.equal(transparentScene.displayRecords[0].edgeMaterial.depthTest, false);

  const hiddenEdgeScene = buildModel(THREE, sampleMeshData(), {
    theme,
    displayMode: CAD_DISPLAY_MODE.HIDDEN_EDGES,
    renderPartsIndividually: true
  });
  assert.equal(hiddenEdgeScene.displayRecords[0].material.opacity, 1);
  assert.equal(hiddenEdgeScene.displayRecords[0].edgeMaterial.depthTest, false);

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

test("buildModel ignores deprecated mesh edge detail and keeps wireframe all-edge mode", () => {
  const baseTheme = cloneThemeSettings("workbench");
  const deprecatedDetailScene = buildModel(THREE, squareMeshData(), {
    theme: {
      ...baseTheme,
      edges: {
        ...baseTheme.edges,
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
    theme: cloneThemeSettings("workbench"),
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
  const theme = cloneThemeSettings("workbench");
  const scene = buildModel(THREE, sampleMeshData(), {
    theme: {
      ...theme,
      edges: {
        ...theme.edges,
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
    theme: cloneThemeSettings("workbench"),
    renderPartsIndividually: true,
    selection: {
      selectedPartIds: ["left"],
      hiddenPartIds: ["right"]
    },
    clip: {
      enabled: true,
      axis: "x",
      offset: 0.5
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
    theme: cloneThemeSettings("workbench"),
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
