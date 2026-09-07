import { useState } from "react";

const ORIENTATION_FALLBACK = Object.freeze({
  x: [1, 0, 0],
  y: [0, 1, 0],
  z: [0, 0, 1]
});

const DEFAULT_VIEW_PLANE_PALETTE = Object.freeze({
  axis: {
    x: {
      front: [250, 88, 79],
      back: [122, 32, 28]
    },
    y: {
      front: [92, 233, 123],
      back: [30, 99, 46]
    },
    z: {
      front: [84, 131, 255],
      back: [30, 53, 126]
    }
  },
  center: {
    fill: [252, 215, 74],
    stroke: [255, 235, 153]
  }
});

const DEFAULT_VIEW_PLANE_SIZE = "6.71875rem";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeCssLength(value, fallback = "") {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return `${value}px`;
  }
  const text = String(value || "").trim();
  return text || fallback;
}

function toRgb(value) {
  const [r = 0, g = 0, b = 0] = Array.isArray(value) ? value : [0, 0, 0];
  return [Math.round(clamp(r, 0, 255)), Math.round(clamp(g, 0, 255)), Math.round(clamp(b, 0, 255))];
}

function mixRgb(from, to, amount) {
  const ratio = clamp(amount, 0, 1);
  const left = toRgb(from);
  const right = toRgb(to);
  return [
    left[0] + (right[0] - left[0]) * ratio,
    left[1] + (right[1] - left[1]) * ratio,
    left[2] + (right[2] - left[2]) * ratio
  ];
}

function rgbToCss(value, alpha = 1) {
  const [r, g, b] = toRgb(value);
  return `rgba(${r}, ${g}, ${b}, ${clamp(alpha, 0, 1)})`;
}

function normalizeRgbTriplet(value, fallback) {
  if (!Array.isArray(value) || value.length < 3) {
    return [...fallback];
  }
  const r = Number(value[0]);
  const g = Number(value[1]);
  const b = Number(value[2]);
  if (!Number.isFinite(r) || !Number.isFinite(g) || !Number.isFinite(b)) {
    return [...fallback];
  }
  return [clamp(r, 0, 255), clamp(g, 0, 255), clamp(b, 0, 255)];
}

function resolveViewPlanePalette(viewerTheme) {
  const themePalette = viewerTheme?.viewPlanePalette || {};
  const themeAxisPalette = themePalette?.axis || {};
  const axis = {};
  for (const axisId of ["x", "y", "z"]) {
    const fallback = DEFAULT_VIEW_PLANE_PALETTE.axis[axisId];
    const custom = themeAxisPalette?.[axisId] || {};
    axis[axisId] = {
      front: normalizeRgbTriplet(custom.front, fallback.front),
      back: normalizeRgbTriplet(custom.back, fallback.back)
    };
  }
  return {
    axis,
    center: {
      fill: normalizeRgbTriplet(themePalette?.center?.fill, DEFAULT_VIEW_PLANE_PALETTE.center.fill),
      stroke: normalizeRgbTriplet(themePalette?.center?.stroke, DEFAULT_VIEW_PLANE_PALETTE.center.stroke)
    }
  };
}

function normalizeAxis(axis, fallback) {
  if (!Array.isArray(axis) || axis.length !== 3) {
    return [...fallback];
  }
  const x = Number(axis[0]);
  const y = Number(axis[1]);
  const z = Number(axis[2]);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
    return [...fallback];
  }
  const magnitude = Math.hypot(x, y, z);
  if (magnitude < 1e-6) {
    return [...fallback];
  }
  return [x / magnitude, y / magnitude, z / magnitude];
}

function normalizeOrientation(orientation) {
  return {
    x: normalizeAxis(orientation?.x, ORIENTATION_FALLBACK.x),
    y: normalizeAxis(orientation?.y, ORIENTATION_FALLBACK.y),
    z: normalizeAxis(orientation?.z, ORIENTATION_FALLBACK.z)
  };
}

function projectDirection(orientation, direction) {
  const [dx = 0, dy = 0, dz = 0] = Array.isArray(direction) ? direction : [0, 0, 0];
  return [
    orientation.x[0] * dx + orientation.y[0] * dy + orientation.z[0] * dz,
    orientation.x[1] * dx + orientation.y[1] * dy + orientation.z[1] * dz,
    orientation.x[2] * dx + orientation.y[2] * dy + orientation.z[2] * dz
  ];
}

function getAxisId(face) {
  const id = String(face?.id || "");
  return id.startsWith("x") ? "x" : id.startsWith("y") ? "y" : "z";
}

