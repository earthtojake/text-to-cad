import { memo, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { VIEW_CUBE_CORNERS, VIEW_CUBE_EDGES, viewPlaneTitle } from "./viewportCameraKit.js";
import { axisColors } from "@cad/core/lib/viewportTheme.js";
import { useI18n } from "../../../i18n/react.js";
import { useControlUsage } from "../../../usage/controls.js";

// The view cube. A cube drawn from the camera's orientation: its faces are the six plane
// views (click TOP, FRONT, RIGHT...) and its corners are the eight isometric views. The
// face, edge and corner shortcuts preserve the current zoom and target. The
// X/Y/Z guides follow the cube edges from its negative corner.

const ORIENTATION_FALLBACK = Object.freeze({
  x: [1, 0, 0],
  y: [0, 1, 0],
  z: [0, 0, 1]
});

// Each face names its side on the cube, in the view's language (`viewCube.face.*`).
const FACE_SIDES = Object.freeze({ z: "top", zNeg: "bottom", yNeg: "front", y: "back", x: "right", xNeg: "left" });
const DEFAULT_VIEW_PLANE_SIZE = "7rem";
const HOME_CORNER_ID = "iso+-+";
// What a hover changes eases in, briefly; what it lights is one plain, lighter shade.
const HOVER_TRANSITION = Object.freeze({ transition: "fill 120ms ease-out" });
const HOVER_FILL = "color-mix(in oklch, var(--background) 55%, var(--foreground))";
// SVG units: the cube's half-size on screen, and where its centre sits.
const SCALE = 21;
const CENTER = 50;
// The cube's box, the view box cropped to the cube: its silhouette at most √3 half-sizes from the centre (36.4 units),
// with room for a corner's dot and an edge's stroke, so the cube fills its box and nothing it draws leaves it.
const VIEW_BOX_MIN = 12;
const VIEW_BOX_SIZE = 100 - 2 * VIEW_BOX_MIN;

/**
 * Where the cube's drawing (its faces' outline, as drawn from `direction`, the camera's place looking at the cube with Z
 * up) stands in its box, in px of a box `size` px square: `{ left, top, right, bottom }` from the box's top-left. What
 * stands against the drawn cube (the corner's Home, `viewportLayout.js`) is placed from it, not from the box.
 * @param {readonly number[]} direction
 * @param {number} [size]
 */
export function cubeInkBox(direction, size = 68) {
  const length = Math.hypot(...direction) || 1;
  const back = direction.map(value => value / length);
  const cross = ([ax, ay, az], [bx, by, bz]) => [ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx];
  const rightRaw = cross([0, 0, 1], back);
  const rightLength = Math.hypot(...rightRaw) || 1;
  const right = rightRaw.map(value => value / rightLength);
  const up = cross(back, right);
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const points = [-1, 1].flatMap(a => [-1, 1].flatMap(b => [-1, 1].map(c => [CENTER + dot(right, [a, b, c]) * SCALE, CENTER - dot(up, [a, b, c]) * SCALE])));
  const px = units => (units - VIEW_BOX_MIN) * size / VIEW_BOX_SIZE;
  return { left: px(Math.min(...points.map(([x]) => x))), top: px(Math.min(...points.map(([, y]) => y))),
    right: px(Math.max(...points.map(([x]) => x))), bottom: px(Math.max(...points.map(([, y]) => y))) };
}
// An axis's letter, by its edge, kept inside the box by more than half its glyph.
const inBox = value => Math.min(100 - VIEW_BOX_MIN - 4, Math.max(VIEW_BOX_MIN + 4, value));

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

// Rounded inset tiles leave a broad bevel for edge and corner picking.
function roundedInsetFace(points) {
  const center = points.reduce((sum, point) => [sum[0] + point[0] / 4, sum[1] + point[1] / 4], [0, 0]);
  const inset = points.map(point => point.map((value, axis) => center[axis] + (value - center[axis]) * 0.84));
  const lerp = (a, b, t) => a.map((value, axis) => value + (b[axis] - value) * t).join(" ");
  return inset.map((point, index) => {
    const before = lerp(point, inset[(index + 3) % 4], 0.2);
    const after = lerp(point, inset[(index + 1) % 4], 0.2);
    return `${index ? "L" : "M"}${before} Q${point.join(" ")} ${after}`;
  }).join(" ") + " Z";
}

// What a hovered edge or corner lights, ON the cube, as a CAD view cube does: an edge, a band along
// it across both faces that meet there; a corner, a square on each of its three faces. Each patch is
// `HOVER_BAND` of its face's width deep (faces span -1..1), drawn where its face is in view.
const HOVER_BAND = 0.36;
function hoverPatches(orientation, direction) {
  const axes = [0, 1, 2].filter(axis => direction[axis] !== 0);
  const inward = value => value * (1 - HOVER_BAND);
  return axes.flatMap(normal => {
    const facing = toView(orientation, [0, 1, 2].map(axis => (axis === normal ? direction[axis] : 0)))[2];
    if (facing <= 0.02) return [];
    const others = [0, 1, 2].filter(axis => axis !== normal);
    // On this face, each other axis runs from the edge or corner inward when it is part of it,
    // and across the whole face when it is not (an edge's length).
    const spans = others.map(axis => direction[axis] !== 0 ? [direction[axis], inward(direction[axis])] : [-1, 1]);
    const quad = [[0, 0], [1, 0], [1, 1], [0, 1]].map(([i, j]) => {
      const point = [0, 0, 0];
      point[normal] = direction[normal];
      point[others[0]] = spans[0][i];
      point[others[1]] = spans[1][j];
      return toScreen(toView(orientation, point));
    });
    return [quad.map(point => point.join(",")).join(" ")];
  });
}

function activateOnKey(event, activate) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  event.stopPropagation();
  activate();
}

