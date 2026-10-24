"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { CAD_SCENE_SCALE } from "@text-to-cad/core/common/cadScene.js";
import { renderModel } from "@text-to-cad/core/common/renderModel.js";
import { cloneThemePresetSettings } from "@text-to-cad/core/common/themeSettings.js";
import {
  createGlbAnimationRuntime,
  disposeGlbAnimationRuntime,
  setGlbAnimationTime,
} from "@text-to-cad/core/lib/render/glbAnimationRuntime.js";
import { buildGlbDocumentFromBuffer, disposeGlbDocument } from "@text-to-cad/core/lib/render/glbMeshData.js";

// The hero plays the planetary gear as one GLB, exported from the model's document by
// `cadgen export` (scripts/sync-hero-glb.mjs): its parts, colours and the `meshCycle` motion,
// which the export baked into a clip. The page reads it the way the CAD Viewer reads any GLB
// (`buildGlbDocumentFromBuffer`) and plays the clip the way the viewer does
// (`glbAnimationRuntime`): no gear math of the site's own.
const HERO_GLB_URL = "/hero/planetary.glb";
const HERO_LABEL = "PLANETARY_GEAR_ASSEMBLY.GLB";
const HERO_CLIP = "meshCycle";
// The mesh cycle covers 1260 degrees of drive in one nominal pass; slowed so
// the hero turns at a display pace rather than a demo pace.
const HERO_CLIP_SPEED = 0.14;
// A fold drawn as an edge: above the 28.5 degrees between a mesh's neighbouring facets on a
// cylinder, so a bore draws its rims and no lines down its wall.
const EDGE_CREASE_DEG = 35;
const EDGE_OPACITY = 0.84;
// The outline around each part, as the CAD scene draws one: its back faces pushed out along their
// normals by this share of the model's radius, in the edge colour, behind the part.
const SILHOUETTE_SCALE = 0.004;
const SILHOUETTE_OPACITY = 0.9;

type PreviewScheme = "dark" | "light";
type HeroGlbDocument = Awaited<ReturnType<typeof buildGlbDocumentFromBuffer>>;

