import { useEffect, useRef } from "react";
import { createScreenSpaceLineSegments, topologyLineDepthBiasForWidth } from "@hardcore/core/common/renderEdges.js";
import { STEP_TREE_TOPOLOGY_NODE_PREFIX } from "@hardcore/core/lib/step/stepTree.js";
import {
  buildEdgeLinePositionsFromProxy, buildFaceBoundaryLinePositions, buildFaceFillGeometryFromDisplayMeshes,
  buildFaceFillGeometryFromProxy, buildVertexMarkerMesh, referenceExplodedViewMatrix, REFERENCE_CORNER_COLOR
} from "@hardcore/core/lib/viewer/referenceGeometry.js";
import { clearOverlayGroup, getHighlightEdgeColor, getHighlightEdgeOpacity, getHighlightEdgeThickness } from "./useStepDisplay.js";

function referenceSelectorType(reference) {
  return String(reference?.selectorType || "").trim();
}

function referenceOccurrenceSelector(reference) {
  const selectorType = referenceSelectorType(reference);
  if (selectorType === "occurrence") {
    return String(reference?.normalizedSelector || reference?.displaySelector || "").trim();
  }
  return String(reference?.occurrenceId || "").trim();
}

function referenceMatchesOccurrenceSubtree(reference, occurrenceSelector) {
  const candidate = referenceOccurrenceSelector(reference);
  const selector = String(occurrenceSelector || "").trim();
  return Boolean(candidate && selector && (candidate === selector || candidate.startsWith(`${selector}.`)));
}

function referenceShapeSelector(reference) {
  const selectorType = referenceSelectorType(reference);
  if (selectorType === "shape") {
    return String(reference?.normalizedSelector || reference?.displaySelector || "").trim();
  }
  return String(reference?.shapeId || "").trim();
}

function referenceMatchesShape(reference, shapeSelector, occurrenceSelector = "") {
  const candidate = referenceShapeSelector(reference);
  const selector = String(shapeSelector || "").trim();
  if (!candidate || !selector || candidate !== selector) {
    return false;
  }
  const occurrence = String(occurrenceSelector || "").trim();
  return !occurrence || referenceMatchesOccurrenceSubtree(reference, occurrence);
}

function syntheticOccurrenceSelectorFromReferenceId(referenceId) {
  const normalizedReferenceId = String(referenceId || "").trim();
  if (!normalizedReferenceId.startsWith(STEP_TREE_TOPOLOGY_NODE_PREFIX)) {
    return "";
  }
  const body = normalizedReferenceId.slice(STEP_TREE_TOPOLOGY_NODE_PREFIX.length);
  const marker = ":occurrence:";
  const markerIndex = body.lastIndexOf(marker);
  return markerIndex >= 0 ? body.slice(markerIndex + marker.length).trim() : "";
}

/**
 * Every face, edge and vertex a set of highlighted references lights, in the order they were
 * named: a face, edge or vertex lights itself; an occurrence or a shape (or a Features row's
 * synthetic occurrence) lights everything of it.
 */
function expandHighlightReferenceIds(referenceIds, pickableReferenceMap, activeSelectorRuntime) {
  const expanded = new Set();
  const runtimeReferences = Array.isArray(activeSelectorRuntime?.references)
    ? activeSelectorRuntime.references
    : activeSelectorRuntime?.referenceMap instanceof Map
      ? [...activeSelectorRuntime.referenceMap.values()]
      : [];
  const add = (referenceId) => {
    const normalizedReferenceId = String(referenceId || "").trim();
    if (normalizedReferenceId) expanded.add(normalizedReferenceId);
  };
  const addChildren = (matches) => {
    for (const childReference of runtimeReferences) {
      const childSelectorType = referenceSelectorType(childReference);
      if ((childSelectorType === "face" || childSelectorType === "edge" || childSelectorType === "vertex") && matches(childReference)) {
        add(childReference?.id);
      }
    }
  };
  for (const referenceId of referenceIds) {
    const normalizedReferenceId = String(referenceId || "").trim();
    const topologyReference = pickableReferenceMap.get(normalizedReferenceId) || activeSelectorRuntime?.referenceMap?.get(normalizedReferenceId) || null;
    if (!topologyReference) {
      const syntheticOccurrenceSelector = syntheticOccurrenceSelectorFromReferenceId(normalizedReferenceId);
      if (syntheticOccurrenceSelector) {
        addChildren(childReference => referenceMatchesOccurrenceSubtree(childReference, syntheticOccurrenceSelector));
      }
      continue;
    }
    const selectorType = referenceSelectorType(topologyReference);
    if (selectorType === "occurrence") {
      const occurrenceSelector = referenceOccurrenceSelector(topologyReference);
      addChildren(childReference => referenceMatchesOccurrenceSubtree(childReference, occurrenceSelector));
      continue;
    }
    if (selectorType === "shape") {
      const shapeSelector = referenceShapeSelector(topologyReference);
      const occurrenceSelector = referenceOccurrenceSelector(topologyReference);
      addChildren(childReference => referenceMatchesShape(childReference, shapeSelector, occurrenceSelector));
      continue;
    }
    add(normalizedReferenceId);
  }
  return expanded;
}

