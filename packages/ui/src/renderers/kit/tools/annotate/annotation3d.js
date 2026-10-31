import { createScreenSpaceLineStrip } from "@text-to-cad/core/common/renderEdges.js";
import {
  ANNOTATION_RENDER_ORDER, annotationDocument, annotationMarkObject, annotationObjectShown as shown, clipAnnotationObject, disposeAnnotationObject
} from "@text-to-cad/core/common/annotation.js";
import { markPoints } from "../../../../annotation/geometry.js";
import { requestSceneFrame } from "../../viewport/sceneFrames.js";

// The annotation in the model: each mark Annotate puts down (`annotation/geometry.js`), drawn over the view
// as the camera stood then, projected into 3D so it stays where it was drawn from every angle.
// Ink lies on the SURFACE under the pen. Every mark has a LEVEL: the plane of the surface it starts on
// (`levelOf`: a flat face's own plane, a curved face's tangent plane at the start point; over nothing,
// the nearest visible surface's plane). Placement says what a point does on the model: On surface
// drops each point onto the visible surface under it, On plane keeps it on the level plane; off the
// model both carry on at the level. Ink the model hides is drawn faint through it
// (`ANNOTATION_HIDDEN_OPACITY`). Every mark is in model coordinates and stays put, whatever a model
// effect that moves the parts, a pose or hiding a part does to the model; Clip cuts it. The projected ink is plain data
// (`AnnotationItem`), kept across scene rebuilds; `mountAnnotations` draws it in a viewer runtime.

/**
 * A mark as Annotate keeps it: an annotation mark (`@text-to-cad/core/common/annotation.js`, the shape a prompt's
 * annotation file and a snapshot job read), its points a Float32Array.
 * @typedef {import("@text-to-cad/core/common/annotation.js").AnnotationMark & { points: Float32Array }} AnnotationItem
 * @typedef {{ point: import("three").Vector3, normal: import("three").Vector3 }} Level  A mark's level: a plane
 *   through `point` with unit `normal`, in model coordinates.
 */

// What a ray from the view can land on: the model's part meshes, as a pick sees them.
function pickTargets(runtime) {
  const targets = [];
  runtime.modelGroup?.traverse(object => {
    if ((object.isMesh || object.isInstancedMesh) && (object.userData?.partId != null || Array.isArray(object.userData?.partIds))) targets.push(object);
  });
  return targets;
}
const partIdOf = hit => (Array.isArray(hit.object.userData?.partIds) && hit.instanceId != null
  ? hit.object.userData.partIds[hit.instanceId] : hit.object.userData?.partId) ?? null;

// A fill's triangles, split until none has an edge longer than `limit` pixels — every one at once,
// so neighbours never meet at a crack: points inside it for the eraser and Select to find it by.
// The outline's points come first, in order; the rest are inside.
const FILL_SEGMENT_PX = 12;
// A stroke's line is split until no piece is longer than this many pixels, so each piece takes the depth
// under it: a two-point line from the model out into the air lies on the model, then on its level, not at
// the model's depth all along. The pen's widths are split with it.
const STROKE_SEGMENT_PX = 6;
function subdivideStroke(points, widths = null) {
  const out = [points[0]], outWidths = widths ? [widths[0]] : null;
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1], b = points[index];
    const pieces = Math.max(1, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / STROKE_SEGMENT_PX));
    for (let piece = 1; piece <= pieces; piece += 1) {
      const t = piece / pieces;
      out.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
      if (outWidths) outWidths.push(widths[index - 1] + (widths[index] - widths[index - 1]) * t);
    }
  }
  return { points: out, widths: outWidths };
}
function subdivideArea(THREE, outline, limit = FILL_SEGMENT_PX) {
  const points = outline.map(point => ({ x: point.x, y: point.y }));
  let triangles = THREE.ShapeUtils.triangulateShape(outline.map(point => new THREE.Vector2(point.x, point.y)), []);
  const middles = new Map();
  const middle = (a, b) => {
    const key = a < b ? `${a}|${b}` : `${b}|${a}`;
    if (!middles.has(key)) { points.push({ x: (points[a].x + points[b].x) / 2, y: (points[a].y + points[b].y) / 2 }); middles.set(key, points.length - 1); }
    return middles.get(key);
  };
  const long = ([a, b, c]) => Math.max(...[[a, b], [b, c], [c, a]].map(([u, v]) => Math.hypot(points[u].x - points[v].x, points[u].y - points[v].y))) > limit;
  for (let pass = 0; pass < 6 && triangles.some(long); pass += 1) {
    triangles = triangles.flatMap(([a, b, c]) => {
      const ab = middle(a, b), bc = middle(b, c), ca = middle(c, a);
      return [[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]];
    });
  }
  return { points, index: triangles.flat() };
}

// Ink stands off what it lies on, toward the eye, by this many screen pixels: clear of the face
// without leaving it. A text mark on a surface by four times as much.
const LIFT_PX = 2;
// A stroke stands in front of everything within this many pixels of its line, beyond half its width,
// so nothing it was drawn over cuts through it. Small: on a slanted face the ink stands off it by this
// reach times the face's slope, so the less the closer it lies.
const COVER_PX = 1;
// A level met this nearly edge-on by the view (the cosine of the angle) is replaced by the plane facing the
// view; a ray met this nearly edge-on gives no depth worth having: the depth of the level's own point stands in.
const GRAZING = 0.08;