const GLB_PREVIEW_PALETTES = {
  dark: {
    background: "#292929",
    border: "#414141",
    edge: "#202b38",
    headerBackground: "#303030",
    headerText: "#d4d4d4",
    keyLight: "#f6f8fb",
    keyLightIntensity: 2.5,
    fillLight: "#7f95ad",
    fillLightIntensity: 0.8,
    ambientLight: "#eef4fa",
    ambientLightIntensity: 1.85,
  },
  light: {
    background: "#fafafa",
    border: "#e5e5e5",
    edge: "#2f3a4b",
    headerBackground: "#ffffff",
    headerText: "#737373",
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

// The viewport's lighting and backdrop: the workbench theme, lit for this page.
function buildWorkbenchTheme(scheme: PreviewScheme) {
  const palette = GLB_PREVIEW_PALETTES[scheme];
  const theme = cloneThemePresetSettings("workbench-light");

  return {
    ...theme,
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

// An outline material: back faces pushed out along their normals, drawn flat behind the part.
function silhouetteMaterial(color: string, offset: number) {
  return new THREE.ShaderMaterial({
    uniforms: {
      color: { value: new THREE.Color(color) },
      opacity: { value: SILHOUETTE_OPACITY },
      offset: { value: offset },
    },
    vertexShader: `
      uniform float offset;
      void main() {
        vec3 displaced = position + normal * offset;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 color;
      uniform float opacity;
      void main() {
        gl_FragColor = vec4(color, opacity);
      }
    `,
    side: THREE.BackSide,
    transparent: true,
    depthTest: true,
    depthWrite: false,
  });
}

// The GLB's scene as a model `renderModel` frames and draws: placed in CAD space (millimetres, Z
// up) by the document's own matrix, each part's colour kept on the matte workbench finish, and each
// part's folds and outline drawn in the edge colour, riding with it as the clip moves it.
function buildHeroModel(glb: HeroGlbDocument, scheme: PreviewScheme) {
  const placed = new THREE.Group();
  placed.matrix.fromArray(glb.cadRootMatrix);
  placed.matrixAutoUpdate = false;
  placed.add(glb.scene);
  const root = new THREE.Group();
  root.add(placed);

  const bounds = glb.animatedBounds ?? glb.restBounds ?? { min: [0, 0, 0], max: [1, 1, 1] };
  const radius = new THREE.Vector3(...bounds.max).sub(new THREE.Vector3(...bounds.min)).length() / 2;
  const edgeColor = GLB_PREVIEW_PALETTES[scheme].edge;
  const edgeMaterial = new LineMaterial({
    color: edgeColor,
    linewidth: 1,
    transparent: true,
    opacity: EDGE_OPACITY,
  });
  const outlineMaterial = silhouetteMaterial(edgeColor, radius * SILHOUETTE_SCALE);
  const edgeGeometries: LineSegmentsGeometry[] = [];
  const meshes: THREE.Mesh[] = [];
  glb.scene.traverse((object: THREE.Object3D) => {
    if ((object as THREE.Mesh).isMesh) {
      meshes.push(object as THREE.Mesh);
    }
  });
  for (const mesh of meshes) {
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (material instanceof THREE.MeshStandardMaterial) {
        material.roughness = 0.92;
        material.metalness = 0;
        material.envMapIntensity = 0;
      }
    }
    const folds = new THREE.EdgesGeometry(mesh.geometry, EDGE_CREASE_DEG);
    const lines = new LineSegmentsGeometry().fromEdgesGeometry(folds);
    folds.dispose();
    edgeGeometries.push(lines);
    mesh.add(new LineSegments2(lines, edgeMaterial));
    const outline = new THREE.Mesh(mesh.geometry, outlineMaterial);
    outline.renderOrder = -1;
    mesh.add(outline);
  }

  return {
    root,
    bounds,
    runtime: {
      // Device pixels, as `renderModel` gives them on every resize.
      syncScreenSpaceLineMaterials(width: number, height: number) {
        edgeMaterial.resolution.set(width, height);
      },
    },
    dispose() {
      for (const geometry of edgeGeometries) {
        geometry.dispose();
      }
      edgeMaterial.dispose();
      outlineMaterial.dispose();
      disposeGlbDocument(glb);
    },
  };
}

export function HeroGlbRender() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [scheme, setScheme] = useState<PreviewScheme>("dark");
  const [status, setStatus] = useState("loading");
  const palette = GLB_PREVIEW_PALETTES[scheme];

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
    let heroModel: ReturnType<typeof buildHeroModel> | null = null;
    let viewport: ReturnType<typeof renderModel> | null = null;
    let animation: ReturnType<typeof createGlbAnimationRuntime> = null;
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
      if (disposed || !heroModel) {
        return;
      }
      if (animation && clipDuration > 0) {
        clipElapsedSec =
          (clipElapsedSec + Math.max(deltaSeconds, 0) * HERO_CLIP_SPEED) %
          clipDuration;
        setGlbAnimationTime(animation, clipElapsedSec);
      }

      if (!dragState.active) {
        dragState.yaw += 0.0018;
      }
      heroModel.root.rotation.x = dragState.pitch;
      heroModel.root.rotation.z = dragState.yaw;
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
      let glb: HeroGlbDocument | null = null;
      try {
        setStatus("loading");
        const response = await fetch(HERO_GLB_URL, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`${HERO_GLB_URL}: HTTP ${response.status}`);
        }
        glb = await buildGlbDocumentFromBuffer(await response.arrayBuffer(), {});
        if (disposed) {
          disposeGlbDocument(glb);
          return;
        }
        const clips = (glb.clips ?? []) as THREE.AnimationClip[];
        const clip = clips.find((candidate) => candidate.name === HERO_CLIP) ?? clips[0];
        if (!clip) {
          throw new Error("hero GLB carries no animation clip");
        }
        clipDuration = clip.duration;
        animation = createGlbAnimationRuntime(THREE, glb.scene, clip);

        heroModel = buildHeroModel(glb, scheme);
        glb = null;
        heroModel.root.rotation.x = dragState.pitch;
        heroModel.root.rotation.z = dragState.yaw;
        viewport = renderModel(THREE, heroModel, {
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
        setStatus(HERO_LABEL);
      } catch (error) {
        if (glb) {
          disposeGlbDocument(glb);
        }
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
      disposeGlbAnimationRuntime(animation);
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
          aria-label="3D render of a sample planetary gear assembly, its gears turning"
          className="absolute inset-0 h-full w-full cursor-grab touch-none active:cursor-grabbing"
        />
      </div>
      <div
        className="flex min-h-8 shrink-0 items-center justify-between gap-3 border-t px-3 py-[7px] font-mono text-label leading-none"
        style={{
          backgroundColor: palette.headerBackground,
          borderColor: palette.border,
          color: palette.headerText,
        }}
      >
        <span className="min-w-0 truncate">{status}</span>
      </div>
    </div>
  );
}
