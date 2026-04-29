import { useEffect, useRef } from "react";
import { VIEWER_PICK_MODE } from "../../../lib/viewer/constants";
import { screenLimitedPickThreshold } from "../../../lib/viewer/pickingThresholds";

const FACE_BOUNDS_EPSILON = 0.25;
const PLANE_SURFACE_EPSILON = 0.25;
const CYLINDER_SURFACE_EPSILON = 0.35;
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
const CORNER_PICK_PRIORITY_WITH_OTHER_PX = 4;
const CORNER_HOVER_PRIORITY_WITH_OTHER_PX = 3;
const HOVER_PICK_MIN_MOVE_PX = 2;
const FINE_POINTER_TAP_SLOP_PX = 4;
const COARSE_POINTER_TAP_SLOP_PX = 12;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function subtract(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function dot(a, b) {
  return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2]);
}

function length(vector) {
  return Math.sqrt(dot(vector, vector));
}

function normalizeAngleAround(angle, center) {
  let adjusted = angle;
  while (adjusted - center > Math.PI) {
    adjusted -= Math.PI * 2;
  }
  while (adjusted - center < -Math.PI) {
    adjusted += Math.PI * 2;
  }
  return adjusted;
}

function pointInBounds(point, bounds, epsilon = 0.8) {
  if (!Array.isArray(point) || point.length !== 3 || !bounds || !Array.isArray(bounds.min) || !Array.isArray(bounds.max)) {
    return false;
  }
  return (
    point[0] >= Number(bounds.min[0] || 0) - epsilon &&
    point[0] <= Number(bounds.max[0] || 0) + epsilon &&
    point[1] >= Number(bounds.min[1] || 0) - epsilon &&
    point[1] <= Number(bounds.max[1] || 0) + epsilon &&
    point[2] >= Number(bounds.min[2] || 0) - epsilon &&
    point[2] <= Number(bounds.max[2] || 0) + epsilon
  );
}

function pointInPolygon2d(point, polygon) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index, index += 1) {
    const x1 = polygon[index][0];
    const y1 = polygon[index][1];
    const x2 = polygon[previous][0];
    const y2 = polygon[previous][1];
    const intersects = ((y1 > point[1]) !== (y2 > point[1])) &&
      (point[0] < ((x2 - x1) * (point[1] - y1)) / ((y2 - y1) || 1e-9) + x1);
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}

function distancePointToSegment2d(point, start, end) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) {
    return Math.hypot(point[0] - start[0], point[1] - start[1]);
  }
  const t = clamp(
    ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy),
    0,
    1
  );
  const projected = [start[0] + dx * t, start[1] + dy * t];
  return Math.hypot(point[0] - projected[0], point[1] - projected[1]);
}

function distancePointToLoop2d(point, loop) {
  let best = Infinity;
  for (let index = 0, previous = loop.length - 1; index < loop.length; previous = index, index += 1) {
    best = Math.min(best, distancePointToSegment2d(point, loop[previous], loop[index]));
  }
  return best;
}

function compareReferenceIdentity(a, b) {
  const aKey = String(a?.entityId ?? a?.id ?? "");
  const bKey = String(b?.entityId ?? b?.id ?? "");
  return aKey.localeCompare(bKey);
}

function projectPointToPlane(point, surface) {
  const origin = surface.origin || [0, 0, 0];
  const relative = subtract(point, origin);
  return [dot(relative, surface.xDir || [1, 0, 0]), dot(relative, surface.yDir || [0, 1, 0])];
}

function projectPointToCylinder(point, surface, thetaCenter) {
  const origin = surface.origin || [0, 0, 0];
  const axis = surface.axis || [0, 1, 0];
  const xDir = surface.xDir || [1, 0, 0];
  const yDir = surface.yDir || [0, 0, 1];
  const relative = subtract(point, origin);
  const axial = dot(relative, axis);
  const radial = [
    relative[0] - axis[0] * axial,
    relative[1] - axis[1] * axial,
    relative[2] - axis[2] * axial
  ];
  const theta = normalizeAngleAround(Math.atan2(dot(radial, yDir), dot(radial, xDir)), thetaCenter);
  return [theta * (surface.radius || 1), axial];
}

function measurePointInsideLoops(projectedPoint, loops2d) {
  const crossings = loops2d.reduce((count, loop) => count + (pointInPolygon2d(projectedPoint, loop) ? 1 : 0), 0);
  if (crossings % 2 !== 1) {
    return null;
  }
  const boundaryDistance = loops2d.reduce(
    (best, loop) => Math.min(best, distancePointToLoop2d(projectedPoint, loop)),
    Infinity
  );
  return {
    boundaryDistance
  };
}

