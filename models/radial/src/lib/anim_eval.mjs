// Evaluate the embedded animation (ANIMATION_JS in src/lib/anim_js.py) headlessly
// and print per-label 4x4 world matrices (and deformed tube paths) as JSON.
//
//   node src/lib/anim_eval.mjs <clip> <t0,t1,...|N> [labels.json] [--raw] [--deg] [--module=anim_js.py]
//
// <times>: a comma list of seconds, or N (N evenly spaced samples over one clip).
// --deg:   the times are crank angles in degrees, over 720 deg per clip duration
//          (t = theta / 90 for `running` and `exploded-running`).
// --module: read ANIMATION_JS from another generated file (default: anim_js.py here).
// --raw:   call update(t) directly (t = duration is NOT wrapped to 0), for the
//          loop-seam check; the default goes through the viewer's
//          evaluateAnimationClip (loop wrap / clamp exactly as the viewer).
// labels.json: {"parts": [{"id", "label"}]} written by lib/animgen.py from the
//          built assembly; the model handle knows exactly those parts, so an
//          unknown label THROWS as it would in the viewer.
//
// Semantics are not mirrored, they are SHARED: this imports the viewer's own
// packages/core/src/common/animationRuntime.js (and its tube-deformation
// chunk) and three.js, so the matrices are the viewer's matrices (premultiply,
// makeRotationAxis, column-major elements) and every deformTube spec passes the
// viewer's validator and path compiler (tangent continuity etc.).
// Output: {clip, duration, samples: [{t, matrices: {label: [16, column-major]},
//          deformations: {label: {path: {normal, segments}}}, styles: {label: {visible?, opacity?}}}]}

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const here = path.dirname(new URL(import.meta.url).pathname);
const args = process.argv.slice(2);
const moduleArg = args.find((a) => a.startsWith("--module="));
const flags = new Set(args.filter((a) => a.startsWith("--")));
const [clipName, samplesArg, labelsPath] = args.filter((a) => !a.startsWith("--"));
if (!clipName || !samplesArg) {
  console.error("usage: node anim_eval.mjs <clip> <t0,t1,...|N> [labels.json] [--raw] [--deg]");
  process.exit(2);
}

// Walk up from here to find the repo's core runtime and a three.js install.
function findUp(rels) {
  let dir = here;
  for (;;) {
    for (const rel of rels) {
      const p = path.join(dir, rel);
      if (existsSync(p)) return p;
    }
    const up = path.dirname(dir);
    if (up === dir) return null;
    dir = up;
  }
}
const runtimePath = findUp(["packages/core/src/common/animationRuntime.js"]);
const threePath = process.env.CADGEN_THREE || findUp([
  "packages/core/node_modules/three/build/three.module.js",
  "apps/web/node_modules/three/build/three.module.js",
  "node_modules/three/build/three.module.js",
  // a lightweight worktree has no node_modules: fall back to the main checkout's
  "../../../packages/core/node_modules/three/build/three.module.js",
]);
if (!runtimePath || !threePath) {
  throw new Error(`cannot find the viewer runtime (${runtimePath}) or three.js (${threePath}); set CADGEN_THREE`);
}
const THREE = await import(pathToFileURL(threePath).href);
const runtime = await import(pathToFileURL(runtimePath).href);
const chunk = await import(pathToFileURL(path.join(path.dirname(runtimePath), "tubeDeformationChunk.js")).href);
const tube = await chunk.loadTubeDeformation();

const pySource = readFileSync(moduleArg ? path.resolve(moduleArg.slice(9)) : path.join(here, "anim_js.py"), "utf8");
const marker = "ANIMATION_JS = r'''";
const start = pySource.indexOf(marker) + marker.length;
const end = pySource.indexOf("'''", start);
if (start < marker.length || end < start) throw new Error("cannot find the ANIMATION_JS literal in anim_js.py");
const source = pySource.slice(start, end);
const ns = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const clips = runtime.normalizeAnimationClips(ns.clips);
const clip = clips[clipName];
if (!clip) throw new Error(`no clip ${clipName}; have ${Object.keys(clips)}`);

const meshData = labelsPath ? JSON.parse(readFileSync(labelsPath, "utf8")) : { parts: [] };
const labelOf = new Map(meshData.parts.map((p) => [String(p.id), String(p.label)]));

let times;
if (samplesArg.includes(",") || samplesArg.includes(".")) {
  times = samplesArg.split(",").map(Number);
} else {
  const n = Number(samplesArg);
  times = Array.from({ length: n }, (_, i) => (clip.duration * i) / n);
}
if (flags.has("--deg")) times = times.map((deg) => (deg / 720) * clip.duration);

const out = { clip: clipName, duration: clip.duration, runtime: runtimePath, three: THREE.REVISION, samples: [] };
for (const t of times) {
  let frame;
  if (flags.has("--raw")) {
    frame = runtime.createAnimationFrame(THREE, meshData);
    clip.update(t, frame.model);
  } else {
    frame = runtime.evaluateAnimationClip(THREE, meshData, clip, t);
  }
  const matrices = {};
  for (const [id, m] of frame.matrices) matrices[labelOf.get(id) ?? id] = Array.from(m.elements);
  const deformations = {};
  for (const [id, d] of frame.deformations) {
    tube.compileDeformation(d);          // the viewer's path compiler: continuity + tangency checks
    deformations[labelOf.get(id) ?? id] = { path: d.pathSpec, rest: d.restSpec };
  }
  const styles = {};
  for (const [id, st] of frame.styles || []) styles[labelOf.get(id) ?? id] = st;
  out.samples.push({ t, matrices, deformations, styles });
}
process.stdout.write(JSON.stringify(out));