export default function ViewPlaneControl({
  showViewPlane,
  previewMode,
  isLoading,
  meshData,
  viewPlaneOffsetRight,
  viewPlaneOffsetBottom = 16,
  activeViewPlaneFace,
  viewPlaneFaces,
  viewPlaneOrientation,
  viewerTheme,
  compact = false,
  variant = "3d",
  viewPlaneSize,
  viewPlaneHeader = null,
  activateViewPlaneFace,
  activateDefaultViewPlane
}) {
  const [hoveredNodeId, setHoveredNodeId] = useState("");

  if (!showViewPlane || previewMode || isLoading || !meshData) {
    return null;
  }

  const orientation = normalizeOrientation(viewPlaneOrientation);
  const palette = resolveViewPlanePalette(viewerTheme);
  const faces = Array.isArray(viewPlaneFaces) ? viewPlaneFaces : [];
  const projectedNodes = faces
    .map((face) => {
      const axisId = getAxisId(face);
      const axisPalette = palette.axis[axisId] || palette.axis.z;
      const [x, y, z] = projectDirection(orientation, face.direction);
      const depth = clamp((z + 1) / 2, 0, 1);
      const fillColor = mixRgb(axisPalette.back, axisPalette.front, depth);
      const edgeColor = mixRgb([10, 16, 28], axisPalette.front, depth * 0.82 + 0.08);
      return {
        id: face.id,
        title: face.title,
        x: 50 + x * 28,
        y: 50 - y * 28,
        z,
        depth,
        radius: 4.95 + depth * 1.05,
        fill: rgbToCss(fillColor),
        edge: rgbToCss(edgeColor),
        stem: rgbToCss(fillColor, 0.32 + depth * 0.48)
      };
    })
    .sort((left, right) => left.z - right.z);
  const backNodes = projectedNodes.filter((node) => node.z < 0);
  const frontNodes = projectedNodes.filter((node) => node.z >= 0);
  const is2d = variant === "2d";
  const customViewPlaneSize = !compact && !is2d
    ? normalizeCssLength(viewPlaneSize, DEFAULT_VIEW_PLANE_SIZE)
    : "";
  const viewPlaneSizeClasses = compact || is2d ? "h-20 w-20" : "";
  const viewPlaneSizeStyle = customViewPlaneSize
    ? { width: customViewPlaneSize, height: customViewPlaneSize }
    : undefined;
  const viewPlaneSurfaceClasses = is2d
    ? "bg-sidebar pointer-events-auto relative rounded-md border border-sidebar-border text-sidebar-foreground shadow-sm transition duration-150"
    : "pointer-events-auto relative text-sidebar-foreground transition duration-150";
  const viewPlaneLabel = is2d ? "2D view selector" : "Perspective selector";
  const normalizedBottomOffset = typeof viewPlaneOffsetBottom === "number"
    ? `${viewPlaneOffsetBottom}px`
    : viewPlaneOffsetBottom;
  const centerHovered = hoveredNodeId === "__default__";
  const renderNode = (node) => {
    const active = activeViewPlaneFace === node.id;
    const hovered = hoveredNodeId === node.id;
    return (
      <g
        key={node.id}
        role="button"
        tabIndex={0}
        aria-label={node.title}
        aria-pressed={active}
        className="group cursor-pointer focus:outline-none"
        onPointerDown={(event) => {
          event.stopPropagation();
        }}
        onPointerEnter={() => {
          setHoveredNodeId(node.id);
        }}
        onPointerMove={() => {
          setHoveredNodeId(node.id);
        }}
        onPointerLeave={() => {
          setHoveredNodeId((current) => (current === node.id ? "" : current));
        }}
        onMouseEnter={() => {
          setHoveredNodeId(node.id);
        }}
        onMouseMove={() => {
          setHoveredNodeId(node.id);
        }}
        onMouseLeave={() => {
          setHoveredNodeId((current) => (current === node.id ? "" : current));
        }}
        onFocus={() => {
          setHoveredNodeId(node.id);
        }}
        onBlur={() => {
          setHoveredNodeId((current) => (current === node.id ? "" : current));
        }}
        onClick={(event) => {
          event.stopPropagation();
          activateViewPlaneFace(node.id);
        }}
        onKeyDown={(event) => {
          if (event.key !== "Enter" && event.key !== " ") {
            return;
          }
          event.preventDefault();
          event.stopPropagation();
          activateViewPlaneFace(node.id);
        }}
      >
        <circle
          cx={node.x}
          cy={node.y}
          r={node.radius + 4.4}
          className="transition-opacity duration-150"
          opacity={hovered ? 1 : 0}
          fill={node.fill}
          fillOpacity="0.12"
          stroke="var(--sidebar-foreground)"
          strokeOpacity="0.72"
          strokeWidth="1.1"
        />
        <circle
          cx={node.x}
          cy={node.y}
          r={node.radius + (active ? 2.1 : 0)}
          fill="none"
          stroke={active ? "var(--sidebar-foreground)" : "transparent"}
          strokeWidth={active ? 1.6 : 0}
        />
        <circle
          cx={node.x}
          cy={node.y}
          r={node.radius}
          className="transition-transform duration-150 ease-out"
          style={{
            transform: hovered ? "scale(1.1)" : "scale(1)",
            transformBox: "fill-box",
            transformOrigin: "center"
          }}
          fill={node.fill}
          stroke={active ? "var(--sidebar-foreground)" : node.edge}
          strokeWidth={active ? 1.35 : 1}
        />
      </g>
    );
  };

  return (
    <div
      className="pointer-events-none absolute z-30 flex flex-col items-end gap-1"
      style={{ right: `${viewPlaneOffsetRight}px`, bottom: normalizedBottomOffset }}
    >
      {viewPlaneHeader ? (
        <div
          className="pointer-events-auto"
          onPointerDown={(event) => {
            event.stopPropagation();
          }}
        >
          {viewPlaneHeader}
        </div>
      ) : null}
      <div
        className={`${viewPlaneSurfaceClasses} ${viewPlaneSizeClasses}`}
        style={viewPlaneSizeStyle}
        onPointerDown={(event) => {
          event.stopPropagation();
        }}
      >
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" aria-label={viewPlaneLabel}>
          <defs>
            <radialGradient id="view-sphere-shell" cx="34%" cy="28%" r="74%">
              <stop offset="0%" stopColor="var(--sidebar)" />
              <stop offset="100%" stopColor="var(--sidebar)" />
            </radialGradient>
          </defs>
          {is2d ? (
            <>
              <rect x="15" y="15" width="70" height="70" rx="8" fill="url(#view-sphere-shell)" stroke="var(--sidebar-border)" strokeWidth="0.75" />
              <line x1="22" y1="50" x2="78" y2="50" fill="none" stroke="color-mix(in oklch, var(--sidebar-foreground) 18%, transparent)" strokeWidth="1" strokeLinecap="round" />
              <line x1="50" y1="22" x2="50" y2="78" fill="none" stroke="color-mix(in oklch, var(--sidebar-foreground) 18%, transparent)" strokeWidth="1" strokeLinecap="round" />
            </>
          ) : (
            <>
              <circle cx="50" cy="50" r="44" fill="url(#view-sphere-shell)" stroke="var(--sidebar-border)" strokeWidth="0.75" />
              <ellipse cx="50" cy="50" rx="30" ry="11.8" fill="none" stroke="color-mix(in oklch, var(--sidebar-foreground) 12%, transparent)" strokeWidth="0.8" />
              <ellipse cx="50" cy="50" rx="14" ry="30" fill="none" stroke="color-mix(in oklch, var(--sidebar-foreground) 12%, transparent)" strokeWidth="0.8" />
            </>
          )}
          {backNodes.map((node) => (
            <line
              key={`${node.id}-stem`}
              x1="50"
              y1="50"
              x2={node.x}
              y2={node.y}
              stroke={node.stem}
              strokeWidth={1.6 + node.depth * 0.8}
              strokeLinecap="round"
              pointerEvents="none"
            />
          ))}
          {backNodes.map((node) => renderNode(node))}
          <g
            role="button"
            tabIndex={0}
            aria-label={is2d ? "Fit 2D view" : "Reset to default isometric view"}
            className="group cursor-pointer focus:outline-none"
            onPointerDown={(event) => {
              event.stopPropagation();
            }}
            onPointerEnter={() => {
              setHoveredNodeId("__default__");
            }}
            onPointerMove={() => {
              setHoveredNodeId("__default__");
            }}
            onPointerLeave={() => {
              setHoveredNodeId((current) => (current === "__default__" ? "" : current));
            }}
            onMouseEnter={() => {
              setHoveredNodeId("__default__");
            }}
            onMouseMove={() => {
              setHoveredNodeId("__default__");
            }}
            onMouseLeave={() => {
              setHoveredNodeId((current) => (current === "__default__" ? "" : current));
            }}
            onFocus={() => {
              setHoveredNodeId("__default__");
            }}
            onBlur={() => {
              setHoveredNodeId((current) => (current === "__default__" ? "" : current));
            }}
            onClick={(event) => {
              event.stopPropagation();
              activateDefaultViewPlane?.();
            }}
            onKeyDown={(event) => {
              if (event.key !== "Enter" && event.key !== " ") {
                return;
              }
              event.preventDefault();
              event.stopPropagation();
              activateDefaultViewPlane?.();
            }}
          >
            <circle cx="50" cy="50" r="10.2" fill="transparent" stroke="none" />
            <circle
              cx="50"
              cy="50"
              r="11.4"
              className="transition-opacity duration-150"
              opacity={centerHovered ? 1 : 0}
              fill={rgbToCss(palette.center.fill, 0.16)}
              stroke="var(--sidebar-foreground)"
              strokeOpacity="0.72"
              strokeWidth="1.1"
            />
            <circle
              cx="50"
              cy="50"
              r="7.3"
              className="transition-transform duration-150 ease-out"
              style={{
                transform: centerHovered ? "scale(1.1)" : "scale(1)",
                transformBox: "fill-box",
                transformOrigin: "center"
              }}
              fill={rgbToCss(palette.center.fill, 0.95)}
              stroke={rgbToCss(palette.center.stroke, 0.72)}
              strokeWidth="1.05"
            />
          </g>
          {frontNodes.map((node) => (
            <line
              key={`${node.id}-stem-front`}
              x1="50"
              y1="50"
              x2={node.x}
              y2={node.y}
              stroke={node.stem}
              strokeWidth={1.6 + node.depth * 0.8}
              strokeLinecap="round"
              pointerEvents="none"
            />
          ))}
          {frontNodes.map((node) => renderNode(node))}
        </svg>
      </div>
    </div>
  );
}
