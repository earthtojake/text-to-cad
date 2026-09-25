import { useEffect, useMemo, useRef } from "react";
import { VIEWER_PICK_MODE } from "@hardcore/core/lib/viewer/constants.js";
import {
  classifyMeasurePick,
  edgeGeometryFromSegments,
  isFinitePoint
} from "@hardcore/core/lib/viewer/measurement.js";
import { buildEdgeLinePositionsFromProxy } from "@hardcore/core/lib/viewer/referenceGeometry.js";
import { pointVisibleByClipPlane } from "@hardcore/core/lib/viewer/clipPlane.js";
import { screenLimitedPickThreshold } from "@hardcore/core/lib/viewer/pickingThresholds.js";
import { PERF_MEASURE_NAMES, perfMeasure, perfStart } from "@hardcore/core/lib/viewer/perfMarks.js";
import { partIdFromIntersection, shouldRaycastRecordForPick } from "./partPicking.js";
import { prefersCoarsePointer } from "../../kit/viewport/dom.js";

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
const HOVER_PICK_MIN_MOVE_PX = 2;
const FINE_POINTER_TAP_SLOP_PX = 4;
const COARSE_POINTER_TAP_SLOP_PX = 12;
export const VIEWER_DOUBLE_CLICK_ACTIVATION_DELAY_MS = 220;

/**
 * What a pick at one point resolves to under the pick mode, from ONE raycast of the model:
 * the part under Parts and Assembly; topology, else the part, under Auto; topology under
 * Measure; topology, else the part, under Topology (a face or edge filter), whose surface
 * never selects that part: a hover lights it, so the pointer shows what a press there
 * reaches, and a press asks for its faces — by mouse or by touch alike. Nothing at all while
 * picking is off: every press and release asks, and a raycast can materialize deformation
 * buffers and enqueue a BVH build for an answer that is always "nothing".
 */
export function resolveViewerReferencePick({
  pickMode,
  suppressTopologyPicking = false,
  intersectModel,
  pickTopology,
  pickPart
}) {
  if (suppressTopologyPicking || pickMode === VIEWER_PICK_MODE.NONE) {
    return null;
  }
  const intersections = intersectModel();
  if (pickMode === VIEWER_PICK_MODE.PARTS || pickMode === VIEWER_PICK_MODE.ASSEMBLY) {
    return pickPart(intersections);
  }
  if (pickMode === VIEWER_PICK_MODE.AUTO) {
    return pickTopology(intersections) || pickPart(intersections);
  }
  if (pickMode === VIEWER_PICK_MODE.MEASURE) {
    return pickTopology(intersections);
  }
  if (pickMode === VIEWER_PICK_MODE.TOPOLOGY) {
    return pickTopology(intersections) || pickPart(intersections);
  }
  return null;
}

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
    edgeGeometry
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

function referenceIdSet(references) {
  return new Set(
    (Array.isArray(references) ? references : []).map((reference) => String(reference?.id || "").trim()).filter(Boolean)
  );
}

