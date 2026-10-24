// A minimal viewer of one engine document: its structure as JSON, each part as one
// binary buffer read with typed-array views (no parsing), drawn once per instance at
// its placement. Hovering shows the element under the pointer and its name: a vertex or
// an edge within a few pixels of it (found in the hovered part's vertex and edge tables,
// on screen), else the face, whose triangle's index range is found in the face table.
// Clicking asks the server what the kernel measures of that element. A document with joints
// gets a Position panel: its configurations, a slider per pair value within its limits, and as
// built; the page poses the instances by forward kinematics over the structure's `kinematics`.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const MAGIC = 0x324d4258; // "XBM2", little-endian
const HEADER_BYTES = 80;
const CLASSES = { 1: "feature", 2: "tangent", 3: "seam", 5: "boundary", 6: "non-manifold" };
const EDGE_PIXELS = 5;
const VERTEX_PIXELS = 7;
const view = document.getElementById("view");
const statusLine = document.getElementById("status");
const titleLine = document.getElementById("title");
const hoverBox = document.getElementById("hover");

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
view.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() || "#f4f4f2");
const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.1, 1e7);
camera.up.set(0, 0, 1);
const controls = new OrbitControls(camera, renderer.domElement);
scene.add(new THREE.HemisphereLight(0xffffff, 0x606070, 2.2));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
scene.add(sun);
const root = new THREE.Group();
scene.add(root);
const overlay = new THREE.Group();
scene.add(overlay);
const highlight = new THREE.MeshBasicMaterial({ color: 0xff9a1f, depthTest: true, polygonOffset: true,
                                                polygonOffsetFactor: -1, polygonOffsetUnits: -4 });
const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x1a1a1a, transparent: true, opacity: 0.55 });
const softEdgeMaterial = new THREE.LineBasicMaterial({ color: 0x1a1a1a, transparent: true, opacity: 0.16 });
const edgeHighlight = new THREE.LineBasicMaterial({ color: 0xff5a00, depthTest: false });
const vertexHighlight = new THREE.PointsMaterial({ color: 0xff5a00, size: 9, sizeAttenuation: false, depthTest: false });

/** One part buffer as typed-array views over it: no copy, no parse. */
export function readPart(buffer) {
  const head = new DataView(buffer, 0, HEADER_BYTES);
  if (head.getUint32(0, true) !== MAGIC) throw new Error("not a part buffer");
  const [nodes, indices, faces, edges, points, vertices] = [8, 12, 16, 20, 24, 28].map((at) => head.getUint32(at, true));
  const offsets = [32, 36, 40, 44, 48, 52, 56].map((at) => head.getUint32(at, true));
  return {
    positions: new Float32Array(buffer, offsets[0], nodes * 3),
    normals: new Float32Array(buffer, offsets[1], nodes * 3),
    indices: new Uint32Array(buffer, offsets[2], indices),
    faces: new Uint32Array(buffer, offsets[3], faces * 3), // ordinal, first index, index count
    edges: new Uint32Array(buffer, offsets[4], edges * 4), // ordinal, first point, point count, class
    edgePoints: new Float32Array(buffer, offsets[5], points * 3),
    vertices: new Float32Array(buffer, offsets[6], vertices * 4), // ordinal, x, y, z
  };
}

const parts = new Map(); // key -> promise of { geometry, lineGeometry, softGeometry, buffer, ... }
let current = null; // the structure on screen
let docId = null;
let version = null;
let fitted = false;

function linearColor(rgba, fallback) {
  if (!rgba) return new THREE.Color(fallback);
  return new THREE.Color().setRGB(rgba[0], rgba[1], rgba[2], THREE.LinearSRGBColorSpace);
}

