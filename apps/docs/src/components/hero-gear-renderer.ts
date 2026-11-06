import * as THREE from "three";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { renderModel } from "@cad/core/common/renderModel.js";
import {
  createGlbAnimationRuntime,
  disposeGlbAnimationRuntime,
  setGlbAnimationTime,
} from "@cad/core/lib/render/glbAnimationRuntime.js";
import { buildGlbDocumentFromBuffer, disposeGlbDocument } from "@cad/core/lib/render/glbMeshData.js";

// The hero's backdrop: the planetary gear as one GLB, exported from the model's document by
// `cad model export` (apps/docs/README.md): its parts and the `meshCycle` motion, which the export
// baked into a clip. The page reads it the way the CAD Viewer reads any GLB
// (`buildGlbDocumentFromBuffer`) and plays the clip the way the viewer does (`glbAnimationRuntime`):
// no gear math of the site's own. It is drawn as a technical drawing with its hidden lines removed:
// each part's folds and outline in one faint ink, its faces only hiding what is behind them.
const HERO_GLB_URL = "/hero/planetary.glb";
const HERO_CLIP = "meshCycle";
// The clip drives the sun 1260 degrees and the carrier one full turn; slowed so the planets take 75
// seconds to go round, a background's pace.
const CLIP_SPEED = 0.08;
// A fold drawn as an edge: above the 28.5 degrees between a mesh's neighbouring facets on a
// cylinder, so a bore draws its rims and no lines down its wall.
const EDGE_CREASE_DEG = 35;
// The folds' width in CSS pixels, and the outline around each part (its back faces pushed out along
// their normals) in millimetres of the model, so a silhouette is heavier than a fold and grows with
// the gear, as a drawing's do.
const FOLD_PX = 1;
const OUTLINE_MM = 0.5;

// Where the gear sits: in the backdrop's bottom-right corner, its centre on the corner, so the right
// edge and the agents under the backdrop cut it to the quarter that turns towards the text. Seen from
// above at 45 degrees. Its ring's radius is a share of the backdrop's height, which leaves the text
// the upper left; on a narrow screen a share of its width instead, so a phone shows the corner arc
// behind the lower half; and never so large that the ring's outline reaches the text's corners
// (`setClearance`), with a little room to spare.
const VIEW: [number, number, number] = [0.8, -1, 1.2];
const RING_RADIUS = { ofHeight: 0.815, ofWidth: 0.9, clearing: 0.96, min: 240 };

/** A point the ring keeps clear of, in CSS pixels from the backdrop's top-left corner. */
export type GearClearance = { x: number; y: number };

export type GearInk = { fold: string; outline: string };

export type HeroGear = {
  /** Moves the clip on by `seconds` of page time. */
  advance(seconds: number): void;
  render(): void;
  setInk(ink: GearInk): void;
  /** The points the ring keeps clear of, as the text lays out; places the gear again and draws. */
  setClearance(points: GearClearance[]): void;
  dispose(): void;
};

type GlbDocument = Awaited<ReturnType<typeof buildGlbDocumentFromBuffer>>;

