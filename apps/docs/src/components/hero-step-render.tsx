"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import {
  animationClipDuration,
  findAnimationClip,
  firstAnimationClipId,
} from "cadgen-js/common/animationClock.js";
import { CAD_SCENE_SCALE, buildModel } from "cadgen-js/common/cadScene.js";
import { loadRenderModule } from "cadgen-js/common/renderModule.js";
import { renderModel } from "cadgen-js/common/renderModel.js";
import {
  loadSource,
  packageSourceFromBaseUrl,
  stepParameterRuntime,
} from "cadgen-js/common/source.js";
import { cloneThemePresetSettings } from "cadgen-js/common/themeSettings.js";

// The hero renders the planetary gear STEP the way every cadgen-js client
// renders a STEP: the model's render package (exact surfaces, tessellated in
// the browser) plus its sidecar (kinematics for the mate graph, copied
// animation clips for choreography). No GLB export, no site-local gear math —
// the same clip the viewer's Animation tab plays drives this scene.
const HERO_PACKAGE_BASE_URL = "/hero/planetary";
const HERO_SIDECAR_URL = "/hero/planetary_gear_assembly.step.json";
// The render module beside the document (<name>.step.js): choreography,
// authored in the model project and synced here as a plain file.
const HERO_RENDER_MODULE_URL = "/hero/planetary_gear_assembly.step.js";
const HERO_STEP_CAD_PATH = "models/assemblies/STEP/planetary_gear_assembly/planetary_gear_assembly.step";
const HERO_STEP_DEMO_URL =
  "https://cad.fun/?file=fun%2Fplanetary_gear_assembly.step";
const HERO_STEP_LABEL = "PLANETARY_GEAR_ASSEMBLY.STEP";
const HERO_CLIP_ID = "meshCycle";
// The mesh cycle covers 1260 degrees of drive in one nominal pass; slowed so
// the hero turns at a display pace rather than a demo pace.
const HERO_CLIP_SPEED = 0.14;

type PreviewScheme = "dark" | "light";
type HeroModel = ReturnType<typeof buildModel>;
type HeroClip = ReturnType<typeof findAnimationClip>;

const STEP_PREVIEW_PALETTES = {
  dark: {
    background: "#111820",
    border: "#3b4553",
    fill: ["#c7d0d8", "#aeb9c3", "#d9dee3", "#8f9ba7"],
    headerBackground: "rgba(17, 24, 32, 0.9)",
    headerText: "#c9d3df",
    keyLight: "#f6f8fb",
    keyLightIntensity: 2.5,
    fillLight: "#7f95ad",
    fillLightIntensity: 0.8,
    ambientLight: "#eef4fa",
    ambientLightIntensity: 1.85,
  },
  light: {
    background: "#eef1f5",
    border: "#c9cfda",
    fill: ["#d7dce0", "#cdd3d8", "#e4e7ea", "#bfc7ce"],
    headerBackground: "rgba(238, 241, 245, 0.9)",
    headerText: "#4c566a",
    keyLight: "#ffffff",
    keyLightIntensity: 2.6,
    fillLight: "#cfd8e3",
    fillLightIntensity: 0.9,
    ambientLight: "#ffffff",
    ambientLightIntensity: 2.2,
  },
} as const;

