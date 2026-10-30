/**
 * Where an FEA result's loads and fixtures act, drawn on the model as every FEA tool draws them:
 * arrows on each loaded face (along the force, or along the inward normal for a pressure), with a
 * label naming the load, and small cones on each fixed face pointing into it (on a roller's face,
 * the cone pressing on a small plate that rolls on the face, its sliding support), and a body load's
 * arrow through the model's middle: the kinds of one table (`MARKER_KINDS`), each in the ink (what
 * drives the part) or the muted grey (what holds it).
 *
 * The places are sampled once per result (`markerSites`): one to five per face, more on a bigger
 * face, spread over it, each a triangle of the face found by the result's `_FACE` attribute. Where
 * a marker stands is worked out from the positions on screen (`markerPoses`), so the markers follow
 * the deformation as it is drawn. The THREE objects (`createFeaMarkers`) are this module's: per
 * kind, one instanced mesh drawn solid where it is in view and one drawn as a faint ghost where the
 * model hides it (the x-ray look), so a fixture under the part reads as under it, never as standing
 * on the face in front. Never picked, and disposed with the markers.
 */
import { clamp } from "@text-to-cad/core/common/numbers.js";
import { forceDirection } from "./fea/setup.js";
import { filePositions } from "./feaResult.js";

// An arrow is this share of the model's bounding diagonal long, whatever the load: the arrows say
// where and which way, the label how much.
export const ARROW_LENGTH = 0.08;
// A fixture's cone, as a share of the diagonal.
const CONE_HEIGHT = 0.03;
// A face gets one more marker for every this share of the diagonal in the square root of its area.
const SPREAD = 0.12;
const MAX_PER_FACE = 5;
// The chosen load's or fixture's markers take the colour a chosen face is tinted toward.
const HIGHLIGHT = "#ff40f2";
// What is left of a marker the model hides: a ghost, drawn over the surface.
export const GHOST_OPACITY = 0.25;

/**
 * Every kind of marker, by name: what it is drawn as (`shape`), in which of the two tones (`tone`:
 * the ink of what drives the part, the muted grey of what holds it), where it stands (`on`: its faces,
 * or the model's middle) and at most how many stand on one face (`most`). `phrase`: what the markers'
 * checkbox says of it.
 */
export const MARKER_KINDS = Object.freeze({
  load: Object.freeze({ shape: "arrow", tone: "load", on: "faces", most: MAX_PER_FACE, phrase: "arrows where the study loads the part" }),
  fixture: Object.freeze({ shape: "cone", tone: "fixture", on: "faces", most: MAX_PER_FACE, phrase: "cones where it holds it" }),
  roller: Object.freeze({ shape: "roller", tone: "fixture", on: "faces", most: MAX_PER_FACE, phrase: "cones on rollers where it may slide" }),
  body_load: Object.freeze({ shape: "arrow", tone: "load", on: "middle", most: 1, phrase: "an arrow through its middle for its weight" }),
});

/** What the markers' checkbox says it draws, over these kinds, in the table's order: "Arrows where the study loads the part, cones where it holds it." */
export function markerGateText(kinds) {
  const phrases = Object.keys(MARKER_KINDS).filter((kind) => kinds.includes(kind)).map((kind) => MARKER_KINDS[kind].phrase);
  if (!phrases.length) return "";
  const text = phrases.join(", ");
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;
}

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const length = (a) => Math.hypot(a[0], a[1], a[2]);
const scaled = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const plus = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const unit = (a) => { const l = length(a); return l > 0 ? scaled(a, 1 / l) : [0, 1, 0]; };
const distanceSq = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;
const point = (array, index) => [array[index * 3], array[index * 3 + 1], array[index * 3 + 2]];

/** CAD (x, y, z) as the result mesh's glTF axes (x, z, -y): the writer's convention. */
const gltfAxes = ([x, y, z]) => [x, z, 0 - y];

