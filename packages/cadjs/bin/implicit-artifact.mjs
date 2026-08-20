#!/usr/bin/env node
/**
 * The implicit CAD package's Node builder: `<name>.implicit.js` in, `model.glb` out.
 *
 * Spawned by `cadgen._internal.node_runtime.run_node_builder` from INSIDE the Python
 * producer's `artifact_build` lock, so it inherits that run's id, status record and progress
 * bar and owns none of them (design §4.3). Its whole job is geometry and bytes:
 *
 *   sample (the SDF over a grid) -> polygonize -> weld -> write (writeGlb, render preset,
 *   quantized + meshopt-compressed).
 *
 * Contract:
 *   node implicit-artifact.mjs --package-dir <abs> --source-path <abs> --run-id <id>
 *                              --resolution N --max-cells N [--threads N] [--write-glb <abs>]
 *   stdout is NDJSON progress + exactly one terminal `result` line (implicitjs
 *   progressStream). Anything it wants to SAY goes to stderr, which the parent inherits.
 *
 * **Baked at the model's defaults.** No live params, no animation (§0.1): the model is loaded
 * and `normalizeImplicitCadModel` resolves its `params.*.default` values, and that one mesh
 * is the artifact.
 *
 * **The bake settings are passed in, not chosen here.** The producer owns them, hashes them
 * into the descriptor's `bakeHash`, and both freshness authorities compare that one value. A
 * builder picking its own default would put a setting in the payload that nothing could
 * invalidate.
 *
 * `model.glb` is written temp + rename, and the parent writes the descriptor only after this
 * exits 0 -- so a reader sees a package with no descriptor (needs-build) rather than a
 * descriptor naming a payload that is missing or half-written.
 */

import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { MeshoptEncoder } from "meshoptimizer";
import { assertWriteLock } from "implicitjs/glb/assertWriteLock.js";
import {
  reportAdvance,
  reportPhase,
  reportResult,
  reportTotal,
} from "implicitjs/glb/progressStream.js";
import { meshImplicitCadModelParallel, planeCounts } from "implicitjs/lib/implicitCad/meshWorkers.js";
import {
  buildImplicitExportGlb,
  buildImplicitRenderGlb,
  weldImplicitMesh,
} from "implicitjs/lib/implicitCad/renderGlb.js";
import { normalizeImplicitCadModel } from "implicitjs/model";

import { beginClosureCapture } from "./implicitClosure.mjs";

const MODEL_GLB_NAME = "model.glb";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const next = argv[index + 1];
    if (next === undefined || next.startsWith("--")) {
      args[token.slice(2)] = "true";
    } else {
      args[token.slice(2)] = next;
      index += 1;
    }
  }
  return args;
}

function requireArg(args, name) {
  const value = String(args[name] || "").trim();
  if (!value) {
    throw new Error(`implicit-artifact.mjs requires --${name}`);
  }
  return value;
}

/** A boolean flag, written either bare (`--flag`, parsed as "true") or as `--flag 1`. */
function parseFlag(value) {
  const text = String(value || "").trim().toLowerCase();
  return text === "1" || text === "true";
}

function positiveInt(value, name) {
  const numeric = Math.floor(Number(value));
  if (!Number.isFinite(numeric) || numeric <= 0) {
    throw new Error(`implicit-artifact.mjs requires a positive --${name}`);
  }
  return numeric;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const packageDir = path.resolve(requireArg(args, "package-dir"));
  const sourcePath = path.resolve(requireArg(args, "source-path"));
  const runId = requireArg(args, "run-id");
  const resolution = positiveInt(args.resolution, "resolution");
  const maxCells = positiveInt(args["max-cells"], "max-cells");
  const threads = args.threads === undefined ? undefined : positiveInt(args.threads, "threads");
  // The sibling `<name>.glb` the gen CLI's --write asks for. Written from the SAME mesh pass
  // as the package, in the export preset -- see buildImplicitExportGlb for why it is not a
  // copy of model.glb.
  const writeGlbPath = args["write-glb"] ? path.resolve(String(args["write-glb"])) : null;

  // Before anything is written: prove this process was started by the lock holder.
  // The parent sets --lock-degraded when it could not take a lock to be started by.
  assertWriteLock(packageDir, runId, { degraded: parseFlag(args["lock-degraded"]) });

  // The first phase is reported BEFORE the model is loaded, so the client's ~120 ms first
  // poll finds a bar rather than a bare `generating`. Its denominator follows once the grid
  // is known -- which needs the model, and the model's auto-bounds pass.
  reportPhase("sample");
  const closure = beginClosureCapture(path.dirname(sourcePath));
  const sourceUrl = pathToFileURL(sourcePath).href;
  const model = normalizeImplicitCadModel(await import(sourceUrl), { sourceUrl });

  const meshOptions = { resolution, maxCells, smoothNormals: true };
  const planes = planeCounts(model, meshOptions);
  reportTotal(planes.sample);
  let polygonizeStarted = false;
  const mesh = await meshImplicitCadModelParallel(model, {
    ...meshOptions,
    threads,
    onSamplePlane: (count = 1) => reportAdvance(count),
    onPolygonizePlane: (count = 1) => {
      if (!polygonizeStarted) {
        polygonizeStarted = true;
        reportPhase("polygonize", planes.polygonize);
      }
      reportAdvance(count);
    },
  });
  if (!mesh.triangleCount) {
    throw new Error(
      `Implicit model produced an empty mesh at resolution ${resolution}: ${sourcePath}. `
      + "Check its bounds, parameter defaults, and GLSL sdf()."
    );
  }

  // Welding is its own phase, so it is welded HERE and handed to the writer already indexed
  // (writeGlb passes indexed input straight through) rather than inside the write phase.
  reportPhase("weld");
  const welded = weldImplicitMesh(mesh);

  reportPhase("write");
  await MeshoptEncoder.ready;
  const { bytes, stats, bounds } = buildImplicitRenderGlb(mesh, {
    model,
    encoder: MeshoptEncoder,
    welded,
  });

  const glbPath = path.join(packageDir, MODEL_GLB_NAME);
  const tempPath = `${glbPath}.tmp-${process.pid}`;
  fs.writeFileSync(tempPath, bytes);
  fs.renameSync(tempPath, glbPath);

  let exportBytes = 0;
  if (writeGlbPath) {
    const exported = buildImplicitExportGlb(mesh, { model, welded });
    fs.mkdirSync(path.dirname(writeGlbPath), { recursive: true });
    fs.writeFileSync(writeGlbPath, exported);
    exportBytes = exported.length;
  }

  reportResult({
    ok: true,
    // Echoed so the parent can assert that ONE run id spanned both runtimes.
    runId,
    glb: MODEL_GLB_NAME,
    resolution,
    name: model.name,
    units: model.units,
    bbox: bounds,
    ...stats,
    ...(writeGlbPath ? { writePath: writeGlbPath, writeBytes: exportBytes } : {}),
    // WHICH files the model loaded. The parent hashes them: one closure digest, in Python,
    // for every package format (design §5.2).
    closureFiles: closure.files(),
  });
}

try {
  await main();
} catch (error) {
  // stderr is the diagnostic channel (inherited by the parent); a non-zero exit is what the
  // parent turns into a failed run, and the descriptor is never written.
  process.stderr.write(`${error?.stack || error}\n`);
  process.exit(1);
}
