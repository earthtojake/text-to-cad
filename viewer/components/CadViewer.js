"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { parseCadRefToken } from "../lib/cadRefs";
import { copyImageBlobToClipboard } from "../lib/clipboard";
import {
  annotatePerspectiveSnapshot,
  clonePerspectiveSnapshot,
  perspectiveSnapshotEqual,
  perspectiveSnapshotMatchesScene,
  resolvePerspectiveSnapshot
} from "../lib/perspective";
import { VIEWER_PICK_MODE } from "../lib/viewer/constants";
import {
  clampSceneModelRadius,
  defaultSceneGridRadius,
  getLightingScopeRadius,
  getSceneScaleSettings,
  normalizeSceneScaleMode,
  VIEWER_SCENE_SCALE
} from "../lib/viewer/sceneScale";
import { DRAWING_TOOL } from "../lib/workbench/constants";
import { getEnvironmentPresetById, LOOK_FLOOR_MODES } from "../lib/lookSettings";
import ViewPlaneControl from "./viewer/ViewPlaneControl";
import { useViewerDrawingOverlay } from "./viewer/hooks/useViewerDrawingOverlay";
import { useViewerPicking } from "./viewer/hooks/useViewerPicking";
import { useViewerRuntime } from "./viewer/hooks/useViewerRuntime";

const DEFAULT_GRID_DIVISIONS = 28;
const GRID_TARGET_DIVISIONS = 40;
const IDLE_PIXEL_RATIO_CAP = 2;
const INTERACTION_PIXEL_RATIO_CAP = 1.25;
const INTERACTION_IDLE_DELAY_MS = 140;
const DEFAULT_DAMPING_FACTOR = 0.14;
const DEFAULT_ZOOM_SPEED = 4.5;
const COARSE_POINTER_ZOOM_SPEED = 1.6;
const ACCELERATED_WHEEL_ZOOM_SPEED = 10;
const TRACKPAD_PINCH_ZOOM_SPEED = 14;
const COARSE_POINTER_PINCH_ZOOM_SPEED = 2.4;
const KEYBOARD_ORBIT_NUDGE_RAD = Math.PI / 32;
const KEYBOARD_ORBIT_SPEED_RAD_PER_SEC = Math.PI * 0.42;
const KEYBOARD_POLAR_EPSILON = 0.02;
const MM_PER_INCH = 25.4;
const PREVIEW_AUTO_ROTATE_SPEED = 1.0;
const VIEW_PLANE_ACTIVE_DOT_THRESHOLD = 0.994;
const VIEW_PLANE_TRANSITION_MS = 280;
const DEFAULT_VIEW_PLANE_ORIENTATION = Object.freeze({
  x: [1, 0, 0],
  y: [0, 1, 0],
  z: [0, 0, 1]
});
const MODEL_FRAME_BUFFER = 1.08;
const DEFAULT_VIEW_DIRECTION = [2.1, 1.08, 1.65];
const VIEW_PLANE_DEFAULT_PRESET = {
  id: "isometric",
  title: "Reset to default isometric view",
  direction: DEFAULT_VIEW_DIRECTION,
  up: [0, 0, 1]
};
const CAD_EDGE_OPACITY = 0.84;
const CAD_EDGE_THRESHOLD_DEG = 16;
const DRAWING_STROKE_COLOR = "#ef4444";
const DRAWING_STROKE_HALO = "rgba(255, 255, 255, 0.94)";
const DRAWING_STROKE_WIDTH = 4;
const DRAWING_STROKE_HALO_WIDTH = 8;
const DRAWING_ARROW_HEAD_LENGTH = 18;
const DRAWING_MIN_POINT_DISTANCE_PX = 2.5;
const DRAWING_MIN_STROKE_LENGTH_PX = 4;
const DRAWING_ERASE_THRESHOLD_PX = 16;
const DRAWING_FILL_COLOR = "rgba(239, 68, 68, 0.22)";
const DRAWING_GUESSED_FILL_COLOR = "rgba(239, 68, 68, 0.16)";
const DRAWING_FILL_ANALYSIS_MAX_DIMENSION = 420;
const DRAWING_FILL_ANALYSIS_MIN_DIMENSION = 96;
const DRAWING_FILL_CONNECT_GAP_PX = 28;
const DRAWING_FILL_RAY_COUNT = 72;
const DRAWING_FILL_MIN_REGION_PIXELS = 56;
const DRAWING_FILL_MAX_REGION_RATIO = 0.92;
const SURFACE_LINE_COLOR = "#ef4444";
const SURFACE_LINE_UNSUPPORTED_TYPES = new Set(["", "SPHERICAL_SURFACE", "TOROIDAL_SURFACE", "BSPLINE_SURFACE"]);
const BASE_VIEWER_THEME = {
  sceneBackground: "#09090b",
  surface: "#f4f4f5",
  surfaceRoughness: 0.92,
  surfaceMetalness: 0.03,
  surfaceClearcoat: 0,
  surfaceClearcoatRoughness: 0.6,
  edge: "#18181b",
  edgeThickness: 1,
  edgeOpacity: CAD_EDGE_OPACITY,
  selected: "#2563eb",
  hover: "#0ea5e9",
  gridCenter: "#3f3f46",
  gridCell: "#27272a",
  gridOpacity: 0.16,
  stageFloorColor: "#141416",
  stageFloorOpacity: 0.78,
  stageFloorRoughness: 0.92,
  stageFloorMetalness: 0,
  stageFloorTransmission: 0,
  stageFloorIor: 1.35,
  stageFloorThickness: 0.035,
  stageFloorAttenuationDistance: 4,
  viewPlanePalette: {
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
    },
    shell: {
      inner: [24, 31, 48],
      outer: [8, 12, 20],
      stroke: [148, 163, 184]
    }
  }
};
const BACKGROUND_TEXTURE_SIZE = 1024;
const FLOOR_GLOW_TEXTURE_SIZE = 512;
const DEFAULT_LIGHTING = {
  toneMappingExposure: 1.08,
  hemisphereSky: "#d3dde6",
  hemisphereGround: "#090c16",
  hemisphereIntensity: 1.62,
  keyLightColor: "#d6e0ea",
  keyLightIntensity: 0.82,
  fillLightColor: "#6b7f95",
  fillLightIntensity: 0.46,
  rimLightColor: "#6db6e8",
  rimLightIntensity: 0.04
};
const DEFAULT_SHADOW_MAP_SIZE = 2048;
const REFERENCE_HOVER_COLOR = "#8dc5ff";
const REFERENCE_SELECTED_COLOR = "#4f9dff";
const REFERENCE_CORNER_COLOR = "#2563eb";
const REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER = 3;
const REFERENCE_HOVER_HIGHLIGHT_WIDTH_MULTIPLIER = REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER / 2;
const REFERENCE_HOVER_FILL_OPACITY = 0.3;
const REFERENCE_SELECTED_FILL_OPACITY = 0.24;
const BEND_GUIDE_COLOR = "#f59e0b";
const BEND_GUIDE_WIDTH_MULTIPLIER = 1.35;
const PART_HOVER_OPACITY_BOOST = 0.08;
const PART_SELECTED_OPACITY_BOOST = 0.12;
const URDF_PART_INTRO_STAGGER_MS = 150;
const URDF_PART_INTRO_DURATION_MS = 620;
const URDF_PART_INTRO_INITIAL_SCALE = 0.76;
const URDF_PART_INTRO_MAX_TILT_RAD = Math.PI / 16;
const URDF_PART_INTRO_VISIBILITY_EPSILON = 0.012;
const URDF_PART_INTRO_MIN_TRAVEL = 0.022;
const LOOK_BACKGROUND_TYPES = {
  SOLID: "solid",
  LINEAR: "linear",
  RADIAL: "radial",
  TRANSPARENT: "transparent"
};
const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;
const VIEW_PLANE_FACES = [
  {
    id: "z",
    label: "Z",
    title: "Jump to top view",
    direction: [0, 0, 1],
    up: [0, 1, 0]
  },
  {
    id: "zNeg",
    label: "-Z",
    title: "Jump to bottom view",
    direction: [0, 0, -1],
    up: [0, 1, 0]
  },
  {
    id: "yNeg",
    label: "-Y",
    title: "Jump to front view",
    direction: [0, -1, 0],
    up: [0, 0, 1]
  },
  {
    id: "y",
    label: "Y",
    title: "Jump to back view",
    direction: [0, 1, 0],
    up: [0, 0, 1]
  },
  {
    id: "x",
    label: "X",
    title: "Jump to right view",
    direction: [1, 0, 0],
    up: [0, 0, 1]
  },
  {
    id: "xNeg",
    label: "-X",
    title: "Jump to left view",
    direction: [-1, 0, 0],
    up: [0, 0, 1]
  }
];
const VIEW_PLANE_FACE_BY_ID = Object.fromEntries(VIEW_PLANE_FACES.map((face) => [face.id, face]));

function viewPlaneOrientationEqual(a, b, epsilon = 1e-4) {
  if (!a || !b) {
    return false;
  }
  for (const axis of ["x", "y", "z"]) {
    const left = a[axis];
    const right = b[axis];
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== 3 || right.length !== 3) {
      return false;
    }
    for (let index = 0; index < 3; index += 1) {
      if (Math.abs((left[index] || 0) - (right[index] || 0)) > epsilon) {
        return false;
      }
    }
  }
  return true;
}

function readViewPlaneOrientation(runtime) {
  if (!runtime?.THREE || !runtime?.camera) {
    return null;
  }
  const inverseCameraRotation = runtime.camera.quaternion.clone().invert();
  const projectAxis = (x, y, z) => {
    const projected = new runtime.THREE.Vector3(x, y, z).applyQuaternion(inverseCameraRotation);
    return [projected.x, projected.y, projected.z];
  };
  return {
    x: projectAxis(1, 0, 0),
    y: projectAxis(0, 1, 0),
    z: projectAxis(0, 0, 1)
  };
}

function isNumericArray(value, stride = 1) {
  return (
    (Array.isArray(value) || ArrayBuffer.isView(value)) &&
    value.length >= stride &&
    value.length % stride === 0
  );
}

function emptyLineGeometry(THREE) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([], 3));
  return geometry;
}

function dataUrlToBlob(dataUrl) {
  const parts = String(dataUrl || "").split(",");
  if (parts.length !== 2) {
    throw new Error("Screenshot encoding failed");
  }
  const mimeMatch = parts[0].match(/data:(.*?);base64/);
  const mimeType = mimeMatch?.[1] || "image/png";
  const binary = atob(parts[1]);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: mimeType });
}

function getViewerThemeValue(viewerTheme, key, fallback) {
  const value = viewerTheme?.[key];
  return value ?? BASE_VIEWER_THEME[key] ?? fallback;
}

function getViewerThemeNumber(viewerTheme, key, fallback) {
  const value = Number(getViewerThemeValue(viewerTheme, key, fallback));
  return Number.isFinite(value) ? value : fallback;
}

function normalizeFloorMode(value, fallback = LOOK_FLOOR_MODES.STAGE) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "glass") {
    return LOOK_FLOOR_MODES.STAGE;
  }
  return Object.values(LOOK_FLOOR_MODES).includes(normalized)
    ? normalized
    : fallback;
}

function resolveFloorMode(floorSettings = {}) {
  return normalizeFloorMode(floorSettings?.mode);
}

function normalizeLookSettingsShape(lookSettings = {}) {
  const materials = lookSettings?.materials || {};
  const edges = lookSettings?.edges || {};
  const background = lookSettings?.background || {};
  const floor = lookSettings?.floor || {};
  const environment = lookSettings?.environment || {};
  const lighting = lookSettings?.lighting || {};
  return {
    materials: {
      defaultColor: String(materials.defaultColor || materials.tintColor || BASE_VIEWER_THEME.surface),
      tintStrength: Number.isFinite(Number(materials.tintStrength)) ? clamp(Number(materials.tintStrength), 0, 1) : 0,
      saturation: Number.isFinite(Number(materials.saturation)) ? clamp(Number(materials.saturation), 0, 2.5) : 1,
      contrast: Number.isFinite(Number(materials.contrast)) ? clamp(Number(materials.contrast), 0, 2.5) : 1,
      brightness: Number.isFinite(Number(materials.brightness)) ? clamp(Number(materials.brightness), 0, 2) : 1,
      roughness: Number.isFinite(Number(materials.roughness)) ? Number(materials.roughness) : BASE_VIEWER_THEME.surfaceRoughness,
      metalness: Number.isFinite(Number(materials.metalness)) ? Number(materials.metalness) : BASE_VIEWER_THEME.surfaceMetalness,
      clearcoat: Number.isFinite(Number(materials.clearcoat)) ? Number(materials.clearcoat) : BASE_VIEWER_THEME.surfaceClearcoat,
      clearcoatRoughness: Number.isFinite(Number(materials.clearcoatRoughness))
        ? Number(materials.clearcoatRoughness)
        : BASE_VIEWER_THEME.surfaceClearcoatRoughness,
      opacity: Number.isFinite(Number(materials.opacity)) ? Number(materials.opacity) : 1,
      envMapIntensity: Number.isFinite(Number(materials.envMapIntensity)) ? Number(materials.envMapIntensity) : 1
    },
    edges: {
      enabled: edges?.enabled === true,
      color: String(edges.color || BASE_VIEWER_THEME.edge),
      thickness: Number.isFinite(Number(edges.thickness))
        ? clamp(Number(edges.thickness), 0.5, 6)
        : BASE_VIEWER_THEME.edgeThickness,
      opacity: Number.isFinite(Number(edges.opacity))
        ? clamp(Number(edges.opacity), 0, 1)
        : clamp(BASE_VIEWER_THEME.edgeOpacity, 0, 1)
    },
    background: {
      type: String(background.type || LOOK_BACKGROUND_TYPES.SOLID),
      solidColor: String(background.solidColor || BASE_VIEWER_THEME.sceneBackground),
      linearStart: String(background.linearStart || "#0d1015"),
      linearEnd: String(background.linearEnd || "#2a3240"),
      linearAngle: Number.isFinite(Number(background.linearAngle)) ? Number(background.linearAngle) : 180,
      radialInner: String(background.radialInner || "#2a3345"),
      radialOuter: String(background.radialOuter || "#0b0f15")
    },
    floor: {
      mode: normalizeFloorMode(floor.mode),
      color: String(floor.color || BASE_VIEWER_THEME.stageFloorColor),
      roughness: Number.isFinite(Number(floor.roughness)) ? clamp(Number(floor.roughness), 0, 1) : 0.72,
      reflectivity: Number.isFinite(Number(floor.reflectivity)) ? clamp(Number(floor.reflectivity), 0, 1) : 0.12,
      shadowOpacity: Number.isFinite(Number(floor.shadowOpacity)) ? clamp(Number(floor.shadowOpacity), 0, 1) : 0.45,
      horizonBlend: Number.isFinite(Number(floor.horizonBlend)) ? clamp(Number(floor.horizonBlend), 0, 1) : 0
    },
    environment: {
      enabled: environment?.enabled !== false,
      presetId: String(environment.presetId || ""),
      intensity: Number.isFinite(Number(environment.intensity)) ? Number(environment.intensity) : 1,
      rotationY: Number.isFinite(Number(environment.rotationY)) ? Number(environment.rotationY) : 0,
      useAsBackground: environment?.useAsBackground === true
    },
    lighting: {
      toneMappingExposure: Number.isFinite(Number(lighting?.toneMappingExposure))
        ? Number(lighting.toneMappingExposure)
        : DEFAULT_LIGHTING.toneMappingExposure,
      directional: {
        enabled: lighting?.directional?.enabled !== false,
        color: String(lighting?.directional?.color || "#ffffff"),
        intensity: Number.isFinite(Number(lighting?.directional?.intensity)) ? Number(lighting.directional.intensity) : 1,
        position: {
          x: Number.isFinite(Number(lighting?.directional?.position?.x)) ? Number(lighting.directional.position.x) : 140,
          y: Number.isFinite(Number(lighting?.directional?.position?.y)) ? Number(lighting.directional.position.y) : 220,
          z: Number.isFinite(Number(lighting?.directional?.position?.z)) ? Number(lighting.directional.position.z) : 140
        }
      },
      spot: {
        enabled: lighting?.spot?.enabled === true,
        color: String(lighting?.spot?.color || "#ffffff"),
        intensity: Number.isFinite(Number(lighting?.spot?.intensity)) ? Number(lighting.spot.intensity) : 1,
        angle: Number.isFinite(Number(lighting?.spot?.angle)) ? Number(lighting.spot.angle) : Math.PI / 6,
        distance: Number.isFinite(Number(lighting?.spot?.distance)) ? Number(lighting.spot.distance) : 0,
        position: {
          x: Number.isFinite(Number(lighting?.spot?.position?.x)) ? Number(lighting.spot.position.x) : 160,
          y: Number.isFinite(Number(lighting?.spot?.position?.y)) ? Number(lighting.spot.position.y) : 120,
          z: Number.isFinite(Number(lighting?.spot?.position?.z)) ? Number(lighting.spot.position.z) : 100
        }
      },
      point: {
        enabled: lighting?.point?.enabled === true,
        color: String(lighting?.point?.color || "#ffffff"),
        intensity: Number.isFinite(Number(lighting?.point?.intensity)) ? Number(lighting.point.intensity) : 1,
        distance: Number.isFinite(Number(lighting?.point?.distance)) ? Number(lighting.point.distance) : 0,
        position: {
          x: Number.isFinite(Number(lighting?.point?.position?.x)) ? Number(lighting.point.position.x) : -120,
          y: Number.isFinite(Number(lighting?.point?.position?.y)) ? Number(lighting.point.position.y) : 80,
          z: Number.isFinite(Number(lighting?.point?.position?.z)) ? Number(lighting.point.position.z) : 140
        }
      },
      ambient: {
        enabled: lighting?.ambient?.enabled === true,
        color: String(lighting?.ambient?.color || "#ffffff"),
        intensity: Number.isFinite(Number(lighting?.ambient?.intensity)) ? Number(lighting.ambient.intensity) : 0
      },
      hemisphere: {
        enabled: lighting?.hemisphere?.enabled !== false,
        skyColor: String(lighting?.hemisphere?.skyColor || "#ffffff"),
        groundColor: String(lighting?.hemisphere?.groundColor || "#e6eaef"),
        intensity: Number.isFinite(Number(lighting?.hemisphere?.intensity)) ? Number(lighting.hemisphere.intensity) : 1
      }
    }
  };
}

function getPixelRatioCap(cap) {
  if (typeof window === "undefined") {
    return 1;
  }
  return Math.min(window.devicePixelRatio || 1, cap);
}

function toThemeArray(value) {
  if (Array.isArray(value)) {
    return value.filter(Boolean);
  }
  return value ? [value] : [];
}

function colorToRgba(THREE, value, alpha = 1) {
  const color = new THREE.Color(value || "#000000");
  return `rgba(${Math.round(color.r * 255)}, ${Math.round(color.g * 255)}, ${Math.round(color.b * 255)}, ${clamp(alpha, 0, 1)})`;
}

function normalizeGradientStops(stops) {
  const filteredStops = toThemeArray(stops);
  if (!filteredStops.length) {
    return [];
  }
  return filteredStops
    .map((stop, index) => {
      if (typeof stop === "string") {
        return {
          offset: filteredStops.length === 1 ? 0 : index / (filteredStops.length - 1),
          color: stop
        };
      }
      const fallbackOffset = filteredStops.length === 1 ? 0 : index / (filteredStops.length - 1);
      const offset = Number(stop?.offset);
      return {
        offset: Number.isFinite(offset) ? clamp(offset, 0, 1) : fallbackOffset,
        color: stop?.color || stop?.value || "#000000"
      };
    })
    .sort((left, right) => left.offset - right.offset);
}

function createSceneBackgroundTexture(THREE, viewerTheme, lookBackground = null) {
  const backgroundType = String(lookBackground?.type || "").trim().toLowerCase();
  const useLookBackground = !!backgroundType;
  const gradientStops = useLookBackground
    ? (
      backgroundType === LOOK_BACKGROUND_TYPES.LINEAR
        ? [
          { offset: 0, color: lookBackground.linearStart || "#000000" },
          { offset: 1, color: lookBackground.linearEnd || "#ffffff" }
        ]
        : backgroundType === LOOK_BACKGROUND_TYPES.RADIAL
          ? [
            { offset: 0, color: lookBackground.radialInner || "#000000" },
            { offset: 1, color: lookBackground.radialOuter || "#ffffff" }
          ]
          : []
    )
    : normalizeGradientStops(viewerTheme?.sceneBackgroundGradient);
  const glowLayers = useLookBackground ? [] : toThemeArray(viewerTheme?.sceneBackgroundGlow);
  if (!gradientStops.length && !glowLayers.length) {
    return null;
  }

  const canvas = document.createElement("canvas");
  canvas.width = BACKGROUND_TEXTURE_SIZE;
  canvas.height = BACKGROUND_TEXTURE_SIZE;
  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }

  context.fillStyle = useLookBackground
    ? lookBackground.solidColor || BASE_VIEWER_THEME.sceneBackground
    : viewerTheme?.sceneBackground || BASE_VIEWER_THEME.sceneBackground;
  context.fillRect(0, 0, canvas.width, canvas.height);

  if (gradientStops.length) {
    if (backgroundType === LOOK_BACKGROUND_TYPES.RADIAL) {
      const radialGradient = context.createRadialGradient(
        canvas.width / 2,
        canvas.height / 2,
        canvas.width * 0.1,
        canvas.width / 2,
        canvas.height / 2,
        canvas.width * 0.75
      );
      for (const stop of gradientStops) {
        radialGradient.addColorStop(stop.offset, stop.color);
      }
      context.fillStyle = radialGradient;
      context.fillRect(0, 0, canvas.width, canvas.height);
    } else {
      const angleDeg = Number.isFinite(Number(lookBackground?.linearAngle)) ? Number(lookBackground.linearAngle) : 180;
      const angleRad = (angleDeg * Math.PI) / 180;
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const radius = Math.max(canvas.width, canvas.height);
      const x1 = cx - Math.cos(angleRad) * radius;
      const y1 = cy - Math.sin(angleRad) * radius;
      const x2 = cx + Math.cos(angleRad) * radius;
      const y2 = cy + Math.sin(angleRad) * radius;
      const linearGradient = context.createLinearGradient(x1, y1, x2, y2);
      for (const stop of gradientStops) {
        linearGradient.addColorStop(stop.offset, stop.color);
      }
      context.fillStyle = linearGradient;
      context.fillRect(0, 0, canvas.width, canvas.height);
    }
  }

  for (const glowLayer of glowLayers) {
    const resolvedX = Number(glowLayer?.x);
    const resolvedY = Number(glowLayer?.y);
    const x = Number.isFinite(resolvedX) ? clamp(resolvedX, 0, 1) : 0.5;
    const y = Number.isFinite(resolvedY) ? clamp(resolvedY, 0, 1) : 0.5;
    const radius = Math.max(Number(glowLayer?.radius) || 0, 0.08);
    const opacity = clamp(Number(glowLayer?.opacity) || 0, 0, 1);
    if (opacity <= 0) {
      continue;
    }
    const centerX = canvas.width * x;
    const centerY = canvas.height * y;
    const outerRadius = canvas.width * radius;
    const glow = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, outerRadius);
    glow.addColorStop(0, colorToRgba(THREE, glowLayer?.color || "#ffffff", opacity));
    glow.addColorStop(0.5, colorToRgba(THREE, glowLayer?.color || "#ffffff", opacity * 0.3));
    glow.addColorStop(1, colorToRgba(THREE, glowLayer?.color || "#ffffff", 0));
    context.fillStyle = glow;
    context.fillRect(0, 0, canvas.width, canvas.height);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  return texture;
}

function disposeTexture(texture) {
  texture?.dispose?.();
}

function applySceneBackground(runtime, viewerTheme, lookBackground = null) {
  if (!runtime?.THREE || !runtime?.scene) {
    return;
  }
  if (String(lookBackground?.type || "").toLowerCase() === LOOK_BACKGROUND_TYPES.TRANSPARENT) {
    disposeTexture(runtime.sceneBackgroundTexture);
    runtime.sceneBackgroundTexture = null;
    runtime.scene.background = null;
    runtime.renderer?.setClearAlpha?.(0);
    return;
  }
  runtime.renderer?.setClearAlpha?.(1);
  disposeTexture(runtime.sceneBackgroundTexture);
  runtime.sceneBackgroundTexture = createSceneBackgroundTexture(runtime.THREE, viewerTheme, lookBackground);
  if (runtime.sceneBackgroundTexture) {
    runtime.scene.background = runtime.sceneBackgroundTexture;
    return;
  }
  runtime.scene.background = new runtime.THREE.Color(
    lookBackground?.solidColor || viewerTheme.sceneBackground || BASE_VIEWER_THEME.sceneBackground
  );
}

function createSafeColor(THREE, value, fallback = "#000000") {
  const normalizedValue = String(value || "").trim();
  const normalizedFallback = String(fallback || "#000000").trim();
  const colorValue = HEX_COLOR_PATTERN.test(normalizedValue) ? normalizedValue : normalizedFallback;
  try {
    return new THREE.Color(colorValue);
  } catch {
    return new THREE.Color(HEX_COLOR_PATTERN.test(normalizedFallback) ? normalizedFallback : "#000000");
  }
}