function faceMatchAtPoint(reference, point) {
  const pickData = reference?.pickData;
  if (!pickData?.loops?.length || !pointInBounds(point, pickData.bbox, FACE_BOUNDS_EPSILON)) {
    return null;
  }

  const surface = pickData.surface || {};

  if (surface.type === "PLANE" && surface.origin && surface.normal && surface.xDir && surface.yDir) {
    const planeDistance = Math.abs(dot(subtract(point, surface.origin), surface.normal));
    if (planeDistance > PLANE_SURFACE_EPSILON) {
      return null;
    }
    const projectedPoint = projectPointToPlane(point, surface);
    const loops2d = pickData.loops.map((loop) => loop.map((loopPoint) => projectPointToPlane(loopPoint, surface)));
    const loopMatch = measurePointInsideLoops(projectedPoint, loops2d);
    if (!loopMatch) {
      return null;
    }
    return {
      boundaryDistance: loopMatch.boundaryDistance,
      surfaceDistance: planeDistance
    };
  }

  if (surface.type === "CYLINDRICAL_SURFACE" && surface.origin && surface.axis && surface.xDir && surface.yDir) {
    const origin = surface.origin;
    const axis = surface.axis;
    const relative = subtract(point, origin);
    const axial = dot(relative, axis);
    const radial = [
      relative[0] - axis[0] * axial,
      relative[1] - axis[1] * axial,
      relative[2] - axis[2] * axial
    ];
    const radialDistance = length(radial);
    const radialError = Math.abs(radialDistance - surface.radius);
    if (!surface.radius || radialError > CYLINDER_SURFACE_EPSILON) {
      return null;
    }
    const pointTheta = Math.atan2(dot(radial, surface.yDir), dot(radial, surface.xDir));
    const projectedPoint = projectPointToCylinder(point, surface, pointTheta);
    const loops2d = pickData.loops.map((loop) =>
      loop.map((loopPoint) => projectPointToCylinder(loopPoint, surface, pointTheta))
    );
    const loopMatch = measurePointInsideLoops(projectedPoint, loops2d);
    if (!loopMatch) {
      return null;
    }
    return {
      boundaryDistance: loopMatch.boundaryDistance,
      surfaceDistance: radialError
    };
  }

  return null;
}

function faceLoopCount(reference) {
  return reference?.loopCount ?? reference?.pickData?.loopCount ?? reference?.pickData?.loops?.length ?? 0;
}

function isPreferredFaceReference(reference) {
  return faceLoopCount(reference) <= 1;
}

function chooseRedirectFaceReference(reference, point, references) {
  const pickData = reference?.pickData;
  const surface = pickData?.surface || {};
  if (isPreferredFaceReference(reference) || surface.type !== "PLANE" || !surface.origin || !surface.xDir || !surface.yDir) {
    return null;
  }

  const projectedPoint = projectPointToPlane(point, surface);
  const loopEntries = Array.isArray(pickData.loopsMeta) ? pickData.loopsMeta : [];
  const faceByEntityId = new Map(
    (Array.isArray(references) ? references : [])
      .filter((candidate) => candidate?.entityType === "ADVANCED_FACE")
      .map((candidate) => [candidate.entityId, candidate])
  );
  const redirectCandidates = [];

  for (const loopEntry of loopEntries) {
    if (loopEntry?.isOuter || !Array.isArray(loopEntry.points) || loopEntry.points.length < 3) {
      continue;
    }
    const loop2d = loopEntry.points.map((loopPoint) => projectPointToPlane(loopPoint, surface));
    const inside = pointInPolygon2d(projectedPoint, loop2d);
    const distance = distancePointToLoop2d(projectedPoint, loop2d);
    if (!inside && distance > 1.1) {
      continue;
    }

    for (const faceEntityId of loopEntry.adjacentFaceEntityIds || []) {
      const candidate = faceByEntityId.get(faceEntityId);
      if (!candidate || !isPreferredFaceReference(candidate)) {
        continue;
      }
      redirectCandidates.push({
        candidate,
        distance,
        inside
      });
    }
  }

  redirectCandidates.sort((a, b) => {
    if (a.inside !== b.inside) {
      return a.inside ? -1 : 1;
    }
    if (Math.abs(a.distance - b.distance) > 1e-4) {
      return a.distance - b.distance;
    }
    const aMetric = a.candidate.pickData?.metric ?? Infinity;
    const bMetric = b.candidate.pickData?.metric ?? Infinity;
    if (aMetric !== bMetric) {
      return aMetric - bMetric;
    }
    return compareReferenceIdentity(a.candidate, b.candidate);
  });

  return redirectCandidates[0]?.candidate || null;
}

