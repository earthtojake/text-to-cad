// Engine-independent trigonometry: sin, cos, acos, atan, atan2.
//
// WHY THIS EXISTS. `Math.sin` and friends are not specified to any accuracy:
// ECMA-262 lets every implementation return its own approximation, and
// implementations disagree. Measured on identical arguments, V8 in Node 26 and
// V8 in the snapshot browser (Chromium 151) return different bits for ~2.9% of
// `Math.sin` calls, ~2.8% of `Math.cos`, ~7.6% of `Math.acos` and ~17% of
// `Math.atan2`.
//
// Both engines tessellate the same components into the same content-addressed
// mesh store (one key per component + tolerances), and the exported GLB / STL /
// 3MF bytes are that tessellation. So an unspecified libm makes a document's
// exported bytes depend on WHICH engine reached the store first — a viewer or
// `cadgen step snapshot` warming the cache changed the GLB a later
// `cadgen glb build` wrote. That is cadgen law 5 (byte determinism); a
// tessellator that is shared by render and export has to be bit-identical in
// every engine that runs it.
//
// WHAT IT IS. The fdlibm/msun kernels — the same algorithm V8 itself ports —
// written in plain JavaScript. Every operation here is `+`, `-`, `*`, `/` or a
// comparison, all of which IEEE 754 defines to the bit and ECMA-262 requires
// exactly, so the result is the same on every engine and platform. Accuracy is
// fdlibm's: under 1 ulp, and exact where the kernels are (`sin(0)`, `cos(0)`).
//
// WHERE IT IS USED. Everything whose output reaches bytes cadgen writes or
// content-addresses: `evaluate.js` and `tessellate.js` on the way into a stored
// tessellation, and `common/tubeDeformation.js` plus `lib/export/*` and
// `lib/glb/writeGlb.js` on the way out into a GLB, STL or 3MF. Callers whose
// results never leave the process — view-dependent LOD, UI, diagnostics — may
// keep using `Math`.
//
// The other `Math` functions these paths use are safe by specification:
// `sqrt` is correctly rounded, and `abs`/`min`/`max`/`round`/`floor`/`ceil`/
// `trunc`/`sign` are exact. `Math.hypot` and `Math.pow` are not specified to
// any accuracy either — the two engines happened to agree on all 20000 sample
// arguments of each — but those paths use `Math.sqrt` of the sum of squares and
// plain multiplication instead, so no unspecified function survives anywhere
// the bytes come from. `trig.test.js` is what keeps it that way.

// fdlibm __kernel_sin coefficients.
const S1 = -1.66666666666666324348e-01;
const S2 = 8.33333333332248946124e-03;
const S3 = -1.98412698298579493134e-04;
const S4 = 2.75573137070700676789e-06;
const S5 = -2.50507602534068634195e-08;
const S6 = 1.58969099521155010221e-10;

// fdlibm __kernel_cos coefficients.
const C1 = 4.16666666666666019037e-02;
const C2 = -1.38888888888741095749e-03;
const C3 = 2.48015872894767294178e-05;
const C4 = -2.75573143513906633035e-07;
const C5 = 2.08757232129817482790e-09;
const C6 = -1.13596475577881948265e-11;

// pi/4, and pi/2 split into three parts whose leading terms have enough
// trailing zero bits that `n * part` is exact for every integer n the medium
// range admits (fdlibm __ieee754_rem_pio2).
const PIO4 = 7.85398163397448278999e-01;
const INV_PIO2 = 6.36619772367581382433e-01;
const PIO2_1 = 1.57079632673412561417e+00;
const PIO2_1T = 6.07710050650619224932e-11;
const PIO2_2 = 6.07710050630396597660e-11;
const PIO2_2T = 2.02226624879595063154e-21;
const PIO2_3 = 2.02226624871116645580e-21;
const PIO2_3T = 8.47842766036889956997e-32;

// Below this the kernels are the identity: sin(x) rounds to x, cos(x) to 1.
const TINY = 3.725290298461914e-09; // 2^-28
// n * PIO2_1 is exact only while |n| stays inside 2^20, which bounds the
// argument. Radians past this are not a tessellation input — a surface
// parameter that large is already meaningless — so it fails loudly (law 10)
// instead of silently returning a reduction that lost its low bits.
const MAX_ARGUMENT = 524288; // 2^19

function kernelSin(x, tail, hasTail) {
  const z = x * x;
  const w = z * z;
  const r = S2 + z * (S3 + z * S4) + z * w * (S5 + z * S6);
  const v = z * x;
  if (!hasTail) return x + v * (S1 + z * r);
  return x - ((z * (0.5 * tail - v * r) - tail) - v * S1);
}

function kernelCos(x, tail) {
  const z = x * x;
  const w = z * z;
  const r = z * (C1 + z * (C2 + z * C3)) + w * w * (C4 + z * (C5 + z * C6));
  const hz = 0.5 * z;
  const a = 1 - hz;
  return a + (((1 - a) - hz) + (z * r - x * tail));
}

