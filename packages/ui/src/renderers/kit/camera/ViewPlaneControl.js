import { memo, useRef, useState } from "react";
import { House } from "lucide-react";
import { VIEW_CUBE_CORNERS } from "./viewportCameraKit.js";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "./ProjectionModeIcons.js";

// The view cube. A cube drawn from the camera's orientation: its faces are the six plane
// views (click TOP, FRONT, RIGHT...) and its corners are the eight isometric views. The
// house beside it resets to the default isometric view and frames the model again. A small
// X/Y/Z triad under it keeps the axis colours the old gizmo carried.

const ORIENTATION_FALLBACK = Object.freeze({
  x: [1, 0, 0],
  y: [0, 1, 0],
  z: [0, 0, 1]
});

const FACE_LABELS = Object.freeze({ z: "TOP", zNeg: "BOTTOM", yNeg: "FRONT", y: "BACK", x: "RIGHT", xNeg: "LEFT" });
const AXIS_COLORS = Object.freeze({ x: "rgb(239, 83, 80)", y: "rgb(76, 175, 80)", z: "rgb(66, 133, 244)" });
const DEFAULT_VIEW_PLANE_SIZE = "6.71875rem";
// SVG units: the cube's half-size on screen, and where its centre sits.
const SCALE = 24;
const CENTER = 50;

function normalizeCssLength(value, fallback = "") {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) return `${value}px`;
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function normalizeAxis(axis, fallback) {
  if (!Array.isArray(axis) || axis.length !== 3) return [...fallback];
  const [x, y, z] = axis.map(Number);
  const magnitude = Math.hypot(x, y, z);
  if (![x, y, z].every(Number.isFinite) || magnitude < 1e-6) return [...fallback];
  return [x / magnitude, y / magnitude, z / magnitude];
}

function normalizeOrientation(orientation) {
  return {
    x: normalizeAxis(orientation?.x, ORIENTATION_FALLBACK.x),
    y: normalizeAxis(orientation?.y, ORIENTATION_FALLBACK.y),
    z: normalizeAxis(orientation?.z, ORIENTATION_FALLBACK.z)
  };
}

// World direction -> camera space: x right, y up, z toward the viewer.
function toView(orientation, [dx = 0, dy = 0, dz = 0]) {
  return [0, 1, 2].map((i) => orientation.x[i] * dx + orientation.y[i] * dy + orientation.z[i] * dz);
}

function toScreen(view, scale = SCALE, cx = CENTER, cy = CENTER) {
  return [cx + view[0] * scale, cy - view[1] * scale];
}

// A face's four corners, in order around it, from its outward normal.
function faceCorners(direction) {
  const axis = direction.findIndex((value) => value !== 0);
  const [u, v] = [0, 1, 2].filter((index) => index !== axis);
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => {
    const corner = [0, 0, 0];
    corner[axis] = direction[axis];
    corner[u] = a;
    corner[v] = b;
    return corner;
  });
}

// Which way is "up" on each face's label: Z on the sides, back (+Y) on top and bottom.
function faceLabelUp(direction) {
  return direction[2] !== 0 ? [0, 1, 0] : [0, 0, 1];
}

function cross([ax, ay, az], [bx, by, bz]) {
  return [ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx];
}

// The label lies ON its face: an affine map from the face's own flat coordinates (x along its
// right, y down it, each face spanning -1..1) to the screen. A face seen edge-on narrows, and
// its label narrows with it instead of spilling past the edge.
function faceLabelTransform(orientation, direction) {
  const up = faceLabelUp(direction);
  const right = cross(up, direction);
  const screenVector = (world) => {
    const view = toView(orientation, world);
    return [view[0] * SCALE, -view[1] * SCALE];
  };
  const [rx, ry] = screenVector(right);
  const [dx, dy] = screenVector(up.map((value) => -value));
  const [cx, cy] = toScreen(toView(orientation, direction));
  return `matrix(${rx} ${ry} ${dx} ${dy} ${cx} ${cy})`;
}

function activateOnKey(event, activate) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  event.stopPropagation();
  activate();
}