function resolveBackgroundFloorColor(THREE, lookBackground = {}, viewerTheme = BASE_VIEWER_THEME) {
  const fallbackColor = viewerTheme?.stageFloorColor || viewerTheme?.sceneBackground || BASE_VIEWER_THEME.stageFloorColor;
  const backgroundType = String(lookBackground?.type || "").trim().toLowerCase();
  if (backgroundType === LOOK_BACKGROUND_TYPES.LINEAR) {
    return createSafeColor(THREE, lookBackground.linearStart, fallbackColor)
      .lerp(createSafeColor(THREE, lookBackground.linearEnd, fallbackColor), 0.7);
  }
  if (backgroundType === LOOK_BACKGROUND_TYPES.RADIAL) {
    return createSafeColor(THREE, lookBackground.radialInner, fallbackColor)
      .lerp(createSafeColor(THREE, lookBackground.radialOuter, fallbackColor), 0.72);
  }
  if (backgroundType === LOOK_BACKGROUND_TYPES.SOLID) {
    return createSafeColor(THREE, lookBackground.solidColor, fallbackColor);
  }
  return createSafeColor(THREE, fallbackColor, BASE_VIEWER_THEME.stageFloorColor);
}

function resolveStageFloorGlassFactor(lookSettings = {}) {
  const materials = lookSettings?.materials || {};
  const environment = lookSettings?.environment || {};
  const roughness = clamp(Number(materials.roughness) || 0, 0, 1);
  const clearcoat = clamp(Number(materials.clearcoat) || 0, 0, 1);
  const envSignal = environment?.enabled
    ? clamp(((Number(materials.envMapIntensity) || 0) * (Number(environment.intensity) || 0)) / 3, 0, 1)
    : 0;
  return clamp((clearcoat * 0.5) + ((1 - roughness) * 0.25) + (envSignal * 0.35), 0, 1);
}

function resolveStageFloorColor(THREE, viewerTheme, lookSettings = {}) {
  const explicitFloorColor = String(lookSettings?.floor?.color || "").trim();
  if (HEX_COLOR_PATTERN.test(explicitFloorColor)) {
    return createSafeColor(THREE, explicitFloorColor, viewerTheme?.stageFloorColor || BASE_VIEWER_THEME.stageFloorColor);
  }

  const backgroundColor = resolveBackgroundFloorColor(THREE, lookSettings?.background, viewerTheme);
  const glassFactor = resolveStageFloorGlassFactor(lookSettings);
  if (glassFactor >= 0.35) {
    const backgroundHsl = {};
    backgroundColor.getHSL(backgroundHsl);
    const floorColor = backgroundColor.clone();
    const lightness = backgroundHsl.l < 0.42
      ? clamp(backgroundHsl.l + 0.012, 0.06, 0.14)
      : clamp(backgroundHsl.l - 0.045, 0.36, 0.78);
    floorColor.setHSL(backgroundHsl.h, clamp(backgroundHsl.s * 0.14, 0, 0.04), lightness);
    return floorColor;
  }

  const groundColor = createSafeColor(
    THREE,
    lookSettings?.lighting?.hemisphere?.groundColor,
    viewerTheme?.stageFloorColor || BASE_VIEWER_THEME.stageFloorColor
  );
  const defaultColor = createSafeColor(THREE, lookSettings?.materials?.defaultColor, "#ffffff");
  const floorColor = backgroundColor.clone()
    .lerp(groundColor, 0.42 - (glassFactor * 0.24))
    .lerp(defaultColor, 0.07 - (glassFactor * 0.04))
    .lerp(backgroundColor, glassFactor * 0.5);
  const floorHsl = {};
  const backgroundHsl = {};
  floorColor.getHSL(floorHsl);
  backgroundColor.getHSL(backgroundHsl);
  const lightness = backgroundHsl.l < 0.42
    ? clamp(
      Math.max(floorHsl.l, backgroundHsl.l + (0.055 - (glassFactor * 0.035))),
      0.1 - (glassFactor * 0.04),
      0.34 - (glassFactor * 0.13)
    )
    : clamp(Math.min(floorHsl.l, backgroundHsl.l - 0.075), 0.38, 0.78);
  floorColor.setHSL(
    floorHsl.h,
    clamp(floorHsl.s * (0.58 - (glassFactor * 0.2)), 0.025, 0.38),
    lightness
  );
  return floorColor;
}

function getStageFloorSetting(lookSettings, key, fallback, min = 0, max = 1) {
  const value = Number(lookSettings?.floor?.[key]);
  return Number.isFinite(value) ? clamp(value, min, max) : fallback;
}

function createStageFloorGlowTexture(THREE, color, opacity) {
  const resolvedOpacity = clamp(Number(opacity) || 0, 0, 1);
  if (resolvedOpacity <= 0.001 || typeof document === "undefined") {
    return null;
  }

  const canvas = document.createElement("canvas");
  canvas.width = FLOOR_GLOW_TEXTURE_SIZE;
  canvas.height = FLOOR_GLOW_TEXTURE_SIZE;
  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }

  const center = FLOOR_GLOW_TEXTURE_SIZE / 2;
  const gradient = context.createRadialGradient(center, center, 0, center, center, center);
  gradient.addColorStop(0, colorToRgba(THREE, color, resolvedOpacity));
  gradient.addColorStop(0.28, colorToRgba(THREE, color, resolvedOpacity * 0.56));
  gradient.addColorStop(0.62, colorToRgba(THREE, color, resolvedOpacity * 0.16));
  gradient.addColorStop(1, colorToRgba(THREE, color, 0));
  context.fillStyle = gradient;
  context.fillRect(0, 0, canvas.width, canvas.height);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  return texture;
}

function createStageFloorPlane(THREE, viewerTheme, lookSettings, size, floorY, lift = 0) {
  const glassFactor = resolveStageFloorGlassFactor(lookSettings);
  const horizonBlend = getStageFloorSetting(lookSettings, "horizonBlend", 0, 0, 1);
  const reflectivity = getStageFloorSetting(lookSettings, "reflectivity", 0.12, 0, 1);
  const roughness = getStageFloorSetting(
    lookSettings,
    "roughness",
    clamp(getViewerThemeNumber(viewerTheme, "stageFloorRoughness", 0.92) - (glassFactor * 0.48), 0.16, 1),
    0,
    1
  );
  const opacity = clamp(
    (getViewerThemeNumber(viewerTheme, "stageFloorOpacity", 0.78) - (glassFactor * 0.02)) * (1 - (horizonBlend * 0.3)),
    0.62,
    1
  );
  const envMapIntensity = clamp(
    (
      Number(lookSettings?.materials?.envMapIntensity || 0) *
        (lookSettings?.environment?.enabled ? Number(lookSettings?.environment?.intensity || 0) : 0) *
        (0.08 + (glassFactor * 0.1))
    ) + (reflectivity * 0.48),
    0,
    1.15
  );
  const material = new THREE.MeshPhysicalMaterial({
    color: resolveStageFloorColor(THREE, viewerTheme, lookSettings),
    roughness,
    metalness: clamp(getViewerThemeNumber(viewerTheme, "stageFloorMetalness", 0) + (reflectivity * 0.06), 0, 0.18),
    clearcoat: clamp((reflectivity * 0.58) + (glassFactor * 0.12), 0, 0.9),
    clearcoatRoughness: clamp(
      roughness * 0.62,
      0.04,
      0.8
    ),
    reflectivity,
    transmission: clamp(
      getViewerThemeNumber(viewerTheme, "stageFloorTransmission", BASE_VIEWER_THEME.stageFloorTransmission) +
        (glassFactor * 0.005),
      0,
      0.02
    ),
    ior: getViewerThemeNumber(viewerTheme, "stageFloorIor", BASE_VIEWER_THEME.stageFloorIor),
    thickness: getViewerThemeNumber(viewerTheme, "stageFloorThickness", BASE_VIEWER_THEME.stageFloorThickness),
    attenuationDistance: getViewerThemeNumber(
      viewerTheme,
      "stageFloorAttenuationDistance",
      BASE_VIEWER_THEME.stageFloorAttenuationDistance
    ),
    transparent: opacity < 0.999 || glassFactor > 0.05,
    opacity,
    side: THREE.FrontSide,
    depthWrite: opacity >= 0.9,
    envMapIntensity
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, 1, 1), material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.set(0, floorY + lift, 0);
  mesh.scale.set(size, size, 1);
  mesh.receiveShadow = false;
  mesh.castShadow = false;
  mesh.renderOrder = -3;
  return mesh;
}

function createStageFloorGlowPlane(THREE, lookSettings, lightingScopeRadius, size, floorY, sceneScaleMode, lift = 0.008) {
  const spotLight = lookSettings?.lighting?.spot || {};
  if (spotLight.enabled === false) {
    return null;
  }

  const reflectivity = getStageFloorSetting(lookSettings, "reflectivity", 0.12, 0, 1);
  const shadowOpacity = getStageFloorSetting(lookSettings, "shadowOpacity", 0.45, 0, 1);
  const spotIntensity = Math.max(Number(spotLight.intensity) || 0, 0);
  const glowOpacity = clamp(0.025 + (spotIntensity * 0.11) + (reflectivity * 0.32) - (shadowOpacity * 0.06), 0, 0.36);
  const texture = createStageFloorGlowTexture(THREE, spotLight.color || "#ffffff", glowOpacity);
  if (!texture) {
    return null;
  }

  const sceneScaleSettings = getSceneScaleSettings(sceneScaleMode);
  const safeLightingRadius = Math.max(Number(lightingScopeRadius) || 0, getLightingScopeRadius(sceneScaleMode));
  const glowSize = Math.min(
    size * 0.24,
    Math.max(safeLightingRadius * 8, sceneScaleSettings.minGridSize * 3.4)
  );
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    opacity: 1,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.FrontSide,
    toneMapped: true
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, 1, 1), material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.set(0, floorY + lift, 0);
  mesh.scale.set(glowSize * 1.45, glowSize, 1);
  mesh.receiveShadow = false;
  mesh.castShadow = false;
  mesh.renderOrder = -2.8;
  return mesh;
}

function createStageShadowPlane(THREE, lookSettings, size, floorY, lift = 0.01) {
  const opacity = getStageFloorSetting(lookSettings, "shadowOpacity", 0.45, 0, 1);
  if (opacity <= 0.001) {
    return null;
  }
  const material = new THREE.ShadowMaterial({
    color: 0x000000,
    opacity,
    transparent: true,
    depthWrite: false
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, 1, 1), material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.set(0, floorY + lift, 0);
  mesh.scale.set(size, size, 1);
  mesh.receiveShadow = true;
  mesh.castShadow = false;
  mesh.renderOrder = -2;
  return mesh;
}

function updateSpotLightTarget(runtime) {
  if (!runtime?.spotLight?.target?.position) {
    return;
  }
  const floorY = Number(runtime.gridFloorY);
  const targetY = runtime.floorMode !== LOOK_FLOOR_MODES.NONE && Number.isFinite(floorY) ? floorY : 0;
  runtime.spotLight.target.position.set(0, targetY, 0);
  runtime.spotLight.target.updateMatrixWorld?.();
}

function getStageFloorSize(radius, sceneScaleMode) {
  const sceneScaleSettings = getSceneScaleSettings(sceneScaleMode);
  const safeRadius = clampSceneModelRadius(radius, sceneScaleMode);
  return Math.max(sceneScaleSettings.minGridSize * 80, safeRadius * 160);
}

function updateStageEffects(runtime, viewerTheme, lookSettings, radius, floorY = 0, floorMode = LOOK_FLOOR_MODES.STAGE) {
  if (!runtime?.THREE || !runtime?.stageGroup) {
    return;
  }

  clearSceneGroup(runtime.stageGroup);

  if (floorMode !== LOOK_FLOOR_MODES.STAGE) {
    return;
  }

  const floorSize = getStageFloorSize(radius, runtime.sceneScaleMode);
  const lightingScopeRadius = getLightingScopeRadius(runtime.sceneScaleMode);
  runtime.stageGroup.add(createStageFloorPlane(runtime.THREE, viewerTheme, lookSettings, floorSize, floorY, 0));
  const glowPlane = createStageFloorGlowPlane(
    runtime.THREE,
    lookSettings,
    lightingScopeRadius,
    floorSize,
    floorY,
    runtime.sceneScaleMode
  );
  if (glowPlane) {
    runtime.stageGroup.add(glowPlane);
  }
  const shadowPlane = createStageShadowPlane(runtime.THREE, lookSettings, floorSize, floorY);
  if (shadowPlane) {
    runtime.stageGroup.add(shadowPlane);
  }
}

function isTrackpadLikeWheelEvent(event) {
  return event.ctrlKey || (event.deltaMode === 0 && Math.abs(event.deltaY) < 20);
}

function normalizeViewportFrameInsets(value = {}) {
  const normalizeInset = (inset) => {
    const numericInset = Number(inset);
    return Number.isFinite(numericInset) ? Math.max(0, numericInset) : 0;
  };
  return {
    top: normalizeInset(value?.top),
    right: normalizeInset(value?.right),
    bottom: normalizeInset(value?.bottom),
    left: normalizeInset(value?.left)
  };
}

function getViewportFrameMetrics(runtime, frameInsets = {}) {
  const canvas = runtime?.renderer?.domElement;
  const width = Math.max(1, canvas?.clientWidth || canvas?.parentElement?.clientWidth || 1);
  const height = Math.max(1, canvas?.clientHeight || canvas?.parentElement?.clientHeight || 1);
  const normalizedInsets = normalizeViewportFrameInsets(frameInsets);
  const left = clamp(normalizedInsets.left, 0, Math.max(width - 1, 0));
  const right = clamp(normalizedInsets.right, 0, Math.max(width - left - 1, 0));
  const top = clamp(normalizedInsets.top, 0, Math.max(height - 1, 0));
  const bottom = clamp(normalizedInsets.bottom, 0, Math.max(height - top - 1, 0));
  const framedWidth = Math.max(1, width - left - right);
  const framedHeight = Math.max(1, height - top - bottom);
  const centerX = left + framedWidth / 2;
  const centerY = top + framedHeight / 2;

  return {
    width,
    height,
    framedWidth,
    framedHeight,
    aspect: framedWidth / framedHeight,
    offsetNdcX: (centerX / width) * 2 - 1,
    offsetNdcY: 1 - (centerY / height) * 2
  };
}

function applyCameraFrameInsets(runtime, frameInsets = {}, { updateProjection = true } = {}) {
  const camera = runtime?.camera;
  if (!camera?.projectionMatrix?.elements) {
    return;
  }
  if (updateProjection) {
    camera.updateProjectionMatrix();
  }
  const { offsetNdcX, offsetNdcY } = getViewportFrameMetrics(runtime, frameInsets);
  camera.projectionMatrix.elements[8] -= offsetNdcX;
  camera.projectionMatrix.elements[9] -= offsetNdcY;
  if (camera.projectionMatrixInverse?.copy) {
    camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
  }
}

function getFitDistanceForBoundingSphere(camera, radius, sceneScaleMode, frameAspect = camera.aspect) {
  const safeRadius = Math.max(radius * MODEL_FRAME_BUFFER, getSceneScaleSettings(sceneScaleMode).minModelRadius);
  const verticalHalfFov = (camera.fov * Math.PI) / 360;
  const horizontalHalfFov = Math.atan(Math.tan(verticalHalfFov) * Math.max(frameAspect, 1e-3));
  const limitingHalfFov = Math.max(Math.min(verticalHalfFov, horizontalHalfFov), 1e-3);
  return safeRadius / Math.sin(limitingHalfFov);
}

function easeInOutCubic(t) {
  if (t <= 0) {
    return 0;
  }
  if (t >= 1) {
    return 1;
  }
  return t < 0.5 ? 4 * t * t * t : 1 - ((-2 * t + 2) ** 3) / 2;
}

function easeOutCubic(t) {
  if (t <= 0) {
    return 0;
  }
  if (t >= 1) {
    return 1;
  }
  return 1 - ((1 - t) ** 3);
}

function easeOutBack(t) {
  if (t <= 0) {
    return 0;
  }
  if (t >= 1) {
    return 1;
  }
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + (c3 * ((t - 1) ** 3)) + (c1 * ((t - 1) ** 2));
}

function mix(a, b, t) {
  return a + ((b - a) * t);
}

function readPerspectiveSnapshot(runtime) {
  if (!runtime?.camera || !runtime?.controls) {
    return null;
  }
  return {
    position: [runtime.camera.position.x, runtime.camera.position.y, runtime.camera.position.z],
    target: [runtime.controls.target.x, runtime.controls.target.y, runtime.controls.target.z],
    up: [runtime.camera.up.x, runtime.camera.up.y, runtime.camera.up.z]
  };
}

function readScopedPerspectiveSnapshot(runtime, { modelKey = "", sceneScaleMode = "" } = {}) {
  return annotatePerspectiveSnapshot(readPerspectiveSnapshot(runtime), {
    modelKey,
    sceneScaleMode
  });
}

function maxDrawingStrokeOrdinal(strokes) {
  let maxOrdinal = 0;
  for (const stroke of Array.isArray(strokes) ? strokes : []) {
    const match = /^stroke-(\d+)$/.exec(String(stroke?.id || ""));
    if (!match) {
      continue;
    }
    const nextOrdinal = Number(match[1]);
    if (Number.isFinite(nextOrdinal) && nextOrdinal > maxOrdinal) {
      maxOrdinal = nextOrdinal;
    }
  }
  return maxOrdinal;
}

function getKeyboardOrbitCommand(event) {
  if (!event) {
    return null;
  }
  if (event.key === "ArrowLeft") {
    return { direction: "left", keyId: "ArrowLeft" };
  }
  if (event.key === "ArrowRight") {
    return { direction: "right", keyId: "ArrowRight" };
  }
  if (event.key === "ArrowUp") {
    return { direction: "up", keyId: "ArrowUp" };
  }
  if (event.key === "ArrowDown") {
    return { direction: "down", keyId: "ArrowDown" };
  }

  const key = String(event.key || "").toLowerCase();
  if (key === "a" || event.code === "KeyA") {
    return { direction: "left", keyId: event.code || "KeyA" };
  }
  if (key === "d" || event.code === "KeyD") {
    return { direction: "right", keyId: event.code || "KeyD" };
  }
  if (key === "w" || event.code === "KeyW") {
    return { direction: "up", keyId: event.code || "KeyW" };
  }
  if (key === "s" || event.code === "KeyS") {
    return { direction: "down", keyId: event.code || "KeyS" };
  }
  return null;
}

function getKeyboardOrbitAxes(keyboardOrbitState) {
  return {
    azimuth:
      (keyboardOrbitState.directionCounts.right > 0 ? 1 : 0) -
      (keyboardOrbitState.directionCounts.left > 0 ? 1 : 0),
    polar:
      (keyboardOrbitState.directionCounts.down > 0 ? 1 : 0) -
      (keyboardOrbitState.directionCounts.up > 0 ? 1 : 0)
  };
}

function clearKeyboardOrbitState(keyboardOrbitState) {
  if (!keyboardOrbitState) {
    return;
  }
  keyboardOrbitState.pressedKeys.clear();
  keyboardOrbitState.directionCounts.left = 0;
  keyboardOrbitState.directionCounts.right = 0;
  keyboardOrbitState.directionCounts.up = 0;
  keyboardOrbitState.directionCounts.down = 0;
  keyboardOrbitState.lastFrameTime = 0;
}

function applyOrbitDelta(runtime, azimuthDelta, polarDelta) {
  if (!runtime?.THREE || !runtime?.camera || !runtime?.controls) {
    return false;
  }
  if (Math.abs(azimuthDelta) < 1e-6 && Math.abs(polarDelta) < 1e-6) {
    return false;
  }

  const offset = new runtime.THREE.Vector3().copy(runtime.camera.position).sub(runtime.controls.target);
  const spherical = new runtime.THREE.Spherical().setFromVector3(offset);
  const minPolar = Math.max(
    Number.isFinite(runtime.controls.minPolarAngle) ? runtime.controls.minPolarAngle : 0,
    KEYBOARD_POLAR_EPSILON
  );
  const maxPolar = Math.min(
    Number.isFinite(runtime.controls.maxPolarAngle) ? runtime.controls.maxPolarAngle : Math.PI,
    Math.PI - KEYBOARD_POLAR_EPSILON
  );
  const nextTheta = spherical.theta + azimuthDelta;
  const minAzimuth = Number.isFinite(runtime.controls.minAzimuthAngle) ? runtime.controls.minAzimuthAngle : -Infinity;
  const maxAzimuth = Number.isFinite(runtime.controls.maxAzimuthAngle) ? runtime.controls.maxAzimuthAngle : Infinity;

  spherical.theta = clamp(normalizeAngleAround(nextTheta, spherical.theta), minAzimuth, maxAzimuth);
  spherical.phi = clamp(spherical.phi + polarDelta, minPolar, maxPolar);
  spherical.makeSafe();
  offset.setFromSpherical(spherical);
  runtime.camera.position.copy(runtime.controls.target).add(offset);
  runtime.camera.lookAt(runtime.controls.target);
  return true;
}

function stepKeyboardOrbit(runtime, timestamp) {
  const keyboardOrbitState = runtime?.keyboardOrbitState;
  if (!keyboardOrbitState) {
    return false;
  }

  const axes = getKeyboardOrbitAxes(keyboardOrbitState);
  if (!axes.azimuth && !axes.polar) {
    keyboardOrbitState.lastFrameTime = 0;
    return false;
  }
  if (!keyboardOrbitState.lastFrameTime) {
    keyboardOrbitState.lastFrameTime = timestamp;
    return false;
  }

  const deltaSeconds = clamp((timestamp - keyboardOrbitState.lastFrameTime) / 1000, 0, 0.05);
  keyboardOrbitState.lastFrameTime = timestamp;
  return applyOrbitDelta(
    runtime,
    axes.azimuth * KEYBOARD_ORBIT_SPEED_RAD_PER_SEC * deltaSeconds,
    axes.polar * KEYBOARD_ORBIT_SPEED_RAD_PER_SEC * deltaSeconds
  );
}

function cancelCameraTransition(runtime, { scheduleIdle = true } = {}) {
  if (!runtime?.cameraTransition) {
    return;
  }
  runtime.cameraTransition = null;
  if (runtime.controls) {
    runtime.controls.enableDamping = true;
    runtime.controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
  }
  if (scheduleIdle) {
    runtime.scheduleIdleQuality?.();
  }
}

function applyPerspectiveSnapshot(runtime, perspective, { scheduleIdle = true } = {}) {
  const nextPerspective = clonePerspectiveSnapshot(perspective);
  if (!runtime?.camera || !runtime?.controls || !nextPerspective) {
    return false;
  }
  cancelCameraTransition(runtime, { scheduleIdle: false });
  clearKeyboardOrbitState(runtime.keyboardOrbitState);
  runtime.camera.position.set(...nextPerspective.position);
  runtime.controls.target.set(...nextPerspective.target);
  runtime.camera.up.set(...nextPerspective.up);
  runtime.camera.lookAt(runtime.controls.target);
  runtime.controls.update();
  if (scheduleIdle) {
    runtime.scheduleIdleQuality?.();
  }
  runtime.requestRender?.();
  return true;
}

function stepCameraTransition(runtime, timestamp) {
  const transition = runtime?.cameraTransition;
  if (!transition || !runtime?.THREE || !runtime?.camera || !runtime?.controls) {
    return false;
  }

  const durationMs = Math.max(transition.durationMs, 1);
  const progress = clamp((timestamp - transition.startTime) / durationMs, 0, 1);
  const eased = easeInOutCubic(progress);
  const position = new runtime.THREE.Vector3().lerpVectors(
    transition.startPosition,
    transition.endPosition,
    eased
  );
  const target = new runtime.THREE.Vector3().lerpVectors(
    transition.startTarget,
    transition.endTarget,
    eased
  );
  const up = new runtime.THREE.Vector3().lerpVectors(
    transition.startUp,
    transition.endUp,
    eased
  );
  runtime.camera.position.copy(position);
  runtime.controls.target.copy(target);
  if (up.lengthSq() > 1e-6) {
    runtime.camera.up.copy(up.normalize());
  }
  runtime.camera.lookAt(target);

  if (progress >= 1) {
    runtime.cameraTransition = null;
    runtime.controls.enableDamping = true;
    runtime.controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
    runtime.scheduleIdleQuality?.();
    return false;
  }
  return true;
}

function transitionCameraToViewPreset(runtime, preset) {
  if (
    !runtime?.THREE ||
    !runtime?.camera ||
    !runtime?.controls ||
    !preset ||
    !Array.isArray(preset.direction) ||
    preset.direction.length !== 3 ||
    !Array.isArray(preset.up) ||
    preset.up.length !== 3
  ) {
    return false;
  }

  const currentTarget = runtime.controls.target.clone();
  const currentOffset = new runtime.THREE.Vector3().copy(runtime.camera.position).sub(currentTarget);
  const fallbackDistance = Math.max(runtime.controls.minDistance || 1, 1);
  const currentDistance = currentOffset.length();
  const distance = clamp(
    Number.isFinite(currentDistance) && currentDistance > 1e-6 ? currentDistance : fallbackDistance,
    runtime.controls.minDistance || 0.01,
    runtime.controls.maxDistance || Infinity
  );
  const nextDirection = new runtime.THREE.Vector3(...preset.direction);
  if (nextDirection.lengthSq() < 1e-6) {
    return false;
  }
  const nextUp = new runtime.THREE.Vector3(...preset.up);
  if (nextUp.lengthSq() < 1e-6) {
    return false;
  }

  nextDirection.normalize();
  nextUp.normalize();
  runtime.cameraTransition = {
    startTime: performance.now(),
    durationMs: VIEW_PLANE_TRANSITION_MS,
    startPosition: runtime.camera.position.clone(),
    endPosition: currentTarget.clone().add(nextDirection.multiplyScalar(distance)),
    startTarget: currentTarget.clone(),
    endTarget: currentTarget.clone(),
    startUp: runtime.camera.up.clone(),
    endUp: nextUp
  };
  runtime.controls.enableDamping = false;
  runtime.beginInteraction?.();
  runtime.requestRender?.();
  return true;
}

function readBoundsVector(THREE, bounds, key) {
  const value = bounds?.[key];
  if (!Array.isArray(value) || value.length < 3) {
    return null;
  }
  const vector = new THREE.Vector3(
    toNumber(value[0], NaN),
    toNumber(value[1], NaN),
    toNumber(value[2], NaN)
  );
  return Number.isFinite(vector.x) && Number.isFinite(vector.y) && Number.isFinite(vector.z)
    ? vector
    : null;
}

function readBoundsCenter(THREE, bounds) {
  const min = readBoundsVector(THREE, bounds, "min");
  const max = readBoundsVector(THREE, bounds, "max");
  if (!min || !max) {
    return null;
  }
  return min.add(max).multiplyScalar(0.5);
}

function readBoundsRadius(THREE, bounds) {
  const min = readBoundsVector(THREE, bounds, "min");
  const max = readBoundsVector(THREE, bounds, "max");
  if (!min || !max) {
    return 0;
  }
  return max.sub(min).length() * 0.5;
}

function readBoundsDimensions(bounds) {
  const min = bounds?.min;
  const max = bounds?.max;
  if (!Array.isArray(min) || !Array.isArray(max) || min.length < 3 || max.length < 3) {
    return null;
  }
  const dimensions = [0, 1, 2].map((index) => Math.abs(toNumber(max[index], NaN) - toNumber(min[index], NaN)));
  return dimensions.every(Number.isFinite) ? dimensions : null;
}

function formatMeasurementMm(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "0.0";
  }
  return numericValue >= 100 ? numericValue.toFixed(0) : numericValue.toFixed(1);
}

