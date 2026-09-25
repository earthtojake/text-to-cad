import { useEffect, useRef } from "react";
import { VIEWER_PICK_MODE } from "cadgen-js/lib/viewer/constants.js";
import {
  classifyMeasurePick,
  edgeGeometryFromSegments,
  isFinitePoint,
  pickMeshVertexByScreenDistance
} from "cadgen-js/lib/viewer/measurement.js";
import { buildEdgeLinePositionsFromProxy } from "cadgen-js/lib/viewer/referenceGeometry.js";
import { pointVisibleByClipPlane } from "cadgen-js/lib/viewer/clipPlane.js";
import { screenLimitedPickThreshold } from "cadgen-js/lib/viewer/pickingThresholds.js";
import { PERF_MEASURE_NAMES, perfMeasure, perfStart } from "cadgen-js/lib/viewer/perfMarks.js";
import { createViewerContextMenuGestureState } from "./viewerContextMenuGesture.js";
import { partIdFromIntersection, shouldRaycastRecordForPick } from "./partPicking.js";

const AUTO_EDGE_PICK_THRESHOLD_FACTOR = 1;
const FRONT_LAYER_DISTANCE_FACTOR = 0.0015;
const FRONT_LAYER_DISTANCE_MIN = 0.02;
const EDGE_OCCLUSION_EPSILON_FACTOR = 0.75;
const EDGE_OCCLUSION_EPSILON_MIN = 0.08;
const EDGE_PICK_MAX_SCREEN_DISTANCE_PX = 10;
const EDGE_PICK_MAX_SCREEN_DISTANCE_WITH_FACE_PX = EDGE_PICK_MAX_SCREEN_DISTANCE_PX;
const EDGE_HOVER_MAX_SCREEN_DISTANCE_PX = 6;
const EDGE_HOVER_MAX_SCREEN_DISTANCE_WITH_FACE_PX = EDGE_HOVER_MAX_SCREEN_DISTANCE_PX;
const EDGE_PICK_PRIORITY_WITH_FACE_PX = EDGE_PICK_MAX_SCREEN_DISTANCE_WITH_FACE_PX;
const EDGE_HOVER_PRIORITY_WITH_FACE_PX = EDGE_HOVER_MAX_SCREEN_DISTANCE_WITH_FACE_PX;
const CORNER_PICK_MAX_SCREEN_DISTANCE_PX = 5;
const CORNER_HOVER_MAX_SCREEN_DISTANCE_PX = 4;
// Mesh Measure has no face/edge fallback, so the corner window is wider
// than STEP's 4/5 px. Still a screen-space cap, not "nearest of the triangle".
const MESH_VERTEX_HOVER_MAX_SCREEN_DISTANCE_PX = 14;
const MESH_VERTEX_PICK_MAX_SCREEN_DISTANCE_PX = 16;
const CORNER_PICK_PRIORITY_WITH_OTHER_PX = 4;
const CORNER_HOVER_PRIORITY_WITH_OTHER_PX = 3;
const HOVER_PICK_MIN_MOVE_PX = 2;
const FINE_POINTER_TAP_SLOP_PX = 4;
const COARSE_POINTER_TAP_SLOP_PX = 12;
export const VIEWER_DOUBLE_CLICK_ACTIVATION_DELAY_MS = 220;

function applyColumnMajorMatrix4(point, elements) {
  if (!isFinitePoint(point) || !elements || elements.length < 16) {
    return null;
  }
  const x = point[0];
  const y = point[1];
  const z = point[2];
  const w = (elements[3] * x) + (elements[7] * y) + (elements[11] * z) + elements[15];
  if (!Number.isFinite(w) || Math.abs(w) < 1e-12) {
    return null;
  }
  return [
    ((elements[0] * x) + (elements[4] * y) + (elements[8] * z) + elements[12]) / w,
    ((elements[1] * x) + (elements[5] * y) + (elements[9] * z) + elements[13]) / w,
    ((elements[2] * x) + (elements[6] * y) + (elements[10] * z) + elements[14]) / w
  ];
}

/**
 * World-space corners of the triangle a mesh ray hit. Used to snap Measure
 * picks to a vertex without walking the rest of the mesh.
 */
export function worldTriangleVerticesFromMeshIntersection(intersection) {
  const face = intersection?.face;
  const position = intersection?.object?.geometry?.attributes?.position;
  const matrix = intersection?.object?.matrixWorld?.elements;
  if (!face || !position || typeof position.getX !== "function" || !matrix) {
    return null;
  }
  const vertices = [];
  for (const index of [face.a, face.b, face.c]) {
    if (!Number.isInteger(index) || index < 0 || index >= position.count) {
      return null;
    }
    const local = [Number(position.getX(index)), Number(position.getY(index)), Number(position.getZ(index))];
    const world = applyColumnMajorMatrix4(local, matrix);
    if (!world) {
      return null;
    }
    vertices.push(world);
  }
  return vertices;
}

const MESH_VERTEX_MEASURE_REFERENCE = Object.freeze({
  selectorType: "vertex",
  pickData: Object.freeze({ selectorType: "vertex" })
});

export function measureHitPointFromWorldIntersection(intersection) {
  if (!intersection?.point) {
    return null;
  }
  const x = Number(intersection.point.x);
  const y = Number(intersection.point.y);
  const z = Number(intersection.point.z);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
    return null;
  }
  return [x, y, z];
}

/**
 * The offset the viewer applies to re-centre the model. Selector geometry — the
 * edge proxy, `pickData.center` — is authored around the model origin, while a
 * ray hit is in world space, and these two frames differ by exactly this
 * translation. The pick groups only ever have their position set (never rotation
 * or scale), so a vector subtraction is the whole transform.
 */
export function measureModelOffsetFromRuntime(runtime) {
  const position = (runtime?.facePickGroup || runtime?.edgePickGroup || runtime?.modelGroup)?.position;
  if (!position) {
    return [0, 0, 0];
  }
  return [position.x, position.y, position.z].map((value) => (Number.isFinite(Number(value)) ? Number(value) : 0));
}

export function measureWorldPointToModel(point, offset) {
  if (!isFinitePoint(point)) {
    return null;
  }
  const [dx, dy, dz] = offset || [0, 0, 0];
  return [point[0] - dx, point[1] - dy, point[2] - dz];
}

export function measureModelPointToWorld(point, offset) {
  if (!isFinitePoint(point)) {
    return null;
  }
  const [dx, dy, dz] = offset || [0, 0, 0];
  return [point[0] + dx, point[1] + dy, point[2] + dz];
}

/**
 * Snapping runs in the model frame and only the resulting point is lifted back
 * out to world. Translating the whole edge-segment buffer instead would redo
 * hundreds of additions on every hover tick to reach the same answer.
 */