// An outline material: back faces pushed out along their normals, drawn flat; the faces in front
// hide all of it but the rim past a part's edge.
function outlineMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      color: { value: new THREE.Color() },
      offset: { value: 0 },
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
      void main() {
        gl_FragColor = vec4(color, 1.0);
        #include <colorspace_fragment>
      }
    `,
    side: THREE.BackSide,
  });
}

/** Loads the gear and draws it into `canvas`, which fills `host`; draws nothing until `render`. */
export async function createHeroGear({
  canvas,
  host,
  ink,
  maxPixelRatio,
}: {
  canvas: HTMLCanvasElement;
  host: HTMLElement;
  ink: GearInk;
  maxPixelRatio: number;
}): Promise<HeroGear> {
  const response = await fetch(HERO_GLB_URL);
  if (!response.ok) {
    throw new Error(`${HERO_GLB_URL}: HTTP ${response.status}`);
  }
  const glb: GlbDocument = await buildGlbDocumentFromBuffer(await response.arrayBuffer(), {});
  const clips = (glb.clips ?? []) as THREE.AnimationClip[];
  const clip = clips.find((candidate) => candidate.name === HERO_CLIP) ?? clips[0] ?? null;
  const animation = clip ? createGlbAnimationRuntime(THREE, glb.scene, clip) : null;

  const placed = new THREE.Group();
  placed.matrix.fromArray(glb.cadRootMatrix);
  placed.matrixAutoUpdate = false;
  placed.add(glb.scene);
  const root = new THREE.Group();
  root.add(placed);

  // In CAD space (millimetres, Z up): the ring's radius. The rest pose's box: `meshCycle` turns the
  // parts inside the fixed ring and never lifts them, while the animated box also covers the file's
  // other clip, an explode along the axis.
  const bounds = glb.restBounds ?? { min: [0, 0, 0], max: [1, 1, 1] };
  const radius = Math.max(bounds.max[0] - bounds.min[0], bounds.max[1] - bounds.min[1]) / 2;

  const folds = new LineMaterial({ linewidth: FOLD_PX });
  const outline = outlineMaterial();
  // The faces write depth and no colour, so a line behind a face is hidden; the offset keeps the
  // folds on the faces they bound.
  const faces = new THREE.MeshBasicMaterial({
    colorWrite: false,
    polygonOffset: true,
    polygonOffsetFactor: 1,
    polygonOffsetUnits: 1,
  });
  const lineGeometries: LineSegmentsGeometry[] = [];
  const meshes: THREE.Mesh[] = [];
  glb.scene.traverse((object: THREE.Object3D) => {
    if ((object as THREE.Mesh).isMesh) meshes.push(object as THREE.Mesh);
  });
  // Three passes: every part's faces first, into the depth buffer, then the outlines, then the
  // folds, each hidden where a face covers it.
  for (const mesh of meshes) {
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      material.dispose();
    }
    mesh.material = faces;
    const contour = new THREE.Mesh(mesh.geometry, outline);
    contour.renderOrder = 1;
    mesh.add(contour);
    const edges = new THREE.EdgesGeometry(mesh.geometry, EDGE_CREASE_DEG);
    const lines = new LineSegmentsGeometry().fromEdgesGeometry(edges);
    edges.dispose();
    lineGeometries.push(lines);
    const drawn = new LineSegments2(lines, folds);
    drawn.renderOrder = 2;
    mesh.add(drawn);
  }

  const setInk = (next: GearInk) => {
    folds.color.set(next.fold);
    (outline.uniforms.color.value as THREE.Color).set(next.outline);
  };
  setInk(ink);

  let clipTime = 0;
  if (animation) setGlbAnimationTime(animation, clipTime);

  const viewport = renderModel(
    THREE,
    {
      root,
      bounds,
      runtime: {
        // Device pixels, as `renderModel` gives them on every resize.
        syncScreenSpaceLineMaterials(width: number, height: number) {
          folds.resolution.set(width, height);
        },
      },
      dispose() {
        for (const geometry of lineGeometries) geometry.dispose();
        folds.dispose();
        outline.dispose();
        faces.dispose();
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
      maxPixelRatio,
      powerPreference: "low-power",
      shadows: false,
    }
  );

  // Sizes the drawing buffer to the backdrop (`renderModel`'s resize, whose own framing this
  // replaces), then places the gear as above: an orthographic camera on the gear's centre, at the
  // scale that gives the ring its radius in pixels, its view running from the centre up and to the
  // left, so the centre lands on the backdrop's bottom-right corner.
  const camera = viewport.camera as THREE.OrthographicCamera;
  const center = new THREE.Vector3(
    (bounds.min[0] + bounds.max[0]) / 2,
    (bounds.min[1] + bounds.max[1]) / 2,
    (bounds.min[2] + bounds.max[2]) / 2
  );
  const view = new THREE.Vector3(...VIEW).normalize();
  const distance = radius * 4;
  // How high the ring's outline reaches over its centre, as a share of its radius: the ring seen at
  // the view's tilt, and the parts' top faces above the centre.
  const tilt = Math.asin(view.z);
  const ringTop = Math.sin(tilt) + ((bounds.max[2] - center.z) / radius) * Math.cos(tilt);
  let clearance: GearClearance[] = [];
  const layout = () => {
    viewport.resize();
    const { width, height } = viewport.renderer.getSize(new THREE.Vector2());
    let ringRadius = Math.min(RING_RADIUS.ofHeight * height, RING_RADIUS.ofWidth * width);
    for (const point of clearance) {
      const across = Math.max(width - point.x, 0);
      const up = Math.max(height - point.y, 0);
      ringRadius = Math.min(ringRadius, RING_RADIUS.clearing * Math.hypot(across, up / ringTop));
    }
    ringRadius = Math.max(ringRadius, RING_RADIUS.min);
    const pixelsPerUnit = ringRadius / radius;
    camera.position.copy(center).addScaledVector(view, distance);
    camera.up.set(0, 0, 1);
    camera.lookAt(center);
    camera.left = -width / pixelsPerUnit;
    camera.right = 0;
    camera.top = height / pixelsPerUnit;
    camera.bottom = 0;
    camera.near = distance - radius * 2;
    camera.far = distance + radius * 2;
    camera.updateProjectionMatrix();
    folds.linewidth = FOLD_PX * viewport.renderer.getPixelRatio();
    outline.uniforms.offset.value = OUTLINE_MM;
  };
  layout();
  const resized = new ResizeObserver(() => {
    layout();
    viewport.render();
  });
  resized.observe(host);

  return {
    advance(seconds: number) {
      if (!animation || !clip || clip.duration <= 0) return;
      clipTime = (clipTime + Math.max(seconds, 0) * CLIP_SPEED) % clip.duration;
      setGlbAnimationTime(animation, clipTime);
    },
    render() {
      viewport.render();
    },
    setInk,
    setClearance(points: GearClearance[]) {
      clearance = points;
      layout();
      viewport.render();
    },
    dispose() {
      resized.disconnect();
      disposeGlbAnimationRuntime(animation);
      viewport.dispose();
    },
  };
}
