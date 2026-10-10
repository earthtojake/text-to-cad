/**
 * Where an FEA result's loads and fixtures act, drawn on the model as every FEA tool draws them:
 * arrows on each loaded face (along the force, or along the inward normal for a pressure), with a
 * label naming the load, and small cones on each fixed face pointing into it (on a roller's face,
 * the cone pressing on a small plate that rolls on the face, its sliding support). Other analyses add
 * their own kinds from one table (`MARKER_KINDS`): a body load's arrow through the model's middle,
 * a shaker's double arrows on the fixtures, a fixed temperature's dot, heat's wavy arrow, the air's
 * strokes, a drop's travel arrow, a flow's inlet and outlet arrows, a rigid floor's see-through
 * plane, a crack front's dots, a speaker face's cone and the sound rings off it, a piezo electrode's
 * plate and a rotor bearing's two races, each in the ink (what drives the part) or the muted grey (what holds or takes from it). An
 * analysis draws the kinds it lists (`markers`, ./fea/analyses), and one that draws fixtures draws
 * rollers too, so a static result with no roller is as it was.
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
import { feaAnalysis } from "./fea/analyses/index.js";
import { plainNumber } from "./fea/numbers.js";
import { axisWords, forceDirection } from "./fea/setup.js";
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
// A rigid floor's plane: see-through, this many diagonals across.
const PLANE_OPACITY = 0.14;
const PLANE_SIZE = 1.6;

/**
 * Every kind of marker, by name: what it is drawn as (`shape`), in which of the two tones (`tone`:
 * the ink of what drives the part, the muted grey of what holds it or takes from it), which of the
 * study's `view.show` switches it follows (`bucket`: loads or fixtures), where it stands (`on`: its
 * faces, the model's middle, a side of its box, a plane) and at most how many stand on one face
 * (`most`; `on: "front"` stands at a crack's front's stations). `phrase`: what Display's gate says of it.
 */
export const MARKER_KINDS = Object.freeze({
  load: Object.freeze({ shape: "arrow", tone: "load", bucket: "loads", on: "faces", most: MAX_PER_FACE, phrase: "arrows where the study loads the part" }),
  fixture: Object.freeze({ shape: "cone", tone: "fixture", bucket: "fixtures", on: "faces", most: MAX_PER_FACE, phrase: "cones where it holds it" }),
  roller: Object.freeze({ shape: "roller", tone: "fixture", bucket: "fixtures", on: "faces", most: MAX_PER_FACE, phrase: "cones on rollers where it may slide" }),
  body_load: Object.freeze({ shape: "arrow", tone: "load", bucket: "loads", on: "middle", most: 1, phrase: "an arrow through its middle for its weight" }),
  base_excitation: Object.freeze({ shape: "double_arrow", tone: "load", bucket: "loads", on: "faces", most: 1, phrase: "double arrows where it is shaken" }),
  temperature: Object.freeze({ shape: "dot", tone: "fixture", bucket: "fixtures", on: "faces", most: MAX_PER_FACE, phrase: "dots where its temperature is fixed" }),
  heat: Object.freeze({ shape: "wavy_arrow", tone: "load", bucket: "loads", on: "faces", most: 3, phrase: "wavy arrows where heat goes in" }),
  convection: Object.freeze({ shape: "strokes", tone: "fixture", bucket: "fixtures", on: "faces", most: 3, phrase: "strokes where air cools it" }),
  drop: Object.freeze({ shape: "arrow", tone: "load", bucket: "loads", on: "faces", most: 1, phrase: "an arrow the way it falls" }),
  inlet: Object.freeze({ shape: "arrow", tone: "load", bucket: "loads", on: "side", most: 1, phrase: "arrows where the flow comes in" }),
  outlet: Object.freeze({ shape: "arrow", tone: "fixture", bucket: "fixtures", on: "side", most: 1, phrase: "where it leaves" }),
  rigid_plane: Object.freeze({ shape: "plane", tone: "fixture", bucket: "fixtures", on: "plane", most: 1, phrase: "a see-through plane for the rigid floor" }),
  // A crack's front (fracture): a dot at each station along it, where its K was read.
  crack_front: Object.freeze({ shape: "dot", tone: "load", bucket: "loads", on: "front", most: 1, phrase: "dots along the crack's front" }),
  // A sound source's face (acoustic): a small speaker cone on it, opening off the face, and two rings of sound past it.
  speaker: Object.freeze({ shape: "speaker", tone: "load", bucket: "loads", on: "faces", most: 3, phrase: "speakers where sound is made" }),
  // A piezo electrode: a thin plate on its face with a terminal standing off it.
  electrode: Object.freeze({ shape: "electrode", tone: "load", bucket: "loads", on: "faces", most: 3, phrase: "plates on its electrodes" }),
  // A rotor's bearing on its faces: two races, one inside the other, lying on the face.
  bearing: Object.freeze({ shape: "bearing", tone: "fixture", bucket: "fixtures", on: "faces", most: 3, phrase: "rings where bearings carry the shaft" }),
});