/**
 * The view's geometry for projecting screen points: the eye, the view direction, a screen point's
 * ray and the point at a depth along it, a point's depth, one screen pixel's size at a depth.
 */
function viewOf(runtime, size) {
  const { THREE, camera } = runtime;
  camera.updateMatrixWorld();
  const eye = new THREE.Vector3().setFromMatrixPosition(camera.matrixWorld);
  const view = new THREE.Vector3(); camera.getWorldDirection(view);
  const caster = new THREE.Raycaster(), ndc = new THREE.Vector2();
  const depthOf = point => point.clone().sub(eye).dot(view);
  const ray = ({ x, y }) => {
    ndc.set((x / size.width) * 2 - 1, -(y / size.height) * 2 + 1);
    caster.setFromCamera(ndc, camera);
    return caster.ray.clone();
  };
  const at = (point, depth) => {
    const { origin, direction } = ray(point);
    const along = direction.dot(view);
    const t = Math.abs(along) < 1e-9 ? 0 : (depth - origin.clone().sub(eye).dot(view)) / along;
    return origin.clone().addScaledVector(direction, t);
  };
  // In front of the eye: a perspective camera draws nothing nearer than its near plane.
  const nearest = camera.isPerspectiveCamera ? camera.near * 2 : -Infinity;
  // One screen pixel's size at a depth.
  const pixel = depth => (camera.isOrthographicCamera
    ? (camera.top - camera.bottom) / (camera.zoom * size.height)
    : 2 * Math.max(depth, camera.near) * Math.tan(THREE.MathUtils.degToRad(camera.getEffectiveFOV()) / 2) / size.height);
  const lifted = (depth, px = LIFT_PX) => Math.max(depth - px * pixel(depth), nearest);
  return { THREE, camera, eye, view, caster, depthOf, ray, at, nearest, pixel, lifted };
}

// The face of the model under a screen point, as a ray from the view meets it: the hit, its point and
// the surface's normal there in world coordinates (the geometry's own smooth normal where it has one,
// else the facet's), turned to face the eye. Null over nothing (or what Clip has cut away).
function faceAt(runtime, targets, point, view) {
  const { THREE } = runtime;
  const planes = Array.isArray(runtime.activeClipPlanes) ? runtime.activeClipPlanes : [];
  const caster = new THREE.Raycaster();
  const ray = view.ray(point);
  caster.ray.copy(ray);
  const hit = caster.intersectObjects(targets, false)
    .find(candidate => shown(candidate.object) && planes.every(plane => plane.distanceToPoint(candidate.point) >= 0) && partIdOf(candidate) != null);
  if (!hit) return null;
  const matrix = hit.object.matrixWorld.clone();
  if (hit.instanceId != null && hit.object.isInstancedMesh) {
    const instance = new THREE.Matrix4();
    hit.object.getMatrixAt(hit.instanceId, instance);
    matrix.multiply(instance);
  }
  let local = hit.face?.normal ? hit.face.normal.clone() : null;
  const attribute = hit.object.geometry?.attributes?.normal;
  if (local && hit.face && attribute && attribute.count > Math.max(hit.face.a, hit.face.b, hit.face.c)) {
    const position = hit.object.geometry.attributes.position;
    const corner = index => new THREE.Vector3().fromBufferAttribute(position, index);
    const at = hit.point.clone().applyMatrix4(matrix.clone().invert());
    const weights = new THREE.Triangle(corner(hit.face.a), corner(hit.face.b), corner(hit.face.c)).getBarycoord(at, new THREE.Vector3());
    if (weights && [weights.x, weights.y, weights.z].every(Number.isFinite)) {
      const smooth = new THREE.Vector3()
        .addScaledVector(new THREE.Vector3().fromBufferAttribute(attribute, hit.face.a), weights.x)
        .addScaledVector(new THREE.Vector3().fromBufferAttribute(attribute, hit.face.b), weights.y)
        .addScaledVector(new THREE.Vector3().fromBufferAttribute(attribute, hit.face.c), weights.z);
      // Only where it agrees with the facet: a mesh with a stray normal never turns a level.
      if (smooth.lengthSq() > 1e-12 && smooth.normalize().dot(local) > 0.5) local = smooth;
    }
  }
  const normal = (local ?? new THREE.Vector3(0, 0, 1)).applyMatrix3(new THREE.Matrix3().getNormalMatrix(matrix)).normalize();
  if (normal.dot(ray.direction) > 0) normal.negate();
  return { hit, point: hit.point.clone(), normal };
}