function formatMeasurementIn(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "0.00";
  }
  return (numericValue / MM_PER_INCH).toFixed(2);
}

function buildBoundsMeasurement(bounds) {
  const dimensions = readBoundsDimensions(bounds);
  if (!dimensions) {
    return null;
  }
  return {
    dimensions,
    mmText: `${formatMeasurementMm(dimensions[0])} x ${formatMeasurementMm(dimensions[1])} x ${formatMeasurementMm(dimensions[2])} mm`,
    inchText: `${formatMeasurementIn(dimensions[0])} x ${formatMeasurementIn(dimensions[1])} x ${formatMeasurementIn(dimensions[2])} in`
  };
}

function findMeasurementPart(meshData, selectedPartIds, hoveredPartId, focusedPartId) {
  const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  if (!parts.length) {
    return null;
  }
  const preferredIds = [
    ...(Array.isArray(selectedPartIds) ? selectedPartIds : []),
    focusedPartId,
    hoveredPartId
  ].map((id) => String(id || "").trim()).filter(Boolean);
  for (const partId of preferredIds) {
    const part = parts.find((candidate) => (
      String(candidate?.id || "").trim() === partId ||
      String(candidate?.occurrenceId || "").trim() === partId
    ));
    if (part) {
      return part;
    }
  }
  return null;
}

function getActiveViewPlaneFaceId(runtime) {
  if (!runtime?.THREE || !runtime?.camera || !runtime?.controls) {
    return "";
  }

  const offset = new runtime.THREE.Vector3().copy(runtime.camera.position).sub(runtime.controls.target);
  if (offset.lengthSq() < 1e-6) {
    return "";
  }
  offset.normalize();

  let bestId = "";
  let bestScore = -Infinity;
  for (const face of VIEW_PLANE_FACES) {
    const direction = new runtime.THREE.Vector3(...face.direction).normalize();
    const score = offset.dot(direction);
    if (score > bestScore) {
      bestScore = score;
      bestId = face.id;
    }
  }
  return bestScore >= VIEW_PLANE_ACTIVE_DOT_THRESHOLD ? bestId : "";
}

function disposeSceneObject(object) {
  if (!object) {
    return;
  }
  while (object.children?.length) {
    disposeSceneObject(object.children[0]);
  }
  if (typeof object.userData?.beforeDispose === "function") {
    object.userData.beforeDispose(object);
    delete object.userData.beforeDispose;
  }
  object.parent?.remove(object);
  object.geometry?.dispose?.();
  const materials = Array.isArray(object.material) ? object.material : [object.material];
  for (const material of materials) {
    material?.map?.dispose?.();
    material?.alphaMap?.dispose?.();
    material?.dispose?.();
  }
}

function clearSceneGroup(group) {
  while (group.children.length) {
    disposeSceneObject(group.children[0]);
  }
}

function shouldUseDisplayVertexColors(meshData) {
  return !!meshData?.has_source_colors && isNumericArray(meshData?.colors, 3);
}

function partUsesDisplayVertexColors(meshData, part) {
  if (!shouldUseDisplayVertexColors(meshData)) {
    return false;
  }
  if (part && Object.hasOwn(part, "hasSourceColors")) {
    return !!part.hasSourceColors;
  }
  return true;
}

function createSurfaceMaterial(THREE, viewerTheme, { color, useVertexColors = false } = {}) {
  const opacity = Number.isFinite(Number(viewerTheme?.surfaceOpacity))
    ? Number(viewerTheme.surfaceOpacity)
    : 1;
  return new THREE.MeshPhysicalMaterial({
    color: color || viewerTheme?.surface || BASE_VIEWER_THEME.surface,
    roughness: getViewerThemeNumber(viewerTheme, "surfaceRoughness", BASE_VIEWER_THEME.surfaceRoughness),
    metalness: getViewerThemeNumber(viewerTheme, "surfaceMetalness", BASE_VIEWER_THEME.surfaceMetalness),
    clearcoat: getViewerThemeNumber(viewerTheme, "surfaceClearcoat", BASE_VIEWER_THEME.surfaceClearcoat),
    clearcoatRoughness: getViewerThemeNumber(
      viewerTheme,
      "surfaceClearcoatRoughness",
      BASE_VIEWER_THEME.surfaceClearcoatRoughness
    ),
    side: THREE.DoubleSide,
    vertexColors: useVertexColors,
    transparent: opacity < 0.999,
    opacity,
    emissive: 0x000000,
    emissiveIntensity: 0,
    polygonOffset: true,
    polygonOffsetFactor: 2,
    polygonOffsetUnits: 2
  });
}

function readSourceColor(THREE, value) {
  const normalized = String(value || "").trim();
  if (!HEX_COLOR_PATTERN.test(normalized)) {
    return null;
  }
  const expanded = normalized.length === 4
    ? `#${normalized[1]}${normalized[1]}${normalized[2]}${normalized[2]}${normalized[3]}${normalized[3]}`
    : normalized;
  return new THREE.Color(expanded);
}

function shapeSourceColor(THREE, sourceColor, materialSettings = {}, { applyTint = true } = {}) {
  const shaped = (sourceColor || new THREE.Color("#ffffff")).clone();
  const tintStrength = clamp(Number(materialSettings.tintStrength) || 0, 0, 1);
  if (applyTint && tintStrength > 0) {
    const tintColor = createSafeColor(THREE, materialSettings.defaultColor || materialSettings.tintColor, "#ffffff");
    shaped.lerp(shaped.clone().multiply(tintColor), tintStrength);
  }

  const saturation = clamp(Number(materialSettings.saturation) || 1, 0, 2.5);
  if (Math.abs(saturation - 1) > 1e-4) {
    const hsl = {};
    shaped.getHSL(hsl);
    shaped.setHSL(hsl.h, clamp(hsl.s * saturation, 0, 1), hsl.l);
  }

  const contrast = clamp(Number(materialSettings.contrast) || 1, 0, 2.5);
  const brightness = clamp(Number(materialSettings.brightness) || 1, 0, 2);
  shaped.r = clamp(((shaped.r - 0.5) * contrast + 0.5) * brightness, 0, 1);
  shaped.g = clamp(((shaped.g - 0.5) * contrast + 0.5) * brightness, 0, 1);
  shaped.b = clamp(((shaped.b - 0.5) * contrast + 0.5) * brightness, 0, 1);
  return shaped;
}

function shapeSourceColorBuffer(THREE, colors, materialSettings = {}) {
  if (!isNumericArray(colors, 3)) {
    return colors;
  }
  const shapedColors = new Float32Array(colors.length);
  const color = new THREE.Color();
  for (let index = 0; index + 2 < colors.length; index += 3) {
    color.setRGB(
      clamp(Number(colors[index]) || 0, 0, 1),
      clamp(Number(colors[index + 1]) || 0, 0, 1),
      clamp(Number(colors[index + 2]) || 0, 0, 1)
    );
    const shaped = shapeSourceColor(THREE, color, materialSettings);
    shapedColors[index] = shaped.r;
    shapedColors[index + 1] = shaped.g;
    shapedColors[index + 2] = shaped.b;
  }
  return shapedColors;
}

function resolveSourceBaseColor(THREE, { hasVertexColors = false, sourceColor = null, materialSettings, fallbackColor = "#ffffff" }) {
  if (hasVertexColors) {
    return new THREE.Color("#ffffff");
  }
  if (!sourceColor) {
    return shapeSourceColor(
      THREE,
      createSafeColor(THREE, materialSettings?.defaultColor, fallbackColor),
      materialSettings,
      { applyTint: false }
    );
  }
  return shapeSourceColor(THREE, sourceColor, materialSettings);
}

function applyMaterialSettingsToRecord(THREE, record, materialSettings) {
  if (!record?.material || !materialSettings) {
    return;
  }
  const hasVertexColors = !!record.hasVertexColors;
  const nextUseVertexColors = hasVertexColors;
  record.useVertexColors = nextUseVertexColors;
  record.baseColor = resolveSourceBaseColor(THREE, {
    hasVertexColors,
    sourceColor: record.sourceColor || null,
    materialSettings,
    fallbackColor: materialSettings?.defaultColor || BASE_VIEWER_THEME.surface
  });
  record.material.vertexColors = nextUseVertexColors;
  record.material.roughness = clamp(Number(materialSettings.roughness) || 0, 0, 1);
  record.material.metalness = clamp(Number(materialSettings.metalness) || 0, 0, 1);
  record.material.clearcoat = clamp(Number(materialSettings.clearcoat) || 0, 0, 1);
  record.material.clearcoatRoughness = clamp(Number(materialSettings.clearcoatRoughness) || 0, 0, 1);
  record.baseOpacity = clamp(Number(materialSettings.opacity) || 0, 0, 1);
  record.material.opacity = record.baseOpacity;
  record.material.transparent = record.baseOpacity < 0.999;
  record.material.envMapIntensity = Math.max(Number(materialSettings.envMapIntensity) || 0, 0);
  if (record.material.color && record.baseColor) {
    record.material.color.copy(record.baseColor);
  }
  record.material.needsUpdate = true;
}

function getPartHighlightColors(THREE) {
  return {
    hoveredSurfaceColor: new THREE.Color(REFERENCE_HOVER_COLOR),
    hoveredEdgeColor: new THREE.Color(REFERENCE_HOVER_COLOR),
    selectedSurfaceColor: new THREE.Color(REFERENCE_SELECTED_COLOR),
    selectedEdgeColor: new THREE.Color(REFERENCE_SELECTED_COLOR)
  };
}

function getLineSegmentPositions(geometry) {
  const positionAttribute = geometry?.getAttribute?.("position");
  const rawPositions = positionAttribute?.array;
  if (!positionAttribute?.count || !rawPositions?.length) {
    return null;
  }
  return rawPositions;
}

function getEdgeThickness(edgeSettings = null, viewerTheme = null) {
  const fallbackThickness = Number.isFinite(Number(viewerTheme?.edgeThickness))
    ? Number(viewerTheme.edgeThickness)
    : BASE_VIEWER_THEME.edgeThickness;
  return Number.isFinite(Number(edgeSettings?.thickness))
    ? clamp(Number(edgeSettings.thickness), 0.5, 6)
    : fallbackThickness;
}

function createScreenSpaceLineSegments(runtime, positions, {
  color,
  opacity = 1,
  lineWidth = BASE_VIEWER_THEME.edgeThickness,
  renderOrder = 26,
  depthTest = false,
  depthWrite = false
} = {}) {
  if (
    !runtime?.LineSegments2 ||
    !runtime?.LineSegmentsGeometry ||
    !runtime?.LineMaterial ||
    !(Array.isArray(positions) || ArrayBuffer.isView(positions)) ||
    !positions.length
  ) {
    return null;
  }

  const lineGeometry = new runtime.LineSegmentsGeometry();
  lineGeometry.setPositions(positions);
  const lineMaterial = new runtime.LineMaterial({
    color,
    linewidth: lineWidth,
    transparent: true,
    opacity,
    depthTest,
    depthWrite,
    toneMapped: false,
    worldUnits: false
  });
  runtime.registerScreenSpaceLineMaterial?.(lineMaterial);
  const line = new runtime.LineSegments2(lineGeometry, lineMaterial);
  line.renderOrder = renderOrder;
  line.frustumCulled = false;
  line.userData.beforeDispose = () => {
    runtime.unregisterScreenSpaceLineMaterial?.(lineMaterial);
  };
  line.userData.disposeGeometry = true;
  line.userData.disposeMaterial = true;
  return line;
}

function createScreenSpaceLineSegmentsFromGeometry(runtime, geometry, options) {
  const positions = getLineSegmentPositions(geometry);
  if (!positions) {
    return null;
  }
  return createScreenSpaceLineSegments(runtime, positions, options);
}

function disposeOverlayChild(runtime, child) {
  if (!child) {
    return;
  }
  if (typeof child.userData?.beforeDispose === "function") {
    child.userData.beforeDispose(child);
    delete child.userData.beforeDispose;
  }
  const materials = Array.isArray(child.material) ? child.material : [child.material];
  if (child.userData?.disposeGeometry !== false) {
    child.geometry?.dispose?.();
  }
  if (child.userData?.disposeMaterial !== false) {
    for (const material of materials) {
      material?.dispose?.();
    }
  }
}

function clearOverlayGroup(runtime, group) {
  while (group?.children?.length) {
    const child = group.children[group.children.length - 1];
    if (!child) {
      continue;
    }
    group.remove(child);
    disposeOverlayChild(runtime, child);
  }
  if (group) {
    group.visible = false;
  }
}

function createDisplayEdgeObject(runtime, geometry, viewerTheme, edgeSettings, partId) {
  const line = createScreenSpaceLineSegmentsFromGeometry(runtime, geometry, {
    color: edgeSettings?.color || viewerTheme?.edge || BASE_VIEWER_THEME.edge,
    opacity: Number.isFinite(Number(edgeSettings?.opacity))
      ? clamp(Number(edgeSettings.opacity), 0, 1)
      : (viewerTheme?.edgeOpacity ?? BASE_VIEWER_THEME.edgeOpacity ?? CAD_EDGE_OPACITY),
    lineWidth: getEdgeThickness(edgeSettings, viewerTheme),
    renderOrder: 3,
    depthTest: true,
    depthWrite: false
  });
  if (!line) {
    return {
      edgeMesh: null,
      edgeMaterial: null
    };
  }
  line.userData.partId = partId;
  return {
    edgeMesh: line,
    edgeMaterial: line.material
  };
}

function applyGeometryNormals(THREE, geometry, normals, recomputeNormals) {
  const hasNormals = isNumericArray(normals, 3);
  if (!recomputeNormals && hasNormals) {
    geometry.setAttribute("normal", new THREE.BufferAttribute(new Float32Array(normals), 3));
    return;
  }
  geometry.computeVertexNormals();
}

function toNumber(value, fallback = 0) {
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function buildPartGeometry(THREE, meshData, part, recomputeNormals, materialSettings = {}) {
  const vertexOffset = toNumber(part?.vertexOffset, 0);
  const vertexCount = toNumber(part?.vertexCount, 0);
  const triangleOffset = toNumber(part?.triangleOffset, 0);
  const triangleCount = toNumber(part?.triangleCount, 0);
  if (vertexCount <= 0 || triangleCount <= 0) {
    return null;
  }

  const positionStart = vertexOffset * 3;
  const positionEnd = positionStart + vertexCount * 3;
  const localVertices = meshData.vertices.slice(positionStart, positionEnd);
  const localColors = partUsesDisplayVertexColors(meshData, part)
    ? shapeSourceColorBuffer(THREE, meshData.colors.slice(positionStart, positionEnd), materialSettings)
    : null;
  const localNormals = isNumericArray(meshData.normals, 3) ? meshData.normals.slice(positionStart, positionEnd) : null;
  const rawIndices = meshData.indices.slice(triangleOffset * 3, triangleOffset * 3 + triangleCount * 3);
  const localIndices = rawIndices.map((index) => index - vertexOffset);
  if (!localIndices.length) {
    return null;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(localVertices), 3));
  geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(localIndices), 1));
  if (localColors && localColors.length === localVertices.length) {
    geometry.setAttribute("color", new THREE.BufferAttribute(new Float32Array(localColors), 3));
  }
  applyGeometryNormals(THREE, geometry, localNormals, recomputeNormals);
  geometry.computeBoundingSphere();
  return geometry;
}

function buildDisplayEdgeGeometry(THREE, sourceGeometry) {
  const edgeGeometry = new THREE.EdgesGeometry(sourceGeometry, CAD_EDGE_THRESHOLD_DEG);
  const positions = edgeGeometry.getAttribute("position");
  if (positions?.count) {
    return edgeGeometry;
  }
  edgeGeometry.dispose();
  return emptyLineGeometry(THREE);
}

function buildEdgeGeometryFromIndices(THREE, vertices, edgeIndices) {
  if (!isNumericArray(vertices, 3) || !isNumericArray(edgeIndices, 2)) {
    return null;
  }
  const vertexCount = Math.floor(vertices.length / 3);
  const segmentCount = Math.floor(edgeIndices.length / 2);
  if (segmentCount <= 0) {
    return null;
  }
  const linePositions = new Float32Array(segmentCount * 6);
  let writeOffset = 0;
  for (let index = 0; index + 1 < edgeIndices.length; index += 2) {
    const a = Number(edgeIndices[index]);
    const b = Number(edgeIndices[index + 1]);
    if (!Number.isInteger(a) || !Number.isInteger(b) || a < 0 || b < 0 || a >= vertexCount || b >= vertexCount) {
      continue;
    }
    const aOffset = a * 3;
    const bOffset = b * 3;
    linePositions[writeOffset] = Number(vertices[aOffset]);
    linePositions[writeOffset + 1] = Number(vertices[aOffset + 1]);
    linePositions[writeOffset + 2] = Number(vertices[aOffset + 2]);
    linePositions[writeOffset + 3] = Number(vertices[bOffset]);
    linePositions[writeOffset + 4] = Number(vertices[bOffset + 1]);
    linePositions[writeOffset + 5] = Number(vertices[bOffset + 2]);
    writeOffset += 6;
  }
  if (!writeOffset) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  const packedPositions = writeOffset === linePositions.length ? linePositions : linePositions.subarray(0, writeOffset);
  geometry.setAttribute("position", new THREE.BufferAttribute(packedPositions, 3));
  return geometry;
}

function buildPartEdgeGeometry(THREE, meshData, part, sourceGeometry) {
  const edgeIndexOffset = toNumber(part?.edgeIndexOffset, 0);
  const edgeIndexCount = toNumber(part?.edgeIndexCount, 0);
  const hasExplicitPartEdges = edgeIndexCount >= 2 && isNumericArray(meshData?.edge_indices, 2);
  if (hasExplicitPartEdges) {
    const partEdgeIndices = typeof meshData.edge_indices.subarray === "function"
      ? meshData.edge_indices.subarray(edgeIndexOffset, edgeIndexOffset + edgeIndexCount)
      : meshData.edge_indices.slice(edgeIndexOffset, edgeIndexOffset + edgeIndexCount);
    const explicitGeometry = buildEdgeGeometryFromIndices(THREE, meshData.vertices, partEdgeIndices);
    if (explicitGeometry) {
      return explicitGeometry;
    }
  }
  return buildDisplayEdgeGeometry(THREE, sourceGeometry);
}

function applyPartTransform(THREE, object3d, transform) {
  if (!object3d) {
    return;
  }
  if (!Array.isArray(transform) || transform.length !== 16) {
    object3d.matrixAutoUpdate = true;
    object3d.position.set(0, 0, 0);
    object3d.rotation.set(0, 0, 0);
    object3d.scale.set(1, 1, 1);
    object3d.updateMatrix();
    return;
  }
  object3d.matrixAutoUpdate = false;
  const matrix = object3d.matrix instanceof THREE.Matrix4 ? object3d.matrix : new THREE.Matrix4();
  matrix.set(
    Number(transform[0]) || 0,
    Number(transform[1]) || 0,
    Number(transform[2]) || 0,
    Number(transform[3]) || 0,
    Number(transform[4]) || 0,
    Number(transform[5]) || 0,
    Number(transform[6]) || 0,
    Number(transform[7]) || 0,
    Number(transform[8]) || 0,
    Number(transform[9]) || 0,
    Number(transform[10]) || 0,
    Number(transform[11]) || 0,
    Number(transform[12]) || 0,
    Number(transform[13]) || 0,
    Number(transform[14]) || 0,
    Number(transform[15]) || 0
  );
  object3d.matrix = matrix;
  object3d.matrixWorldNeedsUpdate = true;
}

function buildPartTransformMatrix(THREE, transform) {
  const matrix = new THREE.Matrix4();
  if (!Array.isArray(transform) || transform.length !== 16) {
    matrix.identity();
    return matrix;
  }
  matrix.set(
    Number(transform[0]) || 0,
    Number(transform[1]) || 0,
    Number(transform[2]) || 0,
    Number(transform[3]) || 0,
    Number(transform[4]) || 0,
    Number(transform[5]) || 0,
    Number(transform[6]) || 0,
    Number(transform[7]) || 0,
    Number(transform[8]) || 0,
    Number(transform[9]) || 0,
    Number(transform[10]) || 0,
    Number(transform[11]) || 0,
    Number(transform[12]) || 0,
    Number(transform[13]) || 0,
    Number(transform[14]) || 0,
    Number(transform[15]) || 0
  );
  return matrix;
}

function applyObjectMatrix(THREE, object3d, matrix) {
  if (!object3d || !(matrix instanceof THREE.Matrix4)) {
    return;
  }
  object3d.matrixAutoUpdate = false;
  const targetMatrix = object3d.matrix instanceof THREE.Matrix4 ? object3d.matrix : new THREE.Matrix4();
  targetMatrix.copy(matrix);
  object3d.matrix = targetMatrix;
  object3d.matrixWorldNeedsUpdate = true;
}

function buildDisplayRecordIntroMatrix(THREE, record, modelRadius = 1) {
  const partCenter = record?.partCenter instanceof THREE.Vector3
    ? record.partCenter.clone()
    : null;
  if (!partCenter) {
    return null;
  }

  const introProgress = clamp(Number(record?.introProgress), 0, 1);
  if (introProgress >= 0.999) {
    return null;
  }

  const reveal = easeOutCubic(introProgress);
  const scale = mix(URDF_PART_INTRO_INITIAL_SCALE, 1, easeOutBack(introProgress));
  const partRadius = Math.max(readBoundsRadius(THREE, record?.partBounds), modelRadius * 0.04, 0.012);
  const travelDistance = clamp(partRadius * 0.45, URDF_PART_INTRO_MIN_TRAVEL, Math.max(modelRadius * 0.08, 0.05));
  const driftDirection = new THREE.Vector3(partCenter.x, (partCenter.y * 0.4) + (modelRadius * 0.1) + 0.08, partCenter.z);
  if (driftDirection.lengthSq() < 1e-6) {
    driftDirection.set(0.35, 1, 0.25);
  }
  driftDirection.normalize();

  const translation = driftDirection.multiplyScalar(travelDistance * ((1 - reveal) ** 2));
  const rotationAxis = new THREE.Vector3(-driftDirection.z, 0, driftDirection.x);
  if (rotationAxis.lengthSq() < 1e-6) {
    rotationAxis.set(0.2, 0, 1);
  }
  rotationAxis.normalize();
  const rotationAngle = URDF_PART_INTRO_MAX_TILT_RAD * ((1 - reveal) ** 2);

  const translateToCenter = new THREE.Matrix4().makeTranslation(partCenter.x, partCenter.y, partCenter.z);
  const translateFromCenter = new THREE.Matrix4().makeTranslation(-partCenter.x, -partCenter.y, -partCenter.z);
  const offsetMatrix = new THREE.Matrix4().makeTranslation(translation.x, translation.y, translation.z);
  const rotationScaleMatrix = new THREE.Matrix4().compose(
    new THREE.Vector3(0, 0, 0),
    new THREE.Quaternion().setFromAxisAngle(rotationAxis, rotationAngle),
    new THREE.Vector3(scale, scale, scale)
  );

  return offsetMatrix.multiply(translateToCenter).multiply(rotationScaleMatrix).multiply(translateFromCenter);
}

function applyDisplayRecordTransform(THREE, record, modelRadius = 1) {
  if (!record) {
    return;
  }

  const baseMatrix = buildPartTransformMatrix(THREE, record.baseTransform);
  const introMatrix = buildDisplayRecordIntroMatrix(THREE, record, modelRadius);
  const combinedMatrix = introMatrix ? introMatrix.multiply(baseMatrix) : baseMatrix;

  applyObjectMatrix(THREE, record.mesh, combinedMatrix);
  applyObjectMatrix(THREE, record.edges, combinedMatrix);
}