/**
 * The two parents every reference highlight hangs in, made once per runtime: the boundary
 * lines in the edge layer and the fills in this scene's own overlay root. The fill is drawn
 * WITH the surfaces, so it hangs in this scene's own overlay root rather than in the viewport's
 * model group: what STEP draws, STEP owns and STEP clears (`stepScene.js`). Each holds one
 * child group per layer -- the selection, the hover -- with its parent's render order, so the
 * two layers sort as one.
 */
function highlightLayerGroups(runtime, stepScene, layer) {
  const { THREE, edgesGroup } = runtime;
  if (!runtime.referenceHighlightGroup || runtime.referenceHighlightGroup.parent !== edgesGroup) {
    runtime.referenceHighlightGroup = new THREE.Group();
    runtime.referenceHighlightGroup.renderOrder = 25;
    edgesGroup.add(runtime.referenceHighlightGroup);
  }
  const overlayRoot = stepScene.overlayObject3D;
  if (!runtime.referenceFaceFillGroup || runtime.referenceFaceFillGroup.parent !== overlayRoot) {
    runtime.referenceFaceFillGroup = new THREE.Group();
    runtime.referenceFaceFillGroup.renderOrder = 24;
    overlayRoot.add(runtime.referenceFaceFillGroup);
  }
  const child = (parent, key) => {
    let group = parent.children.find(candidate => candidate.userData?.referenceHighlightLayer === key);
    if (!group) {
      group = new THREE.Group();
      group.renderOrder = parent.renderOrder;
      group.userData.referenceHighlightLayer = key;
      group.visible = false;
      parent.add(group);
    }
    return group;
  };
  return { lines: child(runtime.referenceHighlightGroup, layer), fills: child(runtime.referenceFaceFillGroup, layer) };
}

function syncHighlightGroupVisibility(runtime) {
  for (const parent of [runtime.referenceHighlightGroup, runtime.referenceFaceFillGroup]) {
    if (!parent) continue;
    for (const group of parent.children) group.visible = group.children.length > 0;
    parent.visible = parent.children.some(group => group.children.length > 0);
  }
}

/**
 * The drawn objects of ONE face, edge or vertex, into `groups`, returned so a layer can find
 * them again. `hovered` is the hover's style: the marker a shade stronger and, while
 * measuring, the lines and fill faint enough not to compete with the rulers.
 */