async function part(doc, key) {
  if (parts.has(key)) return parts.get(key);
  const pending = (async () => {
    const response = await fetch(`/api/doc/${doc}/part/${key}?format=2`);
    if (!response.ok) throw new Error(`part ${key}: ${response.status}`);
    const buffer = readPart(await response.arrayBuffer());
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(buffer.positions, 3));
    geometry.setAttribute("normal", new THREE.BufferAttribute(buffer.normals, 3));
    geometry.setIndex(new THREE.BufferAttribute(buffer.indices, 1));
    geometry.computeBoundingSphere();
    geometry.computeBoundingBox();
    // Every edge's segments, in edge-table order: edge row r is segments [starts[r], starts[r + 1]).
    const rows = buffer.edges.length / 4;
    const starts = new Uint32Array(rows + 1);
    const all = [], hard = [], soft = [];
    for (let row = 0; row < rows; row++) {
      starts[row] = all.length;
      const first = buffer.edges[row * 4 + 1], count = buffer.edges[row * 4 + 2], kind = buffer.edges[row * 4 + 3];
      const drawn = kind === 2 ? soft : kind === 3 ? null : hard; // tangent edges faint, seams not drawn
      for (let at = first; at < first + count - 1; at++) {
        all.push(at, at + 1);
        if (drawn) drawn.push(at, at + 1);
      }
    }
    starts[rows] = all.length;
    const points = new THREE.BufferAttribute(buffer.edgePoints, 3);
    const lines = (index) => {
      const made = new THREE.BufferGeometry();
      made.setAttribute("position", points);
      made.setIndex(index);
      return made;
    };
    let unmeshed = 0;
    for (let row = 0; row < buffer.faces.length; row += 3) if (buffer.faces[row + 2] === 0) unmeshed++;
    return { geometry, lineGeometry: lines(hard), softGeometry: lines(soft), allLines: lines(all), starts, buffer,
             unmeshed };
  })();
  parts.set(key, pending);
  pending.catch(() => parts.delete(key));
  return pending;
}

function dispose(key, held) {
  for (const geometry of [held.geometry, held.lineGeometry, held.softGeometry, held.allLines]) geometry.dispose();
  parts.delete(key);
}

/** The face table row whose index range holds index position ``at``. */
function faceAt(faces, at) {
  let low = 0, high = faces.length / 3 - 1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    const first = faces[middle * 3 + 1], count = faces[middle * 3 + 2];
    if (at < first) high = middle - 1;
    else if (at >= first + count) low = middle + 1;
    else return middle;
  }
  return -1;
}

const materials = new Map(); // look -> one material, shared by every instance of that look

// Every look field the structure serves for a material (``document.material_json``).
const LOOK = ["metallic", "roughness", "ior", "anisotropy", "anisotropyRotation", "transmission", "transmissionColor",
              "transmissionDepth", "coat", "coatRoughness", "emissive", "emissiveStrength"];
const number = (value, fallback) => (typeof value === "number" && Number.isFinite(value) ? value : fallback);

/** The material of one look: a colour and, where the document gives one, a material's
 * whole look as glTF carries it -- metallic, roughness, IOR, anisotropy and its rotation,
 * transmission (through ``thickness`` millimetres, attenuated by its colour over its depth in
 * metres), clear coat and its roughness, emission and its strength; without one, the
 * engine's matte default. */
