import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import { CAD_DISPLAY_MODE } from "../../common/displaySettings.js";
import {
  applyPartVisualState,
  getPartHighlightColors,
  normalizePartIdList,
  referenceMatchesFocusedPart
} from "./partVisualState.js";

const EPSILON = 1e-6;

function assertNear(actual, expected, message = "") {
  assert.ok(Math.abs(actual - expected) < EPSILON, `${message} expected ${expected}, received ${actual}`);
}

function createRecord(partId, {
  baseOpacity = 0.5,
  effectStyle = null,
  effectVisible = true
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
    baseEmissiveColor: new THREE.Color("#111111"),
    baseEmissiveIntensity: 0.2,
    effectStyle,
    effectVisible
  };
}

test("part visual helpers normalize focus ids and model-level references", () => {
  assert.deepEqual(normalizePartIdList([" a ", "", null, "b"]), ["a", "b"]);
  assert.deepEqual(normalizePartIdList(" part-a "), ["part-a"]);

  const focused = new Set(["part-a"]);
  assert.equal(referenceMatchesFocusedPart({ partId: "part-a" }, focused), true);
  assert.equal(referenceMatchesFocusedPart({ partId: "part-b" }, focused), false);
  assert.equal(referenceMatchesFocusedPart({}, new Set(["__model__"])), true);
  assert.equal(referenceMatchesFocusedPart({ partId: "part-a" }, new Set()), true);
});

test("part visual state applies hover and selected styling without changing visibility", () => {
  const hoverRecord = createRecord("hovered");
  const selectedRecord = createRecord("selected");
  applyPartVisualState(THREE, [hoverRecord, selectedRecord], {
    viewerTheme: {
      edge: "#111111",
      edgeOpacity: 0.4
    },
    edgeSettings: {
      color: "#333333",
      opacity: 0.4,
      highlightColor: "#8dc5ff",
      highlightOpacity: 0.9
    },
    hiddenPartIds: [],
    hoveredPartId: "hovered",
    focusedPartId: [],
    selectedPartIds: ["selected"],
    showEdges: true
  });

  const colors = getPartHighlightColors(THREE, {
    edgeSettings: {
      highlightColor: "#8dc5ff"
    }
  });
  assert.equal(hoverRecord.mesh.visible, true);
  assert.equal(hoverRecord.edges.visible, true);
  assert.equal(hoverRecord.material.transparent, true);
  assert.equal(hoverRecord.material.depthWrite, true);
  assert.equal(hoverRecord.mesh.renderOrder, 23);
  assert.equal(hoverRecord.edges.renderOrder, 26);
  assertNear(hoverRecord.material.opacity, 0.9, "hover opacity");
  assert.equal(hoverRecord.material.color.getHexString(), colors.hoveredSurfaceColor.getHexString());
  assert.equal(hoverRecord.material.emissive.getHexString(), colors.hoveredSurfaceColor.getHexString());
  assertNear(hoverRecord.material.emissiveIntensity, 0.12, "hover emissive");
  assert.equal(hoverRecord.edgeMaterial.color.getHexString(), colors.hoveredEdgeColor.getHexString());
  assertNear(hoverRecord.edgeMaterial.opacity, 0.9, "hover edge opacity");

  assertNear(selectedRecord.material.opacity, 0.9, "selected opacity");
  assert.equal(selectedRecord.material.transparent, true);
  assert.equal(selectedRecord.material.depthWrite, true);
  assert.equal(selectedRecord.mesh.renderOrder, 23);
  assert.equal(selectedRecord.edges.renderOrder, 26);
  assert.equal(selectedRecord.material.color.getHexString(), colors.selectedSurfaceColor.getHexString());
  assert.equal(selectedRecord.edgeMaterial.color.getHexString(), colors.selectedEdgeColor.getHexString());
  assertNear(selectedRecord.edgeMaterial.opacity, 0.9, "selected edge opacity");
});

test("part visual state highlights shader-rendered surface edges", () => {
  const record = createRecord("part", {
    baseOpacity: 1
  });
  record.material.userData.cadSurfaceEdges = true;
  record.material.userData.cadSurfaceEdgeBaseColor = new THREE.Color("#111111");
  record.material.userData.cadSurfaceEdgeColor = new THREE.Color("#111111");
  record.material.userData.cadSurfaceEdgeBaseClassSettings = {
    feature: { opacity: 0.25 },
    tangent: { opacity: 0.15 },
    seam: { opacity: 0.2 },
    degenerate: { opacity: 0.1 }
  };
  record.material.userData.cadSurfaceEdgeShader = {
    uniforms: {
      cadSurfaceEdgeColor: { value: new THREE.Color("#111111") },
      cadSurfaceFeatureOpacity: { value: 0.25 },
      cadSurfaceTangentOpacity: { value: 0.15 },
      cadSurfaceSeamOpacity: { value: 0.2 },
      cadSurfaceDegenerateOpacity: { value: 0.1 }
    }
  };

  applyPartVisualState(THREE, [record], {
    viewerTheme: {
      edge: "#111111",
      edgeOpacity: 0.4
    },
    edgeSettings: {
      highlightColor: "#8dc5ff",
      highlightOpacity: 0.9
    },
    hiddenPartIds: [],
    hoveredPartId: "",
    focusedPartId: [],
    selectedPartIds: ["part"],
    showEdges: true
  });

  assert.equal(record.material.userData.cadSurfaceEdgeShader.uniforms.cadSurfaceEdgeColor.value.getHexString(), "8dc5ff");
  assertNear(record.material.userData.cadSurfaceEdgeShader.uniforms.cadSurfaceFeatureOpacity.value, 0.9, "selected feature edge opacity");
  assertNear(record.material.userData.cadSurfaceEdgeShader.uniforms.cadSurfaceTangentOpacity.value, 0.9, "selected tangent edge opacity");

  applyPartVisualState(THREE, [record], {
    viewerTheme: {
      edge: "#111111",
      edgeOpacity: 0.4
    },
    edgeSettings: {
      highlightColor: "#8dc5ff",
      highlightOpacity: 0.9
    },
    hiddenPartIds: [],
    hoveredPartId: "",
    focusedPartId: [],
    selectedPartIds: [],
    showEdges: true
  });

  assert.equal(record.material.userData.cadSurfaceEdgeShader.uniforms.cadSurfaceEdgeColor.value.getHexString(), "111111");
  assertNear(record.material.userData.cadSurfaceEdgeShader.uniforms.cadSurfaceFeatureOpacity.value, 0.25, "restored feature edge opacity");
  assertNear(record.material.userData.cadSurfaceEdgeShader.uniforms.cadSurfaceTangentOpacity.value, 0.15, "restored tangent edge opacity");
});