/** The positions without the displacement the file baked in: where the part is with no load. */
function restPositions(result) {
  const geometry = result.mesh.geometry;
  const base = filePositions(result.mesh);
  const displacement = geometry.getAttribute("_displacement");
  if (displacement?.itemSize !== 3 || displacement.count * 3 !== base.length) return base;
  const rest = new Float32Array(base.length);
  for (let i = 0; i < base.length; i += 1) rest[i] = base[i] - result.deformationScale * displacement.array[i];
  return rest;
}

/** Each triangle of each face: `{ triangles: [[a, b, c]], areas, centroids }` by face index, from `_FACE` (the writer's mesh is indexed). */
function trianglesByFace(result, positions, wanted) {
  const geometry = result.mesh.geometry;
  const faceOf = geometry.getAttribute("_face")?.array;
  const index = geometry.getIndex().array;
  const byFace = new Map([...wanted].map((face) => [face, { triangles: [], areas: [], centroids: [] }]));
  if (!faceOf) return byFace;
  for (let t = 0; t < index.length / 3; t += 1) {
    const corners = [index[t * 3], index[t * 3 + 1], index[t * 3 + 2]];
    const face = Math.round(faceOf[corners[0]]);
    const entry = byFace.get(face);
    if (!entry || Math.round(faceOf[corners[1]]) !== face || Math.round(faceOf[corners[2]]) !== face) continue;
    const [a, b, c] = corners.map((corner) => point(positions, corner));
    entry.triangles.push(corners);
    entry.areas.push(length(cross(sub(b, a), sub(c, a))) / 2);
    entry.centroids.push(scaled(plus(plus(a, b), c), 1 / 3));
  }
  return byFace;
}

/**
 * `count` triangles spread over a face: the one nearest its centre first, then each the farthest
 * from those already chosen, then a few rounds of moving each to the middle of its share of the
 * face's area, so the markers stand inside the face rather than on its edges.
 */
function spreadTriangles({ areas, centroids }, count) {
  const total = areas.reduce((sum, area) => sum + area, 0) || 1;
  const centre = centroids.reduce((sum, c, i) => plus(sum, scaled(c, areas[i] / total)), [0, 0, 0]);
  const nearest = (target) => centroids.reduce((best, c, i) => (distanceSq(c, target) < distanceSq(centroids[best], target) ? i : best), 0);
  const chosen = [nearest(centre)];
  while (chosen.length < Math.min(count, centroids.length)) {
    let far = -1;
    let farthest = -1;
    centroids.forEach((c, i) => {
      const gap = Math.min(...chosen.map((j) => distanceSq(c, centroids[j])));
      if (gap > farthest) { farthest = gap; far = i; }
    });
    chosen.push(far);
  }
  if (chosen.length < 2) return chosen;
  let centres = chosen.map((i) => centroids[i]);
  for (let round = 0; round < 4; round += 1) {
    const sums = centres.map(() => [0, 0, 0]);
    const weights = centres.map(() => 0);
    centroids.forEach((c, i) => {
      let owner = 0;
      centres.forEach((m, j) => { if (distanceSq(c, m) < distanceSq(c, centres[owner])) owner = j; });
      sums[owner] = plus(sums[owner], scaled(c, areas[i]));
      weights[owner] += areas[i];
    });
    centres = centres.map((m, j) => (weights[j] > 0 ? scaled(sums[j], 1 / weights[j]) : m));
  }
  return [...new Set(centres.map(nearest))];
}

/**
 * The study's entries each kind of marker stands for, in the order Study's rows number them
 * (`group`), each with the faces it stands on (`refs`; none for one that stands elsewhere): the
 * loads with faces, the fixtures (a roller's faces its own kind's, each numbered by its place among
 * every fixture, as Study's rows number it) and a body load (gravity, an acceleration: a load with no faces).
 */
