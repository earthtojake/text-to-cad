/**
 * A board in 3D, its stage: the bare board as a kit scene (`lib/viewer/sceneContract.js`) — a slab cut
 * to the outline and as thick as the board, lit, and on its two faces the 2D drawer's pictures of the
 * two sides (`boardFaces.js`), unlit, so a face reads exactly as the 2D view does. Over each face a
 * see-through overlay carries the highlight and the ink.
 *
 * Its frame is `boardFrame.js`'s: the front face at z = 0, the back at z = -thickness. It knows the
 * board's index only to pick: a ray meets the face it enters, the sheet point there inside the
 * outline is handed to `locate`'s caller, and what a pick there MEANS (the 2D view's own
 * `index.pick`, with its filter and its layers) is the view's (`pickAt`). Holes are not cut: a hole
 * reads as one because the 2D drawer paints it in the canvas colour.
 *
 * three.js is passed in; nothing here touches the document but through `createCanvas`.
 *
 * Importing this module has no environmental effects.
 */
import { BOARD_THICKNESS_MM, faceZ, rayOnBoard } from "./boardFrame.js";
import { FACE_PIXELS, createFaceRasters, faceUv } from "./boardFaces.js";
import { pointInPolygon } from "../board2d/geometry.js";

// How far a face's picture and its overlay stand off the slab, so neither fights it for depth.
const FACE_LIFT_MM = 0.01;
const OVERLAY_LIFT_MM = 0.02;
// The slab's edge: FR4's tan, darker on the dark canvas.
const EDGE_COLORS = Object.freeze({ dark: 0x6f6240, light: 0xb9a66a });

const area = ring => ring.reduce((sum, [x, y], index) => { const [nx, ny] = ring[(index + 1) % ring.length]; return sum + x * ny - nx * y; }, 0) / 2;

/**
 * The outline's rings on the page: the largest the board, those inside it its cut-outs.
 * @returns {{ outer: [number, number][], holes: [number, number][][] } | null}
 */
export function outlineRings(outline, sheet) {
  const dx = sheet.x || 0, dy = sheet.y || 0;
  const rings = (outline || []).map(ring => ring.map(([x, y]) => [x + dx, y + dy]))
    .map(ring => (ring.length > 1 && ring[0][0] === ring.at(-1)[0] && ring[0][1] === ring.at(-1)[1] ? ring.slice(0, -1) : ring))
    .filter(ring => ring.length >= 3);
  if (!rings.length) {
    const w = sheet.width, h = sheet.height;
    return { outer: [[dx, dy], [dx + w, dy], [dx + w, dy + h], [dx, dy + h]], holes: [] };
  }
  rings.sort((a, b) => Math.abs(area(b)) - Math.abs(area(a)));
  const [outer, ...rest] = rings;
  return { outer, holes: rest.filter(ring => pointInPolygon(ring[0], outer)) };
}

/**
 * @param {typeof import("three")} THREE
 * @param {{ layout: object, outline: number[][][] | null, thickness?: number, theme: "light" | "dark",
 *   createCanvas?: () => HTMLCanvasElement, pickAt?: (located: { side: string, page: number[], point: number[], distance: number }) => object | null }} options
 *   `outline`: the board's outline as the payload carries it (`board.outline`, page millimetres);
 *   `pickAt`: what a located point picks, the view's (null: nothing).
 */