function addReferenceHighlight(runtime, groups, activeSelectorRuntime, topologyReference, style, hovered) {
  const { THREE } = runtime;
  const objects = [];
  const selectorType = referenceSelectorType(topologyReference);
  if (selectorType === "vertex") {
    const marker = buildVertexMarkerMesh(runtime, THREE, topologyReference, {
      color: REFERENCE_CORNER_COLOR,
      opacity: hovered ? 0.96 : 0.88,
    });
    if (marker) {
      groups.lines.add(marker);
      objects.push(marker);
    }
    return objects;
  }

  const highlightColor = style.color;
  const opacity = hovered ? style.hoverOpacity : style.opacity;
  const linePositions = selectorType === "edge"
    ? buildEdgeLinePositionsFromProxy(activeSelectorRuntime, topologyReference)
    : buildFaceBoundaryLinePositions(activeSelectorRuntime, topologyReference);
  if (linePositions?.length) {
    const referenceVisibilityClass = selectorType === "edge"
      ? activeSelectorRuntime?.edges?.[topologyReference.rowIndex]?.visibilityClass || ""
      : "";
    const lineWidth = style.lineWidth;
    const line = createScreenSpaceLineSegments(runtime, linePositions, {
      color: highlightColor,
      opacity,
      lineWidth,
      renderOrder: 26,
      depthTest: selectorType !== "edge",
      depthWrite: false,
      depthBias: topologyLineDepthBiasForWidth(lineWidth, { visibilityClass: referenceVisibilityClass })
    });
    if (line) {
      // The pick proxy these positions come from is world-at-rest; the exploded view moves
      // the MESH and leaves the proxy alone, so without this the highlight for an exploded
      // part draws where the part sits when collapsed. The face fill below needs no such
      // matrix -- it is rebuilt from the live meshes, which already carry the offset.
      const explodeMatrix = referenceExplodedViewMatrix(runtime, topologyReference);
      if (explodeMatrix) {
        line.matrixAutoUpdate = false;
        line.matrix.copy(explodeMatrix);
        line.matrixWorldNeedsUpdate = true;
      }
      groups.lines.add(line);
      objects.push(line);
    }
  }

  if (selectorType === "face") {
    const fillGeometry = buildFaceFillGeometryFromDisplayMeshes(runtime, THREE, topologyReference) ||
      buildFaceFillGeometryFromProxy(runtime, THREE, activeSelectorRuntime, topologyReference);
    if (fillGeometry) {
      const fillMaterial = new THREE.MeshBasicMaterial({
        color: highlightColor,
        transparent: opacity < 0.999,
        opacity,
        depthTest: true,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -2,
        polygonOffsetUnits: -2,
        side: THREE.DoubleSide,
        toneMapped: false
      });
      const fillMesh = new THREE.Mesh(fillGeometry, fillMaterial);
      fillMesh.renderOrder = 25;
      groups.fills.add(fillMesh);
      objects.push(fillMesh);
    }
  }
  return objects;
}

function highlightableReference(referenceId, pickableReferenceMap, activeSelectorRuntime) {
  const topologyReference = pickableReferenceMap.get(referenceId) || activeSelectorRuntime?.referenceMap?.get(referenceId) || null;
  const selectorType = referenceSelectorType(topologyReference);
  return selectorType === "face" || selectorType === "edge" || selectorType === "vertex" ? topologyReference : null;
}

/**
 * A selected reference that is also hovered is drawn ONCE, in the hover's style: its
 * selection's objects stand aside while the hover lasts.
 */
function applyHoverOverSelection(selectedObjects, hoveredIds) {
  for (const [referenceId, objects] of selectedObjects) {
    const visible = !hoveredIds.has(referenceId);
    for (const object of objects) object.visible = visible;
  }
}

/**
 * The reference highlight: the boundary lines and the fill of every selected or hovered face,
 * edge and vertex, and of everything a selected occurrence or shape owns. It reads the selector
 * runtime AS POSED, and re-reads each record's exploded matrix when the explosion comes to rest.
 *
 * Two layers, so a hover rebuilds only what it lights: the selection's layer re-runs when the
 * selection or what it is drawn from changes, and the hover's with each hover. Together they
 * draw what one pass over both did: a reference both selected and hovered is drawn once, as
 * hovered (`applyHoverOverSelection`).
 */