function applyRuntimeModelBounds(THREE, runtime, bounds, sceneScaleMode) {
  const boundsMin = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const boundsMax = Array.isArray(bounds?.max) ? bounds.max : [0, 0, 0];
  const radius = clampSceneModelRadius(
    new THREE.Vector3(
      toNumber(boundsMax[0]) - toNumber(boundsMin[0]),
      toNumber(boundsMax[1]) - toNumber(boundsMin[1]),
      toNumber(boundsMax[2]) - toNumber(boundsMin[2])
    ).length() / 2,
    sceneScaleMode
  );
  runtime.modelBounds = {
    min: boundsMin,
    max: boundsMax
  };
  runtime.modelRadius = radius;
  if (runtime.keyLight?.shadow?.camera) {
    const normalizedScaleMode = normalizeSceneScaleMode(sceneScaleMode);
    const isUrdfScale = normalizedScaleMode === VIEWER_SCENE_SCALE.URDF;
    const shadowScopeRadius = Math.max(radius, getLightingScopeRadius(normalizedScaleMode));
    const shadowExtent = Math.max(shadowScopeRadius * 2.8, isUrdfScale ? 0.55 : 60);
    const keyLightDistance = typeof runtime.keyLight.position?.length === "function"
      ? runtime.keyLight.position.length()
      : 0;
    const shadowFar = Math.max(
      shadowScopeRadius * 8,
      isUrdfScale ? keyLightDistance + shadowScopeRadius * 6 + 1 : 320
    );
    runtime.keyLight.shadow.mapSize.set(DEFAULT_SHADOW_MAP_SIZE, DEFAULT_SHADOW_MAP_SIZE);
    runtime.keyLight.shadow.bias = -0.00025;
    runtime.keyLight.shadow.normalBias = isUrdfScale ? 0.00045 : 0.012;
    runtime.keyLight.shadow.radius = isUrdfScale ? 20 : 14;
    runtime.keyLight.shadow.camera.left = -shadowExtent;
    runtime.keyLight.shadow.camera.right = shadowExtent;
    runtime.keyLight.shadow.camera.top = shadowExtent;
    runtime.keyLight.shadow.camera.bottom = -shadowExtent;
    runtime.keyLight.shadow.camera.near = 0.1;
    runtime.keyLight.shadow.camera.far = shadowFar;
    runtime.keyLight.shadow.camera.updateProjectionMatrix?.();
  }
  return {
    boundsMin,
    boundsMax,
    radius
  };
}

function applyPartVisualState(THREE, records, {
  viewerTheme,
  edgeSettings,
  hiddenPartIds,
  hoveredPartId,
  focusedPartId,
  selectedPartIds,
  showEdges
}) {
  const hidden = new Set(Array.isArray(hiddenPartIds) ? hiddenPartIds : []);
  const selected = new Set(Array.isArray(selectedPartIds) ? selectedPartIds : []);
  const hovered = new Set(
    (Array.isArray(hoveredPartId) ? hoveredPartId : [hoveredPartId])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const baseEdgeColor = edgeSettings?.color || viewerTheme?.edge || BASE_VIEWER_THEME.edge;
  const defaultSurfaceOpacity = Number.isFinite(Number(viewerTheme?.surfaceOpacity))
    ? Number(viewerTheme.surfaceOpacity)
    : 1;
  const focusIds = new Set(
    (Array.isArray(focusedPartId) ? focusedPartId : [focusedPartId])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const hasFocus = focusIds.size > 0;
  const baseEdgeOpacity = Number.isFinite(Number(edgeSettings?.opacity))
    ? clamp(Number(edgeSettings.opacity), 0, 1)
    : (viewerTheme?.edgeOpacity ?? BASE_VIEWER_THEME.edgeOpacity ?? CAD_EDGE_OPACITY);
  const dimmedEdgeOpacity = hasFocus
    ? Math.max(Math.min(baseEdgeOpacity * 0.28, 0.12), 0.04)
    : baseEdgeOpacity;
  const {
    hoveredSurfaceColor,
    hoveredEdgeColor,
    selectedSurfaceColor,
    selectedEdgeColor
  } = getPartHighlightColors(THREE);

  for (const record of Array.isArray(records) ? records : []) {
    const isHidden = hidden.has(record.partId);
    const isSelected = selected.has(record.partId);
    const isHovered = !isHidden && hovered.has(record.partId);
    const isFocused = !isHidden && hasFocus && focusIds.has(record.partId);
    const isDimmed = !isHidden && hasFocus && !isFocused;
    const introOpacity = Number.isFinite(Number(record?.introOpacity))
      ? clamp(Number(record.introOpacity), 0, 1)
      : 1;
    const introVisible = introOpacity > URDF_PART_INTRO_VISIBILITY_EPSILON;

    record.mesh.visible = !isHidden && introVisible;
    if (record.edges) {
      record.edges.visible = showEdges && !isHidden && introVisible;
    }

    const baseSurfaceOpacity = Number.isFinite(Number(record.baseOpacity))
      ? Number(record.baseOpacity)
      : defaultSurfaceOpacity;
    const dimmedSurfaceOpacity = hasFocus
      ? Math.max(Math.min(baseSurfaceOpacity * 0.2, 0.24), 0.1)
      : baseSurfaceOpacity;
    const highlightedSurfaceOpacity = isSelected
      ? clamp(baseSurfaceOpacity + PART_SELECTED_OPACITY_BOOST, 0, 1)
      : isHovered
        ? clamp(baseSurfaceOpacity + PART_HOVER_OPACITY_BOOST, 0, 1)
        : baseSurfaceOpacity;
    const nextSurfaceOpacity = (isDimmed ? dimmedSurfaceOpacity : highlightedSurfaceOpacity) * introOpacity;
    record.material.transparent = isDimmed || introOpacity < 0.999 || nextSurfaceOpacity < 0.999;
    record.material.opacity = nextSurfaceOpacity;

    if (record.baseColor && record.material.color) {
      record.material.color.copy(
        isSelected
          ? selectedSurfaceColor
          : isHovered
            ? hoveredSurfaceColor
            : record.baseColor
      );
    }

    if ("emissive" in record.material && record.material.emissive) {
      record.material.emissive.set(
        isSelected
          ? REFERENCE_SELECTED_COLOR
          : isHovered
            ? REFERENCE_HOVER_COLOR
            : 0x000000
      );
      record.material.emissiveIntensity = isSelected
        ? 0.08
        : isHovered
          ? 0.12
          : 0;
    }

    if (record.edgeMaterial) {
      record.edgeMaterial.color.set(
        isSelected
          ? selectedEdgeColor
          : isHovered
            ? hoveredEdgeColor
            : baseEdgeColor
      );
      record.edgeMaterial.opacity = isSelected
        ? introOpacity
        : isHovered
          ? introOpacity
          : isDimmed
            ? dimmedEdgeOpacity * introOpacity
            : baseEdgeOpacity * introOpacity;
    }
  }
}

function parseTopologyReferenceId(referenceId) {
  const normalizedReferenceId = String(referenceId || "").trim();
  const parts = normalizedReferenceId.split(":");
  if (parts.length >= 3 && (parts[0] === "face" || parts[0] === "edge")) {
    const kind = parts[0];
    const ordinal = Number(parts[parts.length - 1]);
    const partId = parts.slice(1, -1).join(":").trim();
    if (!partId || !Number.isInteger(ordinal) || ordinal <= 0) {
      return null;
    }
    return {
      id: normalizedReferenceId,
      kind,
      partId,
      ordinal
    };
  }
}

function createReferenceEdgeGeometryFromPoints(THREE, points) {
  if (!Array.isArray(points) || points.length < 2) {
    return null;
  }
  const linePositions = [];
  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1];
    const end = points[index];
    if (!Array.isArray(start) || !Array.isArray(end) || start.length < 3 || end.length < 3) {
      continue;
    }
    linePositions.push(
      Number(start[0]),
      Number(start[1]),
      Number(start[2]),
      Number(end[0]),
      Number(end[1]),
      Number(end[2])
    );
  }
  if (!linePositions.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(linePositions), 3));
  return geometry;
}

function createReferenceFaceLoopGeometry(THREE, loops) {
  if (!Array.isArray(loops) || !loops.length) {
    return null;
  }
  const linePositions = [];
  for (const loop of loops) {
    if (!Array.isArray(loop) || loop.length < 2) {
      continue;
    }
    for (let index = 0; index < loop.length; index += 1) {
      const start = loop[index];
      const end = loop[(index + 1) % loop.length];
      if (!Array.isArray(start) || !Array.isArray(end) || start.length < 3 || end.length < 3) {
        continue;
      }
      linePositions.push(
        Number(start[0]),
        Number(start[1]),
        Number(start[2]),
        Number(end[0]),
        Number(end[1]),
        Number(end[2])
      );
    }
  }
  if (!linePositions.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(linePositions), 3));
  return geometry;
}

function createReferenceFaceBoundaryGeometry(THREE, reference) {
  const pickData = reference?.pickData || {};
  const loopsMeta = Array.isArray(pickData?.loopsMeta) ? pickData.loopsMeta : [];
  const boundaryLoops = loopsMeta
    .filter((loopEntry) => Array.isArray(loopEntry?.points) && loopEntry.points.length >= 2)
    .map((loopEntry) => loopEntry.points);
  if (boundaryLoops.length) {
    return createReferenceFaceLoopGeometry(THREE, boundaryLoops);
  }

  const fallbackLoops = Array.isArray(pickData?.loops)
    ? pickData.loops.filter((loop) => Array.isArray(loop) && loop.length >= 2)
    : [];
  return createReferenceFaceLoopGeometry(THREE, fallbackLoops);
}

function selectOuterLoopPoints(pickData = {}) {
  const loopsMeta = Array.isArray(pickData?.loopsMeta) ? pickData.loopsMeta : [];
  const explicitOuter = loopsMeta.find((loop) => loop?.isOuter && Array.isArray(loop?.points) && loop.points.length >= 3);
  if (explicitOuter) {
    return explicitOuter.points;
  }
  const loops = Array.isArray(pickData?.loops) ? pickData.loops : [];
  return loops.find((loop) => Array.isArray(loop) && loop.length >= 3) || null;
}

function isFinitePoint2(point) {
  return Array.isArray(point) && point.length >= 2 && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]));
}

function isFinitePoint3(point) {
  return Array.isArray(point) && point.length >= 3 && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1])) && Number.isFinite(Number(point[2]));
}

function distanceSquared2d(a, b) {
  const dx = Number(a[0]) - Number(b[0]);
  const dy = Number(a[1]) - Number(b[1]);
  return dx * dx + dy * dy;
}

function distanceSquared3d(a, b) {
  const dx = Number(a[0]) - Number(b[0]);
  const dy = Number(a[1]) - Number(b[1]);
  const dz = Number(a[2]) - Number(b[2]);
  return dx * dx + dy * dy + dz * dz;
}

function sanitizeLoopPair(loop3d, loop2d) {
  const count = Math.min(
    Array.isArray(loop3d) ? loop3d.length : 0,
    Array.isArray(loop2d) ? loop2d.length : 0
  );
  const points3d = [];
  const points2d = [];
  for (let index = 0; index < count; index += 1) {
    const point3d = loop3d[index];
    const point2d = loop2d[index];
    if (!isFinitePoint3(point3d) || !isFinitePoint2(point2d)) {
      continue;
    }
    const normalized3d = [Number(point3d[0]), Number(point3d[1]), Number(point3d[2])];
    const normalized2d = [Number(point2d[0]), Number(point2d[1])];
    const previous3d = points3d[points3d.length - 1];
    const previous2d = points2d[points2d.length - 1];
    if (previous3d && previous2d) {
      const duplicate3d = distanceSquared3d(previous3d, normalized3d) <= 1e-10;
      const duplicate2d = distanceSquared2d(previous2d, normalized2d) <= 1e-10;
      if (duplicate3d || duplicate2d) {
        continue;
      }
    }
    points3d.push(normalized3d);
    points2d.push(normalized2d);
  }

  if (points3d.length >= 3 && distanceSquared3d(points3d[0], points3d[points3d.length - 1]) <= 1e-10) {
    points3d.pop();
    points2d.pop();
  }

  if (points3d.length < 3 || points2d.length < 3) {
    return null;
  }
  return { loop3d: points3d, loop2d: points2d };
}

function averagePoint3(points) {
  if (!Array.isArray(points) || !points.length) {
    return [0, 0, 0];
  }
  let x = 0;
  let y = 0;
  let z = 0;
  let count = 0;
  for (const point of points) {
    if (!isFinitePoint3(point)) {
      continue;
    }
    x += Number(point[0]);
    y += Number(point[1]);
    z += Number(point[2]);
    count += 1;
  }
  if (!count) {
    return [0, 0, 0];
  }
  return [x / count, y / count, z / count];
}

function normalizeVector3(vector) {
  const magnitude = length(vector);
  if (magnitude <= 1e-9) {
    return null;
  }
  return [vector[0] / magnitude, vector[1] / magnitude, vector[2] / magnitude];
}

function cross3(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]
  ];
}

function projectLoopsWithFrame(loops, origin, xDir, yDir) {
  return loops.map((loop) => loop.map((point) => {
    const relative = subtract(point, origin);
    return [dot(relative, xDir), dot(relative, yDir)];
  }));
}

function projectFaceLoopsTo2d(loops, surface) {
  if (!Array.isArray(loops) || !loops.length) {
    return null;
  }

  const sanitizedLoops = loops.map((loop) => (Array.isArray(loop) ? loop.filter(isFinitePoint3) : []));
  const hasAnyValidLoop = sanitizedLoops.some((loop) => loop.length >= 3);
  if (!hasAnyValidLoop) {
    return null;
  }

  if (surface?.type === "PLANE" && Array.isArray(surface?.origin) && Array.isArray(surface?.xDir) && Array.isArray(surface?.yDir)) {
    const origin = surface.origin;
    const xDir = surface.xDir;
    const yDir = surface.yDir;
    return projectLoopsWithFrame(sanitizedLoops, origin, xDir, yDir);
  }
  if (
    surface?.type === "CYLINDRICAL_SURFACE" &&
    Array.isArray(surface?.origin) &&
    Array.isArray(surface?.axis) &&
    Array.isArray(surface?.xDir) &&
    Array.isArray(surface?.yDir) &&
    Number(surface?.radius) > 0
  ) {
    const origin = surface.origin;
    const axis = surface.axis;
    const xDir = surface.xDir;
    const yDir = surface.yDir;
    const radius = Number(surface.radius);
    return sanitizedLoops.map((loop) => {
      let previousAngle = null;
      return loop.map((point) => {
        const relative = subtract(point, origin);
        const axial = dot(relative, axis);
        const radial = [
          relative[0] - axis[0] * axial,
          relative[1] - axis[1] * axial,
          relative[2] - axis[2] * axial
        ];
        const rawAngle = Math.atan2(dot(radial, yDir), dot(radial, xDir));
        const angle = previousAngle === null ? rawAngle : normalizeAngleAround(rawAngle, previousAngle);
        previousAngle = angle;
        return [angle * radius, axial];
      });
    });
  }

  const allPoints = sanitizedLoops.flat();
  const origin = isFinitePoint3(surface?.origin) ? surface.origin : averagePoint3(allPoints);
  let normal = normalizeVector3(surface?.normal || []);
  if (!normal) {
    for (let index = 2; index < allPoints.length; index += 1) {
      const a = allPoints[index - 2];
      const b = allPoints[index - 1];
      const c = allPoints[index];
      const ab = subtract(b, a);
      const ac = subtract(c, a);
      normal = normalizeVector3(cross3(ab, ac));
      if (normal) {
        break;
      }
    }
  }
  if (!normal) {
    normal = [0, 0, 1];
  }

  let axis = Math.abs(normal[2]) < 0.9 ? [0, 0, 1] : [0, 1, 0];
  let xDir = normalizeVector3(cross3(axis, normal));
  if (!xDir) {
    axis = [1, 0, 0];
    xDir = normalizeVector3(cross3(axis, normal));
  }
  if (!xDir) {
    return null;
  }
  const yDir = normalizeVector3(cross3(normal, xDir));
  if (!yDir) {
    return null;
  }

  return projectLoopsWithFrame(sanitizedLoops, origin, xDir, yDir);
}

function buildFallbackFaceFanGeometry(THREE, loop3d, centroid = null) {
  if (!Array.isArray(loop3d) || loop3d.length < 3) {
    return null;
  }

  const cleanedLoop = loop3d.filter(isFinitePoint3).map((point) => [Number(point[0]), Number(point[1]), Number(point[2])]);
  if (cleanedLoop.length < 3) {
    return null;
  }

  const center = isFinitePoint3(centroid) ? centroid.map((value) => Number(value)) : averagePoint3(cleanedLoop);
  const fillPositions = [];
  for (let index = 0; index < cleanedLoop.length; index += 1) {
    const a = cleanedLoop[index];
    const b = cleanedLoop[(index + 1) % cleanedLoop.length];
    fillPositions.push(
      center[0], center[1], center[2],
      a[0], a[1], a[2],
      b[0], b[1], b[2]
    );
  }
  if (!fillPositions.length) {
    return null;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(fillPositions), 3));
  return geometry;
}

function createReferenceFaceFillGeometry(THREE, reference) {
  const pickData = reference?.pickData;
  const loops3d = Array.isArray(pickData?.loops) ? pickData.loops : [];
  if (!loops3d.length) {
    return null;
  }

  const projectedLoops = projectFaceLoopsTo2d(loops3d, pickData?.surface || {});
  if (!projectedLoops) {
    return buildFallbackFaceFanGeometry(
      THREE,
      selectOuterLoopPoints(pickData) || loops3d[0],
      pickData?.centroid || null
    );
  }

  const loopEntries = loops3d
    .map((loop3d, index) => {
      const cleaned = sanitizeLoopPair(loop3d, projectedLoops[index] || []);
      if (!cleaned) {
        return null;
      }
      return {
        index,
        ...cleaned
      };
    })
    .filter((entry) => entry && Array.isArray(entry.loop3d) && entry.loop3d.length >= 3 && Array.isArray(entry.loop2d) && entry.loop2d.length >= 3);
  if (!loopEntries.length) {
    return buildFallbackFaceFanGeometry(
      THREE,
      selectOuterLoopPoints(pickData) || loops3d[0],
      pickData?.centroid || null
    );
  }

  const preferredOuterIndex = Number.isInteger(pickData?.outerLoopIndex) ? pickData.outerLoopIndex : 0;
  const outerEntry = loopEntries.find((entry) => entry.index === preferredOuterIndex) || loopEntries[0];
  if (!outerEntry) {
    return null;
  }
  const contourLoop3d = [...outerEntry.loop3d];
  let contour2d = outerEntry.loop2d.map((point) => new THREE.Vector2(Number(point[0]), Number(point[1])));
  if (contour2d.length < 3) {
    return buildFallbackFaceFanGeometry(THREE, contourLoop3d, pickData?.centroid || null);
  }

  let contourClockwise = THREE.ShapeUtils.isClockWise(contour2d);
  if (contourClockwise) {
    contour2d = [...contour2d].reverse();
    contourLoop3d.reverse();
    contourClockwise = false;
  }

  const holeEntries = loopEntries.filter((entry) => entry.index !== outerEntry.index);
  const holeData = [];
  for (const holeEntry of holeEntries) {
    let holeLoop3d = [...holeEntry.loop3d];
    let hole2d = holeEntry.loop2d.map((point) => new THREE.Vector2(Number(point[0]), Number(point[1])));
    if (hole2d.length < 3) {
      continue;
    }
    const holeClockwise = THREE.ShapeUtils.isClockWise(hole2d);
    if (holeClockwise === contourClockwise) {
      hole2d = [...hole2d].reverse();
      holeLoop3d.reverse();
    }
    holeData.push({
      loop2d: hole2d,
      loop3d: holeLoop3d
    });
  }

  const triangulated = THREE.ShapeUtils.triangulateShape(
    contour2d,
    holeData.map((entry) => entry.loop2d)
  );
  if (!Array.isArray(triangulated) || !triangulated.length) {
    return buildFallbackFaceFanGeometry(THREE, contourLoop3d, pickData?.centroid || null);
  }

  const vertexPoints3d = [
    ...contourLoop3d,
    ...holeData.flatMap((entry) => entry.loop3d)
  ];
  if (!vertexPoints3d.length) {
    return null;
  }

  const fillPositions = [];
  for (const triangle of triangulated) {
    if (!Array.isArray(triangle) || triangle.length !== 3) {
      continue;
    }
    for (const vertexIndex of triangle) {
      const point = vertexPoints3d[vertexIndex];
      if (!Array.isArray(point) || point.length < 3) {
        continue;
      }
      fillPositions.push(
        Number(point[0]),
        Number(point[1]),
        Number(point[2])
      );
    }
  }
  if (!fillPositions.length) {
    return null;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(fillPositions), 3));
  return geometry;
}

function buildEdgeGeometry(THREE, meshData, sourceGeometry) {
  if (isNumericArray(meshData?.edge_indices, 2)) {
    const explicitGeometry = buildEdgeGeometryFromIndices(THREE, meshData.vertices, meshData.edge_indices);
    if (explicitGeometry) {
      return explicitGeometry;
    }
  }
  return buildDisplayEdgeGeometry(THREE, sourceGeometry);
}

function buildEdgePickObjects(THREE, group, references) {
  const objects = [];
  for (const reference of Array.isArray(references) ? references : []) {
    const points = reference?.pickData?.points;
    if (!Array.isArray(points) || points.length < 2) {
      continue;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(points.flat()), 3));
    const material = new THREE.LineBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0
    });
    const line = new THREE.Line(geometry, material);
    line.userData.referenceId = String(reference?.id || "");
    line.userData.partId = String(reference?.partId || "");
    line.userData.metric = reference?.pickData?.metric ?? Infinity;
    group.add(line);
    objects.push(line);
  }
  group.updateMatrixWorld(true);
  return objects;
}

function buildFacePickMesh(THREE, selectorRuntime) {
  const proxy = selectorRuntime?.proxy || {};
  if (!(proxy.facePositions instanceof Float32Array) || !(proxy.faceIndices instanceof Uint32Array) || !proxy.faceIndices.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(proxy.facePositions, 3));
  geometry.setIndex(new THREE.BufferAttribute(proxy.faceIndices, 1));
  const material = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    toneMapped: false,
    colorWrite: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData.faceIds = proxy.faceIds || new Uint32Array(0);
  mesh.frustumCulled = false;
  return mesh;
}

function buildEdgePickLines(THREE, selectorRuntime) {
  const proxy = selectorRuntime?.proxy || {};
  if (!(proxy.edgePositions instanceof Float32Array) || !(proxy.edgeIndices instanceof Uint32Array) || !proxy.edgeIndices.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(proxy.edgePositions, 3));
  geometry.setIndex(new THREE.BufferAttribute(proxy.edgeIndices, 1));
  const material = new THREE.LineBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    toneMapped: false,
  });
  const lines = new THREE.LineSegments(geometry, material);
  lines.userData.edgeIds = proxy.edgeIds || new Uint32Array(0);
  lines.frustumCulled = false;
  return lines;
}

function buildVertexPickPoints(THREE, selectorRuntime) {
  const proxy = selectorRuntime?.proxy || {};
  if (!(proxy.vertexPositions instanceof Float32Array) || !proxy.vertexPositions.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(proxy.vertexPositions, 3));
  const material = new THREE.PointsMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0,
    size: 1.5,
    sizeAttenuation: false,
    depthWrite: false,
    toneMapped: false,
  });
  const points = new THREE.Points(geometry, material);
  points.userData.vertexIds = proxy.vertexIds || new Uint32Array(0);
  points.frustumCulled = false;
  return points;
}

function faceFillOffset(runtime, reference) {
  const normal = Array.isArray(reference?.pickData?.normal) ? reference.pickData.normal : null;
  if (!runtime?.camera || !runtime?.modelGroup || !normal || normal.length < 3) {
    return [0, 0, 0];
  }
  const normalLength = Math.hypot(normal[0], normal[1], normal[2]);
  if (normalLength <= 1e-9) {
    return [0, 0, 0];
  }
  const normalizedNormal = [
    normal[0] / normalLength,
    normal[1] / normalLength,
    normal[2] / normalLength
  ];
  const center = Array.isArray(reference?.pickData?.center) ? reference.pickData.center : [0, 0, 0];
  const modelOffset = runtime.modelGroup.position;
  const worldCenter = [
    Number(center[0] || 0) + Number(modelOffset?.x || 0),
    Number(center[1] || 0) + Number(modelOffset?.y || 0),
    Number(center[2] || 0) + Number(modelOffset?.z || 0)
  ];
  const toCamera = [
    runtime.camera.position.x - worldCenter[0],
    runtime.camera.position.y - worldCenter[1],
    runtime.camera.position.z - worldCenter[2]
  ];
  const facingSign =
    ((normalizedNormal[0] * toCamera[0]) + (normalizedNormal[1] * toCamera[1]) + (normalizedNormal[2] * toCamera[2])) >= 0
      ? 1
      : -1;
  const magnitude = Math.max(Number(runtime.modelRadius || 1) * 0.00075, 0.015);
  return [
    normalizedNormal[0] * facingSign * magnitude,
    normalizedNormal[1] * facingSign * magnitude,
    normalizedNormal[2] * facingSign * magnitude
  ];
}

