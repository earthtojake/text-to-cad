import { edgeGeometryFromSegments } from "@text-to-cad/core/lib/viewer/measurement.js";
import { xbfSegments } from "@text-to-cad/core/lib/xbf/xbfEntities.js";
import { planeOfPoints } from "../kit/camera/lookAt.js";

// A face or edge of an engine document as a look-at subject (`kit/camera/lookAt.js`): what a
// double-click on it turns the view square to, as a STEP's face or edge was. Where it stands now,
// as the view draws it (the pose and Explode included: `scene.elementGeometry`). A face's kind and
// axes are its surface's, read off its mesh (`xbfEntities.js`): a plane by its normal, a
// cylinder's side by its axis, origin and radius, any other face free. An edge is what its
// polyline is, as Measure reads it: straight, a circle (flat, about its centre), else free.

/**
 * @param {object} scene  The document's scene (`createXbfScene`).
 * @param {string} id  A face or an edge (`i3/face/12`, `i3/edge/4`).
 * @returns {import("../kit/camera/lookAt.js").LookSubject | null}
 */
export function xbfLookSubject(scene, id) {
  const element = scene?.elementGeometry?.(id, { points: true });
  if (!element?.points?.length) return null;
  const { points } = element;
  if (element.kind === "face") {
    const surface = element.surface;
    if (surface.type === "plane") return { kind: "plane", normal: surface.normal, origin: surface.origin, points };
    if (surface.type === "cylinder") return { kind: "cylinder", axis: surface.axis, origin: surface.origin, radius: surface.radius, points };
    return { kind: "free", points };
  }
  if (element.kind !== "edge") return null;
  const shape = edgeGeometryFromSegments(xbfSegments(points));
  if (shape?.kind === "line" && shape.direction) return { kind: "line", direction: shape.direction, points };
  if (shape?.kind === "arc" && shape.center) {
    const span = Math.max(...points.map(point => Math.hypot(...point.map((c, i) => c - points[0][i]))));
    const flat = planeOfPoints(points, Math.max(span * 0.01, 1e-6));
    if (flat) return { kind: "circle", axis: flat.normal, center: shape.center, points };
  }
  return { kind: "free", points };
}