// The parts' depth shader: each pixel's depth along the view — the parts as the view shows them,
// clipped as they are. Alpha says where a part is drawn.
const SURFACE_VERTEX = `#include <common>
#include <clipping_planes_pars_vertex>
varying float vInkDepth;
void main() {
#include <begin_vertex>
#include <project_vertex>
#include <clipping_planes_vertex>
  vInkDepth = -mvPosition.z;
}`;
const SURFACE_FRAGMENT = `#include <clipping_planes_pars_fragment>
varying float vInkDepth;
void main() {
#include <clipping_planes_fragment>
  gl_FragColor = vec4(vInkDepth, 0.0, 0.0, 1.0);
}`;
// One per renderer, kept: a material disposed with each stroke would take its program with it.
const surfaceMaterials = new WeakMap();

const canRenderSurface = renderer => Boolean(renderer?.readRenderTargetPixels && renderer.capabilities?.isWebGL2 && renderer.extensions?.has?.("EXT_color_buffer_float"));

// The parts' depth over `box` (CSS pixels of the viewport, `size`; it may reach past the viewport) in
// one render of the parts alone, `res` pixels across it, read back: `null` where the renderer cannot
// draw to floats.
function renderSurface(runtime, targets, box, size, res) {
  const { THREE, renderer, scene, camera } = runtime;
  if (!canRenderSurface(renderer)) return null;
  let material = surfaceMaterials.get(renderer);
  if (!material) {
    material = new THREE.ShaderMaterial({ vertexShader: SURFACE_VERTEX, fragmentShader: SURFACE_FRAGMENT, side: THREE.DoubleSide, clipping: true });
    surfaceMaterials.set(renderer, material);
  }
  const parts = new Set(targets);
  material.clippingPlanes = Array.isArray(runtime.activeClipPlanes) && runtime.activeClipPlanes.length ? runtime.activeClipPlanes : null;
  const target = new THREE.WebGLRenderTarget(res.w, res.h, { type: THREE.FloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter });
  // Only the parts are drawn: the rest of the scene (edges, ink, the floor, caps) steps aside.
  const hidden = [];
  scene.traverse(object => {
    if (object.visible && (object.isMesh || object.isLine || object.isPoints || object.isSprite) && !parts.has(object)) { object.visible = false; hidden.push(object); }
  });
  const kept = { background: scene.background, fog: scene.fog, overrideMaterial: scene.overrideMaterial, onBeforeRender: scene.onBeforeRender, onAfterRender: scene.onAfterRender };
  const renderTarget = renderer.getRenderTarget(), clearColor = renderer.getClearColor(new THREE.Color()), clearAlpha = renderer.getClearAlpha();
  const shadows = renderer.shadowMap.autoUpdate, xr = renderer.xr?.enabled === true;
  const view = camera.view?.enabled ? { ...camera.view } : null;
  const pixels = new Float32Array(res.w * res.h * 4);
  try {
    Object.assign(scene, { background: null, fog: null, overrideMaterial: material, onBeforeRender() {}, onAfterRender() {} });
    renderer.shadowMap.autoUpdate = false;
    if (renderer.xr) renderer.xr.enabled = false;
    camera.setViewOffset(size.width, size.height, box.x, box.y, box.w, box.h);
    camera.updateProjectionMatrix();
    renderer.setRenderTarget(target);
    renderer.setClearColor(0x000000, 0);
    renderer.clear();
    renderer.render(scene, camera);
    renderer.readRenderTargetPixels(target, 0, 0, res.w, res.h, pixels);
  } finally {
    if (view) camera.setViewOffset(view.fullWidth, view.fullHeight, view.offsetX, view.offsetY, view.width, view.height);
    else camera.clearViewOffset();
    camera.updateProjectionMatrix();
    renderer.setRenderTarget(renderTarget);
    renderer.setClearColor(clearColor, clearAlpha);
    renderer.shadowMap.autoUpdate = shadows;
    if (renderer.xr) renderer.xr.enabled = xr;
    Object.assign(scene, kept);
    for (const object of hidden) object.visible = true;
    target.dispose();
  }
  // Read back bottom row first: turned the screen's way up.
  const depth = new Float32Array(res.w * res.h).fill(Infinity);
  for (let row = 0; row < res.h; row += 1) {
    for (let column = 0; column < res.w; column += 1) {
      const from = ((res.h - 1 - row) * res.w + column) * 4;
      if (pixels[from + 3] > 0) depth[row * res.w + column] = pixels[from];
    }
  }
  return depth;
}

// The same, without a GPU: a ray through each pixel's centre.
function castSurface(runtime, targets, box, size, res, depthOf) {
  const { THREE, camera } = runtime;
  const caster = new THREE.Raycaster(), ndc = new THREE.Vector2();
  const planes = Array.isArray(runtime.activeClipPlanes) ? runtime.activeClipPlanes : [];
  const depth = new Float32Array(res.w * res.h).fill(Infinity);
  for (let row = 0; row < res.h; row += 1) {
    for (let column = 0; column < res.w; column += 1) {
      ndc.set(((box.x + (column + 0.5) * box.w / res.w) / size.width) * 2 - 1, -((box.y + (row + 0.5) * box.h / res.h) / size.height) * 2 + 1);
      caster.setFromCamera(ndc, camera);
      const hit = caster.intersectObjects(targets, false)
        .find(candidate => shown(candidate.object) && planes.every(plane => plane.distanceToPoint(candidate.point) >= 0) && partIdOf(candidate) != null);
      if (hit) depth[row * res.w + column] = depthOf(hit.point);
    }
  }
  return depth;
}

