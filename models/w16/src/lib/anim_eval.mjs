// Evaluate a clip of w16.anim.js headlessly and dump per-part world matrices.
//
//   node src/lib/anim_eval.mjs <clip> <t0,t1,...|N> [labels.json] > out.json
//
// Mirrors packages/cadgen-js/src/common/animationRuntime.js exactly: every
// frame starts from rest, .rotate(axis, deg, origin) / .translate(v) PREMULTIPLY
// (later calls act in world space on the already-moved part), m.get() takes a
// label or an occurrence-id list. Occurrence ids are resolved through the
// optional labels.json ({"o1.7": ["chain_link:1_1_inner", ...], ...}) that the
// Python side exports from the built assembly; unknown labels THROW, exactly as
// the viewer would, so a typo in the choreography fails here first.

import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname);
const animPath = path.resolve(here, "..", "w16.anim.js");
const [clipName, samplesArg, labelsPath] = process.argv.slice(2);
if (!clipName || !samplesArg) {
  console.error("usage: node anim_eval.mjs <clip> <t0,t1,...|N> [labels.json]");
  process.exit(2);
}
const { clips } = await import(pathToFileURL(animPath).href);
const clip = clips[clipName];
if (!clip) throw new Error(`no clip ${clipName}; have ${Object.keys(clips)}`);
const groups = labelsPath ? JSON.parse(readFileSync(labelsPath, "utf8")) : {};
const known = new Set(groups.__labels__ || []);

// --- minimal column-major 4x4 (three.js layout) ------------------------------
function ident() { return [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]; }
function mul(a, b) { // a * b
  const o = new Array(16).fill(0);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
    let s = 0;
    for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
    o[c * 4 + r] = s;
  }
  return o;
}
function translation(v) { const m = ident(); m[12] = v[0]; m[13] = v[1]; m[14] = v[2]; return m; }
function rotationAxis(axis, rad) {
  const n = Math.hypot(axis[0], axis[1], axis[2]);
  const x = axis[0] / n, y = axis[1] / n, z = axis[2] / n;
  const c = Math.cos(rad), s = Math.sin(rad), t = 1 - c;
  return [
    t*x*x + c,   t*x*y + s*z, t*x*z - s*y, 0,
    t*x*y - s*z, t*y*y + c,   t*y*z + s*x, 0,
    t*x*z + s*y, t*y*z - s*x, t*z*z + c,   0,
    0, 0, 0, 1,
  ];
}

function frame() {
  const matrices = new Map();
  const styles = new Map();
  const resolve = (target) => {
    const key = String(target).replace(/^#/, "");
    if (known.size && known.has(key)) return [key];
    const parts = key.split(",").map((t) => t.trim()).filter(Boolean);
    if (parts.every((t) => /^o[\d.]+$/.test(t))) {
      const out = [];
      for (const t of parts) for (const lab of groups[t] || []) out.push(lab);
      if (out.length) return out;
    }
    if (!known.size) return [key]; // no label table: trust the choreography
    throw new Error(`animation: no occurrence labeled ${JSON.stringify(target)}`);
  };
  const handle = (target) => {
    const ids = resolve(target);
    const apply = (m) => { for (const id of ids) { const cur = matrices.get(id); matrices.set(id, cur ? mul(m, cur) : m); } };
    return {
      rotate(axis, deg, origin = [0, 0, 0]) {
        const r = rotationAxis(axis, (Number(deg) || 0) * Math.PI / 180);
        apply(mul(translation(origin), mul(r, translation([-origin[0], -origin[1], -origin[2]]))));
        return this;
      },
      translate(v) { apply(translation([Number(v[0]) || 0, Number(v[1]) || 0, Number(v[2]) || 0])); return this; },
      opacity(v) { for (const id of ids) styles.set(id, { ...(styles.get(id) || {}), opacity: v }); return this; },
      visible(v) { for (const id of ids) styles.set(id, { ...(styles.get(id) || {}), visible: !!v }); return this; },
    };
  };
  return { model: { get: handle, labels: () => [...known] }, matrices, styles };
}

let times;
if (samplesArg.includes(",") || Number.isNaN(Number(samplesArg)) === false && samplesArg.includes(".")) {
  times = samplesArg.split(",").map(Number);
} else {
  const n = Number(samplesArg);
  times = Array.from({ length: n }, (_, i) => (clip.duration * i) / n);
}
const out = { clip: clipName, duration: clip.duration, samples: [] };
for (const t of times) {
  const f = frame();
  const localT = clip.loop !== false ? t % clip.duration : Math.min(t, clip.duration);
  clip.update(localT, f.model);
  const mats = {};
  for (const [id, m] of f.matrices) mats[id] = m;
  const sty = {};
  for (const [id, s] of f.styles) sty[id] = s;
  out.samples.push({ t, matrices: mats, styles: sty });
}
process.stdout.write(JSON.stringify(out));
