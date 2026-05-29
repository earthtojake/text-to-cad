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

    this.raycaster = new THREE.Raycaster();
    this.state = "idle"; // idle | dragging | ringing
    this.grab = null;     // { index, deltas, worldStart, localStart }
    this.superposition = null;
    this._boundDown = null;
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
    const localStart = new THREE.Vector3().fromBufferAttribute(
      this.mesh.geometry.attributes.position, index,
    );
    const worldStart = localStart.clone();
    this.mesh.localToWorld(worldStart);
    this.grab = {
      index,
      deltas: vertexModeDeltas(this.mesh, index),
      worldStart,
      localStart,
      planeNormal: this.camera.getWorldDirection(new THREE.Vector3()).clone(),
    };
    this.state = "dragging";
    this.superposition = null;
    return true;
  }

  // Drag the grabbed vertex toward NDC; deforms the mesh by the solved weights.
  dragToNDC(ndcX, ndcY) {
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
    const q = solveDragWeights({
      deltas: this.grab.deltas,
      target,
      frequencies: this.frequencies,
    });
    this._setInfluences(q);
    return q;
  }

  // Release: ring down from the current (full) deformation, zero velocity.
  release() {
    if (this.state !== "dragging") return;
    const q0 = Array.from(this._influences());
    this.superposition = new ModalSuperposition({
      frequencies: this.frequencies,
      weights: q0,
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

  isActive() { return this.state !== "idle"; }
}