function ViewPlaneControl({
  showViewPlane,
  isLoading,
  meshData,
  viewPlaneOffsetRight,
  viewPlaneGutter = 0,
  viewPlaneOffsetLeft,
  viewPlaneOffsetBottom = 16,
  viewPlaneOffsetTop,
  activeViewPlaneFace,
  viewPlaneFaces,
  orientation: orientationStore,
  compact = false,
  disabled = false,
  viewPlaneSize,
  viewPlaneHeader = null,
  activateViewPlaneFace,
  orbitViewCube,
  // The viewport's light or dark (`lib/viewportTheme.js`): the axes in the one XYZ palette, as the grid's.
  scheme = "light"
}) {
  const AXIS_COLORS = axisColors(scheme);
  // The cube's own subscription to the camera's orientation (`createViewPlaneOrientationStore`):
  // a moving camera re-renders the cube and nothing around it.
  const viewPlaneOrientation = useSyncExternalStore(orientationStore.subscribe, orientationStore.getSnapshot, orientationStore.getSnapshot);
  // A face, an edge or a corner pressed, or the cube turned by a drag (`usage/controls.js`).
  const usage = useControlUsage();
  const { t } = useI18n();
  const [hoveredId, setHoveredId] = useState("");
  const [dragging, setDragging] = useState(false);
  // A press that moves more than a few pixels is a drag that orbits, not a click on a face.
  const draggedRef = useRef(false);
  const dragCleanupRef = useRef(null);
  useEffect(() => () => dragCleanupRef.current?.(), []);

  useEffect(() => {
    if (!disabled) return;
    dragCleanupRef.current?.();
    setHoveredId("");
  }, [disabled]);

  const showSelector = showViewPlane;
  if (isLoading || !meshData || (!showSelector && !viewPlaneHeader)) {
    return null;
  }

  const orientation = normalizeOrientation(viewPlaneOrientation);
  const faces = (Array.isArray(viewPlaneFaces) ? viewPlaneFaces : [])
    .map((face) => {
      const facing = toView(orientation, face.direction)[2];
      const points = faceCorners(face.direction).map((corner) => toScreen(toView(orientation, corner)));
      const labelTransform = faceLabelTransform(orientation, face.direction);
      return { ...face, facing, points, labelTransform, label: FACE_SIDES[face.id] ? t(`viewCube.face.${FACE_SIDES[face.id]}`) : face.label || "" };
    })
    // A convex cube: the faces turned toward the camera never overlap, so they are all it draws.
    .filter((face) => face.facing > 0.02);
  const edges = VIEW_CUBE_EDGES.filter((edge) => edge.direction.some((sign, axis) =>
    sign && orientation[["x", "y", "z"][axis]][2] * sign > 0.02
  )).map((edge) => {
    const ends = [-1, 1].map((sign) => {
      const point = [...edge.direction];
      point[edge.along] = sign;
      return toScreen(toView(orientation, point));
    });
    return { ...edge, ends };
  });
  const corners = VIEW_CUBE_CORNERS
    .map((corner) => {
      const view = toView(orientation, corner.direction);
      const [x, y] = toScreen(view);
      return { ...corner, x, y, facing: view[2] };
    })
    .filter((corner) => corner.facing > 0.05);
  // The axes lie on the cube's own edges, nothing past its silhouette: each along the edge parallel to it nearest the
  // camera on the bottom (X and Y the bottom's near edges; Z the upright edge at their corner), drawn from its negative end
  // to its positive one, as an axis points, and lettered just inside its positive end, off the edge away from the centre.
  const near = [0, 1].map(index => (orientation[["x", "y", "z"][index]][2] >= 0 ? 1 : -1));
  const corner = [near[0], near[1], -1];
  const triad = ["x", "y", "z"].map((axis, index) => {
    const from = [...corner], to = [...corner];
    from[index] = -1;
    to[index] = 1;
    const [x0, y0] = toScreen(toView(orientation, from));
    const [x, y] = toScreen(toView(orientation, to));
    const along = [x0 + (x - x0) * 0.82, y0 + (y - y0) * 0.82];
    const off = [along[0] - CENTER, along[1] - CENTER], length = Math.hypot(...off) || 1;
    return { axis, x0, y0, x, y, lx: inBox(along[0] + off[0] / length * 5), ly: inBox(along[1] + off[1] / length * 5), visible: true };
  });

  const hoveredPick = VIEW_CUBE_EDGES.find(edge => edge.id === hoveredId) || VIEW_CUBE_CORNERS.find(corner => corner.id === hoveredId);
  const hoveredPatches = hoveredPick ? hoverPatches(orientation, hoveredPick.direction) : [];

  const sizeStyle = compact ? undefined : {
    width: normalizeCssLength(viewPlaneSize, DEFAULT_VIEW_PLANE_SIZE),
    height: normalizeCssLength(viewPlaneSize, DEFAULT_VIEW_PLANE_SIZE)
  };
  const startDrag = (event) => {
    if (disabled || event.button !== 0 || typeof orbitViewCube !== "function") return;
    dragCleanupRef.current?.();
    draggedRef.current = false;
    let lastX = event.clientX;
    let lastY = event.clientY;
    const startX = lastX;
    const startY = lastY;
    const move = (moveEvent) => {
      if (!draggedRef.current && Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY) < 3) return;
      // The drag's first turn says so: the orbit holds its sideways sense from there to the drag's end.
      const starts = !draggedRef.current;
      if (starts) {
        draggedRef.current = true;
        setDragging(true);
        usage.used("view_cube_drag");
      }
      orbitViewCube(moveEvent.clientX - lastX, moveEvent.clientY - lastY, starts);
      lastX = moveEvent.clientX;
      lastY = moveEvent.clientY;
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      setDragging(false);
      dragCleanupRef.current = null;
      // Keep the drag flag through the click; the next press clears it.
    };
    dragCleanupRef.current = end;
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  };
  const bottom = typeof viewPlaneOffsetBottom === "number" ? `${viewPlaneOffsetBottom}px` : viewPlaneOffsetBottom;
  const hoverProps = (id) => disabled ? {} : ({
    onPointerEnter: () => setHoveredId(id),
    onPointerLeave: () => setHoveredId((current) => (current === id ? "" : current)),
    onFocus: () => setHoveredId(id),
    onBlur: () => setHoveredId((current) => (current === id ? "" : current))
  });
  const pickProps = (id, title, activate) => ({
    role: "button",
    tabIndex: disabled ? -1 : 0,
    "aria-disabled": disabled,
    "aria-label": title,
    className: `${disabled ? "cursor-default" : "cursor-pointer"} focus:outline-none`,
    onPointerDown: (event) => { event.stopPropagation(); startDrag(event); },
    onClick: (event) => {
      event.stopPropagation();
      if (disabled || draggedRef.current) return;
      usage.used("view_cube");
      activate();
    },
    onKeyDown: (event) => activateOnKey(event, () => { if (!disabled) { usage.used("view_cube"); activate(); } }),
    ...hoverProps(id)
  });

  return (
    <div
      className="pointer-events-none absolute z-30 flex flex-col items-center gap-0" data-view-cube=""
      style={{ ...(viewPlaneOffsetLeft != null ? { left: `${viewPlaneOffsetLeft}px` } : {
        left: "var(--cad-viewport-corner-left, auto)", right: `var(--cad-viewport-corner-right, ${viewPlaneOffsetRight}px)` }),
        ...(viewPlaneOffsetTop != null ? { top: viewPlaneOffsetTop } : { bottom }),
        // Its box stands `viewPlaneGutter` in from the host's corner variable, at either side it anchors.
        ...(viewPlaneGutter ? { paddingLeft: `${viewPlaneGutter}px`, paddingRight: `${viewPlaneGutter}px` } : null) }}
    >
      {viewPlaneHeader ? (
        <div className="pointer-events-auto" onPointerDown={(event) => event.stopPropagation()}>
          {viewPlaneHeader}
        </div>
      ) : null}
      {showSelector ? <div
        className={`pointer-events-auto relative touch-none select-none text-foreground ${compact ? "h-20 w-20" : ""} ${dragging ? "cursor-grabbing" : ""}`}
        style={sizeStyle}
        onPointerDown={(event) => { event.stopPropagation(); startDrag(event); }}
      >
        <svg className="absolute inset-0 h-full w-full overflow-visible" viewBox={`${VIEW_BOX_MIN} ${VIEW_BOX_MIN} ${VIEW_BOX_SIZE} ${VIEW_BOX_SIZE}`} aria-label={t("viewCube.label")}>
          {faces.map((face) => {
            const active = activeViewPlaneFace === face.id;
            const hovered = hoveredId === face.id;
            // Faces turned away from the camera are shaded darker, so the cube reads as solid.
            const shade = Math.round(94 + face.facing * 5);
            // Hovered, a face lights plainly (the patch colour an edge or corner lights with), its
            // label at full strength; the view on screen a little less.
            const fill = hovered
              ? HOVER_FILL
              : active
                ? "color-mix(in oklch, var(--background) 82%, var(--foreground))"
                : `color-mix(in oklch, var(--background) ${shade}%, var(--foreground))`;
            return (
              <g key={face.id} {...pickProps(face.id, viewPlaneTitle(face, t), () => activateViewPlaneFace?.(face.id))}>
                <polygon points={face.points.map((point) => point.join(",")).join(" ")}
                  fill="color-mix(in oklch, var(--background) 90%, var(--foreground))" stroke="var(--background)" strokeWidth="0.6" strokeLinejoin="round" />
                <path d={roundedInsetFace(face.points)} fill={fill} pointerEvents="none" style={HOVER_TRANSITION} />
                {/* A face's name: 0.5 of the face's half-size, 10px on a face seen square-on in the 96px cube
                    (the type scale's floor for text drawn into the viewport), foreshortened with its face. */}
                {face.facing > 0.25 ? (
                  <text x="0" y="0" transform={face.labelTransform} textAnchor="middle" dominantBaseline="central"
                    fontSize="0.5" fontWeight={hovered || active ? 600 : 500} fill={hovered || active ? "var(--foreground)" : "color-mix(in oklch, var(--foreground) 90%, transparent)"}
                    opacity={Math.min(1, face.facing * 1.6)} pointerEvents="none" aria-hidden="true">
                    {face.label}
                  </text>
                ) : null}
              </g>
            );
          })}
          {/* The hovered edge's or corner's patches, on the faces, under the pickers. */}
          {hoveredPatches.map((points, index) => <polygon key={index} points={points} fill={HOVER_FILL}
            stroke="var(--background)" strokeWidth="0.6" strokeLinejoin="round" pointerEvents="none" data-view-cube-hover="" />)}
          {edges.map((edge) => {
            // An edge is a view too: hovered (or the view on screen) it shows as a bar along the
            // cube's edge, where nothing marked it before.
            return (
              <g key={edge.id} {...pickProps(edge.id, viewPlaneTitle(edge, t), () => activateViewPlaneFace?.(edge.id))}>
                <line x1={edge.ends[0][0]} y1={edge.ends[0][1]} x2={edge.ends[1][0]} y2={edge.ends[1][1]}
                  stroke="transparent" strokeWidth="8" />
              </g>
            );
          })}
          {corners.map((corner) => {
            // Every corner is an isometric view and shows a dot; the right-front-top one, the
            // usual isometric view, is darker so it is the one to aim for.
            const home = corner.id === HOME_CORNER_ID;
            const tone = home ? 55 : 25;
            return (
              <g key={corner.id} {...pickProps(corner.id, viewPlaneTitle(corner, t), () => activateViewPlaneFace?.(corner.id))}>
                <circle cx={corner.x} cy={corner.y} r="6" fill="transparent" />
                <circle cx={corner.x} cy={corner.y} r={home ? 2.4 : 1.8} pointerEvents="none"
                  fill={`color-mix(in oklch, var(--foreground) ${tone}%, var(--background))`}
                  stroke="var(--background)" strokeWidth="0.8" />
              </g>
            );
          })}
          <g aria-hidden="true" pointerEvents="none">
            {triad.map(({ axis, x0, y0, x, y, lx, ly, visible }) => (
              <g key={axis} opacity={visible ? 1 : 0.4}>
                <line x1={x0} y1={y0} x2={x} y2={y} stroke={AXIS_COLORS[axis]} strokeWidth="1.7" strokeLinecap="round" />
                <text x={lx} y={ly} textAnchor="middle" dominantBaseline="central" fontSize="8" fontWeight="600" fill={AXIS_COLORS[axis]} data-view-cube-axis-label="">
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