export function measurePickForPosition({
  reference = null,
  worldHitPoint = null,
  referenceId = "",
  bypassTopology = false,
  edgeSegments = null,
  edgeGeometry,
  vertexPoint = null,
  modelOffset = null
} = {}) {
  const hitPoint = isFinitePoint(worldHitPoint) ? worldHitPoint : null;
  if (bypassTopology) {
    return classifyMeasurePick({ reference: null, hitPoint, referenceId: "" });
  }
  const modelHitPoint = measureWorldPointToModel(hitPoint, modelOffset);
  const pick = classifyMeasurePick({
    reference,
    hitPoint: modelHitPoint,
    referenceId: referenceId || "",
    edgeSegments,
    edgeGeometry,
    vertexPoint
  });
  if (!pick) {
    return null;
  }
  const worldPoint = measureModelPointToWorld(pick.point, modelOffset);
  if (!worldPoint) {
    return null;
  }
  // A fitted arc centre is a position, so it has to come out to world space with
  // the point. Radius and direction are translation-invariant and stay as they are.
  const geometry = isFinitePoint(pick.geometry?.center)
    ? { ...pick.geometry, center: measureModelPointToWorld(pick.geometry.center, modelOffset) }
    : pick.geometry;
  return { ...pick, point: worldPoint, geometry };
}

function chooseBestEdgeIntersection(intersections, measureScreenDistance = null) {
  if (!intersections.length) {
    return null;
  }
  const scored = intersections.map((intersection) => ({
    intersection,
    screenDistance: typeof measureScreenDistance === "function"
      ? Number(measureScreenDistance(intersection))
      : Infinity,
    pickError: intersection.distanceToRay ?? intersection.distance ?? Infinity,
    distance: intersection.distance ?? Infinity,
    metric: intersection.object.userData.metric ?? Infinity
  }));
  scored.sort((a, b) => {
    const aScreenDistance = Number.isFinite(a.screenDistance) ? a.screenDistance : Infinity;
    const bScreenDistance = Number.isFinite(b.screenDistance) ? b.screenDistance : Infinity;
    if (Math.abs(aScreenDistance - bScreenDistance) > 0.25) {
      return aScreenDistance - bScreenDistance;
    }
    if (Math.abs(a.pickError - b.pickError) > 1e-4) {
      return a.pickError - b.pickError;
    }
    if (Math.abs(a.distance - b.distance) > 1e-4) {
      return a.distance - b.distance;
    }
    return a.metric - b.metric;
  });
  return scored[0].intersection;
}

function frontMostModelIntersections(intersections) {
  if (!Array.isArray(intersections) || !intersections.length) {
    return [];
  }
  const nearestDistance = Number(intersections[0]?.distance);
  if (!Number.isFinite(nearestDistance)) {
    return [];
  }
  const depthWindow = Math.max(FRONT_LAYER_DISTANCE_MIN, nearestDistance * FRONT_LAYER_DISTANCE_FACTOR);
  return intersections.filter((intersection) => Number(intersection?.distance) <= nearestDistance + depthWindow);
}

