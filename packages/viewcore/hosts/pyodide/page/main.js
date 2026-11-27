// The demo page: a parametric model built in this tab by cad's build (kernel-worker.js), its .xbf read and meshed
// by the view core (../../web/worker.js), drawn with three.js. A slider writes its value into the script as cad's
// Save does (kernel.mjs withValues) and builds again.
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const $ = (id) => document.getElementById(id);
const seconds = (ms) => (ms / 1000).toFixed(2);

function connect(url) {
  const worker = new Worker(url, { type: "module" });
  const pending = new Map();
  let next = 1;
  const ready = new Promise((resolve) => {
    worker.onmessage = (event) => {
      if (event.data?.ready) return resolve();
      const waiting = pending.get(event.data.id);
      if (!waiting) return;
      pending.delete(event.data.id);
      event.data.ok ? waiting.resolve(event.data) : waiting.reject(new Error(event.data.error));
    };
  });
  worker.onerror = (event) => {
    for (const waiting of pending.values()) waiting.reject(new Error(event.message || `${url} failed to load`));
    pending.clear();
    say(event.message || `${url} failed to load`, true);
  };
  return async (op, args = {}, transfer = []) => {
    await ready;
    return new Promise((resolve, reject) => { const id = next++; pending.set(id, { resolve, reject }); worker.postMessage({ id, op, ...args }, transfer); });
  };
}

const state = { text: "", rows: [], timings: {}, structure: null, doc: null, xbfBytes: 0, builds: 0 };
const say = (text, bad = false) => { $("status").textContent = text; $("status").className = bad ? "bad" : ""; };

function showTimings() {
  const rows = [["Kernel: interpreter", "start"], ["Kernel: packages", "packages"], ["Kernel: imports", "imports"], ["View core ready", "core"],
    ["Build (cad's build)", "build"], ["Open the .xbf", "open"], ["Mesh every part", "mesh"], ["Slider to picture", "rebuild"]];
  $("timings").replaceChildren(...rows.filter(([, key]) => state.timings[key] != null).map(([label, key]) => {
    const row = document.createElement("tr");
    const a = document.createElement("td"); a.textContent = label;
    const b = document.createElement("td"); b.textContent = state.timings[key].toFixed(2);
    row.append(a, b); return row;
  }));
}

// --- the picture ---------------------------------------------------------------------------------------------
const renderer = new THREE.WebGLRenderer({ canvas: $("view"), antialias: true, preserveDrawingBuffer: true });
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 10000);
camera.up.set(0, 0, 1);
scene.add(new THREE.HemisphereLight(0xffffff, 0x556066, 0.6));
const key = new THREE.DirectionalLight(0xffffff, 1.4); key.position.set(-0.35, -1, 0.9); scene.add(key);
// A metal draws what it reflects: a plain room for it to reflect.
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.9;
const group = new THREE.Group(); scene.add(group);

function render() {
  const canvas = renderer.domElement;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(width, height, false);
  renderer.setClearColor(getComputedStyle(document.body).getPropertyValue("--bg").trim() || "#f2f4f5");
  camera.aspect = width / Math.max(1, height); camera.updateProjectionMatrix();
  renderer.render(scene, camera);
}
addEventListener("resize", render);

/** A part's XBM2 buffer as three.js geometry: its triangles, and its feature and boundary edges as lines. */
function geometries(buffer) {
  const u32 = new Uint32Array(buffer.buffer, buffer.byteOffset, 20);
  const [nodes, indices, , edges, points] = [u32[2], u32[3], u32[4], u32[5], u32[6]];
  const at = (slot) => buffer.byteOffset + u32[8 + slot];
  const faces = new THREE.BufferGeometry();
  faces.setAttribute("position", new THREE.BufferAttribute(new Float32Array(buffer.buffer, at(0), nodes * 3), 3));
  faces.setAttribute("normal", new THREE.BufferAttribute(new Float32Array(buffer.buffer, at(1), nodes * 3), 3));
  faces.setIndex(new THREE.BufferAttribute(new Uint32Array(buffer.buffer, at(2), indices), 1));
  const table = new Uint32Array(buffer.buffer, at(4), edges * 4);
  const polyline = new Float32Array(buffer.buffer, at(5), points * 3);
  const segments = [];
  for (let e = 0; e < edges; e++) {
    const [first, count, kind] = [table[4 * e + 1], table[4 * e + 2], table[4 * e + 3]];
    if (kind !== 1 && kind !== 5) continue; // feature and boundary edges (mesh_format's classes)
    for (let p = first; p + 1 < first + count; p++) segments.push(...polyline.subarray(3 * p, 3 * p + 6));
  }
  const lines = new THREE.BufferGeometry();
  lines.setAttribute("position", new THREE.BufferAttribute(new Float32Array(segments), 3));
  return { faces, lines };
}

