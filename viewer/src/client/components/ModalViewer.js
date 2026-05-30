import { forwardRef, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { extractModalModes, formatModeLabel, ModalPlayer } from "cadjs/common/modalAnimation.js";
import { ModalInteractionController } from "cadjs/common/modalInteractionController.js";

const DEFAULT_SLOWDOWN = 50;

const MODAL_VIEWER_CSS = `
.modal-vib-panel { position:absolute; top:12px; left:12px; width:260px; max-height:calc(100% - 24px);
  display:flex; flex-direction:column; background:rgba(20,24,31,0.92); border:1px solid #2a313c;
  border-radius:12px; overflow:hidden; box-shadow:0 8px 30px rgba(0,0,0,0.4); color:#e6edf3;
  font:12px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; z-index:5; }
.modal-vib-head { display:flex; align-items:center; justify-content:space-between; gap:8px;
  padding:10px 12px; font-size:13px; }
.modal-vib-head button { background:transparent; border:none; color:#9aa7b4; cursor:pointer; font-size:16px; }
.modal-vib-body { padding:0 12px 12px; overflow-y:auto; -webkit-overflow-scrolling:touch; }
.modal-vib-seg { display:flex; gap:6px; margin-bottom:10px; }
.modal-vib-seg button { flex:1; padding:6px 8px; border-radius:8px; border:1px solid #2f3744;
  background:#161b22; color:#c9d4df; cursor:pointer; font-size:12px; }
.modal-vib-seg button[aria-pressed="true"] { background:#2563eb; border-color:#2563eb; color:#fff; }
.modal-vib-modes { max-height:160px; overflow:auto; margin-bottom:6px; }
.modal-vib-modes button { display:flex; width:100%; justify-content:space-between; gap:8px;
  padding:5px 8px; border-radius:7px; border:1px solid transparent; background:transparent;
  color:#e6edf3; cursor:pointer; font-size:12px; text-align:left; }
.modal-vib-modes button[aria-current="true"] { background:#11203a; border-color:#2563eb; }
.modal-vib-modes .freq { color:#7fd1ff; font-variant-numeric:tabular-nums; }
.modal-vib-row { display:flex; align-items:center; justify-content:space-between; gap:8px;
  margin:8px 0; color:#9aa7b4; }
.modal-vib-row input[type=range] { width:46%; accent-color:#2563eb; }
.modal-vib-check input { width:18px; height:18px; accent-color:#2563eb; }
.modal-vib-hint { color:#9aa7b4; font-size:11.5px; margin:8px 0 0; border-top:1px solid #232a33; padding-top:8px; }
@media (max-width:640px), (orientation:portrait) and (max-width:820px) {
  .modal-vib-panel { top:auto; bottom:8px; left:8px; right:8px; width:auto; max-height:46%; }
  .modal-vib-modes { max-height:20vh; }
}
`;

function isTouchDevice() {
  if (typeof window === "undefined") return false;
  return (navigator.maxTouchPoints || 0) > 0 || window.matchMedia("(pointer: coarse)").matches;
}

// Interactive modal-vibration viewer for modal GLBs (one morph target + baked
// clip per mode). Self-contained three.js view -- a sibling of DxfViewer -- so
// it never touches the main CAD pipeline. Drag a vertex to deform as the
// minimum-strain-energy mode blend; release to ring down at the material's
// damped natural frequencies. "Play" tab plays a single mode's baked clip.
const ModalViewer = forwardRef(function ModalViewer({ assetUrl, modelKey, onViewerAlertChange }, ref) {
  const mountRef = useRef(null);
  const apiRef = useRef(null);
  const [modes, setModes] = useState([]);
  const [interaction, setInteraction] = useState("pluck"); // pluck | play
  const [activeMode, setActiveMode] = useState(null);
  const [slowdown, setSlowdown] = useState(DEFAULT_SLOWDOWN);
  const [damping, setDamping] = useState(0.02);
  const [useVel, setUseVel] = useState(isTouchDevice());
  const [material, setMaterial] = useState("");
  const [collapsed, setCollapsed] = useState(false);

  // three.js lifecycle — rebuilt when the asset changes.
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !assetUrl) return undefined;

    let disposed = false;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.domElement.style.touchAction = "none";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    mount.appendChild(renderer.domElement);

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

    const sizeFor = () => ({ w: mount.clientWidth || 1, h: mount.clientHeight || 1 });
    const resize = () => {
      const { w, h } = sizeFor();
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      if (isTouchDevice()) camera.setViewOffset(w, h, 0, Math.round(h * 0.18), w, h);
      else camera.clearViewOffset();
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    let controller = null;
    let player = null;
    let dragging = false;
    const api = { controller: null, player: null, get interaction() { return interactionRef.current; } };
    apiRef.current = api;

    const ndc = (event) => {
      const r = renderer.domElement.getBoundingClientRect();
      return [((event.clientX - r.left) / r.width) * 2 - 1, -((event.clientY - r.top) / r.height) * 2 + 1];
    };
    const dom = renderer.domElement;
    dom.addEventListener("contextmenu", (e) => e.preventDefault());
    const onDown = (e) => {
      if (interactionRef.current !== "pluck" || !controller) return;
      const [x, y] = ndc(e);
      if (controller.pickAtNDC(x, y)) {
        dragging = true;
        controls.enabled = false;
        e.preventDefault();
        dom.setPointerCapture(e.pointerId);
      }
    };
    const onMove = (e) => {
      if (!dragging || !controller) return;
      const [x, y] = ndc(e);
      controller.dragToNDC(x, y);
    };
    const onUp = (e) => {
      if (!dragging) return;
      dragging = false;
      controls.enabled = true;
      controller.release();
      try { dom.releasePointerCapture(e.pointerId); } catch { /* noop */ }
    };
    dom.addEventListener("pointerdown", onDown);
    dom.addEventListener("pointermove", onMove);
    dom.addEventListener("pointerup", onUp);
    dom.addEventListener("pointercancel", onUp);

    const clock = new THREE.Clock();
    let raf = 0;
    const animate = () => {
      raf = requestAnimationFrame(animate);
      const dt = clock.getDelta();
      if (interactionRef.current === "pluck" && controller) controller.update(dt);
      if (interactionRef.current === "play" && player && player.playing) player.update(dt);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    new GLTFLoader().loadAsync(assetUrl).then((gltf) => {
      if (disposed) return;
      scene.add(gltf.scene);
      let mesh = null;
      gltf.scene.traverse((o) => { if (o.isMesh && o.morphTargetInfluences?.length) mesh = o; });
      if (!mesh) {
        onViewerAlertChange?.({ kind: "error", message: "GLB has no modal morph targets." });
        return;
      }
      mesh.material.flatShading = true;
      mesh.material.needsUpdate = true;

      const meshExtras = gltf.parser?.json?.meshes?.[0]?.extras || {};
      const loadedModes = extractModalModes({ animations: gltf.animations, meshExtras });
      const dampingRatio = Number.isFinite(meshExtras.dampingRatio) ? meshExtras.dampingRatio : 0.02;
      const frequencies = loadedModes.map((m) => m.frequencyHz || 0);

      controller = new ModalInteractionController({
        THREE, camera, mesh, frequencies, damping: dampingRatio, slowdown: DEFAULT_SLOWDOWN,
        useVelocity: isTouchDevice(),
      });
      player = new ModalPlayer({ THREE, root: gltf.scene, animations: gltf.animations, meshExtras });
      api.controller = controller;
      api.player = player;

      // Frame the model.
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const sphere = box.getBoundingSphere(new THREE.Sphere());
      controls.target.copy(sphere.center);
      const dist = sphere.radius / Math.sin((camera.fov * Math.PI) / 180 / 2);
      camera.position.copy(sphere.center).add(new THREE.Vector3(0.6, 0.5, 1).normalize().multiplyScalar(dist * 1.4));
      camera.near = sphere.radius / 100;
      camera.far = sphere.radius * 100;
      camera.updateProjectionMatrix();
      controls.update();
      resize();

      setModes(loadedModes);
      setDamping(dampingRatio);
      setMaterial(meshExtras.material || "");
      setActiveMode(loadedModes[0]?.index ?? null);
    }).catch((err) => {
      if (!disposed) onViewerAlertChange?.({ kind: "error", message: String(err?.message || err) });
    });

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      dom.removeEventListener("pointerdown", onDown);
      dom.removeEventListener("pointermove", onMove);
      dom.removeEventListener("pointerup", onUp);
      dom.removeEventListener("pointercancel", onUp);
      controller?.dispose?.();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
      apiRef.current = null;
    };
  }, [assetUrl, modelKey]);

  // Keep the imperative scene in sync with React control state.
  const interactionRef = useRef(interaction);
  useEffect(() => { interactionRef.current = interaction; }, [interaction]);
  useEffect(() => {
    const c = apiRef.current?.controller;
    const p = apiRef.current?.player;
    if (c) { c.setSlowdown(slowdown); c.setDamping(damping); c.setUseVelocity(useVel); }
    if (p) p.setSpeed(DEFAULT_SLOWDOWN / Math.max(1, slowdown));
  }, [slowdown, damping, useVel, modes]);
  useEffect(() => {
    const p = apiRef.current?.player;
    if (interaction === "play" && p && activeMode != null) { p.selectMode(activeMode); p.play(); }
    if (interaction !== "play" && p) p.pause();
    if (interaction !== "pluck") apiRef.current?.controller?.reset?.();
  }, [interaction, activeMode, modes]);

  return (
    <div ref={ref} style={{ position: "absolute", inset: 0 }}>
      <style>{MODAL_VIEWER_CSS}</style>
      <div ref={mountRef} style={{ position: "absolute", inset: 0 }} />
      <div className="modal-vib-panel" data-collapsed={collapsed ? "true" : "false"}>
        <div className="modal-vib-head">
          <span>Modal vibration{material ? ` · ${material}` : ""}</span>
          <button type="button" onClick={() => setCollapsed((v) => !v)} aria-label="Collapse">
            {collapsed ? "▸" : "▾"}
          </button>
        </div>
        {!collapsed && (
          <div className="modal-vib-body">
            <div className="modal-vib-seg">
              <button type="button" aria-pressed={interaction === "pluck"} onClick={() => setInteraction("pluck")}>Pluck (drag)</button>
              <button type="button" aria-pressed={interaction === "play"} onClick={() => setInteraction("play")}>Play mode</button>
            </div>
            <div className="modal-vib-modes">
              {modes.map((m) => (
                <button
                  type="button"
                  key={m.index}
                  aria-current={interaction === "play" && m.index === activeMode ? "true" : "false"}
                  onClick={() => { setInteraction("play"); setActiveMode(m.index); }}
                >
                  <span>{formatModeLabel(m).replace(/^Mode /, "Mode ")}</span>
                  <span className="freq">{m.frequencyHz == null ? "" : `${m.frequencyHz.toFixed(m.frequencyHz < 100 ? 2 : 1)} Hz`}</span>
                </button>
              ))}
            </div>
            <label className="modal-vib-row">Slow‑mo ×{slowdown}
              <input type="range" min="1" max="2000" step="1" value={slowdown}
                onChange={(e) => setSlowdown(Number(e.target.value))} />
            </label>
            <label className="modal-vib-row">Damping ζ {damping}
              <input type="range" min="0" max="0.2" step="0.001" value={damping}
                onChange={(e) => setDamping(Number(e.target.value))} />
            </label>
            <label className="modal-vib-row modal-vib-check">Carry flick velocity
              <input type="checkbox" checked={useVel} onChange={(e) => setUseVel(e.target.checked)} />
            </label>
            <p className="modal-vib-hint">
              {interaction === "pluck"
                ? "Drag any point to deform, release to watch it ring down (slowed)."
                : "Pick a mode to play its baked vibration."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
});

export default ModalViewer;