function markerGroups(result) {
  const study = result.study;
  const roller = (fixture) => fixture.type === "roller";
  const groups = {
    load: study.loads.filter((load) => load.faces.length).map((load) => load.faces),
    fixture: study.fixtures.map((fixture) => (roller(fixture) ? [] : fixture.faces)),
    roller: study.fixtures.map((fixture) => (roller(fixture) ? fixture.faces : [])),
    body_load: study.loads.filter((load) => !load.faces.length && load.g).map(() => []),
  };
  return Object.keys(MARKER_KINDS)
    .flatMap((kind) => groups[kind].map((refs, group) => ({ kind, group, refs })));
}

/**
 * Where the result's markers stand: one entry per marker, `{ kind, group, face, ref, triangle }`
 * (`kind` one of `MARKER_KINDS`; `group` the study entry's place among its kind's, as Study's rows
 * number them; `face` the index into `faces`, `ref` its ref and `triangle` the three vertex indices
 * it stands on, for a marker on a face; -1, null and null for a body load's, through the model's
 * middle), and the model's `diagonal`. Sampled once, against the part at rest; loads first, then
 * fixtures, then each other kind in the table's order.
 */
export function markerSites(result) {
  const rest = restPositions(result);
  let low = [Infinity, Infinity, Infinity];
  let high = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < rest.length; i += 3) {
    low = [Math.min(low[0], rest[i]), Math.min(low[1], rest[i + 1]), Math.min(low[2], rest[i + 2])];
    high = [Math.max(high[0], rest[i]), Math.max(high[1], rest[i + 1]), Math.max(high[2], rest[i + 2])];
  }
  const diagonal = rest.length ? length(sub(high, low)) : 0;
  const groups = markerGroups(result);
  const faceIndex = (ref) => result.faces.indexOf(ref);
  const byFace = trianglesByFace(result, rest, new Set(groups.flatMap((entry) => entry.refs.map(faceIndex)).filter((face) => face >= 0)));
  const sites = [];
  for (const { kind, group, refs } of groups) {
    if (MARKER_KINDS[kind].on !== "faces") {
      sites.push({ kind, group, face: -1, ref: null, triangle: null });
      continue;
    }
    for (const ref of refs) {
      const face = faceIndex(ref);
      const entry = byFace.get(face);
      if (!entry?.triangles.length) continue;
      const area = entry.areas.reduce((sum, value) => sum + value, 0);
      const count = clamp(Math.ceil(Math.sqrt(area) / (SPREAD * (diagonal || 1))), 1, MARKER_KINDS[kind].most);
      for (const t of spreadTriangles(entry, count)) sites.push({ kind, group, face, ref, triangle: entry.triangles[t] });
    }
  }
  return { diagonal, sites };
}

/** A load's direction in the mesh's space and whether it pushes: a force along its vector, a pressure into the face. */
function loadDirection(load, normal) {
  if (load.vector) return unit(gltfAxes(load.vector));
  return (load.pressure ?? 0) < 0 ? normal : scaled(normal, -1);
}

/** A box's eight corners. */
const boxCorners = ({ low, high }) => [0, 1, 2, 3, 4, 5, 6, 7].map((i) => [i & 1 ? high[0] : low[0], i & 2 ? high[1] : low[1], i & 4 ? high[2] : low[2]]);

/** The box of the positions on screen: its `low` and `high` corners and its `centre`. */
function boxOf(positions) {
  const low = [Infinity, Infinity, Infinity];
  const high = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < positions.length; i += 3) {
    for (let k = 0; k < 3; k += 1) {
      const v = positions[i + k];
      if (v < low[k]) low[k] = v;
      if (v > high[k]) high[k] = v;
    }
  }
  return { low, high, centre: scaled(plus(low, high), 0.5) };
}

/** A body load's arrow, through the model's middle along the load. */
function bodyLoadPose(result, site, box, arrow) {
  const load = result.study.loads.filter((entry) => !entry.faces.length && entry.g)[site.group];
  const direction = unit(gltfAxes(load.g));
  return { ...site, tip: plus(box.centre, scaled(direction, arrow / 2)), tail: plus(box.centre, scaled(direction, 0 - arrow / 2)), direction, pushes: true };
}