// Reduce x to r + tail with |r| <= pi/4, and the quadrant count n, so that
// x = n * (pi/2) + r + tail. Three Cody-Waite rounds, applied unconditionally:
// fdlibm skips the later ones when the first leaves no cancellation, which is
// a speed choice, not an accuracy one — running them always is at least as
// accurate and needs no bit inspection of the intermediate.
const reduced = { n: 0, r: 0, tail: 0 };

function reducePio2(x) {
  const n = Math.trunc(x * INV_PIO2 + (x > 0 ? 0.5 : -0.5));
  const fn = n;

  let r = x - fn * PIO2_1;
  let w = fn * PIO2_1T;

  let t = r;
  w = fn * PIO2_2;
  r = t - w;
  w = fn * PIO2_2T - ((t - r) - w);

  t = r;
  w = fn * PIO2_3;
  r = t - w;
  w = fn * PIO2_3T - ((t - r) - w);

  const head = r - w;
  reduced.n = n;
  reduced.r = head;
  reduced.tail = (r - head) - w;
  return reduced;
}

function outOfRange(x) {
  throw new RangeError(
    `deterministic sin/cos is defined for |x| < ${MAX_ARGUMENT} radians, got ${x}`,
  );
}

/** `Math.sin`, computed identically on every JavaScript engine. */
export function sin(x) {
  const ax = Math.abs(x);
  if (!Number.isFinite(x)) return NaN;
  if (ax <= PIO4) {
    if (ax < TINY) return x;
    return kernelSin(x, 0, false);
  }
  if (!(ax < MAX_ARGUMENT)) outOfRange(x);
  const { n, r, tail } = reducePio2(x);
  switch (n & 3) {
    case 0: return kernelSin(r, tail, true);
    case 1: return kernelCos(r, tail);
    case 2: return -kernelSin(r, tail, true);
    default: return -kernelCos(r, tail);
  }
}

/** `Math.cos`, computed identically on every JavaScript engine. */
export function cos(x) {
  const ax = Math.abs(x);
  if (!Number.isFinite(x)) return NaN;
  if (ax <= PIO4) {
    if (ax < TINY) return 1;
    return kernelCos(x, 0);
  }
  if (!(ax < MAX_ARGUMENT)) outOfRange(x);
  const { n, r, tail } = reducePio2(x);
  switch (n & 3) {
    case 0: return kernelCos(r, tail);
    case 1: return -kernelSin(r, tail, true);
    case 2: return -kernelCos(r, tail);
    default: return kernelSin(r, tail, true);
  }
}

// --- Inverse functions -------------------------------------------------------
//
// Same discipline, same source: fdlibm's __ieee754_acos, __ieee754_atan and
// __ieee754_atan2, transcribed. The only thing beyond arithmetic they need is
// reading and clearing a double's low word, which IEEE 754 defines exactly.
// fdlibm's `+tiny` terms are dropped: they exist to raise the C inexact flag
// and are no-ops on a double, so keeping them would only look load-bearing.

const bits = new DataView(new ArrayBuffer(8));

function highWord(x) {
  bits.setFloat64(0, x);
  return bits.getInt32(0);
}

function signBit(x) {
  // True for -0 as well as every negative, which is what atan2's quadrant
  // selection is asking about.
  return (highWord(x) >>> 31) === 1;
}

function dropLowWord(x) {
  bits.setFloat64(0, x);
  bits.setUint32(4, 0);
  return bits.getFloat64(0);
}

const PI = 3.14159265358979311600e+00;
const PI_LO = 1.2246467991473531772e-16;
const PIO2_HI = 1.57079632679489655800e+00;
const PIO2_LO = 6.12323399573676603587e-17;

// fdlibm's asin/acos rational approximation, p/q.
const PS0 = 1.66666666666666657415e-01;
const PS1 = -3.25565818622400915405e-01;
const PS2 = 2.01212532134862925881e-01;
const PS3 = -4.00555345006794114027e-02;
const PS4 = 7.91534994289814532176e-04;
const PS5 = 3.47933107596021167570e-05;
const QS1 = -2.40339491173441421878e+00;
const QS2 = 2.02094576023350569471e+00;
const QS3 = -6.88283971605453293030e-01;
const QS4 = 7.70381505559019352791e-02;

function acosR(z) {
  const p = z * (PS0 + z * (PS1 + z * (PS2 + z * (PS3 + z * (PS4 + z * PS5)))));
  const q = 1 + z * (QS1 + z * (QS2 + z * (QS3 + z * QS4)));
  return p / q;
}