export function createBoardStage(THREE, { layout, outline, thickness = BOARD_THICKNESS_MM, theme = "dark", createCanvas, pickAt = null }) {
  const sheet = layout.sheets[0];
  const rings = outlineRings(outline, sheet);
  const toShape = (ring, Kind) => new Kind(ring.map(([x, y]) => new THREE.Vector2(x, -y)));
  const shape = toShape(rings.outer, THREE.Shape);
  shape.holes = rings.holes.map(ring => toShape(ring, THREE.Path));

  const group = new THREE.Group();
  group.name = "board";
  const slabGeometry = new THREE.ExtrudeGeometry(shape, { depth: thickness, bevelEnabled: false, curveSegments: 8 });
  const slabMaterial = new THREE.MeshStandardMaterial({ color: EDGE_COLORS[theme] ?? EDGE_COLORS.dark, roughness: 0.85, metalness: 0 });
  const slab = new THREE.Mesh(slabGeometry, slabMaterial);
  slab.position.z = -thickness;
  group.add(slab);

  // A face: the outline's triangles, each vertex at its sheet point on the side's raster.
  const faceGeometry = side => {
    const geometry = new THREE.ShapeGeometry(shape, 8);
    const position = geometry.getAttribute("position"), uv = geometry.getAttribute("uv");
    for (let index = 0; index < position.count; index += 1) {
      const [u, v] = faceUv([position.getX(index), -position.getY(index)], sheet, side);
      uv.setXY(index, u, v);
    }
    return geometry;
  };
  const geometries = { top: faceGeometry("top"), bottom: faceGeometry("bottom") };
  // A face's picture is the canvas's pixels as they are: its bytes are sampled, filtered, mipmapped and
  // blended as the 2D canvas composites them (in sRGB, not decoded to linear light and encoded back,
  // which lightens every fine dark line a smaller mip averages in), and put on screen unconverted.
  const texture = () => {
    const made = new THREE.Texture();
    made.colorSpace = THREE.NoColorSpace;
    made.generateMipmaps = true;
    made.minFilter = THREE.LinearMipmapLinearFilter;
    made.magFilter = THREE.LinearFilter;
    return made;
  };
  const asDrawn = shader => { shader.fragmentShader = shader.fragmentShader.replace("#include <colorspace_fragment>", ""); };
  const layer = (side, lift, transparent) => {
    const material = new THREE.MeshBasicMaterial({ map: texture(), toneMapped: false, transparent, depthWrite: !transparent,
      side: side === "bottom" ? THREE.BackSide : THREE.FrontSide });
    material.onBeforeCompile = asDrawn;
    material.customProgramCacheKey = () => "board-face-as-drawn";
    const mesh = new THREE.Mesh(geometries[side], material);
    mesh.position.z = side === "bottom" ? faceZ(side, thickness) - lift : lift;
    mesh.visible = false;
    if (transparent) mesh.renderOrder = 1;
    group.add(mesh);
    return mesh;
  };
  const faces = { top: layer("top", FACE_LIFT_MM, false), bottom: layer("bottom", FACE_LIFT_MM, false) };
  const overlays = { top: layer("top", OVERLAY_LIFT_MM, true), bottom: layer("bottom", OVERLAY_LIFT_MM, true) };

  let renderer = null;
  const maxSize = () => Math.max(1024, Number(renderer?.capabilities?.maxTextureSize) || 4096);
  let rasters = null;
  let software = false;
  const rastersNow = () => (rasters ||= createFaceRasters({ layout, sheet, createCanvas, maxSize: maxSize(), maxPixels: software ? FACE_PIXELS / 4 : FACE_PIXELS }));
  // What each face shows: its Display drawn (by key), or not yet.
  let look = null;
  const drawnKey = { top: "", bottom: "" };
  const wanted = { top: true, bottom: false };
  let overlayPaint = null, overlayScale = 1;
  const timings = { face: 0 };

  // A scratch canvas into a face's texture, uploaded now: the next draw reuses the canvas.
  const uploaded = new Set();
  const upload = (mesh, canvas) => {
    const map = mesh.material.map;
    uploaded.add(mesh);
    map.anisotropy = Math.min(8, Number(renderer.capabilities?.getMaxAnisotropy?.()) || 1);
    map.image = canvas;
    map.needsUpdate = true;
    renderer.initTexture(map);
  };
  const drawFace = side => {
    if (!renderer || !look || !wanted[side]) return false;
    const key = look.key;
    if (drawnKey[side] === key) return false;
    const started = performance.now();
    upload(faces[side], rastersNow().drawFace(side, look));
    timings.face = performance.now() - started;
    faces[side].visible = true;
    drawnKey[side] = key;
    return true;
  };
  const drawOverlay = side => {
    if (!renderer || !overlayPaint || !faces[side].visible) { overlays[side].visible = false; return; }
    const canvas = rastersNow().drawOverlay(side, overlayPaint, { lineScale: overlayScale });
    if (!canvas) { overlays[side].visible = false; return; }
    upload(overlays[side], canvas);
    overlays[side].visible = true;
  };

  const minX = Math.min(...rings.outer.map(p => p[0])), maxX = Math.max(...rings.outer.map(p => p[0]));
  const minY = Math.min(...rings.outer.map(p => p[1])), maxY = Math.max(...rings.outer.map(p => p[1]));
  const bounds = Object.freeze({ min: [minX, 0 - maxY, -thickness], max: [maxX, 0 - minY, 0] });

  /** Where a ray meets the board, inside its outline (not in a cut-out); null off it. */
  const locate = ray => {
    const located = rayOnBoard({ origin: ray.origin.toArray(), direction: ray.direction.toArray() }, thickness);
    if (!located || !pointInPolygon(located.page, rings.outer) || rings.holes.some(ring => pointInPolygon(located.page, ring))) return null;
    return located;
  };

  return {
    object3D: group,
    bounds,
    thickness,
    sheet,
    locate,
    /** The kit's pick: what the view's `pickAt` makes of the point the ray meets, with its world point. */
    pick(ray) {
      const located = locate(ray);
      const hit = located && pickAt ? pickAt(located) : null;
      return hit ? { ...hit, id: hit.selector, point: new THREE.Vector3(...located.point) } : null;
    },
    /**
     * The WebGL renderer the faces are uploaded through (the viewport's; a new one after a lost context).
     * On a software renderer (`softwareRendering`) a face takes a quarter of the budget.
     */
    setRenderer(next, { softwareRendering = false } = {}) {
      if (renderer === next) return;
      renderer = next;
      software = softwareRendering;
      drawnKey.top = drawnKey.bottom = "";
      uploaded.clear();
      rasters?.dispose();
      rasters = null;
      drawFace("top"); drawFace("bottom");
      drawOverlay("top"); drawOverlay("bottom");
    },
    /**
     * What the faces draw: the Display and the theme, as the 2D view draws them at `lineScale` pixels a
     * millimetre (`boardFaces.js`). A change redraws the faces drawn, the back only once it has been seen;
     * a change of side alone redraws nothing.
     */
    setLook({ display, theme: scheme, lineScale = 0 }) {
      const { side, ...rest } = display;
      look = { display, theme: scheme, lineScale, key: JSON.stringify([rest, scheme, Math.round(lineScale * 100)]) };
      slabMaterial.color.setHex(EDGE_COLORS[scheme] ?? EDGE_COLORS.dark);
      const top = drawFace("top"), bottom = drawFace("bottom");
      if (top) drawOverlay("top");
      if (bottom) drawOverlay("bottom");
      return top || bottom;
    },
    /** The camera has seen `side`: its face is drawn from now on. */
    see(side) {
      if (wanted[side]) return false;
      wanted[side] = true;
      const drew = drawFace(side);
      if (drew) drawOverlay(side);
      return drew;
    },
    /**
     * The overlay, drawn again on both faces: `paint(ctx, frame)` in page millimetres (`boardFaces.js`),
     * its lines `lineScale` pixels a millimetre thick as the screen shows them.
     */
    setOverlay(paint, { lineScale = 1 } = {}) {
      overlayPaint = paint;
      overlayScale = lineScale;
      drawOverlay("top"); drawOverlay("bottom");
    },
    /** What the stage holds: the pixels of its face textures and of its scratch canvases, and its last face's draw. */
    stats() {
      const size = raster => (rasters ? rasters[raster].width * rasters[raster].height : 0);
      const sides = ["top", "bottom"];
      return {
        texturePixels: sides.reduce((sum, side) => sum + (uploaded.has(faces[side]) ? size("base") : 0) + (uploaded.has(overlays[side]) ? size("overlay") : 0), 0),
        canvasPixels: rasters?.pixels() ?? 0, drawnSides: sides.filter(side => drawnKey[side]), faceMs: timings.face
      };
    },
    dispose() {
      for (const mesh of [...Object.values(faces), ...Object.values(overlays)]) { mesh.material.map.dispose(); mesh.material.dispose(); }
      for (const geometry of Object.values(geometries)) geometry.dispose();
      slabGeometry.dispose();
      slabMaterial.dispose();
      rasters?.dispose();
      rasters = null;
      renderer = null;
    }
  };
}
