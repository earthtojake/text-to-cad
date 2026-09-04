// Refresh the hero showcase assets from the repo model. The hero renders the
// planetary gear STEP the same way every cadgen-js client does — from its
// RENDER PACKAGE (assembly.json + exact-surface components) plus its SIDECAR
// (<name>.step.json: kinematics + copied animation clips) — served as plain
// static files so production (Vercel) needs no backend and no Git LFS.
//
// The package is content-keyed in the user-level store, and that key is
// cadgen's law, so this script asks cadgen for the directory instead of
// restating the hash. Run it after rebuilding the model:
//
//   python models/assemblies/src/planetary_gear_assembly/planetary_gear_assembly.py
//   node apps/docs/scripts/sync-hero-step-assets.mjs

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const docsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(docsRoot, "..", "..");
const modelStep = path.join(repoRoot, "models/assemblies/STEP/planetary_gear_assembly/planetary_gear_assembly.step");
const modelSidecar = `${modelStep}.json`;
const heroDir = path.join(docsRoot, "public/hero");
const heroPackageDir = path.join(heroDir, "planetary");

const packageDir = execFileSync(
  path.join(repoRoot, ".venv/bin/python"),
  [
    "-c",
    "import sys; from pathlib import Path; from cadgen.catalog import render_package_dir; " +
      "print(render_package_dir(Path(sys.argv[1])))",
    modelStep,
  ],
  { encoding: "utf8" },
).trim();

if (!fs.existsSync(path.join(packageDir, "assembly.json"))) {
  throw new Error(
    `No render package for ${modelStep} at ${packageDir} — run: python models/assemblies/src/planetary_gear_assembly/planetary_gear_assembly.py`,
  );
}
if (!fs.existsSync(modelSidecar)) {
  throw new Error(`Model sidecar missing: ${modelSidecar} — rebuild the model first`);
}

// Ship only what the browser fetches: the descriptor and each component's
// .surf. The package's .brep siblings exist for exact-geometry exports, which
// the hero never does.
fs.rmSync(heroPackageDir, { recursive: true, force: true });
fs.mkdirSync(path.join(heroPackageDir, "components"), { recursive: true });
fs.copyFileSync(path.join(packageDir, "assembly.json"), path.join(heroPackageDir, "assembly.json"));

const descriptor = JSON.parse(fs.readFileSync(path.join(packageDir, "assembly.json"), "utf8"));
let copied = 0;
for (const [cid, entry] of Object.entries(descriptor.components || {})) {
  const surf = String(entry?.surf || "");
  if (!surf) {
    throw new Error(`Component ${cid} declares no surf path in ${packageDir}/assembly.json`);
  }
  fs.copyFileSync(path.join(packageDir, surf), path.join(heroPackageDir, surf));
  copied += 1;
}

fs.copyFileSync(modelSidecar, path.join(heroDir, "planetary_gear_assembly.step.json"));

console.log(`Synced hero assets: ${copied} components + sidecar -> ${heroPackageDir}`);