function compareFaceCandidates(a, b) {
  const aSurfaceDistance = a.match?.surfaceDistance ?? Infinity;
  const bSurfaceDistance = b.match?.surfaceDistance ?? Infinity;
  if (Math.abs(aSurfaceDistance - bSurfaceDistance) > 1e-4) {
    return aSurfaceDistance - bSurfaceDistance;
  }

  const aBoundaryDistance = a.match?.boundaryDistance ?? -Infinity;
  const bBoundaryDistance = b.match?.boundaryDistance ?? -Infinity;
  if (Math.abs(aBoundaryDistance - bBoundaryDistance) > 1e-4) {
    return bBoundaryDistance - aBoundaryDistance;
  }

  const aMetric = a.reference.pickData?.metric ?? Infinity;
  const bMetric = b.reference.pickData?.metric ?? Infinity;
  if (Math.abs(aMetric - bMetric) > 1e-4) {
    return bMetric - aMetric;
  }

  const aPreferred = isPreferredFaceReference(a.reference) ? 0 : 1;
  const bPreferred = isPreferredFaceReference(b.reference) ? 0 : 1;
  if (aPreferred !== bPreferred) {
    return aPreferred - bPreferred;
  }

  return compareReferenceIdentity(a.reference, b.reference);
}

function findBestFaceReference(references, point) {
  const matches = [];
  for (const reference of Array.isArray(references) ? references : []) {
    const match = faceMatchAtPoint(reference, point);
    if (!match) {
      continue;
    }
    matches.push({
      match,
      reference
    });
  }
  matches.sort(compareFaceCandidates);
  return matches[0]?.reference || null;
}