/**
 * Each marker at the positions on screen (`positions`, the mesh's own array): an arrow's `tip`,
 * `tail`, unit `direction` (the way it points) and whether it `pushes`; a cone's `tip` on the face and `direction` into
 * it. An arrow that pushes on its face (against the face's outward normal) has its tip on the face;
 * one that pulls stands on the face by its tail, pointing away. `normal` is the face's outward
 * normal there, from the triangle's winding. A roller stands as a fixture's cone does; a body load's
 * arrow through the model's middle (`bodyLoadPose`).
 */
export function markerPoses(result, { diagonal, sites }, positions) {
  const loads = result.study.loads.filter((load) => load.faces.length);
  const arrow = ARROW_LENGTH * diagonal;
  const box = sites.some((site) => !site.triangle) ? boxOf(positions) : null;
  return sites.map((site) => {
    if (!site.triangle) return bodyLoadPose(result, site, box, arrow);
    const [a, b, c] = site.triangle.map((corner) => point(positions, corner));
    const at = scaled(plus(plus(a, b), c), 1 / 3);
    const normal = unit(cross(sub(b, a), sub(c, a)));
    if (site.kind === "fixture" || site.kind === "roller") return { ...site, normal, tip: at, direction: scaled(normal, -1) };
    const direction = loadDirection(loads[site.group], normal);
    const pushes = direction[0] * normal[0] + direction[1] * normal[1] + direction[2] * normal[2] <= 0;
    const tip = pushes ? at : plus(at, scaled(direction, arrow));
    return { ...site, normal, tip, tail: pushes ? plus(at, scaled(direction, 0 - arrow)) : at, direction, pushes };
  });
}

/** A figure for a label: whole numbers from 10 up, two significant figures below (Study's rows say it the same way). */
function labelNumber(value) {
  const v = Number(value) || 0;
  return String(Math.abs(v) >= 10 ? Math.round(v) : Number(v.toPrecision(2)));
}

/** What a load's label says at `loadScale` times the solved load: "300 N", "2 MPa". */
export function loadLabel(load, loadScale = 1) {
  if (load.vector) return `${labelNumber(Math.hypot(...load.vector) * loadScale)} N`;
  if (load.pressure !== null && load.pressure !== undefined) return `${labelNumber(load.pressure * loadScale)} MPa`;
  return "";
}

/** A body load's amount and way, at `loadScale` times the solved load: "1 g down", "5 g along +X". */
function bodyLoadLabel(load, loadScale) {
  return `${labelNumber(Math.hypot(...load.g) * loadScale)} g ${forceDirection(load.g)}`.trim();
}

/**
 * Each marker kind's label at `loadScale` times the solved load, by its study entry: a load's and a
 * body load's amount; "" for one that says nothing (a fixture).
 */
function labelText(result, kind, group, loadScale) {
  const study = result.study;
  if (kind === "load") return loadLabel(study.loads.filter((entry) => entry.faces.length)[group], loadScale);
  if (kind === "body_load") return bodyLoadLabel(study.loads.filter((entry) => !entry.faces.length && entry.g)[group], loadScale);
  return "";
}

/** Where a marker's label goes: past its free end, away from where it acts (`free`, `anchor`): a push's tail or a pull's tip. */
const labelEnds = (pose) => ({ free: pose.pushes ? pose.tail : pose.tip, anchor: pose.pushes ? pose.tip : pose.tail });

// A body load's label always stands outside the model's outline: its arrow runs through it.
const OUTSIDE_ONLY = new Set(["body_load"]);

// A label stands this share of the model's diagonal clear of its box once it is moved out of it.
const LABEL_CLEARANCE = 0.03;