// What the view shows of the parts over `box` (CSS pixels of the viewport, which it may reach past),
// drawn into at most `budget` pixels on its long side: every pixel's depth along the view (Infinity:
// no part drawn there) and where each pixel's middle falls on the screen.
function depthMap(runtime, targets, box, size, budget, view) {
  const scale = Math.min(1, budget / Math.max(box.w, box.h));
  const res = { w: Math.max(1, Math.round(box.w * scale)), h: Math.max(1, Math.round(box.h * scale)) };
  const depth = renderSurface(runtime, targets, box, size, res) ?? castSurface(runtime, targets, box, size, res, view.depthOf);
  return { depth, res, box, middle: (column, row) => ({ x: box.x + (column + 0.5) * box.w / res.w, y: box.y + (row + 0.5) * box.h / res.h }) };
}

// What the view shows of the parts around a set of screen points, a pixel to a pixel: the nearest
// depth along a stretch of the screen.
function surfaceUnder(runtime, targets, points, pad, size, view) {
  let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
  for (const { x, y } of points) { left = Math.min(left, x); top = Math.min(top, y); right = Math.max(right, x); bottom = Math.max(bottom, y); }
  const x = Math.max(0, Math.floor(left - pad)), y = Math.max(0, Math.floor(top - pad));
  const box = { x, y, w: Math.min(Math.ceil(size.width), Math.ceil(right + pad) + 1) - x, h: Math.min(Math.ceil(size.height), Math.ceil(bottom + pad) + 1) - y };
  if (!(box.w > 0) || !(box.h > 0) || !targets.length) return { nearest: () => Infinity };
  const { depth, res } = depthMap(runtime, targets, box, size, Math.max(box.w, box.h), view);
  const cell = (px, py) => {
    const column = Math.floor(px) - box.x, row = Math.floor(py) - box.y;
    return column < 0 || row < 0 || column >= res.w || row >= res.h ? -1 : row * res.w + column;
  };
  return {
    // The nearest depth within `radius` pixels of the line from `a` to `b` (Infinity: nothing there).
    nearest(a, b, radius) {
      let best = Infinity;
      const steps = Math.max(1, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y)));
      const reach = Math.ceil(radius);
      for (let step = 0; step <= steps; step += 1) {
        const cx = a.x + (b.x - a.x) * step / steps, cy = a.y + (b.y - a.y) * step / steps;
        for (let dy = -reach; dy <= reach; dy += 1) {
          for (let dx = -reach; dx <= reach; dx += 1) {
            const at = cell(cx + dx, cy + dy);
            if (at >= 0 && depth[at] < best) best = depth[at];
          }
        }
      }
      return best;
    },
  };
}

// The depth maps behind a level are read at most this many pixels across: a coarse look, not a pick.
// Without a GPU, where each pixel is a ray through the model, far fewer.
const LOOK_BUDGET_PX = 256;
const LOOK_CPU_BUDGET_PX = 64;

// The box (world) of the parts the view draws, or null without any.
function drawnBox(runtime, targets) {
  const { THREE } = runtime;
  const box = new THREE.Box3();
  for (const target of targets) {
    if (!shown(target)) continue;
    target.updateWorldMatrix(true, false);
    box.union(new THREE.Box3().setFromObject(target));
  }
  return box.isEmpty() ? null : box;
}

// The drawn pixel of a depth map least far from `start` on the screen (the nearer of two as far), searched
// outward from where `start` falls in rings of cells; null where the map has no part drawn.
function nearestCovered(map, start) {
  const { depth, res, box, middle } = map;
  const column0 = Math.min(res.w - 1, Math.max(0, Math.floor((start.x - box.x) / (box.w / res.w))));
  const row0 = Math.min(res.h - 1, Math.max(0, Math.floor((start.y - box.y) / (box.h / res.h))));
  const cell = Math.min(box.w / res.w, box.h / res.h);
  let best = null;
  const visit = (column, row) => {
    if (column < 0 || row < 0 || column >= res.w || row >= res.h) return;
    const found = depth[row * res.w + column];
    if (!Number.isFinite(found)) return;
    const at = middle(column, row);
    const away = Math.hypot(at.x - start.x, at.y - start.y);
    if (!best || away < best.away - 1e-9 || (Math.abs(away - best.away) <= 1e-9 && found < best.depth)) best = { ...at, away, depth: found };
  };
  for (let ring = 0; ring <= Math.max(res.w, res.h); ring += 1) {
    if (best && (ring - 1) * cell > best.away) break;
    for (let row = row0 - ring; row <= row0 + ring; row += 1) {
      if (Math.abs(row - row0) === ring) for (let column = column0 - ring; column <= column0 + ring; column += 1) visit(column, row);
      else { visit(column0 - ring, row); visit(column0 + ring, row); }
    }
  }
  return best;
}