function chooseBestFaceReferenceFromIntersections(references, intersections) {
  const candidates = new Map();
  for (const intersection of intersections) {
    if (!intersection?.point || !intersection?.object) {
      continue;
    }
    const localPoint = intersection.object.worldToLocal(intersection.point.clone());
    const point = [localPoint.x, localPoint.y, localPoint.z];
    let reference = findBestFaceReference(references, point);
    const redirected = chooseRedirectFaceReference(reference, point, references);
    if (redirected) {
      reference = redirected;
    }
    if (!reference) {
      continue;
    }
    const existing = candidates.get(reference.id);
    if (!existing || intersection.distance < existing.distance) {
      candidates.set(reference.id, {
        distance: intersection.distance,
        reference
      });
    }
  }

  const scored = [...candidates.values()];
  scored.sort((a, b) => {
    if (Math.abs(a.distance - b.distance) > 1e-4) {
      return a.distance - b.distance;
    }
    const aMetric = a.reference.pickData?.metric ?? Infinity;
    const bMetric = b.reference.pickData?.metric ?? Infinity;
    if (aMetric !== bMetric) {
      return aMetric - bMetric;
    }
    const aPreferred = isPreferredFaceReference(a.reference) ? 0 : 1;
    const bPreferred = isPreferredFaceReference(b.reference) ? 0 : 1;
    if (aPreferred !== bPreferred) {
      return aPreferred - bPreferred;
    }
    return compareReferenceIdentity(a.reference, b.reference);
  });
  return scored[0]?.reference || null;
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
  focusedPartId,
  onHoverReferenceChange,
  onActivateReference,
  onDoubleActivateReference,
  viewerReadyTick
}) {
  // Keep pointer listeners stable across parent rerenders; hover itself updates parent state.
  const pickModeRef = useRef(pickMode);
  const selectorRuntimeRef = useRef(selectorRuntime);
  const pickableFacesRef = useRef(pickableFaces);
  const pickableEdgesRef = useRef(pickableEdges);
  const pickableVerticesRef = useRef(pickableVertices);
  const focusedPartIdRef = useRef(focusedPartId);
  const onHoverReferenceChangeRef = useRef(onHoverReferenceChange);
  const onActivateReferenceRef = useRef(onActivateReference);
  const onDoubleActivateReferenceRef = useRef(onDoubleActivateReference);
  const allowedFaceReferenceIdsRef = useRef(new Set());
  const allowedEdgeReferenceIdsRef = useRef(new Set());
  const allowedVertexReferenceIdsRef = useRef(new Set());

  pickModeRef.current = pickMode;
  selectorRuntimeRef.current = selectorRuntime;
  pickableFacesRef.current = pickableFaces;
  pickableEdgesRef.current = pickableEdges;
  pickableVerticesRef.current = pickableVertices;
  focusedPartIdRef.current = focusedPartId;
  onHoverReferenceChangeRef.current = onHoverReferenceChange;
  onActivateReferenceRef.current = onActivateReference;
  onDoubleActivateReferenceRef.current = onDoubleActivateReference;
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
    const hoverState = {
      rafId: 0,
      x: 0,
      y: 0,
      lastX: NaN,
      lastY: NaN,
      hoveredReferenceId: ""
    };

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
      const focusId = String(focusedPartIdRef.current || "").trim();
      return runtime.displayRecords
        .filter((record) => {
          if (!record?.mesh?.visible) {
            return false;
          }
          if (focusId && String(record?.partId || "").trim() !== focusId) {
            return false;
          }
          return true;
        })
        .map((record) => record.mesh);
    }

    function intersectVisibleModelMeshes() {
      const modelMeshes = visibleModelMeshes();
      if (!modelMeshes.length) {
        return [];
      }
      return runtime.raycaster.intersectObjects(modelMeshes, false);
    }

    function pickPartReferenceFromIntersections(intersections) {
      const focusId = String(focusedPartIdRef.current || "").trim();
      for (const intersection of intersections) {
        const partId = intersection?.object?.userData?.partId;
        if (!partId) {
          continue;
        }
        if (focusId && partId !== focusId) {
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
      if (!runtime.facePickMesh || !(Array.isArray(pickableFacesRef.current) ? pickableFacesRef.current : []).length) {
        return null;
      }
      const intersections = runtime.raycaster.intersectObject(runtime.facePickMesh, false);
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
      let filteredIntersections = runtime.raycaster.intersectObject(runtime.edgePickLines, false);
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
      let filteredIntersections = runtime.raycaster.intersectObject(runtime.vertexPickPoints, false);
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

    function pickReferenceAtPosition(clientX, clientY, { hover = false } = {}) {
      setPointerFromPosition(clientX, clientY);
      const modelIntersections = intersectVisibleModelMeshes();
      const pickMode = pickModeRef.current;
      if (pickMode === VIEWER_PICK_MODE.PARTS) {
        return pickPartReferenceFromIntersections(modelIntersections);
      }
      if (pickMode === VIEWER_PICK_MODE.ASSEMBLY) {
        return pickPartReferenceFromIntersections(modelIntersections);
      }
      if (pickMode === VIEWER_PICK_MODE.AUTO) {
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

    function commitHoverState(referenceId) {
      const normalizedReferenceId = referenceId || "";
      container.style.cursor = normalizedReferenceId ? "pointer" : "";
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
      container.style.cursor = "";
      if (!hoverState.hoveredReferenceId) {
        return;
      }
      hoverState.hoveredReferenceId = "";
      onHoverReferenceChangeRef.current?.("");
    }

    function flushHoverPick() {
      hoverState.rafId = 0;
      if (runtime.interactionState.active) {
        clearHoverState();
        return;
      }
      hoverState.lastX = hoverState.x;
      hoverState.lastY = hoverState.y;
      commitHoverState(pickReferenceAtPosition(hoverState.x, hoverState.y, { hover: true }));
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

    function handlePointerMove(event) {
      if (!isSceneInteractionTarget(event.target)) {
        clearHoverState();
        return;
      }
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
      pointerDown.active = false;
      pointerDown.pointerType = "";
      pointerDown.referenceId = "";
    }

    function handlePointerDown(event) {
      if (event.button !== 0) {
        return;
      }
      if (!isSceneInteractionTarget(event.target)) {
        return;
      }
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
      const referenceId = pointerDownReferenceId || pickActivationReference(event.clientX, event.clientY, event.pointerType || "");
      onActivateReferenceRef.current?.(referenceId || "", {
        multiSelect: !!event.shiftKey,
        clientX: event.clientX,
        clientY: event.clientY
      });
    }

    function handleDoubleClick(event) {
      if (!isSceneInteractionTarget(event.target)) {
        return;
      }
      const referenceId = pickActivationReference(event.clientX, event.clientY, event.pointerType || "");
      onDoubleActivateReferenceRef.current?.(referenceId || "", {
        multiSelect: !!event.shiftKey,
        clientX: event.clientX,
        clientY: event.clientY
      });
    }

    container.addEventListener("pointermove", handlePointerMove);
    container.addEventListener("pointerleave", handlePointerLeave);
    container.addEventListener("pointerdown", handlePointerDown);
    container.addEventListener("pointerup", handlePointerUp);
    if (!defaultToCoarsePointer) {
      container.addEventListener("dblclick", handleDoubleClick);
    }

    return () => {
      container.removeEventListener("pointermove", handlePointerMove);
      container.removeEventListener("pointerleave", handlePointerLeave);
      container.removeEventListener("pointerdown", handlePointerDown);
      container.removeEventListener("pointerup", handlePointerUp);
      if (!defaultToCoarsePointer) {
        container.removeEventListener("dblclick", handleDoubleClick);
      }
      clearHoverState();
      container.style.cursor = "";
    };
  }, [
    drawingCanvasRef,
    mountRef,
    previewMode,
    runtimeRef,
    sceneMountRef,
    viewerReadyTick
  ]);
}