/** How far from `from` along the unit `way` the box (`low`, `high`) is left behind: 0 from outside it. */
function boxExit(from, way, { low, high }) {
  let leave = Infinity;
  for (let k = 0; k < 3; k += 1) {
    if (from[k] < low[k] - 1e-12 || from[k] > high[k] + 1e-12) return 0;
    if (Math.abs(way[k]) > 1e-12) leave = Math.min(leave, ((way[k] > 0 ? high[k] : low[k]) - from[k]) / way[k]);
  }
  return Number.isFinite(leave) ? Math.max(leave, 0) : 0;
}

/**
 * A label's place outside the model's box, along its marker's line: from the marker's free end on
 * along the arrow, or from its other end back the other way, whichever leaves the box sooner (a
 * load under the part stands below it, not up through it; a load in a pin hole leaves by the
 * nearer side of the part, never inside the hole; a body load through the middle leaves past the
 * model's top or bottom, beside it, not over it), then a little clear of it. `free` and `anchor` as
 * `labelEnds` gives them; `face` is where the label's text runs away from.
 */
export function labelOutside({ free, anchor }, box, diagonal) {
  const along = sub(free, anchor);
  if (!box || !(length(along) > 0)) return { at: free, face: anchor };
  const way = unit(along);
  const back = scaled(way, -1);
  const onward = boxExit(free, way, box);
  const behind = boxExit(anchor, back, box);
  if (onward === 0) return { at: free, face: anchor };
  const clear = LABEL_CLEARANCE * diagonal;
  return behind < onward
    ? { at: plus(anchor, scaled(back, behind + clear)), face: free }
    : { at: plus(free, scaled(way, onward + clear)), face: anchor };
}

/** The convex hull of 2D points, counter-clockwise (Andrew's monotone chain). */
function hull(points) {
  const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (sorted.length < 3) return sorted;
  const turn = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const half = (list) => {
    const out = [];
    for (const p of list) {
      while (out.length >= 2 && turn(out[out.length - 2], out[out.length - 1], p) <= 0) out.pop();
      out.push(p);
    }
    out.pop();
    return out;
  };
  return [...half(sorted), ...half([...sorted].reverse())];
}

/** How far from `from` along the unit (`dx`, `dy`) the convex `shape` (counter-clockwise) is left behind: 0 from outside it. */
function hullExit(from, dx, dy, shape) {
  let leave = Infinity;
  for (let i = 0; i < shape.length; i += 1) {
    const a = shape[i];
    const b = shape[(i + 1) % shape.length];
    const ex = b[0] - a[0];
    const ey = b[1] - a[1];
    // Inside, every edge has the point on its inner (left) side; it leaves by the nearest edge ahead.
    const side = ex * (from[1] - a[1]) - ey * (from[0] - a[0]);
    if (side < 0) return 0;
    const towards = ex * dy - ey * dx;
    if (towards < 0) leave = Math.min(leave, side / -towards);
  }
  return Number.isFinite(leave) ? leave : 0;
}

/**
 * On screen, a label at `at` (its text running away from `face`, where its marker acts), moved along
 * that line until it is outside the model's outline (`corners`: its box's eight corners on screen,
 * whose hull bounds every face, a back face's too), then `gap` pixels clear: on from `at`, or back
 * from `face` the other way, whichever leaves the outline sooner (a load under the part labelled
 * below it, not across it). A line seen end on (an arrow pointing at the eye) moves straight out
 * from the outline's middle instead. Returns `{ x, y }` and the unit direction its text runs (`dx`, `dy`).
 */