function material(rgba, pbr, thickness = 0) {
  const look = pbr ? LOOK.map((field) => pbr[field] ?? null) : null;
  const name = JSON.stringify([rgba || null, look, look && number(pbr.transmission, 0) > 0 ? thickness : null]);
  let found = materials.get(name);
  if (!found) {
    if (!pbr) {
      found = new THREE.MeshStandardMaterial({ color: linearColor(rgba, 0xb8bcc4), roughness: 0.55, metalness: 0.05 });
    } else {
      found = new THREE.MeshPhysicalMaterial({
        color: linearColor(rgba, 0xb8bcc4), metalness: number(pbr.metallic, 0), roughness: number(pbr.roughness, 0.5),
        ior: number(pbr.ior, 1.5), anisotropy: number(pbr.anisotropy, 0),
        anisotropyRotation: number(pbr.anisotropyRotation, 0), clearcoat: number(pbr.coat, 0),
        clearcoatRoughness: number(pbr.coatRoughness, 0), emissive: linearColor(pbr.emissive, 0x000000),
        emissiveIntensity: number(pbr.emissiveStrength, 1),
      });
      if (number(pbr.transmission, 0) > 0) {
        found.transmission = pbr.transmission;
        found.thickness = Math.max(thickness, 0);
        if (number(pbr.transmissionDepth, 0) > 0) {
          found.attenuationDistance = pbr.transmissionDepth * 1000;
          found.attenuationColor = linearColor(pbr.transmissionColor || [1, 1, 1], 0xffffff);
        }
      }
    }
    if (rgba && rgba[3] < 1) {
      found.transparent = true;
      found.opacity = rgba[3];
    }
    materials.set(name, found);
  }
  return found;
}

/** A part's material in one colour: that colour's material or -- for a part with painted
 * faces -- that colour's then each paint's, its geometry grouped by face again whenever
 * its paints change (an edit of paints alone keeps the part's geometry). */
function materialOf(held, prototype, rgba) {
  const pbr = prototype.material;
  const painted = Object.entries(prototype.faceColors || {});
  const given = prototype.faceMaterials || {};
  // A transmissive look's volume is as thick as its part: the smallest extent of its box.
  const box = held.geometry.boundingBox;
  const thickness = box && !box.isEmpty() ? Math.min(...box.getSize(new THREE.Vector3()).toArray()) : 0;
  // An anisotropic look needs a tangent: one perpendicular to each normal will do.
  if ([pbr, ...Object.values(given)].some((look) => number(look?.anisotropy, 0) > 0) && !held.geometry.attributes.tangent) {
    held.geometry.setAttribute("tangent", new THREE.BufferAttribute(tangents(held.buffer.normals), 4));
  }
  if (!painted.length) return material(rgba, pbr, thickness);
  const signature = JSON.stringify([painted, given]);
  if (held.paintsFor !== signature) {
    held.paintsFor = signature;
    held.paints = [];
    held.geometry.clearGroups();
    const index = new Map();
    const byOrdinal = new Map(painted);
    for (let row = 0; row < held.buffer.faces.length; row += 3) {
      const ordinal = String(held.buffer.faces[row]);
      const paint = byOrdinal.get(ordinal);
      let at = 0;
      if (paint) {
        const look = [paint, given[ordinal] || null];
        const name = JSON.stringify(look);
        if (!index.has(name)) {
          index.set(name, held.paints.length + 1);
          held.paints.push(look);
        }
        at = index.get(name);
      }
      held.geometry.addGroup(held.buffer.faces[row + 1], held.buffer.faces[row + 2], at);
    }
  }
  return [material(rgba, pbr, thickness),
          ...held.paints.map(([paint, look]) => material(paint, look || pbr, thickness))];
}

/** A unit tangent per normal, perpendicular to it (w = 1). */
function tangents(normals) {
  const found = new Float32Array((normals.length / 3) * 4);
  for (let at = 0, to = 0; at + 2 < normals.length; at += 3, to += 4) {
    const x = normals[at], y = normals[at + 1], z = normals[at + 2];
    let tx = y, ty = -x, tz = 0;
    if (Math.hypot(tx, ty) < 1e-3) { tx = 0; ty = z; tz = -y; }
    const length = Math.hypot(tx, ty, tz);
    if (length > 0) { found[to] = tx / length; found[to + 1] = ty / length; found[to + 2] = tz / length; }
    else found[to] = 1;
    found[to + 3] = 1;
  }
  return found;
}

// The objects on screen by what places them -- part, path, colour and placement -- so a
// version that changed a few parts makes objects for those alone.
let placed = new Map();