function focusedPartIdSet(value) {
  return new Set(
    (Array.isArray(value) ? value : [value])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
}

function intersectionVisibleByClipPlane(runtime, intersection) {
  return pointVisibleByClipPlane(runtime?.activeClipPlane, intersection?.point);
}

function filterClippedIntersections(runtime, intersections) {
  if (!runtime?.activeClipPlane || !Array.isArray(intersections) || !intersections.length) {
    return intersections;
  }
  return intersections.filter((intersection) => intersectionVisibleByClipPlane(runtime, intersection));
}

export function useViewerPicking({
  runtimeRef,
  mountRef,
  sceneMountRef = null,
  drawingCanvasRef = null,
  previewMode,
  pickMode,
  selectorRuntime,
  pickableFaces,
  pickableEdges,
  pickableVertices,
  hiddenPartIds,
  focusedPartId,
  onHoverReferenceChange,
  onActivateReference,
  onDoubleActivateReference,
  onContextReference,
  onMeasurePick,
  onMeasureHoverPoint,
  viewerReadyTick,
  // While a STEP animation is playing, reference hover/selection is suspended
  // so playback frames skip raycasts and pick-state rebuilds entirely.
  suppressTopologyPicking = false,
  allowMeshVertexSnap = false
}) {
  // Keep pointer listeners stable across parent rerenders; hover itself updates parent state.
  const pickModeRef = useRef(pickMode);
  const selectorRuntimeRef = useRef(selectorRuntime);
  const pickableFacesRef = useRef(pickableFaces);
  const pickableEdgesRef = useRef(pickableEdges);
  const pickableVerticesRef = useRef(pickableVertices);
  const hiddenPartIdsRef = useRef(hiddenPartIds);
  const focusedPartIdRef = useRef(focusedPartId);
  const onHoverReferenceChangeRef = useRef(onHoverReferenceChange);
  const onActivateReferenceRef = useRef(onActivateReference);
  const onDoubleActivateReferenceRef = useRef(onDoubleActivateReference);
  const onContextReferenceRef = useRef(onContextReference);
  const onMeasurePickRef = useRef(onMeasurePick);
  const onMeasureHoverPointRef = useRef(onMeasureHoverPoint);
  const allowMeshVertexSnapRef = useRef(allowMeshVertexSnap);
  const allowedFaceReferenceIdsRef = useRef(new Set());
  const allowedEdgeReferenceIdsRef = useRef(new Set());
  const allowedVertexReferenceIdsRef = useRef(new Set());

  pickModeRef.current = pickMode;
  selectorRuntimeRef.current = selectorRuntime;
  pickableFacesRef.current = pickableFaces;
  pickableEdgesRef.current = pickableEdges;
  pickableVerticesRef.current = pickableVertices;
  hiddenPartIdsRef.current = hiddenPartIds;
  focusedPartIdRef.current = focusedPartId;
  onHoverReferenceChangeRef.current = onHoverReferenceChange;
  onActivateReferenceRef.current = onActivateReference;
  onDoubleActivateReferenceRef.current = onDoubleActivateReference;
  onContextReferenceRef.current = onContextReference;
  onMeasurePickRef.current = onMeasurePick;
  onMeasureHoverPointRef.current = onMeasureHoverPoint;
  allowMeshVertexSnapRef.current = allowMeshVertexSnap === true;
  allowedFaceReferenceIdsRef.current = new Set(
    (Array.isArray(pickableFaces) ? pickableFaces : [])
      .map((reference) => String(reference?.id || "").trim())
      .filter(Boolean)
  );
  allowedEdgeReferenceIdsRef.current = new Set(
    (Array.isArray(pickableEdges) ? pickableEdges : [])
      .map((reference) => String(reference?.id || "").trim())
      .filter(Boolean)
  );
  allowedVertexReferenceIdsRef.current = new Set(
    (Array.isArray(pickableVertices) ? pickableVertices : [])
      .map((reference) => String(reference?.id || "").trim())
      .filter(Boolean)
  );

  // Arming the tool has to change the cursor immediately. Leaving it to the next
  // hover tick means the select pointer lingers until the mouse happens to move.
  useEffect(() => {
    const container = mountRef.current;
    if (!container || pickMode !== VIEWER_PICK_MODE.MEASURE) {
      return undefined;
    }
    container.style.cursor = "crosshair";
    return () => {
      container.style.cursor = "";
    };
  }, [mountRef, pickMode, previewMode, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime || !mountRef.current || previewMode) {
      onHoverReferenceChangeRef.current?.("");
      return;
    }

    const container = mountRef.current;
    const sceneMount = sceneMountRef?.current || null;
    const drawingCanvas = drawingCanvasRef?.current || null;
    const coarsePointerQuery = typeof window.matchMedia === "function"
      ? window.matchMedia("(pointer: coarse)")
      : null;
    const defaultToCoarsePointer = coarsePointerQuery?.matches ?? false;
    const pointerDown = {
      active: false,
      x: 0,
      y: 0,
      pointerType: "",
      referenceId: ""
    };
    const primaryPointer = {
      active: false,
      x: 0,
      y: 0,
      pointerType: ""
    };
    const contextPointer = {
      active: false,
      blocked: false,
      moved: false,
      startedInScene: false,
      x: 0,
      y: 0,
      pointerType: ""
    };
    const hoverState = {
      rafId: 0,
      x: 0,
      y: 0,
      lastX: NaN,
      lastY: NaN,
      hoveredReferenceId: "",
      measureTickEmitted: false
    };
    const doubleClickEnabled = !defaultToCoarsePointer;
    let activationTimerId = 0;
    const contextMenuGesture = createViewerContextMenuGestureState();

    function pointerButtons(event) {
      const buttons = Number(event?.buttons);
      return Number.isFinite(buttons) ? buttons : 0;
    }

    function primaryButtonHeld(event) {
      return (pointerButtons(event) & 1) === 1;
    }

    function contextButtonHeld(event) {
      return (pointerButtons(event) & 2) === 2;
    }

    function chordButtonsHeld(event) {
      return (pointerButtons(event) & 3) === 3;
    }

    function resetPrimaryPointer() {
      primaryPointer.active = false;
      primaryPointer.pointerType = "";
    }

    function resetContextPointer() {
      contextPointer.active = false;
      contextPointer.blocked = false;
      contextPointer.moved = false;
      contextPointer.startedInScene = false;
      contextPointer.pointerType = "";
    }

    function suppressContextMenuFromPanChord() {
      contextMenuGesture.suppressNextContextMenu();
      contextPointer.blocked = true;
      contextPointer.moved = true;
      pointerDown.active = false;
      pointerDown.pointerType = "";
      pointerDown.referenceId = "";
    }

    function setPointerFromPosition(clientX, clientY) {
      const rect = container.getBoundingClientRect();
      runtime.pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
      runtime.pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
      runtime.raycaster.setFromCamera(runtime.pointer, runtime.camera);
      if (runtime.raycaster?.params?.Line) {
        runtime.raycaster.params.Line.threshold = runtime.edgePickThreshold || 1;
      }
      if (runtime.raycaster?.params?.Points) {
        runtime.raycaster.params.Points.threshold = runtime.vertexPickThreshold || 1;
      }
    }

    function projectPointToClient(point) {
      if (!point?.clone || !runtime?.camera) {
        return null;
      }
      const projected = point.clone().project(runtime.camera);
      if (!Number.isFinite(projected.x) || !Number.isFinite(projected.y)) {
        return null;
      }
      const rect = container.getBoundingClientRect();
      return {
        x: rect.left + ((projected.x + 1) * 0.5 * rect.width),
        y: rect.top + ((1 - projected.y) * 0.5 * rect.height)
      };
    }

    function edgeScreenDistance(intersection, clientX, clientY) {
      const clientPoint = projectPointToClient(intersection?.point);
      if (!clientPoint) {
        return Infinity;
      }
      return Math.hypot(clientX - clientPoint.x, clientY - clientPoint.y);
    }

    function pickViewportHeightPx() {
      return container.clientHeight || container.getBoundingClientRect().height || 1;
    }

    function pickSurfaceDistance(modelIntersections) {
      const surfaceDistance = Number(modelIntersections?.[0]?.distance);
      if (Number.isFinite(surfaceDistance) && surfaceDistance > 0) {
        return surfaceDistance;
      }
      const controlsDistance = runtime?.camera?.position?.distanceTo?.(runtime?.controls?.target);
      if (Number.isFinite(controlsDistance) && controlsDistance > 0) {
        return controlsDistance;
      }
      return Number(runtime?.modelRadius || 1);
    }

    function currentPickThreshold(baseThreshold, thresholdScale, maxScreenDistancePx, modelIntersections) {
      return screenLimitedPickThreshold({
        baseThreshold,
        thresholdScale,
        maxScreenDistancePx,
        camera: runtime.camera,
        viewportHeightPx: pickViewportHeightPx(),
        distance: pickSurfaceDistance(modelIntersections)
      });
    }

    function visibleModelMeshes() {
      const focusIds = focusedPartIdSet(focusedPartIdRef.current);
      const hiddenIds = focusedPartIdSet(hiddenPartIdsRef.current);
      return runtime.displayRecords
        .filter((record) => shouldRaycastRecordForPick(record, { focusIds, hiddenIds }))
        .map((record) => record.mesh);
    }

    function intersectVisibleModelMeshes() {
      const modelMeshes = visibleModelMeshes();
      if (!modelMeshes.length) {
        return [];
      }
      return filterClippedIntersections(runtime, runtime.raycaster.intersectObjects(modelMeshes, false));
    }

    function pickPartReferenceFromIntersections(intersections) {
      const focusIds = focusedPartIdSet(focusedPartIdRef.current);
      const hiddenIds = focusedPartIdSet(hiddenPartIdsRef.current);
      for (const intersection of intersections) {
        const partId = partIdFromIntersection(intersection);
        if (!partId) {
          continue;
        }
        if (hiddenIds.has(String(partId || "").trim())) {
          continue;
        }
        if (focusIds.size && !focusIds.has(String(partId || "").trim())) {
          continue;
        }
        return partId;
      }
      return null;
    }

    function faceReferenceFromIntersection(intersection) {
      const triangleIndex = Number(intersection?.faceIndex);
      const faceIds = intersection?.object?.userData?.faceIds;
      const rowIndex = Number.isInteger(triangleIndex) ? Number(faceIds?.[triangleIndex]) : NaN;
      if (!Number.isInteger(rowIndex)) {
        return null;
      }
      const reference = selectorRuntimeRef.current?.faceReferenceByRowIndex?.get?.(rowIndex) || null;
      const referenceId = String(reference?.id || "").trim();
      const allowedFaceReferenceIds = allowedFaceReferenceIdsRef.current;
      if (!referenceId || (allowedFaceReferenceIds.size && !allowedFaceReferenceIds.has(referenceId))) {
        return null;
      }
      return reference;
    }

    function edgeReferenceFromIntersection(intersection) {
      // Three.js reports LineSegments hits as the starting index/vertex offset
      // for the segment (0, 2, 4, ...), while edgeIds is packed per segment.
      const hitIndex = Number(intersection?.index);
      const edgeIds = intersection?.object?.userData?.edgeIds;
      const segmentIndex = Number.isInteger(hitIndex) ? Math.floor(hitIndex / 2) : NaN;
      const rowIndex = Number.isInteger(segmentIndex) ? Number(edgeIds?.[segmentIndex]) : NaN;
      if (!Number.isInteger(rowIndex)) {
        return null;
      }
      const reference = selectorRuntimeRef.current?.edgeReferenceByRowIndex?.get?.(rowIndex) || null;
      const referenceId = String(reference?.id || "").trim();
      const allowedEdgeReferenceIds = allowedEdgeReferenceIdsRef.current;
      if (!referenceId || (allowedEdgeReferenceIds.size && !allowedEdgeReferenceIds.has(referenceId))) {
        return null;
      }
      return reference;
    }

    function vertexReferenceFromIntersection(intersection) {
      const pointIndex = Number(intersection?.index);
      const vertexIds = intersection?.object?.userData?.vertexIds;
      const rowIndex = Number.isInteger(pointIndex) ? Number(vertexIds?.[pointIndex]) : NaN;
      if (!Number.isInteger(rowIndex)) {
        return null;
      }
      const reference = selectorRuntimeRef.current?.vertexReferenceByRowIndex?.get?.(rowIndex) || null;
      const referenceId = String(reference?.id || "").trim();
      const allowedVertexReferenceIds = allowedVertexReferenceIdsRef.current;
      if (!referenceId || (allowedVertexReferenceIds.size && !allowedVertexReferenceIds.has(referenceId))) {
        return null;
      }
      return reference;
    }

    function pickFaceReference(modelIntersections) {
      if (!(Array.isArray(pickableFacesRef.current) ? pickableFacesRef.current : []).length) {
        return null;
      }
      for (const intersection of frontMostModelIntersections(modelIntersections)) {
        const reference = faceReferenceFromIntersection(intersection);
        if (reference) {
          return reference;
        }
      }
      if (!runtime.facePickMesh) {
        return null;
      }
      const intersections = filterClippedIntersections(runtime, runtime.raycaster.intersectObject(runtime.facePickMesh, false));
      if (!intersections.length) {
        return null;
      }
      const frontModelIntersections = frontMostModelIntersections(modelIntersections);
      let filteredIntersections = intersections;
      const nearestSurfaceDistance = Number(frontModelIntersections[0]?.distance);
      if (Number.isFinite(nearestSurfaceDistance)) {
        const depthWindow = Math.max(FRONT_LAYER_DISTANCE_MIN, nearestSurfaceDistance * FRONT_LAYER_DISTANCE_FACTOR);
        filteredIntersections = intersections.filter(
          (intersection) => Number(intersection?.distance) <= nearestSurfaceDistance + depthWindow
        );
      }
      for (const intersection of filteredIntersections.length ? filteredIntersections : intersections) {
        const reference = faceReferenceFromIntersection(intersection);
        if (!reference) {
          continue;
        }
        return reference;
      }
      return null;
    }

    function pickEdgeCandidate(modelIntersections, clientX, clientY, {
      thresholdScale = 1,
      maxScreenDistancePx = EDGE_PICK_MAX_SCREEN_DISTANCE_PX
    } = {}) {
      const pickableEdges = Array.isArray(pickableEdgesRef.current) ? pickableEdgesRef.current : [];
      if (!pickableEdges.length || !runtime.edgePickLines) {
        return null;
      }
      const edgeThreshold = currentPickThreshold(
        runtime.edgePickThreshold || 1,
        thresholdScale,
        maxScreenDistancePx,
        modelIntersections
      );
      if (runtime.raycaster?.params?.Line) {
        runtime.raycaster.params.Line.threshold = edgeThreshold;
      }
      let filteredIntersections = filterClippedIntersections(runtime, runtime.raycaster.intersectObject(runtime.edgePickLines, false));
      const nearestSurfaceDistance = Number(modelIntersections?.[0]?.distance);
      if (Number.isFinite(nearestSurfaceDistance)) {
        const depthAllowance = Math.max(
          EDGE_OCCLUSION_EPSILON_MIN,
          edgeThreshold * EDGE_OCCLUSION_EPSILON_FACTOR
        );
        filteredIntersections = filteredIntersections.filter(
          (intersection) => Number(intersection?.distance) <= nearestSurfaceDistance + depthAllowance
        );
      }
      const best = chooseBestEdgeIntersection(
        filteredIntersections,
        (intersection) => edgeScreenDistance(intersection, clientX, clientY)
      );
      if (!best) {
        return null;
      }
      const bestScreenDistance = edgeScreenDistance(best, clientX, clientY);
      if (Number.isFinite(bestScreenDistance) && bestScreenDistance > maxScreenDistancePx) {
        return null;
      }
      const reference = edgeReferenceFromIntersection(best);
      if (!reference) {
        return null;
      }
      return {
        reference,
        screenDistance: bestScreenDistance
      };
    }

    function pickVertexCandidate(modelIntersections, clientX, clientY, {
      thresholdScale = 1,
      maxScreenDistancePx = CORNER_PICK_MAX_SCREEN_DISTANCE_PX
    } = {}) {
      const pickableVertices = Array.isArray(pickableVerticesRef.current) ? pickableVerticesRef.current : [];
      if (!pickableVertices.length || !runtime.vertexPickPoints) {
        return null;
      }
      const vertexThreshold = currentPickThreshold(
        runtime.vertexPickThreshold || 1,
        thresholdScale,
        maxScreenDistancePx,
        modelIntersections
      );
      if (runtime.raycaster?.params?.Points) {
        runtime.raycaster.params.Points.threshold = vertexThreshold;
      }
      let filteredIntersections = filterClippedIntersections(runtime, runtime.raycaster.intersectObject(runtime.vertexPickPoints, false));
      const nearestSurfaceDistance = Number(modelIntersections?.[0]?.distance);
      if (Number.isFinite(nearestSurfaceDistance)) {
        const depthAllowance = Math.max(
          EDGE_OCCLUSION_EPSILON_MIN,
          vertexThreshold * EDGE_OCCLUSION_EPSILON_FACTOR
        );
        filteredIntersections = filteredIntersections.filter(
          (intersection) => Number(intersection?.distance) <= nearestSurfaceDistance + depthAllowance
        );
      }
      const best = chooseBestEdgeIntersection(
        filteredIntersections,
        (intersection) => edgeScreenDistance(intersection, clientX, clientY)
      );
      if (!best) {
        return null;
      }
      const bestScreenDistance = edgeScreenDistance(best, clientX, clientY);
      if (Number.isFinite(bestScreenDistance) && bestScreenDistance > maxScreenDistancePx) {
        return null;
      }
      const reference = vertexReferenceFromIntersection(best);
      if (!reference) {
        return null;
      }
      return {
        reference,
        screenDistance: bestScreenDistance
      };
    }

    function areFaceAndEdgeAdjacent(faceReference, edgeReference) {
      const adjacentSelectors = Array.isArray(faceReference?.pickData?.adjacentSelectors)
        ? faceReference.pickData.adjacentSelectors
        : [];
      if (!adjacentSelectors.length) {
        return false;
      }
      const edgeDisplaySelector = String(edgeReference?.displaySelector || "").trim();
      const edgeNormalizedSelector = String(edgeReference?.normalizedSelector || "").trim();
      return adjacentSelectors.includes(edgeDisplaySelector) || adjacentSelectors.includes(edgeNormalizedSelector);
    }

    function areEdgeAndVertexAdjacent(edgeReference, vertexReference) {
      const adjacentSelectors = Array.isArray(vertexReference?.pickData?.adjacentSelectors)
        ? vertexReference.pickData.adjacentSelectors
        : [];
      if (!adjacentSelectors.length) {
        return false;
      }
      const edgeDisplaySelector = String(edgeReference?.displaySelector || "").trim();
      const edgeNormalizedSelector = String(edgeReference?.normalizedSelector || "").trim();
      return adjacentSelectors.includes(edgeDisplaySelector) || adjacentSelectors.includes(edgeNormalizedSelector);
    }

    function areFaceAndVertexAdjacent(faceReference, vertexReference) {
      const faceAdjacentSelectors = Array.isArray(faceReference?.pickData?.adjacentSelectors)
        ? faceReference.pickData.adjacentSelectors
        : [];
      const vertexAdjacentSelectors = Array.isArray(vertexReference?.pickData?.adjacentSelectors)
        ? vertexReference.pickData.adjacentSelectors
        : [];
      if (!faceAdjacentSelectors.length || !vertexAdjacentSelectors.length) {
        return false;
      }
      const edgeSelectorSet = new Set(faceAdjacentSelectors);
      return vertexAdjacentSelectors.some((selector) => edgeSelectorSet.has(selector));
    }

    function pickTopologyReference(modelIntersections, clientX, clientY, { hover = false } = {}) {
      const pickableFaces = Array.isArray(pickableFacesRef.current) ? pickableFacesRef.current : [];
      const pickableEdges = Array.isArray(pickableEdgesRef.current) ? pickableEdgesRef.current : [];
      const pickableVertices = Array.isArray(pickableVerticesRef.current) ? pickableVerticesRef.current : [];
      const hasFaces = pickableFaces.length > 0;
      const hasEdges = pickableEdges.length > 0;
      const hasVertices = pickableVertices.length > 0;
      if (!hasFaces && !hasEdges && !hasVertices) {
        return null;
      }
      const faceReference = pickFaceReference(modelIntersections);
      const maxScreenDistancePx = hover
        ? (
          faceReference
            ? EDGE_HOVER_MAX_SCREEN_DISTANCE_WITH_FACE_PX
            : EDGE_HOVER_MAX_SCREEN_DISTANCE_PX
        )
        : (
          faceReference
            ? EDGE_PICK_MAX_SCREEN_DISTANCE_WITH_FACE_PX
            : EDGE_PICK_MAX_SCREEN_DISTANCE_PX
        );
      const edgeCandidate = pickEdgeCandidate(
        modelIntersections,
        clientX,
        clientY,
        {
          thresholdScale: faceReference ? AUTO_EDGE_PICK_THRESHOLD_FACTOR : 1,
          maxScreenDistancePx
        }
      );
      const vertexCandidate = pickVertexCandidate(
        modelIntersections,
        clientX,
        clientY,
        {
          maxScreenDistancePx: hover ? CORNER_HOVER_MAX_SCREEN_DISTANCE_PX : CORNER_PICK_MAX_SCREEN_DISTANCE_PX
        }
      );
      if (vertexCandidate) {
        const vertexPriorityDistancePx = hover ? CORNER_HOVER_PRIORITY_WITH_OTHER_PX : CORNER_PICK_PRIORITY_WITH_OTHER_PX;
        const adjacentToEdge = edgeCandidate && areEdgeAndVertexAdjacent(edgeCandidate.reference, vertexCandidate.reference);
        const adjacentToFace = faceReference && areFaceAndVertexAdjacent(faceReference, vertexCandidate.reference);
        if (!faceReference && !edgeCandidate) {
          return vertexCandidate.reference.id;
        }
        if ((adjacentToEdge || adjacentToFace) && Number(vertexCandidate.screenDistance) <= vertexPriorityDistancePx) {
          return vertexCandidate.reference.id;
        }
      }
      if (faceReference && edgeCandidate) {
        const priorityDistancePx = hover ? EDGE_HOVER_PRIORITY_WITH_FACE_PX : EDGE_PICK_PRIORITY_WITH_FACE_PX;
        if (areFaceAndEdgeAdjacent(faceReference, edgeCandidate.reference)) {
          if (Number(edgeCandidate.screenDistance) <= priorityDistancePx) {
            return edgeCandidate.reference.id;
          }
          return faceReference.id;
        }
        return faceReference.id;
      }
      return edgeCandidate?.reference?.id || faceReference?.id || vertexCandidate?.reference?.id || null;
    }

    function measureReferenceById(referenceId) {
      const selectorRuntime = selectorRuntimeRef.current;
      const reference = selectorRuntime?.referenceMap?.get?.(referenceId) || null;
      if (reference) {
        return reference;
      }
      return (Array.isArray(selectorRuntime?.references) ? selectorRuntime.references : [])
        .find((candidate) => String(candidate?.id || "").trim() === String(referenceId || "").trim()) || null;
    }

    // Hover re-resolves the same edge on every mouse move, so the last slice is
    // kept rather than rebuilt each tick.
    // Hover re-resolves the same edge every tick, and both the proxy slice and
    // the geometry fit are functions of the reference alone.
    let measureEdgeCache = { referenceId: "", segments: null, geometry: null };

    function measureSnapGeometry(reference, referenceId) {
      const selectorType = String(reference?.pickData?.selectorType || reference?.selectorType || "")
        .trim()
        .toLowerCase();
      if (selectorType === "vertex") {
        const center = reference?.pickData?.center;
        return { edgeSegments: null, edgeGeometry: null, vertexPoint: isFinitePoint(center) ? center.slice(0, 3) : null };
      }
      if (selectorType !== "edge") {
        return { edgeSegments: null, edgeGeometry: null, vertexPoint: null };
      }
      if (measureEdgeCache.referenceId !== referenceId) {
        const segments = buildEdgeLinePositionsFromProxy(selectorRuntimeRef.current, reference);
        measureEdgeCache = { referenceId, segments, geometry: edgeGeometryFromSegments(segments) };
      }
      return {
        edgeSegments: measureEdgeCache.segments,
        edgeGeometry: measureEdgeCache.geometry,
        vertexPoint: null
      };
    }

    function projectWorldArrayToClient(point) {
      if (!isFinitePoint(point) || !runtime?.THREE?.Vector3) {
        return null;
      }
      return projectPointToClient(new runtime.THREE.Vector3(point[0], point[1], point[2]));
    }

    function measureReferenceFromPosition(clientX, clientY, { hover = false, bypassTopology = false } = {}) {
      setPointerFromPosition(clientX, clientY);
      const modelIntersections = intersectVisibleModelMeshes();
      const hitIntersection = frontMostModelIntersections(modelIntersections)
        .find((intersection) => measureHitPointFromWorldIntersection(intersection)) || null;
      const worldHitPoint = measureHitPointFromWorldIntersection(hitIntersection);
      const modelOffset = measureModelOffsetFromRuntime(runtimeRef.current);
      if (allowMeshVertexSnapRef.current && !bypassTopology) {
        const triangleWorld = worldTriangleVerticesFromMeshIntersection(hitIntersection);
        const maxScreenDistancePx = hover
          ? MESH_VERTEX_HOVER_MAX_SCREEN_DISTANCE_PX
          : MESH_VERTEX_PICK_MAX_SCREEN_DISTANCE_PX;
        const meshSnap = pickMeshVertexByScreenDistance(
          triangleWorld,
          { x: clientX, y: clientY },
          maxScreenDistancePx,
          projectWorldArrayToClient
        );
        if (!meshSnap) {
          return { pick: null, referenceId: "" };
        }
        return {
          pick: measurePickForPosition({
            reference: MESH_VERTEX_MEASURE_REFERENCE,
            worldHitPoint,
            referenceId: "",
            vertexPoint: measureWorldPointToModel(meshSnap.point, modelOffset),
            modelOffset
          }),
          referenceId: ""
        };
      }
      const referenceId = bypassTopology ? "" : (pickTopologyReference(modelIntersections, clientX, clientY, { hover }) || "");
      const reference = referenceId ? measureReferenceById(referenceId) : null;
      const { edgeSegments, edgeGeometry, vertexPoint } = bypassTopology
        ? { edgeSegments: null, edgeGeometry: null, vertexPoint: null }
        : measureSnapGeometry(reference, referenceId);
      return {
        pick: measurePickForPosition({
          reference,
          worldHitPoint,
          referenceId,
          bypassTopology,
          edgeSegments,
          edgeGeometry,
          vertexPoint,
          modelOffset
        }),
        referenceId
      };
    }

    function pickReferenceAtPosition(clientX, clientY, { hover = false, preferTopology = false } = {}) {
      if (suppressTopologyPicking) {
        return null;
      }
      setPointerFromPosition(clientX, clientY);
      const modelIntersections = intersectVisibleModelMeshes();
      const pickMode = pickModeRef.current;
      if (preferTopology) {
        const topologyReference = pickTopologyReference(modelIntersections, clientX, clientY, { hover });
        if (topologyReference) {
          return topologyReference;
        }
      }
      if (pickMode === VIEWER_PICK_MODE.PARTS) {
        return pickPartReferenceFromIntersections(modelIntersections);
      }
      if (pickMode === VIEWER_PICK_MODE.ASSEMBLY) {
        return pickPartReferenceFromIntersections(modelIntersections);
      }
      if (pickMode === VIEWER_PICK_MODE.AUTO) {
        return pickTopologyReference(modelIntersections, clientX, clientY, { hover }) ||
          pickPartReferenceFromIntersections(modelIntersections);
      }
      if (pickMode === VIEWER_PICK_MODE.MEASURE) {
        return pickTopologyReference(modelIntersections, clientX, clientY, { hover });
      }
      return null;
    }

    function pickActivationReference(clientX, clientY, pointerType = "") {
      if (canHoverWithPointer(pointerType)) {
        return String(hoverState.hoveredReferenceId || "").trim() || pickReferenceAtPosition(clientX, clientY, { hover: true });
      }
      return pickReferenceAtPosition(clientX, clientY);
    }

    function isCoarsePointer(pointerType = "") {
      return pointerType === "touch" || pointerType === "pen" || defaultToCoarsePointer;
    }

    function tapSlopForPointer(pointerType = "") {
      return isCoarsePointer(pointerType) ? COARSE_POINTER_TAP_SLOP_PX : FINE_POINTER_TAP_SLOP_PX;
    }

    function canHoverWithPointer(pointerType = "") {
      return !isCoarsePointer(pointerType);
    }

    function isSceneInteractionTarget(target) {
      if (!(target instanceof Node)) {
        return false;
      }
      if (sceneMount?.contains(target)) {
        return true;
      }
      if (drawingCanvas && (target === drawingCanvas || drawingCanvas.contains?.(target))) {
        return true;
      }
      return false;
    }

    function isSceneEvent(event) {
      return isSceneInteractionTarget(event.target);
    }

    function isActiveSceneGestureEvent(event) {
      return isSceneEvent(event) || contextPointer.active || primaryPointer.active;
    }

    function commitHoverState(referenceId) {
      const normalizedReferenceId = referenceId || "";
      // Measuring keeps one cursor throughout. Swapping to the select pointer
      // over a reference reads as "click to select this", when the click is
      // going to drop a measurement point either way — what is snappable is
      // shown by highlighting the entity, not by changing the cursor.
      const isMeasureMode = pickModeRef.current === VIEWER_PICK_MODE.MEASURE;
      container.style.cursor = isMeasureMode ? "crosshair" : (normalizedReferenceId ? "pointer" : "");
      if (hoverState.hoveredReferenceId === normalizedReferenceId) {
        return;
      }
      hoverState.hoveredReferenceId = normalizedReferenceId;
      onHoverReferenceChangeRef.current?.(normalizedReferenceId);
    }

    function clearHoverState() {
      if (hoverState.rafId) {
        window.cancelAnimationFrame(hoverState.rafId);
        hoverState.rafId = 0;
      }
      hoverState.lastX = NaN;
      hoverState.lastY = NaN;
      container.style.cursor = pickModeRef.current === VIEWER_PICK_MODE.MEASURE ? "crosshair" : "";
      const hadMeasureTick = hoverState.measureTickEmitted;
      hoverState.measureTickEmitted = false;
      if (!hoverState.hoveredReferenceId && !hadMeasureTick) {
        return;
      }
      hoverState.hoveredReferenceId = "";
      onHoverReferenceChangeRef.current?.("");
      if (hadMeasureTick) {
        onMeasureHoverPointRef.current?.(null);
      }
    }

    function clearPendingActivation() {
      if (!activationTimerId) {
        return;
      }
      window.clearTimeout(activationTimerId);
      activationTimerId = 0;
    }

    function commitActivation(referenceId, options = {}) {
      onActivateReferenceRef.current?.(referenceId || "", options);
    }

    function scheduleActivation(referenceId, options = {}) {
      clearPendingActivation();
      if (!doubleClickEnabled) {
        commitActivation(referenceId, options);
        return;
      }
      activationTimerId = window.setTimeout(() => {
        activationTimerId = 0;
        commitActivation(referenceId, options);
      }, VIEWER_DOUBLE_CLICK_ACTIVATION_DELAY_MS);
    }

    function flushHoverPick() {
      hoverState.rafId = 0;
      if (runtime.interactionState.active || suppressTopologyPicking) {
        clearHoverState();
        return;
      }
      hoverState.lastX = hoverState.x;
      hoverState.lastY = hoverState.y;
      if (pickModeRef.current === VIEWER_PICK_MODE.MEASURE) {
        // The measure pass already raycast the model and resolved the topology
        // reference under the cursor; picking again would double every hover.
        hoverState.measureTickEmitted = true;
        const measured = measureReferenceFromPosition(hoverState.x, hoverState.y, { hover: true });
        onMeasureHoverPointRef.current?.(measured.pick);
        commitHoverState(measured.referenceId || "");
        return;
      }
      const pickStartedAt = perfStart();
      const hovered = pickReferenceAtPosition(hoverState.x, hoverState.y, { hover: true });
      perfMeasure(PERF_MEASURE_NAMES.hoverPick, pickStartedAt, { hit: Boolean(hovered) });
      commitHoverState(hovered);
    }

    function scheduleHoverPick(clientX, clientY) {
      hoverState.x = clientX;
      hoverState.y = clientY;
      if (
        Number.isFinite(hoverState.lastX) &&
        Number.isFinite(hoverState.lastY) &&
        Math.hypot(clientX - hoverState.lastX, clientY - hoverState.lastY) < HOVER_PICK_MIN_MOVE_PX
      ) {
        return;
      }
      if (hoverState.rafId) {
        return;
      }
      hoverState.rafId = window.requestAnimationFrame(flushHoverPick);
    }

    function recordPrimaryPointerDown(event) {
      primaryPointer.active = true;
      primaryPointer.x = event.clientX;
      primaryPointer.y = event.clientY;
      primaryPointer.pointerType = event.pointerType || "";
    }

    function recordContextPointerDown(event) {
      const preserveGestureBlock = contextPointer.active || contextPointer.startedInScene;
      const blocked = preserveGestureBlock && contextPointer.blocked;
      const moved = preserveGestureBlock && contextPointer.moved;
      contextPointer.active = true;
      contextPointer.blocked = blocked;
      contextPointer.moved = moved;
      contextPointer.startedInScene = true;
      contextPointer.x = event.clientX;
      contextPointer.y = event.clientY;
      contextPointer.pointerType = event.pointerType || "";
    }

    function shouldOpenContextMenuFromRelease(event) {
      if (!contextPointer.startedInScene || contextPointer.blocked || contextPointer.moved) {
        return false;
      }
      if (primaryPointer.active || primaryButtonHeld(event) || chordButtonsHeld(event)) {
        return false;
      }
      const tapSlop = tapSlopForPointer(contextPointer.pointerType || event.pointerType);
      const moved = Math.hypot(event.clientX - contextPointer.x, event.clientY - contextPointer.y);
      return moved <= tapSlop;
    }

    function openContextMenuFromEvent(event, { suppressNativeContextMenu = true } = {}) {
      clearPendingActivation();
      if (suppressNativeContextMenu) {
        contextMenuGesture.suppressNextContextMenu();
      }
      const referenceId = pickActivationReference(event.clientX, event.clientY, event.pointerType || contextPointer.pointerType || "") || "";
      onContextReferenceRef.current?.(referenceId || "", {
        clientX: event.clientX,
        clientY: event.clientY,
        multiSelect: !!event.shiftKey
      });
      resetContextPointer();
    }

    function releaseContextPointer(event) {
      if (!contextPointer.startedInScene && !contextMenuGesture.isSuppressed()) {
        contextPointer.active = false;
        return;
      }
      if (shouldOpenContextMenuFromRelease(event)) {
        openContextMenuFromEvent(event);
        return;
      }
      contextMenuGesture.suppressNextContextMenu();
      resetContextPointer();
    }

    function updateContextPointerMove(event) {
      if (!contextPointer.active) {
        return;
      }
      const tapSlop = tapSlopForPointer(contextPointer.pointerType || event.pointerType);
      const moved = Math.hypot(event.clientX - contextPointer.x, event.clientY - contextPointer.y);
      if (moved > tapSlop) {
        contextPointer.blocked = true;
        contextPointer.moved = true;
        suppressContextMenuFromPanChord();
      }
    }

    function handlePointerDownCapture(event) {
      if (!isSceneEvent(event)) {
        return;
      }
      if (event.button === 0) {
        if (contextPointer.active || contextButtonHeld(event) || chordButtonsHeld(event)) {
          suppressContextMenuFromPanChord();
        } else {
          recordPrimaryPointerDown(event);
        }
        return;
      }
      if (event.button !== 2) {
        return;
      }
      recordContextPointerDown(event);
      if (pointerDown.active || primaryPointer.active || primaryButtonHeld(event) || chordButtonsHeld(event)) {
        suppressContextMenuFromPanChord();
      }
    }

    function handleMouseDownCapture(event) {
      if (!isSceneEvent(event)) {
        return;
      }
      if (event.button === 0) {
        if (contextPointer.active || contextButtonHeld(event) || chordButtonsHeld(event)) {
          suppressContextMenuFromPanChord();
        } else {
          recordPrimaryPointerDown(event);
        }
        return;
      }
      if (event.button !== 2) {
        return;
      }
      recordContextPointerDown(event);
      if (pointerDown.active || primaryPointer.active || primaryButtonHeld(event) || chordButtonsHeld(event)) {
        suppressContextMenuFromPanChord();
      }
    }

    function handlePointerMoveCapture(event) {
      if (!isActiveSceneGestureEvent(event)) {
        return;
      }
      updateContextPointerMove(event);
      if (chordButtonsHeld(event) || (primaryPointer.active && contextButtonHeld(event))) {
        suppressContextMenuFromPanChord();
      }
    }

    function handleMouseMoveCapture(event) {
      if (!isActiveSceneGestureEvent(event)) {
        return;
      }
      updateContextPointerMove(event);
      if (chordButtonsHeld(event) || (primaryPointer.active && contextButtonHeld(event))) {
        suppressContextMenuFromPanChord();
      }
    }

    function handlePointerUpCapture(event) {
      if (event.button === 0) {
        resetPrimaryPointer();
      } else if (event.button === 2) {
        contextPointer.active = false;
      }
    }

    function handleMouseUpCapture(event) {
      if (event.button === 0) {
        resetPrimaryPointer();
      } else if (event.button === 2) {
        releaseContextPointer(event);
      }
    }

    function handlePointerMove(event) {
      if (!isSceneInteractionTarget(event.target)) {
        clearHoverState();
        return;
      }
      if (primaryPointer.active && !primaryButtonHeld(event)) {
        resetPrimaryPointer();
      }
      if (chordButtonsHeld(event) || (primaryPointer.active && contextButtonHeld(event))) {
        suppressContextMenuFromPanChord();
      }
      updateContextPointerMove(event);
      if (runtime.interactionState.active) {
        clearHoverState();
        return;
      }
      const tapSlop = tapSlopForPointer(pointerDown.pointerType || event.pointerType);
      if (pointerDown.active) {
        const moved = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
        if (moved > tapSlop) {
          pointerDown.active = false;
        }
      }
      if (!canHoverWithPointer(event.pointerType)) {
        clearHoverState();
        return;
      }
      scheduleHoverPick(event.clientX, event.clientY);
    }

    function handlePointerLeave() {
      clearHoverState();
      if (pointerDown.active || primaryPointer.active || contextPointer.active) {
        suppressContextMenuFromPanChord();
      }
      pointerDown.active = false;
      pointerDown.pointerType = "";
      pointerDown.referenceId = "";
      resetPrimaryPointer();
    }

    function handlePointerDown(event) {
      if (event.button !== 0) {
        if (event.button === 2 && isSceneInteractionTarget(event.target)) {
          recordContextPointerDown(event);
          if (pointerDown.active || primaryPointer.active || primaryButtonHeld(event) || chordButtonsHeld(event)) {
            suppressContextMenuFromPanChord();
          }
        }
        return;
      }
      if (!isSceneInteractionTarget(event.target)) {
        return;
      }
      if (chordButtonsHeld(event) || contextButtonHeld(event)) {
        suppressContextMenuFromPanChord();
        return;
      }
      recordPrimaryPointerDown(event);
      pointerDown.active = true;
      pointerDown.x = event.clientX;
      pointerDown.y = event.clientY;
      pointerDown.pointerType = event.pointerType || "";
      pointerDown.referenceId = String(
        canHoverWithPointer(pointerDown.pointerType)
          ? (hoverState.hoveredReferenceId || pickReferenceAtPosition(event.clientX, event.clientY, { hover: true }) || "")
          : (pickReferenceAtPosition(event.clientX, event.clientY) || "")
      ).trim();
    }

    function handlePointerUp(event) {
      if (event.button === 0) {
        resetPrimaryPointer();
      } else if (event.button === 2) {
        contextPointer.active = false;
      }
      if (event.button !== 0) {
        return;
      }
      if (!pointerDown.active && !isSceneInteractionTarget(event.target)) {
        return;
      }
      const tapSlop = tapSlopForPointer(pointerDown.pointerType || event.pointerType);
      const moved = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
      if (!pointerDown.active || moved > tapSlop) {
        pointerDown.active = false;
        pointerDown.pointerType = "";
        pointerDown.referenceId = "";
        return;
      }
      const pointerDownReferenceId = String(pointerDown.referenceId || "").trim();
      pointerDown.active = false;
      pointerDown.pointerType = "";
      pointerDown.referenceId = "";
      if (suppressTopologyPicking) {
        return;
      }
      if (pickModeRef.current === VIEWER_PICK_MODE.MEASURE) {
        onMeasurePickRef.current?.(measureReferenceFromPosition(pointerDown.x, pointerDown.y, {
          bypassTopology: !!event.shiftKey
        }).pick);
        return;
      }
      const referenceId = pointerDownReferenceId || pickActivationReference(event.clientX, event.clientY, event.pointerType || "");
      scheduleActivation(referenceId || "", { multiSelect: !!event.shiftKey });
    }

    function handleDoubleClick(event) {
      if (!isSceneInteractionTarget(event.target)) {
        return;
      }
      clearPendingActivation();
      if (suppressTopologyPicking) {
        return;
      }
      const referenceId = pickActivationReference(event.clientX, event.clientY, event.pointerType || "");
      onDoubleActivateReferenceRef.current?.(referenceId || "", { multiSelect: !!event.shiftKey });
    }

    function handleContextMenu(event) {
      if (!isSceneEvent(event)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      clearPendingActivation();
      contextMenuGesture.consumeSuppression();
      if (!contextPointer.startedInScene) {
        resetContextPointer();
      }
    }

    container.addEventListener("pointerdown", handlePointerDownCapture, true);
    container.addEventListener("pointermove", handlePointerMoveCapture, true);
    container.addEventListener("pointerup", handlePointerUpCapture, true);
    document.addEventListener("mousedown", handleMouseDownCapture, true);
    document.addEventListener("mousemove", handleMouseMoveCapture, true);
    document.addEventListener("mouseup", handleMouseUpCapture, true);
    document.addEventListener("contextmenu", handleContextMenu, true);
    container.addEventListener("pointermove", handlePointerMove);
    container.addEventListener("pointerleave", handlePointerLeave);
    container.addEventListener("pointerdown", handlePointerDown);
    container.addEventListener("pointerup", handlePointerUp);
    if (doubleClickEnabled) {
      container.addEventListener("dblclick", handleDoubleClick);
    }

    return () => {
      container.removeEventListener("pointerdown", handlePointerDownCapture, true);
      container.removeEventListener("pointermove", handlePointerMoveCapture, true);
      container.removeEventListener("pointerup", handlePointerUpCapture, true);
      document.removeEventListener("mousedown", handleMouseDownCapture, true);
      document.removeEventListener("mousemove", handleMouseMoveCapture, true);
      document.removeEventListener("mouseup", handleMouseUpCapture, true);
      document.removeEventListener("contextmenu", handleContextMenu, true);
      container.removeEventListener("pointermove", handlePointerMove);
      container.removeEventListener("pointerleave", handlePointerLeave);
      container.removeEventListener("pointerdown", handlePointerDown);
      container.removeEventListener("pointerup", handlePointerUp);
      if (doubleClickEnabled) {
        container.removeEventListener("dblclick", handleDoubleClick);
      }
      contextMenuGesture.clear();
      clearPendingActivation();
      clearHoverState();
      container.style.cursor = "";
    };
  }, [
    drawingCanvasRef,
    mountRef,
    previewMode,
    runtimeRef,
    sceneMountRef,
    suppressTopologyPicking,
    viewerReadyTick
  ]);
}
