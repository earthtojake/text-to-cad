import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { renderModel } from "@cad/core/common/renderModel.js";
import {
  createGlbAnimationRuntime,
  disposeGlbAnimationRuntime,
  setGlbAnimationTime,
} from "@cad/core/lib/render/glbAnimationRuntime.js";
import { buildGlbDocumentFromBuffer, disposeGlbDocument } from "@cad/core/lib/render/glbMeshData.js";

// A model on a page of the documentation: a GLB `cad model export` wrote, read the way the CAD
// Viewer reads any GLB (`buildGlbDocumentFromBuffer`), lit and framed by core's `renderModel`, with
// its parts' own colours, and its clip played by the viewer's GLB animation runtime. Drag turns it;
// the wheel is left to the page.

// The light: enough that a face turned to it shows its part's colour as the file says it, and a
// face turned away a shade of it. three.js lights a matte surface at its colour times the light over
// pi, so core's defaults (an ambient of 0.2 and one light of 1, a viewer's starting point before its
// look sets them) draw every colour at about a third of itself: dull and grey.
const LIGHTING = {
  ambient: { enabled: true, color: "#ffffff", intensity: 0.62 * Math.PI },
  directional: { enabled: true, color: "#ffffff", intensity: 0.5 * Math.PI, position: { x: 120, y: -200, z: 300 } },
};
// Each part's folds, drawn over it in a dark ink: above the angle between a cylinder's neighbouring
// facets, so a bore draws its rims and no lines down its wall (the hero's rule).
const EDGE_CREASE_DEG = 35;
const EDGE_INK = { color: "#1f2933", opacity: 0.45 };

export type ModelEmbedView = {
  /** Moves the clip on by `seconds`. */
  advance(seconds: number): void;
  render(): void;
  dispose(): void;
};

type GlbDocument = Awaited<ReturnType<typeof buildGlbDocumentFromBuffer>>;

export async function createModelEmbed({
  canvas,
  host,
  url,
  clipName,
  clipSpeed = 1,
}: {
  canvas: HTMLCanvasElement;
  host: HTMLElement;
  url: string;
  clipName?: string;
  clipSpeed?: number;
}): Promise<ModelEmbedView> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  const glb: GlbDocument = await buildGlbDocumentFromBuffer(await response.arrayBuffer(), {});
  const clips = (glb.clips ?? []) as THREE.AnimationClip[];
  const clip = clips.find((candidate) => candidate.name === clipName) ?? clips[0] ?? null;
  const animation = clip ? createGlbAnimationRuntime(THREE, glb.scene, clip) : null;

  const placed = new THREE.Group();
  placed.matrix.fromArray(glb.cadRootMatrix);
  placed.matrixAutoUpdate = false;
  placed.add(glb.scene);
  const root = new THREE.Group();
  root.add(placed);

  const bounds = glb.restBounds ?? { min: [0, 0, 0], max: [1, 1, 1] };
  const centre = new THREE.Vector3(
    (bounds.min[0] + bounds.max[0]) / 2,
    (bounds.min[1] + bounds.max[1]) / 2,
    (bounds.min[2] + bounds.max[2]) / 2,
  );

  // The folds ride on their parts, so they move with the clip; the faces sit a little behind them.
  const ink = new THREE.LineBasicMaterial({ color: EDGE_INK.color, transparent: true, opacity: EDGE_INK.opacity });
  const folds: THREE.EdgesGeometry[] = [];
  const meshes: THREE.Mesh[] = [];
  glb.scene.traverse((object: THREE.Object3D) => {
    if ((object as THREE.Mesh).isMesh) meshes.push(object as THREE.Mesh);
  });
  for (const mesh of meshes) {
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      material.polygonOffset = true;
      material.polygonOffsetFactor = 1;
      material.polygonOffsetUnits = 1;
    }
    const edges = new THREE.EdgesGeometry(mesh.geometry, EDGE_CREASE_DEG);
    folds.push(edges);
    mesh.add(new THREE.LineSegments(edges, ink));
  }

  let clipTime = 0;
  if (animation) setGlbAnimationTime(animation, clipTime);

  const viewport = renderModel(
    THREE,
    {
      root,
      bounds,
      dispose() {
        for (const edges of folds) edges.dispose();
        ink.dispose();
        disposeGlbDocument(glb);
      },
    },
    {
      alpha: true,
      autoRender: false,
      autoResize: false,
      canvas,
      hostElement: host,
      // A plain depth buffer, so the faces' polygon offset keeps the folds in front of them.
      logarithmicDepthBuffer: false,
      maxPixelRatio: 2,
      padding: 0.08,
      powerPreference: "low-power",
      shadows: false,
      theme: { lighting: LIGHTING },
    },
  );

  const controls = new OrbitControls(viewport.camera as THREE.OrthographicCamera, canvas);
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.addEventListener("change", () => viewport.render());
  // The framing is core's (`renderModel` fits the camera to the model on each resize); the turning
  // starts from it, about the model's centre.
  const frame = () => {
    viewport.resize();
    controls.target.copy(centre);
    controls.update();
  };
  frame();
  const resized = new ResizeObserver(() => {
    frame();
    viewport.render();
  });
  resized.observe(host);

  return {
    advance(seconds: number) {
      if (!animation || !clip || clip.duration <= 0) return;
      clipTime = (clipTime + Math.max(seconds, 0) * clipSpeed) % clip.duration;
      setGlbAnimationTime(animation, clipTime);
    },
    render() {
      viewport.render();
    },
    dispose() {
      resized.disconnect();
      controls.dispose();
      disposeGlbAnimationRuntime(animation);
      viewport.dispose();
    },
  };
}