function currentPreviewScheme(): PreviewScheme {
  if (typeof document === "undefined") {
    return "dark";
  }

  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function buildWorkbenchTheme(scheme: PreviewScheme) {
  const palette = STEP_PREVIEW_PALETTES[scheme];
  const theme = cloneThemePresetSettings("workbench-light");
  const materials =
    theme.materials && typeof theme.materials === "object"
      ? theme.materials
      : {};

  return {
    ...theme,
    materials: {
      ...materials,
      defaultColor: palette.fill[0],
      fillColors: [...palette.fill],
      overrideSourceColors: false,
      saturation: 1,
      contrast: 1,
      brightness: 1,
      tintStrength: 0,
      roughness: 0.92,
      metalness: 0,
      clearcoat: 0,
      envMapIntensity: 0,
    },
    edges: {
      ...(theme.edges || {}),
      enabled: true,
      color: scheme === "dark" ? "#202b38" : "#2f3a4b",
      contrastMode: "manual",
      opacity: 1,
      silhouette: true,
      thickness: 1,
    },
    background: {
      type: "solid",
      solidColor: palette.background,
    },
    lighting: {
      ambient: {
        color: palette.ambientLight,
        enabled: true,
        intensity: palette.ambientLightIntensity,
      },
      directionalLights: [
        {
          color: palette.keyLight,
          enabled: true,
          intensity: palette.keyLightIntensity,
          position: { x: -120, y: 180, z: 240 },
        },
        {
          color: palette.fillLight,
          enabled: true,
          intensity: palette.fillLightIntensity,
          position: { x: 180, y: -120, z: 120 },
        },
      ],
      hemisphere: {
        enabled: false,
      },
    },
  };
}

export function HeroStepRender() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [scheme, setScheme] = useState<PreviewScheme>("dark");
  const [status, setStatus] = useState("loading step");
  const palette = STEP_PREVIEW_PALETTES[scheme];

  useEffect(() => {
    const syncScheme = () => {
      setScheme(currentPreviewScheme());
    };

    syncScheme();

    const observer = new MutationObserver(syncScheme);
    observer.observe(document.documentElement, {
      attributeFilter: ["class"],
      attributes: true,
    });

    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    let disposed = false;
    let cadModel: HeroModel | null = null;
    let viewport: ReturnType<typeof renderModel> | null = null;
    let clip: HeroClip = null;
    let clipDuration = 0;
    let clipElapsedSec = 0;
    const dragState = {
      active: false,
      lastX: 0,
      lastY: 0,
      pitch: 0.18,
      pointerId: -1,
      yaw: -0.18,
    };

    const beforeRender = ({ deltaSeconds }: { deltaSeconds: number }) => {
      if (disposed || !cadModel) {
        return;
      }
      if (clip) {
        clipElapsedSec =
          (clipElapsedSec + Math.max(deltaSeconds, 0) * HERO_CLIP_SPEED) %
          clipDuration;
        cadModel.update({
          callbacks: { animation: { clip, elapsedSec: clipElapsedSec } },
        });
      }

      if (!dragState.active) {
        dragState.yaw += 0.0018;
      }
      cadModel.root.rotation.x = dragState.pitch;
      cadModel.root.rotation.z = dragState.yaw;
    };

    const handlePointerDown = (event: PointerEvent) => {
      dragState.active = true;
      dragState.lastX = event.clientX;
      dragState.lastY = event.clientY;
      dragState.pointerId = event.pointerId;
      canvas.setPointerCapture(event.pointerId);
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (!dragState.active || event.pointerId !== dragState.pointerId) {
        return;
      }

      const dx = event.clientX - dragState.lastX;
      const dy = event.clientY - dragState.lastY;
      dragState.lastX = event.clientX;
      dragState.lastY = event.clientY;
      dragState.yaw += dx * 0.008;
      dragState.pitch = Math.max(
        -0.85,
        Math.min(0.85, dragState.pitch + dy * 0.006)
      );
    };

    const handlePointerEnd = (event: PointerEvent) => {
      if (event.pointerId !== dragState.pointerId) {
        return;
      }

      dragState.active = false;
      dragState.pointerId = -1;
      if (canvas.hasPointerCapture(event.pointerId)) {
        canvas.releasePointerCapture(event.pointerId);
      }
    };

    const load = async () => {
      try {
        setStatus("loading step");
        // The tree's descriptor and the render module beside the document load
        // in parallel; the clips come through the same loader the viewer uses
        // (kinematics and animation stay independent end to end).
        const [descriptor, renderModule] = await Promise.all([
          fetch(`${HERO_PACKAGE_BASE_URL}/assembly.json`, {
            cache: "no-store",
          }).then((response) => {
            if (!response.ok) {
              throw new Error(`hero package descriptor: HTTP ${response.status}`);
            }
            return response.json();
          }),
          loadRenderModule(HERO_RENDER_MODULE_URL),
        ]);
        const source = await loadSource({
          ...packageSourceFromBaseUrl(HERO_PACKAGE_BASE_URL, descriptor),
          stepParameterUrl: HERO_SIDECAR_URL,
          cadPath: HERO_STEP_CAD_PATH,
        });
        const clips = renderModule?.clips ?? {};
        if (disposed) {
          return;
        }
        clip =
          findAnimationClip(clips, HERO_CLIP_ID) ??
          findAnimationClip(clips, firstAnimationClipId(clips));
        if (!clip) {
          throw new Error("hero render module declares no animation clips");
        }
        clipDuration = animationClipDuration(clip);

        cadModel = buildModel(THREE, source, {
          theme: buildWorkbenchTheme(scheme),
          displayMode: "solid",
          stepParameters: stepParameterRuntime(source.stepParameterSource),
          scale: CAD_SCENE_SCALE.CAD,
          selection: {
            showEdges: true,
          },
          edgeRendering: {
            mode: "screen-space",
            Line2,
            LineGeometry,
            LineMaterial,
            LineSegments2,
            LineSegmentsGeometry,
          },
        });
        cadModel.root.rotation.x = dragState.pitch;
        cadModel.root.rotation.z = dragState.yaw;
        viewport = renderModel(THREE, cadModel, {
          autoStart: true,
          beforeRender,
          canvas,
          direction: [1, -1, 0.65],
          hostElement: viewportRef.current ?? canvas,
          lockedHalfHeightScale: 0.86,
          padding: 0.1,
          scale: CAD_SCENE_SCALE.CAD,
          theme: buildWorkbenchTheme(scheme),
        });
        setStatus(HERO_STEP_LABEL);
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "render failed");
      }
    };

    canvas.addEventListener("pointerdown", handlePointerDown);
    canvas.addEventListener("pointermove", handlePointerMove);
    canvas.addEventListener("pointerup", handlePointerEnd);
    canvas.addEventListener("pointercancel", handlePointerEnd);
    void load();

    return () => {
      disposed = true;
      canvas.removeEventListener("pointerdown", handlePointerDown);
      canvas.removeEventListener("pointermove", handlePointerMove);
      canvas.removeEventListener("pointerup", handlePointerEnd);
      canvas.removeEventListener("pointercancel", handlePointerEnd);
      viewport?.dispose();
    };
  }, [palette, scheme]);

  return (
    <div
      className="flex h-full min-h-0 flex-col overflow-hidden"
      style={{ backgroundColor: palette.background }}
    >
      <div ref={viewportRef} className="relative min-h-0 flex-1 overflow-hidden">
        <canvas
          ref={canvasRef}
          aria-label="Light 3D render of a sample STEP planetary gear assembly"
          className="absolute inset-0 h-full w-full cursor-grab touch-none active:cursor-grabbing"
        />
      </div>
      <div
        className="flex min-h-8 shrink-0 items-center justify-between gap-3 border-t px-3 py-[7px] text-label uppercase leading-none tracking-[1.5px]"
        style={{
          backgroundColor: palette.headerBackground,
          borderColor: palette.border,
          color: palette.headerText,
        }}
      >
        {status === HERO_STEP_LABEL ? (
          <a
            className="min-w-0 truncate transition hover:text-primary"
            href={HERO_STEP_DEMO_URL}
            target="_blank"
            rel="noreferrer"
            title="Open planetary gear assembly in the text-to-cad demo"
          >
            {status}
          </a>
        ) : (
          <span className="min-w-0 truncate">{status}</span>
        )}
      </div>
    </div>
  );
}