async function show(doc) {
  const timing = {};
  let clock = performance.now();
  const response = await fetch(`/api/doc/${doc}`);
  const structure = await response.json();
  if (structure.error) throw new Error(structure.error);
  titleLine.textContent = structure.name;
  timing.structure = performance.now() - clock;
  const started = clock = performance.now();
  const loaded = await Promise.all(structure.prototypes.map((p) => part(doc, p.key)));
  timing.parts = performance.now() - clock;
  clock = performance.now();
  const next = new Map();
  const children = [];
  const byInstance = [];
  for (const instance of structure.instances) {
    const prototype = structure.prototypes[instance.prototype];
    const held = loaded[instance.prototype];
    const rgba = instance.color || prototype.color;
    const look = JSON.stringify([prototype.material, prototype.faceColors, prototype.faceMaterials]);
    const name = `${prototype.key}|${instance.path}|${rgba}|${look}|${instance.matrix.join(",")}`;
    let objects = placed.get(name);
    if (!objects) {
      objects = [new THREE.Mesh(held.geometry, materialOf(held, prototype, rgba))];
      for (const [geometry, lineMaterial] of [[held.lineGeometry, edgeMaterial], [held.softGeometry, softEdgeMaterial]]) {
        const lines = new THREE.LineSegments(geometry, lineMaterial);
        lines.raycast = () => {};
        objects.push(lines);
      }
      for (const object of objects) {
        object.matrixAutoUpdate = false;
        object.matrix.fromArray(instance.matrix);
        object.matrixWorldNeedsUpdate = true;
      }
    }
    objects[0].userData = { instance, prototype, held };
    next.set(name, objects);
    children.push(...objects);
    byInstance.push(objects);
  }
  clearHover();
  root.clear();
  for (let at = 0; at < children.length; at += 4096) root.add(...children.slice(at, at + 4096));
  placed = next;
  // Parts no longer in the document are let go.
  const wanted = new Set(structure.prototypes.map((p) => p.key));
  for (const [key, pending] of [...parts]) {
    if (!wanted.has(key)) pending.then((held) => dispose(key, held), () => {});
  }
  timing.scene = performance.now() - clock;
  current = structure;
  version = structure.version;
  const triangles = loaded.reduce((sum, held) => sum + held.geometry.index.count / 3, 0);
  const unmeshed = loaded.reduce((sum, held) => sum + held.unmeshed, 0);
  statusLine.textContent = `${structure.prototypes.length} parts, ${structure.instances.length} instances, ` +
    `${Math.round(triangles).toLocaleString()} triangles` +
    (unmeshed ? ` · ${unmeshed} unmeshed face${unmeshed === 1 ? "" : "s"}` : "") +
    ` · ${Math.round(performance.now() - started)} ms`;
  showPose(structure, byInstance);
  if (!fitted) {
    fit();
    fitted = true;
  }
  return timing;
}

// --- position --------------------------------------------------------------------------
//
// The structure's `kinematics` (the engine's `mechanism.py`): link 2 of a pair stands at
// link_1 · item_1 · M(v) · item_2⁻¹, M a turn about Z, a slide along Z, both, or an intrinsic
// X-Y-Z rotation. Each link's placement at the values over its placement as built moves its
// instances. A coupling's joints move only through it: they have no slider of their own here.

