#!/usr/bin/env node
/**
 * The DXF drawing package's Node builder: DXF text on stdin, `preview.glb` out.
 *
 * Spawned by `cadgen._internal.node_runtime.run_node_builder` from INSIDE the Python
 * producer's `artifact_build` lock, so it inherits that run's id, status record and progress
 * bar and owns none of them (design §4.3). Its whole job is geometry and bytes:
 *
 *   parse (cadjs parseDxf) -> mesh (cadjs buildDxfPreviewMeshData) -> write (writeGlb, render
 *   preset, meshopt-compressed).
 *
 * Contract:
 *   node dxf-artifact.mjs --package-dir <abs> --run-id <id> [--name N]  < drawing.dxf
 *   stdout is NDJSON progress + exactly one terminal `result` line (implicitjs progressStream).
 *   Anything it wants to SAY goes to stderr, which the parent captures and echoes.
 *
 * The drawing arrives on STDIN, never as a path. That is what makes an imported drawing and a
 * generated one indistinguishable here: the producer either reads the user's file or
 * serialises the document its generator just built, and this sees the same bytes either way.
 * It is also why no `.dxf` is written into the package -- __cadgen__ caches what was COMPUTED
 * (the GLB), not a copy of an input the user already has, nor a file it could regenerate.
 *
 * There is no `--thickness-mm`. Thickness is a render-time scale on a prism, not a property of
 * the bake (see DXF_PREVIEW_REFERENCE_THICKNESS_MM), so nothing configurable is frozen into
 * preview.glb and nothing about it needs invalidating.
 *
 * `preview.glb` is written temp + rename, and the parent writes the descriptor only after
 * this exits 0 -- so a reader sees a package with no descriptor (needs-build) rather than a
 * descriptor naming a payload that is missing or half-written.
 */

import fs from "node:fs";
import path from "node:path";

import { MeshoptEncoder } from "meshoptimizer";
import { assertWriteLock } from "implicitjs/glb/assertWriteLock.js";
import {
  reportPhase,
  reportResult,
} from "implicitjs/glb/progressStream.js";

import { parseDxf } from "../src/lib/dxf/parseDxf.js";
import {
  buildDxfPreviewGlb,
  DXF_PREVIEW_BAKE_FORMAT,
  DXF_PREVIEW_REFERENCE_THICKNESS_MM,
} from "../src/lib/dxf/previewGlb.js";

const PREVIEW_GLB_NAME = "preview.glb";
const GEOMETRY_JSON_NAME = "geometry.json";

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
    throw new Error(`dxf-artifact.mjs requires --${name}`);
  }
  return value;
}

/** A boolean flag, written either bare (`--flag`, parsed as "true") or as `--flag 1`. */
function parseFlag(value) {
  const text = String(value || "").trim().toLowerCase();
  return text === "1" || text === "true";
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const packageDir = path.resolve(requireArg(args, "package-dir"));
  const runId = requireArg(args, "run-id");
  const name = String(args.name || path.basename(packageDir) || "drawing");

  // Before anything is read or written: prove this process was started by the lock holder.
  // The parent sets --lock-degraded when it could not take a lock to be started by.
  assertWriteLock(packageDir, runId, { degraded: parseFlag(args["lock-degraded"]) });

  reportPhase("parse");
  // fd 0 read whole: the producer writes the drawing and closes the pipe before we get here,
  // so there is nothing to stream and no partial-read case to handle.
  const dxfText = fs.readFileSync(0, "utf8");
  if (!dxfText.trim()) {
    throw new Error("dxf-artifact.mjs received no DXF on stdin");
  }
  const dxfData = parseDxf(dxfText, { fileRef: name });

  // A dimensioned drawing has no flat pattern: preview.glb is the 3D prism of a CUT profile,
  // and there is no profile to extrude. The producer decides which this is from the file's own
  // DXF apparatus (cadgen.drawing_checks.document_is_drawing) and says so here, so the two
  // never disagree about what the package should contain.
  const drawingProfile = String(args.profile || "cut").trim().toLowerCase() === "drawing";

  let bytes = null;
  let stats = { bendLineCount: 0, bendAxisX: [], triangleCount: 0, vertexCount: 0 };
  if (!drawingProfile) {
    reportPhase("mesh");
    await MeshoptEncoder.ready;
    ({ bytes, stats } = buildDxfPreviewGlb(dxfData, {
      encoder: MeshoptEncoder,
      name,
    }));
  }

  reportPhase("write");
  if (bytes) {
    const previewPath = path.join(packageDir, PREVIEW_GLB_NAME);
    const tempPath = `${previewPath}.tmp-${process.pid}`;
    fs.writeFileSync(tempPath, bytes);
    fs.renameSync(tempPath, previewPath);
  }

  // The parsed 2D geometry, cached so the viewer can RE-MESH live and overlay the drawing's
  // annotations. Curved bends need tessellated bend bands, and the flat prism has no
  // vertices inside the bend region to curve -- so a curved preview is a fresh mesh from the
  // contours, not a transform of the baked one. v2 adds text markings (inside `geometry`),
  // the layer summary (names, semantic kinds, ACI colors) for the viewer's layer toggles,
  // and the source units scale; coordinates are always millimetres.
  const geometryPath = path.join(packageDir, GEOMETRY_JSON_NAME);
  const geometryTemp = `${geometryPath}.tmp-${process.pid}`;
  fs.writeFileSync(geometryTemp, JSON.stringify({
    schema: "dxf-geometry/2",
    geometry: dxfData.geometry,
    layers: dxfData.layers ?? [],
    unitsScaleMm: dxfData.unitsScaleMm ?? 1,
    defaultThicknessMm: dxfData.defaultThicknessMm ?? 0,
  }));
  fs.renameSync(geometryTemp, geometryPath);

  reportResult({
    ok: true,
    // Echoed so the parent can assert that ONE run id spanned both runtimes.
    runId,
    profile: drawingProfile ? "drawing" : "cut",
    preview: bytes ? PREVIEW_GLB_NAME : null,
    geometryFile: GEOMETRY_JSON_NAME,
    bakeFormat: DXF_PREVIEW_BAKE_FORMAT,
    referenceThicknessMm: DXF_PREVIEW_REFERENCE_THICKNESS_MM,
    bytes: bytes ? bytes.length : 0,
    bendLineCount: stats.bendLineCount,
    bendAxisX: stats.bendAxisX,
    triangleCount: stats.triangleCount,
    vertexCount: stats.vertexCount,
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