// The drawn pixel least far from the window on the screen, in a render of the region round it that holds
// the model's box on screen (or, with part of the box behind the eye, a window's width and height
// round it): its middle on the screen and its depth. Null where no part is drawn.
function nearestToWindow(runtime, targets, size, view, budget) {
  const { camera } = runtime;
  const model = drawnBox(runtime, targets);
  if (!model) return null;
  let region = { x: -size.width, y: -size.height, w: size.width * 3, h: size.height * 3 };
  const corners = [0, 1, 2, 3, 4, 5, 6, 7].map(index => new runtime.THREE.Vector3(
    index & 1 ? model.max.x : model.min.x, index & 2 ? model.max.y : model.min.y, index & 4 ? model.max.z : model.min.z));
  if (corners.every(corner => view.depthOf(corner) > view.nearest)) {
    const screen = corners.map(corner => { const ndc = corner.clone().project(camera); return { x: (ndc.x + 1) / 2 * size.width, y: (1 - ndc.y) / 2 * size.height }; });
    const left = Math.min(0, ...screen.map(point => point.x)), right = Math.max(size.width, ...screen.map(point => point.x));
    const top = Math.min(0, ...screen.map(point => point.y)), bottom = Math.max(size.height, ...screen.map(point => point.y));
    const padX = (right - left) * 0.05, padY = (bottom - top) * 0.05;
    if ([left, right, top, bottom].every(Number.isFinite)) region = { x: left - padX, y: top - padY, w: right - left + 2 * padX, h: bottom - top + 2 * padY };
  }
  const { depth, res, middle } = depthMap(runtime, targets, region, size, budget, view);
  let best = null;
  for (let row = 0; row < res.h; row += 1) {
    for (let column = 0; column < res.w; column += 1) {
      const found = depth[row * res.w + column];
      if (!Number.isFinite(found)) continue;
      const at = middle(column, row);
      const away = Math.hypot(Math.max(0 - at.x, 0, at.x - size.width), Math.max(0 - at.y, 0, at.y - size.height));
      if (!best || away < best.away - 1e-9 || (Math.abs(away - best.away) <= 1e-9 && found < best.depth)) best = { ...at, away, depth: found };
    }
  }
  return best;
}

/**
 * What the view shows of the parts, looked at only when a level needs it and then kept for the rest of
 * the marks: `window()` the depth map over the viewport, `nearest()` the pixel nearest to the window
 * (null where none is drawn). Pass one to `levelOf` as `depth` to share it between marks.
 *
 * @param {object} runtime
 * @param {object[]} targets
 * @param {{ width: number, height: number }} size
 * @param {ReturnType<typeof viewOf>} view
 * @param {number} [cpuBudget]  Pixels across of the look without a GPU.
 */
function windowLook(runtime, targets, size, view, cpuBudget = LOOK_CPU_BUDGET_PX) {
  const budget = canRenderSurface(runtime.renderer) ? LOOK_BUDGET_PX : cpuBudget;
  let window = null, nearest;
  return {
    window: () => (window ??= depthMap(runtime, targets, { x: 0, y: 0, w: size.width, h: size.height }, size, budget, view)),
    nearest: () => (nearest === undefined ? (nearest = nearestToWindow(runtime, targets, size, view, budget)) : nearest),
  };
}

// A level met edge-on by the view gives rays that stretch along it: the plane facing the view through
// the same point stands in.
function guarded(view, level) {
  const facing = Math.abs(level.normal.dot(view.view));
  return facing < GRAZING ? { point: level.point, normal: view.view.clone().negate() } : level;
}

/**
 * The level of a mark that starts at screen point `start`: the plane of the surface it starts on,
 * in model coordinates. In order:
 *  1. the surface under `start` (a ray from the view): its point, and its normal there — a flat
 *     face's own plane, a curved face's tangent plane;
 *  2. over nothing: the drawn pixel nearest to `start` on the screen in a render of the parts' depth
 *     over the window (searched outward in rings), ray-cast for its surface point and normal;
 *  3. nothing drawn in the window, but a model: the same for the drawn pixel nearest to the window on
 *     the screen (a render over a region round the window that holds the model's box on screen);
 *  4. no model drawn: the plane through the origin facing the view.
 * A plane met nearly edge-on (|normal · view direction| below 0.08) is replaced by the plane facing
 * the view through the same point. Hidden parts and what Clip cuts away are not drawn, so do not count.
 *
 * @param {object} runtime  The viewer runtime (`THREE`, `camera`, `modelGroup`, `renderer`, `scene`, `activeClipPlanes`).
 * @param {{ x: number, y: number }} start  A screen point, in the viewport's CSS pixels.
 * @param {{ width: number, height: number }} size  The viewport's CSS size.
 * @param {{ targets?: object[], view?: ReturnType<typeof viewOf>, depth?: ReturnType<typeof windowLook> | null, cpuBudget?: number }} [options]
 *   `targets`, `view` and `depth` are shared between marks by `projectAnnotations`; `cpuBudget`: pixels across of the look without a GPU.
 * @returns {Level}
 */