const poseBox = document.getElementById("pose");
const COUNT = { revolute: 1, prismatic: 1, cylindrical: 2, spherical: 3 };
const mat = (m) => new THREE.Matrix4().fromArray(m);
const turn = (axis, degrees) => new THREE.Matrix4()[["makeRotationX", "makeRotationY", "makeRotationZ"][axis]](degrees * Math.PI / 180);
function motion(type, v) {
  if (type === "revolute") return turn(2, v[0]);
  if (type === "prismatic") return new THREE.Matrix4().makeTranslation(0, 0, v[0]);
  if (type === "cylindrical") return new THREE.Matrix4().makeTranslation(0, 0, v[1]).multiply(turn(2, v[0]));
  return turn(0, v[0]).multiply(turn(1, v[1])).multiply(turn(2, v[2]));
}
const valuesOf = (value) => (Array.isArray(value) ? value.map(Number) : [Number(value)]);
function linkPlacements(kinematics, values) {
  const found = kinematics.links.map(() => null);
  found[kinematics.ground] = mat(kinematics.links[kinematics.ground].matrix);
  let pending = kinematics.pairs.filter((pair) => pair.frames);
  for (let progress = true; pending.length && progress;) {
    progress = false;
    pending = pending.filter((pair) => {
      const [a, b] = pair.links;
      // A pair with no value holds its links as built.
      const held = !values[pair.label];
      const [one, two] = held ? [mat(kinematics.links[a].matrix).invert(), mat(kinematics.links[b].matrix).invert()]
        : pair.frames.map(mat);
      const moved = held ? new THREE.Matrix4() : motion(pair.type, values[pair.label]);
      if (found[a] && !found[b]) found[b] = found[a].clone().multiply(one).multiply(moved).multiply(two.invert());
      else if (found[b] && !found[a]) found[a] = found[b].clone().multiply(two).multiply(moved.invert()).multiply(one.invert());
      else if (!found[a]) return true;
      progress = true;
      return false;
    });
  }
  return found.map((matrix, at) => matrix || mat(kinematics.links[at].matrix));
}
let pose = null; // { key, values }

function showPose(structure, byInstance) {
  const kinematics = structure.kinematics;
  poseBox.style.display = kinematics ? "block" : "none";
  if (!kinematics) return;
  const asBuilt = Object.fromEntries(Object.entries(kinematics.asBuilt).map(([label, value]) => [label, valuesOf(value)]));
  const coupled = new Map(Object.entries(kinematics.couplings || {}).flatMap(([name, coupling]) =>
    coupling.terms.map(([label]) => [label, name])));
  const key = JSON.stringify([kinematics.pairs, kinematics.configurations]);
  if (pose?.key !== key) pose = { key, values: structuredClone(asBuilt) };
  const reference = linkPlacements(kinematics, asBuilt);
  const warnings = kinematics.warnings || [];
  if (warnings.length) {
    statusLine.textContent += ` · ${warnings.length} kinematics warning${warnings.length === 1 ? "" : "s"}: ${warnings.join("; ")}`;
  }
  const unposable = new Map([...coupled].map(([label, name]) => [label, `it moves only with its coupling ${name}`]));
  for (const label of kinematics.loop || []) unposable.set(label, `pairs ${kinematics.loop.join(", ")} close a loop`);
  const apply = () => {
    const now = linkPlacements(kinematics, pose.values);
    kinematics.links.forEach((link, at) => {
      const delta = now[at].clone().multiply(reference[at].clone().invert());
      for (const index of link.instances) {
        for (const object of byInstance[index]) object.matrix.copy(delta).multiply(mat(structure.instances[index].matrix));
      }
    });
    clearHover();
  };
  poseBox.innerHTML = "";
  const title = document.createElement("b");
  title.textContent = "Position";
  poseBox.append(title);
  const preset = document.createElement("select");
  preset.setAttribute("aria-label", "Configuration");
  for (const name of ["as built", ...Object.keys(kinematics.configurations)]) preset.add(new Option(name, name));
  const reset = document.createElement("button");
  reset.textContent = "Reset";
  poseBox.append(" ", preset, " ", reset);
  const sliders = [];
  for (const pair of kinematics.pairs) {
    if (unposable.has(pair.label)) {
      const note = document.createElement("label");
      note.textContent = `${pair.label}: cannot be posed: ${unposable.get(pair.label)}`;
      poseBox.append(note);
      continue;
    }
    for (let index = 0; index < COUNT[pair.type]; index += 1) {
      const unit = pair.units[index];
      let [min, max] = pair.limits[index];
      min ??= max != null ? max - (unit === "deg" ? 360 : 100) : unit === "deg" ? -180 : -50;
      max ??= min + (unit === "deg" ? 360 : 100);
      const label = document.createElement("label");
      const slider = Object.assign(document.createElement("input"), { type: "range", min, max, step: unit === "deg" ? 1 : 0.1 });
      slider.setAttribute("aria-label", `${pair.label} ${index}`);
      const shown = () => { label.firstChild.textContent = `${pair.label}${COUNT[pair.type] > 1 ? ` ${index}` : ""}: ${pose.values[pair.label][index]} ${unit}`; };
      label.append(document.createTextNode(""), slider);
      slider.addEventListener("input", () => { pose.values[pair.label][index] = Number(slider.value); shown(); preset.value = ""; apply(); });
      sliders.push(() => { slider.value = pose.values[pair.label][index]; shown(); });
      poseBox.append(label);
    }
  }
  const sync = () => { for (const update of sliders) update(); apply(); };
  preset.addEventListener("change", () => {
    pose.values = structuredClone(asBuilt);
    for (const [label, value] of Object.entries(kinematics.configurations[preset.value] || {})) pose.values[label] = valuesOf(value);
    sync();
  });
  reset.addEventListener("click", () => { preset.value = "as built"; pose.values = structuredClone(asBuilt); sync(); });
  sync();
}