/** `Math.acos`, computed identically on every JavaScript engine. */
export function acos(x) {
  const ax = Math.abs(x);
  if (!(ax <= 1)) return NaN; // also catches NaN
  if (ax === 1) return x > 0 ? 0 : PI + 2 * PIO2_LO;
  if (ax < 0.5) {
    if (ax < 6.938893903907228e-18) return PIO2_HI + PIO2_LO; // |x| < 2^-57
    return PIO2_HI - (x - (PIO2_LO - x * acosR(x * x)));
  }
  if (x < 0) {
    const z = (1 + x) * 0.5;
    const s = Math.sqrt(z);
    return PI - 2 * (s + (acosR(z) * s - PIO2_LO));
  }
  const z = (1 - x) * 0.5;
  const s = Math.sqrt(z);
  // Split s into an exactly representable head and the tail the head lost, so
  // 2*(head + tail) keeps the precision a bare 2*s would round away.
  const head = dropLowWord(s);
  const correction = (z - head * head) / (s + head);
  return 2 * (head + (acosR(z) * s + correction));
}

// fdlibm's atan breakpoints, and the exact endpoint it folds each range back to.
const ATAN_HI = [
  4.63647609000806093515e-01, // atan(0.5)
  7.85398163397448278999e-01, // atan(1.0)
  9.82793723247329054082e-01, // atan(1.5)
  1.57079632679489655800e+00, // atan(inf)
];
const ATAN_LO = [
  2.26987774529616870924e-17,
  3.06161699786838301793e-17,
  1.39033110312309984516e-17,
  6.12323399573676603587e-17,
];
const AT = [
  3.33333333333329318027e-01, -1.99999999998764832476e-01,
  1.42857142725034663711e-01, -1.11111104054623557880e-01,
  9.09088713343650656196e-02, -7.69187620504482999495e-02,
  6.66107313738753120669e-02, -5.83357013379057348645e-02,
  4.97687799461593236017e-02, -3.65315727442169155270e-02,
  1.62858201153657823623e-02,
];

/** `Math.atan`, computed identically on every JavaScript engine. */
export function atan(x) {
  if (Number.isNaN(x)) return NaN;
  const negative = signBit(x);
  let ax = Math.abs(x);
  let id;
  if (ax >= 73786976294838206464) { // 2^66: atan has reached its limit
    const z = ATAN_HI[3] + ATAN_LO[3];
    return negative ? -z : z;
  }
  if (ax < 0.4375) {
    if (ax < 1.862645149230957e-09) return x; // |x| < 2^-29
    id = -1;
    ax = x;
  } else if (ax < 0.6875) {
    id = 0;
    ax = (2 * ax - 1) / (2 + ax);
  } else if (ax < 1.1875) {
    id = 1;
    ax = (ax - 1) / (ax + 1);
  } else if (ax < 2.4375) {
    id = 2;
    ax = (ax - 1.5) / (1 + 1.5 * ax);
  } else {
    id = 3;
    ax = -1 / ax;
  }
  const z = ax * ax;
  const w = z * z;
  const odd = z * (AT[0] + w * (AT[2] + w * (AT[4] + w * (AT[6] + w * (AT[8] + w * AT[10])))));
  const even = w * (AT[1] + w * (AT[3] + w * (AT[5] + w * (AT[7] + w * AT[9]))));
  if (id < 0) return ax - ax * (odd + even);
  const result = ATAN_HI[id] - ((ax * (odd + even) - ATAN_LO[id]) - ax);
  return negative ? -result : result;
}

/** `Math.atan2`, computed identically on every JavaScript engine. */
export function atan2(y, x) {
  if (Number.isNaN(x) || Number.isNaN(y)) return NaN;
  if (x === 1) return atan(y);
  const quadrant = (signBit(y) ? 1 : 0) | (signBit(x) ? 2 : 0);
  if (y === 0) {
    // atan2(+-0, +anything) keeps y's sign; a negative x answers +-pi.
    return quadrant < 2 ? y : (quadrant === 2 ? PI : -PI);
  }
  if (x === 0) return signBit(y) ? -PIO2_HI : PIO2_HI;
  if (!Number.isFinite(x)) {
    if (!Number.isFinite(y)) {
      const eighth = [PIO4, -PIO4, 3 * PIO4, -3 * PIO4];
      return eighth[quadrant];
    }
    return [0, -0, PI, -PI][quadrant];
  }
  if (!Number.isFinite(y)) return signBit(y) ? -PIO2_HI : PIO2_HI;

  // How far apart the two magnitudes are, in binary exponents. Far enough and
  // the quotient is already the answer, or already zero.
  const exponents = ((highWord(y) & 0x7fffffff) - (highWord(x) & 0x7fffffff)) >> 20;
  let z;
  if (exponents > 60) z = PIO2_HI + 0.5 * PI_LO;
  else if (signBit(x) && exponents < -60) z = 0;
  else z = atan(Math.abs(y / x));
  switch (quadrant) {
    case 0: return z;
    case 1: return -z;
    case 2: return PI - (z - PI_LO);
    default: return (z - PI_LO) - PI;
  }
}