function partIdSet(value) {
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

export function useStepPicking({
  runtimeRef,
  mountRef,
  sceneMountRef = null,
  previewMode,
  pickMode,
  selectorRuntime,
  pickableFaces,
  pickableEdges,
  hiddenPartIds,
  focusedPartId,
  onHoverReferenceChange,
  onActivateReference,
  onDoubleActivateReference,
  // What is under a point of the screen right now, for the viewport menu: set while the
  // listeners are bound, null otherwise. (clientX, clientY, pointerType) -> reference id or "".
  pickAtRef = null,
  onMeasurePick,
  onMeasureHoverPoint,
  viewerReadyTick,
  // While a STEP animation is playing, reference hover/selection is suspended
  // so playback frames skip raycasts and pick-state rebuilds entirely.
  suppressTopologyPicking = false
}) {
  // Keep pointer listeners stable across parent rerenders; hover itself updates parent state.
  // The listeners read everything that changes through these refs, so nothing here re-binds
  // them: not a pose tick (a posed selector runtime), not a hover, not a new pickable list.
  const pickModeRef = useRef(pickMode);
  const selectorRuntimeRef = useRef(selectorRuntime);
  const pickableFacesRef = useRef(pickableFaces);
  const pickableEdgesRef = useRef(pickableEdges);
  const onHoverReferenceChangeRef = useRef(onHoverReferenceChange);
  const onActivateReferenceRef = useRef(onActivateReference);
  const onDoubleActivateReferenceRef = useRef(onDoubleActivateReference);
  const onMeasurePickRef = useRef(onMeasurePick);
  const onMeasureHoverPointRef = useRef(onMeasureHoverPoint);

  pickModeRef.current = pickMode;
  selectorRuntimeRef.current = selectorRuntime;
  pickableFacesRef.current = pickableFaces;
  pickableEdgesRef.current = pickableEdges;
  onHoverReferenceChangeRef.current = onHoverReferenceChange;
  onActivateReferenceRef.current = onActivateReference;
  onDoubleActivateReferenceRef.current = onDoubleActivateReference;
  onMeasurePickRef.current = onMeasurePick;
  onMeasureHoverPointRef.current = onMeasureHoverPoint;
  // The id sets a pick is checked against, built when their lists change rather than on every
  // render (the layers render per orbit frame) or every pick.
  const pickSetsRef = useRef(null);
  pickSetsRef.current = {
    faces: useMemo(() => referenceIdSet(pickableFaces), [pickableFaces]),
    edges: useMemo(() => referenceIdSet(pickableEdges), [pickableEdges]),
    hidden: useMemo(() => partIdSet(hiddenPartIds), [hiddenPartIds]),
    focused: useMemo(() => partIdSet(focusedPartId), [focusedPartId])
  };

  // Arming the tool has to change the cursor immediately. Leaving it to the next
  // hover tick means the select pointer lingers until the mouse happens to move.
  useEffect(() => {
    const container = mountRef.current;
    if (!container || previewMode || pickMode !== VIEWER_PICK_MODE.MEASURE) {
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
    const defaultToCoarsePointer = prefersCoarsePointer();
    const touches = new Set();
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
      contextPointer.blocked = true;
      contextPointer.moved = true;
      pointerDown.active = false;
      pointerDown.pointerType = "";
      pointerDown.referenceId = "";
    }

    // The viewport's box, read ONCE per pick (every pick starts by aiming the ray) and reused
    // by every candidate it scores, rather than a layout read per candidate.
    let pickRect = null;
    function setPointerFromPosition(clientX, clientY) {
      pickRect = container.getBoundingClientRect();
      runtime.pointer.x = ((clientX - pickRect.left) / pickRect.width) * 2 - 1;
      runtime.pointer.y = -((clientY - pickRect.top) / pickRect.height) * 2 + 1;
      runtime.raycaster.setFromCamera(runtime.pointer, runtime.camera);
      if (runtime.raycaster?.params?.Line) {
        runtime.raycaster.params.Line.threshold = runtime.edgePickThreshold || 1;
      }
    }

    function projectPointToClient(point) {
      if (!point?.clone || !runtime?.camera || !pickRect) {
        return null;
      }
      const projected = point.clone().project(runtime.camera);
      if (!Number.isFinite(projected.x) || !Number.isFinite(projected.y)) {
        return null;
      }
      const rect = pickRect;
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
      return pickRect?.height || 1;
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
      const { focused: focusIds, hidden: hiddenIds } = pickSetsRef.current;
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
      const { focused: focusIds, hidden: hiddenIds } = pickSetsRef.current;
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
      const allowedFaceReferenceIds = pickSetsRef.current.faces;
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
      const allowedEdgeReferenceIds = pickSetsRef.current.edges;
      if (!referenceId || (allowedEdgeReferenceIds.size && !allowedEdgeReferenceIds.has(referenceId))) {
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

    function pickTopologyReference(modelIntersections, clientX, clientY, { hover = false } = {}) {
      const pickableFaces = Array.isArray(pickableFacesRef.current) ? pickableFacesRef.current : [];
      const pickableEdges = Array.isArray(pickableEdgesRef.current) ? pickableEdgesRef.current : [];
      if (!pickableFaces.length && !pickableEdges.length) {
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
      return edgeCandidate?.reference?.id || faceReference?.id || null;
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

    // Hover re-resolves the same edge every tick, and both the proxy slice and the geometry fit
    // are functions of the reference in the selector runtime it came from — which a pose
    // replaces, so the runtime is part of the key.
    let measureEdgeCache = { runtime: null, referenceId: "", segments: null, geometry: null };

    function measureSnapGeometry(reference, referenceId) {
      const selectorType = String(reference?.pickData?.selectorType || reference?.selectorType || "")
        .trim()
        .toLowerCase();
      if (selectorType !== "edge") {
        return { edgeSegments: null, edgeGeometry: null };
      }
      const selectorRuntime = selectorRuntimeRef.current;
      if (measureEdgeCache.referenceId !== referenceId || measureEdgeCache.runtime !== selectorRuntime) {
        const segments = buildEdgeLinePositionsFromProxy(selectorRuntime, reference);
        measureEdgeCache = { runtime: selectorRuntime, referenceId, segments, geometry: edgeGeometryFromSegments(segments) };
      }
      return { edgeSegments: measureEdgeCache.segments, edgeGeometry: measureEdgeCache.geometry };
    }

    function measureReferenceFromPosition(clientX, clientY, { hover = false, bypassTopology = false } = {}) {
      setPointerFromPosition(clientX, clientY);
      const modelIntersections = intersectVisibleModelMeshes();
      const hitIntersection = frontMostModelIntersections(modelIntersections)
        .find((intersection) => measureHitPointFromWorldIntersection(intersection)) || null;
      const worldHitPoint = measureHitPointFromWorldIntersection(hitIntersection);
      const modelOffset = measureModelOffsetFromRuntime(runtimeRef.current);
      const referenceId = bypassTopology ? "" : (pickTopologyReference(modelIntersections, clientX, clientY, { hover }) || "");
      const reference = referenceId ? measureReferenceById(referenceId) : null;
      const { edgeSegments, edgeGeometry } = bypassTopology
        ? { edgeSegments: null, edgeGeometry: null }
        : measureSnapGeometry(reference, referenceId);
      return {
        pick: measurePickForPosition({
          reference,
          worldHitPoint,
          referenceId,
          bypassTopology,
          edgeSegments,
          edgeGeometry,
          modelOffset
        }),
        referenceId
      };
    }

    function pickReferenceAtPosition(clientX, clientY, { hover = false } = {}) {
      return resolveViewerReferencePick({
        pickMode: pickModeRef.current,
        suppressTopologyPicking,
        intersectModel: () => {
          setPointerFromPosition(clientX, clientY);
          return intersectVisibleModelMeshes();
        },
        pickTopology: (intersections) => pickTopologyReference(intersections, clientX, clientY, { hover }),
        pickPart: pickPartReferenceFromIntersections
      });
    }

    function pickActivationReference(clientX, clientY, pointerType = "") {
      // Activation is infrequent and must resolve the coordinates of this
      // gesture. The cached hover can belong to a previous point or even the
      // selector runtime retired by a live scene replacement when pointer-down
      // arrives before the next hover frame.
      return String(pickReferenceAtPosition(clientX, clientY, {
        hover: canHoverWithPointer(pointerType)
      }) || "").trim();
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
      return Boolean(sceneMount?.contains(target));
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
      if (suppressTopologyPicking || pickModeRef.current === VIEWER_PICK_MODE.NONE) {
        clearHoverState();
        return;
      }
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

    // A secondary TAP is the viewport's own menu, whose gesture and items are mounted by the
    // renderer's frame. All this hook keeps of it is that a tap is not an activation in waiting.
    function releaseContextPointer() {
      if (contextPointer.startedInScene && !contextPointer.blocked && !contextPointer.moved) {
        clearPendingActivation();
      }
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
      const tapSlop = tapSlopForPointer(pointerDown.pointerType || event.pointerType);
      if (pointerDown.active) {
        const moved = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
        if (moved > tapSlop) {
          pointerDown.active = false;
        }
      }
      if (runtime.interactionState.active || !canHoverWithPointer(event.pointerType)) {
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
      if (event.pointerType === "touch") {
        touches.add(event.pointerId);
        if (touches.size > 1) { pointerDown.active = false; clearPendingActivation(); return; }
      }
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
      // OrbitControls may clear hover before pointer-up; retain the fresh
      // pointer-down raycast rather than the earlier hover frame.
      pointerDown.referenceId = pickActivationReference(
        event.clientX, event.clientY, pointerDown.pointerType,
      );
    }

    function handlePointerUp(event) {
      touches.delete(event.pointerId);
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
      const press = { clientX: pointerDown.x, clientY: pointerDown.y, pointerType: pointerDown.pointerType || event.pointerType || "" };
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
      // The press point goes with the activation, so a pick that has to wait (a part whose faces
      // are still loading) can be asked again at the same place.
      scheduleActivation(referenceId || "", { multiSelect: !!event.shiftKey, ...press });
    }

    function handlePointerCancel(event) {
      touches.delete(event.pointerId);
      pointerDown.active = false;
      pointerDown.referenceId = "";
      resetPrimaryPointer();
      clearHoverState();
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
      if (!contextPointer.startedInScene) {
        resetContextPointer();
      }
    }

    if (pickAtRef) pickAtRef.current = (clientX, clientY, pointerType = "") => pickActivationReference(clientX, clientY, pointerType) || "";
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
    container.addEventListener("pointercancel", handlePointerCancel);
    if (doubleClickEnabled) {
      container.addEventListener("dblclick", handleDoubleClick);
    }

    return () => {
      if (pickAtRef) pickAtRef.current = null;
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
      container.removeEventListener("pointercancel", handlePointerCancel);
      if (doubleClickEnabled) {
        container.removeEventListener("dblclick", handleDoubleClick);
      }
      clearPendingActivation();
      clearHoverState();
      container.style.cursor = "";
    };
  }, [
    mountRef,
    previewMode,
    runtimeRef,
    sceneMountRef,
    suppressTopologyPicking,
    viewerReadyTick
  ]);
}