function fit() {
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const radius = box.getSize(new THREE.Vector3()).length() / 2 || 1;
  camera.position.copy(center).add(new THREE.Vector3(1.4, -1.8, 1.1).normalize().multiplyScalar(radius * 2.6));
  camera.near = radius / 1000;
  camera.far = radius * 100;
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
}

// --- hover ---------------------------------------------------------------------------

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let hovered = null; // { kind, ordinal, key }

function clearHover() {
  overlay.clear();
  hovered = null;
}

/** The nearest vertex and edge of one placed part to the pointer, on screen, that are
 * not behind the surface the pointer is on. */
function nearest(mesh, hitDistance, clientX, clientY) {
  const { held } = mesh.userData;
  const buffer = held.buffer;
  const matrix = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse)
    .multiply(mesh.matrixWorld);
  const m = matrix.elements;
  const world = mesh.matrixWorld.elements;
  const width = window.innerWidth, height = window.innerHeight;
  const eye = camera.position;
  const slack = hitDistance * 0.02;
  const screen = (x, y, z, out) => {
    const w = m[3] * x + m[7] * y + m[11] * z + m[15];
    out[0] = ((m[0] * x + m[4] * y + m[8] * z + m[12]) / w * 0.5 + 0.5) * width;
    out[1] = (-(m[1] * x + m[5] * y + m[9] * z + m[13]) / w * 0.5 + 0.5) * height;
    return w > 0;
  };
  const visible = (x, y, z) => {
    const wx = world[0] * x + world[4] * y + world[8] * z + world[12] - eye.x;
    const wy = world[1] * x + world[5] * y + world[9] * z + world[13] - eye.y;
    const wz = world[2] * x + world[6] * y + world[10] * z + world[14] - eye.z;
    return Math.sqrt(wx * wx + wy * wy + wz * wz) <= hitDistance + slack;
  };
  const a = [0, 0], b = [0, 0];
  let vertex = null;
  let best = VERTEX_PIXELS;
  const v = buffer.vertices;
  for (let at = 0; at < v.length; at += 4) {
    if (!screen(v[at + 1], v[at + 2], v[at + 3], a)) continue;
    const d = Math.hypot(a[0] - clientX, a[1] - clientY);
    if (d < best && visible(v[at + 1], v[at + 2], v[at + 3])) {
      best = d;
      vertex = { ordinal: v[at], position: [v[at + 1], v[at + 2], v[at + 3]] };
    }
  }
  if (vertex) return { vertex };
  let edge = null;
  best = EDGE_PIXELS;
  const p = buffer.edgePoints;
  const e = buffer.edges;
  for (let row = 0; row < e.length / 4; row++) {
    const first = e[row * 4 + 1], count = e[row * 4 + 2];
    for (let at = first; at < first + count - 1; at++) {
      if (!screen(p[at * 3], p[at * 3 + 1], p[at * 3 + 2], a) || !screen(p[at * 3 + 3], p[at * 3 + 4], p[at * 3 + 5], b)) continue;
      const dx = b[0] - a[0], dy = b[1] - a[1];
      const t = Math.max(0, Math.min(1, ((clientX - a[0]) * dx + (clientY - a[1]) * dy) / (dx * dx + dy * dy || 1)));
      const d = Math.hypot(a[0] + t * dx - clientX, a[1] + t * dy - clientY);
      if (d < best) {
        const x = p[at * 3] + t * (p[at * 3 + 3] - p[at * 3]);
        const y = p[at * 3 + 1] + t * (p[at * 3 + 4] - p[at * 3 + 1]);
        const z = p[at * 3 + 2] + t * (p[at * 3 + 5] - p[at * 3 + 2]);
        if (!visible(x, y, z)) continue;
        best = d;
        edge = { row, ordinal: e[row * 4], kind: e[row * 4 + 3] };
      }
    }
  }
  return edge ? { edge } : {};
}

