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
// Line widths in CSS pixels: the folds, and the outline around each part (its back faces pushed out
// along their normals), a little heavier, as a drawing's silhouettes are.
const FOLD_PX = 1;
const OUTLINE_PX = 1.5;

// Where the gear sits: centred behind the hero, its ring around the text. The view tilts with the
// backdrop's shape (width over height) -- low over a wide screen, so the ring is a wide ellipse
// between the header and the agents, steeper on a tall one, so it rounds out above and below the
// text -- and the ring is as wide as that shape asks (a share of the width: past the edges on a
// phone) while its height keeps clear of the backdrop's top and bottom.
const TILT_DEG_BY_ASPECT: [number, number][] = [[0.65, 60], [1, 48], [1.6, 34], [2.25, 27], [2.7, 22]];
const RING_WIDTH_BY_ASPECT: [number, number][] = [[1, 1.3], [1.6, 0.8]];
const RING_FILLS_HEIGHT = 0.86;
const RING_PX = { min: 420, max: 1200 };
// The side the camera looks from, in plan: the planets' best side at the clip's first pose.
const AZIMUTH: [number, number] = [0.41, -0.91];

export type GearInk = { fold: string; outline: string };

export type HeroGear = {
  /** Moves the clip on by `seconds` of page time. */
  advance(seconds: number): void;
  render(): void;
  setInk(ink: GearInk): void;
  dispose(): void;
};

type GlbDocument = Awaited<ReturnType<typeof buildGlbDocumentFromBuffer>>;

// A value from a table of (x, value) rows, straight between rows, held past the ends.
function interpolate(table: [number, number][], x: number) {
  if (x <= table[0][0]) return table[0][1];
  for (let i = 1; i < table.length; i += 1) {
    const [x1, y1] = table[i];
    if (x <= x1) {
      const [x0, y0] = table[i - 1];
      return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0);
    }
  }
  return table[table.length - 1][1];
}

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

  // In CAD space (millimetres, Z up): the ring's radius, and the assembly's depth along its axis. The
  // rest pose's box: `meshCycle` turns the parts inside the fixed ring and never lifts them, while
  // the animated box also covers the file's other clip, an explode along the axis.
  const bounds = glb.restBounds ?? { min: [0, 0, 0], max: [1, 1, 1] };
  const radius = Math.max(bounds.max[0] - bounds.min[0], bounds.max[1] - bounds.min[1]) / 2;
  const depth = bounds.max[2] - bounds.min[2];

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
  // replaces), then frames the gear as above: an orthographic camera on the gear's centre, at the
  // scale that makes the ring `ringWidth` pixels across.
  const camera = viewport.camera as THREE.OrthographicCamera;
  const center = new THREE.Vector3(
    (bounds.min[0] + bounds.max[0]) / 2,
    (bounds.min[1] + bounds.max[1]) / 2,
    (bounds.min[2] + bounds.max[2]) / 2
  );
  const layout = () => {
    viewport.resize();
    const { width, height } = viewport.renderer.getSize(new THREE.Vector2());
    const aspect = width / Math.max(height, 1);
    const tilt = THREE.MathUtils.degToRad(interpolate(TILT_DEG_BY_ASPECT, aspect));
    const sin = Math.sin(tilt);
    const cos = Math.cos(tilt);
    const ringWidth = Math.min(
      Math.max(
        Math.min(
          interpolate(RING_WIDTH_BY_ASPECT, aspect) * width,
          (RING_FILLS_HEIGHT * height) / (sin + (depth / (2 * radius)) * cos)
        ),
        RING_PX.min
      ),
      RING_PX.max
    );
    const pixelsPerUnit = ringWidth / (2 * radius);
    const halfHeight = height / 2 / pixelsPerUnit;
    const distance = radius * 4;
    camera.position.copy(center).addScaledVector(new THREE.Vector3(AZIMUTH[0] * cos, AZIMUTH[1] * cos, sin), distance);
    camera.up.set(0, 0, 1);
    camera.lookAt(center);
    camera.top = halfHeight;
    camera.bottom = -halfHeight;
    camera.left = -halfHeight * aspect;
    camera.right = halfHeight * aspect;
    camera.near = distance - radius * 2;
    camera.far = distance + radius * 2;
    camera.updateProjectionMatrix();
    folds.linewidth = FOLD_PX * viewport.renderer.getPixelRatio();
    outline.uniforms.offset.value = OUTLINE_PX / pixelsPerUnit;
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
    dispose() {
      resized.disconnect();
      disposeGlbAnimationRuntime(animation);
      viewport.dispose();
    },
  };
}