export function pastOutline(at, face, corners, gap) {
  const shape = hull(corners || []);
  let dx = face ? at[0] - face[0] : 0;
  let dy = face ? at[1] - face[1] : 0;
  let ends = Boolean(face);
  if (Math.hypot(dx, dy) < 2 && shape.length) {
    const middle = shape.reduce((sum, p) => [sum[0] + p[0] / shape.length, sum[1] + p[1] / shape.length], [0, 0]);
    [dx, dy] = [at[0] - middle[0], at[1] - middle[1]];
    ends = false;
  }
  const span = Math.hypot(dx, dy);
  if (!(span > 0)) return { x: at[0] + gap, y: at[1], dx: 1, dy: 0 };
  dx /= span;
  dy /= span;
  if (shape.length < 3) return { x: at[0] + dx * gap, y: at[1] + dy * gap, dx, dy };
  const onward = hullExit(at, dx, dy, shape);
  const back = ends && onward > 0 ? hullExit(face, -dx, -dy, shape) : Infinity;
  if (back < onward) return { x: face[0] - dx * (back + gap), y: face[1] - dy * (back + gap), dx: -dx, dy: -dy };
  return { x: at[0] + dx * (onward + gap), y: at[1] + dy * (onward + gap), dx, dy };
}

/**
 * The THREE objects of a result's markers, added under the result mesh so they ride its transform:
 * `object3D` (a group), `update(positions)` to stand them on the positions on screen,
 * `style({ colours, visible, chosen })` (`chosen(site)` true for a marker of the
 * entry chosen in Study), `labels(loadScale)`: each entry's text and where it goes (`at`,
 * past the free end of the marker nearest the middle of its markers' free ends, out of the model's box
 * along it, and `face`, where it runs from, in the mesh's space, with the box's `corners`; and for a kind
 * whose marker stands on its face, `end`: that marker's own outer end and where it acts, to sit at when
 * in sight; `kind` and `group` say whose), `kinds` (the kinds it draws) and `dispose()`.
 *
 * Loads and fixtures are the six instanced meshes they always were (shafts, heads and cones, each
 * with its ghost); every other kind adds its own after them, only where it has markers.
 *
 * @param {typeof import("three")} THREE
 */
