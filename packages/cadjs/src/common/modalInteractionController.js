// three.js controller for the interactive modal "pluck": pick a vertex, drag it
// (the structure deforms as the minimum-strain-energy blend of mode shapes that
// makes that vertex follow the cursor), release to let it ring as a free modal
// superposition at the material's real damped natural frequencies, in slow time.
//
// Core methods take normalized device coordinates (NDC) so they are unit-
// testable headlessly with a real camera + mesh (three.js raycasting needs no
// DOM). attach()/detach() bind DOM pointer events to those methods.

import { solveDragWeights, ModalSuperposition } from "./modalInteraction.js";

export function vertexModeDeltas(mesh, vertexIndex) {
  const morphs = mesh?.geometry?.morphAttributes?.position || [];
  return morphs.map((attr) => [
    attr.getX(vertexIndex),
    attr.getY(vertexIndex),
    attr.getZ(vertexIndex),
  ]);
}

// Largest single-mode displacement a vertex sees across all modes -- its modal
// "mobility". Clamped (near-)fixed boundary vertices have ~zero mobility.
export function vertexMobility(deltas) {
  let m = 0;
  for (const d of deltas) m = Math.max(m, Math.hypot(d[0], d[1], d[2]));
  return m;
}

export function maxMeshMobility(mesh) {
  const morphs = mesh?.geometry?.morphAttributes?.position || [];
  if (!morphs.length) return 0;
  const count = mesh.geometry.attributes.position.count;
  let maxM = 0;
  for (let v = 0; v < count; v += 1) {
    for (const attr of morphs) {
      maxM = Math.max(maxM, Math.hypot(attr.getX(v), attr.getY(v), attr.getZ(v)));
    }
  }
  return maxM;
}

// Closest of a hit face's three vertices to the hit point (world space).
export function nearestFaceVertex(THREE, mesh, face, worldPoint) {
  const pos = mesh.geometry.attributes.position;
  const candidates = [face.a, face.b, face.c];
  let best = candidates[0];
  let bestDist = Infinity;
  const v = new THREE.Vector3();
  for (const idx of candidates) {
    v.fromBufferAttribute(pos, idx);
    mesh.localToWorld(v);
    const d = v.distanceToSquared(worldPoint);
    if (d < bestDist) {
      bestDist = d;
      best = idx;
    }
  }
  return best;
}

export class ModalInteractionController {
  constructor({
    THREE,
    camera,
    mesh,
    frequencies,
    damping = 0.01,
    slowdown = 200,
    domElement = null,
    onChange = null,
    minMobilityFraction = 0.02,
    useVelocity = false,
  }) {
    if (!THREE) throw new Error("ModalInteractionController requires THREE.");
    this.THREE = THREE;
    this.camera = camera;
    this.mesh = mesh;
    this.frequencies = frequencies || [];
    this.damping = damping;
    this.slowdown = slowdown;
    this.domElement = domElement;
    this.onChange = onChange;
    // Reject grabs on (near-)fixed vertices: they have ~zero modal motion, so
    // asking the solver to make them follow the cursor blows up the weights.
    this.minMobilityFraction = minMobilityFraction;
    this.maxMobility = mesh ? maxMeshMobility(mesh) : 0;
    // Off by default: carrying the flick velocity is fun but can fling the part
    // hard and surprise users. Opt in via the UI / setUseVelocity().
    this.useVelocity = useVelocity;

    this.raycaster = new THREE.Raycaster();
    this.state = "idle"; // idle | dragging | ringing
    this.grab = null;     // { index, deltas, worldStart, localStart }
    this.superposition = null;
    this._boundDown = null;
    this._history = [];          // recent { target:[x,y,z], t } drag samples
    this.flickWindowSec = 0.08;  // estimate flick velocity over this trailing window
  }

  // Average vertex velocity over the trailing flick window. Robust to touch
  // flicks that decelerate just before lift and to coalesced-event timing,
  // which a last-pair instantaneous estimate gets wrong.
  _flickVelocity() {
    const h = this._history;
    if (h.length < 2) return [0, 0, 0];
    const latest = h[h.length - 1];
    let ref = h[0];
    for (let i = h.length - 1; i >= 0; i -= 1) {
      ref = h[i];
      if (latest.t - h[i].t >= this.flickWindowSec) break;
    }
    const dt = latest.t - ref.t;
    if (dt <= 1e-4) return [0, 0, 0];
    return [
      (latest.target[0] - ref.target[0]) / dt,
      (latest.target[1] - ref.target[1]) / dt,
      (latest.target[2] - ref.target[2]) / dt,
    ];
  }

  _now() {
    if (typeof performance !== "undefined" && performance.now) return performance.now() / 1000;
    return Date.now() / 1000;
  }

  _influences() {
    return this.mesh.morphTargetInfluences;
  }

