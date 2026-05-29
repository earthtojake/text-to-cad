// Standalone modal-vibration preview: loads a modal GLB (morph target + baked
// clip per mode, frequencies + material damping in extras) and offers two modes
// driven by the cadjs engine:
//   - Pluck (drag): grab a vertex, drag to deform as a min-strain-energy blend
//     of mode shapes, release to ring down at the material's damped natural
//     frequencies (slowed).
//   - Play mode: play a single mode's baked animation clip.
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { extractModalModes, formatModeLabel, ModalPlayer } from "cadjs/common/modalAnimation.js";
import { ModalInteractionController } from "cadjs/common/modalInteractionController.js";

const GLB_URL = new URLSearchParams(location.search).get("glb") || "/spring_pla.glb";
const DEFAULT_SLOWDOWN = 50;

const app = document.getElementById("app");
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
app.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0e1116);
const camera = new THREE.PerspectiveCamera(45, 1, 0.001, 1000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.HemisphereLight(0xffffff, 0x202830, 1.1));
const key = new THREE.DirectionalLight(0xffffff, 1.6);
key.position.set(1, 1.4, 1.2);
scene.add(key);
const fill = new THREE.DirectionalLight(0x88aaff, 0.5);
fill.position.set(-1, -0.4, -0.8);
scene.add(fill);

function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);
resize();

const ui = {
  title: document.getElementById("title"),
  modes: document.getElementById("modes"),
  slowdown: document.getElementById("slowdown"),
  slowval: document.getElementById("slowval"),
  damping: document.getElementById("damping"),
  dampval: document.getElementById("dampval"),
  reset: document.getElementById("reset"),
  hint: document.getElementById("hint"),
  status: document.getElementById("status"),
  modePluck: document.getElementById("mode-pluck"),
  modePlay: document.getElementById("mode-play"),
};

let mesh = null;
let modes = [];
let controller = null;
let player = null;
let interaction = "pluck"; // "pluck" | "play"
let activeModeIndex = null;
let dragging = false;

function frameObject(object) {
  const box = new THREE.Box3().setFromObject(object);
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  controls.target.copy(sphere.center);
  const dist = sphere.radius / Math.sin((camera.fov * Math.PI) / 180 / 2);
  camera.position.copy(sphere.center).add(new THREE.Vector3(0.6, 0.5, 1).normalize().multiplyScalar(dist * 1.4));
  camera.near = sphere.radius / 100;
  camera.far = sphere.radius * 100;
  camera.updateProjectionMatrix();
  controls.update();
}

function setInteraction(mode) {
  interaction = mode;
  ui.modePluck.setAttribute("aria-pressed", String(mode === "pluck"));
  ui.modePlay.setAttribute("aria-pressed", String(mode === "play"));
  ui.hint.textContent = mode === "pluck"
    ? "Drag any point on the part to deform it, then release to watch it ring down at its natural frequencies (slowed). Damping follows the material."
    : "Click a mode to play its baked vibration. Orbit with the mouse.";
  if (controller) controller.reset();
  if (player) player.pause();
  renderModeList();
}

function renderModeList() {
  ui.modes.innerHTML = "";
  modes.forEach((m) => {
    const el = document.createElement("div");
    el.className = "mode";
    el.setAttribute("role", "button");
    if (interaction === "play" && m.index === activeModeIndex) el.setAttribute("aria-current", "true");
    const left = document.createElement("span");
    left.textContent = formatModeLabel(m).replace(/\s—.*\(/, " (").replace(/^Mode /, "Mode ");
    const right = document.createElement("span");
    right.className = "freq";
    right.textContent = m.frequencyHz == null ? "" : `${m.frequencyHz.toFixed(m.frequencyHz < 100 ? 2 : 1)} Hz`;
    el.append(left, right);
    el.addEventListener("click", () => {
      if (interaction !== "play") setInteraction("play");
      activeModeIndex = m.index;
      player.selectMode(m.index);
      player.play();
      renderModeList();
    });
    ui.modes.appendChild(el);
  });
}

function ndc(event) {
  const r = renderer.domElement.getBoundingClientRect();
  return [((event.clientX - r.left) / r.width) * 2 - 1, -((event.clientY - r.top) / r.height) * 2 + 1];
}

function bindPointer() {
  const dom = renderer.domElement;
  dom.addEventListener("pointerdown", (e) => {
    if (interaction !== "pluck" || !controller) return;
    const [x, y] = ndc(e);
    if (controller.pickAtNDC(x, y)) {
      dragging = true;
      controls.enabled = false;
      dom.setPointerCapture(e.pointerId);
    }
  });
  dom.addEventListener("pointermove", (e) => {
    if (!dragging || !controller) return;
    const [x, y] = ndc(e);
    controller.dragToNDC(x, y);
  });
  const end = (e) => {
    if (!dragging) return;
    dragging = false;
    controls.enabled = true;
    controller.release();
    try { renderer.domElement.releasePointerCapture(e.pointerId); } catch {}
  };
  dom.addEventListener("pointerup", end);
  dom.addEventListener("pointercancel", end);
}

async function load() {
  const gltf = await new GLTFLoader().loadAsync(GLB_URL);
  scene.add(gltf.scene);
  gltf.scene.traverse((o) => { if (o.isMesh && o.morphTargetInfluences?.length) mesh = o; });
  if (!mesh) { ui.title.textContent = "No morph-target mesh in GLB"; return; }

  const meshExtras = gltf.parser?.json?.meshes?.[0]?.extras || {};
  modes = extractModalModes({ animations: gltf.animations, meshExtras });
  const damping = Number.isFinite(meshExtras.dampingRatio) ? meshExtras.dampingRatio : 0.01;
  const material = meshExtras.material || "material";
  const frequencies = modes.map((m) => m.frequencyHz || 0);

  controller = new ModalInteractionController({
    THREE, camera, mesh, frequencies, damping, slowdown: DEFAULT_SLOWDOWN,
  });
  player = new ModalPlayer({ THREE, root: gltf.scene, animations: gltf.animations, meshExtras });

  ui.title.textContent = `${material} · ${modes.length} modes · ζ=${damping}`;
  ui.slowdown.value = String(controller.slowdown);
  ui.slowval.textContent = controller.slowdown;
  ui.damping.value = String(damping);
  ui.dampval.textContent = damping;

  ui.slowdown.addEventListener("input", () => {
    ui.slowval.textContent = ui.slowdown.value;
    controller.setSlowdown(Number(ui.slowdown.value));
  });
  ui.damping.addEventListener("input", () => {
    ui.dampval.textContent = ui.damping.value;
    controller.setDamping(Number(ui.damping.value));
  });
  ui.reset.addEventListener("click", () => { controller.reset(); player.pause(); });
  ui.modePluck.addEventListener("click", () => setInteraction("pluck"));
  ui.modePlay.addEventListener("click", () => setInteraction("play"));

  frameObject(gltf.scene);
  bindPointer();
  setInteraction("pluck");
  ui.status.textContent = `loaded ${GLB_URL}`;
}

const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const dt = clock.getDelta();
  if (interaction === "pluck" && controller) controller.update(dt);
  if (interaction === "play" && player && player.playing) player.update(dt);
  controls.update();
  renderer.render(scene, camera);
}
animate();

load().catch((err) => { ui.title.textContent = "load error"; ui.status.textContent = String(err); });