function buildFaceFillGeometryFromProxy(runtime, THREE, selectorRuntime, reference) {
  const proxy = selectorRuntime?.proxy || {};
  const triangleStart = Number(reference?.pickData?.triangleStart || 0);
  const triangleCount = Number(reference?.pickData?.triangleCount || 0);
  if (!(proxy.facePositions instanceof Float32Array) || !(proxy.faceIndices instanceof Uint32Array) || triangleCount <= 0) {
    return null;
  }
  const indexSlice = proxy.faceIndices.slice(triangleStart * 3, (triangleStart + triangleCount) * 3);
  if (!indexSlice.length) {
    return null;
  }
  const offset = faceFillOffset(runtime, reference);
  const positions = new Float32Array(indexSlice.length * 3);
  let writeOffset = 0;
  for (const vertexIndex of indexSlice) {
    const sourceIndex = Number(vertexIndex) * 3;
    positions[writeOffset] = proxy.facePositions[sourceIndex] + offset[0];
    positions[writeOffset + 1] = proxy.facePositions[sourceIndex + 1] + offset[1];
    positions[writeOffset + 2] = proxy.facePositions[sourceIndex + 2] + offset[2];
    writeOffset += 3;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  return geometry;
}

function buildEdgeLinePositionsFromProxy(selectorRuntime, reference) {
  const proxy = selectorRuntime?.proxy || {};
  const segmentStart = Number(reference?.pickData?.segmentStart || 0);
  const segmentCount = Number(reference?.pickData?.segmentCount || 0);
  if (!(proxy.edgePositions instanceof Float32Array) || !(proxy.edgeIndices instanceof Uint32Array) || segmentCount <= 0) {
    return null;
  }
  const indexSlice = proxy.edgeIndices.slice(segmentStart * 2, (segmentStart + segmentCount) * 2);
  if (!indexSlice.length) {
    return null;
  }
  const linePositions = new Float32Array(segmentCount * 6);
  let writeOffset = 0;
  for (let index = 0; index + 1 < indexSlice.length; index += 2) {
    const startIndex = indexSlice[index] * 3;
    const endIndex = indexSlice[index + 1] * 3;
    linePositions[writeOffset] = proxy.edgePositions[startIndex];
    linePositions[writeOffset + 1] = proxy.edgePositions[startIndex + 1];
    linePositions[writeOffset + 2] = proxy.edgePositions[startIndex + 2];
    linePositions[writeOffset + 3] = proxy.edgePositions[endIndex];
    linePositions[writeOffset + 4] = proxy.edgePositions[endIndex + 1];
    linePositions[writeOffset + 5] = proxy.edgePositions[endIndex + 2];
    writeOffset += 6;
  }
  return writeOffset === linePositions.length ? linePositions : linePositions.subarray(0, writeOffset);
}

function buildAdjacentEdgeLinePositions(selectorRuntime, reference) {
  const selectors = Array.isArray(reference?.pickData?.adjacentSelectors) ? reference.pickData.adjacentSelectors : [];
  if (!selectors.length) {
    return null;
  }
  const positions = [];
  for (const selector of selectors) {
    const edgeReference =
      selectorRuntime?.referenceByDisplaySelector?.get?.(selector) ||
      selectorRuntime?.referenceByNormalizedSelector?.get?.(selector) ||
      null;
    const edgePositions = buildEdgeLinePositionsFromProxy(selectorRuntime, edgeReference);
    if (!edgePositions?.length) {
      continue;
    }
    positions.push(...edgePositions);
  }
  return positions.length ? positions : null;
}

function buildFaceBoundaryLinePositions(selectorRuntime, reference) {
  return buildAdjacentEdgeLinePositions(selectorRuntime, reference);
}

function buildVertexMarkerMesh(runtime, THREE, reference, {
  color,
  opacity,
  renderOrder = 27
} = {}) {
  const center = Array.isArray(reference?.pickData?.center) ? reference.pickData.center : null;
  if (!center || center.length < 3) {
    return null;
  }
  const radius = Math.max(Number(runtime?.modelRadius || 1) * 0.0045, 0.2);
  const geometry = new THREE.SphereGeometry(radius, 16, 16);
  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity,
    depthTest: true,
    depthWrite: false,
    toneMapped: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(center[0], center[1], center[2]);
  mesh.renderOrder = renderOrder;
  return mesh;
}

function subtract(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function dot(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function length(vector) {
  return Math.hypot(vector[0], vector[1], vector[2]);
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
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

function pointInPolygon2d(point, polygon) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index, index += 1) {
    const a = polygon[index];
    const b = polygon[previous];
    if (distancePointToSegment2d(point, a, b) <= 1e-4) {
      return true;
    }
    const intersects =
      (a[1] > point[1]) !== (b[1] > point[1]) &&
      point[0] < ((b[0] - a[0]) * (point[1] - a[1])) / (b[1] - a[1] || 1e-9) + a[0];
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}

async function canvasToBlob(canvas) {
  return new Promise((resolve, reject) => {
    if (!canvas) {
      reject(new Error("Screenshot capture failed"));
      return;
    }
    if (typeof canvas.toBlob === "function") {
      canvas.toBlob((value) => {
        if (value) {
          resolve(value);
          return;
        }
        reject(new Error("Screenshot capture failed"));
      }, "image/png");
      return;
    }

    try {
      resolve(dataUrlToBlob(canvas.toDataURL("image/png")));
    } catch (captureError) {
      reject(captureError);
    }
  });
}

function flipPixelsVertically(pixels, width, height) {
  const rowSize = width * 4;
  const flipped = new Uint8ClampedArray(pixels.length);
  for (let row = 0; row < height; row += 1) {
    const sourceStart = (height - row - 1) * rowSize;
    const targetStart = row * rowSize;
    flipped.set(pixels.subarray(sourceStart, sourceStart + rowSize), targetStart);
  }
  return flipped;
}

// Capture through an offscreen render target so normal interaction can keep
// `preserveDrawingBuffer` disabled.
async function buildCompositeScreenshotBlob(runtime, overlayCanvas) {
  const renderer = runtime?.renderer;
  const scene = runtime?.scene;
  const camera = runtime?.camera;
  const THREE = runtime?.THREE;
  const width = renderer?.domElement?.width || 0;
  const height = renderer?.domElement?.height || 0;
  if (!renderer || !scene || !camera || !THREE || width <= 0 || height <= 0) {
    throw new Error("Screenshot capture failed");
  }

  const renderTarget = new THREE.WebGLRenderTarget(width, height, {
    depthBuffer: true,
    stencilBuffer: false
  });
  renderTarget.texture.colorSpace = renderer.outputColorSpace;
  if ("samples" in renderTarget && renderer.capabilities?.isWebGL2) {
    renderTarget.samples = 4;
  }

  const previousRenderTarget = renderer.getRenderTarget();
  const previousXrEnabled = renderer.xr?.enabled === true;
  const pixelBuffer = new Uint8Array(width * height * 4);
  try {
    if (renderer.xr) {
      renderer.xr.enabled = false;
    }
    renderer.setRenderTarget(renderTarget);
    renderer.render(scene, camera);
    renderer.readRenderTargetPixels(renderTarget, 0, 0, width, height, pixelBuffer);
  } finally {
    renderer.setRenderTarget(previousRenderTarget);
    if (renderer.xr) {
      renderer.xr.enabled = previousXrEnabled;
    }
    renderTarget.dispose();
  }

  const exportCanvas = document.createElement("canvas");
  exportCanvas.width = width;
  exportCanvas.height = height;
  const context = exportCanvas.getContext("2d");
  if (!context) {
    throw new Error("Screenshot capture failed");
  }

  const imageData = new ImageData(flipPixelsVertically(pixelBuffer, width, height), width, height);
  context.putImageData(imageData, 0, 0);
  if (overlayCanvas) {
    context.drawImage(overlayCanvas, 0, 0, width, height);
  }
  return canvasToBlob(exportCanvas);
}

function buildDrawingPoint(event, canvas) {
  const rect = canvas.getBoundingClientRect();
  const width = rect.width || 1;
  const height = rect.height || 1;
  return {
    x: clamp((event.clientX - rect.left) / width, 0, 1),
    y: clamp((event.clientY - rect.top) / height, 0, 1)
  };
}

function drawingPointToPixels(point, width, height) {
  return [point.x * width, point.y * height];
}

function pointsEqual2d(a, b, epsilon = 1e-4) {
  return Math.abs(a[0] - b[0]) <= epsilon && Math.abs(a[1] - b[1]) <= epsilon;
}

function strokeLengthInPixels(stroke, width, height) {
  const points = Array.isArray(stroke?.points) ? stroke.points : [];
  if (points.length < 2) {
    return 0;
  }
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const previous = drawingPointToPixels(points[index - 1], width, height);
    const current = drawingPointToPixels(points[index], width, height);
    total += Math.hypot(current[0] - previous[0], current[1] - previous[1]);
  }
  return total;
}

function getDrawingStrokePoints(stroke) {
  return Array.isArray(stroke?.points)
    ? stroke.points.filter((point) => point && Number.isFinite(point.x) && Number.isFinite(point.y))
    : [];
}

function getFillStrokePoints(stroke) {
  return Array.isArray(stroke?.fillPoints)
    ? stroke.fillPoints.filter((point) => point && Number.isFinite(point.x) && Number.isFinite(point.y))
    : [];
}

function isFillStroke(stroke) {
  return stroke?.tool === DRAWING_TOOL.FILL;
}

function isSurfaceLineStroke(stroke) {
  return stroke?.tool === DRAWING_TOOL.SURFACE_LINE && !!stroke?.surfaceLine;
}

function isClosedDrawingStroke(stroke) {
  return stroke?.tool === DRAWING_TOOL.RECTANGLE || stroke?.tool === DRAWING_TOOL.CIRCLE;
}

function isFillBoundaryStroke(stroke) {
  return !!stroke && stroke.tool !== DRAWING_TOOL.ERASE && stroke.tool !== DRAWING_TOOL.FILL && stroke.tool !== DRAWING_TOOL.SURFACE_LINE;
}

function drawingToolNeedsTwoPoints(tool) {
  return (
    tool === DRAWING_TOOL.LINE ||
    tool === DRAWING_TOOL.SURFACE_LINE ||
    tool === DRAWING_TOOL.ARROW ||
    tool === DRAWING_TOOL.DOUBLE_ARROW ||
    tool === DRAWING_TOOL.RECTANGLE ||
    tool === DRAWING_TOOL.CIRCLE
  );
}

function parseFaceToken(copyText) {
  return String(parseCadRefToken(copyText)?.token || "").trim();
}

function clonePoint3(point) {
  return Array.isArray(point) && point.length >= 3
    ? [Number(point[0]), Number(point[1]), Number(point[2])]
    : null;
}

function clonePoint2(point) {
  return Array.isArray(point) && point.length >= 2
    ? [Number(point[0]), Number(point[1])]
    : null;
}

function projectPointToSurfaceUv(surface, point, angleCenter = null) {
  if (!surface || !Array.isArray(point) || point.length < 3) {
    return null;
  }
  if (
    surface.type === "PLANE" &&
    Array.isArray(surface.origin) &&
    Array.isArray(surface.xDir) &&
    Array.isArray(surface.yDir)
  ) {
    return projectPointToPlane(point, surface);
  }
  if (
    surface.type === "CYLINDRICAL_SURFACE" &&
    Array.isArray(surface.origin) &&
    Array.isArray(surface.axis) &&
    Array.isArray(surface.xDir) &&
    Array.isArray(surface.yDir) &&
    Number(surface.radius) > 0
  ) {
    return projectPointToCylinder(point, surface, angleCenter);
  }
  return null;
}

function pointOnSurfaceFromUv(surface, uv) {
  if (!surface || !Array.isArray(uv) || uv.length < 2) {
    return null;
  }
  if (
    surface.type === "PLANE" &&
    Array.isArray(surface.origin) &&
    Array.isArray(surface.xDir) &&
    Array.isArray(surface.yDir)
  ) {
    return [
      surface.origin[0] + surface.xDir[0] * uv[0] + surface.yDir[0] * uv[1],
      surface.origin[1] + surface.xDir[1] * uv[0] + surface.yDir[1] * uv[1],
      surface.origin[2] + surface.xDir[2] * uv[0] + surface.yDir[2] * uv[1]
    ];
  }
  if (
    surface.type === "CYLINDRICAL_SURFACE" &&
    Array.isArray(surface.origin) &&
    Array.isArray(surface.axis) &&
    Array.isArray(surface.xDir) &&
    Array.isArray(surface.yDir) &&
    Number(surface.radius) > 0
  ) {
    const radius = Number(surface.radius);
    const theta = uv[0] / radius;
    const cosTheta = Math.cos(theta);
    const sinTheta = Math.sin(theta);
    return [
      surface.origin[0] + surface.axis[0] * uv[1] + radius * (surface.xDir[0] * cosTheta + surface.yDir[0] * sinTheta),
      surface.origin[1] + surface.axis[1] * uv[1] + radius * (surface.xDir[1] * cosTheta + surface.yDir[1] * sinTheta),
      surface.origin[2] + surface.axis[2] * uv[1] + radius * (surface.xDir[2] * cosTheta + surface.yDir[2] * sinTheta)
    ];
  }
  return null;
}

function surfaceNormalAtUv(surface, uv) {
  if (!surface || !Array.isArray(uv) || uv.length < 2) {
    return null;
  }
  if (surface.type === "PLANE") {
    return normalizeVector3(surface.normal || []);
  }
  if (
    surface.type === "CYLINDRICAL_SURFACE" &&
    Array.isArray(surface.xDir) &&
    Array.isArray(surface.yDir) &&
    Number(surface.radius) > 0
  ) {
    const theta = uv[0] / Number(surface.radius);
    return normalizeVector3([
      surface.xDir[0] * Math.cos(theta) + surface.yDir[0] * Math.sin(theta),
      surface.xDir[1] * Math.cos(theta) + surface.yDir[1] * Math.sin(theta),
      surface.xDir[2] * Math.cos(theta) + surface.yDir[2] * Math.sin(theta)
    ]);
  }
  return null;
}

function buildSurfaceLinePositions(reference, surfaceLine, { segments = 48, offset = 0.04 } = {}) {
  const surface = reference?.pickData?.surface || {};
  const startPoint = clonePoint3(surfaceLine?.startPoint);
  const endPoint = clonePoint3(surfaceLine?.endPoint);
  const startUv = clonePoint2(surfaceLine?.startUv);
  const endUv = clonePoint2(surfaceLine?.endUv);

  if (surface.type === "PLANE" && startPoint && endPoint) {
    const normal = normalizeVector3(reference?.pickData?.normal || surface.normal || []);
    const project = (point) => normal ? [
      point[0] + normal[0] * offset,
      point[1] + normal[1] * offset,
      point[2] + normal[2] * offset
    ] : point;
    const start = project(startPoint);
    const end = project(endPoint);
    return [
      start[0], start[1], start[2],
      end[0], end[1], end[2]
    ];
  }

  if (surface.type === "CYLINDRICAL_SURFACE" && startUv && endUv) {
    const linePositions = [];
    const count = Math.max(4, Math.round(Number(segments) || 48));
    let previousPoint = null;
    for (let index = 0; index <= count; index += 1) {
      const t = index / count;
      const uv = [
        startUv[0] + (endUv[0] - startUv[0]) * t,
        startUv[1] + (endUv[1] - startUv[1]) * t
      ];
      const point = pointOnSurfaceFromUv(surface, uv);
      if (!point) {
        continue;
      }
      const normal = surfaceNormalAtUv(surface, uv);
      const offsetPoint = normal ? [
        point[0] + normal[0] * offset,
        point[1] + normal[1] * offset,
        point[2] + normal[2] * offset
      ] : point;
      if (previousPoint) {
        linePositions.push(
          previousPoint[0], previousPoint[1], previousPoint[2],
          offsetPoint[0], offsetPoint[1], offsetPoint[2]
        );
      }
      previousPoint = offsetPoint;
    }
    return linePositions;
  }

  if (startPoint && endPoint) {
    return [
      startPoint[0], startPoint[1], startPoint[2],
      endPoint[0], endPoint[1], endPoint[2]
    ];
  }

  return [];
}

function buildRectanglePixelCorners(start, end) {
  return [
    [start[0], start[1]],
    [end[0], start[1]],
    [end[0], end[1]],
    [start[0], end[1]]
  ];
}

function buildCirclePixelPolygon(center, edge, segmentCount = 56) {
  const radius = Math.hypot(edge[0] - center[0], edge[1] - center[1]);
  if (radius < 1e-4) {
    return [center];
  }
  const segments = Math.max(segmentCount, 12);
  const points = [];
  for (let index = 0; index <= segments; index += 1) {
    const angle = (index / segments) * Math.PI * 2;
    points.push([
      center[0] + Math.cos(angle) * radius,
      center[1] + Math.sin(angle) * radius
    ]);
  }
  return points;
}

function getDrawingBoundaryPixelPoints(stroke, width, height) {
  const pixelPoints = getDrawingStrokePoints(stroke).map((point) => drawingPointToPixels(point, width, height));
  if (pixelPoints.length < 2) {
    return pixelPoints;
  }
  if (stroke.tool === DRAWING_TOOL.RECTANGLE) {
    const corners = buildRectanglePixelCorners(pixelPoints[0], pixelPoints[pixelPoints.length - 1]);
    return [...corners, corners[0]];
  }
  if (stroke.tool === DRAWING_TOOL.CIRCLE) {
    return buildCirclePixelPolygon(pixelPoints[0], pixelPoints[pixelPoints.length - 1]);
  }
  return pixelPoints;
}

function drawArrowHead(context, start, end, lineWidth) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const lengthPx = Math.hypot(dx, dy);
  if (lengthPx < 1) {
    return;
  }
  const ux = dx / lengthPx;
  const uy = dy / lengthPx;
  const angle = Math.PI / 7;
  const headLength = Math.max(DRAWING_ARROW_HEAD_LENGTH, lineWidth * 3.25);
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const left = [
    end[0] - headLength * (ux * cos - uy * sin),
    end[1] - headLength * (uy * cos + ux * sin)
  ];
  const right = [
    end[0] - headLength * (ux * cos + uy * sin),
    end[1] - headLength * (uy * cos - ux * sin)
  ];

  context.beginPath();
  context.moveTo(end[0], end[1]);
  context.lineTo(left[0], left[1]);
  context.moveTo(end[0], end[1]);
  context.lineTo(right[0], right[1]);
  context.stroke();
}

function drawPointDot(context, point, lineWidth) {
  context.beginPath();
  context.arc(point[0], point[1], lineWidth * 0.65, 0, Math.PI * 2);
  context.fill();
}

function drawPolylineStroke(context, pixelPoints) {
  context.beginPath();
  pixelPoints.forEach((point, index) => {
    if (index === 0) {
      context.moveTo(point[0], point[1]);
      return;
    }
    context.lineTo(point[0], point[1]);
  });
  context.stroke();
}

function drawRectangleStroke(context, start, end) {
  const x = Math.min(start[0], end[0]);
  const y = Math.min(start[1], end[1]);
  const width = Math.abs(end[0] - start[0]);
  const height = Math.abs(end[1] - start[1]);
  context.strokeRect(x, y, width, height);
}

function drawCircleStroke(context, center, edge) {
  const radius = Math.hypot(edge[0] - center[0], edge[1] - center[1]);
  context.beginPath();
  context.arc(center[0], center[1], radius, 0, Math.PI * 2);
  context.stroke();
}

function drawFillStroke(context, stroke, width, height, { color, alpha = 1 }) {
  const points = getFillStrokePoints(stroke);
  if (points.length < 3) {
    return;
  }

  const pixelPoints = points.map((point) => drawingPointToPixels(point, width, height));
  context.save();
  context.globalAlpha = alpha;
  context.fillStyle = color;
  context.beginPath();
  pixelPoints.forEach((point, index) => {
    if (index === 0) {
      context.moveTo(point[0], point[1]);
      return;
    }
    context.lineTo(point[0], point[1]);
  });
  context.closePath();
  context.fill();
  context.restore();
}

function drawLineStroke(context, stroke, width, height, { color, lineWidth, alpha = 1 }) {
  if (isFillStroke(stroke)) {
    return;
  }
  const points = getDrawingStrokePoints(stroke);
  if (!points.length) {
    return;
  }

  const pixelPoints = points.map((point) => drawingPointToPixels(point, width, height));

  context.save();
  context.globalAlpha = alpha;
  context.strokeStyle = color;
  context.fillStyle = color;
  context.lineCap = "round";
  context.lineJoin = "round";
  context.lineWidth = lineWidth;

  if (pixelPoints.length === 1) {
    drawPointDot(context, pixelPoints[0], lineWidth);
    context.restore();
    return;
  }

  if (stroke.tool === DRAWING_TOOL.RECTANGLE) {
    drawRectangleStroke(context, pixelPoints[0], pixelPoints[pixelPoints.length - 1]);
    context.restore();
    return;
  }

  if (stroke.tool === DRAWING_TOOL.CIRCLE) {
    drawCircleStroke(context, pixelPoints[0], pixelPoints[pixelPoints.length - 1]);
    context.restore();
    return;
  }

  drawPolylineStroke(context, pixelPoints);

  if (stroke.tool === DRAWING_TOOL.ARROW || stroke.tool === DRAWING_TOOL.DOUBLE_ARROW) {
    drawArrowHead(context, pixelPoints[pixelPoints.length - 2], pixelPoints[pixelPoints.length - 1], lineWidth);
  }
  if (stroke.tool === DRAWING_TOOL.DOUBLE_ARROW) {
    drawArrowHead(context, pixelPoints[1], pixelPoints[0], lineWidth);
  }

  context.restore();
}

function createOffscreenCanvas(width, height) {
  if (typeof OffscreenCanvas !== "undefined") {
    return new OffscreenCanvas(width, height);
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function getOpenBoundaryEndpoints(stroke, width, height) {
  if (!isFillBoundaryStroke(stroke) || isClosedDrawingStroke(stroke)) {
    return [];
  }
  const pixelPoints = getDrawingBoundaryPixelPoints(stroke, width, height);
  if (pixelPoints.length < 2) {
    return [];
  }
  const allowSelfConnect = stroke?.tool === DRAWING_TOOL.FREEHAND && pixelPoints.length > 2;
  return [
    {
      strokeId: String(stroke?.id || ""),
      point: pixelPoints[0],
      allowSelfConnect
    },
    {
      strokeId: String(stroke?.id || ""),
      point: pixelPoints[pixelPoints.length - 1],
      allowSelfConnect
    }
  ];
}

function pairNearbyBoundaryEndpoints(endpoints, maxDistance) {
  if (!Array.isArray(endpoints) || endpoints.length < 2 || maxDistance <= 0) {
    return [];
  }
  const candidates = [];
  for (let leftIndex = 0; leftIndex < endpoints.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < endpoints.length; rightIndex += 1) {
      const left = endpoints[leftIndex];
      const right = endpoints[rightIndex];
      const sameStroke = left.strokeId && left.strokeId === right.strokeId;
      if (sameStroke && !(left.allowSelfConnect && right.allowSelfConnect)) {
        continue;
      }
      const distance = Math.hypot(left.point[0] - right.point[0], left.point[1] - right.point[1]);
      if (distance <= maxDistance) {
        candidates.push({ leftIndex, rightIndex, distance });
      }
    }
  }
  candidates.sort((left, right) => left.distance - right.distance);
  const used = new Set();
  const pairs = [];
  for (const candidate of candidates) {
    if (used.has(candidate.leftIndex) || used.has(candidate.rightIndex)) {
      continue;
    }
    used.add(candidate.leftIndex);
    used.add(candidate.rightIndex);
    pairs.push([
      endpoints[candidate.leftIndex].point,
      endpoints[candidate.rightIndex].point
    ]);
  }
  return pairs;
}

function buildBoundaryMaskFromStrokes(strokes, width, height, { gapPx = 0, lineWidth = DRAWING_STROKE_WIDTH } = {}) {
  const canvas = createOffscreenCanvas(width, height);
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    return null;
  }

  context.clearRect(0, 0, width, height);
  const boundaryStrokes = Array.isArray(strokes) ? strokes.filter(isFillBoundaryStroke) : [];
  for (const stroke of boundaryStrokes) {
    drawLineStroke(context, stroke, width, height, {
      color: "#000000",
      lineWidth,
      alpha: 1
    });
  }

  if (gapPx > 0) {
    const connectors = pairNearbyBoundaryEndpoints(
      boundaryStrokes.flatMap((stroke) => getOpenBoundaryEndpoints(stroke, width, height)),
      Math.max(gapPx, lineWidth * 1.15)
    );
    if (connectors.length) {
      context.save();
      context.strokeStyle = "#000000";
      context.lineWidth = lineWidth;
      context.lineCap = "round";
      for (const [start, end] of connectors) {
        context.beginPath();
        context.moveTo(start[0], start[1]);
        context.lineTo(end[0], end[1]);
        context.stroke();
      }
      context.restore();
    }
  }

  const { data } = context.getImageData(0, 0, width, height);
  const mask = new Uint8Array(width * height);
  for (let index = 0; index < mask.length; index += 1) {
    mask[index] = data[index * 4 + 3] > 20 ? 1 : 0;
  }
  return mask;
}

function findNearestOpenSeed(boundaryMask, width, height, seedX, seedY, maxRadius = 5) {
  const x = clamp(Math.round(seedX), 0, width - 1);
  const y = clamp(Math.round(seedY), 0, height - 1);
  for (let radius = 0; radius <= maxRadius; radius += 1) {
    let best = null;
    let bestDistance = Infinity;
    for (let dy = -radius; dy <= radius; dy += 1) {
      for (let dx = -radius; dx <= radius; dx += 1) {
        const px = x + dx;
        const py = y + dy;
        if (px < 0 || py < 0 || px >= width || py >= height) {
          continue;
        }
        if (boundaryMask[py * width + px]) {
          continue;
        }
        const distance = Math.hypot(dx, dy);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = [px, py];
        }
      }
    }
    if (best) {
      return best;
    }
  }
  return null;
}

