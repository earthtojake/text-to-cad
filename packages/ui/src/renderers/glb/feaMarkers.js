/**
 * Where an FEA result's loads and fixtures act, drawn on the model as every FEA tool draws them:
 * arrows on each loaded face (along the force, or along the inward normal for a pressure), with a
 * label naming the load, and small cones on each fixed face pointing into it.
 *
 * The places are sampled once per result (`markerSites`): one to five per face, more on a bigger
 * face, spread over it, each a triangle of the face found by the result's `_FACE` attribute. Where
 * a marker stands is worked out from the positions on screen (`markerPoses`), so the markers follow
 * the deformation as it is drawn. The THREE objects (`createFeaMarkers`) are this module's: one
 * instanced mesh per kind, over the surface (no depth test), never picked, and disposed with it.
 */
import { clamp } from "@text-to-cad/core/common/numbers.js";
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

/** Each triangle of each face: `{ triangles: [[a, b, c]], areas, centroids }` by face index, from `_FACE`. */
function trianglesByFace(result, positions, wanted) {
  const geometry = result.mesh.geometry;
  const faceOf = geometry.getAttribute("_face")?.array;
  const index = geometry.getIndex()?.array;
  const byFace = new Map([...wanted].map((face) => [face, { triangles: [], areas: [], centroids: [] }]));
  if (!faceOf) return byFace;
  const count = index ? index.length / 3 : positions.length / 9;
  for (let t = 0; t < count; t += 1) {
    const corners = index ? [index[t * 3], index[t * 3 + 1], index[t * 3 + 2]] : [t * 3, t * 3 + 1, t * 3 + 2];
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
 * Where the result's markers stand: one entry per marker, `{ kind: "load" | "fixture", group, face,
 * ref, triangle }` (`group` the load's place among the loads with faces, as Study's rows number
 * them, or the fixture's; `face` the index into `faces`, `ref` its ref; `triangle` the three vertex
 * indices it stands on), and the model's `diagonal`. Sampled once, against the part at rest.
 */
export function markerSites(result) {
  const study = result.study;
  if (!study) return { diagonal: 0, sites: [] };
  const rest = restPositions(result);
  let low = [Infinity, Infinity, Infinity];
  let high = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < rest.length; i += 3) {
    low = [Math.min(low[0], rest[i]), Math.min(low[1], rest[i + 1]), Math.min(low[2], rest[i + 2])];
    high = [Math.max(high[0], rest[i]), Math.max(high[1], rest[i + 1]), Math.max(high[2], rest[i + 2])];
  }
  const diagonal = rest.length ? length(sub(high, low)) : 0;
  const groups = [
    ...study.loads.filter((load) => load.faces.length).map((load, group) => ({ kind: "load", group, refs: load.faces })),
    ...study.fixtures.map((fixture, group) => ({ kind: "fixture", group, refs: fixture.faces })),
  ];
  const faceIndex = (ref) => result.faces.indexOf(ref);
  const byFace = trianglesByFace(result, rest, new Set(groups.flatMap((entry) => entry.refs.map(faceIndex)).filter((face) => face >= 0)));
  const sites = [];
  for (const { kind, group, refs } of groups) {
    for (const ref of refs) {
      const face = faceIndex(ref);
      const entry = byFace.get(face);
      if (!entry?.triangles.length) continue;
      const area = entry.areas.reduce((sum, value) => sum + value, 0);
      const count = clamp(Math.ceil(Math.sqrt(area) / (SPREAD * (diagonal || 1))), 1, MAX_PER_FACE);
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

/**
 * Each marker at the positions on screen (`positions`, the mesh's own array): an arrow's `tip`,
 * `tail` and unit `direction` (the way it points); a cone's `tip` on the face and `direction` into
 * it. An arrow that pushes on its face (against the face's outward normal) has its tip on the face;
 * one that pulls stands on the face by its tail, pointing away. `normal` is the face's outward
 * normal there, from the triangle's winding.
 */
export function markerPoses(result, { diagonal, sites }, positions) {
  const loads = result.study ? result.study.loads.filter((load) => load.faces.length) : [];
  const arrow = ARROW_LENGTH * diagonal;
  return sites.map((site) => {
    const [a, b, c] = site.triangle.map((corner) => point(positions, corner));
    const at = scaled(plus(plus(a, b), c), 1 / 3);
    const normal = unit(cross(sub(b, a), sub(c, a)));
    if (site.kind === "fixture") return { ...site, normal, tip: at, direction: scaled(normal, -1) };
    const direction = loadDirection(loads[site.group], normal);
    const pushes = direction[0] * normal[0] + direction[1] * normal[1] + direction[2] * normal[2] <= 0;
    const tip = pushes ? at : plus(at, scaled(direction, arrow));
    return { ...site, normal, tip, tail: pushes ? plus(at, scaled(direction, 0 - arrow)) : at, direction };
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

/**
 * The THREE objects of a result's markers, added under the result mesh so they ride its transform:
 * `object3D` (a group), `update(positions)` to stand them on the positions on screen,
 * `style({ colours, visible: { loads, fixtures }, chosen })` (`chosen(site)` true for a marker of the
 * load or fixture chosen in Study), `labels()`: each load's text and where it goes (`at`, the middle
 * of its arrows' tails, and `tip`, of their tips, in the mesh's space), and `dispose()`.
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
  // Flat colour over the surface: depth neither tested nor written, drawn after the model.
  const material = () => new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false, depthWrite: false, toneMapped: false });
  const loadMaterial = material();
  const fixtureMaterial = material();
  const instanced = (geometry, mat, count) => {
    const mesh = new THREE.InstancedMesh(geometry, mat, Math.max(count, 1));
    mesh.count = count;
    mesh.renderOrder = 10;
    mesh.frustumCulled = false;
    mesh.raycast = () => {};
    group.add(mesh);
    return mesh;
  };
  const shafts = instanced(shaftGeometry, loadMaterial, loads.length);
  const heads = instanced(headGeometry, loadMaterial, loads.length);
  const cones = instanced(coneGeometry, fixtureMaterial, fixtures.length);
  const up = new THREE.Vector3(0, 1, 0);
  const matrix = new THREE.Matrix4();
  const rotation = new THREE.Quaternion();
  const at = new THREE.Vector3();
  const along = new THREE.Vector3();
  const one = new THREE.Vector3(1, 1, 1);
  const colour = new THREE.Color();
  let poses = [];

  const place = (mesh, index, pose) => {
    rotation.setFromUnitVectors(up, along.fromArray(pose.direction));
    matrix.compose(at.fromArray(pose.tip), rotation, one);
    mesh.setMatrixAt(index, matrix);
  };
  return {
    object3D: group,
    sites: placed.sites,
    update(positions) {
      poses = markerPoses(result, placed, positions);
      let load = 0;
      let fixture = 0;
      for (const pose of poses) {
        if (pose.kind === "load") { place(shafts, load, pose); place(heads, load, pose); load += 1; }
        else { place(cones, fixture, pose); fixture += 1; }
      }
      for (const mesh of [shafts, heads, cones]) mesh.instanceMatrix.needsUpdate = true;
    },
    poses: () => poses,
    style({ colours, visible, chosen }) {
      shafts.visible = heads.visible = visible.loads && loads.length > 0;
      cones.visible = visible.fixtures && fixtures.length > 0;
      loads.forEach((site, index) => {
        colour.set(chosen(site) ? HIGHLIGHT : colours.load);
        shafts.setColorAt(index, colour);
        heads.setColorAt(index, colour);
      });
      fixtures.forEach((site, index) => cones.setColorAt(index, colour.set(chosen(site) ? HIGHLIGHT : colours.fixture)));
      for (const mesh of [shafts, heads, cones]) if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    },
    labels(loadScale = 1) {
      const studyLoads = result.study ? result.study.loads.filter((entry) => entry.faces.length) : [];
      return studyLoads.map((entry, index) => {
        const arrows = poses.filter((pose) => pose.kind === "load" && pose.group === index);
        if (!arrows.length) return null;
        const middle = (key) => scaled(arrows.map((pose) => pose[key]).reduce(plus, [0, 0, 0]), 1 / arrows.length);
        return { group: index, text: loadLabel(entry, loadScale), at: middle("tail"), tip: middle("tip") };
      }).filter(Boolean);
    },
    dispose() {
      group.removeFromParent();
      for (const mesh of [shafts, heads, cones]) mesh.dispose();
      for (const geometry of [headGeometry, shaftGeometry, coneGeometry]) geometry.dispose();
      loadMaterial.dispose();
      fixtureMaterial.dispose();
    },
  };
}
