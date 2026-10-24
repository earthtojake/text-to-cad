// Refresh the hero's GLB from the repo model. The hero plays the planetary gear as one GLB:
// the model's document exported by `cadgen export`, its parts and colours, and its
// `meshCycle` motion baked into the clip the page plays. It is served as a plain static file,
// so production (Vercel) needs no backend and no Git LFS. Run it after changing the model:
//
//   node apps/docs/scripts/sync-hero-glb.mjs
//
// It builds the model and exports its document (`cadgen.export(model, path)`) to
// public/hero/planetary.glb, and runs the check the docs CI runs on it. PYTHON_BIN names the Python
// that has cadgen's dependencies (default: the repository's .venv); this checkout's own cadgen
// (packages/cadgen/src) goes first on its path, so a worktree builds and exports with its own engine.

import { execFileSync } from "node:child_process";
import path from "node:path";

import { HERO_GLB, HERO_MODEL, checkHeroGlb, repoRoot } from "./check-hero-glb.mjs";

const python = process.env.PYTHON_BIN || path.join(repoRoot, ".venv/bin/python");
const env = {
  ...process.env,
  PYTHONPATH: [path.join(repoRoot, "packages/cadgen/src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
};
const run = (args) => execFileSync(python, args, { cwd: repoRoot, env, stdio: "inherit" });

// The model's own script builds it, and `cadgen.export` writes the GLB from its document, the
// motions baked as clips: the model function itself, run first (a replay when it is current).
const script = path.join(repoRoot, HERO_MODEL);
const exporter = [
  "import sys",
  "from pathlib import Path",
  "from cadgen import export",
  "script = Path(sys.argv[1])",
  "sys.path.insert(0, str(script.parent))",
  "model = getattr(__import__(script.stem), script.stem)",
  "export(model, sys.argv[2])",
].join("\n");

run(["-c", exporter, script, HERO_GLB]);
const checked = await checkHeroGlb();
console.log(`Hero GLB written: ${path.relative(repoRoot, HERO_GLB)}, ${checked.bytes} bytes, ${checked.clip} turns ${checked.turned} parts.`);