function floodFillInterior(boundaryMask, width, height, seedPoint) {
  const start = findNearestOpenSeed(boundaryMask, width, height, seedPoint[0], seedPoint[1]);
  if (!start) {
    return null;
  }

  const fillMask = new Uint8Array(width * height);
  const queue = new Int32Array(width * height);
  let head = 0;
  let tail = 0;
  const startIndex = start[1] * width + start[0];
  queue[tail++] = startIndex;
  fillMask[startIndex] = 1;
  let area = 0;
  let touchesEdge = false;

  while (head < tail) {
    const index = queue[head++];
    area += 1;
    const x = index % width;
    const y = (index / width) | 0;
    if (x === 0 || y === 0 || x === width - 1 || y === height - 1) {
      touchesEdge = true;
    }

    if (x > 0) {
      const leftIndex = index - 1;
      if (!boundaryMask[leftIndex] && !fillMask[leftIndex]) {
        fillMask[leftIndex] = 1;
        queue[tail++] = leftIndex;
      }
    }
    if (x + 1 < width) {
      const rightIndex = index + 1;
      if (!boundaryMask[rightIndex] && !fillMask[rightIndex]) {
        fillMask[rightIndex] = 1;
        queue[tail++] = rightIndex;
      }
    }
    if (y > 0) {
      const upIndex = index - width;
      if (!boundaryMask[upIndex] && !fillMask[upIndex]) {
        fillMask[upIndex] = 1;
        queue[tail++] = upIndex;
      }
    }
    if (y + 1 < height) {
      const downIndex = index + width;
      if (!boundaryMask[downIndex] && !fillMask[downIndex]) {
        fillMask[downIndex] = 1;
        queue[tail++] = downIndex;
      }
    }
  }

  return {
    mask: fillMask,
    area,
    touchesEdge,
    seed: start
  };
}

function polygonArea2d(points) {
  let area = 0;
  for (let index = 0, previous = points.length - 1; index < points.length; previous = index, index += 1) {
    area += points[previous][0] * points[index][1] - points[index][0] * points[previous][1];
  }
  return area / 2;
}

function removeDuplicatePolygonPoints(points) {
  const next = [];
  for (const point of points) {
    if (!next.length || !pointsEqual2d(next[next.length - 1], point)) {
      next.push(point);
    }
  }
  if (next.length > 1 && pointsEqual2d(next[0], next[next.length - 1])) {
    next.pop();
  }
  return next;
}

function removeCollinearPolygonPoints(points) {
  const loop = removeDuplicatePolygonPoints(points);
  if (loop.length < 3) {
    return loop;
  }
  const next = [];
  for (let index = 0; index < loop.length; index += 1) {
    const previous = loop[(index + loop.length - 1) % loop.length];
    const current = loop[index];
    const following = loop[(index + 1) % loop.length];
    const cross =
      (current[0] - previous[0]) * (following[1] - current[1]) -
      (current[1] - previous[1]) * (following[0] - current[0]);
    if (Math.abs(cross) > 1e-4) {
      next.push(current);
    }
  }
  return next.length >= 3 ? next : loop;
}

function downsamplePolygon(points, maxPoints = 160) {
  if (points.length <= maxPoints) {
    return points;
  }
  const step = points.length / maxPoints;
  const next = [];
  let cursor = 0;
  for (let index = 0; index < maxPoints; index += 1) {
    next.push(points[Math.floor(cursor) % points.length]);
    cursor += step;
  }
  return removeDuplicatePolygonPoints(next);
}

function pointKey(point) {
  return `${point[0]},${point[1]}`;
}

function traceMaskLoops(mask, width, height) {
  const segments = [];
  const adjacency = new Map();
  const addSegment = (start, end) => {
    const index = segments.length;
    segments.push([start, end]);
    const key = pointKey(start);
    const entries = adjacency.get(key);
    if (entries) {
      entries.push(index);
      return;
    }
    adjacency.set(key, [index]);
  };

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (!mask[y * width + x]) {
        continue;
      }
      if (y === 0 || !mask[(y - 1) * width + x]) {
        addSegment([x, y], [x + 1, y]);
      }
      if (x === width - 1 || !mask[y * width + x + 1]) {
        addSegment([x + 1, y], [x + 1, y + 1]);
      }
      if (y === height - 1 || !mask[(y + 1) * width + x]) {
        addSegment([x + 1, y + 1], [x, y + 1]);
      }
      if (x === 0 || !mask[y * width + x - 1]) {
        addSegment([x, y + 1], [x, y]);
      }
    }
  }

  const used = new Uint8Array(segments.length);
  const loops = [];
  for (let index = 0; index < segments.length; index += 1) {
    if (used[index]) {
      continue;
    }
    const loop = [];
    let currentIndex = index;
    let guard = 0;
    while (currentIndex !== -1 && !used[currentIndex] && guard < segments.length + 4) {
      used[currentIndex] = 1;
      const [start, end] = segments[currentIndex];
      if (!loop.length) {
        loop.push(start);
      }
      loop.push(end);
      if (pointsEqual2d(end, loop[0])) {
        break;
      }
      const nextCandidates = adjacency.get(pointKey(end)) || [];
      currentIndex = nextCandidates.find((candidateIndex) => !used[candidateIndex]) ?? -1;
      guard += 1;
    }
    if (loop.length >= 4 && pointsEqual2d(loop[0], loop[loop.length - 1])) {
      const normalizedLoop = removeCollinearPolygonPoints(loop.slice(0, -1));
      if (normalizedLoop.length >= 3) {
        loops.push(normalizedLoop);
      }
    }
  }
  return loops;
}

function normalizePolygonPoints(points, width, height) {
  return points.map((point) => ({
    x: clamp(point[0] / width, 0, 1),
    y: clamp(point[1] / height, 0, 1)
  }));
}

function buildPolygonFromFilledMask(mask, width, height, seedPoint) {
  const loops = traceMaskLoops(mask, width, height);
  if (!loops.length) {
    return null;
  }
  const seed = [seedPoint[0] + 0.5, seedPoint[1] + 0.5];
  const containingLoops = loops.filter((loop) => pointInPolygon2d(seed, loop));
  const sourceLoops = containingLoops.length ? containingLoops : loops;
  const chosen = sourceLoops.reduce((best, current) => {
    if (!best) {
      return current;
    }
    return Math.abs(polygonArea2d(current)) > Math.abs(polygonArea2d(best)) ? current : best;
  }, null);
  if (!chosen) {
    return null;
  }
  const simplified = downsamplePolygon(removeCollinearPolygonPoints(chosen));
  return simplified.length >= 3 ? normalizePolygonPoints(simplified, width, height) : null;
}

function findNearestValidDistance(distances, index, direction) {
  for (let offset = 1; offset < distances.length; offset += 1) {
    const nextIndex = (index + direction * offset + distances.length) % distances.length;
    if (Number.isFinite(distances[nextIndex])) {
      return {
        value: distances[nextIndex],
        offset
      };
    }
  }
  return null;
}

function buildGuessedFillPolygon(boundaryMask, width, height, seedPoint) {
  const start = findNearestOpenSeed(boundaryMask, width, height, seedPoint[0], seedPoint[1]);
  if (!start) {
    return null;
  }
  const maxDistance = Math.hypot(width, height);
  const distances = Array.from({ length: DRAWING_FILL_RAY_COUNT }, () => null);

  for (let index = 0; index < DRAWING_FILL_RAY_COUNT; index += 1) {
    const angle = (index / DRAWING_FILL_RAY_COUNT) * Math.PI * 2;
    const dx = Math.cos(angle);
    const dy = Math.sin(angle);
    for (let distance = 1; distance < maxDistance; distance += 1) {
      const x = Math.round(start[0] + dx * distance);
      const y = Math.round(start[1] + dy * distance);
      if (x < 0 || y < 0 || x >= width || y >= height) {
        break;
      }
      if (boundaryMask[y * width + x]) {
        distances[index] = Math.max(distance - 1.5, 1);
        break;
      }
    }
  }

  const validDistances = distances.filter(Number.isFinite);
  if (validDistances.length < Math.max(12, Math.floor(DRAWING_FILL_RAY_COUNT / 4))) {
    return null;
  }

  const orderedDistances = [...validDistances].sort((left, right) => left - right);
  const medianDistance = orderedDistances[Math.floor(orderedDistances.length / 2)] || 1;
  const resolvedDistances = distances.map((value, index) => {
    if (Number.isFinite(value)) {
      return value;
    }
    const previous = findNearestValidDistance(distances, index, -1);
    const next = findNearestValidDistance(distances, index, 1);
    if (previous && next) {
      const total = previous.offset + next.offset;
      return (previous.value * next.offset + next.value * previous.offset) / Math.max(total, 1);
    }
    if (previous) {
      return previous.value;
    }
    if (next) {
      return next.value;
    }
    return medianDistance;
  });

  let smoothedDistances = resolvedDistances;
  for (let pass = 0; pass < 2; pass += 1) {
    smoothedDistances = smoothedDistances.map((value, index) => {
      const previous = smoothedDistances[(index + smoothedDistances.length - 1) % smoothedDistances.length];
      const next = smoothedDistances[(index + 1) % smoothedDistances.length];
      return (previous + value * 2 + next) / 4;
    });
  }

  const polygon = smoothedDistances.map((distance, index) => {
    const angle = (index / DRAWING_FILL_RAY_COUNT) * Math.PI * 2;
    return [
      clamp(start[0] + Math.cos(angle) * distance, 0, width),
      clamp(start[1] + Math.sin(angle) * distance, 0, height)
    ];
  });
  const simplified = downsamplePolygon(removeCollinearPolygonPoints(polygon), DRAWING_FILL_RAY_COUNT);
  if (simplified.length < 3) {
    return null;
  }
  const area = Math.abs(polygonArea2d(simplified));
  if (area < DRAWING_FILL_MIN_REGION_PIXELS || area > width * height * DRAWING_FILL_MAX_REGION_RATIO) {
    return null;
  }
  return normalizePolygonPoints(simplified, width, height);
}

function buildFillStrokeAtPoint(point, strokes, canvas) {
  const boundaryStrokes = Array.isArray(strokes) ? strokes.filter(isFillBoundaryStroke) : [];
  if (!boundaryStrokes.length) {
    return null;
  }

  const canvasWidth = canvas.width || 1;
  const canvasHeight = canvas.height || 1;
  const maxCanvasDimension = Math.max(canvasWidth, canvasHeight, 1);
  const analysisScale = Math.min(1, DRAWING_FILL_ANALYSIS_MAX_DIMENSION / maxCanvasDimension);
  const analysisWidth = Math.max(DRAWING_FILL_ANALYSIS_MIN_DIMENSION, Math.round(canvasWidth * analysisScale));
  const analysisHeight = Math.max(DRAWING_FILL_ANALYSIS_MIN_DIMENSION, Math.round(canvasHeight * analysisScale));
  const seedPoint = [point.x * (analysisWidth - 1), point.y * (analysisHeight - 1)];
  const lineWidth = Math.max(3, DRAWING_STROKE_WIDTH * analysisScale + 3);
  const gapStrategies = [
    { gapPx: 0, guessed: false },
    { gapPx: DRAWING_FILL_CONNECT_GAP_PX * 0.45 * analysisScale, guessed: true },
    { gapPx: DRAWING_FILL_CONNECT_GAP_PX * analysisScale, guessed: true }
  ];

  for (const strategy of gapStrategies) {
    const boundaryMask = buildBoundaryMaskFromStrokes(boundaryStrokes, analysisWidth, analysisHeight, {
      gapPx: strategy.gapPx,
      lineWidth
    });
    if (!boundaryMask) {
      continue;
    }
    const filledRegion = floodFillInterior(boundaryMask, analysisWidth, analysisHeight, seedPoint);
    if (!filledRegion || filledRegion.area < DRAWING_FILL_MIN_REGION_PIXELS) {
      continue;
    }
    if (filledRegion.touchesEdge || filledRegion.area > analysisWidth * analysisHeight * DRAWING_FILL_MAX_REGION_RATIO) {
      continue;
    }
    const fillPoints = buildPolygonFromFilledMask(
      filledRegion.mask,
      analysisWidth,
      analysisHeight,
      filledRegion.seed
    );
    if (fillPoints?.length >= 3) {
      return {
        tool: DRAWING_TOOL.FILL,
        points: [point],
        fillPoints,
        guessed: strategy.guessed
      };
    }
  }

  const fallbackBoundaryMask = buildBoundaryMaskFromStrokes(boundaryStrokes, analysisWidth, analysisHeight, {
    gapPx: DRAWING_FILL_CONNECT_GAP_PX * analysisScale,
    lineWidth
  });
  if (!fallbackBoundaryMask) {
    return null;
  }
  const fillPoints = buildGuessedFillPolygon(fallbackBoundaryMask, analysisWidth, analysisHeight, seedPoint);
  if (!fillPoints?.length || fillPoints.length < 3) {
    return null;
  }
  return {
    tool: DRAWING_TOOL.FILL,
    points: [point],
    fillPoints,
    guessed: true
  };
}

function redrawDrawingCanvas(canvas, strokes, draftStroke = null) {
  if (!canvas) {
    return;
  }
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);

  const allStrokes = Array.isArray(strokes) ? strokes : [];
  for (const stroke of allStrokes) {
    if (!isFillStroke(stroke)) {
      continue;
    }
    drawFillStroke(context, stroke, width, height, {
      color: stroke?.guessed ? DRAWING_GUESSED_FILL_COLOR : DRAWING_FILL_COLOR,
      alpha: 1
    });
  }
  for (const stroke of allStrokes) {
    if (isSurfaceLineStroke(stroke)) {
      continue;
    }
    drawLineStroke(context, stroke, width, height, {
      color: DRAWING_STROKE_HALO,
      lineWidth: DRAWING_STROKE_HALO_WIDTH
    });
    drawLineStroke(context, stroke, width, height, {
      color: DRAWING_STROKE_COLOR,
      lineWidth: DRAWING_STROKE_WIDTH
    });
  }

  if (draftStroke) {
    drawLineStroke(context, draftStroke, width, height, {
      color: DRAWING_STROKE_HALO,
      lineWidth: DRAWING_STROKE_HALO_WIDTH,
      alpha: 0.78
    });
    drawLineStroke(context, draftStroke, width, height, {
      color: DRAWING_STROKE_COLOR,
      lineWidth: DRAWING_STROKE_WIDTH,
      alpha: 0.9
    });
  }
}

function distanceToStrokeInPixels(point, stroke, width, height) {
  if (isFillStroke(stroke)) {
    const pixelPoint = drawingPointToPixels(point, width, height);
    const polygon = getFillStrokePoints(stroke).map((entry) => drawingPointToPixels(entry, width, height));
    if (polygon.length < 3) {
      return Infinity;
    }
    if (pointInPolygon2d(pixelPoint, polygon)) {
      return 0;
    }
    let minimum = Infinity;
    for (let index = 0; index < polygon.length; index += 1) {
      const start = polygon[index];
      const end = polygon[(index + 1) % polygon.length];
      minimum = Math.min(minimum, distancePointToSegment2d(pixelPoint, start, end));
    }
    return minimum;
  }

  const points = getDrawingStrokePoints(stroke);
  if (!points.length) {
    return Infinity;
  }
  const pixelPoint = drawingPointToPixels(point, width, height);
  const pixelPoints = points.map((entry) => drawingPointToPixels(entry, width, height));
  if (pixelPoints.length === 1) {
    const pointPixels = pixelPoints[0];
    return Math.hypot(pixelPoint[0] - pointPixels[0], pixelPoint[1] - pointPixels[1]);
  }

  if (stroke.tool === DRAWING_TOOL.RECTANGLE) {
    const start = pixelPoints[0];
    const end = pixelPoints[pixelPoints.length - 1];
    const corners = [
      [start[0], start[1]],
      [end[0], start[1]],
      [end[0], end[1]],
      [start[0], end[1]]
    ];
    let minimum = Infinity;
    for (let index = 0; index < corners.length; index += 1) {
      const a = corners[index];
      const b = corners[(index + 1) % corners.length];
      minimum = Math.min(minimum, distancePointToSegment2d(pixelPoint, a, b));
    }
    return minimum;
  }

  if (stroke.tool === DRAWING_TOOL.CIRCLE) {
    const center = pixelPoints[0];
    const edge = pixelPoints[pixelPoints.length - 1];
    const radius = Math.hypot(edge[0] - center[0], edge[1] - center[1]);
    return Math.abs(Math.hypot(pixelPoint[0] - center[0], pixelPoint[1] - center[1]) - radius);
  }

  let minimum = Infinity;
  for (let index = 1; index < pixelPoints.length; index += 1) {
    const start = pixelPoints[index - 1];
    const end = pixelPoints[index];
    minimum = Math.min(minimum, distancePointToSegment2d(pixelPoint, start, end));
  }
  return minimum;
}

function niceGridStep(minimumStep) {
  if (!Number.isFinite(minimumStep) || minimumStep <= 0) {
    return getSceneScaleSettings(VIEWER_SCENE_SCALE.CAD).minGridSize / DEFAULT_GRID_DIVISIONS;
  }
  const exponent = Math.floor(Math.log10(minimumStep));
  const base = 10 ** exponent;
  for (const multiplier of [1, 2, 5, 10]) {
    const step = base * multiplier;
    if (step >= minimumStep) {
      return step;
    }
  }
  return base * 10;
}

function buildGridConfig(radius, sceneScaleMode) {
  const desiredSize = getStageFloorSize(radius, sceneScaleMode);
  const cellSize = niceGridStep(desiredSize / GRID_TARGET_DIVISIONS);
  let divisions = Math.ceil(desiredSize / cellSize);
  if (divisions % 2 !== 0) {
    divisions += 1;
  }
  return {
    size: Math.max(desiredSize, cellSize * divisions),
    divisions: Math.max(DEFAULT_GRID_DIVISIONS, divisions)
  };
}

function updateGridHelper(
  runtime,
  viewerTheme,
  radius,
  floorY = 0,
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
  floorMode = LOOK_FLOOR_MODES.STAGE
) {
  if (!runtime?.THREE || !runtime?.scene) {
    return;
  }
  runtime.gridRadius = radius;
  runtime.gridFloorY = floorY;
  runtime.floorMode = floorMode;
  if (floorMode !== LOOK_FLOOR_MODES.GRID) {
    disposeSceneObject(runtime.gridHelper);
    runtime.gridHelper = null;
    runtime.gridConfig = null;
    return;
  }
  const nextConfig = buildGridConfig(radius, sceneScaleMode);
  const currentConfig = runtime.gridConfig;
  if (currentConfig && currentConfig.size === nextConfig.size && currentConfig.divisions === nextConfig.divisions) {
    runtime.gridHelper?.position.set(0, floorY, 0);
    return;
  }

  disposeSceneObject(runtime.gridHelper);
  runtime.gridHelper = new runtime.THREE.GridHelper(
    nextConfig.size,
    nextConfig.divisions,
    viewerTheme?.gridCenter || BASE_VIEWER_THEME.gridCenter,
    viewerTheme?.gridCell || BASE_VIEWER_THEME.gridCell
  );
  const materials = Array.isArray(runtime.gridHelper.material)
    ? runtime.gridHelper.material
    : [runtime.gridHelper.material];
  for (const material of materials) {
    material.transparent = true;
    material.opacity = viewerTheme?.gridOpacity ?? BASE_VIEWER_THEME.gridOpacity;
    material.depthWrite = false;
    material.toneMapped = false;
  }
  runtime.gridHelper.position.set(0, floorY, 0);
  runtime.scene.add(runtime.gridHelper);
  runtime.gridConfig = nextConfig;
}

