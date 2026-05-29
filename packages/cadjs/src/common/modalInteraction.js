// Interactive modal "pluck": drag a vertex to deform the structure as a blend
// of mode shapes, release to let it ring as a modal superposition.
//
// The morph targets emitted by `cadpy_fea modal --modal-glb` ARE the modal
// basis phi_i, and each mode's natural frequency f_i is stored in the GLB. So
// the whole interaction is small linear algebra over the precomputed modes; no
// FEA re-solve is needed.
//
// Drag: given the grabbed point's per-mode displacement vectors d_i (each
// morph target's displacement of that point) and a target displacement t,
// find modal weights q minimizing the modal (elastic) energy sum w_i q_i^2
// subject to sum q_i d_i = t. With w_i = omega_i^2 this is the minimum-strain-
// energy shape -- the physical static response to pulling that point. The dual
// is a 3x3 solve: q = Winv Dt (D Winv Dt)^-1 t.
//
// Release: free vibration from initial displacement q0, zero velocity:
//   q_i(t) = q0_i * exp(-zeta_i omega_i t) * cos(omega_di t)
// played in slowed time so kHz-to-Hz modes are watchable.

const TWO_PI = Math.PI * 2;

function invert3(m, ridge = 0) {
  // m is row-major [9]; returns inverse [9] or null. Adds a ridge*I for safety.
  const a = m[0] + ridge, b = m[1], c = m[2];
  const d = m[3], e = m[4] + ridge, f = m[5];
  const g = m[6], h = m[7], i = m[8] + ridge;
  const A = e * i - f * h;
  const B = -(d * i - f * g);
  const C = d * h - e * g;
  const det = a * A + b * B + c * C;
  // The ridge keeps det strictly positive even for rank-deficient A (e.g. a
  // single mode only constrains one direction); unreachable directions carry no
  // modal authority, so their large inverse entries multiply zero deltas and
  // never reach the weights. Only bail on a genuinely degenerate det.
  if (!Number.isFinite(det) || det === 0) return null;
  const inv = 1 / det;
  return [
    A * inv, (c * h - b * i) * inv, (b * f - c * e) * inv,
    B * inv, (a * i - c * g) * inv, (c * d - a * f) * inv,
    C * inv, (b * g - a * h) * inv, (a * e - b * d) * inv,
  ];
}

function mat3xVec(m, v) {
  return [
    m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
    m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
    m[6] * v[0] + m[7] * v[1] + m[8] * v[2],
  ];
}

// Solve for modal weights so the grabbed point's displacement matches `target`.
// deltas: Array<[dx,dy,dz]> length N (each mode's displacement of the point).
// target: [tx,ty,tz]. frequencies: Array<Hz> length N (optional; enables the
// minimum-energy weighting). regularization: small ridge for conditioning.
export function solveDragWeights({ deltas, target, frequencies = null, regularization = 1e-6 }) {
  const n = deltas.length;
  if (!n) return [];
  // w_i: modal stiffness weight. Use omega^2; floor avoids dividing by ~0 for
  // soft/rigid modes and keeps the solve well-posed.
  const winv = new Array(n);
  for (let i = 0; i < n; i += 1) {
    const f = frequencies && Number.isFinite(frequencies[i]) ? frequencies[i] : 1;
    const omega2 = (TWO_PI * f) * (TWO_PI * f);
    winv[i] = 1 / (omega2 + 1e-9);
  }
  // A = D Winv D^T  (3x3)
  const A = new Array(9).fill(0);
  for (let i = 0; i < n; i += 1) {
    const d = deltas[i];
    const wi = winv[i];
    for (let r = 0; r < 3; r += 1) {
      for (let c = 0; c < 3; c += 1) {
        A[r * 3 + c] += wi * d[r] * d[c];
      }
    }
  }
  // Scale the ridge to the matrix magnitude for stability.
  const scale = (A[0] + A[4] + A[8]) / 3 || 1;
  const Ainv = invert3(A, regularization * scale);
  if (!Ainv) return new Array(n).fill(0);
  const y = mat3xVec(Ainv, target); // 3-vector
  // q_i = winv_i * (d_i . y)
  const q = new Array(n);
  for (let i = 0; i < n; i += 1) {
    const d = deltas[i];
    q[i] = winv[i] * (d[0] * y[0] + d[1] * y[1] + d[2] * y[2]);
  }
  return q;
}

// Reconstruct the grabbed point's displacement from weights (for verification).
export function applyWeightsToPoint(deltas, weights) {
  const out = [0, 0, 0];
  for (let i = 0; i < deltas.length; i += 1) {
    const q = weights[i] || 0;
    out[0] += q * deltas[i][0];
    out[1] += q * deltas[i][1];
    out[2] += q * deltas[i][2];
  }
  return out;
}

// Free-vibration modal superposition from an initial displacement (zero
// velocity). Each mode rings at its own natural frequency; time is slowed so
// the motion is analyzable.
export class ModalSuperposition {
  constructor({ frequencies, weights, damping = 0.02, slowdown = 200 }) {
    this.frequencies = frequencies.slice();
    this.q0 = weights.slice();
    this.damping = Math.max(0, damping);
    this.slowdown = Math.max(1e-6, slowdown);
    this.elapsedReal = 0;
  }

  // Advance by dt real seconds; returns the current modal weight vector.
  advance(dtRealSeconds) {
    this.elapsedReal += Math.max(0, Number(dtRealSeconds) || 0);
    return this.weightsAt(this.elapsedReal);
  }

  weightsAt(tRealSeconds) {
    const tSim = tRealSeconds / this.slowdown;
    const zeta = this.damping;
    return this.q0.map((q0, i) => {
      const omega = TWO_PI * (this.frequencies[i] || 0);
      const omegaD = omega * Math.sqrt(Math.max(0, 1 - zeta * zeta));
      const envelope = Math.exp(-zeta * omega * tSim);
      return q0 * envelope * Math.cos(omegaD * tSim);
    });
  }

  // Remaining vibration energy fraction (1 at t=0), for auto-stop when settled.
  energyFraction(tRealSeconds = this.elapsedReal) {
    const tSim = tRealSeconds / this.slowdown;
    let maxEnv = 0;
    for (let i = 0; i < this.frequencies.length; i += 1) {
      const omega = TWO_PI * (this.frequencies[i] || 0);
      maxEnv = Math.max(maxEnv, Math.exp(-this.damping * omega * tSim));
    }
    return maxEnv;
  }
}