function draw(structure, meshes) {
  for (const child of [...group.children]) { group.remove(child); }
  const made = new Map();
  for (const instance of structure.instances) {
    const prototype = structure.prototypes[instance.prototype];
    if (!made.has(prototype.key)) made.set(prototype.key, geometries(meshes.get(prototype.key)));
    const { faces, lines } = made.get(prototype.key);
    const rgba = instance.color || prototype.color || [0.8, 0.8, 0.8, 1];
    const look = prototype.material?.pbr?.values || {};
    const material = new THREE.MeshStandardMaterial({ metalness: look.metalness ?? 0, roughness: look.roughness ?? 0.6 });
    material.color.setRGB(rgba[0], rgba[1], rgba[2]); // the structure's colours are linear
    const part = new THREE.Group();
    part.add(new THREE.Mesh(faces, material), new THREE.LineSegments(lines, new THREE.LineBasicMaterial({ color: 0x1b252c })));
    part.matrixAutoUpdate = false;
    part.matrix.fromArray(instance.matrix);
    group.add(part);
  }
  group.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(group);
  const center = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3()).length();
  camera.position.copy(center).add(new THREE.Vector3(-0.9, -1.25, 0.8).normalize().multiplyScalar(size * 1.5));
  camera.near = size / 100; camera.far = size * 10;
  camera.lookAt(center);
  render();
}

// --- the two workers ---------------------------------------------------------------------------------------------
const kernel = connect("kernel-worker.js");
const view = connect("/web/worker.js");

async function show(xbf) {
  let t = performance.now();
  if (state.doc) await view("close", { doc: state.doc });
  state.xbfBytes = xbf.byteLength;
  state.xbfSha256 = [...new Uint8Array(await crypto.subtle.digest("SHA-256", xbf))].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  const opened = await view("open", { bytes: xbf, stem: "plate" }, [xbf.buffer]);
  state.doc = opened.result.doc;
  const structure = (await view("structure", { doc: state.doc })).result;
  state.timings.open = (performance.now() - t) / 1000;
  t = performance.now();
  const meshes = new Map();
  for (const prototype of structure.prototypes) {
    if (!meshes.has(prototype.key)) meshes.set(prototype.key, (await view("mesh", { doc: state.doc, part: prototype.index })).result);
  }
  state.timings.mesh = (performance.now() - t) / 1000;
  state.structure = structure;
  draw(structure, meshes);
}

async function build() {
  const built = (await kernel("build", { request: { name: "model.py", text: state.text } })).result;
  const report = built.reports[0];
  if (!report || report.ok === false) throw new Error(report?.error || "the build made nothing");
  state.rows = report.parameters || [];
  state.timings.build = built.seconds;
  state.builds += 1;
  state.heapBytes = built.heapBytes;
  await show(built.xbf);
}

function sliders() {
  $("parameters").replaceChildren(...(state.structure.parameters || []).map((parameter) => {
    const label = document.createElement("label");
    const name = document.createElement("span"); name.textContent = parameter.name;
    const value = document.createElement("output"); value.textContent = String(parameter.value);
    const input = document.createElement("input");
    input.type = "range"; input.id = `parameter-${parameter.name}`;
    input.min = parameter.min ?? 0; input.max = parameter.max ?? parameter.value * 2;
    input.step = parameter.step ?? (parameter.kind === "int" ? 1 : 0.1); input.value = parameter.value;
    input.addEventListener("input", () => { value.textContent = input.value; });
    input.addEventListener("change", () => set(parameter.name, Number(input.value)));
    label.append(name, value, input);
    return label;
  }));
}

let busy = Promise.resolve();
/** Set a parameter: written into the script as cad's Save writes it, the model built again and shown. */
function set(name, value) {
  busy = busy.then(async () => {
    const started = performance.now();
    say(`Building with ${name} = ${value}…`);
    const changed = (await kernel("withValues", { request: { name: "model.py", values: { [name]: value } } })).result;
    state.text = changed.text;
    await build();
    state.timings.rebuild = (performance.now() - started) / 1000;
    sliders(); showTimings();
    say(`Built in the tab: ${state.structure.prototypes.length} parts, .xbf ${(state.xbfBytes / 1024).toFixed(1)} KB.`);
  }).catch((error) => say(String(error.message || error), true));
  return busy;
}

$("step").addEventListener("click", async () => {
  const started = performance.now();
  const made = (await view("exportBytes", { doc: state.doc, format: "step" })).result;
  $("exported").textContent = `${(made.byteLength / 1024).toFixed(1)} KB in ${seconds(performance.now() - started)} s`;
  state.stepBytes = made.byteLength;
});

const ready = (async () => {
  const began = performance.now();
  const core = view("init", { url: new URL("/viewcore.wasm", location.href).href }).then(() => { state.timings.core = (performance.now() - began) / 1000; });
  const started = (await kernel("start", { base: new URL("/packages/", location.href).href, cad: "/cad.zip", kernelPy: "/host/kernel.py", pins: "/host/pins.json" })).result;
  Object.assign(state.timings, started.timings);
  state.shims = started.shims;
  await core;
  showTimings();
  say("Building the model…");
  state.text = await (await fetch("model.py")).text();
  await build();
  state.timings.first = (performance.now() - began) / 1000;
  sliders(); showTimings();
  $("step").disabled = false;
  say(`Built in the tab: ${state.structure.prototypes.length} parts, .xbf ${(state.xbfBytes / 1024).toFixed(1)} KB.`);
})().catch((error) => { say(String(error.message || error), true); throw error; });

// What a test drives: the first build's promise, a parameter set, and what the page holds.
window.demo = { ready, set, state };
