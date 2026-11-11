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

  let clipTime = 0;
  if (animation) setGlbAnimationTime(animation, clipTime);

  const viewport = renderModel(
    THREE,
    { root, bounds, dispose: () => disposeGlbDocument(glb) },
    {
      alpha: true,
      autoRender: false,
      autoResize: false,
      canvas,
      hostElement: host,
      maxPixelRatio: 2,
      padding: 0.08,
      powerPreference: "low-power",
      shadows: false,
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