/** A crack's front as the file records it (`extras.crack.front_mm`, CAD mm): its stations' points. [] for none. */
function crackFront(result) {
  const front = result.mesh?.userData?.crack?.front_mm;
  return Array.isArray(front) ? front.filter((point) => Array.isArray(point) && point.length === 3 && point.every((c) => Number.isFinite(c))) : [];
}

/** What Display's gate says it draws, over these kinds, in the table's order: "Arrows where the study loads the part, cones where it holds it." */
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
 * The study's entries each kind of marker stands for, in the order Study's rows number them
 * (`group`), each with the faces it stands on (`refs`; none for one that stands elsewhere): the
 * loads with faces, the fixtures (a roller's faces its own kind's, each numbered by its place among
 * every fixture, as Study's rows number it), a body load (gravity, an acceleration: a load with no faces), the
 * shaker (on the fixtures), the fixed temperatures, the heat, the air, the faces a drop lands on,
 * the flow's openings, the rigid planes, the crack front's stations, the speaker faces, the piezo
 * electrodes and the bearings. Only the kinds the result's analysis draws.
 */
function markerGroups(result) {
  const study = result.study;
  const drawn = new Set(feaAnalysis(result).markers);
  // A roller is a fixture that lets its face slide: wherever fixtures are drawn, so are rollers.
  if (drawn.has("fixture")) drawn.add("roller");
  const roller = (fixture) => fixture.type === "roller";
  const entries = (list) => list || [];
  const groups = {
    load: study.loads.filter((load) => load.faces.length).map((load) => load.faces),
    fixture: study.fixtures.map((fixture) => (roller(fixture) ? [] : fixture.faces)),
    roller: study.fixtures.map((fixture) => (roller(fixture) ? fixture.faces : [])),
    body_load: study.loads.filter((load) => !load.faces.length && load.g).map(() => []),
    base_excitation: study.excitation?.kind && study.excitation.kind !== "force" ? [study.fixtures.flatMap((fixture) => fixture.faces)] : [],
    temperature: entries(study.temperatures).map((entry) => entry.faces),
    heat: entries(study.heat).map((entry) => entry.faces),
    convection: entries(study.convection).map((entry) => entry.faces),
    drop: study.drop?.onto.length ? [study.drop.onto] : [],
    inlet: entries(study.flow?.inlets).map(() => []),
    outlet: entries(study.flow?.outlets).map(() => []),
    rigid_plane: [...entries(study.rigidPlanes), ...(study.drop?.floor === "rigid" ? [{ floor: true }] : [])].map(() => []),
    crack_front: crackFront(result).map(() => []),
    speaker: entries(study.acoustic?.sources).filter((source) => source.faces.length).map((source) => source.faces),
    electrode: entries(study.piezo?.electrodes).filter((entry) => entry.faces.length).map((entry) => entry.faces),
    // Every bearing on faces is one group: Study names them in one row.
    bearing: [entries(study.rotor?.bearings).flatMap((entry) => (Array.isArray(entry.faces) ? entry.faces.filter((ref) => typeof ref === "string") : []))]
      .filter((refs) => refs.length),
  };
  return Object.keys(MARKER_KINDS).filter((kind) => drawn.has(kind))
    .flatMap((kind) => groups[kind].map((refs, group) => ({ kind, group, refs })));
}

/**
 * Where the result's markers stand: one entry per marker, `{ kind, group, face, ref, triangle }`
 * (`kind` one of `MARKER_KINDS`; `group` the study entry's place among its kind's, as Study's rows
 * number them; `face` the index into `faces`, `ref` its ref and `triangle` the three vertex indices
 * it stands on, for a marker on a face; -1, null and null for one that stands elsewhere: the
 * model's middle, a side of its box, a plane), and the model's `diagonal`. Sampled once, against the
 * part at rest; loads first, then fixtures, then each other kind in the table's order.
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

// An opening names a side of the part's box in CAD axes; the mesh's are (x, z, -y), so CAD y runs
// along the mesh's z the other way round.
const OPENING_AXES = Object.freeze({ x: [0, 1], y: [2, -1], z: [1, 1] });

/** The middle of the box's side an opening names ("x_min"), and the unit vector out of the box through it; null for a name that is no side. */
function openingSide(opening, box) {
  const match = /^([xyz])_(min|max)$/.exec(String(opening || ""));
  if (!match) return null;
  const [axis, sign] = OPENING_AXES[match[1]];
  const outward = (match[2] === "max" ? 1 : -1) * sign;
  const at = [...box.centre];
  at[axis] = outward > 0 ? box.high[axis] : box.low[axis];
  const out = [0, 0, 0];
  out[axis] = outward;
  return { at, out };
}

/**
 * Where a marker that stands off the faces is: a body load's arrow through the model's middle, along
 * the load; an opening's arrow at the middle of its side, into the box for an inlet and out of it
 * for an outlet (an external flow's one inlet upstream of the part, along the flow); a rigid plane
 * at its point (a floor under a drop, through the lowest point along the fall), facing along its normal.
 */
function offFacePose(result, site, box, positions, arrow) {
  const study = result.study;
  if (site.kind === "body_load") {
    const load = study.loads.filter((entry) => !entry.faces.length && entry.g)[site.group];
    const direction = unit(gltfAxes(load.g));
    return { ...site, tip: plus(box.centre, scaled(direction, arrow / 2)), tail: plus(box.centre, scaled(direction, 0 - arrow / 2)), direction, pushes: true };
  }
  if (site.kind === "inlet" || site.kind === "outlet") {
    const opening = (site.kind === "inlet" ? study.flow.inlets : study.flow.outlets)[site.group];
    const side = openingSide(opening.opening, box);
    if (side) {
      const into = scaled(side.out, -1);
      return site.kind === "inlet"
        ? { ...site, tip: side.at, tail: plus(side.at, scaled(into, 0 - arrow)), direction: into, pushes: true }
        : { ...site, tip: plus(side.at, scaled(side.out, arrow)), tail: side.at, direction: side.out, pushes: false };
    }
    // An external flow: upstream of the part, along the flow.
    const along = opening.velocity ? unit(gltfAxes(opening.velocity)) : [1, 0, 0];
    const reach = Math.abs(along[0]) * (box.high[0] - box.low[0]) + Math.abs(along[1]) * (box.high[1] - box.low[1]) + Math.abs(along[2]) * (box.high[2] - box.low[2]);
    const tip = plus(box.centre, scaled(along, 0 - reach / 2 - arrow * 0.25));
    return { ...site, tip, tail: plus(tip, scaled(along, 0 - arrow)), direction: along, pushes: true };
  }
  // A crack's front: a dot at each of its stations, where the file puts it (CAD mm, in the mesh's metres and axes).
  if (site.kind === "crack_front") {
    const at = gltfAxes(scaled(crackFront(result)[site.group], 0.001));
    return { ...site, tip: at, direction: [0, 1, 0] };
  }
  // A rigid plane: its own point and normal, or under a drop, through the lowest point along the fall.
  const plane = study.rigidPlanes?.[site.group];
  if (plane) return { ...site, tip: gltfAxes(scaled(plane.point, 0.001)), direction: unit(gltfAxes(plane.normal)) };
  const fall = study.drop?.direction ? unit(gltfAxes(study.drop.direction)) : [0, -1, 0];
  let deepest = 0;
  let lowest = box.centre;
  for (let i = 0; i < positions.length; i += 3) {
    const reach = positions[i] * fall[0] + positions[i + 1] * fall[1] + positions[i + 2] * fall[2];
    if (i === 0 || reach > deepest) { deepest = reach; lowest = [positions[i], positions[i + 1], positions[i + 2]]; }
  }
  return { ...site, tip: lowest, direction: scaled(fall, -1) };
}

/**
 * Each marker at the positions on screen (`positions`, the mesh's own array): an arrow's `tip`,
 * `tail`, unit `direction` (the way it points) and whether it `pushes`; a cone's `tip` on the face and `direction` into
 * it. An arrow that pushes on its face (against the face's outward normal) has its tip on the face;
 * one that pulls stands on the face by its tail, pointing away. `normal` is the face's outward
 * normal there, from the triangle's winding. A roller stands as a fixture's cone does. The other kinds: a shaker's double arrow stands off
 * its fixture along the shake (`tip` one end, `tail` the other); a temperature's dot sits on its
 * face; heat's wavy arrow points into its face, its tip on it; the air's strokes rise off their
 * face; a drop's arrow stands on the face that lands, pointing the way it falls. A speaker stands on
 * its face opening off it (`direction` the outward normal); an electrode's plate and a bearing's races
 * lie on their face as a fixture's cone does.
 */
export function markerPoses(result, { diagonal, sites }, positions) {
  const loads = result.study ? result.study.loads.filter((load) => load.faces.length) : [];
  const arrow = ARROW_LENGTH * diagonal;
  const box = sites.some((site) => !site.triangle) ? boxOf(positions) : null;
  return sites.map((site) => {
    if (!site.triangle) return offFacePose(result, site, box, positions, arrow);
    const [a, b, c] = site.triangle.map((corner) => point(positions, corner));
    const at = scaled(plus(plus(a, b), c), 1 / 3);
    const normal = unit(cross(sub(b, a), sub(c, a)));
    if (["fixture", "roller", "temperature", "electrode", "bearing"].includes(site.kind)) return { ...site, normal, tip: at, direction: scaled(normal, -1) };
    if (site.kind === "speaker") return { ...site, normal, tip: at, direction: normal, pushes: false };
    if (site.kind === "convection") return { ...site, normal, tip: at, tail: plus(at, scaled(normal, arrow)), direction: normal };
    if (site.kind === "heat") return { ...site, normal, tip: at, tail: plus(at, scaled(normal, arrow)), direction: scaled(normal, -1), pushes: true };
    if (site.kind === "base_excitation") {
      const shake = result.study.excitation?.direction ? unit(gltfAxes(result.study.excitation.direction)) : [0, 1, 0];
      const middle = plus(at, scaled(normal, arrow * 0.6));
      return { ...site, normal, tip: plus(middle, scaled(shake, arrow / 2)), tail: plus(middle, scaled(shake, 0 - arrow / 2)), direction: shake, pushes: false };
    }
    if (site.kind === "drop") {
      const fall = result.study.drop?.direction ? unit(gltfAxes(result.study.drop.direction)) : normal;
      return { ...site, normal, tip: plus(at, scaled(fall, arrow)), tail: at, direction: fall, pushes: false };
    }
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

/** A drop's height in words: "1 m drop", "500 mm drop". */
export function dropWords(heightMm) {
  const h = Number(heightMm) || 0;
  return h >= 1000 ? `${labelNumber(h / 1000)} m drop` : `${labelNumber(h)} mm drop`;
}

/** What the shaker does, in words: "shaken 1 g along Z", "shaken at random along Z", "a shock along Z". */
export function shakeWords(excitation, loadScale = 1) {
  const along = excitation.direction ? axisWords(excitation.direction) : "";
  const way = along ? ` along ${along}` : "";
  if (excitation.kind === "psd") return `shaken at random${way}`;
  if (excitation.kind === "srs") return `a shock${way}`;
  return excitation.amplitudeG !== null ? `shaken ${labelNumber(excitation.amplitudeG * loadScale)} g${way}` : `shaken${way}`;
}

/** What a heat input's label says: "15 W", "2000 W/m²". */
export const heatWords = (heat) => (heat.watts !== null ? `${plainNumber(heat.watts)} W` : heat.fluxWm2 !== null ? `${plainNumber(heat.fluxWm2)} W/m²` : "heat");

/**
 * Each marker kind's label at `loadScale` times the solved load, by its study entry: a load's and a
 * body load's amount, the shaker's, a fixed temperature, a heat input, the air's temperature, the
 * drop's height, an opening's speed or pressure; "" for one that says nothing (a fixture, a plane).
 */
function labelText(result, kind, group, loadScale) {
  const study = result.study;
  if (kind === "load") return loadLabel(study.loads.filter((entry) => entry.faces.length)[group], loadScale);
  if (kind === "body_load") return bodyLoadLabel(study.loads.filter((entry) => !entry.faces.length && entry.g)[group], loadScale);
  if (kind === "base_excitation") return shakeWords(study.excitation, loadScale);
  if (kind === "temperature") return study.temperatures[group].celsius !== null ? `${plainNumber(study.temperatures[group].celsius)} °C` : "";
  if (kind === "heat") return heatWords(study.heat[group]);
  if (kind === "convection") return study.convection[group].ambientC !== null ? `air ${plainNumber(study.convection[group].ambientC)} °C` : "air";
  if (kind === "drop") return study.drop.heightMm !== null ? dropWords(study.drop.heightMm) : "";
  if (kind === "inlet") return study.flow.inlets[group].speed !== null ? `${plainNumber(study.flow.inlets[group].speed)} m/s` : "";
  if (kind === "outlet") return study.flow.outlets[group].pressure !== null ? `${plainNumber(study.flow.outlets[group].pressure)} Pa` : "";
  if (kind === "speaker") {
    const source = study.acoustic.sources.filter((entry) => entry.faces.length)[group];
    return source.velocityMmS !== null ? `${plainNumber(source.velocityMmS)} mm/s` : "";
  }
  if (kind === "electrode") {
    const electrode = study.piezo.electrodes.filter((entry) => entry.faces.length)[group];
    return electrode.open || electrode.volts === null ? "open" : `${plainNumber(electrode.volts)} V`;
  }
  return "";
}

/**
 * Where a marker's label goes: past its free end, away from where it acts (`free`, `anchor`). An
 * arrow's free end is a push's tail or a pull's tip; a dot's and the air's are off the face along
 * its normal; heat's is its tail; a shaker's one end of its double arrow.
 */
function labelEnds(pose, arrow) {
  if (pose.kind === "temperature" || pose.kind === "electrode") return { free: plus(pose.tip, scaled(pose.normal, arrow * 0.35)), anchor: pose.tip };
  if (pose.kind === "speaker") return { free: plus(pose.tip, scaled(pose.normal, arrow * 0.9)), anchor: pose.tip };
  if (pose.kind === "convection") return { free: plus(pose.tip, scaled(pose.normal, arrow * 0.9)), anchor: pose.tip };
  if (pose.kind === "base_excitation") return { free: pose.tip, anchor: pose.tail };
  return { free: pose.pushes ? pose.tail : pose.tip, anchor: pose.pushes ? pose.tip : pose.tail };
}

/** A wave of `periods` swings from `from` to `to` along Y at `x`, as points for a tube. */
function wavePoints(THREE, from, to, amplitude, periods, x = 0) {
  return Array.from({ length: 25 }, (_, i) => {
    const t = i / 24;
    return new THREE.Vector3(x + amplitude * Math.sin(t * periods * 2 * Math.PI), from + (to - from) * t, 0);
  });
}

/**
 * The THREE objects of a result's markers, added under the result mesh so they ride its transform:
 * `object3D` (a group), `update(positions)` to stand them on the positions on screen,
 * `style({ colours, visible: { loads, fixtures }, chosen })` (`chosen(site)` true for a marker of the
 * entry chosen in Study), `labels(loadScale, visible)`: each entry's text and where it goes (`at`,
 * the middle of its markers' free ends, off the part, and `face`, of the ends where it acts, in the
 * mesh's space; `kind` and `group` say whose), `kinds` (the kinds it draws) and `dispose()`.
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
    double_arrow: () => {
      const shaft = new THREE.CylinderGeometry(arrowLength * 0.035, arrowLength * 0.035, arrowLength - 2 * head, 10);
      shaft.translate(0, -arrowLength / 2, 0);
      const back = new THREE.ConeGeometry(arrowLength * 0.1, head, 16);
      back.rotateX(Math.PI);
      back.translate(0, -arrowLength + head / 2, 0);
      geometries.push(shaft, back);
      return [["shafts", shaft], ["heads", headGeometry], ["tails", back]];
    },
    dot: () => {
      const dot = new THREE.SphereGeometry(arrowLength * 0.12, 14, 10);
      geometries.push(dot);
      return [["dots", dot]];
    },
    wavy_arrow: () => {
      const wave = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(wavePoints(THREE, -arrowLength, -head, arrowLength * 0.07, 2)), 48, arrowLength * 0.03, 6);
      geometries.push(wave);
      return [["shafts", wave], ["heads", headGeometry]];
    },
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
    // A speaker: a small cone, its point on the face and its mouth off it, and two rings of sound past it, wider as they go.
    speaker: () => {
      const depth = arrowLength * 0.25;
      const cone = new THREE.ConeGeometry(arrowLength * 0.13, depth, 16);
      cone.rotateX(Math.PI);
      cone.translate(0, depth / 2, 0);
      const ring = (radius, height) => {
        const torus = new THREE.TorusGeometry(radius, arrowLength * 0.022, 6, 32);
        torus.rotateX(Math.PI / 2);
        torus.translate(0, height, 0);
        return torus;
      };
      const rings = [ring(arrowLength * 0.17, arrowLength * 0.42), ring(arrowLength * 0.24, arrowLength * 0.62)];
      geometries.push(cone, ...rings);
      return [["cones", cone], ["waves", rings[0]], ["waves-2", rings[1]]];
    },
    // An electrode: a thin plate on the face, a stem and a ball terminal off it (the face is along +Y, into the part).
    electrode: () => {
      const thick = arrowLength * 0.03;
      const plate = new THREE.CylinderGeometry(arrowLength * 0.16, arrowLength * 0.16, thick, 20);
      plate.translate(0, -thick / 2, 0);
      const stem = new THREE.CylinderGeometry(arrowLength * 0.02, arrowLength * 0.02, arrowLength * 0.12, 8);
      stem.translate(0, -thick - arrowLength * 0.06, 0);
      const knob = new THREE.SphereGeometry(arrowLength * 0.045, 12, 8);
      knob.translate(0, -thick - arrowLength * 0.12, 0);
      geometries.push(plate, stem, knob);
      return [["plates", plate], ["stems", stem], ["knobs", knob]];
    },
    // A bearing: an outer and an inner race lying on the face.
    bearing: () => {
      const race = (radius, tube) => {
        const torus = new THREE.TorusGeometry(radius, tube, 8, 32);
        torus.rotateX(Math.PI / 2);
        torus.translate(0, -tube, 0);
        return torus;
      };
      const outer = race(arrowLength * 0.17, arrowLength * 0.03);
      const inner = race(arrowLength * 0.09, arrowLength * 0.025);
      geometries.push(outer, inner);
      return [["races", outer], ["races-2", inner]];
    },
    strokes: () => {
      const stroke = (x) => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(wavePoints(THREE, arrowLength * 0.15, arrowLength * 0.75, arrowLength * 0.05, 1.5, x)), 40, arrowLength * 0.025, 6);
      const pair = [stroke(-arrowLength * 0.12), stroke(arrowLength * 0.12)];
      geometries.push(...pair);
      return [["strokes", pair[0]], ["strokes-2", pair[1]]];
    },
  };
  const extra = Object.keys(MARKER_KINDS).filter((kind) => kind !== "load" && kind !== "fixture" && MARKER_KINDS[kind].shape !== "plane")
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
  // A rigid plane: one see-through quad each, never ghosted (it is see-through already), facing along its normal.
  const planeSites = placed.sites.filter((site) => site.kind === "rigid_plane");
  const planeMaterial = planeSites.length ? new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: PLANE_OPACITY, side: THREE.DoubleSide,
    depthWrite: false, toneMapped: false }) : null;
  const planeGeometry = planeSites.length ? new THREE.PlaneGeometry(PLANE_SIZE * placed.diagonal, PLANE_SIZE * placed.diagonal) : null;
  if (planeGeometry) geometries.push(planeGeometry);
  const planes = planeSites.map((site, index) => {
    const mesh = new THREE.Mesh(planeGeometry, planeMaterial);
    mesh.name = `fea-rigid-plane-${index}`;
    mesh.renderOrder = 9;
    mesh.raycast = () => {};
    group.add(mesh);
    return mesh;
  });

  const up = new THREE.Vector3(0, 1, 0);
  const facing = new THREE.Vector3(0, 0, 1);
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
    ghostOf.get(mesh).setMatrixAt(index, matrix);
  };
  const paint = (mesh, index, tone) => { mesh.setColorAt(index, tone); ghostOf.get(mesh).setColorAt(index, tone); };
  return {
    object3D: group,
    sites: placed.sites,
    kinds: [...new Set(placed.sites.map((site) => site.kind))],
    update(positions) {
      poses = markerPoses(result, placed, positions);
      let load = 0;
      let fixture = 0;
      const counts = new Map();
      for (const pose of poses) {
        if (pose.kind === "load") { place(shafts, load, pose); place(heads, load, pose); load += 1; }
        else if (pose.kind === "fixture") { place(cones, fixture, pose); fixture += 1; }
        else if (pose.kind === "rigid_plane") {
          const plane = planes[planeSites.findIndex((site) => site.group === pose.group)];
          // The plane's middle is where the model's middle falls on it.
          const box = boxOf(positions);
          const normal = pose.direction;
          const offset = (box.centre[0] - pose.tip[0]) * normal[0] + (box.centre[1] - pose.tip[1]) * normal[1] + (box.centre[2] - pose.tip[2]) * normal[2];
          plane.position.fromArray(plus(box.centre, scaled(normal, 0 - offset)));
          plane.quaternion.setFromUnitVectors(facing, along.fromArray(normal));
        } else {
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
      shafts.visible = heads.visible = ghostShafts.visible = ghostHeads.visible = visible.loads && loads.length > 0;
      cones.visible = ghostCones.visible = visible.fixtures && fixtures.length > 0;
      loads.forEach((site, index) => {
        colour.set(chosen(site) ? HIGHLIGHT : colours.load);
        paint(shafts, index, colour);
        paint(heads, index, colour);
      });
      fixtures.forEach((site, index) => paint(cones, index, colour.set(chosen(site) ? HIGHLIGHT : colours.fixture)));
      for (const entry of extra) {
        const shown = visible[MARKER_KINDS[entry.kind].bucket] === true;
        for (const mesh of entry.parts) {
          mesh.visible = ghostOf.get(mesh).visible = shown;
          entry.sites.forEach((site, index) => paint(mesh, index, colour.set(chosen(site) ? HIGHLIGHT : colours[entry.tone])));
        }
      }
      planes.forEach((plane, index) => {
        plane.visible = visible.fixtures === true;
        planeMaterial.color.set(chosen(planeSites[index]) ? HIGHLIGHT : colours.fixture);
      });
      for (const mesh of meshes) if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    },
    labels(loadScale = 1, visible = { loads: true, fixtures: true }) {
      const entries = [];
      for (const pose of poses) {
        if (visible[MARKER_KINDS[pose.kind].bucket] !== true || pose.kind === "rigid_plane" || pose.kind === "fixture" || pose.kind === "crack_front") continue;
        let entry = entries.find((item) => item.kind === pose.kind && item.group === pose.group);
        if (!entry) entries.push(entry = { kind: pose.kind, group: pose.group, ends: [] });
        entry.ends.push(labelEnds(pose, arrowLength));
      }
      return entries.map(({ kind, group: index, ends }) => {
        const text = labelText(result, kind, index, loadScale);
        if (!text) return null;
        // The label stands past the markers' free end, off the part: a push's tails, a pull's tips.
        const middle = (pick) => scaled(ends.map(pick).reduce(plus, [0, 0, 0]), 1 / ends.length);
        return { kind, group: index, text, at: middle((end) => end.free), face: middle((end) => end.anchor) };
      }).filter(Boolean);
    },
    dispose() {
      group.removeFromParent();
      for (const mesh of meshes) mesh.dispose();
      for (const geometry of geometries) geometry.dispose();
      for (const material of [...Object.values(materials), ...extra.flatMap((entry) => entry.materials), ...(planeMaterial ? [planeMaterial] : [])]) material.dispose();
    },
  };
}