export function levelOf(runtime, start, size, { targets = pickTargets(runtime), view = viewOf(runtime, size), depth = null, cpuBudget } = {}) {
  const found = (() => {
    if (!targets.length || !(size.width > 0) || !(size.height > 0)) return null;
    const under = faceAt(runtime, targets, start, view);
    if (under) return { point: under.point, normal: under.normal };
    const look = depth ?? windowLook(runtime, targets, size, view, cpuBudget);
    const near = nearestCovered(look.window(), start) ?? look.nearest();
    if (!near) return null;
    const there = faceAt(runtime, targets, near, view);
    return there ? { point: there.point, normal: there.normal } : { point: view.at(near, near.depth), normal: view.view.clone().negate() };
  })();
  if (found) return guarded(view, found);
  const origin = new runtime.THREE.Vector3();
  const middle = { x: size.width / 2, y: size.height / 2 };
  return { point: view.depthOf(origin) > view.nearest ? origin : view.at(middle, view.nearest), normal: view.view.clone().negate() };
}

// The depth along the ray through screen `point` at which it meets `level`; met edge-on or behind the
// eye, the depth of the level's own point.
function levelDepth(view, level, point) {
  const { origin, direction } = view.ray(point);
  const facing = direction.dot(level.normal);
  if (Math.abs(facing) >= GRAZING) {
    const t = level.point.clone().sub(origin).dot(level.normal) / facing;
    const depth = view.depthOf(origin.clone().addScaledVector(direction, t));
    if (depth > view.nearest) return depth;
  }
  return Math.max(view.depthOf(level.point), view.nearest);
}

/**
 * The marks of an annotation projected into the model from the camera they were drawn under.
 *
 * Each point stays on the ray through where it was drawn, so from that view the ink is exactly what
 * was drawn. Each mark has a level (`levelOf`, at the mark's first point, a text mark's anchor corner,
 * or a fill's first outline point; or the `level` given), and `placement` says where a point lies on
 * its ray: `"surface"` (the default) on the visible surface under it — a stroke over the nearest of
 * what is within a few pixels of its line, so it is never cut by what it was drawn over, a fill's
 * point by point — and, over nothing, on the level; `"plane"` on the level, flat across a curved face.
 * A stroke's line is split into pieces of a few pixels first, in both. A text mark is a card facing
 * the view, at the level's depth under its anchor corner, in both. Every point is a little off what it
 * lies on, toward the eye (text, more).
 * `touches`: what each mark was drawn over, most first — the face or edge (`ref`, from `touchesAt`,
 * a screen point's `[{ part, ref }]`), else the part.
 *
 * @param {object} runtime  The viewer runtime (`THREE`, `camera`, `modelGroup`, `renderer`, `scene`, `activeClipPlanes`).
 * @param {import("../../../../annotation/geometry.js").ScreenMark[]} marks
 * @param {{ width: number, height: number }} size  The viewport's CSS size, which the marks' pixels are of.
 * @param {{ placement?: "surface" | "plane", level?: { point: number[], normal: number[] } | null,
 *   touchesAt?: ((point: { x: number, y: number }) => { part: string, ref?: string }[]) | null, cpuBudget?: number }} [options]
 *   `level`: every mark lies on this plane instead of its own (a fill of a flat shape, on the shape's plane).
 * @returns {AnnotationItem[]}
 */
export function projectAnnotations(runtime, marks, size, { placement = "surface", level = null, touchesAt = null, cpuBudget } = {}) {
  const { THREE, camera } = runtime;
  const { width, height } = size;
  if (!THREE || !camera || !(width > 0) || !(height > 0) || !marks.length) return [];
  const view = viewOf(runtime, size);
  const targets = pickTargets(runtime);
  const look = windowLook(runtime, targets, size, view, cpuBudget);
  const given = level ? guarded(view, { point: new THREE.Vector3(...level.point), normal: new THREE.Vector3(...level.normal).normalize() }) : null;
  const { lifted } = view;
  const partAt = point => { const hit = faceAt(runtime, targets, point, view)?.hit; return hit ? partIdOf(hit) : null; };
  const onSurface = placement !== "plane" && targets.length > 0;
  const shaped = marks.map(mark => {
    const area = mark.kind === "area" ? subdivideArea(THREE, mark.outline) : null;
    const line = mark.kind === "stroke" ? subdivideStroke(mark.points, mark.widths) : null;
    return { mark, area, line, points: area ? area.points : line ? line.points : markPoints(mark) };
  });
  // The parts' depth is read only for ink that lies on them, only under it.
  const reach = Math.max(FILL_SEGMENT_PX, ...shaped.map(({ mark }) => (mark.kind === "stroke" ? mark.width * Math.max(1, ...(mark.widths || [1])) / 2 + COVER_PX : 0)));
  const surface = onSurface
    ? surfaceUnder(runtime, targets, shaped.flatMap(({ points }) => points), reach + 1, size, view) : null;

  return shaped.map(({ mark, area, line, points }) => {
    const widths = line?.widths ?? mark.widths;
    const start = mark.kind === "stroke" ? mark.points[0] : mark.kind === "area" ? mark.outline[0] : mark.corners[0];
    const own = given ?? levelOf(runtime, start, size, { targets, view, depth: look });
    const onLevel = point => levelDepth(view, own, point);
    let depths;
    if (mark.kind === "text") {
      // A card facing the view, at the level's depth under its anchor corner.
      const card = lifted(onLevel(start), LIFT_PX * 4);
      depths = points.map(() => card);
    } else if (!surface) depths = points.map(point => lifted(onLevel(point)));
    else if (mark.kind === "stroke") {
      const radius = index => mark.width * (widths?.[index] ?? 1) / 2 + COVER_PX;
      // Each point takes the nearest depth within its own reach, never a neighbour's: on a slanted face a
      // piece of line ahead is nearer, and would lift the point off it.
      const near = points.map((point, index) => surface.nearest(point, point, radius(index)));
      depths = near.map((depth, index) => (Number.isFinite(depth) ? lifted(depth) : lifted(onLevel(points[index]))));
    } else {
      depths = points.map(point => { const depth = surface.nearest(point, point, FILL_SEGMENT_PX / 2); return Number.isFinite(depth) ? lifted(depth) : lifted(onLevel(point)); });
    }
    const positions = new Float32Array(points.length * 3);
    points.forEach((point, index) => view.at(point, depths[index]).toArray(positions, index * 3));
    const item = { id: mark.id, kind: mark.kind, points: positions, color: mark.color, ...(mark.group ? { group: mark.group } : {}),
      ...(mark.view ? { view: mark.view } : {}), touches: touchesOf(mark.kind === "area" ? mark.outline : points, touchesAt, partAt) };
    if (mark.kind === "stroke") Object.assign(item, { width: mark.width, opacity: mark.opacity, closed: mark.closed,
      ...(widths ? { widths } : {}) });
    else if (mark.kind === "area") Object.assign(item, { opacity: mark.opacity, triangles: area.index, outline: mark.outline.length });
    else Object.assign(item, { text: mark.text, fontPx: mark.fontPx });
    return item;
  });
}

