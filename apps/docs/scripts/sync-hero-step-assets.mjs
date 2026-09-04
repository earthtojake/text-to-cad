// Refresh the hero showcase assets from the repo model. The hero renders the
// planetary gear STEP the same way every cadgen-js client does — from the
// TREE behind the document (assembly.json + exact-surface components) plus
// its SIDECAR (<name>.step.json: kinematics + copied animation clips) — served
// as plain static files so production (Vercel) needs no backend and no Git LFS.
//
// The tree lives in cadgen's store, keyed by the STEP file's bytes, and the
// store holds no directories: this script asks cadgen to export a view of the
// tree (assembly.json + components/<cid>.surf) and copies what the browser
// fetches. Run it after rebuilding the model:
//
//   python models/assemblies/src/planetary_gear_assembly/planetary_gear_assembly.py
//   node apps/docs/scripts/sync-hero-step-assets.mjs
//
// Set CADGEN_CACHE_DIR to the store the model was built into if it was not
// the default one, and PYTHON_BIN to the interpreter that has cadgen when it
// is not the repo's .venv.

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const docsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(docsRoot, "..", "..");
const modelScript = "models/assemblies/src/planetary_gear_assembly/planetary_gear_assembly.py";
const modelStep = path.join(repoRoot, "models/assemblies/STEP/planetary_gear_assembly/planetary_gear_assembly.step");
const modelSidecar = `${modelStep}.json`;
const heroDir = path.join(docsRoot, "public/hero");
const heroTreeDir = path.join(heroDir, "planetary");
const rebuildHint = `run: python ${modelScript}`;
// The Python that has cadgen: PYTHON_BIN when set (a worktree has no .venv of
// its own), else the repo's .venv.
const python = process.env.PYTHON_BIN || path.join(repoRoot, ".venv/bin/python");

if (!fs.existsSync(modelStep)) {
  throw new Error(`Model STEP missing: ${modelStep} — ${rebuildHint}`);
}
if (!fs.existsSync(modelSidecar)) {
  throw new Error(`Model sidecar missing: ${modelSidecar} — ${rebuildHint}`);
}

// A view of the tree in a fresh temporary directory (ours to remove). An empty
// line means the store has no tree for these bytes: the model was not built,
// or was built into another store.
const viewDir = execFileSync(
  python,
  [
    "-c",
    "import sys; from pathlib import Path; " +
      "from cadgen.catalog import result_tree_for; from cadgen.store.view import export_view; " +
      "tree = result_tree_for(Path(sys.argv[1])); print(export_view(tree) if tree else '')",
    modelStep,
  ],
  { encoding: "utf8" },
).trim();

if (!viewDir) {
  throw new Error(`The store has no tree for ${modelStep} — ${rebuildHint} (in the same CADGEN_CACHE_DIR)`);
}

try {
  const descriptor = JSON.parse(fs.readFileSync(path.join(viewDir, "assembly.json"), "utf8"));

  // Ship only what the browser fetches: the descriptor and each component's
  // .surf. The .brep siblings exist for exact-geometry exports, which the hero
  // never does.
  fs.rmSync(heroTreeDir, { recursive: true, force: true });
  fs.mkdirSync(path.join(heroTreeDir, "components"), { recursive: true });
  fs.copyFileSync(path.join(viewDir, "assembly.json"), path.join(heroTreeDir, "assembly.json"));

  let copied = 0;
  for (const [cid, entry] of Object.entries(descriptor.components || {})) {
    const surf = String(entry?.surf || "");
    if (!surf) {
      throw new Error(`Component ${cid} declares no surf path in ${viewDir}/assembly.json`);
    }
    fs.copyFileSync(path.join(viewDir, surf), path.join(heroTreeDir, surf));
    copied += 1;
  }

  fs.copyFileSync(modelSidecar, path.join(heroDir, "planetary_gear_assembly.step.json"));
  console.log(`Synced hero assets: ${copied} components + sidecar -> ${heroTreeDir}`);
} finally {
  fs.rmSync(viewDir, { recursive: true, force: true });
}
