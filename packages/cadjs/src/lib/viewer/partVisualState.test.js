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
import {
  PART_HOVER_EDGE_EMPHASIS,
  PART_HOVER_EMISSIVE_INTENSITY,
  PART_HOVER_HIGHLIGHT_BLEND,
  PART_SELECTED_EMISSIVE_INTENSITY,
  PART_SELECTED_HIGHLIGHT_BLEND,
  partHighlightSurfaceColor
} from "./partHighlight.js";

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
  assert.equal(referenceMatchesFocusedPart({ partId: "part-a.child" }, focused), true);
  assert.equal(referenceMatchesFocusedPart({}, new Set(["__model__"])), true);
  assert.equal(referenceMatchesFocusedPart({ partId: "part-a" }, new Set()), true);
});

test("part visual state matches focused assembly ids against descendant records", () => {
  const focusedChild = createRecord("o1.4.1", { baseOpacity: 0.8 });
  const dimmedSibling = createRecord("o1.5", { baseOpacity: 0.8 });

  applyPartVisualState(THREE, [focusedChild, dimmedSibling], {
    viewerTheme: {
      edge: "#111111",
      edgeOpacity: 0.5
    },
    edgeSettings: {
      opacity: 0.5
    },
    hiddenPartIds: [],
    hoveredPartId: "",
    focusedPartId: ["o1.4"],
    selectedPartIds: [],
    showEdges: true
  });

  assertNear(focusedChild.material.opacity, 0.8, "focused descendant opacity");
  assertNear(focusedChild.edgeMaterial.opacity, 0.5, "focused descendant edge opacity");
  assertNear(dimmedSibling.material.opacity, 0.035, "unfocused sibling opacity");
  assertNear(dimmedSibling.edgeMaterial.opacity, 0.035, "unfocused sibling edge opacity");
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
  assert.equal(
    hoverRecord.material.color.getHexString(),
    partHighlightSurfaceColor(
      THREE,
      new THREE.Color("#aaaaaa"),
      colors.hoveredSurfaceColor,
      PART_HOVER_HIGHLIGHT_BLEND
    ).getHexString()
  );
  assert.equal(hoverRecord.material.emissive.getHexString(), colors.hoveredSurfaceColor.getHexString());
  assertNear(hoverRecord.material.emissiveIntensity, PART_HOVER_EMISSIVE_INTENSITY, "hover emissive");
  assert.equal(hoverRecord.edgeMaterial.color.getHexString(), colors.hoveredEdgeColor.getHexString());
  // Hover keeps a lighter outline than selection.
  assertNear(hoverRecord.edgeMaterial.opacity, 0.9 * PART_HOVER_EDGE_EMPHASIS, "hover edge opacity");
  assert.equal(hoverRecord.ghostMesh, undefined, "hover never builds an occlusion ghost");

  assertNear(selectedRecord.material.opacity, 0.9, "selected opacity");
  assert.equal(selectedRecord.material.transparent, true);
  assert.equal(selectedRecord.material.depthWrite, true);
  assert.equal(selectedRecord.mesh.renderOrder, 23);
  assert.equal(selectedRecord.edges.renderOrder, 26);
  // The surface blends toward the highlight color so the part stays
  // recognizable; edges and emissive keep the full highlight color.
  assert.equal(
    selectedRecord.material.color.getHexString(),
    partHighlightSurfaceColor(
      THREE,
      new THREE.Color("#aaaaaa"),
      colors.selectedSurfaceColor,
      PART_SELECTED_HIGHLIGHT_BLEND
    ).getHexString()
  );
  assert.notEqual(selectedRecord.material.color.getHexString(), "aaaaaa");
  assert.equal(selectedRecord.material.emissive.getHexString(), colors.selectedSurfaceColor.getHexString());
  assertNear(selectedRecord.material.emissiveIntensity, PART_SELECTED_EMISSIVE_INTENSITY, "selected emissive");
  assert.equal(selectedRecord.edgeMaterial.color.getHexString(), colors.selectedEdgeColor.getHexString());
  assertNear(selectedRecord.edgeMaterial.opacity, 0.9, "selected edge opacity");

  // Selection must read stronger than hover on every axis, or "about to pick"
  // and "already picked" are indistinguishable.
  assert.ok(
    selectedRecord.material.emissiveIntensity > hoverRecord.material.emissiveIntensity,
    "selection should glow more than hover"
  );
  assert.ok(
    selectedRecord.edgeMaterial.opacity > hoverRecord.edgeMaterial.opacity,
    "selection should outline harder than hover"
  );
});

test("hover and selection use distinct colors", () => {
  const colors = getPartHighlightColors(THREE, { edgeSettings: { highlightColor: "#4f9dff" } });
  assert.notEqual(
    colors.hoveredSurfaceColor.getHexString(),
    colors.selectedSurfaceColor.getHexString(),
    "hover and selection must be separate colors, not two strengths of one"
  );
  // A theme can override either independently.
  const themed = getPartHighlightColors(THREE, {
    edgeSettings: { highlightColor: "#ff0000", hoverColor: "#00ff00" }
  });
  assert.equal(themed.selectedSurfaceColor.getHexString(), "ff0000");
  assert.equal(themed.hoveredEdgeColor.getHexString(), "00ff00");
});