// What a mark was drawn over is read at up to this many of its points.
const TOUCH_SAMPLES = 16;
// What a mark was drawn over, most first: each face or edge `touchesAt` names at a sample of its
// points, with its part; without `touchesAt`, each part under them.
function touchesOf(points, touchesAt, partAt) {
  const tally = new Map();
  const step = Math.max(1, (points.length - 1) / Math.max(1, TOUCH_SAMPLES - 1));
  for (let at = 0; at < points.length; at += step) {
    const point = points[Math.round(at)];
    const found = touchesAt ? touchesAt(point) || [] : [{ part: partAt(point) }];
    for (const touch of found) {
      if (touch?.part == null) continue;
      const entry = touch.ref ? { part: String(touch.part), ref: String(touch.ref) } : { part: String(touch.part) };
      const key = `${entry.part}\u0000${entry.ref || ""}`;
      const counted = tally.get(key) || { touch: entry, count: 0 };
      counted.count += 1;
      tally.set(key, counted);
    }
  }
  return [...tally.values()].sort((a, b) => b.count - a.count).map(({ touch }) => touch);
}

/**
 * The annotation as an annotation file says it (`@text-to-cad/core/common/annotation.js`).
 * @param {readonly AnnotationItem[]} items
 * @param {string} [units]
 */
export function annotationDocumentOf(items, units = "mm") {
  return annotationDocument({ units, marks: items });
}

/** Each item's points, as vectors: in model coordinates, where it was drawn. */
export function annotationWorldPoints(runtime, item) {
  const points = [];
  for (let index = 0; index < item.points.length; index += 3) points.push(new runtime.THREE.Vector3().fromArray(item.points, index));
  return points;
}

/**
 * The ink as it falls on the screen now (`annotation/geometry.js`'s `ScreenAnnotation`): to hit-test with
 * the eraser and Select, and to bound a fill. Ink behind the eye is not there.
 */
export function annotationsOnScreen(runtime, items, { width, height }) {
  const { THREE, camera } = runtime;
  camera.updateMatrixWorld();
  const eye = new THREE.Vector3().setFromMatrixPosition(camera.matrixWorld);
  const view = new THREE.Vector3(); camera.getWorldDirection(view);
  return items.flatMap(item => {
    const all = annotationWorldPoints(runtime, item);
    // A fill's outline: its first points (the rest are inside it).
    const world = item.kind === "area" && item.outline ? all.slice(0, item.outline) : all;
    if (world.some(point => point.clone().sub(eye).dot(view) <= 0)) return [];
    const points = world.map(point => {
      const ndc = point.clone().project(camera);
      return { x: ((ndc.x + 1) / 2) * width, y: ((1 - ndc.y) / 2) * height };
    });
    return [{ id: item.id, kind: item.kind, points, closed: Boolean(item.closed), width: Math.max(...(item.widths || [1])) * (item.width || 0) }];
  });
}