test("part visual state hides hidden records and ghosts dimmed records", () => {
  const hiddenRecord = createRecord("hidden");
  const dimmedRecord = createRecord("dimmed", {
    baseOpacity: 0.8,
    effectStyle: {
      edgeOpacity: 0.5
    }
  });
  applyPartVisualState(THREE, [hiddenRecord, dimmedRecord], {
    viewerTheme: {
      edge: "#111111",
      edgeOpacity: 0.5
    },
    edgeSettings: {
      opacity: 0.5
    },
    hiddenPartIds: ["hidden"],
    hoveredPartId: "",
    focusedPartId: ["focused"],
    selectedPartIds: [],
    showEdges: true
  });

  assert.equal(hiddenRecord.mesh.visible, false);
  assert.equal(hiddenRecord.edges.visible, false);
  assert.equal(hiddenRecord.material.transparent, true);
  assert.equal(hiddenRecord.material.depthWrite, false);
  assert.equal(hiddenRecord.mesh.renderOrder, 2);
  assert.equal(hiddenRecord.edges.renderOrder, 3);
  assertNear(hiddenRecord.material.opacity, 0, "hidden opacity");
  assertNear(hiddenRecord.edgeMaterial.opacity, 0, "hidden edge opacity");
  assert.equal(dimmedRecord.mesh.visible, true);
  assert.equal(dimmedRecord.edges.visible, true);
  assert.equal(dimmedRecord.material.transparent, true);
  assert.equal(dimmedRecord.material.depthWrite, false);
  assert.equal(dimmedRecord.mesh.renderOrder, 2);
  assert.equal(dimmedRecord.edges.renderOrder, 3);
  assertNear(dimmedRecord.material.opacity, 0.035, "dimmed opacity");
  assertNear(dimmedRecord.edgeMaterial.opacity, 0.035, "dimmed edge opacity");
});

test("part visual state restores depth and render order after highlight", () => {
  const record = createRecord("part", {
    baseOpacity: 1
  });
  applyPartVisualState(THREE, [record], {
    viewerTheme: {},
    edgeSettings: {},
    hiddenPartIds: [],
    hoveredPartId: "part",
    focusedPartId: [],
    selectedPartIds: [],
    showEdges: true
  });

  assert.equal(record.material.transparent, true);
  assert.equal(record.material.depthWrite, true);
  assert.equal(record.mesh.renderOrder, 23);
  assert.equal(record.edges.renderOrder, 26);

  applyPartVisualState(THREE, [record], {
    viewerTheme: {},
    edgeSettings: {},
    hiddenPartIds: [],
    hoveredPartId: "",
    focusedPartId: [],
    selectedPartIds: [],
    showEdges: true
  });

  assert.equal(record.material.transparent, false);
  assert.equal(record.material.depthWrite, true);
  assert.equal(record.mesh.renderOrder, 2);
  assert.equal(record.edges.renderOrder, 3);
});

test("part visual state keeps selected x-ray surfaces translucent", () => {
  const selectedRecord = createRecord("selected", {
    baseOpacity: 0.22
  });
  selectedRecord.material.depthWrite = false;
  selectedRecord.baseDepthWrite = true;
  const hoveredRecord = createRecord("hovered", {
    baseOpacity: 0.22
  });
  hoveredRecord.material.depthWrite = false;
  hoveredRecord.baseDepthWrite = true;

  applyPartVisualState(THREE, [selectedRecord, hoveredRecord], {
    viewerTheme: {
      edge: "#111111",
      edgeOpacity: 0.4
    },
    edgeSettings: {
      highlightColor: "#8dc5ff",
      highlightOpacity: 0.9
    },
    hiddenPartIds: [],
    hoveredPartId: "hovered",
    focusedPartId: [],
    selectedPartIds: ["selected"],
    showEdges: true,
    displayMode: CAD_DISPLAY_MODE.TRANSPARENT
  });

  assertNear(selectedRecord.material.opacity, 0.34, "selected x-ray opacity");
  assert.equal(selectedRecord.material.transparent, true);
  assert.equal(selectedRecord.material.depthWrite, false);
  assertNear(hoveredRecord.material.opacity, 0.3, "hovered x-ray opacity");
  assert.equal(hoveredRecord.material.transparent, true);
  assert.equal(hoveredRecord.material.depthWrite, false);
});