const CadViewer = forwardRef(function CadViewer({
  meshData,
  modelKey,
  perspective = null,
  perspectiveRef = null,
  showEdges,
  recomputeNormals,
  theme = BASE_VIEWER_THEME,
  lookSettings = null,
  floorModeOverride = "",
  previewMode = false,
  showViewPlane = true,
  viewPlaneOffsetRight = 16,
  viewPlaneOffsetBottom = 16,
  compactViewPlane = false,
  viewportFrameInsets = null,
  isLoading = false,
  pickMode = VIEWER_PICK_MODE.AUTO,
  renderPartsIndividually = false,
  partIntroAnimation = null,
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
  pickableParts = [],
  hiddenPartIds = [],
  selectedPartIds = [],
  hoveredPartId = "",
  hoveredReferenceId = "",
  selectedReferenceIds = [],
  selectorRuntime = null,
  pickableFaces = [],
  pickableEdges = [],
  pickableVertices = [],
  surfaceLineFaceId = "",
  focusedPartId = "",
  drawingEnabled = false,
  drawingTool = DRAWING_TOOL.FREEHAND,
  drawingStrokes = [],
  onDrawingStrokesChange,
  onPerspectiveChange,
  onHoverReferenceChange,
  onActivateReference,
  onDoubleActivateReference,
  onViewerAlertChange
}, ref) {
  const normalizedSceneScaleMode = normalizeSceneScaleMode(sceneScaleMode);
  const defaultGridRadius = defaultSceneGridRadius(normalizedSceneScaleMode);
  const normalizedViewportFrameInsets = useMemo(
    () => normalizeViewportFrameInsets(viewportFrameInsets),
    [
      viewportFrameInsets?.top,
      viewportFrameInsets?.right,
      viewportFrameInsets?.bottom,
      viewportFrameInsets?.left
    ]
  );
  const interactionHostRef = useRef(null);
  const mountRef = useRef(null);
  const drawingCanvasRef = useRef(null);
  const drawingDraftRef = useRef(null);
  const drawingStrokesRef = useRef(Array.isArray(drawingStrokes) ? drawingStrokes : []);
  const drawingChangeRef = useRef(onDrawingStrokesChange);
  const perspectiveChangeRef = useRef(onPerspectiveChange);
  const viewerAlertChangeRef = useRef(onViewerAlertChange);
  const lastEmittedPerspectiveRef = useRef(null);
  const suppressPerspectiveEventsRef = useRef(0);
  const drawingIdRef = useRef(0);
  const runtimeRef = useRef(null);
  const viewportFrameInsetsRef = useRef(normalizedViewportFrameInsets);
  const framedModelKeyRef = useRef("");
  const modelTransformRef = useRef({
    modelKey: "",
    offset: null
  });
  const partIntroStateRef = useRef({
    frameId: 0,
    playedIntroKey: ""
  });
  const [error, setError] = useState("");
  const [viewerReadyTick, setViewerReadyTick] = useState(0);
  const [activeViewPlaneFace, setActiveViewPlaneFace] = useState("");
  const [viewPlaneOrientation, setViewPlaneOrientation] = useState(DEFAULT_VIEW_PLANE_ORIENTATION);
  const activeViewPlaneFaceRef = useRef("");
  const previewModeRef = useRef(previewMode);
  const viewerTheme = theme || BASE_VIEWER_THEME;
  const normalizedLookSettings = useMemo(() => normalizeLookSettingsShape(lookSettings), [lookSettings]);
  const resolvedFloorMode = floorModeOverride
    ? normalizeFloorMode(floorModeOverride, resolveFloorMode(normalizedLookSettings.floor))
    : resolveFloorMode(normalizedLookSettings.floor);
  const edgesVisible = showEdges && normalizedLookSettings.edges.enabled;
  const partVisualStateEnabled =
    pickMode === VIEWER_PICK_MODE.PARTS ||
    pickMode === VIEWER_PICK_MODE.ASSEMBLY ||
    (
      pickMode === VIEWER_PICK_MODE.AUTO &&
      Array.isArray(pickableParts) &&
      pickableParts.length > 0
    ) ||
    !!String(focusedPartId || "").trim();
  const partVisualStateRef = useRef({
    viewerTheme,
    edgeSettings: normalizedLookSettings.edges,
    hiddenPartIds: partVisualStateEnabled ? hiddenPartIds : [],
    hoveredPartId: partVisualStateEnabled ? hoveredPartId : "",
    focusedPartId: partVisualStateEnabled ? focusedPartId : "",
    selectedPartIds: partVisualStateEnabled ? selectedPartIds : [],
    showEdges: edgesVisible
  });

  useEffect(() => {
    partVisualStateRef.current = {
      viewerTheme,
      edgeSettings: normalizedLookSettings.edges,
      hiddenPartIds: partVisualStateEnabled ? hiddenPartIds : [],
      hoveredPartId: partVisualStateEnabled ? hoveredPartId : "",
      focusedPartId: partVisualStateEnabled ? focusedPartId : "",
      selectedPartIds: partVisualStateEnabled ? selectedPartIds : [],
      showEdges: edgesVisible
    };
  }, [
    edgesVisible,
    focusedPartId,
    hiddenPartIds,
    hoveredPartId,
    partVisualStateEnabled,
    selectedPartIds,
    viewerTheme,
    normalizedLookSettings.edges
  ]);
  const focusedPartIdValue = String(focusedPartId || "").trim();
  const activeSurfaceLineFaceId = String(surfaceLineFaceId || "").trim();
  const filteredPickableFaces = useMemo(() => (
    focusedPartIdValue
      ? (Array.isArray(pickableFaces) ? pickableFaces : []).filter((reference) => String(reference?.partId || "").trim() === focusedPartIdValue)
      : (Array.isArray(pickableFaces) ? pickableFaces : [])
  ), [focusedPartIdValue, pickableFaces]);
  const filteredPickableEdges = useMemo(() => (
    focusedPartIdValue
      ? (Array.isArray(pickableEdges) ? pickableEdges : []).filter((reference) => String(reference?.partId || "").trim() === focusedPartIdValue)
      : (Array.isArray(pickableEdges) ? pickableEdges : [])
  ), [focusedPartIdValue, pickableEdges]);
  const filteredPickableVertices = useMemo(() => (
    focusedPartIdValue
      ? (Array.isArray(pickableVertices) ? pickableVertices : []).filter((reference) => String(reference?.partId || "").trim() === focusedPartIdValue)
      : (Array.isArray(pickableVertices) ? pickableVertices : [])
  ), [focusedPartIdValue, pickableVertices]);
  const measurementSummary = useMemo(() => {
    const modelMeasurement = buildBoundsMeasurement(meshData?.bounds);
    if (!modelMeasurement) {
      return null;
    }
    const activePart = findMeasurementPart(meshData, selectedPartIds, hoveredPartId, focusedPartIdValue);
    const partMeasurement = activePart ? buildBoundsMeasurement(activePart.bounds) : null;
    return {
      model: modelMeasurement,
      part: partMeasurement
        ? {
          label: String(activePart?.label || activePart?.name || activePart?.id || "Selected part").trim(),
          measurement: partMeasurement
        }
        : null,
      partCount: Array.isArray(meshData?.parts) ? meshData.parts.length : 0
    };
  }, [meshData, selectedPartIds, hoveredPartId, focusedPartIdValue]);
  const pickableReferenceMap = useMemo(() => {
    if (selectorRuntime?.referenceMap instanceof Map) {
      return selectorRuntime.referenceMap;
    }
    const map = new Map();
    for (const reference of [...filteredPickableFaces, ...filteredPickableEdges, ...filteredPickableVertices]) {
      const referenceId = String(reference?.id || "").trim();
      if (!referenceId) {
        continue;
      }
      map.set(referenceId, reference);
    }
    return map;
  }, [filteredPickableEdges, filteredPickableFaces, filteredPickableVertices, selectorRuntime]);
  const pickableFaceReferenceIds = useMemo(
    () => new Set(filteredPickableFaces.map((reference) => String(reference?.id || "").trim()).filter(Boolean)),
    [filteredPickableFaces]
  );
  const syncDrawingCanvasSize = (runtime = runtimeRef.current) => {
    const canvas = drawingCanvasRef.current;
    if (!canvas) {
      return null;
    }
    const rendererCanvas = runtime?.renderer?.domElement;
    const width = rendererCanvas?.width || mountRef.current?.clientWidth || 1;
    const height = rendererCanvas?.height || mountRef.current?.clientHeight || 1;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    return canvas;
  };
  const renderDrawingOverlay = () => {
    const canvas = syncDrawingCanvasSize();
    if (!canvas) {
      return;
    }
    redrawDrawingCanvas(canvas, drawingStrokesRef.current, drawingDraftRef.current);
  };
  useEffect(() => {
    viewportFrameInsetsRef.current = normalizedViewportFrameInsets;
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }
    applyCameraFrameInsets(runtime, normalizedViewportFrameInsets);
    runtime.requestRender?.();
  }, [
    normalizedViewportFrameInsets.top,
    normalizedViewportFrameInsets.right,
    normalizedViewportFrameInsets.bottom,
    normalizedViewportFrameInsets.left,
    viewerReadyTick
  ]);
  const runWithoutPerspectiveEvents = (callback) => {
    suppressPerspectiveEventsRef.current += 1;
    try {
      return callback();
    } finally {
      suppressPerspectiveEventsRef.current = Math.max(0, suppressPerspectiveEventsRef.current - 1);
    }
  };
  const emitPerspectiveChange = (runtime = runtimeRef.current) => {
    const nextPerspective = readScopedPerspectiveSnapshot(runtime, {
      modelKey,
      sceneScaleMode: normalizedSceneScaleMode
    });
    if (!nextPerspective) {
      return;
    }
    if (suppressPerspectiveEventsRef.current > 0) {
      lastEmittedPerspectiveRef.current = nextPerspective;
      return;
    }
    if (perspectiveSnapshotEqual(lastEmittedPerspectiveRef.current, nextPerspective)) {
      return;
    }
    lastEmittedPerspectiveRef.current = nextPerspective;
    perspectiveChangeRef.current?.(nextPerspective);
  };
  const syncViewPlaneOrientation = (runtime = runtimeRef.current) => {
    const nextOrientation = readViewPlaneOrientation(runtime);
    if (!nextOrientation) {
      return;
    }
    setViewPlaneOrientation((current) => (
      viewPlaneOrientationEqual(current, nextOrientation) ? current : nextOrientation
    ));
  };
  const buildSurfaceLineFaceAnchor = (event, canvas, lockedReferenceId = "", startUv = null) => {
    const runtime = runtimeRef.current;
    if (!runtime?.raycaster || !runtime?.camera || !runtime?.facePickMesh || !selectorRuntime?.faceReferenceByRowIndex) {
      return null;
    }
    const activeLockedReferenceId = String(lockedReferenceId || activeSurfaceLineFaceId).trim();

    const rect = canvas.getBoundingClientRect();
    const width = rect.width || 1;
    const height = rect.height || 1;
    runtime.pointer.x = ((event.clientX - rect.left) / width) * 2 - 1;
    runtime.pointer.y = -((event.clientY - rect.top) / height) * 2 + 1;
    runtime.raycaster.setFromCamera(runtime.pointer, runtime.camera);

    const intersections = runtime.raycaster.intersectObject(runtime.facePickMesh, false);
    for (const intersection of intersections) {
      const triangleIndex = Number(intersection?.faceIndex);
      const rowIndex = Number.isInteger(triangleIndex) ? Number(runtime.facePickMesh.userData?.faceIds?.[triangleIndex]) : NaN;
      if (!Number.isInteger(rowIndex)) {
        continue;
      }
      const reference = selectorRuntime.faceReferenceByRowIndex.get(rowIndex) || null;
      const referenceId = String(reference?.id || "").trim();
      if (!referenceId) {
        continue;
      }
      if (activeLockedReferenceId) {
        if (referenceId !== activeLockedReferenceId) {
          continue;
        }
      } else if (pickableFaceReferenceIds.size && !pickableFaceReferenceIds.has(referenceId)) {
        continue;
      }

      const surface = reference?.pickData?.surface || {};
      if (SURFACE_LINE_UNSUPPORTED_TYPES.has(String(surface.type || "").trim())) {
        return null;
      }
      const localPoint = intersection.object.worldToLocal(intersection.point.clone());
      const point = [localPoint.x, localPoint.y, localPoint.z];
      const angleCenter = surface.type === "CYLINDRICAL_SURFACE" && Array.isArray(startUv) ? (startUv[0] / Math.max(Number(surface.radius) || 1, 1)) : null;
      const uv = projectPointToSurfaceUv(surface, point, angleCenter);
      if (!uv) {
        return null;
      }
      return {
        screenPoint: buildDrawingPoint(event, canvas),
        surfaceLine: {
          referenceId,
          selector: String(reference?.displaySelector || "").trim(),
          normalizedSelector: String(reference?.normalizedSelector || "").trim(),
          faceToken: parseFaceToken(reference?.copyText),
          partId: String(reference?.partId || "").trim(),
          surfaceType: String(surface.type || "").trim(),
          startPoint: point,
          endPoint: point,
          startUv: uv,
          endUv: uv
        }
      };
    }
    return null;
  };
  const updateSurfaceLineFaceAnchor = (event, canvas, draftSurfaceLine) => {
    const lockedReferenceId = String(draftSurfaceLine?.referenceId || "").trim();
    if (!lockedReferenceId) {
      return null;
    }
    const nextAnchor = buildSurfaceLineFaceAnchor(event, canvas, lockedReferenceId, draftSurfaceLine?.startUv);
    if (!nextAnchor) {
      return null;
    }
    return {
      screenPoint: nextAnchor.screenPoint,
      surfaceLine: {
        ...draftSurfaceLine,
        endPoint: nextAnchor.surfaceLine.endPoint,
        endUv: nextAnchor.surfaceLine.endUv
      }
    };
  };

  const activateViewPlaneFace = (faceId) => {
    const runtime = runtimeRef.current;
    const face = VIEW_PLANE_FACE_BY_ID[faceId];
    if (!runtime || !face) {
      return false;
    }
    activeViewPlaneFaceRef.current = face.id;
    setActiveViewPlaneFace(face.id);
    return transitionCameraToViewPreset(runtime, face);
  };
  const activateDefaultViewPlane = () => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return false;
    }
    activeViewPlaneFaceRef.current = "";
    setActiveViewPlaneFace("");
    return transitionCameraToViewPreset(runtime, VIEW_PLANE_DEFAULT_PRESET);
  };

  useImperativeHandle(ref, () => ({
    async captureScreenshot({ filename = "cad-screenshot.png", mode = "download" } = {}) {
      const runtime = runtimeRef.current;
      if (!runtime?.renderer || !runtime?.scene || !runtime?.camera) {
        throw new Error("Viewer not ready");
      }

      renderDrawingOverlay();
      const blobPromise = buildCompositeScreenshotBlob(runtime, drawingCanvasRef.current);

      if (mode === "clipboard") {
        return await copyImageBlobToClipboard(blobPromise);
      }

      const blob = await blobPromise;
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
      return blob;
    },
    getPerspective() {
      return readScopedPerspectiveSnapshot(runtimeRef.current, {
        modelKey,
        sceneScaleMode: normalizedSceneScaleMode
      });
    },
    focusViewPreset(faceId) {
      return activateViewPlaneFace(faceId);
    }
  }), [modelKey, normalizedSceneScaleMode]);

  useEffect(() => {
    previewModeRef.current = previewMode;
  }, [previewMode]);

  useEffect(() => {
    drawingChangeRef.current = onDrawingStrokesChange;
  }, [onDrawingStrokesChange]);

  useEffect(() => {
    perspectiveChangeRef.current = onPerspectiveChange;
  }, [onPerspectiveChange]);

  useEffect(() => {
    viewerAlertChangeRef.current = onViewerAlertChange;
  }, [onViewerAlertChange]);

  useEffect(() => {
    drawingStrokesRef.current = Array.isArray(drawingStrokes) ? drawingStrokes : [];
    drawingIdRef.current = Math.max(drawingIdRef.current, maxDrawingStrokeOrdinal(drawingStrokesRef.current));
    renderDrawingOverlay();
  }, [drawingStrokes]);

  useViewerRuntime({
    mountRef,
    runtimeRef,
    previewModeRef,
    setError,
    setViewerReadyTick,
    viewerTheme,
    syncDrawingCanvasSize,
    renderDrawingOverlay,
    emitPerspectiveChange,
    setActiveViewPlaneFace,
    activeViewPlaneFaceRef,
    stepCameraTransition,
    stepKeyboardOrbit,
    getActiveViewPlaneFaceId,
    cancelCameraTransition,
    clearKeyboardOrbitState,
    isTrackpadLikeWheelEvent,
    getKeyboardOrbitCommand,
    getKeyboardOrbitAxes,
    applyOrbitDelta,
    getViewerThemeValue,
    getPixelRatioCap,
    applySceneBackground,
    applyCameraFrameInsets,
    frameInsetsRef: viewportFrameInsetsRef,
    updateGridHelper,
    clearSceneGroup,
    disposeSceneObject,
    disposeTexture,
    syncViewPlaneOrientation,
    BASE_VIEWER_THEME,
    DEFAULT_LIGHTING,
    DEFAULT_DAMPING_FACTOR,
    DEFAULT_ZOOM_SPEED,
    COARSE_POINTER_ZOOM_SPEED,
    INTERACTION_PIXEL_RATIO_CAP,
    IDLE_PIXEL_RATIO_CAP,
    INTERACTION_IDLE_DELAY_MS,
    TRACKPAD_PINCH_ZOOM_SPEED,
    COARSE_POINTER_PINCH_ZOOM_SPEED,
    ACCELERATED_WHEEL_ZOOM_SPEED,
    KEYBOARD_ORBIT_NUDGE_RAD,
    defaultGridRadius,
    sceneScaleMode: normalizedSceneScaleMode,
    floorMode: resolvedFloorMode
  });

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }
    runtime.sceneScaleMode = normalizedSceneScaleMode;
  }, [normalizedSceneScaleMode]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }

    applySceneBackground(runtime, viewerTheme, normalizedLookSettings.background);
    runtime.renderer.toneMappingExposure = Math.max(normalizedLookSettings.lighting.toneMappingExposure, 0.05);

    runtime.hemisphereLight.visible = normalizedLookSettings.lighting.hemisphere.enabled;
    runtime.hemisphereLight.color.set(normalizedLookSettings.lighting.hemisphere.skyColor);
    runtime.hemisphereLight.groundColor.set(normalizedLookSettings.lighting.hemisphere.groundColor);
    runtime.hemisphereLight.intensity = normalizedLookSettings.lighting.hemisphere.intensity;

    runtime.ambientLight.visible = normalizedLookSettings.lighting.ambient.enabled;
    runtime.ambientLight.color.set(normalizedLookSettings.lighting.ambient.color);
    runtime.ambientLight.intensity = normalizedLookSettings.lighting.ambient.intensity;

    runtime.keyLight.visible = normalizedLookSettings.lighting.directional.enabled;
    runtime.keyLight.color.set(normalizedLookSettings.lighting.directional.color);
    runtime.keyLight.intensity = normalizedLookSettings.lighting.directional.intensity;
    runtime.keyLight.position.set(
      normalizedLookSettings.lighting.directional.position.x,
      normalizedLookSettings.lighting.directional.position.y,
      normalizedLookSettings.lighting.directional.position.z
    );

    const fillIntensity = getViewerThemeNumber(viewerTheme, "fillLightIntensity", DEFAULT_LIGHTING.fillLightIntensity);
    runtime.fillLight.visible = fillIntensity > 0.0001;
    runtime.fillLight.color.set(getViewerThemeValue(viewerTheme, "fillLightColor", DEFAULT_LIGHTING.fillLightColor));
    runtime.fillLight.intensity = Math.max(fillIntensity, 0);

    const rimIntensity = getViewerThemeNumber(viewerTheme, "rimLightIntensity", DEFAULT_LIGHTING.rimLightIntensity);
    runtime.rimLight.visible = rimIntensity > 0.0001;
    runtime.rimLight.color.set(getViewerThemeValue(viewerTheme, "rimLightColor", DEFAULT_LIGHTING.rimLightColor));
    runtime.rimLight.intensity = Math.max(rimIntensity, 0);

    runtime.spotLight.visible = normalizedLookSettings.lighting.spot.enabled;
    runtime.spotLight.color.set(normalizedLookSettings.lighting.spot.color);
    runtime.spotLight.intensity = normalizedLookSettings.lighting.spot.intensity;
    runtime.spotLight.angle = normalizedLookSettings.lighting.spot.angle;
    runtime.spotLight.distance = normalizedLookSettings.lighting.spot.distance;
    runtime.spotLight.position.set(
      normalizedLookSettings.lighting.spot.position.x,
      normalizedLookSettings.lighting.spot.position.y,
      normalizedLookSettings.lighting.spot.position.z
    );
    updateSpotLightTarget(runtime);

    runtime.pointLight.visible = normalizedLookSettings.lighting.point.enabled;
    runtime.pointLight.color.set(normalizedLookSettings.lighting.point.color);
    runtime.pointLight.intensity = normalizedLookSettings.lighting.point.intensity;
    runtime.pointLight.distance = normalizedLookSettings.lighting.point.distance;
    runtime.pointLight.position.set(
      normalizedLookSettings.lighting.point.position.x,
      normalizedLookSettings.lighting.point.position.y,
      normalizedLookSettings.lighting.point.position.z
    );

    // Keep a single primary shadow; the spot light drives the floor glow/fill.
    runtime.keyLight.castShadow = runtime.keyLight.visible;
    runtime.spotLight.castShadow = false;

    const materialSettings = {
      ...normalizedLookSettings.materials,
      envMapIntensity: normalizedLookSettings.materials.envMapIntensity * (
        normalizedLookSettings.environment.enabled ? normalizedLookSettings.environment.intensity : 0
      )
    };
    for (const record of runtime.displayRecords || []) {
      applyMaterialSettingsToRecord(runtime.THREE, record, materialSettings);
    }

    runtime.gridConfig = null;
    updateGridHelper(
      runtime,
      viewerTheme,
      runtime.gridRadius ?? defaultGridRadius,
      runtime.gridFloorY ?? 0,
      normalizedSceneScaleMode,
      resolvedFloorMode
    );
    updateSpotLightTarget(runtime);
    if (runtime.hasVisibleModel) {
      updateStageEffects(
        runtime,
        viewerTheme,
        normalizedLookSettings,
        runtime.gridRadius ?? defaultGridRadius,
        runtime.gridFloorY ?? 0,
        resolvedFloorMode
      );
    } else {
      clearSceneGroup(runtime.stageGroup);
    }
    runtime.requestRender();
  }, [defaultGridRadius, normalizedLookSettings, normalizedSceneScaleMode, resolvedFloorMode, viewerReadyTick, viewerTheme]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.scene) {
      return;
    }

    let cancelled = false;
    const environmentSettings = normalizedLookSettings.environment;
    const clearEnvironmentTexture = () => {
      runtime.scene.environment = null;
      disposeTexture(runtime.environmentTexture);
      runtime.environmentTexture = null;
      runtime.environmentTextureUrl = "";
    };
    const applyBackgroundFallback = () => {
      clearEnvironmentTexture();
      applySceneBackground(runtime, viewerTheme, normalizedLookSettings.background);
      runtime.requestRender();
    };

    const loadAndApplyEnvironment = async () => {
      if (!environmentSettings.enabled) {
        viewerAlertChangeRef.current?.(null);
        applyBackgroundFallback();
        return;
      }

      const preset = getEnvironmentPresetById(environmentSettings.presetId);
      const textureUrl = String(preset?.url || "").trim();
      if (!textureUrl) {
        viewerAlertChangeRef.current?.(null);
        applyBackgroundFallback();
        return;
      }

      if (!runtime.environmentTexture || runtime.environmentTextureUrl !== textureUrl) {
        const textureLoader = new runtime.THREE.TextureLoader();
        if (typeof textureLoader.setCrossOrigin === "function") {
          textureLoader.setCrossOrigin("anonymous");
        }
        const nextTexture = await textureLoader.loadAsync(textureUrl);
        if (cancelled) {
          nextTexture.dispose?.();
          return;
        }
        nextTexture.mapping = runtime.THREE.EquirectangularReflectionMapping;
        nextTexture.colorSpace = runtime.THREE.SRGBColorSpace;
        nextTexture.needsUpdate = true;
        disposeTexture(runtime.environmentTexture);
        runtime.environmentTexture = nextTexture;
        runtime.environmentTextureUrl = textureUrl;
      }

      runtime.scene.environment = runtime.environmentTexture;
      viewerAlertChangeRef.current?.(null);

      if (runtime.scene.environmentRotation?.set) {
        runtime.scene.environmentRotation.set(0, environmentSettings.rotationY, 0);
      }
      if (environmentSettings.useAsBackground) {
        runtime.scene.background = runtime.environmentTexture;
        if (runtime.scene.backgroundRotation?.set) {
          runtime.scene.backgroundRotation.set(0, environmentSettings.rotationY, 0);
        }
      } else {
        applySceneBackground(runtime, viewerTheme, normalizedLookSettings.background);
      }
      runtime.requestRender();
    };

    loadAndApplyEnvironment().catch((error) => {
      if (!cancelled) {
        applyBackgroundFallback();
        viewerAlertChangeRef.current?.({
          severity: "warning",
          summary: "Environment unavailable",
          title: "Environment preset could not be loaded",
          message: `Failed to load ${String(getEnvironmentPresetById(environmentSettings.presetId)?.label || "the selected environment preset")}.`,
          resolution: "The viewer fell back to the current background settings. Check the network connection or choose another preset."
        });
        console.error("Failed to apply environment texture", error);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [viewerReadyTick, viewerTheme, normalizedLookSettings.background, normalizedLookSettings.environment]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }

    if (runtime.interactionState.restoreTimerId) {
      window.clearTimeout(runtime.interactionState.restoreTimerId);
      runtime.interactionState.restoreTimerId = 0;
    }
    clearKeyboardOrbitState(runtime.keyboardOrbitState);
    runtime.previewOrbitEnabled = !!previewMode;
    runtime.controls.autoRotate = !!previewMode;
    runtime.controls.autoRotateSpeed = PREVIEW_AUTO_ROTATE_SPEED;
    runtime.controls.enabled = true;
    runtime.controls.enableDamping = true;
    runtime.controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
    runtime.interactionState.active = !!previewMode;
    if (previewMode) {
      cancelCameraTransition(runtime, { scheduleIdle: false });
    } else {
      runtime.scheduleIdleQuality();
    }
    runtime.requestRender();
  }, [previewMode, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }

    const {
      THREE,
      modelGroup,
      edgesGroup,
      facePickGroup,
      edgePickGroup
    } = runtime;

    const clearDisplayedModel = () => {
      cancelCameraTransition(runtime);
      clearSceneGroup(runtime.stageGroup);
      clearSceneGroup(modelGroup);
      clearSceneGroup(edgesGroup);
      clearSceneGroup(facePickGroup);
      clearSceneGroup(edgePickGroup);
      runtime.facePickMesh = null;
      runtime.edgePickLines = null;
      runtime.edgePickObjects = [];
      runtime.displayRecords = [];
      runtime.hasVisibleModel = false;
      runtime.requestRender();
    };

    if (isLoading) {
      clearDisplayedModel();
      setError("");
      return;
    }

    if (!meshData || !isNumericArray(meshData.vertices, 3) || !isNumericArray(meshData.indices, 3)) {
      clearDisplayedModel();
      return;
    }

    clearDisplayedModel();

    const { camera, controls } = runtime;
    const displayRecords = [];
    const shouldRenderParts =
      renderPartsIndividually ||
      Array.isArray(pickableParts) &&
      pickableParts.length > 0 &&
      (
        pickMode === VIEWER_PICK_MODE.PARTS ||
        pickMode === VIEWER_PICK_MODE.ASSEMBLY ||
        pickMode === VIEWER_PICK_MODE.AUTO ||
        !!String(focusedPartId || "").trim()
      );
    const renderedParts = renderPartsIndividually
      ? (Array.isArray(meshData?.parts) ? meshData.parts : [])
      : pickableParts;
    const useVertexColors = shouldUseDisplayVertexColors(meshData);
    const materialSettings = {
      ...normalizedLookSettings.materials,
      envMapIntensity: normalizedLookSettings.materials.envMapIntensity * (
        normalizedLookSettings.environment.enabled ? normalizedLookSettings.environment.intensity : 0
      )
    };

    if (shouldRenderParts) {
      for (const part of renderedParts) {
        const geometry = buildPartGeometry(THREE, meshData, part, recomputeNormals, normalizedLookSettings.materials);
        if (!geometry) {
          continue;
        }
        const hasVertexColors = !!geometry.getAttribute("color");
        const sourceColor = readSourceColor(THREE, part?.color);
        const usePartVertexColors = hasVertexColors;
        const baseColor = resolveSourceBaseColor(THREE, {
          hasVertexColors,
          sourceColor,
          materialSettings: normalizedLookSettings.materials,
          fallbackColor: normalizedLookSettings.materials.defaultColor || viewerTheme?.surface || BASE_VIEWER_THEME.surface
        });
        const material = createSurfaceMaterial(THREE, viewerTheme, {
          color: baseColor,
          useVertexColors: usePartVertexColors
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        mesh.userData.partId = part.id;
        const displayPartTransform = renderPartsIndividually ? part?.transform : null;
        applyPartTransform(THREE, mesh, displayPartTransform);
        modelGroup.add(mesh);

        let edgeMaterial = null;
        let edgeMesh = null;
        if (edgesVisible) {
          const edgeResult = createDisplayEdgeObject(
            runtime,
            buildPartEdgeGeometry(THREE, meshData, part, geometry),
            viewerTheme,
            normalizedLookSettings.edges,
            part.id
          );
          edgeMaterial = edgeResult.edgeMaterial;
          edgeMesh = edgeResult.edgeMesh;
          if (edgeMesh) {
            applyPartTransform(THREE, edgeMesh, displayPartTransform);
            edgesGroup.add(edgeMesh);
          }
        }

        displayRecords.push({
          partId: part.id,
          mesh,
          edges: edgeMesh,
          material,
          edgeMaterial,
          baseColor,
          sourceColor,
          baseTransform: displayPartTransform,
          introOpacity: 1,
          introProgress: 1,
          introOrder: Math.max(Math.round(Number(part?.introOrder) || 0), 0),
          partCenter: readBoundsCenter(THREE, part.bounds),
          partBounds: part.bounds,
          hasVertexColors,
          useVertexColors: usePartVertexColors
        });
      }
    } else {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(meshData.vertices), 3));
      geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(meshData.indices), 1));
      if (useVertexColors && meshData.colors.length === meshData.vertices.length) {
        geometry.setAttribute("color", new THREE.BufferAttribute(shapeSourceColorBuffer(THREE, meshData.colors, normalizedLookSettings.materials), 3));
      }
      applyGeometryNormals(THREE, geometry, meshData.normals, recomputeNormals);
      geometry.computeBoundingSphere();

      const hasVertexColors = useVertexColors;
      const sourceColor = readSourceColor(THREE, meshData?.sourceColor);
      const useModelVertexColors = hasVertexColors;
      const baseColor = resolveSourceBaseColor(THREE, {
        hasVertexColors,
        sourceColor,
        materialSettings: normalizedLookSettings.materials,
        fallbackColor: normalizedLookSettings.materials.defaultColor || viewerTheme?.surface || BASE_VIEWER_THEME.surface
      });
      const material = createSurfaceMaterial(THREE, viewerTheme, {
        color: baseColor,
        useVertexColors: useModelVertexColors
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.userData.partId = "__model__";
      modelGroup.add(mesh);

      let edgeMaterial = null;
      let edgeMesh = null;
      if (edgesVisible) {
        const edgeResult = createDisplayEdgeObject(
          runtime,
          buildEdgeGeometry(THREE, meshData, geometry),
          viewerTheme,
          normalizedLookSettings.edges,
          "__model__"
        );
        edgeMaterial = edgeResult.edgeMaterial;
        edgeMesh = edgeResult.edgeMesh;
        if (edgeMesh) {
          edgesGroup.add(edgeMesh);
        }
      }

      displayRecords.push({
        partId: "__model__",
        mesh,
        edges: edgeMesh,
        material,
        edgeMaterial,
        baseColor,
        sourceColor,
        baseTransform: null,
        introOpacity: 1,
        introProgress: 1,
        introOrder: 0,
        partCenter: readBoundsCenter(THREE, meshData.bounds),
        partBounds: meshData.bounds,
        hasVertexColors,
        useVertexColors: useModelVertexColors
      });
    }

    runtime.displayRecords = displayRecords;
    for (const record of runtime.displayRecords) {
      applyMaterialSettingsToRecord(THREE, record, materialSettings);
      applyDisplayRecordTransform(THREE, record, runtime.modelRadius || 1);
    }
    runtime.hasVisibleModel = true;

    const boundsMin = Array.isArray(meshData.bounds?.min) ? meshData.bounds.min : [0, 0, 0];
    const boundsMax = Array.isArray(meshData.bounds?.max) ? meshData.bounds.max : [0, 0, 0];
    const center = new THREE.Vector3(
      (toNumber(boundsMin[0]) + toNumber(boundsMax[0])) / 2,
      (toNumber(boundsMin[1]) + toNumber(boundsMax[1])) / 2,
      (toNumber(boundsMin[2]) + toNumber(boundsMax[2])) / 2
    );
    const { radius } = applyRuntimeModelBounds(THREE, runtime, meshData.bounds, normalizedSceneScaleMode);
    updateGridHelper(
      runtime,
      viewerTheme,
      radius,
      toNumber(boundsMin[1]) - center.y,
      normalizedSceneScaleMode,
      resolvedFloorMode
    );
    updateSpotLightTarget(runtime);
    updateStageEffects(runtime, viewerTheme, normalizedLookSettings, radius, runtime.gridFloorY ?? 0, resolvedFloorMode);

    const previousTransform = modelTransformRef.current;
    if (previousTransform.modelKey !== modelKey || !previousTransform.offset) {
      previousTransform.modelKey = modelKey || "";
      previousTransform.offset = new THREE.Vector3(-center.x, -center.y, -center.z);
    }
    modelGroup.position.copy(previousTransform.offset);
    edgesGroup.position.copy(previousTransform.offset);
    facePickGroup.position.copy(previousTransform.offset);
    edgePickGroup.position.copy(previousTransform.offset);
    facePickGroup.updateMatrixWorld(true);
    edgePickGroup.updateMatrixWorld(true);

    applyPartVisualState(THREE, displayRecords, {
      viewerTheme,
      edgeSettings: normalizedLookSettings.edges,
      hiddenPartIds: shouldRenderParts ? hiddenPartIds : [],
      hoveredPartId: shouldRenderParts ? hoveredPartId : "",
      focusedPartId: shouldRenderParts ? focusedPartId : "",
      selectedPartIds: shouldRenderParts ? selectedPartIds : [],
      showEdges: edgesVisible
    });
    modelGroup.updateMatrixWorld(true);
    edgesGroup.updateMatrixWorld(true);

    camera.near = Math.max(radius / 1200, 0.01);
    camera.far = Math.max(radius * 600, 2000);
    camera.updateProjectionMatrix();
    applyCameraFrameInsets(runtime, viewportFrameInsetsRef.current, { updateProjection: false });
    controls.minDistance = Math.max(radius / 2200, 0.02);
    controls.maxDistance = Math.max(radius * 140, 50);
    controls.zoomSpeed = DEFAULT_ZOOM_SPEED;
    runtime.edgePickThreshold = Math.max(radius / 320, 0.65);

    if (framedModelKeyRef.current !== (modelKey || "")) {
      const nextPerspective = resolvePerspectiveSnapshot(
        perspectiveRef ? perspectiveRef.current : undefined,
        perspective
      );
      const nextPerspectiveMatchesScene = perspectiveSnapshotMatchesScene(nextPerspective, {
        modelKey,
        sceneScaleMode: normalizedSceneScaleMode
      });
      runWithoutPerspectiveEvents(() => {
        if (
          !nextPerspectiveMatchesScene ||
          !applyPerspectiveSnapshot(runtime, nextPerspective, { scheduleIdle: false })
        ) {
          cancelCameraTransition(runtime);
          const frameMetrics = getViewportFrameMetrics(runtime, viewportFrameInsetsRef.current);
          const fitDistance = getFitDistanceForBoundingSphere(camera, radius, normalizedSceneScaleMode, frameMetrics.aspect);
          const viewDirection = new THREE.Vector3(...DEFAULT_VIEW_DIRECTION).normalize();
          camera.position.copy(viewDirection.multiplyScalar(fitDistance));
          controls.target.set(0, 0, 0);
          controls.update();
          runtime.requestRender();
        }
      });
      framedModelKeyRef.current = modelKey || "";
      lastEmittedPerspectiveRef.current = readScopedPerspectiveSnapshot(runtime, {
        modelKey,
        sceneScaleMode: normalizedSceneScaleMode
      });
    }

    setError("");
    runtime.requestRender();
  }, [
    meshData,
    modelKey,
    perspective,
    perspectiveRef,
    edgesVisible,
    recomputeNormals,
    isLoading,
    viewerReadyTick,
    pickMode,
    renderPartsIndividually,
    pickableParts,
    focusedPartId,
    normalizedSceneScaleMode,
    resolvedFloorMode,
    viewerTheme,
    normalizedLookSettings.materials,
    normalizedLookSettings.edges
  ]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (
      !runtime?.THREE ||
      isLoading ||
      !renderPartsIndividually ||
      !Array.isArray(meshData?.parts) ||
      !Array.isArray(runtime.displayRecords) ||
      !runtime.displayRecords.length
    ) {
      return;
    }

    const partsById = new Map(
      meshData.parts.map((part) => [String(part?.id || ""), part]).filter(([partId]) => partId)
    );
    let updated = false;
    for (const record of runtime.displayRecords) {
      const part = partsById.get(String(record?.partId || ""));
      if (!part) {
        continue;
      }
      record.baseTransform = part.transform;
      record.partBounds = part.bounds;
      record.partCenter = readBoundsCenter(runtime.THREE, part.bounds);
      record.introOrder = Math.max(Math.round(Number(part?.introOrder) || 0), 0);
      applyDisplayRecordTransform(runtime.THREE, record, runtime.modelRadius || 1);
      updated = true;
    }

    if (!updated) {
      return;
    }

    applyRuntimeModelBounds(runtime.THREE, runtime, meshData.bounds, normalizedSceneScaleMode);
    runtime.requestRender();
  }, [
    meshData?.parts,
    meshData?.bounds,
    isLoading,
    renderPartsIndividually,
    normalizedSceneScaleMode,
    viewerReadyTick
  ]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }

    applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
    runtime.requestRender();
  }, [viewerReadyTick, partVisualStateEnabled, edgesVisible, focusedPartId, hiddenPartIds, hoveredPartId, pickMode, pickableParts, selectedPartIds, viewerTheme, normalizedLookSettings.edges]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (
      !runtime?.THREE ||
      isLoading ||
      !renderPartsIndividually ||
      !Array.isArray(runtime.displayRecords) ||
      !runtime.displayRecords.length
    ) {
      return;
    }

    const animationEnabled = partIntroAnimation?.enabled !== false;
    const introKey = String(partIntroAnimation?.introKey || "").trim();
    const replayToken = Math.max(Number(partIntroAnimation?.replayToken) || 0, 0);
    const playbackKey = replayToken ? `${introKey}:replay:${replayToken}` : introKey;
    const stopAnimation = () => {
      if (partIntroStateRef.current.frameId && typeof cancelAnimationFrame === "function") {
        cancelAnimationFrame(partIntroStateRef.current.frameId);
      }
      partIntroStateRef.current.frameId = 0;
    };
    const snapToVisible = () => {
      for (const record of runtime.displayRecords) {
        record.introProgress = 1;
        record.introOpacity = 1;
        applyDisplayRecordTransform(runtime.THREE, record, runtime.modelRadius || 1);
      }
      applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
      runtime.requestRender();
    };

    stopAnimation();

    if (!introKey) {
      partIntroStateRef.current.playedIntroKey = "";
      snapToVisible();
      return stopAnimation;
    }

    if (!animationEnabled && !replayToken) {
      partIntroStateRef.current.playedIntroKey = playbackKey;
      snapToVisible();
      return stopAnimation;
    }

    if (partIntroStateRef.current.playedIntroKey === playbackKey) {
      snapToVisible();
      return stopAnimation;
    }

    partIntroStateRef.current.playedIntroKey = playbackKey;
    const startTime = typeof performance !== "undefined" && typeof performance.now === "function"
      ? performance.now()
      : Date.now();

    for (const record of runtime.displayRecords) {
      record.introProgress = 0;
      record.introOpacity = 0;
      applyDisplayRecordTransform(runtime.THREE, record, runtime.modelRadius || 1);
    }
    applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
    runtime.requestRender();

    const stepIntro = (timestamp) => {
      let hasPendingRecords = false;
      for (const record of runtime.displayRecords) {
        const introOrder = Math.max(Math.round(Number(record?.introOrder) || 0), 0);
        const delayMs = introOrder * URDF_PART_INTRO_STAGGER_MS;
        const progress = clamp((timestamp - startTime - delayMs) / URDF_PART_INTRO_DURATION_MS, 0, 1);
        record.introProgress = progress;
        record.introOpacity = easeOutCubic(clamp(progress / 0.6, 0, 1));
        applyDisplayRecordTransform(runtime.THREE, record, runtime.modelRadius || 1);
        if (progress < 0.999) {
          hasPendingRecords = true;
        }
      }

      applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
      runtime.requestRender();

      if (hasPendingRecords && typeof requestAnimationFrame === "function") {
        partIntroStateRef.current.frameId = requestAnimationFrame(stepIntro);
        return;
      }

      partIntroStateRef.current.frameId = 0;
      snapToVisible();
    };

    if (typeof requestAnimationFrame === "function") {
      partIntroStateRef.current.frameId = requestAnimationFrame(stepIntro);
    } else {
      snapToVisible();
    }

    return stopAnimation;
  }, [
    isLoading,
    renderPartsIndividually,
    viewerReadyTick,
    partIntroAnimation?.enabled,
    partIntroAnimation?.introKey,
    partIntroAnimation?.replayToken
  ]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgePickGroup || !runtime?.facePickGroup || !runtime?.vertexPickGroup) {
      return;
    }

    clearSceneGroup(runtime.facePickGroup);
    clearSceneGroup(runtime.edgePickGroup);
    clearSceneGroup(runtime.vertexPickGroup);
    runtime.facePickMesh = null;
    runtime.edgePickLines = null;
    runtime.vertexPickPoints = null;
    runtime.edgePickObjects = [];

    const facePickMesh = buildFacePickMesh(runtime.THREE, selectorRuntime);
    if (facePickMesh) {
      runtime.facePickMesh = facePickMesh;
      runtime.facePickGroup.add(facePickMesh);
    }

    const edgePickLines = buildEdgePickLines(runtime.THREE, selectorRuntime);
    if (edgePickLines) {
      runtime.edgePickLines = edgePickLines;
      runtime.edgePickGroup.add(edgePickLines);
      runtime.edgePickObjects = [edgePickLines];
    }

    const vertexPickPoints = buildVertexPickPoints(runtime.THREE, selectorRuntime);
    if (vertexPickPoints) {
      runtime.vertexPickPoints = vertexPickPoints;
      runtime.vertexPickGroup.add(vertexPickPoints);
    }

    if (modelTransformRef.current.offset) {
      runtime.facePickGroup.position.copy(modelTransformRef.current.offset);
      runtime.edgePickGroup.position.copy(modelTransformRef.current.offset);
      runtime.vertexPickGroup.position.copy(modelTransformRef.current.offset);
    } else {
      runtime.facePickGroup.position.set(0, 0, 0);
      runtime.edgePickGroup.position.set(0, 0, 0);
      runtime.vertexPickGroup.position.set(0, 0, 0);
    }
    runtime.facePickGroup.updateMatrixWorld(true);
    runtime.edgePickGroup.updateMatrixWorld(true);
    runtime.vertexPickGroup.updateMatrixWorld(true);
  }, [modelKey, selectorRuntime, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }

    const { THREE, edgesGroup } = runtime;
    if (!runtime.surfaceLineGroup || runtime.surfaceLineGroup.parent !== edgesGroup) {
      runtime.surfaceLineGroup = new THREE.Group();
      runtime.surfaceLineGroup.renderOrder = 21;
      edgesGroup.add(runtime.surfaceLineGroup);
    }
    const lineGroup = runtime.surfaceLineGroup;
    clearOverlayGroup(runtime, lineGroup);

    const surfaceLineStrokes = (Array.isArray(drawingStrokes) ? drawingStrokes : []).filter(isSurfaceLineStroke);
    if (!surfaceLineStrokes.length) {
      return () => {
        clearOverlayGroup(runtime, lineGroup);
      };
    }

    const lineWidth = Math.max(getEdgeThickness(normalizedLookSettings.edges, viewerTheme) * 1.6, 1.8);
    const lineOffset = Math.max(runtime.modelRadius || 0, 1) * 0.0008 + 0.02;
    for (const stroke of surfaceLineStrokes) {
      const surfaceLine = stroke?.surfaceLine;
      const referenceId = String(surfaceLine?.referenceId || "").trim();
      const reference = pickableReferenceMap.get(referenceId) || selectorRuntime?.referenceMap?.get(referenceId) || null;
      if (!reference) {
        continue;
      }
      const linePositions = buildSurfaceLinePositions(reference, surfaceLine, {
        offset: lineOffset
      });
      if (!linePositions.length) {
        continue;
      }
      const line = createScreenSpaceLineSegments(runtime, linePositions, {
        color: SURFACE_LINE_COLOR,
        opacity: 0.98,
        lineWidth,
        renderOrder: 22,
        depthTest: true,
        depthWrite: false
      });
      if (line) {
        lineGroup.add(line);
      }
    }
    lineGroup.visible = lineGroup.children.length > 0;
    runtime.requestRender();

    return () => {
      clearOverlayGroup(runtime, lineGroup);
    };
  }, [drawingStrokes, normalizedLookSettings.edges, pickableReferenceMap, selectorRuntime, viewerReadyTick, viewerTheme]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }

    const { THREE, edgesGroup } = runtime;
    if (!runtime.bendGuideGroup || runtime.bendGuideGroup.parent !== edgesGroup) {
      runtime.bendGuideGroup = new THREE.Group();
      runtime.bendGuideGroup.renderOrder = 15;
      edgesGroup.add(runtime.bendGuideGroup);
    }
    const bendGuideGroup = runtime.bendGuideGroup;
    clearOverlayGroup(runtime, bendGuideGroup);

    if (isLoading || !meshData || !isNumericArray(meshData.guide_line_segments, 6)) {
      return () => {
        clearOverlayGroup(runtime, bendGuideGroup);
      };
    }

    const bendGuideLine = createScreenSpaceLineSegments(runtime, meshData.guide_line_segments, {
      color: BEND_GUIDE_COLOR,
      opacity: 0.98,
      lineWidth: Math.max(getEdgeThickness(normalizedLookSettings.edges, viewerTheme) * BEND_GUIDE_WIDTH_MULTIPLIER, 1.4),
      renderOrder: 16,
      depthTest: false,
      depthWrite: false
    });
    if (bendGuideLine) {
      bendGuideGroup.add(bendGuideLine);
    }
    bendGuideGroup.visible = bendGuideGroup.children.length > 0;
    runtime.requestRender();

    return () => {
      clearOverlayGroup(runtime, bendGuideGroup);
    };
  }, [isLoading, meshData, modelKey, normalizedLookSettings.edges, viewerReadyTick, viewerTheme]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }

    const { THREE, edgesGroup } = runtime;
    if (!runtime.partHighlightGroup || runtime.partHighlightGroup.parent !== edgesGroup) {
      runtime.partHighlightGroup = new THREE.Group();
      runtime.partHighlightGroup.renderOrder = 22;
      edgesGroup.add(runtime.partHighlightGroup);
    }
    const highlightGroup = runtime.partHighlightGroup;
    clearOverlayGroup(runtime, highlightGroup);

    // Assembly hover and selection use material state only. Building outline
    // geometry here is expensive for dense imported components and is not
    // needed until a leaf part is inspected for face/edge picking.
    highlightGroup.visible = false;
    runtime.requestRender();

    return () => {
      clearOverlayGroup(runtime, highlightGroup);
    };
  }, [modelKey, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup || !runtime?.modelGroup) {
      return;
    }

    const { THREE, edgesGroup, modelGroup } = runtime;
    if (!runtime.referenceHighlightGroup || runtime.referenceHighlightGroup.parent !== edgesGroup) {
      runtime.referenceHighlightGroup = new THREE.Group();
      runtime.referenceHighlightGroup.renderOrder = 25;
      edgesGroup.add(runtime.referenceHighlightGroup);
    }
    const highlightGroup = runtime.referenceHighlightGroup;
    if (!runtime.referenceFaceFillGroup || runtime.referenceFaceFillGroup.parent !== modelGroup) {
      runtime.referenceFaceFillGroup = new THREE.Group();
      runtime.referenceFaceFillGroup.renderOrder = 24;
      modelGroup.add(runtime.referenceFaceFillGroup);
    }
    const faceFillGroup = runtime.referenceFaceFillGroup;

    clearOverlayGroup(runtime, highlightGroup);
    clearOverlayGroup(runtime, faceFillGroup);
    const baseEdgeThickness = getEdgeThickness(normalizedLookSettings.edges, viewerTheme);
    const selectedLineWidth = baseEdgeThickness * REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER;
    const hoveredLineWidth = baseEdgeThickness * REFERENCE_HOVER_HIGHLIGHT_WIDTH_MULTIPLIER;

    const seenReferenceIds = new Set();
    const orderedReferenceIds = [];
    for (const referenceId of Array.isArray(selectedReferenceIds) ? selectedReferenceIds : []) {
      const normalizedReferenceId = String(referenceId || "").trim();
      if (!normalizedReferenceId || seenReferenceIds.has(normalizedReferenceId)) {
        continue;
      }
      seenReferenceIds.add(normalizedReferenceId);
      orderedReferenceIds.push(normalizedReferenceId);
    }
    const normalizedHoveredReferenceId = String(hoveredReferenceId || "").trim();
    if (normalizedHoveredReferenceId && !seenReferenceIds.has(normalizedHoveredReferenceId)) {
      orderedReferenceIds.push(normalizedHoveredReferenceId);
    }

    for (const referenceId of orderedReferenceIds) {
      const topologyReference = pickableReferenceMap.get(referenceId) || selectorRuntime?.referenceMap?.get(referenceId) || null;
      if (!topologyReference) {
        continue;
      }
      const selectorType = String(topologyReference?.selectorType || "").trim();
      if (selectorType !== "face" && selectorType !== "edge" && selectorType !== "vertex") {
        continue;
      }

      const isHovered = referenceId === normalizedHoveredReferenceId;
      if (selectorType === "vertex") {
        const marker = buildVertexMarkerMesh(runtime, THREE, topologyReference, {
          color: REFERENCE_CORNER_COLOR,
          opacity: isHovered ? 0.96 : 0.88,
        });
        if (marker) {
          highlightGroup.add(marker);
        }
        continue;
      }

      const highlightColor = isHovered ? REFERENCE_HOVER_COLOR : REFERENCE_SELECTED_COLOR;

      const linePositions = selectorType === "edge"
        ? buildEdgeLinePositionsFromProxy(selectorRuntime, topologyReference)
        : buildFaceBoundaryLinePositions(selectorRuntime, topologyReference);
      if (linePositions?.length) {
        const line = createScreenSpaceLineSegments(runtime, linePositions, {
          color: highlightColor,
          opacity: isHovered ? 1 : 0.98,
          lineWidth: isHovered ? hoveredLineWidth : selectedLineWidth,
          renderOrder: 26,
          depthTest: true,
          depthWrite: false
        });
        if (line) {
          highlightGroup.add(line);
        }
      }

      if (selectorType === "face") {
        const fillGeometry = buildFaceFillGeometryFromProxy(runtime, THREE, selectorRuntime, topologyReference);
        if (fillGeometry) {
          const fillMaterial = new THREE.MeshBasicMaterial({
            color: highlightColor,
            transparent: true,
            opacity: isHovered ? REFERENCE_HOVER_FILL_OPACITY : REFERENCE_SELECTED_FILL_OPACITY,
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
          faceFillGroup.add(fillMesh);
        }
      }
    }

    highlightGroup.visible = highlightGroup.children.length > 0;
    faceFillGroup.visible = faceFillGroup.children.length > 0;
    runtime.requestRender();

    return () => {
      clearOverlayGroup(runtime, highlightGroup);
      clearOverlayGroup(runtime, faceFillGroup);
    };
  }, [hoveredReferenceId, pickableReferenceMap, selectedReferenceIds, selectorRuntime, viewerReadyTick, viewerTheme, normalizedLookSettings.edges]);

  useViewerDrawingOverlay({
    drawingCanvasRef,
    drawingDraftRef,
    drawingStrokesRef,
    drawingChangeRef,
    drawingIdRef,
    drawingEnabled,
    drawingTool,
    meshData,
    previewMode,
    viewerReadyTick,
    renderDrawingOverlay,
    redrawDrawingCanvas,
    buildDrawingPoint,
    distanceToStrokeInPixels,
    strokeLengthInPixels,
    drawingToolNeedsTwoPoints,
    buildFillStrokeAtPoint,
    buildSurfaceLineAnchor: buildSurfaceLineFaceAnchor,
    updateSurfaceLineAnchor: updateSurfaceLineFaceAnchor,
    drawingEraseThresholdPx: DRAWING_ERASE_THRESHOLD_PX,
    drawingMinPointDistancePx: DRAWING_MIN_POINT_DISTANCE_PX,
    drawingMinStrokeLengthPx: DRAWING_MIN_STROKE_LENGTH_PX
  });

  useViewerPicking({
    runtimeRef,
    mountRef: interactionHostRef,
    sceneMountRef: mountRef,
    drawingCanvasRef,
    previewMode,
    pickMode,
    selectorRuntime,
    pickableFaces: filteredPickableFaces,
    pickableEdges: filteredPickableEdges,
    pickableVertices: filteredPickableVertices,
    focusedPartId: focusedPartIdValue,
    onHoverReferenceChange,
    onActivateReference,
    onDoubleActivateReference,
    viewerReadyTick
  });

  return (
    <div ref={interactionHostRef} className="relative h-full w-full">
      <div className="h-full w-full" ref={mountRef} />
      <canvas
        ref={drawingCanvasRef}
        className="absolute inset-0 z-10 h-full w-full touch-none"
        style={{
          pointerEvents: drawingEnabled && !previewMode && !!meshData ? "auto" : "none",
          cursor: drawingEnabled && !previewMode && !!meshData
            ? (drawingTool === DRAWING_TOOL.ERASE ? "cell" : drawingTool === DRAWING_TOOL.FILL ? "copy" : "crosshair")
            : "default"
        }}
        aria-hidden="true"
      />
      <ViewPlaneControl
        showViewPlane={showViewPlane}
        previewMode={previewMode}
        isLoading={isLoading}
        meshData={meshData}
        viewPlaneOffsetRight={viewPlaneOffsetRight}
        viewPlaneOffsetBottom={viewPlaneOffsetBottom}
        compact={compactViewPlane}
        activeViewPlaneFace={activeViewPlaneFace}
        viewPlaneFaces={VIEW_PLANE_FACES}
        viewPlaneOrientation={viewPlaneOrientation}
        viewerTheme={viewerTheme}
        activateViewPlaneFace={activateViewPlaneFace}
        activateDefaultViewPlane={activateDefaultViewPlane}
      />
      {!previewMode && !isLoading && measurementSummary ? (
        <div className="cad-glass-popover pointer-events-none absolute bottom-4 left-4 z-20 max-w-[min(24rem,calc(100vw-2rem))] rounded-[10px] border border-white/10 px-3 py-2 text-[11px] leading-5 text-popover-foreground shadow-[var(--ui-shadow-soft)]">
          <p className="font-semibold uppercase tracking-[0.16em] text-muted-foreground">Dimensions</p>
          <p className="mt-1 font-medium text-foreground">Model XYZ</p>
          <p className="font-mono text-muted-foreground">{measurementSummary.model.mmText}</p>
          <p className="font-mono text-muted-foreground">{measurementSummary.model.inchText}</p>
          {measurementSummary.part ? (
            <div className="mt-2 border-t border-white/10 pt-2">
              <p className="truncate font-medium text-foreground" title={measurementSummary.part.label}>
                {measurementSummary.part.label}
              </p>
              <p className="font-mono text-muted-foreground">{measurementSummary.part.measurement.mmText}</p>
              <p className="font-mono text-muted-foreground">{measurementSummary.part.measurement.inchText}</p>
            </div>
          ) : measurementSummary.partCount > 1 ? (
            <p className="mt-2 text-muted-foreground">Select or hover a part for part dimensions.</p>
          ) : null}
        </div>
      ) : null}
      {error ? (
        <p className="cad-glass-popover pointer-events-none absolute left-4 top-24 z-20 rounded-[10px] border border-[var(--ui-error-bg)] px-4 py-3 text-sm text-[var(--ui-error-text)] shadow-[var(--ui-shadow-soft)] sm:top-20">
          {error}
        </p>
      ) : null}
    </div>
  );
});

export default CadViewer;