test("hovering an already-selected part keeps the selected treatment", () => {
  const record = createRecord("part");
  const children = [];
  record.mesh = { visible: true, renderOrder: 2, add: (child) => children.push(child) };
  record.geometry = new THREE.BufferGeometry();

  applyPartVisualState(THREE, [record], {
    viewerTheme: { edge: "#111111", edgeOpacity: 0.4 },
    edgeSettings: { highlightColor: "#4f9dff", highlightOpacity: 0.9 },
    hiddenPartIds: [],
    hoveredPartId: "part",
    focusedPartId: [],
    selectedPartIds: ["part"],
    showEdges: true
  });

  const colors = getPartHighlightColors(THREE, { edgeSettings: { highlightColor: "#4f9dff" } });
  assert.equal(record.material.emissive.getHexString(), colors.selectedSurfaceColor.getHexString());
  assertNear(record.material.emissiveIntensity, PART_SELECTED_EMISSIVE_INTENSITY, "selected emissive wins");
  assertNear(record.edgeMaterial.opacity, 0.9, "selected edge opacity wins");
  assert.ok(record.ghostMesh?.visible, "a hovered selection still ghosts");
});

test("part highlight surface color blends the part color toward the highlight color", () => {
  const base = new THREE.Color("#c05ac8");
  const highlight = new THREE.Color("#4f9dff");

  const selected = partHighlightSurfaceColor(THREE, base, highlight, PART_SELECTED_HIGHLIGHT_BLEND);
  const hovered = partHighlightSurfaceColor(THREE, base, highlight, PART_HOVER_HIGHLIGHT_BLEND);

  // A saturated part must still shift visibly; the pre-fix tone-shift left
  // already-saturated colors essentially unchanged.
  assert.notEqual(selected.getHexString(), base.getHexString());
  assert.ok(
    selected.b - base.b > 0.1,
    `selected highlight should pull toward the highlight hue, got ${selected.getHexString()}`
  );
  // Hover is a weaker cue than selection.
  assert.ok(hovered.b < selected.b, "hover blend should be weaker than selected blend");
  // Parts with no base color (reference geometry) fall back to the flat color.
  assert.equal(partHighlightSurfaceColor(THREE, null, highlight, 0.5), highlight);
});

test("occlusion ghost is built lazily and only while the part is selected", () => {
  const record = createRecord("selected");
  const children = [];
  record.mesh = {
    visible: true,
    renderOrder: 2,
    add: (child) => children.push(child)
  };
  record.geometry = new THREE.BufferGeometry();
  record.material.clippingPlanes = [new THREE.Plane()];

  const state = (selectedPartIds) => ({
    viewerTheme: { edge: "#111111", edgeOpacity: 0.4 },
    edgeSettings: { color: "#333333", opacity: 0.4, highlightColor: "#8dc5ff", highlightOpacity: 0.9 },
    hiddenPartIds: [],
    hoveredPartId: null,
    focusedPartId: [],
    selectedPartIds,
    showEdges: true
  });

  // Unselected parts must not allocate a ghost mesh at all.
  applyPartVisualState(THREE, [record], state([]));
  assert.equal(record.ghostMesh, undefined);
  assert.equal(children.length, 0);

  applyPartVisualState(THREE, [record], state(["selected"]));
  assert.ok(record.ghostMesh, "ghost mesh is created on selection");
  assert.equal(children.length, 1);
  assert.equal(record.ghostMesh.visible, true);
  assert.equal(record.ghostMesh.userData.isOcclusionGhost, true);
  assert.equal(record.ghostMesh.castShadow, false);
  assert.equal(record.ghostMaterial.depthFunc, THREE.GreaterDepth);
  assert.equal(record.ghostMaterial.depthWrite, false);
  assert.equal(record.ghostMaterial.side, THREE.FrontSide);
  // The ghost must honor the section clip planes the surface is using.
  assert.equal(record.ghostMaterial.clippingPlanes, record.material.clippingPlanes);
  assert.equal(record.ghostMaterial.color.getHexString(), "8dc5ff");

  // Deselecting hides the existing ghost without building a second one.
  applyPartVisualState(THREE, [record], state([]));
  assert.equal(record.ghostMesh.visible, false);
  assert.equal(children.length, 1);
});

test("part visual state highlights shader-rendered surface edges", () => {
  const record = createRecord("part", {
    baseOpacity: 1
  });
  record.material.userData.cadSurfaceEdges = true;
  record.material.userData.cadSurfaceEdgeBaseColor = new THREE.Color("#111111");
  record.material.userData.cadSurfaceEdgeColor = new THREE.Color("#111111");
  record.material.userData.cadSurfaceEdgeBaseClassSettings = {
    feature: { color: "#111111", opacity: 0.25 },
    tangent: { color: "#224466", opacity: 0.15 },
    seam: { color: "#335577", opacity: 0.2 },
    degenerate: { color: "#446688", opacity: 0.1 }
  };
  record.material.userData.cadSurfaceEdgeShader = {
    uniforms: {
      cadSurfaceEdgeColor: { value: new THREE.Color("#111111") },
      cadSurfaceFeatureColor: { value: new THREE.Color("#111111") },
      cadSurfaceTangentColor: { value: new THREE.Color("#224466") },
      cadSurfaceSeamColor: { value: new THREE.Color("#335577") },
      cadSurfaceDegenerateColor: { value: new THREE.Color("#446688") },
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
  assert.equal(record.material.userData.cadSurfaceEdgeShader.uniforms.cadSurfaceFeatureColor.value.getHexString(), "8dc5ff");
  assert.equal(record.material.userData.cadSurfaceEdgeShader.uniforms.cadSurfaceTangentColor.value.getHexString(), "8dc5ff");
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
  assert.equal(record.material.userData.cadSurfaceEdgeShader.uniforms.cadSurfaceFeatureColor.value.getHexString(), "111111");
  assert.equal(record.material.userData.cadSurfaceEdgeShader.uniforms.cadSurfaceTangentColor.value.getHexString(), "224466");
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