export function createFeaMarkers(THREE, result) {
  const placed = markerSites(result);
  const arrowLength = ARROW_LENGTH * placed.diagonal;
  const coneHeight = CONE_HEIGHT * placed.diagonal;
  const group = new THREE.Group();
  group.name = "fea-markers";
  const loads = placed.sites.filter((site) => site.kind === "load");
  const fixtures = placed.sites.filter((site) => site.kind === "fixture");

  // One arrow: its tip at the origin, pointing up +Y, its shaft back down to -length.
  const head = arrowLength * 0.3;
  const headGeometry = new THREE.ConeGeometry(arrowLength * 0.1, head, 16);
  headGeometry.translate(0, -head / 2, 0);
  const shaftGeometry = new THREE.CylinderGeometry(arrowLength * 0.035, arrowLength * 0.035, arrowLength - head, 10);
  shaftGeometry.translate(0, -head - (arrowLength - head) / 2, 0);
  const coneGeometry = new THREE.ConeGeometry(coneHeight * 0.45, coneHeight, 12);
  coneGeometry.translate(0, -coneHeight / 2, 0);
  const geometries = [headGeometry, shaftGeometry, coneGeometry];
  // Two passes, both after the model and in the transparent list so their order holds: first the
  // ghost, only where something nearer hides the marker (depth greater than what is drawn there,
  // nothing written), then the solid marker, depth-tested as the model is. Each fragment is one or
  // the other, so a hidden marker never shows solid and a visible one never carries its ghost.
  const solidMaterial = () => new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 1, toneMapped: false });
  const ghostMaterial = () => new THREE.MeshBasicMaterial({
    color: 0xffffff, transparent: true, opacity: GHOST_OPACITY, depthFunc: THREE.GreaterDepth, depthWrite: false, toneMapped: false,
  });
  const materials = { load: solidMaterial(), fixture: solidMaterial(), loadGhost: ghostMaterial(), fixtureGhost: ghostMaterial() };
  const instanced = (geometry, mat, count, renderOrder, name) => {
    const mesh = new THREE.InstancedMesh(geometry, mat, Math.max(count, 1));
    mesh.name = name;
    mesh.count = count;
    mesh.renderOrder = renderOrder;
    mesh.frustumCulled = false;
    mesh.raycast = () => {};
    group.add(mesh);
    return mesh;
  };
  const shafts = instanced(shaftGeometry, materials.load, loads.length, 11, "fea-load-shafts");
  const heads = instanced(headGeometry, materials.load, loads.length, 11, "fea-load-heads");
  const cones = instanced(coneGeometry, materials.fixture, fixtures.length, 11, "fea-fixture-cones");
  const ghostShafts = instanced(shaftGeometry, materials.loadGhost, loads.length, 10, "fea-load-shafts-ghost");
  const ghostHeads = instanced(headGeometry, materials.loadGhost, loads.length, 10, "fea-load-heads-ghost");
  const ghostCones = instanced(coneGeometry, materials.fixtureGhost, fixtures.length, 10, "fea-fixture-cones-ghost");
  const meshes = [shafts, heads, cones, ghostShafts, ghostHeads, ghostCones];
  const ghostOf = new Map([[shafts, ghostShafts], [heads, ghostHeads], [cones, ghostCones]]);

  // Every other kind: its pieces, each one instanced mesh and its ghost, in its tone. Built only for
  // a kind with markers, so a result of loads and fixtures alone has the six meshes above.
  const shapes = {
    arrow: () => [["shafts", shaftGeometry], ["heads", headGeometry]],
    // A roller, as it rolls on its face: two small balls on the face, a thin plate on them and the
    // fixture's cone on the plate, its tip on the plate, all along the cone's axis into the face.
    roller: () => {
      const ball = coneHeight * 0.14;
      const plate = coneHeight * 0.08;
      const balls = [-1, 1].map((side) => {
        const sphere = new THREE.SphereGeometry(ball, 12, 8);
        sphere.translate(side * coneHeight * 0.2, -ball, 0);
        return sphere;
      });
      const disc = new THREE.CylinderGeometry(coneHeight * 0.42, coneHeight * 0.42, plate, 20);
      disc.translate(0, -2 * ball - plate / 2, 0);
      const cone = new THREE.ConeGeometry(coneHeight * 0.4, coneHeight * 0.85, 12);
      cone.translate(0, -2 * ball - plate - coneHeight * 0.425, 0);
      geometries.push(...balls, disc, cone);
      return [["cones", cone], ["plates", disc], ["balls", balls[0]], ["balls-2", balls[1]]];
    },
  };
  const extra = Object.keys(MARKER_KINDS).filter((kind) => kind !== "load" && kind !== "fixture")
    .map((kind) => ({ kind, sites: placed.sites.filter((site) => site.kind === kind) })).filter((entry) => entry.sites.length);
  for (const entry of extra) {
    const { shape, tone } = MARKER_KINDS[entry.kind];
    const solid = solidMaterial();
    const ghost = ghostMaterial();
    entry.tone = tone;
    entry.materials = [solid, ghost];
    const name = `fea-${entry.kind.replace(/_/g, "-")}`;
    entry.parts = shapes[shape]().map(([part, geometry]) => {
      const mesh = instanced(geometry, solid, entry.sites.length, 11, `${name}-${part}`);
      const shadow = instanced(geometry, ghost, entry.sites.length, 10, `${name}-${part}-ghost`);
      ghostOf.set(mesh, shadow);
      meshes.push(mesh, shadow);
      return mesh;
    });
  }
  const up = new THREE.Vector3(0, 1, 0);
  const matrix = new THREE.Matrix4();
  const rotation = new THREE.Quaternion();
  const at = new THREE.Vector3();
  const along = new THREE.Vector3();
  const one = new THREE.Vector3(1, 1, 1);
  const colour = new THREE.Color();
  let poses = [];
  let box = null;

  const place = (mesh, index, pose) => {
    rotation.setFromUnitVectors(up, along.fromArray(pose.direction));
    matrix.compose(at.fromArray(pose.tip), rotation, one);
    mesh.setMatrixAt(index, matrix);
    ghostOf.get(mesh).setMatrixAt(index, matrix);
  };
  const paint = (mesh, index, tone) => { mesh.setColorAt(index, tone); ghostOf.get(mesh).setColorAt(index, tone); };
  return {
    object3D: group,
    sites: placed.sites,
    kinds: [...new Set(placed.sites.map((site) => site.kind))],
    update(positions) {
      poses = markerPoses(result, placed, positions);
      box = boxOf(positions);
      let load = 0;
      let fixture = 0;
      const counts = new Map();
      for (const pose of poses) {
        if (pose.kind === "load") { place(shafts, load, pose); place(heads, load, pose); load += 1; }
        else if (pose.kind === "fixture") { place(cones, fixture, pose); fixture += 1; }
        else {
          const entry = extra.find((item) => item.kind === pose.kind);
          const index = counts.get(pose.kind) || 0;
          counts.set(pose.kind, index + 1);
          for (const mesh of entry.parts) place(mesh, index, pose);
        }
      }
      for (const mesh of meshes) mesh.instanceMatrix.needsUpdate = true;
    },
    poses: () => poses,
    style({ colours, visible, chosen }) {
      shafts.visible = heads.visible = ghostShafts.visible = ghostHeads.visible = visible && loads.length > 0;
      cones.visible = ghostCones.visible = visible && fixtures.length > 0;
      loads.forEach((site, index) => {
        colour.set(chosen(site) ? HIGHLIGHT : colours.load);
        paint(shafts, index, colour);
        paint(heads, index, colour);
      });
      fixtures.forEach((site, index) => paint(cones, index, colour.set(chosen(site) ? HIGHLIGHT : colours.fixture)));
      for (const entry of extra) {
        for (const mesh of entry.parts) {
          mesh.visible = ghostOf.get(mesh).visible = visible;
          entry.sites.forEach((site, index) => paint(mesh, index, colour.set(chosen(site) ? HIGHLIGHT : colours[entry.tone])));
        }
      }
      for (const mesh of meshes) if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    },
    labels(loadScale = 1) {
      const entries = [];
      for (const pose of poses) {
        if (pose.kind === "fixture" || pose.kind === "roller") continue;
        let entry = entries.find((item) => item.kind === pose.kind && item.group === pose.group);
        if (!entry) entries.push(entry = { kind: pose.kind, group: pose.group, ends: [] });
        entry.ends.push(labelEnds(pose));
      }
      return entries.map(({ kind, group: index, ends }) => {
        const text = labelText(result, kind, index, loadScale);
        if (!text) return null;
        // The label stands past one marker's free end, off the part (a push's tail, a pull's tip), and FeaLoadLabels
        // carries it on along that arrow. Of several, the one nearest their middle: the middle itself may be inside
        // the part (arrows all round a shaft, a shake held at both ends), one arrow's end never is.
        const middle = scaled(ends.map((end) => end.free).reduce(plus, [0, 0, 0]), 1 / ends.length);
        const away = (end) => length(sub(end.free, middle));
        const chosen = ends.reduce((best, end) => (away(end) < away(best) ? end : best));
        // Never on or inside the part: on along its line out of the model's box (`labelOutside`); FeaLoadLabels
        // then takes it past the outline on screen (`pastOutline`, from the box's `corners`). A load on its faces
        // also offers its own arrow's outer end (`end`), which FeaLoadLabels uses only where that end is in sight
        // and the label drawn there is clear of the model; a body load, drawn through the part, always stands outside.
        const { at, face } = labelOutside(chosen, box, placed.diagonal);
        const end = OUTSIDE_ONLY.has(kind) ? {} : { end: { at: chosen.free, face: chosen.anchor } };
        return { kind, group: index, text, at, face, ...end, ...(box ? { corners: boxCorners(box) } : {}) };
      }).filter(Boolean);
    },
    dispose() {
      group.removeFromParent();
      for (const mesh of meshes) mesh.dispose();
      for (const geometry of geometries) geometry.dispose();
      for (const material of [...Object.values(materials), ...extra.flatMap((entry) => entry.materials)]) material.dispose();
    },
  };
}