function describe(head, lines) {
  hoverBox.style.display = "block";
  hoverBox.innerHTML = "";
  const title = document.createElement("b");
  title.textContent = head;
  hoverBox.append(title);
  for (const text of lines) {
    const line = document.createElement("div");
    line.textContent = text;
    hoverBox.append(line);
  }
}

/** The element under the pointer: a vertex or an edge within a few pixels of it, else the
 * face; with what to draw over it and what to say of it. */
function pick(event) {
  pointer.x = (event.clientX / window.innerWidth) * 2 - 1;
  pointer.y = -(event.clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects(root.children, true).find((found) => found.object.isMesh);
  if (!hit) return null;
  const mesh = hit.object;
  const { instance, prototype, held } = mesh.userData;
  const near = nearest(mesh, hit.distance, event.clientX, event.clientY);
  const placed = (object) => {
    object.matrixAutoUpdate = false;
    object.matrix.copy(mesh.matrix);
    object.renderOrder = 2;
    return object;
  };
  const target = { key: prototype.key, instance: instance.path };
  if (near.vertex) {
    return { ...target, kind: "vertex", ordinal: near.vertex.ordinal,
             head: `${instance.path} · vertex ${near.vertex.ordinal}`,
             lines: [near.vertex.position.map((value) => value.toFixed(3)).join(", ")],
             draw: () => {
               const point = new THREE.BufferGeometry();
               point.setAttribute("position", new THREE.Float32BufferAttribute(near.vertex.position, 3));
               return placed(new THREE.Points(point, vertexHighlight));
             } };
  }
  if (near.edge) {
    const { row, ordinal, kind } = near.edge;
    return { ...target, kind: "edge", ordinal, head: `${instance.path} · edge ${ordinal} · ${CLASSES[kind] || "edge"}`,
             lines: [(prototype.edgeNames || {})[String(ordinal)] || "(no element name)"],
             draw: () => {
               const line = placed(new THREE.LineSegments(held.allLines, edgeHighlight));
               line.onBeforeRender = (r, s, c, geometry) =>
                 geometry.setDrawRange(held.starts[row], held.starts[row + 1] - held.starts[row]);
               line.onAfterRender = (r, s, c, geometry) => geometry.setDrawRange(0, Infinity);
               return line;
             } };
  }
  const faces = held.buffer.faces;
  const row = faceAt(faces, hit.faceIndex * 3);
  if (row < 0) return null;
  const ordinal = faces[row * 3];
  return { ...target, kind: "face", ordinal, head: `${instance.path} · face ${ordinal}`,
           lines: [(prototype.faceNames || {})[String(ordinal)] || "(no element name)"],
           draw: () => {
             const face = placed(new THREE.Mesh(mesh.geometry, highlight));
             face.onBeforeRender = (r, s, c, geometry) => geometry.setDrawRange(faces[row * 3 + 1], faces[row * 3 + 2]);
             face.onAfterRender = (r, s, c, geometry) => geometry.setDrawRange(0, Infinity);
             return face;
           } };
}

function hover(event) {
  const target = pick(event);
  const same = (a, b) => a && b && a.key === b.key && a.instance === b.instance && a.kind === b.kind &&
    a.ordinal === b.ordinal;
  if (same(target, hovered)) return; // the same element: what is shown stays, its facts too
  clearHover();
  if (!target) {
    hoverBox.style.display = "none";
    return;
  }
  overlay.add(target.draw());
  hovered = target;
  describe(target.head, target.lines);
}

let queued = null;
renderer.domElement.addEventListener("pointermove", (event) => {
  if (queued === null) setTimeout(() => { hover(queued); queued = null; }, 0);
  queued = event;
});

/** A click asks the server what the kernel measures of the hovered element. */
renderer.domElement.addEventListener("click", async (event) => {
  hover(event);
  const target = hovered;
  if (!target || !docId) return;
  const facts = await (await fetch(`/api/doc/${docId}/part/${target.key}/${target.kind}/${target.ordinal}`)).json();
  if (hovered !== target) return;
  const lines = Object.entries(facts).filter(([name]) => !["kind", "ordinal"].includes(name))
    .map(([name, value]) => `${name}: ${JSON.stringify(value, (_k, v) => typeof v === "number" ? +v.toPrecision(6) : v)}`);
  describe(target.head, [...target.lines, ...lines]);
});

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

function frame() {
  sun.position.copy(camera.position);
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

/** Draw now, without waiting for an animation frame, and wait for the GPU to finish: the
 * moment the new geometry is on screen. (A hidden page gets no animation frames.) */
function drawNow() {
  sun.position.copy(camera.position);
  renderer.render(scene, camera);
  const gl = renderer.getContext();
  gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4));
}