  _setInfluences(q) {
    const inf = this._influences();
    for (let i = 0; i < inf.length; i += 1) inf[i] = q[i] || 0;
    if (this.onChange) this.onChange(inf);
  }

  // Pick the vertex under NDC; returns true if something was grabbed.
  pickAtNDC(ndcX, ndcY) {
    const THREE = this.THREE;
    this.raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), this.camera);
    const hits = this.raycaster.intersectObject(this.mesh, false);
    if (!hits.length || !hits[0].face) return false;
    const hit = hits[0];
    const index = nearestFaceVertex(THREE, this.mesh, hit.face, hit.point);
    const deltas = vertexModeDeltas(this.mesh, index);
    // Ignore grabs on clamped/stationary vertices (no modal authority).
    if (this.maxMobility > 0 &&
        vertexMobility(deltas) < this.minMobilityFraction * this.maxMobility) {
      return false;
    }
    const localStart = new THREE.Vector3().fromBufferAttribute(
      this.mesh.geometry.attributes.position, index,
    );
    const worldStart = localStart.clone();
    this.mesh.localToWorld(worldStart);
    this.grab = {
      index,
      deltas,
      worldStart,
      localStart,
      planeNormal: this.camera.getWorldDirection(new THREE.Vector3()).clone(),
    };
    this.state = "dragging";
    this.superposition = null;
    this._history = [];
    return true;
  }

  // Drag the grabbed vertex toward NDC; deforms the mesh by the solved weights
  // and tracks the vertex velocity (for the release flick). `now` is seconds.
  dragToNDC(ndcX, ndcY, now = this._now()) {
    if (this.state !== "dragging" || !this.grab) return null;
    const THREE = this.THREE;
    this.raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), this.camera);
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(
      this.grab.planeNormal, this.grab.worldStart,
    );
    const hitPoint = new THREE.Vector3();
    if (!this.raycaster.ray.intersectPlane(plane, hitPoint)) return null;
    // Target displacement of the grabbed vertex in the mesh's local space
    // (morph deltas are local).
    const localNow = hitPoint.clone();
    this.mesh.worldToLocal(localNow);
    const target = [
      localNow.x - this.grab.localStart.x,
      localNow.y - this.grab.localStart.y,
      localNow.z - this.grab.localStart.z,
    ];
    this._history.push({ target, t: now });
    // Keep a little more than the flick window so the trailing estimate is stable.
    const cutoff = now - Math.max(0.25, this.flickWindowSec * 2);
    while (this._history.length > 2 && this._history[0].t < cutoff) this._history.shift();
    const q = solveDragWeights({
      deltas: this.grab.deltas,
      target,
      frequencies: this.frequencies,
    });
    this._setInfluences(q);
    return q;
  }

  // Release: ring down from the current deformation, with the flick velocity
  // propagated into modal initial velocities (same min-energy projection).
  release() {
    if (this.state !== "dragging") return;
    const q0 = Array.from(this._influences());
    let velocities = q0.map(() => 0);
    if (this.useVelocity && this.grab) {
      const v = this._flickVelocity();
      if (v[0] || v[1] || v[2]) {
        // The drag velocity is in real seconds, but the physics clock runs in
        // slowed time (tau = t_real / slowdown), so the physical initial
        // velocity is d(disp)/d(tau) = v_real * slowdown. Without this factor
        // the flick energy is `slowdown`x too small to see.
        const physVelocity = v.map((c) => c * this.slowdown);
        velocities = solveDragWeights({
          deltas: this.grab.deltas,
          target: physVelocity,
          frequencies: this.frequencies,
        });
      }
    }
    this.superposition = new ModalSuperposition({
      frequencies: this.frequencies,
      weights: q0,
      velocities,
      damping: this.damping,
      slowdown: this.slowdown,
    });
    this.state = "ringing";
  }

  // Advance ringing; returns true while still ringing (so the host keeps
  // requesting frames). Auto-stops when the envelope has decayed.
  update(dtSeconds) {
    if (this.state !== "ringing" || !this.superposition) return false;
    const q = this.superposition.advance(dtSeconds);
    this._setInfluences(q);
    if (this.superposition.energyFraction() < 1e-3) {
      this.reset();
      return false;
    }
    return true;
  }

  reset() {
    this.state = "idle";
    this.grab = null;
    this.superposition = null;
    const inf = this._influences();
    for (let i = 0; i < inf.length; i += 1) inf[i] = 0;
    if (this.onChange) this.onChange(inf);
  }

  setDamping(d) { this.damping = Math.max(0, Number(d) || 0); }
  setSlowdown(s) { this.slowdown = Math.max(1e-6, Number(s) || 1); }
  setUseVelocity(on) { this.useVelocity = Boolean(on); }

  isActive() { return this.state !== "idle"; }
}