// What Select has picked is haloed: a wider line in the selection's blue behind the ink, along a
// stroke, round a fill's outline or a text mark's box; what the pointer rests on, a fainter one.
const SELECTION_COLOR = "#2979ff";
const HALO_PX = 6;
const PICKED_OPACITY = 0.5;
const HOVERED_OPACITY = 0.25;
function haloObject(runtime, item, lineScale, opacity) {
  const outline = item.kind === "stroke" ? item.points
    : item.points.subarray(0, 3 * (item.kind === "area" ? item.outline ?? item.points.length / 3 : 4));
  const closed = item.kind !== "stroke" || item.closed;
  const points = closed && item.kind !== "stroke" ? Float32Array.from([...outline, ...outline.subarray(0, 3)]) : outline;
  const width = item.kind === "stroke" ? item.width * Math.max(1, ...(item.widths || [1])) : 2;
  const halo = createScreenSpaceLineStrip(runtime, points, { color: SELECTION_COLOR, opacity,
    lineWidth: (width + HALO_PX) * lineScale, renderOrder: ANNOTATION_RENDER_ORDER - 1, depthTest: true, depthWrite: false });
  if (halo) {
    halo.matrixAutoUpdate = false;
    halo.matrixWorldAutoUpdate = false;
    halo.frustumCulled = false;
    halo.userData.haloOpacity = opacity;
  }
  return halo;
}

// Where the ink is in the world, as a box ({ min, max }), or null without any.
function inkBounds(runtime, items) {
  const box = new runtime.THREE.Box3();
  for (const item of items) for (const point of annotationWorldPoints(runtime, item)) box.expandByPoint(point);
  return box.isEmpty() ? null : { min: box.min.toArray(), max: box.max.toArray() };
}

/**
 * Draws projected ink in a viewer runtime until `dispose()`: `update(items, selected)` draws a
 * annotation's ink as it is now, making objects only for items it has not drawn yet and dropping those
 * it no longer has (an item is never changed in place: a changed one is a new item), and halos the
 * ink Select has picked (`selected`, ids) and, fainter, what the pointer rests on (`hovered`). Every
 * draw, before the ink is drawn, each mark takes the clip planes the model has; the marks stay
 * where they were drawn.
 *
 * @param {object} runtime
 * @returns {{ group: import("three").Group, update(items: AnnotationItem[], selected?: readonly string[], hovered?: readonly string[]): void, dispose(): void }}
 */
export function mountAnnotations(runtime) {
  const { THREE, scene } = runtime;
  // Ink casts no shadow: a frame that keeps the shadow maps it has (`viewport/sceneFrames.js`).
  const redraw = () => requestSceneFrame(runtime, false);
  const group = new THREE.Group();
  group.name = "annotations";
  scene.add(group);
  const radius = Number(runtime.modelRadius) || 1;
  // A stroke's width is in CSS pixels; the line's in device pixels.
  const lineScale = Number(runtime.renderer?.getPixelRatio?.()) || 1;
  let entries = new Map();
  let halos = new Map();
  const follow = () => {
    const planes = Array.isArray(runtime.activeClipPlanes) ? runtime.activeClipPlanes : [];
    for (const object of [...entries.values(), ...halos.values()]) clipAnnotationObject(object, planes);
  };
  // Three can draw an opaque object more than once within a scene render (for example,
  // the transmission buffer before the main view). Update clipping before the ink draws
  // without wrapping a scene hook: counting object callbacks as frames could make that
  // hook wrap itself and recurse forever on glass models.
  const sentinel = new THREE.Mesh(new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(new Float32Array(9), 3)),
    new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false, depthTest: false }));
  sentinel.frustumCulled = false;
  sentinel.renderOrder = -1e9;
  sentinel.onBeforeRender = follow;
  group.add(sentinel);
  const release = disposeAnnotationObject;
  return {
    group,
    update(items, selected = [], hovered = []) {
      const next = new Map();
      for (const item of items) {
        let object = entries.get(item);
        if (!object) {
          object = annotationMarkObject(runtime, item, { radius, lineScale });
          if (!object) continue;
          group.add(object);
        }
        next.set(item, object);
      }
      for (const [item, object] of entries) if (!next.has(item)) release(object);
      entries = next;
      const picked = new Set(selected);
      const lit = new Set(hovered);
      const nextHalos = new Map();
      for (const item of items) {
        const opacity = picked.has(item.id) ? PICKED_OPACITY : lit.has(item.id) ? HOVERED_OPACITY : 0;
        if (!opacity) continue;
        let halo = halos.get(item);
        if (halo && halo.userData.haloOpacity !== opacity) { release(halo); halos.delete(item); halo = null; }
        halo ??= haloObject(runtime, item, lineScale, opacity);
        if (!halo) continue;
        if (!halo.parent) group.add(halo);
        nextHalos.set(item, halo);
      }
      for (const [item, halo] of halos) if (!nextHalos.has(item)) release(halo);
      halos = nextHalos;
      follow();
      // The ink's box, for the camera's depth range (`viewport/useViewerRuntime.js`): ink drawn beyond
      // the model (in the air beside it) is not cut off by a near plane fitted to the model alone.
      runtime.annotationBounds = inkBounds(runtime, items);
      redraw();
    },
    dispose() {
      runtime.annotationBounds = null;
      group.removeFromParent();
      sentinel.geometry.dispose();
      sentinel.material.dispose();
      for (const object of [...entries.values(), ...halos.values()]) release(object);
      entries = new Map();
      halos = new Map();
      redraw();
    },
  };
}