function ViewPlaneControl({
  showViewPlane,
  previewMode,
  isLoading,
  meshData,
  viewPlaneOffsetRight,
  viewPlaneOffsetBottom = 16,
  activeViewPlaneFace,
  viewPlaneFaces,
  viewPlaneOrientation,
  compact = false,
  viewPlaneSize,
  viewPlaneHeader = null,
  activateViewPlaneFace,
  activateDefaultViewPlane,
  orbitViewCube,
  projection = "orthographic",
  onProjectionChange = null
}) {
  const [hoveredId, setHoveredId] = useState("");
  const [dragging, setDragging] = useState(false);
  // A press that moves more than a few pixels is a drag that orbits, not a click on a face.
  const draggedRef = useRef(false);

  const showSelector = showViewPlane && !previewMode;
  if (isLoading || !meshData || (!showSelector && !viewPlaneHeader)) {
    return null;
  }

  const orientation = normalizeOrientation(viewPlaneOrientation);
  const faces = (Array.isArray(viewPlaneFaces) ? viewPlaneFaces : [])
    .map((face) => {
      const facing = toView(orientation, face.direction)[2];
      const points = faceCorners(face.direction).map((corner) => toScreen(toView(orientation, corner)));
      const labelTransform = faceLabelTransform(orientation, face.direction);
      return { ...face, facing, points, labelTransform, label: FACE_LABELS[face.id] || face.label || "" };
    })
    // A convex cube: the faces turned toward the camera never overlap, so they are all it draws.
    .filter((face) => face.facing > 0.02);
  const corners = VIEW_CUBE_CORNERS
    .map((corner) => {
      const view = toView(orientation, corner.direction);
      const [x, y] = toScreen(view);
      return { ...corner, x, y, facing: view[2] };
    })
    .filter((corner) => corner.facing > 0.05);
  const triad = ["x", "y", "z"].map((axis) => {
    const view = orientation[axis];
    const [x, y] = toScreen(view, 9, 11, 89);
    const [lx, ly] = toScreen(view, 13, 11, 89);
    return { axis, x, y, lx, ly, depth: view[2] };
  }).sort((left, right) => left.depth - right.depth);

  const sizeStyle = compact ? undefined : {
    width: normalizeCssLength(viewPlaneSize, DEFAULT_VIEW_PLANE_SIZE),
    height: normalizeCssLength(viewPlaneSize, DEFAULT_VIEW_PLANE_SIZE)
  };
  const startDrag = (event) => {
    if (event.button !== 0 || typeof orbitViewCube !== "function") return;
    draggedRef.current = false;
    let lastX = event.clientX;
    let lastY = event.clientY;
    const startX = lastX;
    const startY = lastY;
    const move = (moveEvent) => {
      if (!draggedRef.current && Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY) < 3) return;
      if (!draggedRef.current) {
        draggedRef.current = true;
        setDragging(true);
      }
      orbitViewCube(moveEvent.clientX - lastX, moveEvent.clientY - lastY);
      lastX = moveEvent.clientX;
      lastY = moveEvent.clientY;
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      setDragging(false);
      // The click that ends a drag lands after pointerup; let it see the drag, then forget it.
      setTimeout(() => { draggedRef.current = false; }, 0);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  };
  const bottom = typeof viewPlaneOffsetBottom === "number" ? `${viewPlaneOffsetBottom}px` : viewPlaneOffsetBottom;
  const hoverProps = (id) => ({
    onPointerEnter: () => setHoveredId(id),
    onPointerLeave: () => setHoveredId((current) => (current === id ? "" : current)),
    onFocus: () => setHoveredId(id),
    onBlur: () => setHoveredId((current) => (current === id ? "" : current))
  });
  const pickProps = (id, title, activate) => ({
    role: "button",
    tabIndex: 0,
    "aria-label": title,
    className: "cursor-pointer focus:outline-none",
    onPointerDown: (event) => { event.stopPropagation(); startDrag(event); },
    onClick: (event) => {
      event.stopPropagation();
      if (draggedRef.current) return;
      activate();
    },
    onKeyDown: (event) => activateOnKey(event, activate),
    ...hoverProps(id)
  });

  return (
    <div
      className="pointer-events-none absolute z-30 flex flex-col items-end gap-1"
      style={{ right: `${viewPlaneOffsetRight}px`, bottom }}
    >
      {viewPlaneHeader ? (
        <div className="pointer-events-auto" onPointerDown={(event) => event.stopPropagation()}>
          {viewPlaneHeader}
        </div>
      ) : null}
      {showSelector ? <div
        className={`pointer-events-auto relative select-none text-foreground ${compact ? "h-20 w-20" : ""} ${dragging ? "cursor-grabbing" : ""}`}
        style={sizeStyle}
        onPointerDown={(event) => { event.stopPropagation(); startDrag(event); }}
      >
        <button type="button" aria-label="Reset to default isometric view" title="Reset to default isometric view"
          className="absolute left-0 top-0 z-10 flex size-5 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => { event.stopPropagation(); activateDefaultViewPlane?.(); }}>
          <House className="size-3" strokeWidth={2} aria-hidden="true" />
        </button>
        {typeof onProjectionChange === "function" ? (() => {
          // Orthographic or perspective sits with the cube, as in Fusion and Onshape: it is how
          // the camera looks, not how the model is drawn. The icon shows the current one.
          const perspective = projection === "perspective";
          const Icon = perspective ? PerspectiveProjectionIcon : OrthographicProjectionIcon;
          const label = perspective ? "Perspective: switch to orthographic" : "Orthographic: switch to perspective";
          return (
            <button type="button" aria-label={label} title={label}
              className="absolute right-0 top-0 z-10 flex size-5 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => { event.stopPropagation(); onProjectionChange(perspective ? "orthographic" : "perspective"); }}>
              <Icon className="size-3.5" />
            </button>
          );
        })() : null}
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" aria-label="View cube">
          {faces.map((face) => {
            const active = activeViewPlaneFace === face.id;
            const hovered = hoveredId === face.id;
            // Faces turned away from the camera are shaded darker, so the cube reads as solid.
            const shade = Math.round(55 + face.facing * 45);
            const fill = active || hovered
              ? `color-mix(in oklch, var(--primary) ${active ? 28 : 16}%, var(--background))`
              : `color-mix(in oklch, var(--background) ${shade}%, var(--foreground))`;
            return (
              <g key={face.id} {...pickProps(face.id, face.title, () => activateViewPlaneFace?.(face.id))}>
                <polygon points={face.points.map((point) => point.join(",")).join(" ")}
                  fill={fill} stroke="color-mix(in oklch, var(--foreground) 35%, transparent)" strokeWidth="1" strokeLinejoin="round" />
                {face.facing > 0.25 ? (
                  <text x="0" y="0" transform={face.labelTransform} textAnchor="middle" dominantBaseline="central"
                    fontSize="0.36" fontWeight="600" fill="color-mix(in oklch, var(--foreground) 70%, transparent)"
                    opacity={Math.min(1, face.facing * 1.6)} pointerEvents="none" aria-hidden="true">
                    {face.label}
                  </text>
                ) : null}
              </g>
            );
          })}
          {corners.map((corner) => {
            const shown = hoveredId === corner.id || activeViewPlaneFace === corner.id;
            return (
              <g key={corner.id} {...pickProps(corner.id, corner.title, () => activateViewPlaneFace?.(corner.id))}>
                <circle cx={corner.x} cy={corner.y} r="5" fill="transparent" />
                <circle cx={corner.x} cy={corner.y} r="2.6" pointerEvents="none"
                  fill={shown ? "var(--primary)" : "transparent"} />
              </g>
            );
          })}
          <g aria-hidden="true" pointerEvents="none">
            {triad.map(({ axis, x, y, lx, ly }) => (
              <g key={axis}>
                <line x1="11" y1="89" x2={x} y2={y} stroke={AXIS_COLORS[axis]} strokeWidth="1.4" strokeLinecap="round" />
                <text x={lx} y={ly} textAnchor="middle" dominantBaseline="central" fontSize="7" fontWeight="600" fill={AXIS_COLORS[axis]}>
                  {axis.toUpperCase()}
                </text>
              </g>
            ))}
          </g>
        </svg>
      </div> : null}
    </div>
  );
}

// Its props change with the camera and the theme, never with the model's pose: a viewer that
// re-renders per animation frame must not rebuild the cube's faces with it.
export default memo(ViewPlaneControl);