export function useStepHighlights(layers) {
  const { viewport, props, policy, stepScene, activeSelectorRuntime, pickableReferenceMap,
    explodedViewPoseTick, displayRecordsToken } = layers;
  const { runtimeRef, viewerReadyTick } = viewport;
  const { hoveredReferenceId, selectedReferenceIds, measureModeActive } = props;
  const { viewerTheme, displayEdgeSettings } = policy;
  // What the two layers share: the selection's objects by reference, and what the hover lights.
  const sharedRef = useRef({ selectedObjects: new Map(), hoveredIds: new Set() });

  // The selection's layer.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }
    // The fill's geometry is read off the display meshes of the build on screen, so a rebuild
    // invalidates it -- which is why `displayRecordsToken` is a dependency below and not
    // merely a nicety.
    const groups = highlightLayerGroups(runtime, stepScene, "selected");
    const shared = sharedRef.current;
    clearOverlayGroup(runtime, groups.lines);
    clearOverlayGroup(runtime, groups.fills);
    shared.selectedObjects = new Map();
    const style = {
      color: getHighlightEdgeColor(displayEdgeSettings),
      opacity: getHighlightEdgeOpacity(displayEdgeSettings),
      lineWidth: getHighlightEdgeThickness(displayEdgeSettings, viewerTheme)
    };
    const expanded = expandHighlightReferenceIds(Array.isArray(selectedReferenceIds) ? selectedReferenceIds : [],
      pickableReferenceMap, activeSelectorRuntime);
    for (const referenceId of expanded) {
      const topologyReference = highlightableReference(referenceId, pickableReferenceMap, activeSelectorRuntime);
      if (!topologyReference) continue;
      const objects = addReferenceHighlight(runtime, groups, activeSelectorRuntime, topologyReference, style, false);
      if (objects.length) shared.selectedObjects.set(referenceId, objects);
    }
    applyHoverOverSelection(shared.selectedObjects, shared.hoveredIds);
    syncHighlightGroupVisibility(runtime);
    // A frame for what THIS layer changed, and only that: with no reference highlighted
    // before or after, a posed selector runtime is not a reason to draw.
    const drawn = groups.lines.children.length > 0 || groups.fills.children.length > 0;
    if (drawn || runtime.referenceSelectionHighlightDrawn === true) runtime.requestRender();
    runtime.referenceSelectionHighlightDrawn = drawn;

    return () => {
      clearOverlayGroup(runtime, groups.lines);
      clearOverlayGroup(runtime, groups.fills);
      shared.selectedObjects = new Map();
      syncHighlightGroupVisibility(runtime);
    };
  }, [activeSelectorRuntime, displayRecordsToken, explodedViewPoseTick, pickableReferenceMap,
    selectedReferenceIds, stepScene, viewerReadyTick, viewerTheme, displayEdgeSettings]);

  // The hover's layer.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }
    const groups = highlightLayerGroups(runtime, stepScene, "hovered");
    const shared = sharedRef.current;
    clearOverlayGroup(runtime, groups.lines);
    clearOverlayGroup(runtime, groups.fills);
    const highlightEdgeOpacity = getHighlightEdgeOpacity(displayEdgeSettings);
    const style = {
      color: getHighlightEdgeColor(displayEdgeSettings),
      opacity: highlightEdgeOpacity,
      // In measure mode the snapped topology still needs a visible target, but the
      // full-strength face fill would compete with the amber/cyan annotations.
      hoverOpacity: measureModeActive ? Math.max(0.08, highlightEdgeOpacity * 0.35) : highlightEdgeOpacity,
      lineWidth: getHighlightEdgeThickness(displayEdgeSettings, viewerTheme)
    };
    const normalizedHoveredReferenceId = String(hoveredReferenceId || "").trim();
    const hoveredIds = new Set();
    if (normalizedHoveredReferenceId) {
      for (const referenceId of expandHighlightReferenceIds([normalizedHoveredReferenceId], pickableReferenceMap, activeSelectorRuntime)) {
        const topologyReference = highlightableReference(referenceId, pickableReferenceMap, activeSelectorRuntime);
        if (!topologyReference) continue;
        hoveredIds.add(referenceId);
        addReferenceHighlight(runtime, groups, activeSelectorRuntime, topologyReference, style, true);
      }
    }
    shared.hoveredIds = hoveredIds;
    applyHoverOverSelection(shared.selectedObjects, hoveredIds);
    syncHighlightGroupVisibility(runtime);
    const drawn = groups.lines.children.length > 0 || groups.fills.children.length > 0;
    if (drawn || runtime.referenceHoverHighlightDrawn === true) runtime.requestRender();
    runtime.referenceHoverHighlightDrawn = drawn;

    return () => {
      clearOverlayGroup(runtime, groups.lines);
      clearOverlayGroup(runtime, groups.fills);
      shared.hoveredIds = new Set();
      applyHoverOverSelection(shared.selectedObjects, shared.hoveredIds);
      syncHighlightGroupVisibility(runtime);
    };
  }, [activeSelectorRuntime, displayRecordsToken, explodedViewPoseTick, hoveredReferenceId, pickableReferenceMap,
    stepScene, viewerReadyTick, viewerTheme, displayEdgeSettings, measureModeActive]);
}