// Each version the page drew after the first: when it noticed the version, when its first
// draw of it ended (epoch milliseconds), and the daemon's account of the patch.
const updates = [];

/** Wait on the server for a version other than the one shown; show it, timed. */
async function poll(doc) {
  let delay = 0;
  try {
    const response = await fetch(`/api/doc/${doc}/version?after=${encodeURIComponent(version)}&wait=25`);
    const answer = await response.json();
    if (answer.version && answer.version !== version) {
      const noticed = performance.now();
      const timing = await show(doc);
      const clock = performance.now();
      drawNow();
      const drawn = performance.now();
      timing.draw = drawn - clock;
      for (const name in timing) timing[name] = Math.round(timing[name]);
      updates.push({ version: answer.version, noticedAt: performance.timeOrigin + noticed,
                     drawnAt: performance.timeOrigin + drawn, ms: Math.round(drawn - noticed), timing,
                     patch: answer.patch });
    }
  } catch (error) {
    statusLine.textContent = String(error);
    delay = 1000;
  }
  setTimeout(() => poll(doc), delay);
}

async function start() {
  // The page of one document is ``/<id>``; ``/`` shows the last one served.
  let doc = /^\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(location.pathname) ? location.pathname.slice(1) : null;
  if (!doc) {
    const listing = await (await fetch("/api/docs")).json();
    doc = listing.length ? listing[listing.length - 1].id : null;
  }
  if (!doc) {
    statusLine.textContent = "no document is served";
    return;
  }
  docId = doc;
  await show(doc);
  window.__xbf = { scene, camera, controls, current: () => current, readPart, hover, hovered: () => hovered, updates,
                   pose: () => pose };
  requestAnimationFrame(frame);
  poll(doc);
}

start().catch((error) => { statusLine.textContent = String(error); });
